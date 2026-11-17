"""Explicit composition root for the canonical SQLite identity authority."""

from dataclasses import dataclass
from pathlib import Path

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.identity_authority import SQLiteIdentityAuthority
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.core.errors import ContractError


@dataclass(frozen=True, slots=True)
class SQLiteIdentityComposition:
    """Identity authority and database bound to one exact SQLite instance."""

    database: SQLiteDatabase
    authority: SQLiteIdentityAuthority

    def __post_init__(self) -> None:
        if not isinstance(self.database, SQLiteDatabase):
            raise ContractError("database debe ser SQLiteDatabase")
        if not isinstance(self.authority, SQLiteIdentityAuthority):
            raise ContractError("authority debe ser SQLiteIdentityAuthority")
        if self.authority._database is not self.database:
            raise ContractError(
                "authority y composition deben usar la misma instancia SQLite"
            )


def compose_sqlite_identity_on_database(
    database: SQLiteDatabase,
) -> SQLiteIdentityComposition:
    """Compose Identity on an existing database owned by a higher-level root.

    This is the supported seam for a future shared local authority composition.
    It never creates or substitutes a database instance. Schema migration errors
    propagate before the authority is exposed.
    """
    if not isinstance(database, SQLiteDatabase):
        raise ContractError("database debe ser SQLiteDatabase")
    database.apply_migrations(SQLITE_MIGRATIONS)
    authority = SQLiteIdentityAuthority(database)
    return SQLiteIdentityComposition(database=database, authority=authority)


def compose_sqlite_identity(
    path: str | Path,
    *,
    busy_timeout_ms: int = 5000,
) -> SQLiteIdentityComposition:
    """Initialize a dedicated Identity database for standalone callers.

    The parent directory must already exist, as required by SQLiteDatabase.
    Shared application compositions should use
    compose_sqlite_identity_on_database instead.
    """
    database = SQLiteDatabase(path, busy_timeout_ms=busy_timeout_ms)
    return compose_sqlite_identity_on_database(database)
