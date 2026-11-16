"""Pruebas de composición del planificador con el adaptador Ollama."""

from datetime import datetime, timezone
import unittest

from atlas.assistant.request_planner import (
    RequestPlanningStatus,
)
from atlas.bootstrap import build_request_planner
from atlas.core.errors import ContractError
from atlas.ports.llm import LLMResponse


NOW = datetime(2026, 11, 16, 18, 0, tzinfo=timezone.utc)


class FakeProvider:
    def __init__(self, content):
        self.content = content
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return LLMResponse("ollama", request.model, self.content)


class BootstrapTests(unittest.TestCase):
    def test_builds_planner_and_creates_plan_from_structured_model_output(self):
        provider = FakeProvider(
            '{"status":"ready","kind":"workspace.list",'
            '"parameters":{"workspace_id":"demo"},"message":null}'
        )
        planner = build_request_planner(provider, "gemma4:e2b-it-q4_K_M")

        result = planner.process("Lista los archivos del workspace demo", NOW)

        self.assertIs(result.status, RequestPlanningStatus.PLANNED)
        self.assertEqual(result.plan.intent.kind.value, "workspace.list")
        self.assertEqual(len(provider.requests), 1)
        self.assertEqual(provider.requests[0].model, "gemma4:e2b-it-q4_K_M")

    def test_composed_planner_returns_clarification(self):
        provider = FakeProvider(
            '{"status":"needs_clarification","kind":null,'
            '"parameters":{},"message":"¿Qué workspace?"}'
        )

        result = build_request_planner(provider).process(
            "Inspecciona mi workspace", NOW
        )

        self.assertIs(result.status, RequestPlanningStatus.NEEDS_CLARIFICATION)
        self.assertEqual(result.message, "¿Qué workspace?")

    def test_composed_planner_returns_unsupported(self):
        provider = FakeProvider(
            '{"status":"unsupported","kind":null,'
            '"parameters":{},"message":"No puedo enviar correos."}'
        )

        result = build_request_planner(provider).process("Envía un correo", NOW)

        self.assertIs(result.status, RequestPlanningStatus.UNSUPPORTED)
        self.assertEqual(result.message, "No puedo enviar correos.")

    def test_rejects_invalid_provider_or_model(self):
        with self.assertRaises(ContractError):
            build_request_planner(object())
        with self.assertRaises(ContractError):
            build_request_planner(FakeProvider("{}"), " ")


if __name__ == "__main__":
    unittest.main()
