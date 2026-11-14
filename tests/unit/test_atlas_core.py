"""Pruebas del orquestador AtlasCore."""

from datetime import datetime, timezone
import unittest

from atlas.application import AtlasCore
from atlas.assistant.models import (
    AssistantRequest,
    AssistantResponse,
    AssistantResponseKind,
)
from atlas.core.errors import ContractError
from tests.fixtures.contexts import user_context


NOW = datetime(2026, 11, 14, 18, 0, tzinfo=timezone.utc)


class FakeRequestFactory:
    def __init__(self):
        self.contents = []

    def create(self, content):
        self.contents.append(content)
        context = user_context()
        return AssistantRequest(
            request_id=context.request_id,
            context=context,
            content=content,
            received_at=NOW,
        )


class FakeAssistant:
    def __init__(self):
        self.requests = []

    def respond(self, request):
        self.requests.append(request)
        return AssistantResponse(
            request_id=request.request_id,
            context=request.context,
            kind=AssistantResponseKind.INFORMATIONAL,
            content="respuesta completa",
            created_at=NOW,
        )

    def respond_streaming(self, request, on_token):
        self.requests.append(request)
        on_token("respuesta ")
        on_token("progresiva")
        return AssistantResponse(
            request_id=request.request_id,
            context=request.context,
            kind=AssistantResponseKind.INFORMATIONAL,
            content="respuesta progresiva",
            created_at=NOW,
        )


class InvalidAssistant:
    def respond(self, request):
        return "no es una respuesta"

    def respond_streaming(self, request, on_token):
        return "no es una respuesta"


class AtlasCoreTests(unittest.TestCase):
    def setUp(self):
        self.factory = FakeRequestFactory()
        self.assistant = FakeAssistant()
        self.core = AtlasCore(self.factory, self.assistant)

    def test_respond_builds_request_and_returns_correlated_response(self):
        response = self.core.respond("Hola Atlas")

        self.assertEqual(self.factory.contents, ["Hola Atlas"])
        self.assertEqual(len(self.assistant.requests), 1)
        request = self.assistant.requests[0]
        self.assertEqual(request.content, "Hola Atlas")
        self.assertEqual(response.request_id, request.request_id)
        self.assertEqual(response.context, request.context)
        self.assertEqual(response.content, "respuesta completa")

    def test_streaming_forwards_tokens_and_returns_final_response(self):
        tokens = []

        response = self.core.respond_streaming("Hola Atlas", tokens.append)

        self.assertEqual(tokens, ["respuesta ", "progresiva"])
        self.assertEqual(response.content, "respuesta progresiva")
        self.assertEqual(response.request_id, self.assistant.requests[0].request_id)

    def test_rejects_empty_content_before_creating_request(self):
        with self.assertRaises(ContractError):
            self.core.respond("  ")

        self.assertEqual(self.factory.contents, [])

    def test_rejects_factory_that_returns_invalid_request(self):
        class InvalidFactory:
            def create(self, content):
                return object()

        core = AtlasCore(InvalidFactory(), self.assistant)
        with self.assertRaises(ContractError):
            core.respond("Hola")

    def test_rejects_assistant_that_returns_invalid_response(self):
        core = AtlasCore(self.factory, InvalidAssistant())
        with self.assertRaises(ContractError):
            core.respond("Hola")

    def test_rejects_missing_dependencies_and_invalid_callback(self):
        with self.assertRaises(ContractError):
            AtlasCore(object(), self.assistant)
        with self.assertRaises(ContractError):
            AtlasCore(self.factory, object())
        with self.assertRaises(ContractError):
            self.core.respond_streaming("Hola", None)


if __name__ == "__main__":
    unittest.main()
