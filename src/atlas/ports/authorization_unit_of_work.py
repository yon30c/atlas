
"""Puerto de unidad de trabajo para operaciones de autorización."""

from typing import Protocol

from atlas.ports.grant_renewals import GrantRenewalRepository
from atlas.ports.grants import GrantRepository
from atlas.ports.agent_delegations import AgentDelegationRepository
from atlas.ports.identity_authority import IdentityAuthorityPort
from atlas.ports.agent_identity_authority import AgentIdentityAuthorityPort
from atlas.ports.native_agent_identity_authority import NativeAgentIdentityAuthorityPort
from atlas.ports.project_environment_associations import ProjectEnvironmentAssociationReaderPort
from atlas.ports.project_environment_associations import (
    ProjectEnvironmentAssociationReaderPort,
)


class AuthorizationUnitOfWork(Protocol):
    """Coordina operaciones atómicas sobre Grants y renovaciones."""

    grants: GrantRepository
    renewals: GrantRenewalRepository
    workspaces: ProjectEnvironmentAssociationReaderPort
    agent_delegations: AgentDelegationRepository
    identity: IdentityAuthorityPort
    agent_identity: AgentIdentityAuthorityPort
    native_agent_identity: NativeAgentIdentityAuthorityPort
    project_environments: object

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
