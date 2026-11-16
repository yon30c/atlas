"""Trusted verification boundary for multi-authority recovery evidence."""

from datetime import datetime
from typing import Protocol

from atlas.memory.authority_changes import MultiAuthorityRecoveryEvidence


class MultiAuthorityRecoveryEvidenceVerifierPort(Protocol):
    """Authenticate evidence against trusted issuer and authoritative sources.

    Implementations must verify issuer trust and key status, signature or
    equivalent attestation, digest against the actual payload, operation and
    complete target/revision binding, evidence-kind semantics, revocation,
    replay protection, source authority and current fencing/revision state.
    A cached or point-in-time check without the required consistency guarantee
    is insufficient. Return True only when every check succeeds; return False
    for invalid evidence and raise when verification cannot be completed.
    """

    def verify(
        self,
        evidence: MultiAuthorityRecoveryEvidence,
        now: datetime,
    ) -> bool:
        """Return True only for independently authenticated, current evidence."""
