"""Global recovery completion and atomic gate reopening for ME-03J-B."""

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
from atlas.memory.journal_reducer import ConsistencyJournalReducer, ConsistencyProjection
from atlas.memory.receipt_verification import (
    TerminalReceiptKind,
    TerminalReceiptVerificationRequest,
    VerifiedTerminalReceipt,
    match_verified_receipt,
)
from atlas.ports.consistency_journal import ConsistencyJournalPort
from atlas.ports.recovery_completion import RecoveryCompletionFinalizerPort
from atlas.ports.recovery_gate import RecoveryGatePort
from atlas.ports.recovery_receipt_verifier import RecoveryCompletionVerifierPort


def _required(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacía")


@dataclass(frozen=True, slots=True)
class RecoveryCompletionRequest:
    consistency_domain_id: str
    authority_epoch: int
    operation_id: str
    generation: int
    affected_admission_ids: frozenset[str]
    route_ids: frozenset[str]
    admission_receipts: tuple[VerifiedTerminalReceipt, ...]

    def __post_init__(self) -> None:
        for field in ("consistency_domain_id", "operation_id"):
            _required(getattr(self, field), field)
        if isinstance(self.authority_epoch, bool) or not isinstance(self.authority_epoch, int) or self.authority_epoch < 1:
            raise ContractError("authority_epoch debe ser positiva")
        if isinstance(self.generation, bool) or not isinstance(self.generation, int) or self.generation < 1:
            raise ContractError("generation debe ser positiva")
        if not isinstance(self.affected_admission_ids, frozenset) or not self.affected_admission_ids:
            raise ContractError("affected_admission_ids debe ser frozenset no vacío")
        for admission_id in self.affected_admission_ids:
            _required(admission_id, "affected_admission_ids")
        if not isinstance(self.route_ids, frozenset) or not self.route_ids:
            raise ContractError("route_ids debe ser frozenset no vacío")
        for route_id in self.route_ids:
            _required(route_id, "route_ids")
        if not isinstance(self.admission_receipts, tuple) or not self.admission_receipts:
            raise ContractError("admission_receipts debe ser tupla no vacía")
        admission_ids = set()
        receipt_ids = set()
        verification_ids = set()
        routes = set()
        for receipt in self.admission_receipts:
            if not isinstance(receipt, VerifiedTerminalReceipt):
                raise ContractError("admission_receipts contiene evidencia inválida")
            if (
                receipt.consistency_domain_id != self.consistency_domain_id
                or receipt.authority_epoch != self.authority_epoch
                or receipt.operation_id != self.operation_id
                or receipt.kind is not TerminalReceiptKind.ADMISSION_CANCELLED
                or receipt.generation != self.generation
                or receipt.endpoint_id is not None
            ):
                raise ContractError("admission receipt no corresponde a esta recuperación")
            if (
                receipt.admission_id in admission_ids
                or receipt.receipt_id in receipt_ids
                or receipt.verification_id in verification_ids
            ):
                raise ContractError("admission receipt duplicado")
            admission_ids.add(receipt.admission_id)
            receipt_ids.add(receipt.receipt_id)
            verification_ids.add(receipt.verification_id)
        if admission_ids != set(self.affected_admission_ids):
            raise ContractError("admission receipts no cubren exactamente las admisiones")
        if not self.route_ids and self.affected_admission_ids:
            raise ContractError("route_ids debe reflejar el inventario de la recuperación")


@dataclass(frozen=True, slots=True)
class RecoveryCompletionReceipt:
    consistency_domain_id: str
    authority_epoch: int
    operation_id: str
    generation: int
    affected_admission_ids: frozenset[str]
    route_ids: frozenset[str]
    receipt_id: str

    def __post_init__(self) -> None:
        _required(self.consistency_domain_id, "consistency_domain_id")
        _required(self.operation_id, "operation_id")
        _required(self.receipt_id, "receipt_id")
        if isinstance(self.authority_epoch, bool) or not isinstance(self.authority_epoch, int) or self.authority_epoch < 1:
            raise ContractError("authority_epoch debe ser positiva")
        if isinstance(self.generation, bool) or not isinstance(self.generation, int) or self.generation < 1:
            raise ContractError("generation debe ser positiva")
        if not isinstance(self.affected_admission_ids, frozenset) or not self.affected_admission_ids:
            raise ContractError("affected_admission_ids debe ser frozenset no vacío")
        if not isinstance(self.affected_admission_ids, frozenset) or not self.affected_admission_ids:
            raise ContractError("affected_admission_ids debe ser frozenset no vacío")
        for admission_id in self.affected_admission_ids:
            _required(admission_id, "affected_admission_ids")
        if not isinstance(self.route_ids, frozenset) or not self.route_ids:
            raise ContractError("route_ids debe ser frozenset no vacío")
        for route_id in self.route_ids:
            _required(route_id, "route_ids")


@dataclass(frozen=True, slots=True)
class VerifiedRecoveryCompletionReceipt:
    verification_id: str
    issuer_id: str
    verified_at: datetime
    receipt: RecoveryCompletionReceipt

    def __post_init__(self) -> None:
        _required(self.verification_id, "verification_id")
        _required(self.issuer_id, "issuer_id")
        if (
            not isinstance(self.verified_at, datetime)
            or self.verified_at.tzinfo is None
            or self.verified_at.utcoffset() != timedelta(0)
        ):
            raise ContractError("verified_at debe ser UTC")
        if not isinstance(self.receipt, RecoveryCompletionReceipt):
            raise ContractError("receipt debe ser RecoveryCompletionReceipt")


class RecoveryCompletionStatus(str, Enum):
    RECOVERY_RECONCILED = "recovery_reconciled"
    PENDING = "pending"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class RecoveryCompletionResult:
    status: RecoveryCompletionStatus
    operation_id: str | None
    generation: int | None
    receipt_id: str | None


class RecoveryCompletionCoordinator:
    """Verifica la totalidad y delega commit+reapertura a una frontera atómica."""

    def __init__(
        self,
        journal: ConsistencyJournalPort,
        recovery_gate: RecoveryGatePort,
        finalizer: RecoveryCompletionFinalizerPort,
        verifier: RecoveryCompletionVerifierPort,
        terminal_verifier: object,
        *,
        domain_id: str,
        id_factory: Callable[[], str],
        clock: Callable[[], datetime],
    ) -> None:
        if not callable(getattr(journal, "load_recovery_state", None)):
            raise ContractError("journal debe implementar ConsistencyJournalPort")
        if not callable(getattr(recovery_gate, "reconcile_and_open_recovery_gate", None)):
            raise ContractError("recovery_gate debe implementar reapertura atómica")
        if not callable(getattr(recovery_gate, "ensure_recovery_gate_open", None)):
            raise ContractError("recovery_gate debe implementar restauración del gate abierto")
        if not callable(getattr(finalizer, "finalize_recovery", None)):
            raise ContractError("finalizer debe implementar RecoveryCompletionFinalizerPort")
        if not callable(getattr(verifier, "verify_recovery_completion", None)):
            raise ContractError("verifier debe implementar RecoveryCompletionVerifierPort")
        if not callable(getattr(terminal_verifier, "verify_terminal_receipt", None)):
            raise ContractError("terminal_verifier debe implementar TerminalReceiptVerifierPort")
        if not callable(id_factory) or not callable(clock):
            raise ContractError("id_factory y clock deben ser invocables")
        _required(domain_id, "domain_id")
        self._journal = journal
        self._gate = recovery_gate
        self._finalizer = finalizer
        self._verifier = verifier
        self._terminal_verifier = terminal_verifier
        self._domain_id = domain_id
        self._id_factory = id_factory
        self._clock = clock
        self._reducer = ConsistencyJournalReducer()

    def _load(self):
        try:
            state = self._journal.load_recovery_state(self._domain_id)
            if state is None or state.domain_id != self._domain_id:
                return None
            return state, self._reducer.reduce(state)
        except Exception:
            return None

    def _verify_admission_receipts(self, state, closure, projection):
        admissions = {
            item.admission_id: item
            for item in projection.admissions
            if item.admission_id in closure.affected_admission_ids
        }
        if set(admissions) != set(closure.affected_admission_ids):
            return None, None
        routes = frozenset(
            route for item in admissions.values() for route in item.route_ids
        )
        if routes != closure.route_ids:
            return None, None
        verified = []
        for admission_id in sorted(closure.affected_admission_ids):
            admission = admissions[admission_id]
            if (
                admission.status is not ReadAdmissionStatus.CANCELLED
                or admission.terminal_operation_id != closure.operation_id
                or admission.terminal_generation != closure.generation
                or admission.terminal_receipt_id is None
            ):
                return None, None
            request = TerminalReceiptVerificationRequest(
                consistency_domain_id=state.domain_id,
                authority_epoch=state.authority_epoch,
                operation_id=closure.operation_id,
                admission_id=admission_id,
                receipt_id=admission.terminal_receipt_id,
                kind=TerminalReceiptKind.ADMISSION_CANCELLED,
                generation=closure.generation,
            )
            try:
                result = self._terminal_verifier.verify_terminal_receipt(request)
            except Exception:
                return None, None
            receipt = match_verified_receipt(request, result)
            if receipt is None:
                return None, None
            verified.append(receipt)
        return tuple(verified), routes

    def run(self) -> RecoveryCompletionResult:
        loaded = self._load()
        if loaded is None:
            return RecoveryCompletionResult(RecoveryCompletionStatus.BLOCKED, None, None, None)
        state, projection = loaded
        active = tuple(item for item in projection.recovery_closures if not item.reconciled)
        if not active:
            reconciled = tuple(item for item in projection.recovery_closures if item.reconciled)
            if not reconciled:
                return RecoveryCompletionResult(RecoveryCompletionStatus.BLOCKED, None, None, None)
            closure = max(reconciled, key=lambda item: item.generation)
            try:
                opened = self._gate.ensure_recovery_gate_open(
                    closure.operation_id, closure.generation, closure.terminal_receipt_id
                )
            except Exception:
                opened = False
            return RecoveryCompletionResult(
                RecoveryCompletionStatus.RECOVERY_RECONCILED if opened is True else RecoveryCompletionStatus.BLOCKED,
                closure.operation_id, closure.generation, closure.terminal_receipt_id,
            )
        if len(active) != 1:
            return RecoveryCompletionResult(RecoveryCompletionStatus.BLOCKED, None, None, None)
        closure = active[0]
        admission_receipts, routes = self._verify_admission_receipts(state, closure, projection)
        if admission_receipts is None or routes is None:
            return RecoveryCompletionResult(
                RecoveryCompletionStatus.PENDING, closure.operation_id, closure.generation, None
            )
        request = RecoveryCompletionRequest(
            consistency_domain_id=state.domain_id,
            authority_epoch=state.authority_epoch,
            operation_id=closure.operation_id,
            generation=closure.generation,
            affected_admission_ids=closure.affected_admission_ids,
            route_ids=routes,
            admission_receipts=admission_receipts,
        )
        try:
            receipt = self._finalizer.finalize_recovery(request)
        except Exception:
            receipt = None
        if not isinstance(receipt, RecoveryCompletionReceipt) or (
            receipt.consistency_domain_id != request.consistency_domain_id
            or receipt.authority_epoch != request.authority_epoch
            or receipt.operation_id != request.operation_id
            or receipt.generation != request.generation
            or receipt.affected_admission_ids != request.affected_admission_ids
            or receipt.route_ids != request.route_ids
        ):
            return RecoveryCompletionResult(
                RecoveryCompletionStatus.PENDING, closure.operation_id, closure.generation, None
            )
        try:
            verified = self._verifier.verify_recovery_completion(request, receipt)
        except Exception:
            verified = None
        if not isinstance(verified, VerifiedRecoveryCompletionReceipt) or (
            verified.receipt != receipt
        ):
            return RecoveryCompletionResult(
                RecoveryCompletionStatus.PENDING, closure.operation_id, closure.generation, receipt.receipt_id
            )
        try:
            now = self._clock()
            if (
                not isinstance(now, datetime)
                or now.tzinfo is None
                or now.utcoffset() != timedelta(0)
            ):
                raise ContractError("clock debe devolver UTC")
            transition = ConsistencyTransition(
                record_id=self._id_factory(),
                schema_version=1,
                record_kind=ConsistencyRecordKind.RECOVERY_RECONCILED,
                operation_id=closure.operation_id,
                occurred_at=now,
                generation=closure.generation,
                receipt_id=receipt.receipt_id,
                affected_admission_ids=closure.affected_admission_ids,
                route_ids=closure.route_ids,
            )
            expected = ConsistencyPosition(
                state.domain_id, state.authority_epoch, state.head_sequence
            )
            self._gate.reconcile_and_open_recovery_gate(
                expected, transition, verified
            )
        except Exception:
            pass

        final = self._load()
        if final is None:
            return RecoveryCompletionResult(
                RecoveryCompletionStatus.PENDING, closure.operation_id, closure.generation, receipt.receipt_id
            )
        reconciled = next(
            (item for item in final[1].recovery_closures
             if item.operation_id == closure.operation_id and item.reconciled),
            None,
        )
        if reconciled is None or reconciled.terminal_receipt_id != receipt.receipt_id:
            return RecoveryCompletionResult(
                RecoveryCompletionStatus.PENDING, closure.operation_id, closure.generation, receipt.receipt_id
            )
        try:
            opened = self._gate.ensure_recovery_gate_open(
                closure.operation_id, closure.generation, receipt.receipt_id
            )
        except Exception:
            opened = False
        return RecoveryCompletionResult(
            RecoveryCompletionStatus.RECOVERY_RECONCILED if opened is True else RecoveryCompletionStatus.BLOCKED,
            closure.operation_id, closure.generation, receipt.receipt_id,
        )
