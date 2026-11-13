"""Identidades del dominio Atlas."""
from dataclasses import dataclass
from enum import Enum

from atlas.core.errors import ContractError


class IdentityKind(str, Enum):
    USER = "user"
    AGENT = "agent"
    SERVICE = "service"
    WATCHER = "watcher"
    SYSTEM = "system"


class IdentityStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


def _required(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacia")
    return value


@dataclass(frozen=True, slots=True)
class Identity:
    identity_id: str
    kind: IdentityKind
    status: IdentityStatus
    revision: int = 1

    def __post_init__(self) -> None:
        _required(self.identity_id, "identity_id")

        if not isinstance(self.kind, IdentityKind):
            raise ContractError("kind debe ser un IdentityKind valido")

        if not isinstance(self.status, IdentityStatus):
            raise ContractError("status debe ser un IdentityStatus valido")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise ContractError("revision debe ser un entero positivo")