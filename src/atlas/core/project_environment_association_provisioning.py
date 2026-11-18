"""Domain contracts for offline Project/Environment association provisioning."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from atlas.core.errors import ContractError
from atlas.memory.models import EnvironmentId, ProjectId


def _uuid4(value: object, field: str) -> None:
    if not isinstance(value, str):
        raise ContractError(f"{field} debe ser UUIDv4")
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise ContractError(f"{field} debe ser UUIDv4") from exc
    if parsed.version != 4 or str(parsed) != value:
        raise ContractError(f"{field} debe ser UUIDv4 canónico")


def _normalized_text(value: object, field: str, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ContractError(f"{field} debe ser texto normalizado sin controles")


@dataclass(frozen=True, slots=True)
class ProjectEnvironmentAssociationProvisioningRequest:
    """Exact operator intent; it carries no Atlas identity or permission claim."""

    operation_id: str
    project_id: ProjectId
    environment_id: EnvironmentId
    reason: str

    def __post_init__(self) -> None:
        _uuid4(self.operation_id, "operation_id")
        _normalized_text(self.project_id, "project_id", 256)
        _normalized_text(self.environment_id, "environment_id", 256)
        _normalized_text(self.reason, "reason", 500)


@dataclass(frozen=True, slots=True)
class ProjectEnvironmentAssociationProvisioningProvenance:
    """Host-process evidence captured by the guarded offline entrypoint."""

    event_id: str
    real_uid: int
    effective_uid: int
    terminal_id: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        _uuid4(self.event_id, "event_id")
        if isinstance(self.real_uid, bool) or not isinstance(self.real_uid, int) or self.real_uid <= 0:
            raise ContractError("real_uid debe ser un entero positivo")
        if (
            isinstance(self.effective_uid, bool)
            or not isinstance(self.effective_uid, int)
            or self.effective_uid != 0
        ):
            raise ContractError("effective_uid debe ser exactamente 0")
        _normalized_text(self.terminal_id, "terminal_id", 256)
        if (
            not isinstance(self.occurred_at, datetime)
            or self.occurred_at.tzinfo is None
            or self.occurred_at.utcoffset() != timedelta(0)
        ):
            raise ContractError("occurred_at debe ser datetime UTC")
