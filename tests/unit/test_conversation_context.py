"""Pruebas del contexto conversacional acotado por sesión."""

from datetime import datetime, timezone
import unittest

from atlas.application.conversation import (
    ConversationContextProcessor,
    InMemoryConversationHistory,
)
from atlas.assistant.models import (
    AssistantRequest,
    AssistantResponse,
    AssistantResponseKind,
    ConversationMessageRole,
)
from atlas.core.errors import ContractError
from tests.fixtures.contexts import user_context


NOW = datetime(2026, 11, 14, 18, 0, tzinfo=timezone.utc)


def make_request(content, conversation_id="conversation-a"):
    context = user_context()
    return AssistantRequest(
        request_id=context.request_id,
        context=context,
        content=content,
        received_at=NOW,
        conversation_id=conversation_id,
    )


class FakeAssistant:
    def __init__(self):
        self.requests = []
        self.next_kind = AssistantResponseKind.INFORMATIONAL

    def _respond(self, request):
        self.requests.append(request)
        return AssistantResponse(
            request_id=request.request_id,
            context=request.context,
            kind=self.next_kind,
            content=f"respuesta a {request.content}",
            created_at=NOW,
        )

    def respond(self, request):
        return self._respond(request)

    def respond_streaming(self, request, on_token):
        response = self._respond(request)
        on_token(response.content)
        return response


class ConversationContextTests(unittest.TestCase):
    def setUp(self):
        self.assistant = FakeAssistant()
        self.history = InMemoryConversationHistory(max_turns=8)
        self.processor = ConversationContextProcessor(
            self.assistant,
            self.history,
        )

    def test_previous_turn_is_added_to_next_request(self):
        self.processor.respond(make_request("Mi nombre es Ana"))
        self.processor.respond(make_request("¿Cómo me llamo?"))

        second_request = self.assistant.requests[1]
        self.assertEqual(
            [message.role for message in second_request.history],
            [
                ConversationMessageRole.USER,
                ConversationMessageRole.ASSISTANT,
            ],
        )
        self.assertEqual(
            [message.content for message in second_request.history],
            ["Mi nombre es Ana", "respuesta a Mi nombre es Ana"],
        )

    def test_histories_are_isolated_between_conversations(self):
        self.processor.respond(make_request("dato privado", "conversation-a"))
        self.processor.respond(make_request("hola", "conversation-b"))

        second_request = self.assistant.requests[1]
        self.assertEqual(second_request.history, ())
        self.assertEqual(
            len(self.history.get_history("conversation-a")),
            2,
        )
        self.assertEqual(
            self.history.get_history("conversation-b")[0].content,
            "hola",
        )

    def test_history_is_limited_to_configured_number_of_turns(self):
        history = InMemoryConversationHistory(max_turns=2)
        processor = ConversationContextProcessor(self.assistant, history)

        for content in ("uno", "dos", "tres"):
            processor.respond(make_request(content))

        retained = history.get_history("conversation-a")
        self.assertEqual(len(retained), 4)
        self.assertEqual(
            [message.content for message in retained],
            [
                "dos",
                "respuesta a dos",
                "tres",
                "respuesta a tres",
            ],
        )

    def test_historical_messages_are_truncated_to_character_limit(self):
        history = InMemoryConversationHistory(
            max_turns=1,
            max_message_chars=40,
        )
        history.append_turn(
            "conversation-a",
            "u" * 100,
            "a" * 100,
        )

        messages = history.get_history("conversation-a")
        self.assertEqual(len(messages), 2)
        self.assertTrue(all(len(message.content) <= 40 for message in messages))
        self.assertTrue(all("contenido histórico truncado" in message.content for message in messages))

    def test_error_response_is_not_saved_in_history(self):
        self.assistant.next_kind = AssistantResponseKind.ERROR
        self.processor.respond(make_request("fallo"))
        self.assertEqual(self.history.get_history("conversation-a"), ())

        self.assistant.next_kind = AssistantResponseKind.INFORMATIONAL
        self.processor.respond(make_request("reintento"))
        self.assertEqual(
            [message.content for message in self.history.get_history("conversation-a")],
            ["reintento", "respuesta a reintento"],
        )

    def test_streaming_turn_is_saved_after_success(self):
        emitted = []
        response = self.processor.respond_streaming(
            make_request("mensaje progresivo"),
            emitted.append,
        )

        self.assertEqual(emitted, [response.content])
        self.assertEqual(
            [message.content for message in self.history.get_history("conversation-a")],
            ["mensaje progresivo", response.content],
        )

    def test_request_without_conversation_id_is_rejected(self):
        with self.assertRaises(ContractError):
            self.processor.respond(make_request("sin sesión", None))

    def test_invalid_history_limits_and_dependencies_are_rejected(self):
        for invalid_limit in (0, -1, True, 1.5):
            with self.subTest(invalid_limit=invalid_limit):
                with self.assertRaises(ContractError):
                    InMemoryConversationHistory(max_turns=invalid_limit)

        for invalid_limit in (0, -1, True, 1.5, 10):
            with self.subTest(max_message_chars=invalid_limit):
                with self.assertRaises(ContractError):
                    InMemoryConversationHistory(max_message_chars=invalid_limit)

        with self.assertRaises(ContractError):
            ConversationContextProcessor(object(), self.history)
        with self.assertRaises(ContractError):
            ConversationContextProcessor(self.assistant, object())

    def test_response_with_wrong_correlation_is_not_saved(self):
        class InvalidAssistant(FakeAssistant):
            def respond(self, request):
                response = super().respond(request)
                return AssistantResponse(
                    request_id="wrong-request",
                    context=request.context,
                    kind=response.kind,
                    content=response.content,
                    created_at=NOW,
                )

        processor = ConversationContextProcessor(
            InvalidAssistant(),
            self.history,
        )
        with self.assertRaises(ContractError):
            processor.respond(make_request("no guardar"))
        self.assertEqual(self.history.get_history("conversation-a"), ())


if __name__ == "__main__":
    unittest.main()
