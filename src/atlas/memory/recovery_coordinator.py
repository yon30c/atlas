"""Journal-first orchestration for fail-closed admission recovery.

The coordinator persists the domain recovery gate before contacting any endpoint.
It records each independently verified endpoint fence immediately, allowing a
later invocation to resume without reopening old emitters. It deliberately does
not terminalize admissions or reconcile the recovery operation.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable

from atlas.core.errors import ContractError
from atlas.memory.journal import (
    ConsistencyPosition,
    ConsistencyRecordKind,
    ConsistencyTransition,
)
from atlas.memory.journal_reducer import (
    ConsistencyJournalReducer,
    ConsistencyProjection,
    EndpointProjectionStatus,
)
from atlas.memory.trust import (
    ConsistencyRecoveryVerificationResult,
    ConsistencyRecoveryVerificationStatus,
)
from atlas.memory.recovery import (
    RecoveryEndpointSequence,
    RecoveryFencePlan,
    UnresolvedAdmissionRecovery,
    build_recovery_fence_plan,
    execute_recovery_fencing,
)
from atlas.ports.consistency_journal import ConsistencyJournalPort
from atlas.ports.recovery_gate import RecoveryGatePort


class RecoveryCoordinatorStatus(str, Enum):
    FENCING_RECORDED = "fencing_recorded"
    PENDING = "pending"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class RecoveryCoordinatorResult:
    status: RecoveryCoordinatorStatus
    operation_id: str | None
    generation: int | None
    recorded_endpoint_ids: tuple[tuple[str, str], ...]
    pending_endpoint_ids: tuple[tuple[str, str], ...]


class RecoveryJournalCoordinator:
    """Journal-first, resumable coordinator; no read capability is restored."""

    def __init__(
        self,
        journal: ConsistencyJournalPort,
        recovery_gate: RecoveryGatePort,
        fencer: object,
        verifier: object,
        *,
        trust_context_factory: object,
        domain_id: str,
        id_factory: Callable[[], str],
        clock: Callable[[], datetime],
    ) -> None:
        if not callable(getattr(journal, "load_verified_recovery_state", None)) or not callable(
            getattr(journal, "append_transition", None)
        ):
            raise ContractError("journal debe implementar ConsistencyJournalPort")
        if not callable(getattr(verifier, "verify_terminal_receipt_with_context", None)):
            raise ContractError("verifier debe implementar TerminalReceiptVerifierPort trust-aware")
        if not callable(getattr(trust_context_factory, "for_terminal_receipt", None)):
            raise ContractError("trust_context_factory debe implementar ReceiptTrustContextFactoryPort")
        if not callable(id_factory) or not callable(clock):
            raise ContractError("id_factory y clock deben ser invocables")
        if not isinstance(domain_id, str) or not domain_id.strip():
            raise ContractError("domain_id debe ser no vacío")
        if (
            not callable(getattr(recovery_gate, "close_recovery_gate", None))
            or not callable(getattr(recovery_gate, "ensure_recovery_gate_closed", None))
        ):
            raise ContractError("recovery_gate debe implementar RecoveryGatePort completo")
        self._journal = journal
        self._recovery_gate = recovery_gate
        self._fencer = fencer
        self._verifier = verifier
        self._trust_context_factory = trust_context_factory
        self._domain_id = domain_id
        self._id_factory = id_factory
        self._clock = clock
        self._reducer = ConsistencyJournalReducer()

    def _load(self) -> tuple[object, ConsistencyProjection] | None:
        try:
            result = self._journal.load_verified_recovery_state(self._domain_id)
            if (
                not isinstance(result, ConsistencyRecoveryVerificationResult)
                or result.status is not ConsistencyRecoveryVerificationStatus.VERIFIED
                or result.verified_state is None
            ):
                return None
            state = result.verified_state.state
            if state.domain_id != self._domain_id:
                return None
            return state, self._reducer.reduce(state)
        except Exception:
            return None

    def _append(self, state: object, transition: ConsistencyTransition) -> bool:
        expected = ConsistencyPosition(
            state.domain_id, state.authority_epoch, state.head_sequence
        )
        try:
            commit = self._journal.append_transition(expected, transition)
            if (
                commit is None
                or commit.record_id != transition.record_id
                or commit.position.consistency_domain_id != state.domain_id
                or commit.position.authority_epoch != state.authority_epoch
                or commit.position.sequence != state.head_sequence + 1
            ):
                return False
            loaded = self._load()
            return bool(
                loaded is not None
                and loaded[0].head_sequence == commit.position.sequence
            )
        except Exception:
            return False

    def _close_gate(
        self, state: object, transition: ConsistencyTransition
    ) -> bool:
        expected = ConsistencyPosition(
            state.domain_id, state.authority_epoch, state.head_sequence
        )
        try:
            commit = self._recovery_gate.close_recovery_gate(expected, transition)
            if (
                commit is None
                or commit.record_id != transition.record_id
                or commit.position.consistency_domain_id != state.domain_id
                or commit.position.authority_epoch != state.authority_epoch
                or commit.position.sequence != state.head_sequence + 1
            ):
                return False
            loaded = self._load()
            return bool(
                loaded is not None
                and loaded[0].head_sequence == commit.position.sequence
            )
        except Exception:
            return False

    def _new_transition(
        self, kind: ConsistencyRecordKind, operation_id: str, **fields: object
    ) -> ConsistencyTransition | None:
        try:
            now = self._clock()
            if (
                not isinstance(now, datetime)
                or now.tzinfo is None
                or now.utcoffset() != timedelta(0)
            ):
                return None
            return ConsistencyTransition(
                record_id=self._id_factory(),
                schema_version=1,
                record_kind=kind,
                operation_id=operation_id,
                occurred_at=now,
                **fields,
            )
        except Exception:
            return None

    @staticmethod
    def _active_recovery(
        projection: ConsistencyProjection,
    ):
        pending = tuple(
            item for item in projection.recovery_closures if not item.reconciled
        )
        return pending[0] if len(pending) == 1 else None

    def _ensure_closed(
        self, state: object, projection: ConsistencyProjection
    ) -> tuple[str, int] | None:
        active = self._active_recovery(projection)
        if active is not None:
            try:
                restored = self._recovery_gate.ensure_recovery_gate_closed(
                    active.operation_id, active.generation
                )
            except Exception:
                return None
            if restored is not True:
                return None
            return active.operation_id, active.generation
        if any(not item.reconciled for item in projection.recovery_closures):
            return None

        admissions_by_id = {
            item.admission_id: item for item in projection.admissions
        }
        if any(not item.reconciled for item in projection.invalidations):
            return None
        if any(
            admission_id not in admissions_by_id
            or admissions_by_id[admission_id].status.value
            not in ("completed", "cancelled")
            for closure in projection.forget_closures
            for admission_id in closure.affected_admission_ids
        ):
            return None

        generations = (
            [item.generation for item in projection.admissions]
            + [item.generation for item in projection.forget_closures]
            + [item.generation for item in projection.invalidations]
            + [item.generation for item in projection.recovery_closures]
        )
        generation = max(generations, default=0) + 1
        plan = build_recovery_fence_plan(projection, generation)
        if plan is None or not plan.admissions:
            return None
        affected = frozenset(item.admission_id for item in plan.admissions)
        routes = frozenset(
            endpoint.endpoint_id
            for admission in plan.admissions
            for endpoint in admission.endpoint_sequences
        )
        transition = self._new_transition(
            ConsistencyRecordKind.RECOVERY_CLOSED,
            plan.operation_id,
            generation=generation,
            route_ids=routes,
            affected_admission_ids=affected,
        )
        if transition is None or not self._close_gate(state, transition):
            return None
        return plan.operation_id, generation

    def run(self) -> RecoveryCoordinatorResult:
        loaded = self._load()
        if loaded is None:
            return RecoveryCoordinatorResult(
                RecoveryCoordinatorStatus.BLOCKED, None, None, (), ()
            )
        state, projection = loaded
        closed = self._ensure_closed(state, projection)
        if closed is None:
            return RecoveryCoordinatorResult(
                RecoveryCoordinatorStatus.BLOCKED, None, None, (), ()
            )
        operation_id, generation = closed

        recorded: list[tuple[str, str]] = []
        pending: list[tuple[str, str]] = []
        loaded = self._load()
        if loaded is None:
            return RecoveryCoordinatorResult(
                RecoveryCoordinatorStatus.PENDING, operation_id, generation, (), ()
            )
        _, projection = loaded
        plan = build_recovery_fence_plan(projection, generation)
        if plan is None or plan.operation_id != operation_id:
            return RecoveryCoordinatorResult(
                RecoveryCoordinatorStatus.BLOCKED, operation_id, generation, (), ()
            )

        endpoint_projection = {
            (admission.admission_id, endpoint.endpoint_id): endpoint
            for admission in projection.admissions
            for endpoint in admission.endpoints
        }
        for admission in plan.admissions:
            for endpoint in admission.endpoint_sequences:
                key = (admission.admission_id, endpoint.endpoint_id)
                current_endpoint = endpoint_projection.get(key)
                if (
                    current_endpoint is not None
                    and current_endpoint.status is EndpointProjectionStatus.FENCED
                    and current_endpoint.terminal_operation_id == operation_id
                    and current_endpoint.terminal_generation == generation
                ):
                    recorded.append(key)
                    continue
                if (
                    current_endpoint is not None
                    and current_endpoint.status is EndpointProjectionStatus.FENCED
                ):
                    pending.append(key)
                    continue
                single = UnresolvedAdmissionRecovery(
                    admission_id=admission.admission_id,
                    old_generation=admission.old_generation,
                    route_ids=frozenset({endpoint.endpoint_id}),
                    endpoint_sequences=(endpoint,),
                    target=admission.target,
                    recoverable=admission.recoverable,
                )
                single_plan = RecoveryFencePlan(
                    consistency_domain_id=plan.consistency_domain_id,
                    authority_epoch=plan.authority_epoch,
                    operation_id=plan.operation_id,
                    generation=plan.generation,
                    admissions=(single,),
                )
                try:
                    verification_time = self._clock()
                    batch = execute_recovery_fencing(
                        single_plan,
                        self._fencer,
                        self._verifier,
                        self._trust_context_factory,
                        verification_time,
                    )
                except Exception:
                    batch = None
                if batch is None:
                    pending.append(key)
                    continue
                receipt = batch.verified_receipts[0]
                transition = self._new_transition(
                    ConsistencyRecordKind.ENDPOINT_FENCED,
                    operation_id,
                    admission_id=admission.admission_id,
                    endpoint_id=endpoint.endpoint_id,
                    generation=generation,
                    receipt_id=receipt.receipt_id,
                )
                latest = self._load()
                if (
                    transition is None
                    or latest is None
                    or not self._append(latest[0], transition)
                ):
                    pending.append(key)
                    continue
                recorded.append(key)

        final = self._load()
        if final is None:
            status = RecoveryCoordinatorStatus.PENDING
        else:
            projection = final[1]
            all_fenced = all(
                endpoint.status is EndpointProjectionStatus.FENCED
                and endpoint.terminal_operation_id == operation_id
                and endpoint.terminal_generation == generation
                for admission in projection.admissions
                if admission.admission_id in {
                    item.admission_id
                    for item in plan.admissions
                }
                for endpoint in admission.endpoints
            )
            status = (
                RecoveryCoordinatorStatus.FENCING_RECORDED
                if all_fenced and not pending
                else RecoveryCoordinatorStatus.PENDING
            )
        return RecoveryCoordinatorResult(
            status, operation_id, generation, tuple(recorded), tuple(pending)
        )
