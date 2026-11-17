"""Immutable trust policy for multi-authority recovery evidence issuers."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from atlas.core.errors import ContractError
from atlas.memory.authority_changes import (
    MultiAuthorityRecoveryEvidence,
    MultiAuthorityRecoveryEvidenceKind,
)


def _required(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacía")


def _utc(value: object, field: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ContractError(f"{field} debe ser un datetime UTC")


@dataclass(frozen=True, slots=True)
class RecoveryEvidenceIssuerTrustPolicy:
    """Allowlist policy; it does not authenticate signatures or payloads."""

    issuer_id: str
    policy_revision: int
    enabled: bool
    allowed_evidence_kinds: tuple[MultiAuthorityRecoveryEvidenceKind, ...]
    valid_from: datetime
    valid_until: datetime | None
    max_evidence_lifetime_seconds: int

    def __post_init__(self) -> None:
        _required(self.issuer_id, "issuer_id")
        if (
            isinstance(self.policy_revision, bool)
            or not isinstance(self.policy_revision, int)
            or self.policy_revision < 1
        ):
            raise ContractError("policy_revision debe ser un entero positivo")
        if not isinstance(self.enabled, bool):
            raise ContractError("enabled debe ser bool")
        if (
            not isinstance(self.allowed_evidence_kinds, tuple)
            or not self.allowed_evidence_kinds
            or any(
                not isinstance(kind, MultiAuthorityRecoveryEvidenceKind)
                for kind in self.allowed_evidence_kinds
            )
        ):
            raise ContractError("allowed_evidence_kinds debe ser una tupla no vacía de tipos válidos")
        if len(set(self.allowed_evidence_kinds)) != len(self.allowed_evidence_kinds):
            raise ContractError("allowed_evidence_kinds no puede contener duplicados")
        object.__setattr__(
            self,
            "allowed_evidence_kinds",
            tuple(sorted(self.allowed_evidence_kinds, key=lambda kind: kind.value)),
        )
        _utc(self.valid_from, "valid_from")
        if self.valid_until is not None:
            _utc(self.valid_until, "valid_until")
            if self.valid_until <= self.valid_from:
                raise ContractError("valid_until debe ser posterior a valid_from")
        if (
            isinstance(self.max_evidence_lifetime_seconds, bool)
            or not isinstance(self.max_evidence_lifetime_seconds, int)
            or self.max_evidence_lifetime_seconds < 1
        ):
            raise ContractError("max_evidence_lifetime_seconds debe ser positivo")

    def allows(
        self,
        evidence: MultiAuthorityRecoveryEvidence,
        now: datetime,
    ) -> bool:
        """Check policy scope and time bounds, not evidence authenticity."""
        if not isinstance(evidence, MultiAuthorityRecoveryEvidence):
            raise ContractError("evidence debe ser MultiAuthorityRecoveryEvidence")
        _utc(now, "now")
        lifetime = (evidence.expires_at - evidence.issued_at).total_seconds()
        return (
            self.enabled is True
            and evidence.issuer_id == self.issuer_id
            and evidence.evidence_kind in self.allowed_evidence_kinds
            and self.valid_from <= now
            and (self.valid_until is None or now < self.valid_until)
            and evidence.issued_at >= self.valid_from
            and (
                self.valid_until is None
                or evidence.expires_at <= self.valid_until
            )
            and lifetime <= self.max_evidence_lifetime_seconds
        )
