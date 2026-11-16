"""SQLite adapter for durable conversation metadata and full history."""

from datetime import datetime, timezone
import sqlite3
from uuid import uuid4

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.conversation_migrations import CONVERSATION_MIGRATIONS
from atlas.application.conversation import ConversationHistoryStore, ConversationRepository
from atlas.assistant.conversation import Conversation, ConversationStatus
from atlas.assistant.models import ConversationMessage, ConversationMessageRole
from atlas.core.errors import ContractError, NotFoundError


def _utc_text(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ContractError("datetime debe estar en UTC")
    return value.isoformat(timespec="microseconds")


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ContractError("timestamp SQLite no está en UTC")
    return parsed


def _require_content(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacía")


class SQLiteConversationRepository(ConversationRepository, ConversationHistoryStore):
    """Persistencia independiente: metadatos y el historial íntegro."""

    def __init__(self, database: SQLiteDatabase) -> None:
        if not isinstance(database, SQLiteDatabase):
            raise ContractError("database debe ser SQLiteDatabase")
        self._database = database

    def initialize(self) -> None:
        self._database.apply_migrations(CONVERSATION_MIGRATIONS)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Conversation:
        return Conversation(
            conversation_id=row["conversation_id"], title=row["title"],
            status=ConversationStatus(row["status"]),
            created_at=_parse_utc(row["created_at"]),
            updated_at=_parse_utc(row["updated_at"]),
            last_message_at=None if row["last_message_at"] is None else _parse_utc(row["last_message_at"]),
        )

    @staticmethod
    def _get(connection: sqlite3.Connection, conversation_id: str):
        return connection.execute("SELECT * FROM conversations WHERE conversation_id = ?", (conversation_id,)).fetchone()

    def create(self, conversation: Conversation) -> Conversation:
        if not isinstance(conversation, Conversation):
            raise ContractError("conversation debe ser Conversation")
        try:
            with self._database.unit_of_work() as unit:
                connection = unit._connection_for(self._database)
                connection.execute(
                    """INSERT INTO conversations (
                        conversation_id, title, status, created_at, updated_at, last_message_at
                    ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (conversation.conversation_id, conversation.title, conversation.status.value,
                     _utc_text(conversation.created_at), _utc_text(conversation.updated_at),
                     None if conversation.last_message_at is None else _utc_text(conversation.last_message_at)),
                )
        except sqlite3.IntegrityError as exc:
            raise ContractError("conversation_id ya existe o viola el esquema") from exc
        return conversation

    def get(self, conversation_id: str) -> Conversation | None:
        _require_content(conversation_id, "conversation_id")
        with self._database.connection() as connection:
            row = self._get(connection, conversation_id)
            return None if row is None else self._from_row(row)

    def list_conversations(self, *, include_closed: bool = False) -> tuple[Conversation, ...]:
        if not isinstance(include_closed, bool):
            raise ContractError("include_closed debe ser booleano")
        query = "SELECT * FROM conversations"
        if not include_closed:
            query += " WHERE status = 'active'"
        query += " ORDER BY updated_at DESC, conversation_id"
        with self._database.connection() as connection:
            return tuple(self._from_row(row) for row in connection.execute(query))

    def rename(self, conversation_id: str, title: str, updated_at: datetime) -> Conversation:
        _require_content(conversation_id, "conversation_id")
        _require_content(title, "title")
        timestamp = _utc_text(updated_at)
        with self._database.unit_of_work() as unit:
            connection = unit._connection_for(self._database)
            row = self._get(connection, conversation_id)
            if row is None:
                raise NotFoundError("conversación no encontrada")
            if updated_at < _parse_utc(row["updated_at"]):
                raise ContractError("updated_at no puede retroceder")
            connection.execute("UPDATE conversations SET title = ?, updated_at = ? WHERE conversation_id = ?", (title, timestamp, conversation_id))
            return self._from_row(self._get(connection, conversation_id))

    def close(self, conversation_id: str, updated_at: datetime) -> Conversation:
        _require_content(conversation_id, "conversation_id")
        timestamp = _utc_text(updated_at)
        with self._database.unit_of_work() as unit:
            connection = unit._connection_for(self._database)
            row = self._get(connection, conversation_id)
            if row is None:
                raise NotFoundError("conversación no encontrada")
            if updated_at < _parse_utc(row["updated_at"]):
                raise ContractError("updated_at no puede retroceder")
            connection.execute("UPDATE conversations SET status = 'closed', updated_at = ? WHERE conversation_id = ?", (timestamp, conversation_id))
            connection.execute("UPDATE conversation_state SET active_conversation_id = NULL WHERE singleton = 1 AND active_conversation_id = ?", (conversation_id,))
            return self._from_row(self._get(connection, conversation_id))

    def delete(self, conversation_id: str) -> None:
        _require_content(conversation_id, "conversation_id")
        with self._database.unit_of_work() as unit:
            connection = unit._connection_for(self._database)
            if self._get(connection, conversation_id) is None:
                raise NotFoundError("conversación no encontrada")
            connection.execute("UPDATE conversation_state SET active_conversation_id = NULL WHERE singleton = 1 AND active_conversation_id = ?", (conversation_id,))
            connection.execute("DELETE FROM conversation_messages WHERE conversation_id = ?", (conversation_id,))
            connection.execute("DELETE FROM conversations WHERE conversation_id = ?", (conversation_id,))

    def get_active_conversation(self) -> Conversation | None:
        with self._database.connection() as connection:
            row = connection.execute(
                """SELECT c.* FROM conversation_state AS s
                JOIN conversations AS c ON c.conversation_id = s.active_conversation_id
                WHERE s.singleton = 1 AND c.status = 'active'"""
            ).fetchone()
            return None if row is None else self._from_row(row)

    def set_active_conversation(self, conversation_id: str) -> None:
        _require_content(conversation_id, "conversation_id")
        with self._database.unit_of_work() as unit:
            connection = unit._connection_for(self._database)
            row = self._get(connection, conversation_id)
            if row is None or row["status"] != ConversationStatus.ACTIVE.value:
                raise NotFoundError("conversación activa no encontrada")
            connection.execute(
                """INSERT INTO conversation_state(singleton, active_conversation_id) VALUES (1, ?)
                ON CONFLICT(singleton) DO UPDATE SET active_conversation_id = excluded.active_conversation_id""",
                (conversation_id,),
            )

    def get_history(self, conversation_id: str) -> tuple[ConversationMessage, ...]:
        _require_content(conversation_id, "conversation_id")
        with self._database.connection() as connection:
            rows = connection.execute(
                "SELECT role, content FROM conversation_messages WHERE conversation_id = ? ORDER BY sequence",
                (conversation_id,),
            ).fetchall()
            return tuple(ConversationMessage(ConversationMessageRole(row["role"]), row["content"]) for row in rows)

    def append_turn(self, conversation_id: str, user_content: str, assistant_content: str) -> None:
        _require_content(conversation_id, "conversation_id")
        _require_content(user_content, "user_content")
        _require_content(assistant_content, "assistant_content")
        now = datetime.now(timezone.utc)
        timestamp = _utc_text(now)
        with self._database.unit_of_work() as unit:
            connection = unit._connection_for(self._database)
            row = self._get(connection, conversation_id)
            if row is None or row["status"] != ConversationStatus.ACTIVE.value:
                raise NotFoundError("conversación activa no encontrada")
            sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM conversation_messages WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()[0]
            for offset, (role, content) in enumerate((
                (ConversationMessageRole.USER.value, user_content),
                (ConversationMessageRole.ASSISTANT.value, assistant_content),
            )):
                connection.execute(
                    """INSERT INTO conversation_messages (
                        message_id, conversation_id, sequence, role, content, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (str(uuid4()), conversation_id, sequence + offset, role, content, timestamp),
                )
            connection.execute(
                "UPDATE conversations SET updated_at = ?, last_message_at = ? WHERE conversation_id = ?",
                (timestamp, timestamp, conversation_id),
            )
