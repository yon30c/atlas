"""Resultado neutral de autorización para operaciones del Memory Engine."""
from dataclasses import dataclass
from enum import Enum

from atlas.memory.consistency import AuthorizationSnapshot
from atlas.memory.errors import MemoryContractError


class MemoryAuthorizationDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class MemoryAuthorizationResult:
    """ALLOW solo se representa junto a un snapshot exacto emitido por CAM."""

    decision: MemoryAuthorizationDecision
    snapshot: AuthorizationSnapshot | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, MemoryAuthorizationDecision):
            raise MemoryContractError("decision debe ser MemoryAuthorizationDecision")
        if self.decision is MemoryAuthorizationDecision.ALLOW:
            if not isinstance(self.snapshot, AuthorizationSnapshot):
                raise MemoryContractError("ALLOW requiere AuthorizationSnapshot")
        elif self.snapshot is not None:
            raise MemoryContractError("DENY no puede incluir snapshot")
