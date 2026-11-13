"""Snapshots tipados de metadatos autoritativos, sin contenido de memoria."""
from dataclasses import dataclass

from atlas.core.errors import ContractError
from atlas.memory.identifiers import validate_atlas_id
from atlas.memory.models import (
    MemoryClassification,
    MemoryId,
    MemoryVersionId,
    MemoryVersionStatus,
    ProjectId,
)


def _opaque_id(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacía")


@dataclass(frozen=True, slots=True)
class MemoryVersionMetadata:
    """Metadatos mínimos para validar una versión y su relación con la memoria."""

    version_id: MemoryVersionId
    memory_id: MemoryId
    status: MemoryVersionStatus
    classification: MemoryClassification
    parent_version_id: MemoryVersionId | None

    def __post_init__(self) -> None:
        validate_atlas_id(self.version_id, "version_id")
        validate_atlas_id(self.memory_id, "memory_id")
        if not isinstance(self.status, MemoryVersionStatus):
            raise ContractError("status debe ser MemoryVersionStatus")
        if not isinstance(self.classification, MemoryClassification):
            raise ContractError("classification debe ser MemoryClassification")
        if self.parent_version_id is not None:
            validate_atlas_id(self.parent_version_id, "parent_version_id")


@dataclass(frozen=True, slots=True)
class ProjectMetadata:
    """Estado mínimo de un proyecto resuelto desde su fuente canónica."""

    project_id: ProjectId
    status: str

    def __post_init__(self) -> None:
        _opaque_id(self.project_id, "project_id")
        _opaque_id(self.status, "status")


@dataclass(frozen=True, slots=True)
class EnvironmentMetadata:
    """Identidad mínima de un entorno resuelto desde su fuente canónica."""

    environment_id: str
    status: str

    def __post_init__(self) -> None:
        _opaque_id(self.environment_id, "environment_id")
        _opaque_id(self.status, "status")
