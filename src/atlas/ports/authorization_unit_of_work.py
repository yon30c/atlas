
"""Puerto de unidad de trabajo para operaciones de autorización."""

from typing import Protocol

from atlas.ports.grant_renewals import GrantRenewalRepository
from atlas.ports.grants import GrantRepository
from atlas.ports.project_environment_associations import (
    ProjectEnvironmentAssociationReaderPort,
)


class AuthorizationUnitOfWork(Protocol):
    """Coordina operaciones atómicas sobre Grants y renovaciones."""

    grants: GrantRepository
    renewals: GrantRenewalRepository
    workspaces: ProjectEnvironmentAssociationReaderPort

    def __enter__(self) -> "AuthorizationUnitOfWork":
        """Inicia la unidad de trabajo."""
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> None:
        """Finaliza la unidad de trabajo."""
        ...

    def commit(self) -> None:
        """Confirma atómicamente todos los cambios."""
        ...

    def rollback(self) -> None:
        """Revierte todos los cambios pendientes."""
        ...
