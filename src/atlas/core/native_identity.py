"""Canonical native issuer and Identity(USER) binding domain contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import re
from uuid import UUID

from atlas.core.errors import ContractError


_SHA256_RE = re.compile(r"[0-9a-f]{64}", re.ASCII)
_REALM_RE = re.compile(r"[a-z0-9][a-z0-9._-]{1,63}", re.ASCII)


def _uuid4(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{field_name} debe ser UUIDv4 canónico")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise ContractError(f"{field_name} debe ser UUIDv4 canónico") from None
    if parsed.version != 4 or str(parsed) != value:
        raise ContractError(f"{field_name} debe ser UUIDv4 canónico lowercase")
    return value


def _revision(value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractError("revision debe ser un entero positivo")


def _utc(value: object, field_name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ContractError(f"{field_name} debe ser datetime con zona horaria")
    offset = value.utcoffset()
    if offset is None or offset != timedelta(0):
        raise ContractError(f"{field_name} debe estar en UTC")


class NativeIssuerProfile(str, Enum):
    NATIVE_AUTHORITY_PROOF = "NATIVE_AUTHORITY_PROOF"


class NativeIssuerStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class NativeIdentityBindingStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


@dataclass(frozen=True, slots=True)
class NativeIdentityIssuer:
    """Identity Authority-owned issuer identity for one stable logical realm."""

    issuer_id: str
    realm: str
    profile: NativeIssuerProfile
    status: NativeIssuerStatus
    revision: int = 1

    def __post_init__(self) -> None:
        _uuid4(self.issuer_id, "issuer_id")
        if not isinstance(self.realm, str) or _REALM_RE.fullmatch(self.realm) is None:
            raise ContractError("realm debe ser un identificador lowercase estable")
        if not isinstance(self.profile, NativeIssuerProfile):
            raise ContractError("profile debe ser NativeIssuerProfile")
        if self.profile is not NativeIssuerProfile.NATIVE_AUTHORITY_PROOF:
            raise ContractError("perfil de issuer nativo no admitido")
        if not isinstance(self.status, NativeIssuerStatus):
            raise ContractError("status debe ser NativeIssuerStatus")
        _revision(self.revision)


@dataclass(frozen=True, slots=True)
class NativeIdentityBinding:
    """Immutable issuer/subject association to one canonical Identity(USER)."""

    binding_id: str
    identity_id: str
    issuer_id: str
    subject_digest: str
    status: NativeIdentityBindingStatus
    created_at: datetime
    verified_at: datetime
    revision: int = 1
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        _uuid4(self.binding_id, "binding_id")
        _uuid4(self.identity_id, "identity_id")
        _uuid4(self.issuer_id, "issuer_id")
        if not isinstance(self.subject_digest, str) or _SHA256_RE.fullmatch(self.subject_digest) is None:
            raise ContractError("subject_digest debe ser SHA-256 lowercase")
        if not isinstance(self.status, NativeIdentityBindingStatus):
            raise ContractError("status debe ser NativeIdentityBindingStatus")
        _revision(self.revision)
        _utc(self.created_at, "created_at")
        _utc(self.verified_at, "verified_at")
        if self.verified_at < self.created_at:
            raise ContractError("verified_at no puede preceder created_at")
        if self.revoked_at is not None:
            _utc(self.revoked_at, "revoked_at")
            if self.revoked_at < self.created_at:
                raise ContractError("revoked_at no puede preceder created_at")
        if self.status is NativeIdentityBindingStatus.ACTIVE and self.revoked_at is not None:
            raise ContractError("un binding activo no puede tener revoked_at")
        if self.status is NativeIdentityBindingStatus.REVOKED and self.revoked_at is None:
            raise ContractError("un binding revocado requiere revoked_at")
