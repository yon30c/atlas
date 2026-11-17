"""Pruebas del servicio de aplicación de planificación."""

from datetime import datetime, timezone
import unittest

from atlas.assistant.planning import (
    AssistantIntent,
    AssistantPlan,
    IntentInterpretation,
    IntentKind,
    InterpretationStatus,
)
from atlas.assistant.planning_service import AssistantPlanningService
from atlas.core.errors import ContractError


NOW = datetime(2026, 11, 16, 18, 0, tzinfo=timezone.utc)


class AssistantPlanningServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = AssistantPlanningService()

    def test_creates_single_step_plan_for_workspace_list(self):
        interpretation = IntentInterpretation(
            InterpretationStatus.READY,
            AssistantIntent(
                IntentKind.WORKSPACE_LIST,
                (("workspace_id", "demo"),),
            ),
        )

        result = self.service.plan(interpretation, NOW)

        self.assertIsInstance(result, AssistantPlan)
        self.assertEqual(result.intent, interpretation.intent)
        self.assertEqual(result.goal, "Listar archivos del workspace 'demo'")
        self.assertEqual(len(result.steps), 1)
        self.assertEqual(result.steps[0].step_id, "step-1")
        self.assertIs(result.steps[0].capability, IntentKind.WORKSPACE_LIST)
        self.assertEqual(dict(result.steps[0].parameters), {"workspace_id": "demo"})
        self.assertIn("Listado", result.steps[0].expected_result)
        self.assertEqual(result.created_at, NOW)

    def test_creates_single_step_plan_for_workspace_read(self):
        interpretation = IntentInterpretation(
            InterpretationStatus.READY,
            AssistantIntent(
                IntentKind.WORKSPACE_READ,
                (("workspace_id", "demo"), ("path", "README.md")),
            ),
        )

        result = self.service.plan(interpretation, NOW)

        self.assertIsInstance(result, AssistantPlan)
        self.assertEqual(
            result.goal,
            "Leer el archivo 'README.md' del workspace 'demo'",
        )
        self.assertEqual(
            dict(result.steps[0].parameters),
            {"workspace_id": "demo", "path": "README.md"},
        )
        self.assertIn("README.md", result.steps[0].expected_result)

    def test_preserves_clarification_without_creating_plan(self):
        interpretation = IntentInterpretation(
            InterpretationStatus.NEEDS_CLARIFICATION,
            message="¿Qué workspace debo inspeccionar?",
        )

        result = self.service.plan(interpretation, NOW)

        self.assertIs(result, interpretation)

    def test_preserves_unsupported_result_without_creating_plan(self):
        interpretation = IntentInterpretation(
            InterpretationStatus.UNSUPPORTED,
            message="No puedo enviar correos.",
        )

        result = self.service.plan(interpretation, NOW)

        self.assertIs(result, interpretation)

    def test_rejects_non_interpretation_input(self):
        with self.assertRaises(ContractError):
            self.service.plan("ready", NOW)

    def test_plan_rejects_non_utc_timestamp(self):
        interpretation = IntentInterpretation(
            InterpretationStatus.READY,
            AssistantIntent(
                IntentKind.WORKSPACE_LIST,
                (("workspace_id", "demo"),),
            ),
        )

        with self.assertRaises(ContractError):
            self.service.plan(
                interpretation,
                datetime(2026, 11, 16, 18, 0),
            )


if __name__ == "__main__":
    unittest.main()
