"""Modelos de eventos y respuestas del asistente."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping
from uuid import UUID

from atlas.core.context import OperationContext
from atlas.core.errors import ContractError
from atlas.core.identity import _required


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
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ContractError("occurred_at debe incluir zona horaria")
        if self.occurred_at.utcoffset() != timezone.utc.utcoffset(self.occurred_at):
            raise ContractError("occurred_at debe estar en UTC")
        if not isinstance(self.context, OperationContext):
            raise ContractError("context debe ser OperationContext")
        if not isinstance(self.attributes, Mapping) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in self.attributes.items()):
            raise ContractError("attributes debe mapear cadenas a cadenas")