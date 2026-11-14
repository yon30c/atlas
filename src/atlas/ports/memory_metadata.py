"""Puertos de lectura para metadatos autoritativos de Memory Engine."""
from typing import Protocol

from atlas.memory.metadata import (
    EnvironmentMetadata,
    MemoryVersionMetadata,
    ProjectMetadata,
)
from atlas.memory.models import Memory, MemoryId, MemoryVersionId, ProjectId


class MemoryMetadataPort(Protocol):
    """Resuelve metadatos de memoria/versiones; nunca devuelve contenido."""

    def get_memory(self, memory_id: MemoryId) -> Memory | None:
        """Obtiene owner, scope y puntero vigente de una memoria."""

    def get_version(
        self,
        memory_id: MemoryId,
        version_id: MemoryVersionId,
    ) -> MemoryVersionMetadata | None:
        """Obtiene estado y relación padre/hijo de una versión concreta."""


class ProjectMetadataPort(Protocol):
    """Consulta la fuente canónica de proyectos."""

    def get_project(self, project_id: ProjectId) -> ProjectMetadata | None:
        """Devuelve existencia y estado del proyecto."""


class EnvironmentMetadataPort(Protocol):
    """Consulta la fuente canónica de entornos."""

    def get_environment(
        self,
        environment_id: str,
    ) -> EnvironmentMetadata | None:
        """Devuelve existencia y estado del entorno."""
