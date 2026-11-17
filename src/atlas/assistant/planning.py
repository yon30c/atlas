"""Contratos de intención y planificación para los primeros flujos funcionales."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from atlas.core.errors import ContractError


class IntentKind(str, Enum):
    """Capacidades de producto admitidas por el primer flujo vertical."""

    WORKSPACE_LIST = "workspace.list"
    WORKSPACE_READ = "workspace.read"


class InterpretationStatus(str, Enum):
    """Resultado de interpretar una solicitud del propietario."""

    READY = "ready"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"


def _required_text(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacía")


def _validate_parameters(parameters: tuple[tuple[str, str], ...]) -> None:
    if not isinstance(parameters, tuple):
        raise ContractError("parameters debe ser una tupla inmutable")
    seen = set()
    for item in parameters:
        if (
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not item[0].strip()
            or not isinstance(item[1], str)
            or not item[1].strip()
        ):
            raise ContractError("cada parámetro debe ser un par (nombre, valor) no vacío")
        if item[0] in seen:
            raise ContractError("no se permiten nombres de parámetros duplicados")
        seen.add(item[0])


@dataclass(frozen=True, slots=True)
class AssistantIntent:
    """Intención tipada propuesta para evaluación por la aplicación."""

    kind: IntentKind
    parameters: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, IntentKind):
            raise ContractError("kind debe ser IntentKind")
        _validate_parameters(self.parameters)
        allowed = {
            IntentKind.WORKSPACE_LIST: {"workspace_id"},
            IntentKind.WORKSPACE_READ: {"workspace_id", "path"},
        }[self.kind]
        names = {name for name, _ in self.parameters}
        if not names.issubset(allowed):
            raise ContractError("la intención contiene parámetros desconocidos")
        if "workspace_id" not in names:
            raise ContractError("workspace_id es obligatorio")
        if self.kind is IntentKind.WORKSPACE_READ and "path" not in names:
            raise ContractError("path es obligatorio para workspace.read")


@dataclass(frozen=True, slots=True)
class IntentInterpretation:
    """Resultado de interpretación: intención lista, aclaración o no soportada."""

    status: InterpretationStatus
    intent: AssistantIntent | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, InterpretationStatus):
            raise ContractError("status debe ser InterpretationStatus")
        if self.status is InterpretationStatus.READY:
            if not isinstance(self.intent, AssistantIntent) or self.message is not None:
                raise ContractError("READY requiere intent y no admite message")
        elif self.status is InterpretationStatus.NEEDS_CLARIFICATION:
            if self.intent is not None:
                raise ContractError("NEEDS_CLARIFICATION no puede incluir intent")
            _required_text(self.message, "message")
        else:
            if self.intent is not None:
                raise ContractError("UNSUPPORTED no puede incluir intent")
            _required_text(self.message, "message")


@dataclass(frozen=True, slots=True)
class PlanStep:
    """Paso declarativo de un plan; no ejecuta la capacidad."""

    step_id: str
    capability: IntentKind
    parameters: tuple[tuple[str, str], ...]
    expected_result: str

    def __post_init__(self) -> None:
        _required_text(self.step_id, "step_id")
        if not isinstance(self.capability, IntentKind):
            raise ContractError("capability debe ser IntentKind")
        _validate_parameters(self.parameters)
        _required_text(self.expected_result, "expected_result")
        names = {name for name, _ in self.parameters}
        if "workspace_id" not in names:
            raise ContractError("el paso requiere workspace_id")
        if self.capability is IntentKind.WORKSPACE_READ and "path" not in names:
            raise ContractError("workspace.read requiere path")
        allowed = {
            IntentKind.WORKSPACE_LIST: {"workspace_id"},
            IntentKind.WORKSPACE_READ: {"workspace_id", "path"},
        }[self.capability]
        if not names.issubset(allowed):
            raise ContractError("el paso contiene parámetros desconocidos")


@dataclass(frozen=True, slots=True)
class AssistantPlan:
    """Plan validado y listo para revisión; no equivale a ejecución."""

    plan_id: str
    goal: str
    intent: AssistantIntent
    steps: tuple[PlanStep, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        _required_text(self.plan_id, "plan_id")
        _required_text(self.goal, "goal")
        if not isinstance(self.intent, AssistantIntent):
            raise ContractError("intent debe ser AssistantIntent")
        if (
            not isinstance(self.steps, tuple)
            or not self.steps
            or any(not isinstance(step, PlanStep) for step in self.steps)
        ):
            raise ContractError("steps debe ser una tupla no vacía de PlanStep")
        if any(step.capability is not self.intent.kind for step in self.steps):
            raise ContractError("los pasos deben corresponder a la intención del plan")
        if not isinstance(self.created_at, datetime):
            raise ContractError("created_at debe ser datetime")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() != timezone.utc.utcoffset(self.created_at):
            raise ContractError("created_at debe estar en UTC")

    @classmethod
    def create(
        cls,
        goal: str,
        intent: AssistantIntent,
        steps: tuple[PlanStep, ...],
        created_at: datetime,
    ) -> "AssistantPlan":
        """Crea un plan nuevo con identificador generado localmente."""
        return cls(
            plan_id=str(uuid4()),
            goal=goal,
            intent=intent,
            steps=steps,
            created_at=created_at,
        )
