"""Explicit composition root for the canonical local authority SQLite store.

This module only binds one database instance to the shared authority UoW
factory. It deliberately does not create directories, initialize SQLite,
apply migrations, provision authority records, or register a runtime.
"""

from dataclasses import dataclass
from pathlib import Path

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.local_authority_unit_of_work import (
    SQLiteLocalAuthorityUnitOfWorkFactory,
)
from atlas.core.errors import ContractError


@dataclass(frozen=True, slots=True)
class SQLiteLocalAuthorityStorageComposition:
    """One database instance and the UoW factory bound to that exact instance."""

    database: SQLiteDatabase
    unit_of_work_factory: SQLiteLocalAuthorityUnitOfWorkFactory

    def __post_init__(self) -> None:
        if not isinstance(self.database, SQLiteDatabase):
            raise ContractError("database debe ser SQLiteDatabase")
        if not isinstance(
            self.unit_of_work_factory,
            SQLiteLocalAuthorityUnitOfWorkFactory,
        ):
            raise ContractError(
                "unit_of_work_factory debe ser SQLiteLocalAuthorityUnitOfWorkFactory"
            )
        if self.unit_of_work_factory._database is not self.database:
            raise ContractError(
                "database y unit_of_work_factory deben compartir la misma instancia SQLite"
            )


def compose_sqlite_local_authority_storage_on_database(
    database: SQLiteDatabase,
) -> SQLiteLocalAuthorityStorageComposition:
    """Bind the shared authority UoW factory to an already-created database.

    The caller owns path selection and database lifecycle. This function does
    not initialize the database or apply migrations.
    """
    if not isinstance(database, SQLiteDatabase):
        raise ContractError("database debe ser SQLiteDatabase")

    return SQLiteLocalAuthorityStorageComposition(
        database=database,
        unit_of_work_factory=SQLiteLocalAuthorityUnitOfWorkFactory(database),
    )


def compose_sqlite_local_authority_storage(
    path: str | Path,
    *,
    busy_timeout_ms: int = 5000,
) -> SQLiteLocalAuthorityStorageComposition:
    """Create one database object and bind the canonical authority UoW factory.

    The parent directory must already exist. No file is created until the
    database is first opened, and no schema migration is run here. Deployment
    and administrative tooling must perform those steps explicitly.
    """
    database = SQLiteDatabase(path, busy_timeout_ms=busy_timeout_ms)
    return compose_sqlite_local_authority_storage_on_database(database)
