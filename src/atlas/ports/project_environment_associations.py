"""Puerto de lectura para asociaciones canónicas Project/Environment."""

from typing import Protocol

from atlas.memory.models import EnvironmentId, ProjectId
from atlas.workspace.models import ProjectEnvironmentAssociation


class ProjectEnvironmentAssociationReaderPort(Protocol):
    """Resuelve la asociación exacta dentro de la transacción del caller."""

    def get_association(
        self, project_id: ProjectId, environment_id: EnvironmentId
    ) -> ProjectEnvironmentAssociation | None:
        """Devuelve el vínculo canónico exacto o None si no existe."""
        ...
