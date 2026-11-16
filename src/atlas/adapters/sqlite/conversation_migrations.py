"""Independent schema history for durable conversations."""

from atlas.adapters.sqlite.database import SQLiteMigration


CONVERSATION_SCHEMA_V1 = SQLiteMigration(
    version=1,
    name="conversation_history",
    sql="""
    CREATE TABLE conversations (
        conversation_id TEXT PRIMARY KEY CHECK (length(trim(conversation_id)) > 0),
        title TEXT NOT NULL CHECK (length(trim(title)) > 0),
        status TEXT NOT NULL CHECK (status IN ('active', 'closed')),
        created_at TEXT NOT NULL CHECK (length(trim(created_at)) > 0),
        updated_at TEXT NOT NULL CHECK (length(trim(updated_at)) > 0),
        last_message_at TEXT,
        CHECK (last_message_at IS NULL OR last_message_at >= created_at),
        CHECK (updated_at >= created_at),
        CHECK (last_message_at IS NULL OR last_message_at <= updated_at)
    );

    CREATE TABLE conversation_messages (
        message_id TEXT PRIMARY KEY CHECK (length(trim(message_id)) > 0),
        conversation_id TEXT NOT NULL,
        sequence INTEGER NOT NULL CHECK (sequence > 0),
        role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
        content TEXT NOT NULL CHECK (length(trim(content)) > 0),
        created_at TEXT NOT NULL CHECK (length(trim(created_at)) > 0),
        UNIQUE (conversation_id, sequence),
        FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE TABLE conversation_state (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        active_conversation_id TEXT,
        FOREIGN KEY (active_conversation_id) REFERENCES conversations(conversation_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    );

    CREATE INDEX conversations_status_updated
        ON conversations(status, updated_at DESC, conversation_id);

    CREATE INDEX conversation_messages_order
        ON conversation_messages(conversation_id, sequence);
    """,
)


CONVERSATION_MIGRATIONS = (CONVERSATION_SCHEMA_V1,)
