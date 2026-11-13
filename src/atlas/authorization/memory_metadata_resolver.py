"""Resolución tipada y fail-closed de metadatos autoritativos."""

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
from atlas.ports.memory_metadata import (
    EnvironmentMetadataPort,
    MemoryMetadataPort,
    ProjectMetadataPort,
)


class MemoryMetadataResolver:
    """Resuelve recursos de memoria/proyecto/entorno y valida su identidad exacta.

    Los puertos son fuentes autoritativas. Este resolver no usa datos del
    OperationContext como sustituto de metadatos canónicos y no recupera
    contenido de versiones.
    """

    def __init__(
        self,
        memory_port: MemoryMetadataPort,
        project_port: ProjectMetadataPort,
        environment_port: EnvironmentMetadataPort,
    ) -> None:
        self._memory_port = memory_port
        self._project_port = project_port
        self._environment_port = environment_port

    @staticmethod
    def _valid_id(value: object) -> bool:
        return isinstance(value, str) and bool(value.strip())

    def resolve_memory(self, memory_id: MemoryId) -> Memory | None:
        """Devuelve Memory solo si el puerto confirma exactamente el ID pedido."""
        if not self._valid_id(memory_id):
            return None
        try:
            result = self._memory_port.get_memory(memory_id)
        except Exception:
            return None
        if not isinstance(result, Memory) or result.memory_id != memory_id:
            return None
        return result

    def resolve_version(
        self,
        memory_id: MemoryId,
        version_id: MemoryVersionId,
    ) -> MemoryVersionMetadata | None:
        """Resuelve una versión solo bajo su memoria padre exacta."""
        if not self._valid_id(memory_id) or not self._valid_id(version_id):
            return None
        try:
            result = self._memory_port.get_version(memory_id, version_id)
        except Exception:
            return None
        if not isinstance(result, MemoryVersionMetadata):
            return None
        if result.memory_id != memory_id or result.version_id != version_id:
            return None
        return result

    def resolve_project(self, project_id: ProjectId) -> ProjectMetadata | None:
        """Devuelve metadatos solo si project_id coincide exactamente."""
        if not self._valid_id(project_id):
            return None
        try:
            result = self._project_port.get_project(project_id)
        except Exception:
            return None
        if not isinstance(result, ProjectMetadata) or result.project_id != project_id:
            return None
        return result

    def resolve_environment(
        self,
        environment_id: EnvironmentId,
    ) -> EnvironmentMetadata | None:
        """Devuelve metadatos solo si environment_id coincide exactamente."""
        if not self._valid_id(environment_id):
            return None
        try:
            result = self._environment_port.get_environment(environment_id)
        except Exception:
            return None
        if (
            not isinstance(result, EnvironmentMetadata)
            or result.environment_id != environment_id
        ):
            return None
        return result
