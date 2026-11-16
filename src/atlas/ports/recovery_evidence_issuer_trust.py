"""Port for retrieving authoritative issuer trust policy."""

from typing import Protocol

from atlas.application.recovery_evidence_trust import (
    RecoveryEvidenceIssuerTrustPolicy,
)


class RecoveryEvidenceIssuerTrustPolicyPort(Protocol):
    """Return the current policy for an issuer, or None when it is untrusted.

    Implementations must read an authoritative, current policy source. A stale
    cache is not sufficient for revocation-sensitive verification.
    """

    def get_policy(
        self,
        issuer_id: str,
    ) -> RecoveryEvidenceIssuerTrustPolicy | None:
        """Return the current issuer policy."""
