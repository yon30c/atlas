"""Shared SQLite composition for the local authority foundation."""

from dataclasses import dataclass
from pathlib import Path

from atlas.adapters.sqlite.authority_changes import SQLiteAuthorityChangeStore
from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.grant_repository import SQLiteGrantRepository
from atlas.adapters.sqlite.grant_renewal_repository import SQLiteGrantRenewalRepository
from atlas.adapters.sqlite.project_environment_repository import (
    SQLiteProjectEnvironmentRepository,
)
from atlas.adapters.sqlite.authorization_unit_of_work import (
    SQLiteAuthorizationUnitOfWorkFactory,
)
from atlas.adapters.sqlite.identity_composition import (
    SQLiteIdentityComposition,
    compose_sqlite_identity_on_database,
)
from atlas.core.errors import ContractError


@dataclass(frozen=True, slots=True)
class SQLiteLocalAuthorityFoundation:
    """Identity, Grant and authority-change persistence on one exact database."""

    database: SQLiteDatabase
    identity: SQLiteIdentityComposition
    grants: SQLiteGrantRepository
    renewals: SQLiteGrantRenewalRepository
    projects_environments: SQLiteProjectEnvironmentRepository
    authorization_unit_of_work_factory: SQLiteAuthorizationUnitOfWorkFactory
    authority_changes: SQLiteAuthorityChangeStore

    def __post_init__(self) -> None:
        if not isinstance(self.database, SQLiteDatabase):
            raise ContractError("database debe ser SQLiteDatabase")
        if not isinstance(self.identity, SQLiteIdentityComposition):
            raise ContractError("identity debe ser SQLiteIdentityComposition")
        if self.identity.database is not self.database:
            raise ContractError("Identity debe compartir la base canónica")
        if not isinstance(self.grants, SQLiteGrantRepository):
            raise ContractError("grants debe ser SQLiteGrantRepository")
        if self.grants._database is not self.database:
            raise ContractError("Grant debe compartir la base canónica")
        if not isinstance(self.renewals, SQLiteGrantRenewalRepository):
            raise ContractError("renewals debe ser SQLiteGrantRenewalRepository")
        if self.renewals._database is not self.database:
            raise ContractError("renewals debe compartir la base canónica")
        if not isinstance(self.projects_environments, SQLiteProjectEnvironmentRepository):
            raise ContractError("projects_environments debe ser SQLiteProjectEnvironmentRepository")
        if self.projects_environments._database is not self.database:
            raise ContractError("Project/Environment debe compartir la base canónica")
        if not isinstance(self.authorization_unit_of_work_factory, SQLiteAuthorizationUnitOfWorkFactory):
            raise ContractError("authorization_unit_of_work_factory inválida")
        if self.authorization_unit_of_work_factory._database is not self.database:
            raise ContractError("la unidad de autorización debe compartir la base canónica")
        if not isinstance(self.authority_changes, SQLiteAuthorityChangeStore):
            raise ContractError("authority_changes debe ser SQLiteAuthorityChangeStore")
        if self.authority_changes._database is not self.database:
            raise ContractError("authority changes debe compartir la base canónica")


def compose_sqlite_local_authority(
    path: str | Path,
    *,
    busy_timeout_ms: int = 5000,
) -> SQLiteLocalAuthorityFoundation:
    """Create the initial shared local authority composition.

    This foundation includes Identity, Grants, Project/Environment metadata
    and the durable authority-change ledger. Invalidation coordination and
    admission remain deliberately uncomposed.
    """
    database = SQLiteDatabase(path, busy_timeout_ms=busy_timeout_ms)
    identity = compose_sqlite_identity_on_database(database)
    grants = SQLiteGrantRepository(database)
    renewals = SQLiteGrantRenewalRepository(database)
    projects_environments = SQLiteProjectEnvironmentRepository(database)
    authorization_unit_of_work_factory = SQLiteAuthorizationUnitOfWorkFactory(database)
    authority_changes = SQLiteAuthorityChangeStore(database)
    return SQLiteLocalAuthorityFoundation(
        database=database,
        identity=identity,
        grants=grants,
        renewals=renewals,
        projects_environments=projects_environments,
        authorization_unit_of_work_factory=authorization_unit_of_work_factory,
        authority_changes=authority_changes,
    )
