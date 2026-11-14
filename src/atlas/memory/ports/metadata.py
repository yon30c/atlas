"""Puertos neutrales para resolver metadatos autoritativos de memoria.

Los adaptadores de cada consumidor implementan estos contratos consultando
sus propias fuentes canónicas. Los puertos nunca devuelven contenido de memoria.
"""
from typing import Protocol

from atlas.memory.metadata import (
    EnvironmentMetadata,
    MemoryVersionMetadata,
    ProjectMetadata,
)
from atlas.memory.models import (
    EnvironmentId,
    Memory,
    MemoryId,
    MemoryVersionId,
    ProjectId,
)


class MemoryMetadataPort(Protocol):
    """Metadatos de memoria y versiones, sin contenido."""

    def get_memory(self, memory_id: MemoryId) -> Memory | None:
        """Devuelve owner, scope y puntero vigente de la memoria."""

    def get_version(
        self,
        memory_id: MemoryId,
        version_id: MemoryVersionId,
    ) -> MemoryVersionMetadata | None:
        """Devuelve metadatos de una versión bajo su memoria padre exacta."""


class ProjectMetadataPort(Protocol):
    """Consulta la fuente canónica del consumidor para proyectos."""

    def get_project(self, project_id: ProjectId) -> ProjectMetadata | None:
        """Devuelve existencia, estado y revisión del proyecto."""


class EnvironmentMetadataPort(Protocol):
    """Consulta la fuente canónica del consumidor para entornos."""

    def get_environment(
        self,
        environment_id: EnvironmentId,
    ) -> EnvironmentMetadata | None:
        """Devuelve existencia, estado y revisión del entorno."""
