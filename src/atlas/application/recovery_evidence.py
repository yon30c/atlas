"""Verification service for untrusted multi-authority recovery evidence."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from atlas.core.errors import ContractError
from atlas.memory.authority_changes import (
    AuthorityChangeTarget,
    MultiAuthorityRecoveryEvidence,
    MultiAuthorityRecoveryEvidenceKind,
)
from atlas.ports.multi_authority_recovery_evidence_verifier import (
    MultiAuthorityRecoveryEvidenceVerifierPort,
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

    def __post_init__(self) -> None:
        if not isinstance(self.status, RecoveryEvidenceVerificationStatus):
            raise ContractError("status debe ser RecoveryEvidenceVerificationStatus")
        if not isinstance(self.evidence_id, str) or not self.evidence_id.strip():
            raise ContractError("evidence_id debe ser una cadena no vacía")


def _validate_utc(value: datetime, field: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ContractError(f"{field} debe ser un datetime UTC")


class MultiAuthorityRecoveryEvidenceVerificationService:
    """Checks local bindings then delegates authenticity to a trusted verifier."""

    def __init__(self, verifier: MultiAuthorityRecoveryEvidenceVerifierPort) -> None:
        if verifier is None or not callable(getattr(verifier, "verify", None)):
            raise ContractError("verifier debe implementar verify(evidence, now)")
        self._verifier = verifier

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
            verified = self._verifier.verify(evidence, now)
        except Exception:
            return RecoveryEvidenceVerification(
                RecoveryEvidenceVerificationStatus.UNAVAILABLE,
                evidence.evidence_id,
            )

        return RecoveryEvidenceVerification(
            RecoveryEvidenceVerificationStatus.VERIFIED
            if verified is True
            else RecoveryEvidenceVerificationStatus.DENIED,
            evidence.evidence_id,
        )
