"""Comandos de consola para preparar planes de trabajo sin ejecutarlos."""

from atlas.adapters.ollama import OllamaError
from atlas.assistant.request_planner import (
    AssistantRequestPlanner,
    RequestPlanningStatus,
)
from atlas.core.errors import AtlasError
from atlas.ports.clock import Clock


class PlanningConsoleCommands:
    """Expone planificación explícita; nunca ejecuta capacidades."""

    def __init__(
        self,
        planner: AssistantRequestPlanner | None,
        clock: Clock,
    ) -> None:
        if planner is not None and not callable(getattr(planner, "process", None)):
            raise TypeError("planner debe implementar process(content, created_at)")
        if not callable(getattr(clock, "now", None)):
            raise TypeError("clock debe implementar now()")
        self._planner = planner
        self._clock = clock

    def handle(self, content: str) -> str | None:
        command, _, request = content.strip().partition(" ")
        if command.casefold() != "/plan":
            return None
        request = request.strip()
        if not request:
            return "Uso: /plan <descripción de lo que quieres hacer>"

        if self._planner is None:
            return "La planificación requiere Ollama; no está disponible en modo offline."

        try:
            result = self._planner.process(request, self._clock.now())
        except (OllamaError, AtlasError, ValueError) as exc:
            return f"No se pudo preparar el plan: {exc}"

        if result.status is RequestPlanningStatus.NEEDS_CLARIFICATION:
            return f"Necesito una aclaración antes de preparar el plan: {result.message}"
        if result.status is RequestPlanningStatus.UNSUPPORTED:
            return f"Todavía no puedo preparar un plan para esa solicitud: {result.message}"

        plan = result.plan
        lines = [
            "Plan preparado (solo vista previa; no se ejecutó ninguna operación).",
            f"Objetivo: {plan.goal}",
            f"Plan: {plan.plan_id}",
        ]
        for index, step in enumerate(plan.steps, start=1):
            lines.append(f"Paso {index}: {step.capability.value}")
            for name, value in step.parameters:
                lines.append(f"  {name}: {value}")
            lines.append(f"  Resultado esperado: {step.expected_result}")
        lines.append(
            "La ejecución de capacidades sigue deshabilitada hasta completar "
            "la autenticación confiable y la integración CAM."
        )
        return "\n".join(lines)
