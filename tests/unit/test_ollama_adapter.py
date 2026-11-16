"""Pruebas del adaptador local Ollama sin servidor externo."""

import unittest

from atlas.core.errors import ContractError
from atlas.adapters.ollama import (
    OllamaProvider,
    OllamaResponseError,
    OllamaUnavailableError,
)
from atlas.ports.llm import (
    LLMMessage,
    LLMMessageRole,
    LLMRequest,
)


class FakeTransport:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def post_json(self, url, payload, timeout):
        self.calls.append((url, payload, timeout))
        if self.error is not None:
            raise self.error
        return self.result


class OllamaProviderTests(unittest.TestCase):
    def setUp(self):
        self.request = LLMRequest(
            model="gemma4:e2b",
            messages=(
                LLMMessage(LLMMessageRole.SYSTEM, "Eres Atlas."),
                LLMMessage(LLMMessageRole.USER, "Hola."),
            ),
            temperature=0.2,
            max_tokens=128,
        )
        self.result = {
            "model": "gemma4:e2b",
            "message": {"role": "assistant", "content": "Hola. ¿En qué te ayudo?"},
            "done_reason": "stop",
        }

    def test_uses_local_chat_endpoint_and_maps_request(self):
        transport = FakeTransport(self.result)
        provider = OllamaProvider(transport=transport, timeout=12)

        response = provider.generate(self.request)

        url, payload, timeout = transport.calls[0]
        self.assertEqual(url, "http://127.0.0.1:11434/api/chat")
        self.assertEqual(timeout, 12)
        self.assertEqual(payload["model"], "gemma4:e2b")
        self.assertEqual(
            payload["messages"],
            [
                {"role": "system", "content": "Eres Atlas."},
                {"role": "user", "content": "Hola."},
            ],
        )
        self.assertIs(payload["stream"], False)
        self.assertEqual(
            payload["options"],
            {"temperature": 0.2, "num_predict": 128},
        )
        self.assertEqual(response.provider, "ollama")
        self.assertEqual(response.model, "gemma4:e2b")
        self.assertEqual(response.content, "Hola. ¿En qué te ayudo?")
        self.assertEqual(response.finish_reason, "stop")

    def test_omits_generation_options_when_not_configured(self):
        transport = FakeTransport(self.result)
        provider = OllamaProvider(transport=transport)
        request = LLMRequest(
            model="local-model",
            messages=(LLMMessage(LLMMessageRole.USER, "Hola"),),
        )

        provider.generate(request)

        payload = transport.calls[0][1]
        self.assertNotIn("options", payload)

    def test_applies_optional_thinking_and_json_format_settings(self):
        transport = FakeTransport(self.result)
        provider = OllamaProvider(
            transport=transport,
            think=False,
            response_format="json",
        )

        provider.generate(self.request)

        payload = transport.calls[0][1]
        self.assertIs(payload["think"], False)
        self.assertEqual(payload["format"], "json")

    def test_omits_thinking_and_format_settings_by_default(self):
        transport = FakeTransport(self.result)
        provider = OllamaProvider(transport=transport)

        provider.generate(self.request)

        payload = transport.calls[0][1]
        self.assertNotIn("think", payload)
        self.assertNotIn("format", payload)

    def test_rejects_invalid_thinking_and_format_settings(self):
        for kwargs in (
            {"think": "false"},
            {"think": 0},
            {"response_format": "xml"},
            {"response_format": {}},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ContractError):
                    OllamaProvider(transport=FakeTransport(self.result), **kwargs)

    def test_accepts_localhost_and_loopback_addresses(self):
        for address in (
            "http://localhost:11434",
            "http://127.0.0.1:11434",
            "http://[::1]:11434",
        ):
            with self.subTest(address=address):
                provider = OllamaProvider(base_url=address, transport=FakeTransport(self.result))
                self.assertTrue(provider._base_url.startswith("http://"))

    def test_rejects_non_local_or_unsafe_base_urls(self):
        invalid_urls = (
            "https://localhost:11434",
            "http://ollama.example.com:11434",
            "http://127.0.0.1.evil.example:11434",
            "http://user:pass@localhost:11434",
            "http://localhost:11434/api",
            "http://localhost:11434?redirect=1",
            "http://localhost:99999",
            "",
        )
        for address in invalid_urls:
            with self.subTest(address=address):
                with self.assertRaises(ContractError):
                    OllamaProvider(base_url=address, transport=FakeTransport(self.result))

    def test_rejects_invalid_timeout_and_transport(self):
        for timeout in (0, -1, True, float("inf"), "30"):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ContractError):
                    OllamaProvider(timeout=timeout, transport=FakeTransport(self.result))
        with self.assertRaises(ContractError):
            OllamaProvider(transport=object())

    def test_rejects_non_llm_request(self):
        provider = OllamaProvider(transport=FakeTransport(self.result))
        with self.assertRaises(ContractError):
            provider.generate("Hola")

    def test_maps_transport_unavailability(self):
        provider = OllamaProvider(
            transport=FakeTransport(error=TimeoutError("timeout"))
        )
        with self.assertRaises(OllamaUnavailableError):
            provider.generate(self.request)

    def test_propagates_ollama_response_errors(self):
        provider = OllamaProvider(
            transport=FakeTransport(error=OllamaResponseError("HTTP 500"))
        )
        with self.assertRaises(OllamaResponseError):
            provider.generate(self.request)

    def test_rejects_provider_error_and_malformed_payloads(self):
        invalid_results = (
            {"error": "model not found"},
            {},
            {"message": "not-an-object"},
            {"message": {"content": " "}},
            {"message": {"content": 42}},
        )
        for result in invalid_results:
            with self.subTest(result=result):
                provider = OllamaProvider(transport=FakeTransport(result))
                with self.assertRaises(OllamaResponseError):
                    provider.generate(self.request)

    def test_falls_back_to_requested_model_when_response_omits_model(self):
        provider = OllamaProvider(
            transport=FakeTransport(
                {"message": {"content": "Respuesta local"}}
            )
        )

        response = provider.generate(self.request)

        self.assertEqual(response.model, self.request.model)
        self.assertIsNone(response.finish_reason)


if __name__ == "__main__":
    unittest.main()
