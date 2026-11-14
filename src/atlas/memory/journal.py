"""Modelos puros del registro durable de consistencia ME-03.

No implementan persistencia, orden distribuido ni verificación criptográfica.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from atlas.core.errors import ContractError
from atlas.memory.consistency import (
    AuthorityKind,
    AuthorizationRevisionSet,
    ReadAdmissionStatus,
)
from atlas.memory.envelope import AuthenticatedConsistencyEnvelope
from atlas.memory.identifiers import validate_atlas_id
from atlas.memory.models import MemoryScopeKind


def _required(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacía")


def _positive(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractError(f"{field} debe ser un entero positivo")


def _non_negative(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractError(f"{field} debe ser un entero no negativo")


def _utc(value: object, field: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ContractError(f"{field} debe ser un datetime UTC")


SUPPORTED_CONSISTENCY_SCHEMA_VERSIONS = frozenset({1, 2})

class ConsistencyRecordKind(str, Enum):
    READ_ADMITTED = "read_admitted"
    READ_ACTIVATED = "read_activated"
    EGRESS_COMMITTED = "egress_committed"
    ENDPOINT_COMPLETED = "endpoint_completed"
    ENDPOINT_FENCED = "endpoint_fenced"
    FORGET_CLOSED = "forget_closed"
    INVALIDATION_CLOSED = "invalidation_closed"
    ADMISSION_RECONCILED = "admission_reconciled"
    FORGET_SUPPRESSED = "forget_suppressed"
    INVALIDATION_RECONCILED = "invalidation_reconciled"
    RECOVERY_CLOSED = "recovery_closed"
    RECOVERY_RECONCILED = "recovery_reconciled"
    CHECKPOINT_COMMITTED = "checkpoint_committed"


_COMMON_TRANSITION_FIELDS = frozenset({
    "record_id", "schema_version", "record_kind", "operation_id", "occurred_at",
})
_TRANSITION_FIELDS_BY_KIND = {
    ConsistencyRecordKind.READ_ADMITTED: _COMMON_TRANSITION_FIELDS | frozenset({
        "idempotency_key", "request_id", "correlation_id", "actor_identity_id",
        "subject_user_id", "owner_id", "memory_id", "version_id", "snapshot_id",
        "revisions", "admission_id", "generation", "route_ids",
    }) | frozenset({"scope_kind", "scope_project_id"}),
    ConsistencyRecordKind.READ_ACTIVATED: _COMMON_TRANSITION_FIELDS | frozenset({
        "admission_id", "generation",
    }),
    ConsistencyRecordKind.EGRESS_COMMITTED: _COMMON_TRANSITION_FIELDS | frozenset({
        "admission_id", "endpoint_id", "generation", "emission_id",
        "emission_sequence", "receipt_id",
    }),
    ConsistencyRecordKind.ENDPOINT_COMPLETED: _COMMON_TRANSITION_FIELDS | frozenset({
        "admission_id", "endpoint_id", "generation", "receipt_id", "final_sequence",
    }),
    ConsistencyRecordKind.ENDPOINT_FENCED: _COMMON_TRANSITION_FIELDS | frozenset({
        "admission_id", "endpoint_id", "generation", "receipt_id",
    }),
    ConsistencyRecordKind.FORGET_CLOSED: _COMMON_TRANSITION_FIELDS | frozenset({
        "idempotency_key", "request_id", "correlation_id", "actor_identity_id",
        "subject_user_id", "owner_id", "memory_id", "generation", "proof_reference",
        "route_ids", "affected_admission_ids",
    }),
    ConsistencyRecordKind.INVALIDATION_CLOSED: _COMMON_TRANSITION_FIELDS | frozenset({
        "authority_kind", "authority_id", "generation", "previous_revision",
        "new_revision", "route_ids", "affected_admission_ids",
    }),
    ConsistencyRecordKind.ADMISSION_RECONCILED: _COMMON_TRANSITION_FIELDS | frozenset({
        "admission_id", "generation", "receipt_id", "admission_terminal_status",
    }),
    ConsistencyRecordKind.FORGET_SUPPRESSED: _COMMON_TRANSITION_FIELDS | frozenset({
        "memory_id", "generation", "route_ids", "affected_admission_ids",
    }),
    ConsistencyRecordKind.INVALIDATION_RECONCILED: _COMMON_TRANSITION_FIELDS | frozenset({
        "authority_kind", "authority_id", "generation", "route_ids",
        "affected_admission_ids",
    }),
    ConsistencyRecordKind.RECOVERY_CLOSED: _COMMON_TRANSITION_FIELDS | frozenset({
        "generation", "route_ids", "affected_admission_ids",
    }),
    ConsistencyRecordKind.RECOVERY_RECONCILED: _COMMON_TRANSITION_FIELDS | frozenset({
        "generation", "receipt_id", "route_ids", "affected_admission_ids",
    }),
    ConsistencyRecordKind.CHECKPOINT_COMMITTED: _COMMON_TRANSITION_FIELDS | frozenset({
        "checkpoint_reference",
    }),
}


@dataclass(frozen=True, slots=True)
class ConsistencyPosition:
    consistency_domain_id: str
    authority_epoch: int
    sequence: int

    def __post_init__(self) -> None:
        _required(self.consistency_domain_id, "consistency_domain_id")
        _positive(self.authority_epoch, "authority_epoch")
        _non_negative(self.sequence, "sequence")


@dataclass(frozen=True, slots=True)
class ConsistencyTransition:
    """Transición sin payload; los campos opcionales dependen de record_kind."""

    record_id: str
    schema_version: int
    record_kind: ConsistencyRecordKind
    operation_id: str
    occurred_at: datetime
    idempotency_key: str | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    actor_identity_id: str | None = None
    subject_user_id: str | None = None
    owner_id: str | None = None
    memory_id: str | None = None
    version_id: str | None = None
    snapshot_id: str | None = None
    revisions: AuthorizationRevisionSet | None = None
    scope_kind: MemoryScopeKind | None = None
    scope_project_id: str | None = None
    authority_kind: AuthorityKind | None = None
    authority_id: str | None = None
    admission_id: str | None = None
    endpoint_id: str | None = None
    generation: int | None = None
    emission_id: str | None = None
    emission_sequence: int | None = None
    final_sequence: int | None = None
    receipt_id: str | None = None
    proof_reference: str | None = None
    checkpoint_reference: str | None = None
    previous_revision: int | None = None
    new_revision: int | None = None
    admission_terminal_status: ReadAdmissionStatus | None = None
    route_ids: frozenset[str] = frozenset()
    affected_admission_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        validate_atlas_id(self.record_id, "record_id")
        _positive(self.schema_version, "schema_version")
        if self.schema_version not in SUPPORTED_CONSISTENCY_SCHEMA_VERSIONS:
            raise ContractError("schema_version de transición no soportada")
        if not isinstance(self.record_kind, ConsistencyRecordKind):
            raise ContractError("record_kind debe ser ConsistencyRecordKind")
        if self.schema_version == 2 and self.record_kind is not ConsistencyRecordKind.READ_ADMITTED:
            raise ContractError("schema_version 2 solo aplica a READ_ADMITTED")
        if self.schema_version == 1 and (
            self.scope_kind is not None or self.scope_project_id is not None
        ):
            raise ContractError("scope_kind/scope_project_id requieren schema_version 2")
        _required(self.operation_id, "operation_id")
        _utc(self.occurred_at, "occurred_at")

        for field in (
            "idempotency_key", "request_id", "correlation_id",
            "actor_identity_id", "subject_user_id", "owner_id", "snapshot_id",
            "authority_id", "admission_id", "endpoint_id", "emission_id",
            "receipt_id", "proof_reference", "checkpoint_reference",
        ):
            value = getattr(self, field)
            if value is not None:
                _required(value, field)

        if self.memory_id is not None:
            validate_atlas_id(self.memory_id, "memory_id")
        if self.version_id is not None:
            validate_atlas_id(self.version_id, "version_id")
        if self.revisions is not None and not isinstance(
            self.revisions, AuthorizationRevisionSet
        ):
            raise ContractError("revisions debe ser AuthorizationRevisionSet")
        if self.scope_kind is not None and not isinstance(self.scope_kind, MemoryScopeKind):
            raise ContractError("scope_kind debe ser MemoryScopeKind")
        if self.scope_project_id is not None:
            _required(self.scope_project_id, "scope_project_id")
        if self.authority_kind is not None and not isinstance(
            self.authority_kind, AuthorityKind
        ):
            raise ContractError("authority_kind debe ser AuthorityKind")
        if self.generation is not None:
            _positive(self.generation, "generation")
        for field in ("previous_revision", "new_revision"):
            value = getattr(self, field)
            if value is not None:
                _positive(value, field)
        if self.admission_terminal_status is not None and not isinstance(
            self.admission_terminal_status, ReadAdmissionStatus
        ):
            raise ContractError("admission_terminal_status debe ser ReadAdmissionStatus")
        if self.emission_sequence is not None:
            _positive(self.emission_sequence, "emission_sequence")
        if self.final_sequence is not None:
            _non_negative(self.final_sequence, "final_sequence")
        for field in ("route_ids", "affected_admission_ids"):
            values = getattr(self, field)
            if not isinstance(values, frozenset):
                raise ContractError(f"{field} debe ser frozenset")
            for value in values:
                _required(value, field)

        allowed_fields = _TRANSITION_FIELDS_BY_KIND[self.record_kind]
        if self.record_kind is ConsistencyRecordKind.READ_ADMITTED and self.schema_version == 1:
            allowed_fields = allowed_fields - frozenset({"scope_kind", "scope_project_id"})
        for field in self.__dataclass_fields__:
            if field in allowed_fields:
                continue
            value = getattr(self, field)
            if value is not None and not (
                field in ("route_ids", "affected_admission_ids")
                and value == frozenset()
            ):
                raise ContractError(
                    f"{field} no está permitido para {self.record_kind.value}"
                )

        required_by_kind = {
            ConsistencyRecordKind.READ_ADMITTED: (
                "memory_id", "version_id", "snapshot_id", "revisions",
                "admission_id", "generation",
            ),
            ConsistencyRecordKind.READ_ACTIVATED: ("admission_id", "generation"),
            ConsistencyRecordKind.EGRESS_COMMITTED: (
                "admission_id", "endpoint_id", "generation", "emission_id",
                "emission_sequence", "receipt_id",
            ),
            ConsistencyRecordKind.ENDPOINT_COMPLETED: (
                "admission_id", "endpoint_id", "generation", "receipt_id",
                "final_sequence",
            ),
            ConsistencyRecordKind.ENDPOINT_FENCED: (
                "admission_id", "endpoint_id", "generation", "receipt_id",
            ),
            ConsistencyRecordKind.FORGET_CLOSED: (
                "memory_id", "generation", "proof_reference", "idempotency_key",
                "request_id", "actor_identity_id", "subject_user_id", "owner_id",
            ),
            ConsistencyRecordKind.INVALIDATION_CLOSED: (
                "authority_kind", "authority_id", "generation",
                "previous_revision", "new_revision",
            ),
            ConsistencyRecordKind.ADMISSION_RECONCILED: (
                "admission_id", "generation", "receipt_id",
                "admission_terminal_status",
            ),
            ConsistencyRecordKind.FORGET_SUPPRESSED: (
                "memory_id", "generation",
            ),
            ConsistencyRecordKind.INVALIDATION_RECONCILED: (
                "authority_kind", "authority_id", "generation",
            ),
            ConsistencyRecordKind.RECOVERY_CLOSED: ("generation",),
            ConsistencyRecordKind.RECOVERY_RECONCILED: (
                "generation", "receipt_id",
            ),
            ConsistencyRecordKind.CHECKPOINT_COMMITTED: ("checkpoint_reference",),
        }
        for field in required_by_kind.get(self.record_kind, ()):
            value = getattr(self, field)
            if value is None:
                raise ContractError(f"{field} es obligatorio para {self.record_kind.value}")

        if self.record_kind in (
            ConsistencyRecordKind.READ_ADMITTED,
            ConsistencyRecordKind.READ_ACTIVATED,
            ConsistencyRecordKind.EGRESS_COMMITTED,
        ):
            if self.operation_id != f"read:{self.admission_id}":
                raise ContractError("operation_id debe corresponder a la admisión exacta")

        if self.record_kind is ConsistencyRecordKind.READ_ADMITTED:
            if self.schema_version == 2:
                for field in ("owner_id", "actor_identity_id", "request_id", "scope_kind"):
                    if getattr(self, field) is None:
                        raise ContractError(f"{field} es obligatorio para READ_ADMITTED v2")
                if self.scope_kind is MemoryScopeKind.PRIVATE:
                    if self.scope_project_id is not None:
                        raise ContractError("PRIVATE no admite scope_project_id")
                    if self.subject_user_id != self.owner_id:
                        raise ContractError("PRIVATE requiere subject_user_id igual a owner_id")
                    if any(value is not None for value in (
                        self.revisions.project_revision,
                        self.revisions.environment_revision,
                        self.revisions.grant_revision,
                    )):
                        raise ContractError("PRIVATE no admite revisiones PROJECT o Grant")
                elif self.scope_kind is MemoryScopeKind.PROJECT:
                    if self.scope_project_id is None:
                        raise ContractError("PROJECT requiere scope_project_id")
                    project_revision = self.revisions.project_revision
                    if project_revision is None or project_revision.authority_id != self.scope_project_id:
                        raise ContractError("scope_project_id debe coincidir con project_revision")
                    if any(value is None for value in (
                        self.revisions.environment_revision,
                        self.revisions.grant_revision,
                    )):
                        raise ContractError("PROJECT requiere revisiones de entorno y Grant")
            if not self.route_ids:
                raise ContractError("READ_ADMITTED requiere al menos una ruta registrada")
            if self.revisions.memory_revision.authority_id != self.memory_id:
                raise ContractError("revisions.memory_revision no coincide con memory_id")
            if self.revisions.version_revision.authority_id != self.version_id:
                raise ContractError("revisions.version_revision no coincide con version_id")
            if (
                self.actor_identity_id is None
                or self.revisions.identity_revision.authority_id != self.actor_identity_id
            ):
                raise ContractError("READ_ADMITTED requiere la revisión de la identidad exacta")
        if self.record_kind in (
            ConsistencyRecordKind.FORGET_CLOSED,
            ConsistencyRecordKind.INVALIDATION_CLOSED,
            ConsistencyRecordKind.FORGET_SUPPRESSED,
            ConsistencyRecordKind.INVALIDATION_RECONCILED,
        ) and bool(self.route_ids) != bool(self.affected_admission_ids):
            raise ContractError("rutas y admisiones afectadas deben estar vacías o presentes juntas")
        if self.record_kind is ConsistencyRecordKind.INVALIDATION_CLOSED:
            if self.new_revision <= self.previous_revision:
                raise ContractError("new_revision debe ser mayor que previous_revision")
        if self.record_kind is ConsistencyRecordKind.ADMISSION_RECONCILED:
            if self.admission_terminal_status not in (
                ReadAdmissionStatus.COMPLETED, ReadAdmissionStatus.CANCELLED
            ):
                raise ContractError("ADMISSION_RECONCILED requiere estado terminal COMPLETED o CANCELLED")
        if self.record_kind is not ConsistencyRecordKind.ADMISSION_RECONCILED and self.admission_terminal_status is not None:
            raise ContractError("admission_terminal_status solo aplica a ADMISSION_RECONCILED")
        if self.record_kind is not ConsistencyRecordKind.INVALIDATION_CLOSED and any(
            value is not None for value in (self.previous_revision, self.new_revision)
        ):
            raise ContractError("previous_revision/new_revision solo aplican a INVALIDATION_CLOSED")
        if self.record_kind is ConsistencyRecordKind.FORGET_CLOSED:
            if self.subject_user_id != self.owner_id:
                raise ContractError("FORGET_CLOSED requiere sujeto autenticado igual al propietario")
            if self.authority_kind is not None or self.authority_id is not None:
                raise ContractError("FORGET_CLOSED usa memory_id, no authority genérica")
        if self.record_kind is ConsistencyRecordKind.EGRESS_COMMITTED:
            if self.receipt_id is None:
                raise ContractError("EGRESS_COMMITTED requiere recibo durable del endpoint")


REQUEST_PROJECTION_VERSION = 1
_REQUEST_PROJECTION_EXCLUDED_FIELDS = frozenset({
    "record_id",
    "operation_id",
    "occurred_at",
    "request_id",
    "correlation_id",
    "idempotency_key",
})


def consistency_transition_request_projection(
    consistency_domain_id: str,
    authority_epoch: int,
    transition: ConsistencyTransition,
) -> dict[str, object]:
    """Return the explicit v1 semantic request projection for idempotency.

    Technical invocation/transport identifiers are intentionally excluded.
    Business identifiers and authorization/effect fields remain included.
    The per-kind allowlist is closed by _TRANSITION_FIELDS_BY_KIND.
    """
    _required(consistency_domain_id, "consistency_domain_id")
    _positive(authority_epoch, "authority_epoch")
    if not isinstance(transition, ConsistencyTransition):
        raise ContractError("transition debe ser ConsistencyTransition")

    allowed_fields = _TRANSITION_FIELDS_BY_KIND[transition.record_kind]
    if (
        transition.record_kind is ConsistencyRecordKind.READ_ADMITTED
        and transition.schema_version == 1
    ):
        allowed_fields = allowed_fields - frozenset({
            "scope_kind", "scope_project_id"
        })

    semantic_fields = allowed_fields - _REQUEST_PROJECTION_EXCLUDED_FIELDS
    return {
        "request_projection_version": REQUEST_PROJECTION_VERSION,
        "consistency_domain_id": consistency_domain_id,
        "authority_epoch": authority_epoch,
        "record_kind": transition.record_kind,
        "schema_version": transition.schema_version,
        "semantic_fields": {
            field: getattr(transition, field)
            for field in sorted(semantic_fields)
        },
    }


def same_semantic_transition(
    consistency_domain_id: str,
    authority_epoch: int,
    expected: ConsistencyTransition,
    committed: ConsistencyTransition,
) -> bool:
    """Compare two transitions by their versioned semantic request projection."""
    return consistency_transition_request_projection(
        consistency_domain_id, authority_epoch, expected
    ) == consistency_transition_request_projection(
        consistency_domain_id, authority_epoch, committed
    )


@dataclass(frozen=True, slots=True)
class JournalCommit:
    position: ConsistencyPosition
    record_id: str
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.position, ConsistencyPosition):
            raise ContractError("position debe ser ConsistencyPosition")
        validate_atlas_id(self.record_id, "record_id")
        if not isinstance(self.replayed, bool):
            raise ContractError("replayed debe ser bool")



class JournalOperationResolutionStatus(str, Enum):
    COMMITTED_EXACT = "committed_exact"
    NOT_COMMITTED = "not_committed"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class JournalOperationResolution:
    """Resultado de reconciliación de un append incierto."""

    status: JournalOperationResolutionStatus
    append_id: str
    idempotency_key: str | None
    expected_position: ConsistencyPosition
    expected_transition: ConsistencyTransition
    current_position: ConsistencyPosition | None
    commit: JournalCommit | None
    committed_transition: ConsistencyTransition | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, JournalOperationResolutionStatus):
            raise ContractError("status debe ser JournalOperationResolutionStatus")
        _required(self.append_id, "append_id")
        if self.idempotency_key is not None:
            _required(self.idempotency_key, "idempotency_key")
        if not isinstance(self.expected_position, ConsistencyPosition):
            raise ContractError("expected_position debe ser ConsistencyPosition")
        if not isinstance(self.expected_transition, ConsistencyTransition):
            raise ContractError("expected_transition debe ser ConsistencyTransition")
        if self.expected_transition.idempotency_key != self.idempotency_key:
            raise ContractError("expected_transition no corresponde a idempotency_key")
        if self.current_position is not None and not isinstance(
            self.current_position, ConsistencyPosition
        ):
            raise ContractError("current_position debe ser ConsistencyPosition")
        if self.commit is not None and not isinstance(self.commit, JournalCommit):
            raise ContractError("commit debe ser JournalCommit")
        if self.committed_transition is not None and not isinstance(
            self.committed_transition, ConsistencyTransition
        ):
            raise ContractError("committed_transition debe ser ConsistencyTransition")
        if self.status is JournalOperationResolutionStatus.COMMITTED_EXACT:
            if (
                self.commit is None or self.current_position is None
                or self.committed_transition is None
            ):
                raise ContractError("COMMITTED_EXACT requiere commit y posición actual")
            if (
                self.commit.position.consistency_domain_id
                    != self.expected_position.consistency_domain_id
                or self.commit.position.authority_epoch
                    != self.expected_position.authority_epoch
                or self.commit.position.sequence != self.expected_position.sequence + 1
                or self.current_position.consistency_domain_id
                    != self.expected_position.consistency_domain_id
                or self.current_position.authority_epoch
                    != self.expected_position.authority_epoch
                or self.current_position.sequence < self.commit.position.sequence
                or not same_semantic_transition(
                    self.expected_position.consistency_domain_id,
                    self.expected_position.authority_epoch,
                    self.expected_transition,
                    self.committed_transition,
                )
                or self.committed_transition.idempotency_key
                    != self.expected_transition.idempotency_key
                or self.commit.record_id != self.committed_transition.record_id
            ):
                raise ContractError(
                    "commit/transición/posición no corresponden exactamente a la solicitud"
                )
        elif self.commit is not None or self.committed_transition is not None:
            raise ContractError(
                "solo COMMITTED_EXACT puede incluir commit y transición persistida"
            )
        if self.status is JournalOperationResolutionStatus.NOT_COMMITTED:
            if self.current_position is None:
                raise ContractError("NOT_COMMITTED requiere posición actual demostrada")
            if (
                self.current_position.consistency_domain_id
                    != self.expected_position.consistency_domain_id
                or self.current_position.authority_epoch
                    != self.expected_position.authority_epoch
                or self.current_position.sequence < self.expected_position.sequence
            ):
                raise ContractError(
                    "NOT_COMMITTED requiere misma autoridad, época y posición no regresiva"
                )
        if self.status is JournalOperationResolutionStatus.UNKNOWN and self.commit is not None:
            raise ContractError("UNKNOWN no puede afirmar un commit")


@dataclass(frozen=True, slots=True)
class JournalEntry:
    position: ConsistencyPosition
    transition: ConsistencyTransition
    envelope: AuthenticatedConsistencyEnvelope | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.position, ConsistencyPosition):
            raise ContractError("position debe ser ConsistencyPosition")
        if not isinstance(self.transition, ConsistencyTransition):
            raise ContractError("transition debe ser ConsistencyTransition")
        if self.envelope is not None:
            if not isinstance(self.envelope, AuthenticatedConsistencyEnvelope):
                raise ContractError("envelope debe ser AuthenticatedConsistencyEnvelope")
            if (self.envelope.object_kind != "journal_entry"
                    or self.envelope.object_id != self.transition.record_id
                    or self.envelope.consistency_domain_id != self.position.consistency_domain_id
                    or self.envelope.authority_epoch != self.position.authority_epoch
                    or self.envelope.sequence != self.position.sequence
                    or self.envelope.schema_version != self.transition.schema_version):
                raise ContractError("envelope no corresponde a la entrada exacta del journal")


@dataclass(frozen=True, slots=True)
class ConsistencyCheckpoint:
    checkpoint_id: str
    position: ConsistencyPosition
    state_reference: str
    integrity_reference: str
    created_at: datetime
    envelope: AuthenticatedConsistencyEnvelope | None = None

    def __post_init__(self) -> None:
        validate_atlas_id(self.checkpoint_id, "checkpoint_id")
        if not isinstance(self.position, ConsistencyPosition):
            raise ContractError("position debe ser ConsistencyPosition")
        _required(self.state_reference, "state_reference")
        _required(self.integrity_reference, "integrity_reference")
        _utc(self.created_at, "created_at")
        if self.envelope is not None:
            if not isinstance(self.envelope, AuthenticatedConsistencyEnvelope):
                raise ContractError("envelope debe ser AuthenticatedConsistencyEnvelope")
            if (self.envelope.object_kind != "checkpoint"
                    or self.envelope.object_id != self.checkpoint_id
                    or self.envelope.consistency_domain_id != self.position.consistency_domain_id
                    or self.envelope.authority_epoch != self.position.authority_epoch
                    or self.envelope.sequence != self.position.sequence):
                raise ContractError("envelope no corresponde al checkpoint exacto")


@dataclass(frozen=True, slots=True)
class ConsistencyRecoveryState:
    """Estado estructural sin autenticación; no debe alimentar el reducer operativo.

    La recuperación operativa requiere evidencia tipada del perfil local o
    anclado, producida por la frontera de verificación confiable.
    """

    domain_id: str
    authority_epoch: int
    checkpoint: ConsistencyCheckpoint | None
    entries: tuple[JournalEntry, ...]
    head_sequence: int
    continuity_reference: str

    def __post_init__(self) -> None:
        _required(self.domain_id, "domain_id")
        _positive(self.authority_epoch, "authority_epoch")
        _non_negative(self.head_sequence, "head_sequence")
        _required(self.continuity_reference, "continuity_reference")
        if not isinstance(self.entries, tuple):
            raise ContractError("entries debe ser tuple")
        if self.checkpoint is not None:
            if not isinstance(self.checkpoint, ConsistencyCheckpoint):
                raise ContractError("checkpoint debe ser ConsistencyCheckpoint")
            if (
                self.checkpoint.position.consistency_domain_id != self.domain_id
                or self.checkpoint.position.authority_epoch != self.authority_epoch
            ):
                raise ContractError("checkpoint pertenece a otro dominio o época")
        start = self.checkpoint.position.sequence if self.checkpoint else 0
        expected = start + 1
        seen_record_ids = set()
        for entry in self.entries:
            if not isinstance(entry, JournalEntry):
                raise ContractError("entries solo puede contener JournalEntry")
            position = entry.position
            if (
                position.consistency_domain_id != self.domain_id
                or position.authority_epoch != self.authority_epoch
            ):
                raise ContractError("entry pertenece a otro dominio o época")
            if position.sequence != expected:
                raise ContractError("journal contiene huecos o secuencias fuera de orden")
            if entry.transition.record_id in seen_record_ids:
                raise ContractError("record_id duplicado en journal")
            seen_record_ids.add(entry.transition.record_id)
            expected += 1
        actual_head = expected - 1
        if actual_head != self.head_sequence:
            raise ContractError("head_sequence no coincide con checkpoint y entries")
