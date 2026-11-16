"""Port for atomic, one-time admission of verified recovery evidence."""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from atlas.core.errors import ContractError

from atlas.application.recovery_admission import RecoveryEvidenceAdmissionCommand


class RecoveryEvidenceAdmissionStatus(str, Enum):
    ADMITTED = "ADMITTED"
    REPLAYED = "REPLAYED"
    STALE_ISSUER = "STALE_ISSUER"
    ISSUER_DISABLED = "ISSUER_DISABLED"
    OPERATION_MISMATCH = "OPERATION_MISMATCH"
    EVIDENCE_REUSED = "EVIDENCE_REUSED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class RecoveryEvidenceAdmissionResult:
    """Outcome of a durable admission attempt; never execution authority."""

    status: RecoveryEvidenceAdmissionStatus
    admission_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.status, RecoveryEvidenceAdmissionStatus):
            raise ContractError("status debe ser RecoveryEvidenceAdmissionStatus")
        if not isinstance(self.admission_id, str) or not self.admission_id.strip():
            raise ContractError("admission_id debe ser una cadena no vacía")

    @property
    def effect_permitted(self) -> bool:
        """Admission records evidence; it never authorizes a recovery effect."""
        return False

class RecoveryEvidenceAdmissionPort(Protocol):
    """Atomically persist admission against the current local authority snapshot.

    Implementations MUST, in one transaction/fencing boundary:
    - verify that the issuer is enabled at exactly issuer_registry_revision;
    - verify operation_id and the complete canonical target/revision set against
      the durable operation reservation, including its current lifecycle and claims;
    - enforce one-time use of evidence_id and immutable admission_id binding;
    - return REPLAYED only for an exact replay of the original command;
    - reject changed payloads, stale revisions and evidence reused by another
      operation without creating partial records.

    A point-in-time read followed by a later insert is not conforming. This port
    does not claim that a later external effect is fenced; that requires the
    eventual effect to share the same coordinator boundary.
    """

    def admit(
        self,
        command: RecoveryEvidenceAdmissionCommand,
    ) -> RecoveryEvidenceAdmissionResult:
        """Persist or replay one exact admission request atomically."""
