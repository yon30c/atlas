"""Pruebas de los modelos de dominio de conversación."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import unittest

from atlas.assistant.conversation import Conversation, ConversationStatus
from atlas.core.errors import ContractError


NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def make_conversation(**overrides):
    values = {
        "conversation_id": "conversation-1",
        "title": "Nueva conversación",
        "status": ConversationStatus.ACTIVE,
        "created_at": NOW,
        "updated_at": NOW,
        "last_message_at": None,
    }
    values.update(overrides)
    return Conversation(**values)


class ConversationDomainTests(unittest.TestCase):

    def test_valid_conversation_can_be_created(self):
        conversation = make_conversation()
        self.assertEqual(conversation.conversation_id, "conversation-1")
        self.assertEqual(conversation.status, ConversationStatus.ACTIVE)
        self.assertIsNone(conversation.last_message_at)

    def test_closed_conversation_is_valid(self):
        conversation = make_conversation(status=ConversationStatus.CLOSED)
        self.assertEqual(conversation.status, ConversationStatus.CLOSED)

    def test_last_message_timestamp_is_valid(self):
        message_at = NOW + timedelta(minutes=2)
        conversation = make_conversation(
            updated_at=message_at,
            last_message_at=message_at,
        )
        self.assertEqual(conversation.last_message_at, message_at)

    def test_required_text_fields_are_validated(self):
        for field in ("conversation_id", "title"):
            for invalid in ("", "   ", None, 123):
                with self.subTest(field=field, value=invalid):
                    with self.assertRaises(ContractError):
                        make_conversation(**{field: invalid})

    def test_status_must_be_conversation_status(self):
        with self.assertRaises(ContractError):
            make_conversation(status="active")

    def test_timestamps_must_be_utc(self):
        non_utc = datetime(
            2026, 11, 16, 8, 0, tzinfo=timezone(timedelta(hours=-4))
        )
        with self.assertRaises(ContractError):
            make_conversation(created_at=non_utc)
        with self.assertRaises(ContractError):
            make_conversation(updated_at=non_utc)
        with self.assertRaises(ContractError):
            make_conversation(last_message_at=non_utc)

    def test_updated_at_cannot_precede_created_at(self):
        with self.assertRaises(ContractError):
            make_conversation(updated_at=NOW - timedelta(seconds=1))

    def test_last_message_cannot_precede_creation(self):
        with self.assertRaises(ContractError):
            make_conversation(last_message_at=NOW - timedelta(seconds=1))

    def test_last_message_cannot_follow_update(self):
        with self.assertRaises(ContractError):
            make_conversation(last_message_at=NOW + timedelta(seconds=1))

    def test_conversation_is_immutable(self):
        conversation = make_conversation()
        with self.assertRaises(FrozenInstanceError):
            conversation.title = "Otro título"


if __name__ == "__main__":
    unittest.main()
