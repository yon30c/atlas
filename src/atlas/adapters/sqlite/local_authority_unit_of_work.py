"""Shared SQLite transaction scope for canonical local authority repositories.

This is a persistence composition seam, not an authorization or consistency
coordinator. It can persist recovery-evidence admission receipts, but does not
authorize operations, invalidate grants, fence effects, or release claims.
"""

from typing import Self

from atlas.adapters.sqlite.authorization_unit_of_work import (
    SQLiteAuthorizationUnitOfWork,
)
from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.authority_changes import SQLiteAuthorityChangeStore
from atlas.adapters.sqlite.identity_authority import SQLiteIdentityAuthority
from atlas.adapters.sqlite.platform_admin_authority import SQLitePlatformAdminAuthorityReader
from atlas.adapters.sqlite.agent_identity_authority import SQLiteAgentIdentityAuthority
from atlas.adapters.sqlite.native_agent_identity_authority import SQLiteNativeAgentIdentityAuthority
from atlas.adapters.sqlite.agent_delegation_repository import SQLiteAgentDelegationRepository
from atlas.adapters.sqlite.native_identity_authority import SQLiteNativeIdentityAuthority
from atlas.adapters.sqlite.native_authentication_authority import SQLiteNativeAuthenticationAuthority
from atlas.adapters.sqlite.project_environment_repository import (
    SQLiteProjectEnvironmentRepository,
)
from atlas.adapters.sqlite.project_environment_association_repository import (
    SQLiteProjectEnvironmentAssociationRepository,
)
from atlas.adapters.sqlite.workspace_registry_repository import (
    SQLiteWorkspaceRegistryRepository,
)
from atlas.adapters.sqlite.recovery_evidence_issuer_registry_repository import (
    SQLiteRecoveryEvidenceIssuerRegistryRepository,
)
from atlas.adapters.sqlite.recovery_evidence_admission_repository import (
    SQLiteRecoveryEvidenceAdmissionRepository,
)
from atlas.adapters.sqlite.recovery_evidence_trust_policy_repository import (
    SQLiteRecoveryEvidenceIssuerTrustPolicyRepository,
)
from atlas.core.errors import ContractError


class SQLiteLocalAuthorityUnitOfWork(SQLiteAuthorizationUnitOfWork):
    """One transaction shared by canonical authorities, ledger, trust policies and issuer inventory."""

    def __init__(self, database: SQLiteDatabase) -> None:
        super().__init__(database)
        self.identity = None
        self.platform_admin = None
        self.agent_identity = None
        self.native_agent_identity = None
        self.agent_delegations = None
        self.native_identity = None
        self.native_authentication = None
        self.project_environments = None
        self.workspaces = None
        self.project_environment_associations = None
        self.authority_changes = None
        self.recovery_evidence_trust_policies = None
        self.recovery_evidence_issuer_registry = None
        self.recovery_evidence_admissions = None

    def __enter__(self) -> Self:
        super().__enter__()
        try:
            self.identity = SQLiteIdentityAuthority(
                self._database,
                unit_of_work=self._unit,
            )
            self.platform_admin = SQLitePlatformAdminAuthorityReader(
                self._database,
                unit_of_work=self._unit,
            )
            self.agent_identity = SQLiteAgentIdentityAuthority(
                self._database,
                unit_of_work=self._unit,
            )
            self.native_agent_identity = SQLiteNativeAgentIdentityAuthority(
                self._database,
                unit_of_work=self._unit,
            )
            self.agent_delegations = SQLiteAgentDelegationRepository(
                self._database,
                unit_of_work=self._unit,
            )
            self.native_identity = SQLiteNativeIdentityAuthority(
                self._database,
                unit_of_work=self._unit,
            )
            self.native_authentication = SQLiteNativeAuthenticationAuthority(
                self._database,
                unit_of_work=self._unit,
            )
            self.project_environments = SQLiteProjectEnvironmentRepository(
                self._database,
                unit_of_work=self._unit,
            )
            self.workspaces = SQLiteWorkspaceRegistryRepository(
                self._database,
                unit_of_work=self._unit,
            )
            self.project_environment_associations = (
                SQLiteProjectEnvironmentAssociationRepository(
                    self._database,
                    unit_of_work=self._unit,
                )
            )
            self.authority_changes = SQLiteAuthorityChangeStore(
                self._database,
                unit_of_work=self._unit,
            )
            self.recovery_evidence_trust_policies = (
                SQLiteRecoveryEvidenceIssuerTrustPolicyRepository(
                    self._database,
                    unit_of_work=self._unit,
                )
            )
            self.recovery_evidence_issuer_registry = (
                SQLiteRecoveryEvidenceIssuerRegistryRepository(
                    self._database,
                    unit_of_work=self._unit,
                )
            )
            self.recovery_evidence_admissions = (
                SQLiteRecoveryEvidenceAdmissionRepository(
                    self._database,
                    unit_of_work=self._unit,
                )
            )
            return self
        except BaseException as exc:
            self.__exit__(type(exc), exc, exc.__traceback__)
            raise


class SQLiteLocalAuthorityUnitOfWorkFactory:
    """Creates shared local-authority transaction scopes for one database."""

    def __init__(self, database: SQLiteDatabase) -> None:
        if not isinstance(database, SQLiteDatabase):
            raise ContractError("database debe ser SQLiteDatabase")
        self._database = database

    def __call__(self) -> SQLiteLocalAuthorityUnitOfWork:
        return SQLiteLocalAuthorityUnitOfWork(self._database)
