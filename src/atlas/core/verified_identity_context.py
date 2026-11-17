"""Ephemeral, attested evidence that a native USER identity was verified."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import re
from uuid import UUID

from atlas.core.errors import ContractError
from atlas.core.identity import IdentityKind


_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{43}", re.ASCII)


def _uuid4(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise ContractError(f"{field_name} debe ser UUIDv4 canónico")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise ContractError(f"{field_name} debe ser UUIDv4 canónico") from None
    if parsed.version != 4 or str(parsed) != value:
        raise ContractError(f"{field_name} debe ser UUIDv4 canónico lowercase")


def _utc(value: object, field_name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ContractError(f"{field_name} debe ser datetime UTC")
    if value.utcoffset() != timedelta(0):
        raise ContractError(f"{field_name} debe ser datetime UTC")


@dataclass(frozen=True, slots=True, repr=False)
class VerifiedIdentityContext:
    """Short-lived USER identity evidence; never a credential or CAM grant."""

    context_id: str
    identity_id: str
    identity_type: IdentityKind
    identity_revision: int
    user_id: str
    binding_id: str
    binding_revision: int
    issuer_id: str
    authenticated_at: datetime
    verified_at: datetime
    expires_at: datetime
    verification_ref: str = field(repr=False)
    attestation: str = field(repr=False)

    def __post_init__(self) -> None:
        for name in ("context_id", "identity_id", "user_id", "binding_id", "issuer_id"):
            _uuid4(getattr(self, name), name)
        if self.identity_type is not IdentityKind.USER:
            raise ContractError("VerifiedIdentityContext solo admite Identity(USER)")
        for name in ("identity_revision", "binding_revision"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ContractError(f"{name} debe ser entero positivo")
        for name in ("authenticated_at", "verified_at", "expires_at"):
            _utc(getattr(self, name), name)
        if self.verified_at < self.authenticated_at:
            raise ContractError("verified_at no puede preceder authenticated_at")
        if self.expires_at <= self.verified_at:
            raise ContractError("expires_at debe ser posterior a verified_at")
        for name in ("verification_ref", "attestation"):
            if not isinstance(getattr(self, name), str) or _TOKEN_RE.fullmatch(getattr(self, name)) is None:
                raise ContractError(f"{name} debe ser una referencia opaca de 256 bits")

    def attestation_payload(self) -> bytes:
        """Canonical claims covered by the process-independent HMAC attestation."""
        claims = {
            "context_id": self.context_id,
            "identity_id": self.identity_id,
            "identity_type": self.identity_type.value,
            "identity_revision": self.identity_revision,
            "user_id": self.user_id,
            "binding_id": self.binding_id,
            "binding_revision": self.binding_revision,
            "issuer_id": self.issuer_id,
            "authenticated_at": self.authenticated_at.isoformat(timespec="microseconds"),
            "verified_at": self.verified_at.isoformat(timespec="microseconds"),
            "expires_at": self.expires_at.isoformat(timespec="microseconds"),
            "verification_ref": self.verification_ref,
        }
        return json.dumps(
            claims, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("ascii")

    def __repr__(self) -> str:
        return (
            "VerifiedIdentityContext("
            f"context_id={self.context_id!r}, identity_id={self.identity_id!r}, "
            f"user_id={self.user_id!r}, binding_id={self.binding_id!r}, "
            "verification_ref=<redacted>, attestation=<redacted>)"
        )
