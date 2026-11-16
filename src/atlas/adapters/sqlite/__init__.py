"""SQLite infrastructure for the single-server local profile."""

from atlas.adapters.sqlite.database import SQLiteDatabase, SQLiteMigration, SQLiteUnitOfWork
from atlas.adapters.sqlite.authority_changes import SQLiteAuthorityChangeStore
from atlas.adapters.sqlite.grant_repository import SQLiteGrantRepository
from atlas.adapters.sqlite.grant_renewal_repository import SQLiteGrantRenewalRepository
from atlas.adapters.sqlite.authorization_unit_of_work import (
    SQLiteAuthorizationUnitOfWork,
    SQLiteAuthorizationUnitOfWorkFactory,
)
from atlas.adapters.sqlite.conversation_backup import ConversationBackup
from atlas.adapters.sqlite.conversation_export import ConversationExport
from atlas.adapters.sqlite.conversation_migrations import CONVERSATION_MIGRATIONS, CONVERSATION_SCHEMA_V1
from atlas.adapters.sqlite.conversation_repository import SQLiteConversationRepository
from atlas.adapters.sqlite.conversation_storage import prepare_conversation_database_path
from atlas.adapters.sqlite.recovery_gate import LocalSQLiteRecoveryGateAdapter
from atlas.adapters.sqlite.migrations import (
    SQLITE_MIGRATIONS, CORE_SCHEMA_V1, CORE_SCHEMA_V2, CORE_SCHEMA_V3,
    CORE_SCHEMA_V4, CORE_SCHEMA_V5, CORE_SCHEMA_V6, CORE_SCHEMA_V7, CORE_SCHEMA_V8,
)

__all__ = [
    "SQLiteDatabase", "SQLiteMigration", "SQLiteUnitOfWork",
    "SQLiteAuthorityChangeStore", "SQLiteGrantRepository", "SQLiteGrantRenewalRepository",
    "SQLiteAuthorizationUnitOfWork", "SQLiteAuthorizationUnitOfWorkFactory",
    "SQLiteConversationRepository",
    "ConversationBackup", "ConversationExport", "prepare_conversation_database_path",
    "LocalSQLiteRecoveryGateAdapter", "SQLITE_MIGRATIONS",
    "CORE_SCHEMA_V1", "CORE_SCHEMA_V2", "CORE_SCHEMA_V3",
    "CORE_SCHEMA_V4", "CORE_SCHEMA_V5", "CORE_SCHEMA_V6", "CORE_SCHEMA_V7", "CORE_SCHEMA_V8",
    "CONVERSATION_MIGRATIONS", "CONVERSATION_SCHEMA_V1",
]
