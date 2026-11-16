"""SQLite infrastructure for the single-server local profile."""

from atlas.adapters.sqlite.database import SQLiteDatabase, SQLiteMigration, SQLiteUnitOfWork
from atlas.adapters.sqlite.authority_changes import SQLiteAuthorityChangeStore
from atlas.adapters.sqlite.conversation_migrations import (
    CONVERSATION_MIGRATIONS, CONVERSATION_SCHEMA_V1,
)
from atlas.adapters.sqlite.conversation_repository import SQLiteConversationRepository
from atlas.adapters.sqlite.recovery_gate import LocalSQLiteRecoveryGateAdapter
from atlas.adapters.sqlite.migrations import (
    SQLITE_MIGRATIONS, CORE_SCHEMA_V1, CORE_SCHEMA_V2, CORE_SCHEMA_V3,
    CORE_SCHEMA_V4, CORE_SCHEMA_V5, CORE_SCHEMA_V6,
)

__all__ = [
    "SQLiteDatabase",
    "SQLiteMigration",
    "SQLiteUnitOfWork",
    "SQLiteAuthorityChangeStore",
    "SQLiteConversationRepository",
    "LocalSQLiteRecoveryGateAdapter",
    "SQLITE_MIGRATIONS",
    "CORE_SCHEMA_V1",
    "CORE_SCHEMA_V2",
    "CORE_SCHEMA_V3",
    "CORE_SCHEMA_V4",
    "CORE_SCHEMA_V5",
    "CORE_SCHEMA_V6",
    "CONVERSATION_MIGRATIONS",
    "CONVERSATION_SCHEMA_V1",
]
