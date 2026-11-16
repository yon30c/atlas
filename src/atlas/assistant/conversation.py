"""Modelos de dominio para la administración de conversaciones Atlas."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from atlas.core.errors import ContractError


class ConversationStatus(str, Enum):
    """Estados del ciclo de vida de una conversación."""

    ACTIVE = "active"
    CLOSED = "closed"


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacía")


def _require_utc(value: datetime, field: str) -> None:
    if not isinstance(value, datetime):
        raise ContractError(f"{field} debe ser datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ContractError(f"{field} debe incluir zona horaria")
    if value.utcoffset() != timezone.utc.utcoffset(value):
        raise ContractError(f"{field} debe estar en UTC")


@dataclass(frozen=True, slots=True)
class Conversation:
    """Identidad y metadatos de una conversación, independientes del proveedor."""

    conversation_id: str
    title: str
    status: ConversationStatus
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_text(self.conversation_id, "conversation_id")
        _require_text(self.title, "title")

        if not isinstance(self.status, ConversationStatus):
            raise ContractError("status debe ser ConversationStatus")

        _require_utc(self.created_at, "created_at")
        _require_utc(self.updated_at, "updated_at")

        if self.updated_at < self.created_at:
            raise ContractError("updated_at no puede ser anterior a created_at")

        if self.last_message_at is not None:
            _require_utc(self.last_message_at, "last_message_at")
            if self.last_message_at < self.created_at:
                raise ContractError(
                    "last_message_at no puede ser anterior a created_at"
                )
            if self.last_message_at > self.updated_at:
                raise ContractError(
                    "last_message_at no puede ser posterior a updated_at"
                )
