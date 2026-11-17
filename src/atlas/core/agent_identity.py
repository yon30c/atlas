"""Canonical AGENT identity aggregate, deliberately separate from USER identity."""

from dataclasses import dataclass

from atlas.core.errors import ContractError
from atlas.core.identity import Identity, IdentityKind
from atlas.core.user_identity import validate_canonical_uuid4


@dataclass(frozen=True, slots=True)
class CanonicalAgentIdentity:
    """Canonical AGENT principal; it has no UserId and cannot represent a USER."""

    identity: Identity

    def __post_init__(self) -> None:
        if not isinstance(self.identity, Identity):
            raise ContractError("identity debe ser Identity")
        validate_canonical_uuid4(self.identity.identity_id, "identity_id")
        if self.identity.kind is not IdentityKind.AGENT:
            raise ContractError("la identidad canónica del agente debe ser AGENT")
