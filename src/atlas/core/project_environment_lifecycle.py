"""Domain contracts for audited Project/Environment lifecycle transitions."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from uuid import UUID

from atlas.core.errors import ContractError
from atlas.memory.models import EnvironmentId, ProjectId
from atlas.workspace.models import ProjectEnvironmentStatus


def _required(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value.strip() != value:
        raise ContractError(f"{field} debe ser texto no vacío y normalizado")
    return value


def _uuid4(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{field} debe ser UUIDv4 canónico")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise ContractError(f"{field} debe ser UUIDv4 canónico") from None
    if parsed.version != 4 or str(parsed) != value:
        raise ContractError(f"{field} debe ser UUIDv4 canónico lowercase")
    return value


def _revision(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractError(f"{field} debe ser un entero positivo")


def _utc(value: object, field: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ContractError(f"{field} debe ser datetime UTC")


def _reason(value: object) -> str:
    if not isinstance(value, str):
        raise ContractError("reason debe ser texto")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ContractError("reason no admite caracteres de control")
    normalized = " ".join(value.split())
    if not normalized or normalized != value or len(normalized) > 500:
        raise ContractError(
            "reason debe estar normalizado, contener entre 1 y 500 caracteres"
        )
    return normalized


@dataclass(frozen=True, slots=True)
class ProjectEnvironmentLifecycleRequest:
    """Caller intent only; it carries no authorization claims."""

    project_id: ProjectId
    environment_id: EnvironmentId
    target_status: ProjectEnvironmentStatus
    expected_revision: int
    reason: str

    def __post_init__(self) -> None:
        _required(self.project_id, "project_id")
        _required(self.environment_id, "environment_id")
        if not isinstance(self.target_status, ProjectEnvironmentStatus):
            raise ContractError("target_status debe ser ProjectEnvironmentStatus")
        if self.target_status not in (
            ProjectEnvironmentStatus.ACTIVE,
            ProjectEnvironmentStatus.SUSPENDED,
        ):
            raise ContractError("target_status no es una transición admitida")
        _revision(self.expected_revision, "expected_revision")
        _reason(self.reason)


@dataclass(frozen=True, slots=True)
class ProjectEnvironmentLifecycleEvent:
    """Immutable audit fact for one authorized association state transition."""

    event_id: str
    project_id: ProjectId
    environment_id: EnvironmentId
    previous_status: ProjectEnvironmentStatus
    new_status: ProjectEnvironmentStatus
    previous_revision: int
    new_revision: int
    actor_user_id: str
    actor_identity_id: str
    verified_identity_context_id: str
    request_id: str
    correlation_id: str
    reason: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        _uuid4(self.event_id, "event_id")
        _required(self.project_id, "project_id")
        _required(self.environment_id, "environment_id")
        if not isinstance(self.previous_status, ProjectEnvironmentStatus):
            raise ContractError("previous_status inválido")
        if not isinstance(self.new_status, ProjectEnvironmentStatus):
            raise ContractError("new_status inválido")
        if self.previous_status is self.new_status:
            raise ContractError("el evento debe representar una transición real")
        if {
            self.previous_status,
            self.new_status,
        } != {
            ProjectEnvironmentStatus.ACTIVE,
            ProjectEnvironmentStatus.SUSPENDED,
        }:
            raise ContractError("transición de asociación no admitida")
        _revision(self.previous_revision, "previous_revision")
        _revision(self.new_revision, "new_revision")
        if self.new_revision != self.previous_revision + 1:
            raise ContractError("new_revision debe ser previous_revision + 1")
        for field in (
            "actor_user_id",
            "actor_identity_id",
            "verified_identity_context_id",
        ):
            _uuid4(getattr(self, field), field)
        _required(self.request_id, "request_id")
        _required(self.correlation_id, "correlation_id")
        _reason(self.reason)
        _utc(self.occurred_at, "occurred_at")
