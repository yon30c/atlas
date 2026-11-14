"""SQLite-backed recovery gate projection bound to one authenticated journal.

This adapter implements RecoveryGatePort only. It is not the complete
ProtectedMemoryRecoveryAuthorityPort and does not serialize read admission or
protected egress until those operations share this same transaction boundary.
"""
from datetime import datetime, timezone

from atlas.adapters.sqlite.consistency_journal import SQLiteConsistencyJournal
from atlas.core.errors import ContractError
from atlas.memory.journal import (
    ConsistencyPosition,
    ConsistencyRecordKind,
    ConsistencyTransition,
    JournalCommit,
)
from atlas.memory.recovery_completion import VerifiedRecoveryCompletionReceipt
from atlas.memory.trust import (
    ConsistencyRecoveryVerificationResult,
    ConsistencyRecoveryVerificationStatus,
)
from atlas.ports.recovery_gate import RecoveryGatePort


def _utc_text(value: datetime) -> str:
    return value.isoformat(timespec="microseconds")


class _AbortGateTransaction(Exception):
    """Internal sentinel used to force rollback when journal append is rejected."""


class LocalSQLiteRecoveryGateAdapter(RecoveryGatePort):
    """Persist gate projection and its authenticated journal event atomically.

    Every operation first obtains a locally VERIFIED recovery snapshot, then
    rechecks its exact head under BEGIN IMMEDIATE before writing. The journal
    event and gate projection share one SQLiteUnitOfWork.
    """

    def __init__(self, journal: SQLiteConsistencyJournal) -> None:
        if not isinstance(journal, SQLiteConsistencyJournal):
            raise ContractError("journal debe ser SQLiteConsistencyJournal")
        if journal.recovery_trust_policy is None:
            raise ContractError(
                "journal debe tener recovery_verifier y recovery_trust_policy configurados"
            )
        self._journal = journal
        self._database = journal._database

    @property
    def consistency_journal(self) -> SQLiteConsistencyJournal:
        """Exact journal instance whose SQLite database this adapter updates."""
        return self._journal

    def _verified_snapshot(self, domain_id: str):
        try:
            result = self._journal.load_verified_recovery_state(domain_id)
        except Exception:
            return None
        if (
            not isinstance(result, ConsistencyRecoveryVerificationResult)
            or result.status is not ConsistencyRecoveryVerificationStatus.VERIFIED
            or result.verified_local_state is None
        ):
            return None
        verified = result.verified_local_state
        state = verified.state
        projection = verified.projection
        if (
            state.domain_id != domain_id
            or verified.consistency_domain_id != domain_id
            or verified.authority_epoch != state.authority_epoch
            or verified.head_sequence != state.head_sequence
            or projection is None
            or projection.domain_id != domain_id
            or projection.authority_epoch != state.authority_epoch
            or projection.head_sequence != state.head_sequence
        ):
            return None
        return state, projection

    @staticmethod
    def _head_commitment(state) -> str | None:
        if state.head_sequence == 0:
            return None
        if state.entries:
            envelope = state.entries[-1].envelope
        elif state.checkpoint is not None:
            envelope = state.checkpoint.envelope
        else:
            return None
        return envelope.object_commitment if envelope is not None else None

    def _domain_row_matches(self, row, state) -> bool:
        return bool(
            row is not None
            and row["profile"] == "local"
            and row["trust_policy_version"] == self._journal.trust_policy_version
            and row["authority_epoch"] == state.authority_epoch
            and row["head_sequence"] == state.head_sequence
            and row["head_commitment"] == self._head_commitment(state)
        )

    @staticmethod
    def _active_closures(projection):
        return tuple(item for item in projection.recovery_closures if not item.reconciled)

    @staticmethod
    def _latest_closure(projection):
        if not projection.recovery_closures:
            return None
        return max(projection.recovery_closures, key=lambda item: item.generation)

    @staticmethod
    def _same_recovery_transition(transition, closure) -> bool:
        return bool(
            transition.operation_id == closure.operation_id
            and transition.generation == closure.generation
            and transition.affected_admission_ids == closure.affected_admission_ids
            and transition.route_ids == closure.route_ids
        )

    @staticmethod
    def _update_projection(
        connection,
        *,
        domain_id: str,
        epoch: int,
        head_sequence: int,
        head_commitment: str | None,
        gate_state: str,
        operation_id: str | None,
        generation: int | None,
        receipt_id: str | None,
    ) -> bool:
        updated = connection.execute(
            """
            UPDATE consistency_domains
            SET recovery_gate_state=?,
                active_recovery_operation_id=?,
                active_recovery_generation=?,
                recovery_receipt_id=?,
                updated_at=?
            WHERE domain_id=?
              AND authority_epoch=?
              AND head_sequence=?
              AND head_commitment IS ?
            """,
            (
                gate_state,
                operation_id,
                generation,
                receipt_id,
                _utc_text(datetime.now(timezone.utc)),
                domain_id,
                epoch,
                head_sequence,
                head_commitment,
            ),
        )
        return updated.rowcount == 1

    def close_recovery_gate(
        self,
        expected_position: ConsistencyPosition,
        transition: ConsistencyTransition,
    ) -> JournalCommit | None:
        """Atomically append RECOVERY_CLOSED and materialize the closed gate."""
        if (
            not isinstance(expected_position, ConsistencyPosition)
            or not isinstance(transition, ConsistencyTransition)
            or transition.record_kind is not ConsistencyRecordKind.RECOVERY_CLOSED
        ):
            return None
        domain_id = expected_position.consistency_domain_id
        snapshot = self._verified_snapshot(domain_id)
        if snapshot is None:
            return None
        state, projection = snapshot
        if (
            expected_position.authority_epoch != state.authority_epoch
            or expected_position.sequence != state.head_sequence
        ):
            return None

        active = self._active_closures(projection)
        # An existing closure must be restored through ensure_recovery_gate_closed.
        if active:
            return None
        pending_admissions = tuple(
            item for item in projection.admissions
            if item.status.value not in ("completed", "cancelled")
        )
        expected_admissions = frozenset(item.admission_id for item in pending_admissions)
        expected_routes = frozenset(
            route_id for item in pending_admissions for route_id in item.route_ids
        )
        prior_generations = (
            [item.generation for item in projection.admissions]
            + [item.generation for item in projection.forget_closures]
            + [item.generation for item in projection.invalidations]
            + [item.generation for item in projection.recovery_closures]
        )
        forget_admission_ids = frozenset(
            admission_id
            for closure in projection.forget_closures
            for admission_id in closure.affected_admission_ids
        )
        terminal_admission_ids = frozenset(
            item.admission_id for item in projection.admissions
            if item.status.value in ("completed", "cancelled")
        )
        if (
            not expected_admissions
            or not expected_routes
            or transition.operation_id != (
                f"recovery:{domain_id}:{state.authority_epoch}:{transition.generation}"
            )
            or transition.affected_admission_ids != expected_admissions
            or transition.route_ids != expected_routes
            or (
                prior_generations
                and transition.generation <= max(prior_generations)
            )
            or any(not item.reconciled for item in projection.invalidations)
            or not forget_admission_ids.issubset(terminal_admission_ids)
        ):
            return None

        commit = None
        try:
            with self._database.unit_of_work() as unit_of_work:
                connection = unit_of_work._connection_for(self._database)
                row = connection.execute(
                    "SELECT * FROM consistency_domains WHERE domain_id=?",
                    (domain_id,),
                ).fetchone()
                if not self._domain_row_matches(row, state):
                    raise _AbortGateTransaction()
                if (
                    row["active_recovery_operation_id"] is not None
                    or row["active_recovery_generation"] is not None
                ):
                    raise _AbortGateTransaction()

                commit = self._journal.append_transition_in(
                    unit_of_work,
                    expected_position,
                    f"append:{transition.record_id}",
                    transition,
                )
                if commit is None or commit.record_id != transition.record_id:
                    raise _AbortGateTransaction()

                current = connection.execute(
                    "SELECT head_sequence, head_commitment FROM consistency_domains WHERE domain_id=?",
                    (domain_id,),
                ).fetchone()
                if current is None or current["head_sequence"] != commit.position.sequence:
                    raise _AbortGateTransaction()
                if not self._update_projection(
                    connection,
                    domain_id=domain_id,
                    epoch=state.authority_epoch,
                    head_sequence=current["head_sequence"],
                    head_commitment=current["head_commitment"],
                    gate_state="closed",
                    operation_id=transition.operation_id,
                    generation=transition.generation,
                    receipt_id=None,
                ):
                    raise _AbortGateTransaction()
        except Exception:
            return None
        return commit

    def ensure_recovery_gate_closed(
        self, operation_id: str, generation: int
    ) -> bool:
        """Restore only the exact active closure proven by the verified journal."""
        if not isinstance(operation_id, str) or not operation_id.strip():
            return False
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            return False
        snapshot = self._verified_snapshot(self._journal.recovery_trust_policy.consistency_domain_id)
        if snapshot is None:
            return False
        state, projection = snapshot
        active = self._active_closures(projection)
        if (
            len(active) != 1
            or active[0].operation_id != operation_id
            or active[0].generation != generation
            or self._latest_closure(projection) != active[0]
        ):
            return False
        try:
            with self._database.unit_of_work() as unit_of_work:
                connection = unit_of_work._connection_for(self._database)
                row = connection.execute(
                    "SELECT * FROM consistency_domains WHERE domain_id=?",
                    (state.domain_id,),
                ).fetchone()
                if not self._domain_row_matches(row, state):
                    raise _AbortGateTransaction()
                if (
                    row["recovery_gate_state"] == "closed"
                    and row["active_recovery_operation_id"] == operation_id
                    and row["active_recovery_generation"] == generation
                    and row["recovery_receipt_id"] is None
                ):
                    return True
                if not self._update_projection(
                    connection,
                    domain_id=state.domain_id,
                    epoch=state.authority_epoch,
                    head_sequence=state.head_sequence,
                    head_commitment=self._head_commitment(state),
                    gate_state="closed",
                    operation_id=operation_id,
                    generation=generation,
                    receipt_id=None,
                ):
                    raise _AbortGateTransaction()
            return True
        except Exception:
            return False

    def reconcile_and_open_recovery_gate(
        self,
        expected_position: ConsistencyPosition,
        transition: ConsistencyTransition,
        verified_receipt: VerifiedRecoveryCompletionReceipt,
    ) -> JournalCommit | None:
        """Atomically persist verified RECOVERY_RECONCILED and open the gate."""
        if (
            not isinstance(expected_position, ConsistencyPosition)
            or not isinstance(transition, ConsistencyTransition)
            or transition.record_kind is not ConsistencyRecordKind.RECOVERY_RECONCILED
            or not isinstance(verified_receipt, VerifiedRecoveryCompletionReceipt)
        ):
            return None
        receipt = verified_receipt.receipt
        if (
            receipt.consistency_domain_id != expected_position.consistency_domain_id
            or receipt.authority_epoch != expected_position.authority_epoch
            or receipt.operation_id != transition.operation_id
            or receipt.generation != transition.generation
            or receipt.receipt_id != transition.receipt_id
            or receipt.affected_admission_ids != transition.affected_admission_ids
            or receipt.route_ids != transition.route_ids
        ):
            return None

        domain_id = expected_position.consistency_domain_id
        snapshot = self._verified_snapshot(domain_id)
        if snapshot is None:
            return None
        state, projection = snapshot
        if expected_position.authority_epoch != state.authority_epoch:
            return None

        active = self._active_closures(projection)
        matching = next(
            (
                item for item in projection.recovery_closures
                if item.operation_id == transition.operation_id
                and item.generation == transition.generation
            ),
            None,
        )
        if matching is None or self._latest_closure(projection) != matching:
            return None
        if not self._same_recovery_transition(transition, matching):
            return None
        if matching.reconciled:
            if (
                matching.terminal_receipt_id != receipt.receipt_id
                or active
                or expected_position.sequence >= state.head_sequence
            ):
                return None
            already_reconciled = True
        else:
            if (
                len(active) != 1
                or active[0] != matching
                or expected_position.sequence != state.head_sequence
                or any(
                    admission.status.value not in ("completed", "cancelled")
                    for admission in projection.admissions
                    if admission.admission_id in matching.affected_admission_ids
                )
            ):
                return None
            already_reconciled = False

        commit = None
        try:
            with self._database.unit_of_work() as unit_of_work:
                connection = unit_of_work._connection_for(self._database)
                row = connection.execute(
                    "SELECT * FROM consistency_domains WHERE domain_id=?",
                    (domain_id,),
                ).fetchone()
                if not self._domain_row_matches(row, state):
                    raise _AbortGateTransaction()
                if already_reconciled:
                    if not (
                        row["recovery_gate_state"] == "open"
                        and row["active_recovery_operation_id"] is None
                        and row["active_recovery_generation"] is None
                        and row["recovery_receipt_id"] == receipt.receipt_id
                    ):
                        raise _AbortGateTransaction()
                else:
                    if not (
                        row["recovery_gate_state"] == "closed"
                        and row["active_recovery_operation_id"] == matching.operation_id
                        and row["active_recovery_generation"] == matching.generation
                        and row["recovery_receipt_id"] is None
                    ):
                        raise _AbortGateTransaction()

                commit = self._journal.append_transition_in(
                    unit_of_work,
                    expected_position,
                    f"append:{transition.record_id}",
                    transition,
                )
                if commit is None or commit.record_id != transition.record_id:
                    raise _AbortGateTransaction()
                if not already_reconciled:
                    current = connection.execute(
                        "SELECT head_sequence, head_commitment FROM consistency_domains WHERE domain_id=?",
                        (domain_id,),
                    ).fetchone()
                    if current is None or current["head_sequence"] != commit.position.sequence:
                        raise _AbortGateTransaction()
                    if not self._update_projection(
                        connection,
                        domain_id=domain_id,
                        epoch=state.authority_epoch,
                        head_sequence=current["head_sequence"],
                        head_commitment=current["head_commitment"],
                        gate_state="open",
                        operation_id=None,
                        generation=None,
                        receipt_id=receipt.receipt_id,
                    ):
                        raise _AbortGateTransaction()
        except Exception:
            return None
        return commit

    def ensure_recovery_gate_open(
        self, operation_id: str, generation: int, receipt_id: str | None
    ) -> bool:
        """Restore open state only for the latest verified terminal recovery event."""
        if (
            not isinstance(operation_id, str) or not operation_id.strip()
            or isinstance(generation, bool) or not isinstance(generation, int) or generation < 1
            or not isinstance(receipt_id, str) or not receipt_id.strip()
        ):
            return False
        snapshot = self._verified_snapshot(self._journal.recovery_trust_policy.consistency_domain_id)
        if snapshot is None:
            return False
        state, projection = snapshot
        closure = next(
            (
                item for item in projection.recovery_closures
                if item.operation_id == operation_id and item.generation == generation
            ),
            None,
        )
        if (
            closure is None
            or not closure.reconciled
            or closure.terminal_receipt_id != receipt_id
            or self._latest_closure(projection) != closure
            or self._active_closures(projection)
        ):
            return False
        try:
            with self._database.unit_of_work() as unit_of_work:
                connection = unit_of_work._connection_for(self._database)
                row = connection.execute(
                    "SELECT * FROM consistency_domains WHERE domain_id=?",
                    (state.domain_id,),
                ).fetchone()
                if not self._domain_row_matches(row, state):
                    raise _AbortGateTransaction()
                if (
                    row["recovery_gate_state"] == "open"
                    and row["active_recovery_operation_id"] is None
                    and row["active_recovery_generation"] is None
                    and row["recovery_receipt_id"] == receipt_id
                ):
                    return True
                if not self._update_projection(
                    connection,
                    domain_id=state.domain_id,
                    epoch=state.authority_epoch,
                    head_sequence=state.head_sequence,
                    head_commitment=self._head_commitment(state),
                    gate_state="open",
                    operation_id=None,
                    generation=None,
                    receipt_id=receipt_id,
                ):
                    raise _AbortGateTransaction()
            return True
        except Exception:
            return False
