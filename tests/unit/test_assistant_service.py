"""Pruebas del servicio conversacional mínimo."""

from datetime import datetime, timezone
import unittest

from atlas.assistant import (
    AssistantRequest,
    AssistantResponseKind,
    AssistantService,
)
from atlas.core.errors import ContractError
from tests.fixtures.contexts import user_context


class FixedClock:
    def __init__(self, value):
        self.value = value

    def now(self):
        return self.value


class FixedResponseGenerator:
    def __init__(self, result):
        self.result = result
        self.received_request = None

    def generate(self, request):
        self.received_request = request
        return self.result


class AssistantServiceTests(unittest.TestCase):
    def setUp(self):
        self.context = user_context()
        self.now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
        self.request = AssistantRequest(
            request_id=self.context.request_id,
            context=self.context,
            content="Hola, Atlas",
            received_at=self.now,
        )

    def test_respond_builds_correlated_response(self):
        generator = FixedResponseGenerator(
            (AssistantResponseKind.INFORMATIONAL, "Hola. ¿En qué te ayudo?")
        )
        service = AssistantService(generator, FixedClock(self.now))

        response = service.respond(self.request)

        self.assertIs(generator.received_request, self.request)
        self.assertEqual(response.request_id, self.request.request_id)
        self.assertIs(response.context, self.request.context)
        self.assertIs(response.kind, AssistantResponseKind.INFORMATIONAL)
        self.assertEqual(response.content, "Hola. ¿En qué te ayudo?")
        self.assertEqual(response.created_at, self.now)

    def test_rejects_non_request_input(self):
        service = AssistantService(
            FixedResponseGenerator(
                (AssistantResponseKind.INFORMATIONAL, "Hola")
            ),
            FixedClock(self.now),
        )

        with self.assertRaises(ContractError):
            service.respond("Hola, Atlas")

    def test_rejects_invalid_generator_result_shape(self):
        service = AssistantService(
            FixedResponseGenerator("Hola"),
            FixedClock(self.now),
        )

        with self.assertRaises(ContractError):
            service.respond(self.request)

    def test_rejects_invalid_response_kind_or_empty_content(self):
        invalid_results = (
            ("informational", "Hola"),
            (AssistantResponseKind.INFORMATIONAL, " "),
        )
        for result in invalid_results:
            with self.subTest(result=result):
                service = AssistantService(
                    FixedResponseGenerator(result),
                    FixedClock(self.now),
                )
                with self.assertRaises(ContractError):
                    service.respond(self.request)

    def test_rejects_missing_dependencies(self):
        with self.assertRaises(ContractError):
            AssistantService(object(), FixedClock(self.now))

        with self.assertRaises(ContractError):
            AssistantService(
                FixedResponseGenerator(
                    (AssistantResponseKind.INFORMATIONAL, "Hola")
                ),
                object(),
            )


if __name__ == "__main__":
    unittest.main()
