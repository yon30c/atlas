"""Snapshots tipados de metadatos autoritativos, sin contenido de memoria."""
from dataclasses import dataclass

from atlas.core.errors import ContractError
from atlas.memory.identifiers import validate_atlas_id
from atlas.memory.models import MemoryId, MemoryVersionId, MemoryVersionStatus, ProjectId


def _opaque_id(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacía")


@dataclass(frozen=True, slots=True)
class MemoryVersionMetadata:
    """Metadatos mínimos para validar una versión y su relación con la memoria."""

    version_id: MemoryVersionId
    memory_id: MemoryId
    status: MemoryVersionStatus
    parent_version_id: MemoryVersionId | None

    def __post_init__(self) -> None:
        validate_atlas_id(self.version_id, "version_id")
        validate_atlas_id(self.memory_id, "memory_id")
        if not isinstance(self.status, MemoryVersionStatus):
            raise ContractError("status debe ser MemoryVersionStatus")
        if self.parent_version_id is not None:
            validate_atlas_id(self.parent_version_id, "parent_version_id")


@dataclass(frozen=True, slots=True)
class ProjectMetadata:
    """Estado mínimo de un proyecto resuelto desde su fuente canónica."""

    project_id: ProjectId
    is_active: bool

    def __post_init__(self) -> None:
        _opaque_id(self.project_id, "project_id")
        if not isinstance(self.is_active, bool):
            raise ContractError("is_active debe ser bool")


@dataclass(frozen=True, slots=True)
class EnvironmentMetadata:
    """Identidad mínima de un entorno resuelto desde su fuente canónica."""

    environment_id: str
    is_active: bool

    def __post_init__(self) -> None:
        _opaque_id(self.environment_id, "environment_id")
        if not isinstance(self.is_active, bool):
            raise ContractError("is_active debe ser bool")
