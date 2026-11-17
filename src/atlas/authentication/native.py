"""Native authentication domain contracts; persistence is intentionally separate."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import re
import secrets
from uuid import UUID

from atlas.authentication.credentials import LoginHandle
from atlas.core.errors import ContractError


_OPAQUE_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{43}", re.ASCII)
_SHA256_RE = re.compile(r"[0-9a-f]{64}", re.ASCII)
_AUDIENCE_RE = re.compile(r"[a-z][a-z0-9._:-]{0,127}", re.ASCII)


class NativeAuthenticatorStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class NativeAuthenticationProofStatus(str, Enum):
    PENDING = "PENDING"
    CONSUMED = "CONSUMED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


def _uuid4(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{field_name} debe ser un UUIDv4 canónico")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise ContractError(f"{field_name} debe ser un UUIDv4 canónico") from None
    if parsed.version != 4 or str(parsed) != value:
        raise ContractError(f"{field_name} debe ser un UUIDv4 canónico lowercase")
    return value


def _positive_revision(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractError(f"{field_name} debe ser un entero positivo")


def _utc(value: object, field_name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ContractError(f"{field_name} debe ser un datetime con zona horaria")
    offset = value.utcoffset()
    if offset is None or offset != timedelta(0):
        raise ContractError(f"{field_name} debe estar en UTC")


def _validate_random_token(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _OPAQUE_TOKEN_RE.fullmatch(value) is None:
        raise ContractError(f"{field_name} debe ser una referencia opaca de 256 bits")
    try:
        decoded = base64.urlsafe_b64decode(value + "=")
    except (ValueError, base64.binascii.Error):
        raise ContractError(f"{field_name} no tiene codificación base64url válida") from None
    if len(decoded) != 32 or base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") != value:
        raise ContractError(f"{field_name} no representa exactamente 256 bits")
    return value


@dataclass(frozen=True, slots=True, repr=False)
class NativeSubject:
    """Random, issuer-scoped subject; never a login handle or canonical user ID."""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        _validate_random_token(self.value, "native_subject")

    @classmethod
    def generate(cls) -> NativeSubject:
        return cls(secrets.token_urlsafe(32))

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.value.encode("ascii")).hexdigest()

    def __repr__(self) -> str:
        return "NativeSubject(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class NativeProofReference:
    """One-shot proof handle; only its digest belongs in durable storage."""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        _validate_random_token(self.value, "proof_reference")

    @classmethod
    def generate(cls) -> NativeProofReference:
        return cls(secrets.token_urlsafe(32))

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.value.encode("ascii")).hexdigest()

    def __repr__(self) -> str:
        return "NativeProofReference(<redacted>)"


@dataclass(frozen=True, slots=True)
class NativeAuthenticator:
    """Authentication-owned credential aggregate; never carries identity or grants."""

    authenticator_id: str
    issuer_id: str
    native_subject: NativeSubject
    login_handle: LoginHandle
    password_hash_phc: str = field(repr=False)
    credential_revision: int = 1
    status: NativeAuthenticatorStatus = NativeAuthenticatorStatus.ACTIVE

    def __post_init__(self) -> None:
        _uuid4(self.authenticator_id, "authenticator_id")
        _uuid4(self.issuer_id, "issuer_id")
        if not isinstance(self.native_subject, NativeSubject):
            raise ContractError("native_subject debe ser NativeSubject")
        if not isinstance(self.login_handle, LoginHandle):
            raise ContractError("login_handle debe ser LoginHandle")
        if (
            not isinstance(self.password_hash_phc, str)
            or not self.password_hash_phc.startswith("$argon2id$v=19$")
        ):
            raise ContractError("password_hash_phc debe ser un PHC Argon2id válido")
        _positive_revision(self.credential_revision, "credential_revision")
        if not isinstance(self.status, NativeAuthenticatorStatus):
            raise ContractError("status debe ser NativeAuthenticatorStatus")


@dataclass(frozen=True, slots=True)
class NativeAuthenticationProof:
    """Durable proof metadata; the raw reference is never part of this record."""

    proof_id: str
    reference_digest: str
    issuer_id: str
    native_subject: NativeSubject
    authenticator_id: str
    credential_revision: int
    authenticated_at: datetime
    expires_at: datetime
    audience: str
    status: NativeAuthenticationProofStatus = NativeAuthenticationProofStatus.PENDING

    def __post_init__(self) -> None:
        _uuid4(self.proof_id, "proof_id")
        _uuid4(self.issuer_id, "issuer_id")
        _uuid4(self.authenticator_id, "authenticator_id")
        if not isinstance(self.reference_digest, str) or _SHA256_RE.fullmatch(self.reference_digest) is None:
            raise ContractError("reference_digest debe ser SHA-256 lowercase")
        if not isinstance(self.native_subject, NativeSubject):
            raise ContractError("native_subject debe ser NativeSubject")
        _positive_revision(self.credential_revision, "credential_revision")
        _utc(self.authenticated_at, "authenticated_at")
        _utc(self.expires_at, "expires_at")
        if self.expires_at <= self.authenticated_at:
            raise ContractError("expires_at debe ser posterior a authenticated_at")
        if not isinstance(self.audience, str) or _AUDIENCE_RE.fullmatch(self.audience) is None:
            raise ContractError("audience debe ser un identificador interno explícito")
        if not isinstance(self.status, NativeAuthenticationProofStatus):
            raise ContractError("status debe ser NativeAuthenticationProofStatus")
