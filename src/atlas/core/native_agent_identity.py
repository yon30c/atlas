"""Native issuer binding for canonical AGENT identities; separate from USER bindings."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import re

from atlas.core.errors import ContractError
from atlas.core.user_identity import validate_canonical_uuid4


_SHA256_RE = re.compile(r"[0-9a-f]{64}", re.ASCII)


class NativeAgentIdentityBindingStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class NativeAgentIdentityBinding:
    """Immutable issuer/subject association to one canonical AGENT identity."""

    binding_id: str
    identity_id: str
    issuer_id: str
    subject_digest: str
    status: NativeAgentIdentityBindingStatus
    created_at: datetime
    verified_at: datetime
    revision: int = 1
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("binding_id", "identity_id", "issuer_id"):
            validate_canonical_uuid4(getattr(self, name), name)
        if not isinstance(self.subject_digest, str) or _SHA256_RE.fullmatch(self.subject_digest) is None:
            raise ContractError("subject_digest debe ser SHA-256 lowercase")
        if not isinstance(self.status, NativeAgentIdentityBindingStatus):
            raise ContractError("status debe ser NativeAgentIdentityBindingStatus")
        for name in ("revision",):
            if isinstance(getattr(self, name), bool) or not isinstance(getattr(self, name), int) or getattr(self, name) < 1:
                raise ContractError(f"{name} debe ser un entero positivo")
        for name in ("created_at", "verified_at"):
            value = getattr(self, name)
            if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
                raise ContractError(f"{name} debe ser datetime UTC")
        if self.verified_at < self.created_at:
            raise ContractError("verified_at no puede preceder created_at")
        if self.revoked_at is not None:
            if not isinstance(self.revoked_at, datetime) or self.revoked_at.tzinfo is None or self.revoked_at.utcoffset() != timedelta(0):
                raise ContractError("revoked_at debe ser datetime UTC")
            if self.revoked_at < self.created_at:
                raise ContractError("revoked_at no puede preceder created_at")
        if self.status is NativeAgentIdentityBindingStatus.ACTIVE and self.revoked_at is not None:
            raise ContractError("un binding activo no puede tener revoked_at")
        if self.status is NativeAgentIdentityBindingStatus.REVOKED and self.revoked_at is None:
            raise ContractError("un binding revocado requiere revoked_at")
