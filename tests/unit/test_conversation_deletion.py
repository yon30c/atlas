"""Pruebas específicas del borrado transaccional de conversaciones."""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from atlas.adapters.sqlite.conversation_repository import SQLiteConversationRepository
from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.application.conversation_manager import ConversationManager
from atlas.core.errors import NotFoundError


NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


class FixedClock:
    def now(self):
        return NOW


class ConversationDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "conversations.sqlite3"
        self.database = SQLiteDatabase(database_path)
        self.repository = SQLiteConversationRepository(self.database)
        self.repository.initialize()
        self.manager = ConversationManager(self.repository, FixedClock())

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_repository_delete_removes_conversation_messages_and_active_reference(self):
        conversation = self.manager.create()
        self.repository.append_turn(
            conversation.conversation_id,
            "mensaje del usuario",
            "respuesta del asistente",
        )

        self.repository.delete(conversation.conversation_id)

        self.assertIsNone(self.repository.get(conversation.conversation_id))
        self.assertEqual(self.repository.get_history(conversation.conversation_id), ())
        self.assertIsNone(self.repository.get_active_conversation())
        with self.database.connection() as connection:
            state = connection.execute(
                "SELECT active_conversation_id FROM conversation_state WHERE singleton = 1"
            ).fetchone()
        self.assertIsNone(state["active_conversation_id"])

    def test_repository_delete_of_unknown_conversation_preserves_existing_data(self):
        conversation = self.manager.create()
        self.repository.append_turn(
            conversation.conversation_id,
            "mensaje conservado",
            "respuesta conservada",
        )

        persisted = self.repository.get(conversation.conversation_id)

        with self.assertRaises(NotFoundError):
            self.repository.delete("conversation-does-not-exist")

        self.assertEqual(
            self.repository.get(conversation.conversation_id),
            persisted,
        )
        self.assertEqual(
            [message.content for message in self.repository.get_history(conversation.conversation_id)],
            ["mensaje conservado", "respuesta conservada"],
        )
        self.assertEqual(
            self.repository.get_active_conversation().conversation_id,
            conversation.conversation_id,
        )

    def test_repository_delete_rolls_back_when_conversation_row_cannot_be_deleted(self):
        conversation = self.manager.create()
        self.repository.append_turn(
            conversation.conversation_id,
            "mensaje que debe sobrevivir al rollback",
            "respuesta que debe sobrevivir al rollback",
        )
        with self.database.connection() as connection:
            connection.execute(
                """
                CREATE TRIGGER reject_conversation_delete
                BEFORE DELETE ON conversations
                BEGIN
                    SELECT RAISE(ABORT, 'injected conversation delete failure');
                END
                """
            )

        persisted = self.repository.get(conversation.conversation_id)

        with self.assertRaisesRegex(sqlite3.IntegrityError, "injected conversation delete failure"):
            self.repository.delete(conversation.conversation_id)

        self.assertEqual(
            self.repository.get(conversation.conversation_id),
            persisted,
        )
        self.assertEqual(
            [message.content for message in self.repository.get_history(conversation.conversation_id)],
            [
                "mensaje que debe sobrevivir al rollback",
                "respuesta que debe sobrevivir al rollback",
            ],
        )
        self.assertEqual(
            self.repository.get_active_conversation().conversation_id,
            conversation.conversation_id,
        )

    def test_manager_delete_of_active_conversation_creates_replacement(self):
        first = self.manager.create("Primera")
        self.repository.append_turn(first.conversation_id, "privado", "respuesta privada")
        remaining = self.manager.create("Segunda")
        self.manager.select(first.conversation_id)

        self.manager.delete(first.conversation_id)

        active = self.manager.active()
        self.assertIsNotNone(active)
        self.assertNotEqual(active.conversation_id, first.conversation_id)
        self.assertNotEqual(active.conversation_id, remaining.conversation_id)
        self.assertIsNone(self.repository.get(first.conversation_id))
        self.assertEqual(self.repository.get_history(first.conversation_id), ())
        self.assertIsNotNone(self.repository.get(remaining.conversation_id))
        self.assertEqual(
            {item.conversation_id for item in self.manager.list()},
            {remaining.conversation_id, active.conversation_id},
        )

    def test_manager_delete_of_inactive_conversation_preserves_active_conversation(self):
        removed = self.manager.create("Eliminar")
        active = self.manager.create("Conservar")

        self.manager.delete(removed.conversation_id)

        self.assertIsNone(self.repository.get(removed.conversation_id))
        self.assertEqual(
            self.manager.active().conversation_id,
            active.conversation_id,
        )
        self.assertEqual(
            [item.conversation_id for item in self.manager.list()],
            [active.conversation_id],
        )

    def test_manager_delete_of_unknown_conversation_preserves_active_conversation(self):
        active = self.manager.create("Conservar")

        with self.assertRaises(NotFoundError):
            self.manager.delete("conversation-does-not-exist")

        self.assertEqual(
            self.manager.active().conversation_id,
            active.conversation_id,
        )
        self.assertEqual(
            [item.conversation_id for item in self.manager.list()],
            [active.conversation_id],
        )


if __name__ == "__main__":
    unittest.main()
