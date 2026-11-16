"""Shared SQLite transaction scope for canonical local authority repositories.

This is a persistence composition seam, not an authorization or consistency
coordinator. It does not admit operations, invalidate grants, fence routes,
or release authority-change claims.
"""

from typing import Self

from atlas.adapters.sqlite.authorization_unit_of_work import (
    SQLiteAuthorizationUnitOfWork,
)
from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.authority_changes import SQLiteAuthorityChangeStore
from atlas.adapters.sqlite.identity_authority import SQLiteIdentityAuthority
from atlas.adapters.sqlite.project_environment_repository import (
    SQLiteProjectEnvironmentRepository,
)
from atlas.adapters.sqlite.recovery_evidence_trust_policy_repository import (
    SQLiteRecoveryEvidenceIssuerTrustPolicyRepository,
)
from atlas.core.errors import ContractError


class SQLiteLocalAuthorityUnitOfWork(SQLiteAuthorizationUnitOfWork):
    """One transaction shared by Identity, Grants, renewals, Project and Environment."""

    def __init__(self, database: SQLiteDatabase) -> None:
        super().__init__(database)
        self.identity = None
        self.project_environments = None
        self.authority_changes = None
        self.recovery_evidence_trust_policies = None

    def __enter__(self) -> Self:
        super().__enter__()
        try:
            self.identity = SQLiteIdentityAuthority(
                self._database,
                unit_of_work=self._unit,
            )
            self.project_environments = SQLiteProjectEnvironmentRepository(
                self._database,
                unit_of_work=self._unit,
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
