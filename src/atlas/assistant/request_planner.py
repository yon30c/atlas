"""Orquestación de interpretación y planificación de solicitudes."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from atlas.assistant.planning import (
    AssistantPlan,
    IntentInterpretation,
    InterpretationStatus,
)
from atlas.assistant.planning_service import AssistantPlanningService
from atlas.core.errors import ContractError
from atlas.ports.intent_interpreter import IntentInterpreter


class RequestPlanningStatus(str, Enum):
    """Estado observable del procesamiento de una solicitud."""

    PLANNED = "planned"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class RequestPlanningResult:
    """Resultado de planificación; nunca representa ejecución."""

    status: RequestPlanningStatus
    plan: AssistantPlan | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, RequestPlanningStatus):
            raise ContractError("status debe ser RequestPlanningStatus")
        if self.status is RequestPlanningStatus.PLANNED:
            if not isinstance(self.plan, AssistantPlan) or self.message is not None:
                raise ContractError("PLANNED requiere plan y no admite message")
        else:
            if self.plan is not None:
                raise ContractError("un resultado sin plan no puede incluir plan")
            if not isinstance(self.message, str) or not self.message.strip():
                raise ContractError("el resultado requiere un mensaje no vacío")


class AssistantRequestPlanner:
    """Coordina interpretación y planificación sin ejecutar capacidades."""

    def __init__(
        self,
        interpreter: IntentInterpreter,
        planning_service: AssistantPlanningService | None = None,
    ) -> None:
        if not callable(getattr(interpreter, "interpret", None)):
            raise ContractError("interpreter debe implementar interpret(content)")
        self._interpreter = interpreter
        self._planning_service = planning_service or AssistantPlanningService()

    def process(
        self,
        content: str,
        created_at: datetime,
    ) -> RequestPlanningResult:
        """Interpreta una solicitud y devuelve un plan o un resultado no planificable."""
        if not isinstance(content, str) or not content.strip():
            raise ContractError("content debe ser una cadena no vacía")

        interpretation = self._interpreter.interpret(content.strip())
        if not isinstance(interpretation, IntentInterpretation):
            raise ContractError("interpreter debe devolver IntentInterpretation")

        if interpretation.status is InterpretationStatus.NEEDS_CLARIFICATION:
            return RequestPlanningResult(
                RequestPlanningStatus.NEEDS_CLARIFICATION,
                message=interpretation.message,
            )
        if interpretation.status is InterpretationStatus.UNSUPPORTED:
            return RequestPlanningResult(
                RequestPlanningStatus.UNSUPPORTED,
                message=interpretation.message,
            )

        planned = self._planning_service.plan(interpretation, created_at)
        if not isinstance(planned, AssistantPlan):
            raise ContractError("la planificación READY no produjo AssistantPlan")
        return RequestPlanningResult(
            RequestPlanningStatus.PLANNED,
            plan=planned,
        )
