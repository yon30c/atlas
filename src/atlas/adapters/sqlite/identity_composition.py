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


def compose_sqlite_identity(
    path: str | Path,
    *,
    busy_timeout_ms: int = 5000,
) -> SQLiteIdentityComposition:
    """Initialize the complete schema before exposing the identity authority.

    The parent directory must already exist, as required by SQLiteDatabase.
    Migration errors propagate and no partially initialized composition is
    returned to the caller.
    """
    database = SQLiteDatabase(path, busy_timeout_ms=busy_timeout_ms)
    database.apply_migrations(SQLITE_MIGRATIONS)
    authority = SQLiteIdentityAuthority(database)
    return SQLiteIdentityComposition(database=database, authority=authority)
