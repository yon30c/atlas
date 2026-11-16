"""Read-only diagnostics for persisted recovery-evidence issuer policies."""

from dataclasses import dataclass
from enum import Enum

from atlas.core.errors import ContractError


class RecoveryEvidenceIssuerTrustPolicyAuditStatus(str, Enum):
    HEALTHY = "healthy"
    DISABLED = "disabled"
    CORRUPT = "corrupt"
    MISSING_POLICY = "missing_policy"


@dataclass(frozen=True, slots=True)
class RecoveryEvidenceIssuerTrustPolicyAudit:
    """Diagnostic snapshot for one issuer; it never grants trust or mutates state."""

    issuer_id: str
    status: RecoveryEvidenceIssuerTrustPolicyAuditStatus
    revisions: tuple[int, ...]
    latest_revision: int | None
    diagnostic_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.issuer_id, str) or not self.issuer_id.strip():
            raise ContractError("issuer_id debe ser una cadena no vacía")
        if not isinstance(self.status, RecoveryEvidenceIssuerTrustPolicyAuditStatus):
            raise ContractError("status de auditoría inválido")
        if not isinstance(self.revisions, tuple) or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in self.revisions
        ):
            raise ContractError("revisions debe ser una tupla de enteros positivos")
        if self.latest_revision is not None and (
            isinstance(self.latest_revision, bool)
            or not isinstance(self.latest_revision, int)
            or self.latest_revision < 1
        ):
            raise ContractError("latest_revision debe ser None o entero positivo")
        if not isinstance(self.diagnostic_codes, tuple) or any(
            not isinstance(code, str) or not code.strip()
            for code in self.diagnostic_codes
        ):
            raise ContractError("diagnostic_codes debe ser una tupla de códigos no vacíos")


@dataclass(frozen=True, slots=True)
class RecoveryEvidenceIssuerTrustPolicyAuditReport:
    """Stable, read-only result for auditing all registered issuers."""

    issuers: tuple[RecoveryEvidenceIssuerTrustPolicyAudit, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.issuers, tuple) or any(
            not isinstance(item, RecoveryEvidenceIssuerTrustPolicyAudit)
            for item in self.issuers
        ):
            raise ContractError("issuers debe ser una tupla de diagnósticos válidos")
        ids = tuple(item.issuer_id for item in self.issuers)
        if len(set(ids)) != len(ids):
            raise ContractError("el informe no puede repetir emisores")

    @property
    def is_healthy(self) -> bool:
        return bool(self.issuers) and all(
            item.status is RecoveryEvidenceIssuerTrustPolicyAuditStatus.HEALTHY
            for item in self.issuers
        )
