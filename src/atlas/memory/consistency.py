"""Modelos inmutables para consistencia, admisión y entrega protegida ME-03."""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum

from atlas.core.errors import ContractError
from atlas.memory.identifiers import validate_atlas_id
from atlas.memory.models import MemoryClassification, MemoryScope, MemoryScopeKind, MemoryVersionStatus


def _required(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacía")
    return value


def _utc(value: object, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ContractError(f"{field} debe ser un datetime UTC")


def _positive_int(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractError(f"{field} debe ser un entero positivo")


class AuthorityKind(str, Enum):
    MEMORY = "memory"
    MEMORY_VERSION = "memory_version"
    IDENTITY = "identity"
    PROJECT = "project"
    ENVIRONMENT = "environment"
    GRANT = "grant"
    CONSISTENCY = "consistency"


@dataclass(frozen=True, slots=True)
class AuthorityRevision:
    authority_kind: AuthorityKind
    authority_id: str
    revision: int

    def __post_init__(self) -> None:
        if not isinstance(self.authority_kind, AuthorityKind):
            raise ContractError("authority_kind debe ser AuthorityKind")
        _required(self.authority_id, "authority_id")
        _positive_int(self.revision, "revision")


@dataclass(frozen=True, slots=True)
class AuthorizationRevisionSet:
    memory_revision: AuthorityRevision
    version_revision: AuthorityRevision
    identity_revision: AuthorityRevision
    project_revision: AuthorityRevision | None = None
    environment_revision: AuthorityRevision | None = None
    grant_revision: AuthorityRevision | None = None
    admission_generation: int | None = None

    def __post_init__(self) -> None:
        required = (
            (self.memory_revision, AuthorityKind.MEMORY, "memory_revision"),
            (self.version_revision, AuthorityKind.MEMORY_VERSION, "version_revision"),
            (self.identity_revision, AuthorityKind.IDENTITY, "identity_revision"),
        )
        for value, kind, field in required:
            if not isinstance(value, AuthorityRevision) or value.authority_kind is not kind:
                raise ContractError(f"{field} debe ser revisión de {kind.value}")
        optional = (
            (self.project_revision, AuthorityKind.PROJECT, "project_revision"),
            (self.environment_revision, AuthorityKind.ENVIRONMENT, "environment_revision"),
            (self.grant_revision, AuthorityKind.GRANT, "grant_revision"),
        )
        for value, kind, field in optional:
            if value is not None and (
                not isinstance(value, AuthorityRevision) or value.authority_kind is not kind
            ):
                raise ContractError(f"{field} debe ser revisión de {kind.value}")
        if self.admission_generation is not None:
            _positive_int(self.admission_generation, "admission_generation")


@dataclass(frozen=True, slots=True)
class AuthorizationSnapshot:
    """Evidencia inmutable emitida por CAM; no es un permiso autónomo."""

    snapshot_id: str
    decision_id: str
    request_id: str
    action: str
    actor_identity_id: str
    subject_user_id: str
    memory_id: str
    version_id: str
    owner_id: str
    scope: MemoryScope
    revisions: AuthorizationRevisionSet
    version_status: MemoryVersionStatus
    classification: MemoryClassification
    issued_at: datetime
    project_id: str | None = None
    environment_id: str | None = None
    grant_expires_at: datetime | None = None

    def __post_init__(self) -> None:
        for field in ("snapshot_id", "decision_id", "request_id", "action",
                      "actor_identity_id", "subject_user_id", "owner_id"):
            _required(getattr(self, field), field)
        validate_atlas_id(self.memory_id, "memory_id")
        validate_atlas_id(self.version_id, "version_id")
        if not isinstance(self.scope, MemoryScope):
            raise ContractError("scope debe ser MemoryScope")
        if not isinstance(self.revisions, AuthorizationRevisionSet):
            raise ContractError("revisions debe ser AuthorizationRevisionSet")
        if self.action != "memory.read":
            raise ContractError("action debe ser memory.read")
        if not isinstance(self.version_status, MemoryVersionStatus) or self.version_status is not MemoryVersionStatus.APPROVED:
            raise ContractError("el snapshot solo puede representar versiones APPROVED")
        if not isinstance(self.classification, MemoryClassification) or self.classification is MemoryClassification.RESTRICTED:
            raise ContractError("classification no permite un snapshot de lectura")
        _utc(self.issued_at, "issued_at")
        if self.revisions.admission_generation is not None:
            raise ContractError("CAM no puede asignar admission_generation antes de la admisión")
        if self.revisions.memory_revision.authority_id != self.memory_id:
            raise ContractError("memory_revision no corresponde a memory_id")
        if self.revisions.version_revision.authority_id != self.version_id:
            raise ContractError("version_revision no corresponde a version_id")
        if self.revisions.identity_revision.authority_id != self.actor_identity_id:
            raise ContractError("identity_revision no corresponde al actor")
        if self.scope.kind is MemoryScopeKind.PRIVATE:
            if self.subject_user_id != self.owner_id:
                raise ContractError("PRIVATE requiere que el sujeto autenticado sea el propietario")
            if any(v is not None for v in (
                self.project_id, self.environment_id, self.grant_expires_at,
                self.revisions.project_revision, self.revisions.environment_revision,
                self.revisions.grant_revision,
            )):
                raise ContractError("PRIVATE no puede incluir datos/revisiones PROJECT o Grant")
        elif self.scope.kind is MemoryScopeKind.PROJECT:
            _required(self.project_id, "project_id")
            _required(self.environment_id, "environment_id")
            if self.project_id != self.scope.project_id:
                raise ContractError("project_id no coincide con el scope canónico")
            project_rev = self.revisions.project_revision
            environment_rev = self.revisions.environment_revision
            grant_rev = self.revisions.grant_revision
            if any(v is None for v in (project_rev, environment_rev, grant_rev)):
                raise ContractError("PROJECT requiere revisiones de proyecto, entorno y Grant")
            if project_rev.authority_id != self.project_id:
                raise ContractError("project_revision no corresponde a project_id")
            if environment_rev.authority_id != self.environment_id:
                raise ContractError("environment_revision no corresponde a environment_id")
            if self.grant_expires_at is None:
                raise ContractError("PROJECT requiere grant_expires_at")
            _utc(self.grant_expires_at, "grant_expires_at")
            if self.grant_expires_at <= self.issued_at:
                raise ContractError("grant_expires_at debe ser posterior a issued_at")


@dataclass(frozen=True, slots=True)
class ReadTarget:
    memory_id: str
    version_id: str
    owner_id: str
    scope: MemoryScope

    def __post_init__(self) -> None:
        validate_atlas_id(self.memory_id, "memory_id")
        validate_atlas_id(self.version_id, "version_id")
        _required(self.owner_id, "owner_id")
        if not isinstance(self.scope, MemoryScope):
            raise ContractError("scope debe ser MemoryScope")


@dataclass(frozen=True, slots=True)
class DeliveryRouteSet:
    route_ids: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.route_ids, frozenset) or not self.route_ids:
            raise ContractError("route_ids debe ser un frozenset no vacío")
        for route_id in self.route_ids:
            _required(route_id, "route_id")


class ReadAdmissionStatus(str, Enum):
    ADMITTED = "admitted"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    UNRESOLVED = "unresolved"


_ALLOWED_ADMISSION_TRANSITIONS = {
    ReadAdmissionStatus.ADMITTED: {ReadAdmissionStatus.ACTIVE, ReadAdmissionStatus.CANCELLED, ReadAdmissionStatus.UNRESOLVED},
    ReadAdmissionStatus.ACTIVE: {ReadAdmissionStatus.COMPLETED, ReadAdmissionStatus.CANCELLED, ReadAdmissionStatus.UNRESOLVED},
    ReadAdmissionStatus.UNRESOLVED: {ReadAdmissionStatus.COMPLETED, ReadAdmissionStatus.CANCELLED},
    ReadAdmissionStatus.COMPLETED: set(),
    ReadAdmissionStatus.CANCELLED: set(),
}


@dataclass(frozen=True, slots=True)
class ReadAdmission:
    admission_id: str
    snapshot_id: str
    target: ReadTarget
    generation: int
    route_ids: frozenset[str]
    status: ReadAdmissionStatus
    admitted_at: datetime

    def __post_init__(self) -> None:
        _required(self.admission_id, "admission_id")
        _required(self.snapshot_id, "snapshot_id")
        if not isinstance(self.target, ReadTarget):
            raise ContractError("target debe ser ReadTarget")
        _positive_int(self.generation, "generation")
        if not isinstance(self.route_ids, frozenset) or not self.route_ids:
            raise ContractError("route_ids debe ser un frozenset no vacío")
        for route_id in self.route_ids:
            _required(route_id, "route_id")
        if not isinstance(self.status, ReadAdmissionStatus):
            raise ContractError("status debe ser ReadAdmissionStatus")
        _utc(self.admitted_at, "admitted_at")

    def transition(self, status: ReadAdmissionStatus) -> "ReadAdmission":
        if not isinstance(status, ReadAdmissionStatus):
            raise ContractError("status debe ser ReadAdmissionStatus")
        if status not in _ALLOWED_ADMISSION_TRANSITIONS[self.status]:
            raise ContractError(f"transición inválida: {self.status.value} -> {status.value}")
        return replace(self, status=status)


@dataclass(frozen=True, slots=True)
class AuthorizationInvalidation:
    invalidation_id: str
    authority: AuthorityKind
    authority_id: str
    previous_revision: int
    new_revision: int
    affected_admission_ids: frozenset[str]

    def __post_init__(self) -> None:
        _required(self.invalidation_id, "invalidation_id")
        if not isinstance(self.authority, AuthorityKind):
            raise ContractError("authority debe ser AuthorityKind")
        _required(self.authority_id, "authority_id")
        _positive_int(self.previous_revision, "previous_revision")
        _positive_int(self.new_revision, "new_revision")
        if self.new_revision <= self.previous_revision:
            raise ContractError("new_revision debe ser mayor que previous_revision")
        if not isinstance(self.affected_admission_ids, frozenset):
            raise ContractError("affected_admission_ids debe ser frozenset")
        for admission_id in self.affected_admission_ids:
            _required(admission_id, "admission_id")


@dataclass(frozen=True, slots=True)
class EndpointFenceReceipt:
    operation_id: str
    admission_id: str
    endpoint_id: str
    generation: int
    fenced_at: datetime
    confirmed: bool

    def __post_init__(self) -> None:
        for field in ("operation_id", "admission_id", "endpoint_id"):
            _required(getattr(self, field), field)
        _positive_int(self.generation, "generation")
        _utc(self.fenced_at, "fenced_at")
        if not isinstance(self.confirmed, bool):
            raise ContractError("confirmed debe ser bool")


@dataclass(frozen=True, slots=True)
class EgressReceipt:
    admission_id: str
    endpoint_id: str
    emission_id: str
    sequence: int
    generation: int
    committed_at: datetime

    def __post_init__(self) -> None:
        for field in ("admission_id", "endpoint_id", "emission_id"):
            _required(getattr(self, field), field)
        _positive_int(self.sequence, "sequence")
        _positive_int(self.generation, "generation")
        _utc(self.committed_at, "committed_at")



class EndpointDeliveryStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FENCED = "fenced"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class EndpointCompletionReceipt:
    admission_id: str
    endpoint_id: str
    final_sequence: int
    completed_at: datetime

    def __post_init__(self) -> None:
        _required(self.admission_id, "admission_id")
        _required(self.endpoint_id, "endpoint_id")
        if isinstance(self.final_sequence, bool) or not isinstance(self.final_sequence, int) or self.final_sequence < 0:
            raise ContractError("final_sequence debe ser un entero no negativo")
        _utc(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    operation_id: str
    resolved_admission_ids: frozenset[str]
    unresolved_admission_ids: frozenset[str]

    def __post_init__(self) -> None:
        _required(self.operation_id, "operation_id")
        for field in ("resolved_admission_ids", "unresolved_admission_ids"):
            values = getattr(self, field)
            if not isinstance(values, frozenset):
                raise ContractError(f"{field} debe ser frozenset")
            for value in values:
                _required(value, field)
        if self.resolved_admission_ids & self.unresolved_admission_ids:
            raise ContractError("una admisión no puede estar resuelta y no resuelta")
