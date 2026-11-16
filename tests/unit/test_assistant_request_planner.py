"""Pruebas del orquestador de interpretación y planificación."""

from datetime import datetime, timezone
import unittest

from atlas.assistant.planning import (
    AssistantIntent,
    AssistantPlan,
    IntentInterpretation,
    IntentKind,
    InterpretationStatus,
)
from atlas.assistant.request_planner import (
    AssistantRequestPlanner,
    RequestPlanningResult,
    RequestPlanningStatus,
)
from atlas.core.errors import ContractError


NOW = datetime(2026, 11, 16, 18, 0, tzinfo=timezone.utc)


class FakeInterpreter:
    def __init__(self, result):
        self.result = result
        self.received_content = None
        self.calls = 0

    def interpret(self, content):
        self.calls += 1
        self.received_content = content
        return self.result


class AssistantRequestPlannerTests(unittest.TestCase):
    def test_ready_workspace_list_becomes_planned_result(self):
        interpretation = IntentInterpretation(
            InterpretationStatus.READY,
            AssistantIntent(
                IntentKind.WORKSPACE_LIST,
                (("workspace_id", "demo"),),
            ),
        )
        interpreter = FakeInterpreter(interpretation)
        planner = AssistantRequestPlanner(interpreter)

        result = planner.process("  Lista los archivos del workspace demo  ", NOW)

        self.assertIsInstance(result, RequestPlanningResult)
        self.assertIs(result.status, RequestPlanningStatus.PLANNED)
        self.assertIsInstance(result.plan, AssistantPlan)
        self.assertEqual(result.plan.intent, interpretation.intent)
        self.assertEqual(interpreter.calls, 1)
        self.assertEqual(
            interpreter.received_content,
            "Lista los archivos del workspace demo",
        )

    def test_ready_workspace_read_becomes_planned_result(self):
        interpretation = IntentInterpretation(
            InterpretationStatus.READY,
            AssistantIntent(
                IntentKind.WORKSPACE_READ,
                (("workspace_id", "demo"), ("path", "README.md")),
            ),
        )

        result = AssistantRequestPlanner(
            FakeInterpreter(interpretation)
        ).process("Lee README.md", NOW)

        self.assertIs(result.status, RequestPlanningStatus.PLANNED)
        self.assertEqual(
            dict(result.plan.steps[0].parameters),
            {"workspace_id": "demo", "path": "README.md"},
        )

    def test_clarification_is_returned_without_plan(self):
        interpretation = IntentInterpretation(
            InterpretationStatus.NEEDS_CLARIFICATION,
            message="¿Qué workspace debo inspeccionar?",
        )

        result = AssistantRequestPlanner(
            FakeInterpreter(interpretation)
        ).process("Inspecciona mi workspace", NOW)

        self.assertIs(result.status, RequestPlanningStatus.NEEDS_CLARIFICATION)
        self.assertIsNone(result.plan)
        self.assertEqual(result.message, interpretation.message)

    def test_unsupported_is_returned_without_plan(self):
        interpretation = IntentInterpretation(
            InterpretationStatus.UNSUPPORTED,
            message="No puedo enviar correos.",
        )

        result = AssistantRequestPlanner(
            FakeInterpreter(interpretation)
        ).process("Envía un correo", NOW)

        self.assertIs(result.status, RequestPlanningStatus.UNSUPPORTED)
        self.assertIsNone(result.plan)
        self.assertEqual(result.message, interpretation.message)

    def test_rejects_invalid_interpreter_and_interpreter_result(self):
        with self.assertRaises(ContractError):
            AssistantRequestPlanner(object())

        with self.assertRaises(ContractError):
            AssistantRequestPlanner(FakeInterpreter("ready")).process(
                "Lista archivos", NOW
            )

    def test_rejects_empty_request_without_calling_interpreter(self):
        interpreter = FakeInterpreter(
            IntentInterpretation(
                InterpretationStatus.UNSUPPORTED,
                message="No soportado",
            )
        )
        planner = AssistantRequestPlanner(interpreter)

        with self.assertRaises(ContractError):
            planner.process("  ", NOW)

        self.assertEqual(interpreter.calls, 0)

    def test_invalid_timestamp_is_rejected_for_ready_interpretation(self):
        interpretation = IntentInterpretation(
            InterpretationStatus.READY,
            AssistantIntent(
                IntentKind.WORKSPACE_LIST,
                (("workspace_id", "demo"),),
            ),
        )

        with self.assertRaises(ContractError):
            AssistantRequestPlanner(FakeInterpreter(interpretation)).process(
                "Lista archivos", datetime(2026, 11, 16, 18, 0)
            )


if __name__ == "__main__":
    unittest.main()
