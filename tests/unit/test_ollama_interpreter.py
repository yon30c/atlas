"""Pruebas del adaptador LLM de interpretación de intenciones."""

import unittest

from atlas.adapters.ollama_interpreter import (
    INTENT_INTERPRETER_SYSTEM_PROMPT,
    OllamaIntentInterpreter,
)
from atlas.assistant.planning import IntentKind, InterpretationStatus
from atlas.core.errors import ContractError
from atlas.ports.llm import LLMMessageRole, LLMResponse


class FakeProvider:
    def __init__(self, content):
        self.content = content
        self.request = None

    def generate(self, request):
        self.request = request
        return LLMResponse("ollama", request.model, self.content)


class OllamaIntentInterpreterTests(unittest.TestCase):
    def test_interprets_explicit_workspace_listing(self):
        provider = FakeProvider(
            '{"status":"ready","kind":"workspace.list",'
            '"parameters":{"workspace_id":"demo"},"message":null}'
        )
        interpreter = OllamaIntentInterpreter(provider)

        result = interpreter.interpret("Lista los archivos del workspace demo")

        self.assertIs(result.status, InterpretationStatus.READY)
        self.assertIs(result.intent.kind, IntentKind.WORKSPACE_LIST)
        self.assertEqual(provider.request.model, "gemma4:e2b")
        self.assertEqual(
            [message.role for message in provider.request.messages],
            [LLMMessageRole.SYSTEM, LLMMessageRole.USER],
        )
        self.assertEqual(
            provider.request.messages[0].content,
            INTENT_INTERPRETER_SYSTEM_PROMPT,
        )
        self.assertEqual(
            provider.request.messages[1].content,
            "Lista los archivos del workspace demo",
        )
        self.assertEqual(provider.request.temperature, 0.0)
        self.assertEqual(provider.request.max_tokens, 256)

    def test_returns_clarification_when_workspace_is_ambiguous(self):
        provider = FakeProvider(
            '{"status":"needs_clarification","kind":null,'
            '"parameters":{},"message":"¿Qué workspace debo inspeccionar?"}'
        )
        result = OllamaIntentInterpreter(provider).interpret("Lista mis archivos")
        self.assertIs(result.status, InterpretationStatus.NEEDS_CLARIFICATION)

    def test_marks_unavailable_capability_as_unsupported(self):
        provider = FakeProvider(
            '{"status":"unsupported","kind":null,'
            '"parameters":{},"message":"No puedo enviar correos todavía."}'
        )
        result = OllamaIntentInterpreter(provider).interpret("Envía un correo")
        self.assertIs(result.status, InterpretationStatus.UNSUPPORTED)

    def test_rejects_malformed_or_untrusted_model_output(self):
        for output in (
            "No puedo hacerlo",
            '{"status":"ready","kind":"shell.exec","parameters":{},"message":null}',
            '{"status":"ready","kind":"workspace.list",'
            '"parameters":{"workspace_id":"demo","execute":"true"},"message":null}',
        ):
            with self.subTest(output=output):
                provider = FakeProvider(output)
                with self.assertRaises(ContractError):
                    OllamaIntentInterpreter(provider).interpret("Lista archivos")

    def test_rejects_empty_input_before_calling_provider(self):
        provider = FakeProvider("{}")
        interpreter = OllamaIntentInterpreter(provider)
        with self.assertRaises(ContractError):
            interpreter.interpret("  ")
        self.assertIsNone(provider.request)

    def test_rejects_invalid_provider_and_configuration(self):
        with self.assertRaises(ContractError):
            OllamaIntentInterpreter(object())
        with self.assertRaises(ContractError):
            OllamaIntentInterpreter(FakeProvider("{}"), " ")
        with self.assertRaises(ContractError):
            OllamaIntentInterpreter(
                FakeProvider("{}"), system_prompt=" "
            )


if __name__ == "__main__":
    unittest.main()
