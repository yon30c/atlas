"""Immutable canonical records for Project/Environment links and Workspaces."""

from dataclasses import dataclass
from enum import Enum

from atlas.core.errors import ContractError
from atlas.memory.models import EnvironmentId, ProjectId


def _required(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value.strip() != value:
        raise ContractError(f"{field} debe ser texto no vacío y normalizado")
    return value


def _revision(value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractError("revision debe ser un entero positivo")


class ProjectEnvironmentStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class WorkspaceStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class ProjectEnvironmentAssociation:
    project_id: ProjectId
    environment_id: EnvironmentId
    status: ProjectEnvironmentStatus
    revision: int = 1

    def __post_init__(self) -> None:
        _required(self.project_id, "project_id")
        _required(self.environment_id, "environment_id")
        if not isinstance(self.status, ProjectEnvironmentStatus):
            raise ContractError("status debe ser ProjectEnvironmentStatus")
        _revision(self.revision)


@dataclass(frozen=True, slots=True)
class WorkspaceRecord:
    workspace_id: str
    owner_user_id: str
    project_id: ProjectId
    environment_id: EnvironmentId
    root_ref: str
    status: WorkspaceStatus = WorkspaceStatus.ACTIVE
    revision: int = 1

    def __post_init__(self) -> None:
        _required(self.workspace_id, "workspace_id")
        _required(self.owner_user_id, "owner_user_id")
        _required(self.project_id, "project_id")
        _required(self.environment_id, "environment_id")
        _required(self.root_ref, "root_ref")
        if "://" in self.root_ref or self.root_ref.startswith(("/", "\\\\")) or "\\\\" in self.root_ref:
            raise ContractError("root_ref debe ser una referencia simbólica, no una ruta")
        if not isinstance(self.status, WorkspaceStatus):
            raise ContractError("status debe ser WorkspaceStatus")
        _revision(self.revision)
