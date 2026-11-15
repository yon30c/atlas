"""Modelo canónico de usuario interno de Atlas."""
from dataclasses import dataclass
from uuid import UUID

from atlas.core.errors import ContractError
from atlas.core.identity import Identity, IdentityKind


def validate_canonical_uuid4(value: str, field: str) -> str:
    """Require a lowercase, hyphenated canonical UUIDv4 without normalization."""
    if not isinstance(value, str):
        raise ContractError(f"{field} debe ser UUIDv4 canónico")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ContractError(f"{field} debe ser UUIDv4 canónico") from exc
    if str(parsed) != value or parsed.version != 4:
        raise ContractError(f"{field} debe ser UUIDv4 canónico")
    return value


@dataclass(frozen=True, slots=True)
class CanonicalUserIdentity:
    """Canonical Atlas UserId paired with its internal USER identity."""

    user_id: str
    identity: Identity

    def __post_init__(self) -> None:
        validate_canonical_uuid4(self.user_id, "user_id")
        if not isinstance(self.identity, Identity):
            raise ContractError("identity debe ser Identity")
        validate_canonical_uuid4(self.identity.identity_id, "identity_id")
        if self.identity.kind is not IdentityKind.USER:
            raise ContractError("la identidad canónica del usuario debe ser USER")
