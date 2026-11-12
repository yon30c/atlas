"""Modelos mínimos de memoria."""
from dataclasses import dataclass
from datetime import datetime, timezone

from atlas.core.context import OperationContext
from atlas.core.enums import MemoryStatus
from atlas.core.errors import ContractError
from atlas.core.identity import _required


def _aware_utc(value: datetime, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ContractError(f"{field} debe incluir zona horaria")
    if value.utcoffset() != timezone.utc.utcoffset(value):
        raise ContractError(f"{field} debe estar en UTC")


@dataclass(frozen=True, slots=True)
class Memory:
    memory_id: str
    owner_id: str
    content: str
    status: MemoryStatus
    created_at: datetime

    def __post_init__(self) -> None:
        for name in ("memory_id", "owner_id", "content"):
            _required(getattr(self, name), name)
        if not isinstance(self.status, MemoryStatus):
            raise ContractError("status debe ser MemoryStatus")
        _aware_utc(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class MemoryProposal:
    owner_id: str
    content: str
    context: OperationContext

    def __post_init__(self) -> None:
        _required(self.owner_id, "owner_id")
        _required(self.content, "content")
        if not isinstance(self.context, OperationContext):
            raise ContractError("context debe ser OperationContext")
        if self.owner_id != self.context.user_id:
            raise ContractError("owner_id debe coincidir con el usuario del contexto")