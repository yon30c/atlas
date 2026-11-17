"""Verification service for untrusted multi-authority recovery evidence."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import json

from atlas.core.errors import ContractError
from atlas.memory.authority_changes import (
    AuthorityChangeTarget,
    MultiAuthorityRecoveryEvidence,
    MultiAuthorityRecoveryEvidenceKind,
)
from atlas.ports.multi_authority_recovery_evidence_verifier import (
    MultiAuthorityRecoveryEvidenceVerifierPort,
)
from atlas.authorization.recovery_evidence_trust import (
    RecoveryEvidenceIssuerTrustPolicy,
)
from atlas.ports.recovery_evidence_issuer_trust import (
    RecoveryEvidenceIssuerTrustPolicyPort,
)
from atlas.authorization.recovery_evidence_issuer_registry import (
    RecoveryEvidenceIssuerRegistration,
)
from atlas.ports.recovery_evidence_issuer_registry import (
    RecoveryEvidenceIssuerRegistryPort,
)


class RecoveryEvidenceVerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    DENIED = "DENIED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class RecoveryEvidenceVerification:
    """Verification outcome; VERIFIED is not execution or recovery authority."""

    status: RecoveryEvidenceVerificationStatus
    evidence_id: str
    issuer_registry_revision: int | None = None
    evidence_digest: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, RecoveryEvidenceVerificationStatus):
            raise ContractError("status debe ser RecoveryEvidenceVerificationStatus")
        if not isinstance(self.evidence_id, str) or not self.evidence_id.strip():
            raise ContractError("evidence_id debe ser una cadena no vacía")
        if self.issuer_registry_revision is not None and (
            isinstance(self.issuer_registry_revision, bool)
            or not isinstance(self.issuer_registry_revision, int)
            or self.issuer_registry_revision < 1
        ):
            raise ContractError("issuer_registry_revision debe ser un entero positivo")
        if (
            self.status is RecoveryEvidenceVerificationStatus.VERIFIED
            and (self.issuer_registry_revision is None or self.evidence_digest is None)
        ):
            raise ContractError("VERIFIED requiere revisión del inventario y digest de evidencia")
        if self.evidence_digest is not None and (
            not isinstance(self.evidence_digest, str)
            or len(self.evidence_digest) != 64
            or any(char not in "0123456789abcdef" for char in self.evidence_digest)
        ):
            raise ContractError("evidence_digest debe ser SHA-256 hexadecimal lowercase")
        if self.status is not RecoveryEvidenceVerificationStatus.VERIFIED and (
            self.issuer_registry_revision is not None or self.evidence_digest is not None
        ):
            raise ContractError("solo VERIFIED puede incluir revisión y digest de evidencia")



def recovery_evidence_digest(evidence: MultiAuthorityRecoveryEvidence) -> str:
    """Hash every field of the immutable evidence claim in canonical form."""
    if not isinstance(evidence, MultiAuthorityRecoveryEvidence):
        raise ContractError("evidence debe ser MultiAuthorityRecoveryEvidence")
    payload = {
        "evidence_id": evidence.evidence_id,
        "operation_id": evidence.operation_id,
        "evidence_kind": evidence.evidence_kind.value,
        "issuer_id": evidence.issuer_id,
        "issued_at": evidence.issued_at.isoformat(timespec="microseconds"),
        "expires_at": evidence.expires_at.isoformat(timespec="microseconds"),
        "payload_digest": evidence.payload_digest,
        "attestation_ref": evidence.attestation_ref,
        "targets": [
            {
                "authority_kind": target.authority_kind.value,
                "authority_id": target.authority_id,
                "expected_revision": target.expected_revision,
                "proposed_revision": target.proposed_revision,
                "observed_revision": target.observed_revision,
            }
            for target in evidence.targets
        ],
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()



def _validate_utc(value: datetime, field: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ContractError(f"{field} debe ser un datetime UTC")


class MultiAuthorityRecoveryEvidenceVerificationService:
    """Checks local bindings then delegates authenticity to a trusted verifier."""

    def __init__(
        self,
        verifier: MultiAuthorityRecoveryEvidenceVerifierPort,
        trust_policy_port: RecoveryEvidenceIssuerTrustPolicyPort,
        issuer_registry_port: RecoveryEvidenceIssuerRegistryPort,
    ) -> None:
        if verifier is None or not callable(getattr(verifier, "verify", None)):
            raise ContractError("verifier debe implementar verify(evidence, now)")
        if trust_policy_port is None or not callable(
            getattr(trust_policy_port, "get_policy", None)
        ):
            raise ContractError("trust_policy_port debe implementar get_policy(issuer_id)")
        if issuer_registry_port is None or not callable(
            getattr(issuer_registry_port, "get_registration", None)
        ):
            raise ContractError(
                "issuer_registry_port debe implementar get_registration(issuer_id)"
            )
        self._verifier = verifier
        self._trust_policy_port = trust_policy_port
        self._issuer_registry_port = issuer_registry_port

    def verify(
        self,
        evidence: MultiAuthorityRecoveryEvidence,
        *,
        operation_id: str,
        evidence_kind: MultiAuthorityRecoveryEvidenceKind,
        targets: tuple[AuthorityChangeTarget, ...],
        now: datetime,
    ) -> RecoveryEvidenceVerification:
        if not isinstance(evidence, MultiAuthorityRecoveryEvidence):
            raise ContractError("evidence debe ser MultiAuthorityRecoveryEvidence")
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ContractError("operation_id debe ser una cadena no vacía")
        if not isinstance(evidence_kind, MultiAuthorityRecoveryEvidenceKind):
            raise ContractError("evidence_kind debe ser MultiAuthorityRecoveryEvidenceKind")
        if not isinstance(targets, tuple) or len(targets) < 2:
            raise ContractError("targets debe contener al menos dos objetivos")
        if any(not isinstance(target, AuthorityChangeTarget) for target in targets):
            raise ContractError("targets contiene un tipo no permitido")
        _validate_utc(now, "now")

        if (
            not evidence.matches(operation_id, evidence_kind, targets)
            or now < evidence.issued_at
            or now >= evidence.expires_at
        ):
            return RecoveryEvidenceVerification(
                RecoveryEvidenceVerificationStatus.DENIED,
                evidence.evidence_id,
            )

        try:
            registration = self._issuer_registry_port.get_registration(
                evidence.issuer_id
            )
        except Exception:
            return RecoveryEvidenceVerification(
                RecoveryEvidenceVerificationStatus.UNAVAILABLE,
                evidence.evidence_id,
            )

        if (
            registration is None
            or not isinstance(registration, RecoveryEvidenceIssuerRegistration)
            or registration.enabled is not True
            or registration.issuer_id != evidence.issuer_id
        ):
            return RecoveryEvidenceVerification(
                RecoveryEvidenceVerificationStatus.DENIED,
                evidence.evidence_id,
            )

        try:
            policy = self._trust_policy_port.get_policy(evidence.issuer_id)
        except Exception:
            return RecoveryEvidenceVerification(
                RecoveryEvidenceVerificationStatus.UNAVAILABLE,
                evidence.evidence_id,
            )

        if policy is None or not isinstance(policy, RecoveryEvidenceIssuerTrustPolicy):
            return RecoveryEvidenceVerification(
                RecoveryEvidenceVerificationStatus.DENIED,
                evidence.evidence_id,
            )
        if not policy.allows(evidence, now):
            return RecoveryEvidenceVerification(
                RecoveryEvidenceVerificationStatus.DENIED,
                evidence.evidence_id,
            )

        try:
            verified = self._verifier.verify(evidence, now)
        except Exception:
            return RecoveryEvidenceVerification(
                RecoveryEvidenceVerificationStatus.UNAVAILABLE,
                evidence.evidence_id,
            )

        if verified is not True:
            return RecoveryEvidenceVerification(
                RecoveryEvidenceVerificationStatus.DENIED,
                evidence.evidence_id,
            )

        # Re-read after the potentially slow cryptographic verifier. A revision
        # change during verification invalidates this result. This is a bounded
        # stale-snapshot check, not a lease or an effect-time fencing guarantee.
        try:
            current_registration = self._issuer_registry_port.get_registration(
                evidence.issuer_id
            )
        except Exception:
            return RecoveryEvidenceVerification(
                RecoveryEvidenceVerificationStatus.UNAVAILABLE,
                evidence.evidence_id,
            )

        if (
            current_registration is None
            or not isinstance(
                current_registration, RecoveryEvidenceIssuerRegistration
            )
            or current_registration.issuer_id != evidence.issuer_id
            or current_registration.enabled is not True
            or current_registration.registry_revision
            != registration.registry_revision
        ):
            return RecoveryEvidenceVerification(
                RecoveryEvidenceVerificationStatus.DENIED,
                evidence.evidence_id,
            )

        return RecoveryEvidenceVerification(
            RecoveryEvidenceVerificationStatus.VERIFIED,
            evidence.evidence_id,
            registration.registry_revision,
            recovery_evidence_digest(evidence),
        )
