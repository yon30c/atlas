"""Port for the authoritative inventory of recovery-evidence issuers."""

from typing import Protocol

from atlas.authorization.recovery_evidence_issuer_registry import (
    RecoveryEvidenceIssuerRegistration,
)


class RecoveryEvidenceIssuerRegistryPort(Protocol):
    """Read the current inventory snapshot for an issuer."""

    def get_registration(
        self,
        issuer_id: str,
    ) -> RecoveryEvidenceIssuerRegistration | None:
        """Return the latest registration snapshot, if present."""

    def list_registrations(self) -> tuple[RecoveryEvidenceIssuerRegistration, ...]:
        """Return the latest snapshot for each known issuer in stable order."""
