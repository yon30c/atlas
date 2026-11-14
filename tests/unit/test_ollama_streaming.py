"""Pruebas de streaming Ollama hasta la interfaz de consola."""

from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from atlas.adapters.ollama import OllamaProvider
from atlas.adapters.ollama_assistant import OllamaResponseGenerator
from atlas.assistant.models import AssistantRequest, AssistantResponseKind
from atlas.assistant.service import AssistantService
from atlas.cli import DEFAULT_MODEL, main
from atlas.ports.llm import LLMResponse
from tests.fixtures.contexts import user_context


class FakeStreamingTransport:
    def __init__(self, events):
        self.events = events
        self.calls = []

    def post_json(self, url, payload, timeout):
        raise AssertionError("La ruta de streaming debía utilizarse")

    def post_json_stream(self, url, payload, timeout, on_event):
        self.calls.append((url, payload, timeout))
        for event in self.events:
            on_event(event)


class FakeStreamingProvider:
    def __init__(self):
        self.request = None

    def generate(self, request):
        raise AssertionError("La ruta de streaming debía utilizarse")

    def generate_stream(self, request, on_token):
        self.request = request
        on_token("Hola")
        on_token(", Atlas.")
        return LLMResponse(
            provider="ollama",
            model=request.model,
            content="Hola, Atlas.",
            finish_reason="stop",
        )


class FixedClock:
    def __init__(self, value):
        self.value = value

    def now(self):
        return self.value


class OllamaStreamingTests(unittest.TestCase):
    def setUp(self):
        context = user_context()
        self.now = datetime(2026, 11, 14, 16, 0, tzinfo=timezone.utc)
        self.request = AssistantRequest(
            request_id=context.request_id,
            context=context,
            content="Hola",
            received_at=self.now,
        )

    def test_provider_streams_tokens_and_uses_stream_true(self):
        transport = FakeStreamingTransport([
            {"message": {"role": "assistant", "content": "Hola"}},
            {"message": {"role": "assistant", "content": " Atlas"}},
            {"model": "gemma4:e2b", "done": True, "done_reason": "stop"},
        ])
        provider = OllamaProvider(transport=transport)
        received = []

        response = provider.generate_stream(
            self._llm_request(), received.append
        )

        url, payload, timeout = transport.calls[0]
        self.assertEqual(url, "http://127.0.0.1:11434/api/chat")
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["model"], DEFAULT_MODEL)
        self.assertEqual(received, ["Hola", " Atlas"])
        self.assertEqual(response.content, "Hola Atlas")
        self.assertEqual(response.finish_reason, "stop")

    def test_provider_rejects_error_event_during_stream(self):
        transport = FakeStreamingTransport([{"error": "model not found"}])
        provider = OllamaProvider(transport=transport)
        with self.assertRaises(Exception):
            provider.generate_stream(self._llm_request(), lambda _token: None)

    def test_generator_and_service_preserve_streamed_response(self):
        provider = FakeStreamingProvider()
        generator = OllamaResponseGenerator(provider)
        service = AssistantService(generator, FixedClock(self.now))
        received = []

        response = service.respond_streaming(self.request, received.append)

        self.assertEqual(received, ["Hola", ", Atlas."])
        self.assertEqual(response.content, "Hola, Atlas.")
        self.assertIs(response.kind, AssistantResponseKind.INFORMATIONAL)
        self.assertEqual(response.request_id, self.request.request_id)
        self.assertEqual(provider.request.model, DEFAULT_MODEL)

    def test_cli_defaults_to_gemma_and_streams_to_terminal_writer(self):
        provider = FakeStreamingProvider()
        inputs = iter(["Hola, Atlas", "salir"])
        output = []
        written = []

        with patch.dict("os.environ", {"ATLAS_MODE": "", "ATLAS_MODEL": ""}):
            main(
                input_fn=lambda _prompt: next(inputs),
                output_fn=output.append,
                write_fn=written.append,
                user_id="stream-test",
                provider=provider,
            )

        self.assertEqual(provider.request.model, DEFAULT_MODEL)
        self.assertEqual("".join(written), "Atlas> Hola, Atlas.\n")
        self.assertIn("Atlas está listo. Escribe 'salir' para terminar.", output)
        self.assertEqual(output[-1], "Atlas: hasta luego.")

    def _llm_request(self):
        from atlas.ports.llm import LLMMessage, LLMMessageRole, LLMRequest

        return LLMRequest(
            model=DEFAULT_MODEL,
            messages=(LLMMessage(LLMMessageRole.USER, "Hola"),),
        )


if __name__ == "__main__":
    unittest.main()
