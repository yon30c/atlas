"""Pruebas del puente conversacional con el proveedor Ollama."""

from dataclasses import replace
from datetime import datetime, timezone
import unittest

from atlas.adapters.ollama import OllamaResponseError, OllamaUnavailableError
from atlas.adapters.ollama_assistant import (
    ATLAS_SYSTEM_PROMPT,
    OllamaResponseGenerator,
)
from atlas.assistant.models import (
    AssistantRequest,
    AssistantResponseKind,
    ConversationMessage,
    ConversationMessageRole,
)
from atlas.assistant.service import AssistantService
from atlas.core.errors import ContractError
from atlas.ports.llm import LLMMessageRole, LLMRequest, LLMResponse
from tests.fixtures.contexts import user_context


class FixedClock:
    def __init__(self, value):
        self.value = value

    def now(self):
        return self.value


class FakeProvider:
    def __init__(self, response=None, error=None):
        self.response = response or LLMResponse(
            provider="ollama",
            model="gemma4:e2b",
            content="Hola. ¿En qué te ayudo?",
        )
        self.error = error
        self.received_request = None

    def generate(self, request):
        self.received_request = request
        if self.error is not None:
            raise self.error
        return self.response


class OllamaResponseGeneratorTests(unittest.TestCase):
    def setUp(self):
        context = user_context()
        now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
        self.request = AssistantRequest(
            request_id=context.request_id,
            context=context,
            content="Hola, Atlas",
            received_at=now,
        )

    def test_maps_assistant_request_to_local_llm_request(self):
        provider = FakeProvider()
        generator = OllamaResponseGenerator(provider, "gemma4:e2b")

        kind, content = generator.generate(self.request)

        llm_request = provider.received_request
        self.assertIsInstance(llm_request, LLMRequest)
        self.assertEqual(llm_request.model, "gemma4:e2b")
        self.assertEqual(
            [message.role for message in llm_request.messages],
            [LLMMessageRole.SYSTEM, LLMMessageRole.USER],
        )
        self.assertEqual(llm_request.messages[0].content, ATLAS_SYSTEM_PROMPT)
        self.assertEqual(llm_request.messages[1].content, "Hola, Atlas")
        self.assertEqual(llm_request.temperature, 0.2)
        self.assertEqual(llm_request.max_tokens, 512)
        self.assertIs(kind, AssistantResponseKind.INFORMATIONAL)
        self.assertEqual(content, "Hola. ¿En qué te ayudo?")

    def test_maps_history_between_system_and_current_user_messages(self):
        provider = FakeProvider()
        generator = OllamaResponseGenerator(provider, "gemma4:e2b")
        request = replace(
            self.request,
            history=(
                ConversationMessage(ConversationMessageRole.USER, "Me llamo Ana"),
                ConversationMessage(
                    ConversationMessageRole.ASSISTANT,
                    "Mucho gusto, Ana.",
                ),
            ),
        )

        generator.generate(request)

        messages = provider.received_request.messages
        self.assertEqual(
            [message.role for message in messages],
            [
                LLMMessageRole.SYSTEM,
                LLMMessageRole.USER,
                LLMMessageRole.ASSISTANT,
                LLMMessageRole.USER,
            ],
        )
        self.assertEqual(
            [message.content for message in messages],
            [
                ATLAS_SYSTEM_PROMPT,
                "Me llamo Ana",
                "Mucho gusto, Ana.",
                "Hola, Atlas",
            ],
        )

    def test_allows_explicit_generation_configuration(self):
        provider = FakeProvider()
        generator = OllamaResponseGenerator(
            provider,
            "local-model",
            system_prompt="Responde en español.",
            temperature=0,
            max_tokens=64,
        )

        generator.generate(self.request)

        llm_request = provider.received_request
        self.assertEqual(llm_request.messages[0].content, "Responde en español.")
        self.assertEqual(llm_request.temperature, 0)
        self.assertEqual(llm_request.max_tokens, 64)

    def test_reports_unavailable_ollama_as_error_response(self):
        provider = FakeProvider(error=OllamaUnavailableError("offline"))
        generator = OllamaResponseGenerator(provider, "gemma4:e2b")

        kind, content = generator.generate(self.request)

        self.assertIs(kind, AssistantResponseKind.ERROR)
        self.assertIn("Ollama esté disponible", content)
        self.assertIn("modelo configurado", content)

    def test_reports_ollama_response_error_without_leaking_raw_error(self):
        provider = FakeProvider(
            error=OllamaResponseError("raw provider response")
        )
        generator = OllamaResponseGenerator(provider, "gemma4:e2b")

        kind, content = generator.generate(self.request)

        self.assertIs(kind, AssistantResponseKind.ERROR)
        self.assertNotIn("raw provider response", content)

    def test_rejects_invalid_dependencies_and_configuration(self):
        with self.assertRaises(ContractError):
            OllamaResponseGenerator(object(), "gemma4:e2b")
        with self.assertRaises(ContractError):
            OllamaResponseGenerator(FakeProvider(), " ")
        with self.assertRaises(ContractError):
            OllamaResponseGenerator(
                FakeProvider(), "gemma4:e2b", system_prompt=" "
            )

    def test_rejects_non_assistant_request(self):
        generator = OllamaResponseGenerator(FakeProvider(), "gemma4:e2b")

        with self.assertRaises(ContractError):
            generator.generate("Hola")

    def test_rejects_invalid_provider_response(self):
        class InvalidProvider:
            def generate(self, request):
                return "not-an-llm-response"

        generator = OllamaResponseGenerator(InvalidProvider(), "local-model")

        with self.assertRaises(ContractError):
            generator.generate(self.request)

    def test_assistant_service_wraps_local_model_response(self):
        provider = FakeProvider()
        generator = OllamaResponseGenerator(provider, "gemma4:e2b")
        service = AssistantService(
            response_generator=generator,
            clock=FixedClock(self.request.received_at),
        )

        response = service.respond(self.request)

        self.assertEqual(response.request_id, self.request.request_id)
        self.assertIs(response.context, self.request.context)
        self.assertIs(response.kind, AssistantResponseKind.INFORMATIONAL)
        self.assertEqual(response.content, "Hola. ¿En qué te ayudo?")
        self.assertEqual(response.created_at, self.request.received_at)

    def test_assistant_service_preserves_provider_failure_as_error_kind(self):
        provider = FakeProvider(error=OllamaUnavailableError("offline"))
        generator = OllamaResponseGenerator(provider, "gemma4:e2b")
        service = AssistantService(
            response_generator=generator,
            clock=FixedClock(self.request.received_at),
        )

        response = service.respond(self.request)

        self.assertIs(response.kind, AssistantResponseKind.ERROR)
        self.assertIn("modelo configurado", response.content)


if __name__ == "__main__":
    unittest.main()
