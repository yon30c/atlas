"""Pure models and reducer for the ME-03D Forget Coordinator.

These types coordinate logical suppression with verifiable destination deletion.
They do not implement storage adapters or claim physical deletion on their own.
"""
from dataclasses import dataclass, replace
from enum import Enum

from atlas.core.errors import ContractError
from atlas.memory.forget import ForgetClosure, ForgetClosureStatus, ForgetTarget


def _required(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacía")


def _positive(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractError(f"{field} debe ser un entero positivo")


class ForgetOperationState(str, Enum):
    CLOSING = "closing"
    SUPPRESSED = "suppressed"
    INVENTORY_PENDING = "inventory_pending"
    PURGING = "purging"
    VERIFYING = "verifying"
    BLOCKED = "blocked"
    COMPLETED = "completed"


class ForgetBlockReason(str, Enum):
    INVENTORY_UNAVAILABLE = "inventory_unavailable"
    INVENTORY_INCOMPLETE = "inventory_incomplete"
    INVENTORY_CHANGED = "inventory_changed"
    DELETE_REJECTED = "delete_rejected"
    DELETE_OUTCOME_UNKNOWN = "delete_outcome_unknown"
    DESTINATION_PRESENT = "destination_present"
    DESTINATION_UNAVAILABLE = "destination_unavailable"
    VERIFICATION_INDETERMINATE = "verification_indeterminate"
    RECEIPT_CONTRADICTION = "receipt_contradiction"
    RETENTION_POLICY_UNDEFINED = "retention_policy_undefined"
    CANONICAL_UPDATE_UNKNOWN = "canonical_update_unknown"
    RECOVERY_UNVERIFIED = "recovery_unverified"


class ForgetDestinationKind(str, Enum):
    PRIMARY_STORAGE = "primary_storage"
    VERSION_HISTORY = "version_history"
    SEARCH_INDEX = "search_index"
    DERIVED_INDEX = "derived_index"
    EMBEDDING_INDEX = "embedding_index"
    CACHE = "cache"
    REPLICA = "replica"
    BACKUP = "backup"
    EXPORT = "export"
    OPERATIONAL_COPY = "operational_copy"
    RESTORE_SOURCE = "restore_source"


class ForgetDeletionOutcome(str, Enum):
    ACKNOWLEDGED = "acknowledged"
    ALREADY_ABSENT = "already_absent"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class ForgetVerificationOutcome(str, Enum):
    ABSENT = "absent"
    PRESENT = "present"
    UNAVAILABLE = "unavailable"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True, slots=True)
class ForgetDestination:
    destination_id: str
    kind: ForgetDestinationKind

    def __post_init__(self) -> None:
        _required(self.destination_id, "destination_id")
        if not isinstance(self.kind, ForgetDestinationKind):
            raise ContractError("kind debe ser ForgetDestinationKind")


@dataclass(frozen=True, slots=True)
class ForgetDestinationInventory:
    inventory_id: str
    operation_id: str
    target: ForgetTarget
    revision: int
    destinations: tuple[ForgetDestination, ...]
    coverage_reference: str
    complete: bool
    retention_policy_reference: str | None = None

    def __post_init__(self) -> None:
        _required(self.inventory_id, "inventory_id")
        _required(self.operation_id, "operation_id")
        _required(self.coverage_reference, "coverage_reference")
        if not isinstance(self.target, ForgetTarget):
            raise ContractError("target debe ser ForgetTarget")
        _positive(self.revision, "revision")
        if not isinstance(self.destinations, tuple) or any(
            not isinstance(item, ForgetDestination) for item in self.destinations
        ):
            raise ContractError("destinations debe ser tuple[ForgetDestination, ...]")
        ids = tuple(item.destination_id for item in self.destinations)
        if len(ids) != len(set(ids)):
            raise ContractError("inventario contiene destination_id duplicado")
        if not isinstance(self.complete, bool):
            raise ContractError("complete debe ser bool")
        if self.retention_policy_reference is not None:
            _required(self.retention_policy_reference, "retention_policy_reference")


@dataclass(frozen=True, slots=True)
class ForgetDeletionAttempt:
    operation_id: str
    destination_id: str
    inventory_revision: int
    attempt_id: str
    outcome: ForgetDeletionOutcome
    receipt_id: str | None = None

    def __post_init__(self) -> None:
        for field in ("operation_id", "destination_id", "attempt_id"):
            _required(getattr(self, field), field)
        _positive(self.inventory_revision, "inventory_revision")
        if not isinstance(self.outcome, ForgetDeletionOutcome):
            raise ContractError("outcome debe ser ForgetDeletionOutcome")
        if self.receipt_id is not None:
            _required(self.receipt_id, "receipt_id")
        if (
            self.outcome is not ForgetDeletionOutcome.UNKNOWN
            and self.receipt_id is None
        ):
            raise ContractError("un resultado de eliminación conocido requiere receipt_id")


@dataclass(frozen=True, slots=True)
class ForgetVerificationReceipt:
    operation_id: str
    destination_id: str
    inventory_revision: int
    verification_id: str
    outcome: ForgetVerificationOutcome
    evidence_reference: str | None = None

    def __post_init__(self) -> None:
        for field in ("operation_id", "destination_id", "verification_id"):
            _required(getattr(self, field), field)
        _positive(self.inventory_revision, "inventory_revision")
        if not isinstance(self.outcome, ForgetVerificationOutcome):
            raise ContractError("outcome debe ser ForgetVerificationOutcome")
        if self.evidence_reference is not None:
            _required(self.evidence_reference, "evidence_reference")
        if (
            self.outcome in (
                ForgetVerificationOutcome.ABSENT,
                ForgetVerificationOutcome.PRESENT,
            )
            and self.evidence_reference is None
        ):
            raise ContractError("ABSENT/PRESENT requieren evidencia de verificación")


@dataclass(frozen=True, slots=True)
class ForgetCanonicalStateReceipt:
    operation_id: str
    memory_id: str
    expected_revision: int
    new_revision: int
    tombstone_reference: str
    receipt_id: str

    def __post_init__(self) -> None:
        _required(self.operation_id, "operation_id")
        _required(self.memory_id, "memory_id")
        _required(self.tombstone_reference, "tombstone_reference")
        _required(self.receipt_id, "receipt_id")
        _positive(self.expected_revision, "expected_revision")
        _positive(self.new_revision, "new_revision")
        if self.new_revision <= self.expected_revision:
            raise ContractError("new_revision debe superar expected_revision")


@dataclass(frozen=True, slots=True)
class ForgetOperation:
    closure: ForgetClosure
    state: ForgetOperationState
    inventory: ForgetDestinationInventory | None = None
    deletion_attempts: tuple[ForgetDeletionAttempt, ...] = ()
    verification_receipts: tuple[ForgetVerificationReceipt, ...] = ()
    block_reason: ForgetBlockReason | None = None
    resume_state: ForgetOperationState | None = None
    canonical_state_revision: int | None = None
    tombstone_reference: str | None = None
    canonical_receipt: ForgetCanonicalStateReceipt | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.closure, ForgetClosure):
            raise ContractError("closure debe ser ForgetClosure")
        if not isinstance(self.state, ForgetOperationState):
            raise ContractError("state debe ser ForgetOperationState")
        if self.state is ForgetOperationState.CLOSING:
            if self.closure.status is not ForgetClosureStatus.CLOSING:
                raise ContractError("CLOSING requiere ForgetClosure CLOSING")
        elif self.state is not ForgetOperationState.BLOCKED:
            if self.closure.status is not ForgetClosureStatus.SUPPRESSED:
                raise ContractError("las fases posteriores requieren supresión lógica")
        if self.inventory is not None:
            if not isinstance(self.inventory, ForgetDestinationInventory):
                raise ContractError("inventory debe ser ForgetDestinationInventory")
            if self.inventory.target != self.closure.target:
                raise ContractError("inventario no coincide con ForgetTarget")
            if self.inventory.operation_id != self.closure.operation_id:
                raise ContractError("inventario pertenece a otra operación Forget")
        if not isinstance(self.deletion_attempts, tuple) or any(
            not isinstance(item, ForgetDeletionAttempt) for item in self.deletion_attempts
        ):
            raise ContractError("deletion_attempts debe ser tuple tipado")
        if not isinstance(self.verification_receipts, tuple) or any(
            not isinstance(item, ForgetVerificationReceipt)
            for item in self.verification_receipts
        ):
            raise ContractError("verification_receipts debe ser tuple tipado")
        attempt_ids = tuple(item.attempt_id for item in self.deletion_attempts)
        deletion_receipt_ids = tuple(
            item.receipt_id for item in self.deletion_attempts if item.receipt_id is not None
        )
        verification_ids = tuple(item.verification_id for item in self.verification_receipts)
        verification_evidence = tuple(
            item.evidence_reference for item in self.verification_receipts
            if item.evidence_reference is not None
        )
        if len(attempt_ids) != len(set(attempt_ids)):
            raise ContractError("attempt_id duplicado")
        if len(deletion_receipt_ids) != len(set(deletion_receipt_ids)):
            raise ContractError("receipt_id de eliminación duplicado")
        if len(verification_evidence) != len(set(verification_evidence)):
            raise ContractError("evidencia de verificación reutilizada")
        if len(verification_ids) != len(set(verification_ids)):
            raise ContractError("verification_id duplicado")
        for item in self.deletion_attempts + self.verification_receipts:
            if item.operation_id != self.closure.operation_id:
                raise ContractError("recibo pertenece a otra operación Forget")
            if self.inventory is None or item.inventory_revision > self.inventory.revision:
                raise ContractError("recibo no corresponde a una revisión de inventario conocida")
            if item.destination_id not in {
                destination.destination_id for destination in self.inventory.destinations
            }:
                raise ContractError("recibo referencia destino fuera del inventario")
        if self.state in (
            ForgetOperationState.PURGING,
            ForgetOperationState.VERIFYING,
            ForgetOperationState.COMPLETED,
        ) and (self.inventory is None or not self.inventory.complete):
            raise ContractError("PURGING/VERIFYING/COMPLETED requiere inventario completo")
        if self.state in (
            ForgetOperationState.PURGING,
            ForgetOperationState.VERIFYING,
            ForgetOperationState.COMPLETED,
        ) and self.inventory is not None:
            has_backup = any(
                item.kind in (
                    ForgetDestinationKind.BACKUP,
                    ForgetDestinationKind.RESTORE_SOURCE,
                )
                for item in self.inventory.destinations
            )
            if has_backup and self.inventory.retention_policy_reference is None:
                raise ContractError("destinos de backup requieren política de retención verificable")
        if self.state is ForgetOperationState.BLOCKED:
            if self.resume_state in (
                ForgetOperationState.PURGING,
                ForgetOperationState.VERIFYING,
            ) and (self.inventory is None or not self.inventory.complete):
                raise ContractError("BLOCKED reanudable en purga/verificación requiere inventario completo")
            if not isinstance(self.block_reason, ForgetBlockReason):
                raise ContractError("BLOCKED requiere block_reason")
            if not isinstance(self.resume_state, ForgetOperationState):
                raise ContractError("BLOCKED requiere resume_state")
            if self.resume_state in (
                ForgetOperationState.BLOCKED,
                ForgetOperationState.COMPLETED,
            ):
                raise ContractError("resume_state debe ser una fase reanudable no terminal")
        elif self.block_reason is not None or self.resume_state is not None:
            raise ContractError("block_reason/resume_state solo aplican a BLOCKED")
        if self.canonical_state_revision is not None:
            _positive(self.canonical_state_revision, "canonical_state_revision")
        if self.tombstone_reference is not None:
            _required(self.tombstone_reference, "tombstone_reference")
        canonical_fields = (
            self.canonical_state_revision is not None,
            self.tombstone_reference is not None,
            self.canonical_receipt is not None,
        )
        if len(set(canonical_fields)) != 1:
            raise ContractError("revisión canónica, tombstone y recibo deben coexistir")
        if self.canonical_receipt is not None:
            if not isinstance(self.canonical_receipt, ForgetCanonicalStateReceipt):
                raise ContractError("canonical_receipt debe ser ForgetCanonicalStateReceipt")
            if (
                self.canonical_receipt.operation_id != self.closure.operation_id
                or self.canonical_receipt.memory_id != self.closure.target.memory_id
                or self.canonical_receipt.new_revision != self.canonical_state_revision
                or self.canonical_receipt.tombstone_reference != self.tombstone_reference
            ):
                raise ContractError("recibo canónico no coincide con operación/objetivo/estado")
        if self.state is ForgetOperationState.COMPLETED:
            if self.inventory is None or not self.inventory.complete:
                raise ContractError("COMPLETED requiere inventario completo")
            if self.canonical_state_revision is None or self.tombstone_reference is None:
                raise ContractError("COMPLETED requiere estado canónico y tombstone")
            if not self._all_destinations_absent():
                raise ContractError("COMPLETED requiere verificación ABSENT de todos los destinos")

    def _latest_verification(self, destination_id: str):
        matches = [
            item for item in self.verification_receipts
            if item.destination_id == destination_id
            and item.inventory_revision == self.inventory.revision
        ]
        return matches[-1] if matches else None

    def _all_destinations_absent(self) -> bool:
        if self.inventory is None or not self.inventory.complete:
            return False
        for destination in self.inventory.destinations:
            receipt = self._latest_verification(destination.destination_id)
            if receipt is None or receipt.outcome is not ForgetVerificationOutcome.ABSENT:
                return False
        return True


class ForgetCoordinatorReducer:
    """Transiciones puras, monotónicas y fail-closed del Forget Coordinator."""

    @staticmethod
    def _require(condition: bool, message: str) -> None:
        if not condition:
            raise ContractError(message)

    def mark_suppressed(
        self, operation: ForgetOperation, closure: ForgetClosure
    ) -> ForgetOperation:
        if operation.state is ForgetOperationState.SUPPRESSED:
            self._require(closure == operation.closure, "reintento SUPPRESSED contradictorio")
            return operation
        self._require(
            isinstance(closure, ForgetClosure),
            "closure debe ser ForgetClosure",
        )
        self._require(
            operation.state is ForgetOperationState.CLOSING
            or (
                operation.state is ForgetOperationState.BLOCKED
                and operation.resume_state is ForgetOperationState.CLOSING
            ),
            "operación no está CLOSING",
        )
        self._require(
            closure.closure_id == operation.closure.closure_id
            and closure.operation_id == operation.closure.operation_id
            and closure.idempotency_key == operation.closure.idempotency_key
            and closure.target == operation.closure.target
            and closure.generation == operation.closure.generation
            and closure.affected_admission_ids == operation.closure.affected_admission_ids
            and closure.delivery_route_ids == operation.closure.delivery_route_ids,
            "closure SUPPRESSED no coincide con el cierre original",
        )
        self._require(
            closure.status is ForgetClosureStatus.SUPPRESSED
            and not closure.unresolved_admission_ids,
            "SUPPRESSED requiere todas las admisiones resueltas",
        )
        return replace(operation, closure=closure, state=ForgetOperationState.SUPPRESSED)

    def request_inventory(self, operation: ForgetOperation) -> ForgetOperation:
        if operation.state is ForgetOperationState.INVENTORY_PENDING:
            return operation
        self._require(
            operation.state is ForgetOperationState.SUPPRESSED
            or (
                operation.state is ForgetOperationState.BLOCKED
                and operation.resume_state is ForgetOperationState.SUPPRESSED
            ),
            "inventario solo puede solicitarse después de SUPPRESSED",
        )
        return replace(operation, state=ForgetOperationState.INVENTORY_PENDING)

    def accept_inventory(
        self,
        operation: ForgetOperation,
        inventory: ForgetDestinationInventory,
    ) -> ForgetOperation:
        self._require(
            isinstance(inventory, ForgetDestinationInventory),
            "inventory debe ser ForgetDestinationInventory",
        )
        self._require(
            operation.state in (
                ForgetOperationState.INVENTORY_PENDING,
                ForgetOperationState.PURGING,
                ForgetOperationState.VERIFYING,
            ) or (
                operation.state is ForgetOperationState.BLOCKED
                and operation.resume_state in (
                    ForgetOperationState.INVENTORY_PENDING,
                    ForgetOperationState.PURGING,
                    ForgetOperationState.VERIFYING,
                )
            ),
            "estado no admite inventario",
        )
        self._require(
            inventory.target == operation.closure.target,
            "inventario no corresponde al objetivo Forget",
        )
        self._require(
            not any(item.outcome is ForgetDeletionOutcome.UNKNOWN for item in operation.deletion_attempts),
            "debe reconciliar intentos UNKNOWN antes de refrescar inventario",
        )
        previous = operation.inventory
        if previous is not None:
            self._require(inventory.revision >= previous.revision, "inventario retrocedió de revisión")
            if inventory.revision == previous.revision:
                self._require(
                    inventory.inventory_id == previous.inventory_id
                    and inventory.destinations == previous.destinations
                    and inventory.coverage_reference == previous.coverage_reference
                    and inventory.complete == previous.complete
                    and inventory.retention_policy_reference == previous.retention_policy_reference,
                    "misma revisión de inventario con contenido contradictorio",
                )
                return operation
            else:
                previous_kinds = {
                    item.destination_id: item.kind for item in previous.destinations
                }
                new_kinds = {
                    item.destination_id: item.kind for item in inventory.destinations
                }
                self._require(
                    set(previous_kinds).issubset(set(new_kinds)),
                    "inventario nuevo omite destinos anteriores sin evidencia de retiro",
                )
                self._require(
                    all(new_kinds[key] is kind for key, kind in previous_kinds.items()),
                    "un destination_id estable no puede cambiar de clase",
                )
        if not inventory.complete:
            return replace(
                operation,
                inventory=inventory,
                state=ForgetOperationState.BLOCKED,
                block_reason=ForgetBlockReason.INVENTORY_INCOMPLETE,
                resume_state=ForgetOperationState.INVENTORY_PENDING,
                canonical_state_revision=None,
                tombstone_reference=None,
                canonical_receipt=None,
            )
        has_backup = any(
            item.kind in (
                ForgetDestinationKind.BACKUP,
                ForgetDestinationKind.RESTORE_SOURCE,
            )
            for item in inventory.destinations
        )
        if has_backup and inventory.retention_policy_reference is None:
            return replace(
                operation,
                inventory=inventory,
                state=ForgetOperationState.BLOCKED,
                block_reason=ForgetBlockReason.RETENTION_POLICY_UNDEFINED,
                resume_state=ForgetOperationState.INVENTORY_PENDING,
                canonical_state_revision=None,
                tombstone_reference=None,
                canonical_receipt=None,
            )
        if previous is not None and inventory.revision > previous.revision:
            return replace(
                operation,
                inventory=inventory,
                state=ForgetOperationState.PURGING,
                block_reason=None,
                resume_state=None,
                canonical_state_revision=None,
                tombstone_reference=None,
                canonical_receipt=None,
            )
        return replace(
            operation,
            inventory=inventory,
            state=ForgetOperationState.PURGING,
            block_reason=None,
            resume_state=None,
        )

    def record_deletion_attempt(
        self, operation: ForgetOperation, attempt: ForgetDeletionAttempt
    ) -> ForgetOperation:
        self._require(
            isinstance(attempt, ForgetDeletionAttempt),
            "attempt debe ser ForgetDeletionAttempt",
        )
        allowed = operation.state is ForgetOperationState.PURGING or (
            operation.state is ForgetOperationState.BLOCKED
            and operation.resume_state is ForgetOperationState.PURGING
        )
        self._require(allowed, "operación no está en fase PURGING")
        self._require(operation.inventory is not None, "falta inventario")
        self._require(
            attempt.operation_id == operation.closure.operation_id
            and attempt.inventory_revision == operation.inventory.revision
            and attempt.destination_id in {
                item.destination_id for item in operation.inventory.destinations
            },
            "intento no coincide con operación/destino/revisión",
        )
        existing = next(
            (item for item in operation.deletion_attempts if item.attempt_id == attempt.attempt_id),
            None,
        )
        if existing is not None:
            self._require(existing == attempt, "attempt_id repetido con contenido contradictorio")
            return operation
        previous_unknown = any(
            item.destination_id == attempt.destination_id
            and item.outcome is ForgetDeletionOutcome.UNKNOWN
            for item in operation.deletion_attempts
        )
        self._require(
            not previous_unknown,
            "intento UNKNOWN debe reconciliarse antes de emitir otro intento",
        )
        updated = replace(
            operation,
            deletion_attempts=operation.deletion_attempts + (attempt,),
            state=ForgetOperationState.PURGING,
            block_reason=None,
            resume_state=None,
        )
        if attempt.outcome is ForgetDeletionOutcome.REJECTED:
            return self.block(updated, ForgetBlockReason.DELETE_REJECTED, ForgetOperationState.PURGING)
        if attempt.outcome is ForgetDeletionOutcome.UNKNOWN:
            return self.block(updated, ForgetBlockReason.DELETE_OUTCOME_UNKNOWN, ForgetOperationState.PURGING)
        return updated

    def reconcile_unknown_attempt(
        self,
        operation: ForgetOperation,
        attempt_id: str,
        reconciled_outcome: ForgetDeletionOutcome,
        receipt_id: str,
    ) -> ForgetOperation:
        _required(receipt_id, "receipt_id")
        index = next(
            (i for i, item in enumerate(operation.deletion_attempts) if item.attempt_id == attempt_id),
            None,
        )
        self._require(index is not None, "attempt_id desconocido")
        old = operation.deletion_attempts[index]
        if old.outcome is not ForgetDeletionOutcome.UNKNOWN:
            self._require(
                old.outcome is reconciled_outcome and old.receipt_id == receipt_id,
                "reconciliación repetida con resultado contradictorio",
            )
            return operation
        self._require(
            operation.state is ForgetOperationState.BLOCKED
            and operation.block_reason is ForgetBlockReason.DELETE_OUTCOME_UNKNOWN
            and operation.inventory is not None,
            "no hay intento UNKNOWN pendiente",
        )
        self._require(
            reconciled_outcome in (
                ForgetDeletionOutcome.ACKNOWLEDGED,
                ForgetDeletionOutcome.ALREADY_ABSENT,
                ForgetDeletionOutcome.REJECTED,
            ),
            "resultado reconciliado no puede seguir UNKNOWN",
        )
        replacement = replace(old, outcome=reconciled_outcome, receipt_id=receipt_id)
        attempts = list(operation.deletion_attempts)
        attempts[index] = replacement
        updated = replace(
            operation,
            deletion_attempts=tuple(attempts),
            state=ForgetOperationState.PURGING,
            block_reason=None,
            resume_state=None,
        )
        if reconciled_outcome is ForgetDeletionOutcome.REJECTED:
            return self.block(updated, ForgetBlockReason.DELETE_REJECTED, ForgetOperationState.PURGING)
        return updated

    def begin_verification(self, operation: ForgetOperation) -> ForgetOperation:
        if operation.state is ForgetOperationState.VERIFYING:
            return operation
        self._require(operation.state is ForgetOperationState.PURGING, "operación no está PURGING")
        self._require(operation.inventory is not None and operation.inventory.complete, "inventario incompleto")
        for destination in operation.inventory.destinations:
            attempts = [
                item for item in operation.deletion_attempts
                if item.destination_id == destination.destination_id
                and item.inventory_revision == operation.inventory.revision
            ]
            self._require(
                attempts and attempts[-1].outcome in (
                    ForgetDeletionOutcome.ACKNOWLEDGED,
                    ForgetDeletionOutcome.ALREADY_ABSENT,
                ),
                "cada destino requiere intento de eliminación conocido",
            )
        return replace(operation, state=ForgetOperationState.VERIFYING)

    def record_verification(
        self, operation: ForgetOperation, receipt: ForgetVerificationReceipt
    ) -> ForgetOperation:
        self._require(
            isinstance(receipt, ForgetVerificationReceipt),
            "receipt debe ser ForgetVerificationReceipt",
        )
        allowed = operation.state is ForgetOperationState.VERIFYING or (
            operation.state is ForgetOperationState.BLOCKED
            and operation.resume_state is ForgetOperationState.VERIFYING
        )
        self._require(allowed, "operación no está VERIFYING")
        self._require(operation.inventory is not None, "falta inventario")
        self._require(
            receipt.operation_id == operation.closure.operation_id
            and receipt.inventory_revision == operation.inventory.revision
            and receipt.destination_id in {
                item.destination_id for item in operation.inventory.destinations
            },
            "verificación no coincide con operación/destino/revisión",
        )
        self._require(
            any(
                item.destination_id == receipt.destination_id
                and item.inventory_revision == receipt.inventory_revision
                and item.outcome in (
                    ForgetDeletionOutcome.ACKNOWLEDGED,
                    ForgetDeletionOutcome.ALREADY_ABSENT,
                )
                for item in operation.deletion_attempts
            ),
            "verificación sin intento de eliminación conocido",
        )
        existing = next(
            (item for item in operation.verification_receipts
             if item.verification_id == receipt.verification_id),
            None,
        )
        if existing is not None:
            self._require(
                existing == receipt,
                "verification_id repetido con evidencia contradictoria",
            )
            return operation
        updated = replace(
            operation,
            verification_receipts=operation.verification_receipts + (receipt,),
            state=ForgetOperationState.VERIFYING,
            block_reason=None,
            resume_state=None,
        )
        if receipt.outcome is ForgetVerificationOutcome.PRESENT:
            return self.block(updated, ForgetBlockReason.DESTINATION_PRESENT, ForgetOperationState.VERIFYING)
        if receipt.outcome is ForgetVerificationOutcome.UNAVAILABLE:
            return self.block(updated, ForgetBlockReason.DESTINATION_UNAVAILABLE, ForgetOperationState.VERIFYING)
        if receipt.outcome is ForgetVerificationOutcome.INDETERMINATE:
            return self.block(updated, ForgetBlockReason.VERIFICATION_INDETERMINATE, ForgetOperationState.VERIFYING)
        return updated

    def block(
        self,
        operation: ForgetOperation,
        reason: ForgetBlockReason,
        resume_state: ForgetOperationState | None = None,
    ) -> ForgetOperation:
        self._require(operation.state is not ForgetOperationState.COMPLETED, "COMPLETED es terminal")
        if operation.state is ForgetOperationState.BLOCKED:
            original_resume = operation.resume_state
        else:
            original_resume = resume_state or operation.state
        self._require(
            original_resume not in (
                ForgetOperationState.BLOCKED,
                ForgetOperationState.COMPLETED,
            ),
            "resume_state debe ser una fase reanudable no terminal",
        )
        return replace(
            operation,
            state=ForgetOperationState.BLOCKED,
            block_reason=reason,
            resume_state=original_resume,
        )

    def mark_canonical_forgotten(
        self,
        operation: ForgetOperation,
        expected_inventory_revision: int,
        expected_canonical_revision: int,
        receipt: ForgetCanonicalStateReceipt,
    ) -> ForgetOperation:
        _positive(expected_inventory_revision, "expected_inventory_revision")
        _positive(expected_canonical_revision, "expected_canonical_revision")
        self._require(
            isinstance(receipt, ForgetCanonicalStateReceipt),
            "receipt debe ser ForgetCanonicalStateReceipt",
        )
        self._require(
            receipt.operation_id == operation.closure.operation_id
            and receipt.memory_id == operation.closure.target.memory_id
            and receipt.expected_revision == expected_canonical_revision,
            "recibo canónico no corresponde a operación/objetivo exactos",
        )
        self._require(operation.state is ForgetOperationState.VERIFYING, "operación no está VERIFYING")
        if (
            operation.inventory is None
            or not operation.inventory.complete
            or operation.inventory.revision != expected_inventory_revision
        ):
            return self.block(
                operation,
                ForgetBlockReason.INVENTORY_CHANGED,
                ForgetOperationState.VERIFYING,
            )
        if operation.canonical_receipt is not None:
            self._require(
                operation.canonical_receipt == receipt,
                "actualización canónica repetida con resultado contradictorio",
            )
            return operation
        self._require(
            operation._all_destinations_absent(),
            "no todos los destinos tienen verificación ABSENT",
        )
        return replace(
            operation,
            canonical_state_revision=receipt.new_revision,
            tombstone_reference=receipt.tombstone_reference,
            canonical_receipt=receipt,
        )

    def complete(
        self,
        operation: ForgetOperation,
        current_inventory_revision: int,
        canonical_receipt: ForgetCanonicalStateReceipt,
    ) -> ForgetOperation:
        _positive(current_inventory_revision, "current_inventory_revision")
        self._require(
            isinstance(canonical_receipt, ForgetCanonicalStateReceipt),
            "canonical_receipt debe ser ForgetCanonicalStateReceipt",
        )
        if operation.state is ForgetOperationState.COMPLETED:
            self._require(
                operation.inventory is not None
                and operation.inventory.revision == current_inventory_revision
                and operation.canonical_receipt == canonical_receipt,
                "reintento COMPLETED contradice el resultado registrado",
            )
            return operation
        self._require(operation.state is ForgetOperationState.VERIFYING, "operación no está VERIFYING")
        if (
            operation.inventory is None
            or operation.inventory.revision != current_inventory_revision
            or not operation.inventory.complete
        ):
            return self.block(
                operation,
                ForgetBlockReason.INVENTORY_CHANGED,
                ForgetOperationState.VERIFYING,
            )
        if not operation._all_destinations_absent():
            return self.block(
                operation,
                ForgetBlockReason.VERIFICATION_INDETERMINATE,
                ForgetOperationState.VERIFYING,
            )
        self._require(
            operation.canonical_receipt == canonical_receipt
            and canonical_receipt.operation_id == operation.closure.operation_id
            and canonical_receipt.memory_id == operation.closure.target.memory_id,
            "faltan actualización canónica verificable o recibo exacto",
        )
        return replace(operation, state=ForgetOperationState.COMPLETED)
