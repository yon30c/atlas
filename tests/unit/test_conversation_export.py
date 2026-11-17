"""Pruebas unitarias de exportación portable de conversaciones."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone

from atlas.adapters.sqlite.conversation_export import ConversationExport
from atlas.assistant.conversation import Conversation, ConversationStatus
from atlas.assistant.models import ConversationMessage, ConversationMessageRole
from atlas.core.errors import ContractError, NotFoundError


NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


class FakeRepository:
    def __init__(self):
        self.conversation = Conversation(
            conversation_id="conversation-1",
            title="Proyecto privado",
            status=ConversationStatus.CLOSED,
            created_at=NOW,
            updated_at=NOW,
        )
        self.messages = (
            ConversationMessage(ConversationMessageRole.USER, "Hola"),
            ConversationMessage(ConversationMessageRole.ASSISTANT, "Respuesta"),
        )

    def get(self, conversation_id):
        return self.conversation if conversation_id == self.conversation.conversation_id else None

    def get_history(self, conversation_id):
        return self.messages


class ConversationExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.exporter = ConversationExport(FakeRepository())

    def tearDown(self):
        self.temp.cleanup()

    def test_exports_metadata_and_full_history_as_versioned_json(self):
        destination = self.directory / "conversation.json"
        result = self.exporter.export("conversation-1", destination)

        self.assertEqual(result, destination)
        payload = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(payload["format"], "atlas-conversation-export")
        self.assertEqual(payload["format_version"], 1)
        self.assertEqual(payload["conversation"]["status"], "closed")
        self.assertEqual(
            payload["messages"],
            [
                {"role": "user", "content": "Hola"},
                {"role": "assistant", "content": "Respuesta"},
            ],
        )

    @unittest.skipUnless(os.name == "posix", "permisos POSIX")
    def test_export_file_is_private(self):
        destination = self.directory / "private.json"
        self.exporter.export("conversation-1", destination)
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)

    def test_existing_destination_is_never_overwritten(self):
        destination = self.directory / "existing.json"
        destination.write_text("preserve", encoding="utf-8")
        with self.assertRaises(ContractError):
            self.exporter.export("conversation-1", destination)
        self.assertEqual(destination.read_text(encoding="utf-8"), "preserve")

    def test_unknown_conversation_is_rejected(self):
        with self.assertRaises(NotFoundError):
            self.exporter.export("missing", self.directory / "missing.json")

    def test_relative_destination_is_rejected(self):
        with self.assertRaises(ContractError):
            self.exporter.export("conversation-1", "relative.json")


if __name__ == "__main__":
    unittest.main()
