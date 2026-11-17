"""Pruebas de contratos de intención y planificación del Assistant."""

from datetime import datetime, timezone
import unittest

from atlas.assistant.planning import (
    AssistantIntent,
    AssistantPlan,
    IntentInterpretation,
    InterpretationStatus,
    IntentKind,
    PlanStep,
)
from atlas.core.errors import ContractError


NOW = datetime(2026, 11, 16, 18, 0, tzinfo=timezone.utc)


class AssistantPlanningTests(unittest.TestCase):
    def test_workspace_list_intent_requires_workspace_id(self):
        intent = AssistantIntent(
            IntentKind.WORKSPACE_LIST,
            (("workspace_id", "demo"),),
        )
        self.assertEqual(intent.kind, IntentKind.WORKSPACE_LIST)

    def test_workspace_read_intent_requires_path(self):
        with self.assertRaises(ContractError):
            AssistantIntent(
                IntentKind.WORKSPACE_READ,
                (("workspace_id", "demo"),),
            )

        intent = AssistantIntent(
            IntentKind.WORKSPACE_READ,
            (("workspace_id", "demo"), ("path", "README.md")),
        )
        self.assertEqual(dict(intent.parameters)["path"], "README.md")

    def test_intent_rejects_unknown_or_duplicate_parameters(self):
        with self.assertRaises(ContractError):
            AssistantIntent(
                IntentKind.WORKSPACE_LIST,
                (("workspace_id", "demo"), ("unexpected", "value")),
            )
        with self.assertRaises(ContractError):
            AssistantIntent(
                IntentKind.WORKSPACE_LIST,
                (("workspace_id", "demo"), ("workspace_id", "other")),
            )

    def test_interpretation_ready_requires_intent(self):
        result = IntentInterpretation(
            InterpretationStatus.READY,
            AssistantIntent(IntentKind.WORKSPACE_LIST, (("workspace_id", "demo"),)),
        )
        self.assertIs(result.status, InterpretationStatus.READY)

        with self.assertRaises(ContractError):
            IntentInterpretation(InterpretationStatus.READY)

    def test_interpretation_can_request_clarification(self):
        result = IntentInterpretation(
            InterpretationStatus.NEEDS_CLARIFICATION,
            message="¿Qué workspace debo inspeccionar?",
        )
        self.assertIsNone(result.intent)

        with self.assertRaises(ContractError):
            IntentInterpretation(
                InterpretationStatus.NEEDS_CLARIFICATION,
                AssistantIntent(IntentKind.WORKSPACE_LIST, (("workspace_id", "demo"),)),
                "Aclaración",
            )

    def test_interpretation_can_mark_unsupported_request(self):
        result = IntentInterpretation(
            InterpretationStatus.UNSUPPORTED,
            message="La solicitud no corresponde a una capacidad disponible.",
        )
        self.assertIs(result.status, InterpretationStatus.UNSUPPORTED)

    def test_plan_requires_matching_steps_and_utc_timestamp(self):
        intent = AssistantIntent(IntentKind.WORKSPACE_LIST, (("workspace_id", "demo"),))
        step = PlanStep(
            "step-1", IntentKind.WORKSPACE_LIST,
            (("workspace_id", "demo"),), "Listado de archivos del workspace demo",
        )
        plan = AssistantPlan.create("Listar archivos", intent, (step,), NOW)
        self.assertTrue(plan.plan_id)
        self.assertEqual(plan.steps, (step,))

        wrong_step = PlanStep(
            "step-2", IntentKind.WORKSPACE_READ,
            (("workspace_id", "demo"), ("path", "README.md")), "Leer README",
        )
        with self.assertRaises(ContractError):
            AssistantPlan("plan-2", "Listar archivos", intent, (wrong_step,), NOW)

        with self.assertRaises(ContractError):
            AssistantPlan.create("Listar archivos", intent, (step,), datetime(2026, 11, 16))

    def test_plan_is_not_an_execution_result(self):
        intent = AssistantIntent(IntentKind.WORKSPACE_LIST, (("workspace_id", "demo"),))
        step = PlanStep(
            "step-1", IntentKind.WORKSPACE_LIST,
            (("workspace_id", "demo"),), "Listado de archivos",
        )
        plan = AssistantPlan.create("Listar archivos", intent, (step,), NOW)
        self.assertFalse(hasattr(plan, "execution_result"))
        self.assertFalse(hasattr(plan, "executed_at"))


if __name__ == "__main__":
    unittest.main()
