"""Pruebas de los contratos neutrales para modelos de lenguaje."""

import unittest

from atlas.core.errors import ContractError
from atlas.ports.llm import (
    LLMMessage,
    LLMMessageRole,
    LLMRequest,
    LLMResponse,
)


class LLMContractTests(unittest.TestCase):
    def test_builds_valid_request_with_optional_generation_settings(self):
        request = LLMRequest(
            model="gemma4:e2b",
            messages=(
                LLMMessage(LLMMessageRole.SYSTEM, "Eres Atlas."),
                LLMMessage(LLMMessageRole.USER, "Hola."),
            ),
            temperature=0.2,
            max_tokens=256,
        )

        self.assertEqual(request.model, "gemma4:e2b")
        self.assertEqual(len(request.messages), 2)
        self.assertEqual(request.temperature, 0.2)
        self.assertEqual(request.max_tokens, 256)

    def test_rejects_invalid_messages(self):
        invalid_values = ((), [], ("Hola",), ("not-a-message",))
        for messages in invalid_values:
            with self.subTest(messages=messages):
                with self.assertRaises(ContractError):
                    LLMRequest(model="local-model", messages=messages)

    def test_rejects_invalid_message_role(self):
        with self.assertRaises(ContractError):
            LLMMessage("user", "Hola")

    def test_rejects_blank_model_and_message_content(self):
        with self.assertRaises(ContractError):
            LLMRequest(model=" ", messages=(LLMMessage(LLMMessageRole.USER, "Hola"),))
        with self.assertRaises(ContractError):
            LLMMessage(LLMMessageRole.USER, " ")

    def test_rejects_invalid_generation_settings(self):
        message = (LLMMessage(LLMMessageRole.USER, "Hola"),)
        for temperature in (-0.1, 2.1, True, "0.5"):
            with self.subTest(temperature=temperature):
                with self.assertRaises(ContractError):
                    LLMRequest("model", message, temperature=temperature)
        for max_tokens in (0, -1, 1.5, True, "100"):
            with self.subTest(max_tokens=max_tokens):
                with self.assertRaises(ContractError):
                    LLMRequest("model", message, max_tokens=max_tokens)

    def test_builds_valid_response(self):
        response = LLMResponse(
            provider="ollama",
            model="gemma4:e2b",
            content="Hola, ¿en qué puedo ayudarte?",
            finish_reason="stop",
        )

        self.assertEqual(response.provider, "ollama")
        self.assertEqual(response.model, "gemma4:e2b")
        self.assertEqual(response.finish_reason, "stop")

    def test_rejects_invalid_response_fields(self):
        for values in (
            (" ", "model", "text"),
            ("ollama", " ", "text"),
            ("ollama", "model", " "),
        ):
            with self.subTest(values=values):
                with self.assertRaises(ContractError):
                    LLMResponse(*values)

    def test_contract_does_not_expose_execution_capabilities(self):
        self.assertEqual(
            set(LLMMessageRole),
            {
                LLMMessageRole.SYSTEM,
                LLMMessageRole.USER,
                LLMMessageRole.ASSISTANT,
            },
        )


if __name__ == "__main__":
    unittest.main()
