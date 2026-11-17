"""Ephemeral, attested evidence that a native AGENT identity was verified."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import re

from atlas.core.agent_identity import CanonicalAgentIdentity
from atlas.core.errors import ContractError
from atlas.core.identity import IdentityKind
from atlas.core.user_identity import validate_canonical_uuid4


_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{43}", re.ASCII)


def _revision(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractError(f"{field_name} debe ser un entero positivo")


def _utc(value: object, field_name: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ContractError(f"{field_name} debe ser datetime UTC")


@dataclass(frozen=True, slots=True, repr=False)
class VerifiedAgentIdentityContext:
    """Short-lived AGENT-only evidence; never a USER context or CAM grant."""

    context_id: str
    identity_id: str
    identity_type: IdentityKind
    identity_revision: int
    binding_id: str
    binding_revision: int
    issuer_id: str
    authenticated_at: datetime
    verified_at: datetime
    expires_at: datetime
    verification_ref: str = field(repr=False)
    attestation: str = field(repr=False)

    def __post_init__(self) -> None:
        for name in ("context_id", "identity_id", "binding_id", "issuer_id"):
            validate_canonical_uuid4(getattr(self, name), name)
        if self.identity_type is not IdentityKind.AGENT:
            raise ContractError(
                "VerifiedAgentIdentityContext solo admite Identity(AGENT)"
            )
        _revision(self.identity_revision, "identity_revision")
        _revision(self.binding_revision, "binding_revision")
        for name in ("authenticated_at", "verified_at", "expires_at"):
            _utc(getattr(self, name), name)
        if self.verified_at < self.authenticated_at:
            raise ContractError("verified_at no puede preceder authenticated_at")
        if self.expires_at <= self.verified_at:
            raise ContractError("expires_at debe ser posterior a verified_at")
        for name in ("verification_ref", "attestation"):
            value = getattr(self, name)
            if not isinstance(value, str) or _TOKEN_RE.fullmatch(value) is None:
                raise ContractError(f"{name} debe ser una referencia opaca de 256 bits")

    def attestation_payload(self) -> bytes:
        """Canonical AGENT-specific claims covered by the attestation."""
        claims = {
            "protocol": "atlas:verified-agent-identity:v1",
            "context_id": self.context_id,
            "identity_id": self.identity_id,
            "identity_type": self.identity_type.value,
            "identity_revision": self.identity_revision,
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
            "VerifiedAgentIdentityContext("
            f"context_id={self.context_id!r}, identity_id={self.identity_id!r}, "
            f"binding_id={self.binding_id!r}, issuer_id={self.issuer_id!r}, "
            "verification_ref=<redacted>, attestation=<redacted>)"
        )
