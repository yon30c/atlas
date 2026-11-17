"""Domain contracts for owner-issued, non-transitive AGENT delegations."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json
import re

from atlas.core.errors import ContractError
from atlas.core.user_identity import validate_canonical_uuid4


_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{43}", re.ASCII)


def _required(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field_name} debe ser una cadena no vacía")


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


class AgentDelegationStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class AgentDelegationScope:
    """Explicit resource-ID and action subsets; wildcards are forbidden."""

    resource_type: str
    resource_ids: frozenset[str]
    actions: frozenset[str]

    def __post_init__(self) -> None:
        _required(self.resource_type, "resource_type")
        if not isinstance(self.resource_ids, frozenset) or not self.resource_ids:
            raise ContractError("resource_ids debe ser un frozenset no vacío")
        if not isinstance(self.actions, frozenset) or not self.actions:
            raise ContractError("actions debe ser un frozenset no vacío")
        for resource_id in self.resource_ids:
            _required(resource_id, "resource_id")
            if "*" in resource_id or "?" in resource_id:
                raise ContractError("No se permiten wildcards en resource_ids")
        for action in self.actions:
            _required(action, "action")
            if action == "*":
                raise ContractError("No se permiten acciones wildcard")


@dataclass(frozen=True, slots=True)
class AgentDelegation:
    """Canonical owner consent bounded by one exact CAM Grant revision."""

    delegation_id: str
    owner_user_id: str
    owner_identity_id: str
    agent_identity_id: str
    grant_id: str
    grant_revision: int
    project_id: str
    environment: str
    scope: AgentDelegationScope
    issuer_id: str
    issued_at: datetime
    not_before: datetime
    expires_at: datetime
    created_by_user_identity_id: str
    status: AgentDelegationStatus = AgentDelegationStatus.ACTIVE
    revision: int = 1
    revoked_at: datetime | None = None
    revoked_by_user_id: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "delegation_id", "owner_user_id", "owner_identity_id",
            "agent_identity_id", "issuer_id", "created_by_user_identity_id",
        ):
            validate_canonical_uuid4(getattr(self, name), name)
        if self.owner_identity_id == self.agent_identity_id:
            raise ContractError("owner y agent deben ser identidades distintas")
        if self.created_by_user_identity_id != self.owner_identity_id:
            raise ContractError("la delegación debe ser creada por la identidad del propietario")
        for name in ("grant_id", "project_id", "environment"):
            _required(getattr(self, name), name)
        _revision(self.grant_revision, "grant_revision")
        _revision(self.revision, "revision")
        if not isinstance(self.scope, AgentDelegationScope):
            raise ContractError("scope debe ser AgentDelegationScope")
        if not isinstance(self.status, AgentDelegationStatus):
            raise ContractError("status debe ser AgentDelegationStatus")
        for name in ("issued_at", "not_before", "expires_at"):
            _utc(getattr(self, name), name)
        if self.not_before < self.issued_at:
            raise ContractError("not_before no puede preceder issued_at")
        if self.expires_at <= self.not_before:
            raise ContractError("expires_at debe ser posterior a not_before")
        if self.revoked_at is not None:
            _utc(self.revoked_at, "revoked_at")
        if self.status is AgentDelegationStatus.ACTIVE:
            if self.revoked_at is not None or self.revoked_by_user_id is not None:
                raise ContractError("una delegación activa no puede tener datos de revocación")
        else:
            if self.revoked_at is None or self.revoked_by_user_id is None:
                raise ContractError("una delegación revocada requiere auditoría de revocación")
            validate_canonical_uuid4(self.revoked_by_user_id, "revoked_by_user_id")


@dataclass(frozen=True, slots=True, repr=False)
class VerifiedAgentDelegationContext:
    """Short-lived attested snapshot of owner consent; not CAM authorization."""

    context_id: str
    delegation_id: str
    delegation_revision: int
    owner_user_id: str
    owner_identity_id: str
    agent_identity_id: str
    grant_id: str
    grant_revision: int
    project_id: str
    environment: str
    scope: AgentDelegationScope
    issuer_id: str
    realm: str
    audience: str
    verified_at: datetime
    expires_at: datetime
    verification_ref: str = field(repr=False)
    attestation: str = field(repr=False)

    def __post_init__(self) -> None:
        for name in (
            "context_id", "delegation_id", "owner_user_id", "owner_identity_id",
            "agent_identity_id", "issuer_id",
        ):
            validate_canonical_uuid4(getattr(self, name), name)
        if self.owner_identity_id == self.agent_identity_id:
            raise ContractError("owner y agent deben ser identidades distintas")
        for name in ("grant_id", "project_id", "environment", "realm", "audience"):
            _required(getattr(self, name), name)
        for name in ("delegation_revision", "grant_revision"):
            _revision(getattr(self, name), name)
        if not isinstance(self.scope, AgentDelegationScope):
            raise ContractError("scope debe ser AgentDelegationScope")
        for name in ("verified_at", "expires_at"):
            _utc(getattr(self, name), name)
        if self.expires_at <= self.verified_at:
            raise ContractError("expires_at debe ser posterior a verified_at")
        for name in ("verification_ref", "attestation"):
            value = getattr(self, name)
            if not isinstance(value, str) or _TOKEN_RE.fullmatch(value) is None:
                raise ContractError(f"{name} debe ser una referencia opaca de 256 bits")

    def attestation_payload(self) -> bytes:
        claims = {
            "protocol": "atlas:verified-agent-delegation:v1",
            "context_id": self.context_id,
            "delegation_id": self.delegation_id,
            "delegation_revision": self.delegation_revision,
            "owner_user_id": self.owner_user_id,
            "owner_identity_id": self.owner_identity_id,
            "agent_identity_id": self.agent_identity_id,
            "grant_id": self.grant_id,
            "grant_revision": self.grant_revision,
            "project_id": self.project_id,
            "environment": self.environment,
            "resource_type": self.scope.resource_type,
            "resource_ids": sorted(self.scope.resource_ids),
            "actions": sorted(self.scope.actions),
            "issuer_id": self.issuer_id,
            "realm": self.realm,
            "audience": self.audience,
            "verified_at": self.verified_at.isoformat(timespec="microseconds"),
            "expires_at": self.expires_at.isoformat(timespec="microseconds"),
            "verification_ref": self.verification_ref,
        }
        return json.dumps(
            claims, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("ascii")

    def __repr__(self) -> str:
        return (
            "VerifiedAgentDelegationContext("
            f"context_id={self.context_id!r}, delegation_id={self.delegation_id!r}, "
            f"agent_identity_id={self.agent_identity_id!r}, grant_id={self.grant_id!r}, "
            "verification_ref=<redacted>, attestation=<redacted>)"
        )


def validate_agent_delegation_transition(
    current: AgentDelegation, updated: AgentDelegation
) -> None:
    """Reject illegal state transitions before a CAS persistence operation.

    This check must run against the canonical current row inside the same
    transaction/fencing boundary used by the authority. A value object alone
    cannot infer its history.
    """
    if not isinstance(current, AgentDelegation) or not isinstance(updated, AgentDelegation):
        raise ContractError("current y updated deben ser AgentDelegation")
    if current.delegation_id != updated.delegation_id:
        raise ContractError("no se puede cambiar delegation_id")
    if updated.revision != current.revision + 1:
        raise ContractError("la revisión debe avanzar exactamente en una unidad")
    if current.status is AgentDelegationStatus.REVOKED:
        if updated.status is not AgentDelegationStatus.REVOKED:
            raise ContractError("una delegación revocada no puede reactivarse")
        if (
            updated.revoked_at != current.revoked_at
            or updated.revoked_by_user_id != current.revoked_by_user_id
        ):
            raise ContractError("la auditoría de revocación es inmutable")
    if current.status is AgentDelegationStatus.ACTIVE and updated.status is AgentDelegationStatus.REVOKED:
        if updated.revoked_at is None or updated.revoked_by_user_id is None:
            raise ContractError("la revocación requiere auditoría completa")
