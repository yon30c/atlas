"""Snapshots tipados de metadatos autoritativos, sin contenido de memoria."""
from dataclasses import dataclass
from uuid import UUID

from atlas.memory.errors import MemoryContractError
from atlas.memory.models import (
    EnvironmentId,
    MemoryClassification,
    MemoryId,
    MemoryVersionId,
    MemoryVersionStatus,
    ProjectId,
)


def _opaque_id(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise MemoryContractError(f"{field} debe ser una cadena no vacía")


def _memory_uuid7(value: object, field: str) -> None:
    if not isinstance(value, str):
        raise MemoryContractError(f"{field} debe ser un UUIDv7")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise MemoryContractError(f"{field} debe ser un UUIDv7") from None
    if parsed.version != 7 or str(parsed) != value:
        raise MemoryContractError(f"{field} debe usar UUIDv7 canónico lowercase")


@dataclass(frozen=True, slots=True)
class MemoryVersionMetadata:
    """Metadatos mínimos para validar una versión y su relación con la memoria."""

    version_id: MemoryVersionId
    memory_id: MemoryId
    status: MemoryVersionStatus
    classification: MemoryClassification
    parent_version_id: MemoryVersionId | None
    revision: int

    def __post_init__(self) -> None:
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise MemoryContractError("revision debe ser un entero positivo")
        _memory_uuid7(self.version_id, "version_id")
        _memory_uuid7(self.memory_id, "memory_id")
        if not isinstance(self.status, MemoryVersionStatus):
            raise MemoryContractError("status debe ser MemoryVersionStatus")
        if not isinstance(self.classification, MemoryClassification):
            raise MemoryContractError("classification debe ser MemoryClassification")
        if self.parent_version_id is not None:
            _memory_uuid7(self.parent_version_id, "parent_version_id")


@dataclass(frozen=True, slots=True)
class ProjectMetadata:
    """Estado mínimo de un proyecto resuelto desde su fuente canónica."""

    project_id: ProjectId
    status: str
    revision: int

    def __post_init__(self) -> None:
        _opaque_id(self.project_id, "project_id")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise MemoryContractError("revision debe ser un entero positivo")
        _opaque_id(self.status, "status")


@dataclass(frozen=True, slots=True)
class EnvironmentMetadata:
    """Identidad mínima de un entorno resuelto desde su fuente canónica."""

    environment_id: EnvironmentId
    status: str
    revision: int

    def __post_init__(self) -> None:
        _opaque_id(self.environment_id, "environment_id")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise MemoryContractError("revision debe ser un entero positivo")
        _opaque_id(self.status, "status")
