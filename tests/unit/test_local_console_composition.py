"""Pruebas de la composición local de Atlas."""

from datetime import datetime, timezone
import unittest

from atlas.adapters.system_clock import SystemClock
from atlas.assistant.local_console import (
    LocalConsoleRequestFactory,
    LocalModeResponseGenerator,
)
from atlas.assistant.models import AssistantRequest, AssistantResponseKind
from atlas.cli import main
from atlas.core.identity import IdentityKind, IdentityStatus


class FixedClock:
    def __init__(self, value):
        self.value = value

    def now(self):
        return self.value


class LocalConsoleCompositionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 14, 14, 0, tzinfo=timezone.utc)
        self.clock = FixedClock(self.now)

    def test_system_clock_returns_utc_aware_datetime(self):
        now = SystemClock().now()

        self.assertIsNotNone(now.tzinfo)
        self.assertEqual(now.utcoffset().total_seconds(), 0)

    def test_factory_builds_local_user_context(self):
        factory = LocalConsoleRequestFactory(self.clock, user_id="greed")

        request = factory.create("Hola, Atlas")

        self.assertIsInstance(request, AssistantRequest)
        self.assertEqual(request.content, "Hola, Atlas")
        self.assertEqual(request.received_at, self.now)
        self.assertEqual(request.context.created_at, self.now)
        self.assertEqual(request.context.user_id, "local:greed")
        self.assertEqual(request.context.actor.identity_id, "local-user:greed")
        self.assertIs(request.context.actor.kind, IdentityKind.USER)
        self.assertIs(request.context.actor.status, IdentityStatus.ACTIVE)
        self.assertEqual(request.context.origin, "console")
        self.assertEqual(request.context.environment, "local")
        self.assertEqual(request.context.purpose, "local_conversation")
        self.assertEqual(request.context.classification, "internal")
        self.assertIsNone(request.context.delegation)
        self.assertIsNone(request.context.project_id)

    def test_factory_correlates_requests_and_keeps_conversation_id(self):
        factory = LocalConsoleRequestFactory(self.clock, user_id="greed")

        first = factory.create("Uno")
        second = factory.create("Dos")

        self.assertNotEqual(first.request_id, second.request_id)
        self.assertEqual(first.context.correlation_id, first.request_id)
        self.assertEqual(second.context.correlation_id, second.request_id)
        self.assertEqual(first.conversation_id, second.conversation_id)

    def test_local_generator_does_not_claim_to_be_an_llm(self):
        factory = LocalConsoleRequestFactory(self.clock, user_id="greed")
        request = factory.create("¿Qué puedes hacer?")

        kind, content = LocalModeResponseGenerator().generate(request)

        self.assertIs(kind, AssistantResponseKind.INFORMATIONAL)
        self.assertIn("Todavía no tengo conectado un modelo", content)
        self.assertIn("no puedo interpretar solicitudes", content)

    def test_main_runs_a_complete_local_terminal_session(self):
        inputs = iter(["Hola, Atlas", "salir"])
        output = []

        main(
            input_fn=lambda _prompt: next(inputs),
            output_fn=output.append,
            user_id="test-user",
        )

        self.assertEqual(output[0], "Atlas está listo. Escribe 'salir' para terminar.")
        self.assertTrue(any("modelo de lenguaje" in line for line in output))
        self.assertEqual(output[-1], "Atlas: hasta luego.")


if __name__ == "__main__":
    unittest.main()
