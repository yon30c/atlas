"""Read-only integrity audit contracts for durable recovery admissions."""

from dataclasses import dataclass
from enum import Enum

from atlas.core.errors import ContractError


class RecoveryEvidenceAdmissionAuditStatus(str, Enum):
    HEALTHY = "HEALTHY"
    CORRUPT = "CORRUPT"


@dataclass(frozen=True, slots=True)
class RecoveryEvidenceAdmissionAudit:
    admission_id: str
    status: RecoveryEvidenceAdmissionAuditStatus
    diagnostic_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.admission_id, str) or not self.admission_id.strip():
            raise ContractError("admission_id debe ser una cadena no vacía")
        if not isinstance(self.status, RecoveryEvidenceAdmissionAuditStatus):
            raise ContractError("status debe ser RecoveryEvidenceAdmissionAuditStatus")
        if not isinstance(self.diagnostic_codes, tuple) or any(
            not isinstance(code, str) or not code.strip()
            for code in self.diagnostic_codes
        ):
            raise ContractError("diagnostic_codes debe ser una tupla de códigos no vacíos")
        if self.status is RecoveryEvidenceAdmissionAuditStatus.HEALTHY and self.diagnostic_codes:
            raise ContractError("una admisión HEALTHY no puede tener diagnósticos")
        if self.status is RecoveryEvidenceAdmissionAuditStatus.CORRUPT and not self.diagnostic_codes:
            raise ContractError("una admisión CORRUPT requiere diagnósticos")


@dataclass(frozen=True, slots=True)
class RecoveryEvidenceAdmissionAuditReport:
    admissions: tuple[RecoveryEvidenceAdmissionAudit, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.admissions, tuple) or any(
            not isinstance(item, RecoveryEvidenceAdmissionAudit)
            for item in self.admissions
        ):
            raise ContractError("admissions debe contener auditorías válidas")
        identifiers = tuple(item.admission_id for item in self.admissions)
        if len(set(identifiers)) != len(identifiers):
            raise ContractError("el informe no puede repetir admission_id")

    @property
    def healthy_count(self) -> int:
        return sum(
            item.status is RecoveryEvidenceAdmissionAuditStatus.HEALTHY
            for item in self.admissions
        )

    @property
    def corrupt_count(self) -> int:
        return sum(
            item.status is RecoveryEvidenceAdmissionAuditStatus.CORRUPT
            for item in self.admissions
        )
