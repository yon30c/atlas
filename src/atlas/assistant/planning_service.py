"""Servicio de aplicación para convertir intenciones listas en planes declarativos."""

from datetime import datetime

from atlas.assistant.planning import (
    AssistantPlan,
    IntentInterpretation,
    IntentKind,
    InterpretationStatus,
    PlanStep,
)
from atlas.core.errors import ContractError


class AssistantPlanningService:
    """Construye planes de un solo paso; nunca ejecuta capacidades."""

    def plan(
        self,
        interpretation: IntentInterpretation,
        created_at: datetime,
    ) -> AssistantPlan | IntentInterpretation:
        """Devuelve un plan para READY o conserva la aclaración/rechazo original."""
        if not isinstance(interpretation, IntentInterpretation):
            raise ContractError("interpretation debe ser IntentInterpretation")

        if interpretation.status is not InterpretationStatus.READY:
            return interpretation

        intent = interpretation.intent
        parameters = intent.parameters
        values = dict(parameters)
        workspace_id = values["workspace_id"]

        if intent.kind is IntentKind.WORKSPACE_LIST:
            goal = f"Listar archivos del workspace '{workspace_id}'"
            expected_result = (
                f"Listado de entradas del workspace '{workspace_id}'"
            )
        else:
            path = values["path"]
            goal = f"Leer el archivo '{path}' del workspace '{workspace_id}'"
            expected_result = (
                f"Contenido del archivo '{path}' del workspace '{workspace_id}'"
            )

        step = PlanStep(
            step_id="step-1",
            capability=intent.kind,
            parameters=parameters,
            expected_result=expected_result,
        )
        return AssistantPlan.create(
            goal=goal,
            intent=intent,
            steps=(step,),
            created_at=created_at,
        )
