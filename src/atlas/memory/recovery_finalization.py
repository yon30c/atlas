"""Finalización verificable de admisiones durante recuperación ME-03J.

Este coordinador solo registra ADMISSION_RECONCILED. Nunca registra
RECOVERY_RECONCILED ni reabre el gate; esa operación requiere otra frontera
atómica después de validar el conjunto completo.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable

from atlas.core.errors import ContractError
from atlas.memory.consistency import ReadAdmissionStatus
from atlas.memory.journal import (
    ConsistencyPosition,
    ConsistencyRecordKind,
    ConsistencyTransition,
)
from atlas.memory.journal_reducer import (
    AdmissionProjection,
    ConsistencyJournalReducer,
    ConsistencyProjection,
    EndpointProjectionStatus,
)
from atlas.memory.trust import (
    ConsistencyRecoveryVerificationResult,
    ConsistencyRecoveryVerificationStatus,
)
from atlas.memory.receipt_verification import (
    TerminalReceiptKind,
    TerminalReceiptVerificationRequest,
    VerifiedTerminalReceipt,
)
from atlas.memory.receipt_trust import verify_terminal_receipt_with_context
from atlas.ports.consistency_journal import ConsistencyJournalPort


def _required(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacía")


@dataclass(frozen=True, slots=True)
class RecoveryAdmissionFinalizationRequest:
    consistency_domain_id: str
    authority_epoch: int
    operation_id: str
    admission_id: str
    previous_generation: int
    generation: int
    route_ids: frozenset[str]
    endpoint_receipts: tuple[VerifiedTerminalReceipt, ...]

    def __post_init__(self) -> None:
        for field in ("consistency_domain_id", "operation_id", "admission_id"):
            _required(getattr(self, field), field)
        if isinstance(self.authority_epoch, bool) or not isinstance(self.authority_epoch, int) or self.authority_epoch < 1:
            raise ContractError("authority_epoch debe ser positivo")
        if isinstance(self.previous_generation, bool) or not isinstance(self.previous_generation, int) or self.previous_generation < 1:
            raise ContractError("previous_generation debe ser positiva")
        if isinstance(self.generation, bool) or not isinstance(self.generation, int) or self.generation <= self.previous_generation:
            raise ContractError("generation debe superar previous_generation")
        if not isinstance(self.route_ids, frozenset) or not self.route_ids:
            raise ContractError("route_ids debe ser frozenset no vacío")
        if not isinstance(self.endpoint_receipts, tuple) or not self.endpoint_receipts:
            raise ContractError("endpoint_receipts debe ser una tupla no vacía")
        endpoints = []
        receipt_ids = set()
        verification_ids = set()
        for receipt in self.endpoint_receipts:
            if not isinstance(receipt, VerifiedTerminalReceipt):
                raise ContractError("endpoint_receipts contiene evidencia inválida")
            if (
                receipt.consistency_domain_id != self.consistency_domain_id
                or receipt.authority_epoch != self.authority_epoch
                or receipt.operation_id != self.operation_id
                or receipt.admission_id != self.admission_id
                or receipt.kind is not TerminalReceiptKind.ENDPOINT_FENCED
                or receipt.generation != self.generation
                or receipt.previous_generation != self.previous_generation
                or receipt.endpoint_id is None
            ):
                raise ContractError("endpoint receipt no corresponde a la finalización exacta")
            if (
                receipt.endpoint_id in endpoints
                or receipt.receipt_id in receipt_ids
                or receipt.verification_id in verification_ids
            ):
                raise ContractError("endpoint receipt duplicado")
            endpoints.append(receipt.endpoint_id)
            receipt_ids.add(receipt.receipt_id)
            verification_ids.add(receipt.verification_id)
        if frozenset(endpoints) != self.route_ids:
            raise ContractError("endpoint_receipts debe cubrir exactamente route_ids")


@dataclass(frozen=True, slots=True)
class RecoveryAdmissionTerminalReceipt:
    consistency_domain_id: str
    authority_epoch: int
    operation_id: str
    admission_id: str
    generation: int
    receipt_id: str

    def __post_init__(self) -> None:
        _required(self.consistency_domain_id, "consistency_domain_id")
        if isinstance(self.authority_epoch, bool) or not isinstance(self.authority_epoch, int) or self.authority_epoch < 1:
            raise ContractError("authority_epoch debe ser positiva")
        _required(self.operation_id, "operation_id")
        _required(self.admission_id, "admission_id")
        _required(self.receipt_id, "receipt_id")
        if isinstance(self.generation, bool) or not isinstance(self.generation, int) or self.generation < 1:
            raise ContractError("generation debe ser positiva")


class RecoveryAdmissionFinalizationStatus(str, Enum):
    ADMISSIONS_TERMINAL = "admissions_terminal"
    PENDING = "pending"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class RecoveryAdmissionFinalizationResult:
    status: RecoveryAdmissionFinalizationStatus
    operation_id: str | None
    generation: int | None
    reconciled_admission_ids: tuple[str, ...]
    pending_admission_ids: tuple[str, ...]


class RecoveryAdmissionFinalizationCoordinator:
    """Verifica endpoint fences y registra terminalidad de admisiones, fail-closed."""

    def __init__(
        self,
        journal: ConsistencyJournalPort,
        finalizer: object,
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
        if not callable(getattr(finalizer, "finalize_cancelled_admission", None)):
            raise ContractError("finalizer debe implementar RecoveryAdmissionFinalizerPort")
        if not callable(getattr(verifier, "verify_terminal_receipt_with_context", None)):
            raise ContractError("verifier debe implementar TerminalReceiptVerifierPort trust-aware")
        if not callable(getattr(trust_context_factory, "for_terminal_receipt", None)):
            raise ContractError("trust_context_factory debe implementar ReceiptTrustContextFactoryPort")
        if not callable(id_factory) or not callable(clock):
            raise ContractError("id_factory y clock deben ser invocables")
        _required(domain_id, "domain_id")
        self._journal = journal
        self._finalizer = finalizer
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
                or result.state is None
            ):
                return None
            state = result.state
            if state.domain_id != self._domain_id:
                return None
            return state, self._reducer.reduce(state)
        except Exception:
            return None

    def _verify_endpoint_fences(
        self,
        state: object,
        closure_operation_id: str,
        closure_generation: int,
        admission: AdmissionProjection,
    ) -> tuple[VerifiedTerminalReceipt, ...] | None:
        if (
            not admission.route_ids
            or len(admission.endpoints) != len(admission.route_ids)
            or {item.endpoint_id for item in admission.endpoints} != admission.route_ids
        ):
            return None
        verified = []
        for endpoint in admission.endpoints:
            if (
                endpoint.status is not EndpointProjectionStatus.FENCED
                or endpoint.terminal_operation_id != closure_operation_id
                or endpoint.terminal_generation != closure_generation
                or endpoint.terminal_receipt_id is None
            ):
                return None
            request = TerminalReceiptVerificationRequest(
                consistency_domain_id=state.domain_id,
                authority_epoch=state.authority_epoch,
                operation_id=closure_operation_id,
                admission_id=admission.admission_id,
                receipt_id=endpoint.terminal_receipt_id,
                kind=TerminalReceiptKind.ENDPOINT_FENCED,
                generation=closure_generation,
                endpoint_id=endpoint.endpoint_id,
                previous_generation=admission.generation,
                fenced_through_sequence=endpoint.last_emission_sequence,
            )
            try:
                receipt = verify_terminal_receipt_with_context(
                    self._verifier,
                    self._trust_context_factory,
                    request,
                    purpose="recovery-admission-endpoint-fencing",
                    verification_time=self._clock(),
                )
            except Exception:
                return None
            if receipt is None:
                return None
            verified.append(receipt)
        return tuple(verified)

    def _append_and_confirm(
        self,
        state: object,
        transition: ConsistencyTransition,
    ) -> bool:
        expected = ConsistencyPosition(
            state.domain_id, state.authority_epoch, state.head_sequence
        )
        try:
            commit = self._journal.append_transition(
                expected, f"append:{transition.record_id}", transition
            )
            if commit is not None and (
                commit.position.consistency_domain_id != state.domain_id
                or commit.position.authority_epoch != state.authority_epoch
                or (
                    not commit.replayed
                    and (
                        commit.record_id != transition.record_id
                        or commit.position.sequence != state.head_sequence + 1
                    )
                )
                or (commit.replayed and commit.position.sequence > state.head_sequence)
            ):
                return False
        except Exception:
            # Append outcome is ambiguous: reload below before deciding.
            pass
        latest = self._load()
        if latest is None:
            return False
        projection = latest[1]
        item = next(
            (value for value in projection.admissions
             if value.admission_id == transition.admission_id),
            None,
        )
        return bool(
            item is not None
            and item.status is ReadAdmissionStatus.CANCELLED
            and item.terminal_operation_id == transition.operation_id
            and item.terminal_generation == transition.generation
            and item.terminal_receipt_id == transition.receipt_id
        )

    def run(self) -> RecoveryAdmissionFinalizationResult:
        loaded = self._load()
        if loaded is None:
            return RecoveryAdmissionFinalizationResult(
                RecoveryAdmissionFinalizationStatus.BLOCKED, None, None, (), ()
            )
        state, projection = loaded
        active = tuple(item for item in projection.recovery_closures if not item.reconciled)
        if len(active) != 1:
            return RecoveryAdmissionFinalizationResult(
                RecoveryAdmissionFinalizationStatus.BLOCKED, None, None, (), ()
            )
        closure = active[0]
        reconciled = []
        pending = []
        for admission_id in sorted(closure.affected_admission_ids):
            current = self._load()
            if current is None:
                pending.append(admission_id)
                continue
            state, projection = current
            admission = next(
                (item for item in projection.admissions if item.admission_id == admission_id),
                None,
            )
            if admission is None:
                pending.append(admission_id)
                continue
            if (
                admission.status is ReadAdmissionStatus.CANCELLED
                and admission.terminal_operation_id == closure.operation_id
                and admission.terminal_generation == closure.generation
            ):
                reconciled.append(admission_id)
                continue
            if admission.status is not ReadAdmissionStatus.UNRESOLVED:
                pending.append(admission_id)
                continue
            endpoint_receipts = self._verify_endpoint_fences(
                state, closure.operation_id, closure.generation, admission
            )
            if endpoint_receipts is None:
                pending.append(admission_id)
                continue
            request = RecoveryAdmissionFinalizationRequest(
                consistency_domain_id=state.domain_id,
                authority_epoch=state.authority_epoch,
                operation_id=closure.operation_id,
                admission_id=admission_id,
                previous_generation=admission.generation,
                generation=closure.generation,
                route_ids=admission.route_ids,
                endpoint_receipts=endpoint_receipts,
            )
            try:
                terminal = self._finalizer.finalize_cancelled_admission(request)
            except Exception:
                pending.append(admission_id)
                continue
            if (
                not isinstance(terminal, RecoveryAdmissionTerminalReceipt)
                or terminal.consistency_domain_id != state.domain_id
                or terminal.authority_epoch != state.authority_epoch
                or terminal.operation_id != closure.operation_id
                or terminal.admission_id != admission_id
                or terminal.generation != closure.generation
            ):
                pending.append(admission_id)
                continue
            terminal_request = TerminalReceiptVerificationRequest(
                consistency_domain_id=state.domain_id,
                authority_epoch=state.authority_epoch,
                operation_id=closure.operation_id,
                admission_id=admission_id,
                receipt_id=terminal.receipt_id,
                kind=TerminalReceiptKind.ADMISSION_CANCELLED,
                generation=closure.generation,
            )
            try:
                verified_terminal = verify_terminal_receipt_with_context(
                    self._verifier,
                    self._trust_context_factory,
                    terminal_request,
                    purpose="recovery-admission-terminalization",
                    verification_time=self._clock(),
                )
            except Exception:
                pending.append(admission_id)
                continue
            if verified_terminal is None:
                pending.append(admission_id)
                continue
            try:
                now = self._clock()
                if (
                    not isinstance(now, datetime)
                    or now.tzinfo is None
                    or now.utcoffset() != timedelta(0)
                ):
                    pending.append(admission_id)
                    continue
                transition = ConsistencyTransition(
                    record_id=self._id_factory(),
                    schema_version=1,
                    record_kind=ConsistencyRecordKind.ADMISSION_RECONCILED,
                    operation_id=closure.operation_id,
                    occurred_at=now,
                    admission_id=admission_id,
                    generation=closure.generation,
                    receipt_id=terminal.receipt_id,
                    admission_terminal_status=ReadAdmissionStatus.CANCELLED,
                )
            except Exception:
                pending.append(admission_id)
                continue
            if self._append_and_confirm(state, transition):
                reconciled.append(admission_id)
            else:
                pending.append(admission_id)

        final = self._load()
        if final is None:
            status = RecoveryAdmissionFinalizationStatus.PENDING
        else:
            projection = final[1]
            current_closure = next(
                (item for item in projection.recovery_closures
                 if item.operation_id == closure.operation_id),
                None,
            )
            all_terminal = bool(
                current_closure is not None
                and all(
                    item.status is ReadAdmissionStatus.CANCELLED
                    and item.terminal_operation_id == closure.operation_id
                    and item.terminal_generation == closure.generation
                    and item.terminal_receipt_id is not None
                    for item in projection.admissions
                    if item.admission_id in closure.affected_admission_ids
                )
            )
            status = (
                RecoveryAdmissionFinalizationStatus.ADMISSIONS_TERMINAL
                if all_terminal and not pending
                else RecoveryAdmissionFinalizationStatus.PENDING
            )
        return RecoveryAdmissionFinalizationResult(
            status,
            closure.operation_id,
            closure.generation,
            tuple(reconciled),
            tuple(pending),
        )
