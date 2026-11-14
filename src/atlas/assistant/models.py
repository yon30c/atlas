"""Modelos de interacción conversacional del asistente Atlas."""
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping
from uuid import UUID

from atlas.core.context import OperationContext
from atlas.core.errors import ContractError
from atlas.core.identity import _required


class AssistantResponseKind(str, Enum):
    """Clasificación informativa de una respuesta; no representa autorización."""

    INFORMATIONAL = "informational"
    CLARIFICATION = "clarification"
    PROPOSAL = "proposal"
    PLAN = "plan"
    APPROVAL_REQUIRED = "approval_required"
    RESULT = "result"
    PARTIAL_RESULT = "partial_result"
    ERROR = "error"


class ConversationMessageRole(str, Enum):
    """Roles permitidos en el historial de una conversación."""

    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    """Mensaje histórico neutral respecto al proveedor LLM."""

    role: ConversationMessageRole
    content: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, ConversationMessageRole):
            raise ContractError("role debe ser ConversationMessageRole")
        _required(self.content, "content")


def _require_utc(value: datetime, field: str) -> None:
    if not isinstance(value, datetime):
        raise ContractError(f"{field} debe ser datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ContractError(f"{field} debe incluir zona horaria")
    if value.utcoffset() != timezone.utc.utcoffset(value):
        raise ContractError(f"{field} debe estar en UTC")


@dataclass(frozen=True, slots=True)
class AssistantRequest:
    """Solicitud conversacional vinculada a un contexto operativo explícito."""

    request_id: str
    context: OperationContext
    content: str
    received_at: datetime
    conversation_id: str | None = None
    attachments: tuple[str, ...] = ()
    history: tuple[ConversationMessage, ...] = ()

    def __post_init__(self) -> None:
        _required(self.request_id, "request_id")
        if not isinstance(self.context, OperationContext):
            raise ContractError("context debe ser OperationContext")
        if self.request_id != self.context.request_id:
            raise ContractError("request_id debe coincidir con context.request_id")
        _required(self.content, "content")
        _require_utc(self.received_at, "received_at")

        if self.conversation_id is not None:
            _required(self.conversation_id, "conversation_id")

        if not isinstance(self.attachments, tuple) or any(
            not isinstance(item, str) or not item.strip()
            for item in self.attachments
        ):
            raise ContractError("attachments debe ser una tupla de referencias no vacias")

        if not isinstance(self.history, tuple) or any(
            not isinstance(item, ConversationMessage) for item in self.history
        ):
            raise ContractError("history debe ser una tupla de ConversationMessage")


@dataclass(frozen=True, slots=True)
class AssistantResponse:
    """Respuesta conversacional; su tipo no acredita ejecución ni autorización."""

    request_id: str
    context: OperationContext
    kind: AssistantResponseKind
    content: str
    created_at: datetime

    def __post_init__(self) -> None:
        _required(self.request_id, "request_id")
        if not isinstance(self.context, OperationContext):
            raise ContractError("context debe ser OperationContext")
        if self.request_id != self.context.request_id:
            raise ContractError("request_id debe coincidir con context.request_id")
        if not isinstance(self.kind, AssistantResponseKind):
            raise ContractError("kind debe ser AssistantResponseKind")
        _required(self.content, "content")
        _require_utc(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class DomainEvent:
    event_id: UUID
    event_type: str
    occurred_at: datetime
    context: OperationContext
    attributes: Mapping[str, str]

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, UUID):
            raise ContractError("event_id debe ser UUID")
        _required(self.event_type, "event_type")
        _require_utc(self.occurred_at, "occurred_at")
        if not isinstance(self.context, OperationContext):
            raise ContractError("context debe ser OperationContext")
        if not isinstance(self.attributes, Mapping) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in self.attributes.items()):
            raise ContractError("attributes debe mapear cadenas a cadenas")
