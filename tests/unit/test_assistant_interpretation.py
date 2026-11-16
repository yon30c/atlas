"""Pruebas del parser de salidas estructuradas de intención."""

import unittest

from atlas.assistant.interpretation import parse_intent_interpretation
from atlas.assistant.planning import IntentKind, InterpretationStatus
from atlas.core.errors import ContractError


class StructuredIntentParserTests(unittest.TestCase):
    def test_parses_workspace_list(self):
        result = parse_intent_interpretation(
            '{"status":"ready","kind":"workspace.list",'
            '"parameters":{"workspace_id":"demo"},"message":null}'
        )
        self.assertIs(result.status, InterpretationStatus.READY)
        self.assertIs(result.intent.kind, IntentKind.WORKSPACE_LIST)
        self.assertEqual(dict(result.intent.parameters), {"workspace_id": "demo"})

    def test_parses_workspace_read(self):
        result = parse_intent_interpretation(
            '{"status":"ready","kind":"workspace.read",'
            '"parameters":{"workspace_id":"demo","path":"README.md"},"message":null}'
        )
        self.assertEqual(dict(result.intent.parameters)["path"], "README.md")

    def test_parses_clarification(self):
        result = parse_intent_interpretation(
            '{"status":"needs_clarification","kind":null,'
            '"parameters":{},"message":"¿Qué workspace?"}'
        )
        self.assertIs(result.status, InterpretationStatus.NEEDS_CLARIFICATION)

    def test_parses_unsupported(self):
        result = parse_intent_interpretation(
            '{"status":"unsupported","kind":null,'
            '"parameters":{},"message":"No disponible"}'
        )
        self.assertIs(result.status, InterpretationStatus.UNSUPPORTED)

    def test_rejects_invalid_json_and_non_object(self):
        for content in ("not json", "[]", '"text"'):
            with self.subTest(content=content), self.assertRaises(ContractError):
                parse_intent_interpretation(content)

    def test_rejects_unknown_fields_and_missing_fields(self):
        base = '{"status":"ready","kind":"workspace.list",'
        for content in (
            base + '"parameters":{"workspace_id":"demo"},"message":null,"execute":true}',
            '{"status":"ready","kind":"workspace.list","parameters":{}}',
        ):
            with self.subTest(content=content), self.assertRaises(ContractError):
                parse_intent_interpretation(content)

    def test_rejects_unknown_capabilities_and_parameters(self):
        for content in (
            '{"status":"ready","kind":"shell.exec","parameters":{},"message":null}',
            '{"status":"ready","kind":"workspace.list",'
            '"parameters":{"workspace_id":"demo","command":"ls"},"message":null}',
        ):
            with self.subTest(content=content), self.assertRaises(ContractError):
                parse_intent_interpretation(content)

    def test_rejects_inconsistent_status_payloads(self):
        for content in (
            '{"status":"ready","kind":null,"parameters":{},"message":null}',
            '{"status":"needs_clarification","kind":"workspace.list",'
            '"parameters":{},"message":"Aclarar"}',
            '{"status":"unsupported","kind":null,"parameters":{},'
            '"message":" "}',
        ):
            with self.subTest(content=content), self.assertRaises(ContractError):
                parse_intent_interpretation(content)


if __name__ == "__main__":
    unittest.main()
