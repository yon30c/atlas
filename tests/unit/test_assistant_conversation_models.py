from datetime import datetime, timezone, timedelta
import unittest

from atlas.assistant import (
    AssistantRequest,
    AssistantResponse,
    AssistantResponseKind,
)
from atlas.core.errors import ContractError
from tests.fixtures.contexts import user_context


class AssistantConversationModelTests(unittest.TestCase):
    def setUp(self):
        self.context = user_context()
        self.now = datetime.now(timezone.utc)

    def test_request_preserves_context_and_optional_conversation_data(self):
        request = AssistantRequest(
            request_id=self.context.request_id,
            context=self.context,
            content="Hola, Atlas",
            received_at=self.now,
            conversation_id="conversation-1",
            attachments=("file-ref-1",),
        )

        self.assertEqual(request.context, self.context)
        self.assertEqual(request.conversation_id, "conversation-1")
        self.assertEqual(request.attachments, ("file-ref-1",))

    def test_request_rejects_context_with_different_request_id(self):
        with self.assertRaises(ContractError):
            AssistantRequest(
                request_id="another-request",
                context=self.context,
                content="Hola",
                received_at=self.now,
            )

    def test_request_rejects_naive_timestamp_and_invalid_attachments(self):
        with self.assertRaises(ContractError):
            AssistantRequest(
                request_id=self.context.request_id,
                context=self.context,
                content="Hola",
                received_at=datetime(2026, 1, 1),
            )

        with self.assertRaises(ContractError):
            AssistantRequest(
                request_id=self.context.request_id,
                context=self.context,
                content="Hola",
                received_at=self.now,
                attachments=("valid-ref", " "),
            )

    def test_request_rejects_non_utc_offset(self):
        with self.assertRaises(ContractError):
            AssistantRequest(
                request_id=self.context.request_id,
                context=self.context,
                content="Hola",
                received_at=datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=2))),
            )

    def test_response_preserves_request_context_and_kind(self):
        response = AssistantResponse(
            request_id=self.context.request_id,
            context=self.context,
            kind=AssistantResponseKind.INFORMATIONAL,
            content="Hola. ¿En qué puedo ayudarte?",
            created_at=self.now,
        )

        self.assertEqual(response.request_id, self.context.request_id)
        self.assertIs(response.kind, AssistantResponseKind.INFORMATIONAL)

    def test_response_rejects_mismatched_request_and_invalid_kind(self):
        with self.assertRaises(ContractError):
            AssistantResponse(
                request_id="another-request",
                context=self.context,
                kind=AssistantResponseKind.RESULT,
                content="Completado",
                created_at=self.now,
            )

        with self.assertRaises(ContractError):
            AssistantResponse(
                request_id=self.context.request_id,
                context=self.context,
                kind="result",
                content="Completado",
                created_at=self.now,
            )


if __name__ == "__main__":
    unittest.main()
