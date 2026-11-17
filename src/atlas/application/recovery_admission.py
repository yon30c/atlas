"""Admission command contracts for independently verified recovery evidence.

The command is a request to a future transactional coordinator, not an
authorization token and not permission to perform a recovery effect.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from atlas.application.recovery_evidence import (
    RecoveryEvidenceVerification,
    RecoveryEvidenceVerificationStatus,
    recovery_evidence_digest,
)
from atlas.core.errors import ContractError
from atlas.memory.authority_changes import (
    AuthorityChangeTarget,
    MultiAuthorityRecoveryEvidence,
    MultiAuthorityRecoveryEvidenceKind,
)


@dataclass(frozen=True, slots=True, init=False)
class RecoveryEvidenceAdmissionCommand:
    """Exact, immutable binding submitted to an atomic admission coordinator."""

    admission_id: str
    operation_id: str
    evidence_id: str
    evidence_digest: str
    issuer_id: str
    issuer_registry_revision: int
    evidence_kind: MultiAuthorityRecoveryEvidenceKind
    targets: tuple[AuthorityChangeTarget, ...]
    requested_at: datetime

    def __post_init__(self) -> None:
        for field in ("admission_id", "operation_id", "evidence_id", "issuer_id"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"{field} debe ser una cadena no vacía")
        if (
            not isinstance(self.evidence_digest, str)
            or len(self.evidence_digest) != 64
            or any(char not in "0123456789abcdef" for char in self.evidence_digest)
        ):
            raise ContractError("evidence_digest debe ser SHA-256 hexadecimal lowercase")
        if (
            isinstance(self.issuer_registry_revision, bool)
            or not isinstance(self.issuer_registry_revision, int)
            or self.issuer_registry_revision < 1
        ):
            raise ContractError("issuer_registry_revision debe ser un entero positivo")
        if not isinstance(self.evidence_kind, MultiAuthorityRecoveryEvidenceKind):
            raise ContractError("evidence_kind debe ser MultiAuthorityRecoveryEvidenceKind")
        if not isinstance(self.targets, tuple) or len(self.targets) < 2:
            raise ContractError("targets debe contener al menos dos objetivos")
        if any(not isinstance(item, AuthorityChangeTarget) for item in self.targets):
            raise ContractError("targets contiene un tipo no permitido")
        identities = tuple(
            (item.authority_kind.value, item.authority_id) for item in self.targets
        )
        if len(set(identities)) != len(identities):
            raise ContractError("targets no puede contener identidades duplicadas")
        canonical = tuple(sorted(
            self.targets,
            key=lambda item: (item.authority_kind.value, item.authority_id),
        ))
        object.__setattr__(self, "targets", canonical)
        if (
            not isinstance(self.requested_at, datetime)
            or self.requested_at.tzinfo is None
            or self.requested_at.utcoffset() != timedelta(0)
        ):
            raise ContractError("requested_at debe ser un datetime UTC")

    def __init__(self, *args, **kwargs) -> None:
        raise ContractError(
            "use from_verified_evidence para construir un comando de admisión"
        )

    @classmethod
    def from_verified_evidence(
        cls,
        *,
        admission_id: str,
        evidence: MultiAuthorityRecoveryEvidence,
        verification: RecoveryEvidenceVerification,
        operation_id: str,
        evidence_kind: MultiAuthorityRecoveryEvidenceKind,
        targets: tuple[AuthorityChangeTarget, ...],
        requested_at: datetime,
    ) -> "RecoveryEvidenceAdmissionCommand":
        """Build a command only from a VERIFIED result bound to this evidence."""
        if not isinstance(evidence, MultiAuthorityRecoveryEvidence):
            raise ContractError("evidence debe ser MultiAuthorityRecoveryEvidence")
        if not isinstance(verification, RecoveryEvidenceVerification):
            raise ContractError("verification debe ser RecoveryEvidenceVerification")
        if verification.status is not RecoveryEvidenceVerificationStatus.VERIFIED:
            raise ContractError("la evidencia debe estar VERIFIED para solicitar admisión")
        if verification.evidence_id != evidence.evidence_id:
            raise ContractError("verification no corresponde a evidence")
        digest = recovery_evidence_digest(evidence)
        if verification.evidence_digest != digest:
            raise ContractError("verification no corresponde al contenido exacto de evidence")
        if verification.issuer_registry_revision is None:
            raise ContractError("verification no contiene revisión del inventario")
        if not evidence.matches(operation_id, evidence_kind, targets):
            raise ContractError("evidence no coincide con operación, tipo y objetivos")
        command = object.__new__(cls)
        values = {
            "admission_id": admission_id,
            "operation_id": operation_id,
            "evidence_id": evidence.evidence_id,
            "evidence_digest": digest,
            "issuer_id": evidence.issuer_id,
            "issuer_registry_revision": verification.issuer_registry_revision,
            "evidence_kind": evidence_kind,
            "targets": targets,
            "requested_at": requested_at,
        }
        for field, value in values.items():
            object.__setattr__(command, field, value)
        command.__post_init__()
        return command
