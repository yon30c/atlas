"""Pruebas de comandos de vista previa de planes."""

from datetime import datetime, timezone
import unittest

from atlas.adapters.console_planning import PlanningConsoleCommands
from atlas.assistant.planning import (
    AssistantIntent,
    AssistantPlan,
    IntentInterpretation,
    IntentKind,
    InterpretationStatus,
    PlanStep,
)
from atlas.assistant.request_planner import (
    RequestPlanningResult,
    RequestPlanningStatus,
)
from atlas.core.errors import ContractError


NOW = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)


class FixedClock:
    def now(self):
        return NOW


class FakePlanner:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def process(self, content, created_at):
        self.calls.append((content, created_at))
        if self.error is not None:
            raise self.error
        return self.result


def planned_result():
    intent = AssistantIntent(
        IntentKind.WORKSPACE_LIST,
        (("workspace_id", "demo"),),
    )
    plan = AssistantPlan.create(
        goal="Listar archivos del workspace demo",
        intent=intent,
        steps=(
            PlanStep(
                step_id="step-1",
                capability=IntentKind.WORKSPACE_LIST,
                parameters=intent.parameters,
                expected_result="Listado de entradas del workspace demo",
            ),
        ),
        created_at=NOW,
    )
    return RequestPlanningResult(RequestPlanningStatus.PLANNED, plan=plan)


class PlanningConsoleCommandsTests(unittest.TestCase):
    def test_unrelated_command_is_not_handled(self):
        commands = PlanningConsoleCommands(FakePlanner(planned_result()), FixedClock())
        self.assertIsNone(commands.handle("/new conversación"))

    def test_plan_without_request_shows_usage(self):
        commands = PlanningConsoleCommands(FakePlanner(planned_result()), FixedClock())
        self.assertIn("Uso: /plan", commands.handle("/plan"))

    def test_offline_mode_explains_planner_is_unavailable(self):
        commands = PlanningConsoleCommands(None, FixedClock())
        self.assertIn("modo offline", commands.handle("/plan lista el workspace demo"))

    def test_planned_result_is_displayed_as_preview_not_execution(self):
        planner = FakePlanner(planned_result())
        commands = PlanningConsoleCommands(planner, FixedClock())

        result = commands.handle("/plan inspecciona el workspace demo")

        self.assertIn("solo vista previa", result)
        self.assertIn("workspace.list", result)
        self.assertIn("workspace_id: demo", result)
        self.assertIn("no se ejecutó ninguna operación", result)
        self.assertIn("autenticación confiable", result)
        self.assertEqual(
            planner.calls,
            [("inspecciona el workspace demo", NOW)],
        )

    def test_clarification_and_unsupported_results_are_not_presented_as_plans(self):
        clarification = RequestPlanningResult(
            RequestPlanningStatus.NEEDS_CLARIFICATION,
            message="¿Qué workspace quieres inspeccionar?",
        )
        commands = PlanningConsoleCommands(FakePlanner(clarification), FixedClock())
        self.assertIn("Necesito una aclaración", commands.handle("/plan lista archivos"))

        unsupported = RequestPlanningResult(
            RequestPlanningStatus.UNSUPPORTED,
            message="La solicitud no corresponde a una capacidad disponible.",
        )
        commands = PlanningConsoleCommands(FakePlanner(unsupported), FixedClock())
        result = commands.handle("/plan ejecuta un comando")
        self.assertIn("Todavía no puedo preparar un plan", result)
        self.assertNotIn("Paso 1", result)

    def test_planner_contract_errors_are_reported_without_claiming_success(self):
        planner = FakePlanner(error=ContractError("respuesta inválida"))
        commands = PlanningConsoleCommands(planner, FixedClock())
        result = commands.handle("/plan inspecciona demo")
        self.assertIn("No se pudo preparar el plan", result)
        self.assertNotIn("Plan preparado", result)


if __name__ == "__main__":
    unittest.main()
