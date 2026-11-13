"""Modelos inmutables del dominio de memoria Atlas."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import NewType
from urllib.parse import urlsplit

from atlas.core.errors import ContractError
from atlas.memory.identifiers import validate_atlas_id


MemoryId = NewType("MemoryId", str)
MemoryVersionId = NewType("MemoryVersionId", str)
ProposalId = NewType("ProposalId", str)
UserId = NewType("UserId", str)
IdentityId = NewType("IdentityId", str)
ProjectId = NewType("ProjectId", str)
EnvironmentId = NewType("EnvironmentId", str)


class MemoryScopeKind(str, Enum):
    PRIVATE = "PRIVATE"
    PROJECT = "PROJECT"


class MemoryVersionStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    FORGOTTEN = "forgotten"


class MemoryClassification(str, Enum):
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class MemoryProposalIntent(str, Enum):
    CREATE_MEMORY = "CREATE_MEMORY"
    NEW_VERSION = "NEW_VERSION"


class SourceKind(str, Enum):
    USER_INPUT = "USER_INPUT"
    CONVERSATION = "CONVERSATION"
    FILE = "FILE"
    CONNECTOR = "CONNECTOR"
    TOOL_RESULT = "TOOL_RESULT"
    SYSTEM_EVENT = "SYSTEM_EVENT"
    DERIVED = "DERIVED"
    IMPORT = "IMPORT"


class ReferenceAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


def _required(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacía")
    return value


def _optional_required(value: object, field: str) -> None:
    if value is not None:
        _required(value, field)


def _utc(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ContractError(f"{field} debe ser un datetime con zona horaria UTC")
    offset = value.utcoffset()
    if offset is None or offset != timedelta(0):
        raise ContractError(f"{field} debe estar en UTC")
    return value


def _enum(value: object, enum_type: type[Enum], field: str) -> None:
    if not isinstance(value, enum_type):
        raise ContractError(f"{field} debe ser {enum_type.__name__}")


def _opaque_id(value: object, field: str, optional: bool = False) -> None:
    if optional and value is None:
        return
    _required(value, field)


def _no_url_or_credentials(value: str, field: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or "://" in value:
        raise ContractError(f"{field} debe ser una referencia opaca, no una URL")


@dataclass(frozen=True, slots=True)
class MemoryScope:
    kind: MemoryScopeKind
    project_id: ProjectId | None = None

    def __post_init__(self) -> None:
        _enum(self.kind, MemoryScopeKind, "kind")
        if self.kind is MemoryScopeKind.PRIVATE and self.project_id is not None:
            raise ContractError("PRIVATE no admite project_id")
        if self.kind is MemoryScopeKind.PROJECT:
            _opaque_id(self.project_id, "project_id")


@dataclass(frozen=True, slots=True)
class Memory:
    memory_id: MemoryId
    owner_id: UserId
    scope: MemoryScope
    current_approved_version_id: MemoryVersionId | None
    created_at: datetime
    updated_at: datetime
    revision: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise ContractError("revision debe ser un entero positivo")
        validate_atlas_id(self.memory_id, "memory_id")
        _opaque_id(self.owner_id, "owner_id")
        if not isinstance(self.scope, MemoryScope):
            raise ContractError("scope debe ser MemoryScope")
        if self.current_approved_version_id is not None:
            validate_atlas_id(self.current_approved_version_id, "current_approved_version_id")
        _utc(self.created_at, "created_at")
        _utc(self.updated_at, "updated_at")
        if self.updated_at < self.created_at:
            raise ContractError("updated_at no puede ser anterior a created_at")


@dataclass(frozen=True, slots=True)
class ProvenanceContext:
    origin: str
    actor_identity_id: IdentityId
    request_id: str
    correlation_id: str
    project_id: ProjectId | None = None
    environment_id: EnvironmentId | None = None

    def __post_init__(self) -> None:
        _required(self.origin, "origin")
        _opaque_id(self.actor_identity_id, "actor_identity_id")
        _required(self.request_id, "request_id")
        _required(self.correlation_id, "correlation_id")
        _opaque_id(self.project_id, "project_id", optional=True)
        _opaque_id(self.environment_id, "environment_id", optional=True)


@dataclass(frozen=True, slots=True)
class OpaqueReference:
    resource_type: str
    resource_id: str
    availability: ReferenceAvailability

    def __post_init__(self) -> None:
        _required(self.resource_type, "resource_type")
        resource_id = _required(self.resource_id, "resource_id")
        _enum(self.availability, ReferenceAvailability, "availability")
        _no_url_or_credentials(resource_id, "resource_id")


@dataclass(frozen=True, slots=True)
class MemoryProvenance:
    source_kind: SourceKind
    source_ref: OpaqueReference | None
    captured_at: datetime
    captured_by: IdentityId
    origin_context: ProvenanceContext
    transformation: str | None = None
    evidence_refs: tuple[OpaqueReference, ...] = ()

    def __post_init__(self) -> None:
        _enum(self.source_kind, SourceKind, "source_kind")
        if self.source_ref is not None and not isinstance(self.source_ref, OpaqueReference):
            raise ContractError("source_ref debe ser OpaqueReference o None")
        _utc(self.captured_at, "captured_at")
        _opaque_id(self.captured_by, "captured_by")
        if not isinstance(self.origin_context, ProvenanceContext):
            raise ContractError("origin_context debe ser ProvenanceContext")
        if self.transformation is not None:
            _required(self.transformation, "transformation")
        if not isinstance(self.evidence_refs, tuple):
            raise ContractError("evidence_refs debe ser tuple")
        if any(not isinstance(ref, OpaqueReference) for ref in self.evidence_refs):
            raise ContractError("evidence_refs solo admite OpaqueReference")


@dataclass(frozen=True, slots=True)
class MemoryVersion:
    version_id: MemoryVersionId
    memory_id: MemoryId
    version_number: int
    content: str
    classification: MemoryClassification
    status: MemoryVersionStatus
    provenance: MemoryProvenance
    parent_version_id: MemoryVersionId | None
    created_at: datetime
    submitted_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: UserId | None = None
    revision: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise ContractError("revision debe ser un entero positivo")
        validate_atlas_id(self.version_id, "version_id")
        validate_atlas_id(self.memory_id, "memory_id")
        if isinstance(self.version_number, bool) or not isinstance(self.version_number, int) or self.version_number < 1:
            raise ContractError("version_number debe ser un entero positivo")
        _required(self.content, "content")
        _enum(self.classification, MemoryClassification, "classification")
        _enum(self.status, MemoryVersionStatus, "status")
        if not isinstance(self.provenance, MemoryProvenance):
            raise ContractError("provenance debe ser MemoryProvenance")
        if self.parent_version_id is not None:
            validate_atlas_id(self.parent_version_id, "parent_version_id")
        _utc(self.created_at, "created_at")
        _utc(self.submitted_at, "submitted_at")
        if self.submitted_at < self.created_at:
            raise ContractError("submitted_at no puede ser anterior a created_at")
        if self.reviewed_at is not None:
            _utc(self.reviewed_at, "reviewed_at")
            if self.reviewed_at < self.submitted_at:
                raise ContractError("reviewed_at no puede ser anterior a submitted_at")
        _optional_required(self.reviewed_by, "reviewed_by")
        if self.status is MemoryVersionStatus.PENDING_REVIEW:
            if self.reviewed_at is not None or self.reviewed_by is not None:
                raise ContractError("pending_review no puede contener datos de revisión")
        elif self.reviewed_at is None or self.reviewed_by is None:
            raise ContractError("un estado revisado exige reviewed_at y reviewed_by")


@dataclass(frozen=True, slots=True)
class MemoryProposal:
    proposal_id: ProposalId
    intent: MemoryProposalIntent
    memory_id: MemoryId
    version_id: MemoryVersionId
    submitted_by: IdentityId
    submitted_at: datetime

    def __post_init__(self) -> None:
        validate_atlas_id(self.proposal_id, "proposal_id")
        _enum(self.intent, MemoryProposalIntent, "intent")
        validate_atlas_id(self.memory_id, "memory_id")
        validate_atlas_id(self.version_id, "version_id")
        _opaque_id(self.submitted_by, "submitted_by")
        _utc(self.submitted_at, "submitted_at")
