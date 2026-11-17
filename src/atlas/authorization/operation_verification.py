"""Verificación de evidencia CAM para operaciones generales."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from atlas.authorization.models import AuthorizationRequest
from atlas.authorization.operation_models import OperationAuthorizationEvidence
from atlas.core.errors import ContractError
from atlas.ports.operation_authorization_verifier import (
    OperationAuthorizationEvidenceVerifierPort,
)


class OperationEvidenceStatus(str, Enum):
    VERIFIED = "verified"
    DENIED = "denied"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class OperationEvidenceVerification:
    """Resultado de verificación; VERIFIED no ejecuta la operación."""

    status: OperationEvidenceStatus
    evidence_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.status, OperationEvidenceStatus):
            raise ContractError("status debe ser OperationEvidenceStatus")
        if not isinstance(self.evidence_id, str) or not self.evidence_id.strip():
            raise ContractError("evidence_id debe ser una cadena no vacía")


def _validate_utc(value: datetime, field: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ContractError(f"{field} debe ser un datetime con zona horaria")
    if value.utcoffset() != timedelta(0):
        raise ContractError(f"{field} debe estar en UTC")


class OperationAuthorizationEvidenceVerificationService:
    """Valida claims localmente y delega la confianza a un verificador CAM."""

    def __init__(self, verifier: OperationAuthorizationEvidenceVerifierPort) -> None:
        if verifier is None or not callable(getattr(verifier, "verify", None)):
            raise ContractError("verifier debe implementar verify(request, evidence, now)")
        self._verifier = verifier

    def verify(
        self,
        request: AuthorizationRequest,
        evidence: OperationAuthorizationEvidence,
        now: datetime,
    ) -> OperationEvidenceVerification:
        if not isinstance(request, AuthorizationRequest):
            raise ContractError("request debe ser AuthorizationRequest")
        if not isinstance(evidence, OperationAuthorizationEvidence):
            raise ContractError("evidence debe ser OperationAuthorizationEvidence")
        _validate_utc(now, "now")

        if not evidence.matches(request) or not evidence.is_current_at(now):
            return OperationEvidenceVerification(
                OperationEvidenceStatus.DENIED,
                evidence.evidence_id,
            )

        try:
            verified = self._verifier.verify(request, evidence, now)
        except Exception:
            return OperationEvidenceVerification(
                OperationEvidenceStatus.UNAVAILABLE,
                evidence.evidence_id,
            )

        return OperationEvidenceVerification(
            OperationEvidenceStatus.VERIFIED
            if verified is True
            else OperationEvidenceStatus.DENIED,
            evidence.evidence_id,
        )
