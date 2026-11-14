"""Provider-agnostic ports for external anchors and consistency verification."""
from typing import Protocol

from atlas.memory.journal import ConsistencyRecoveryState
from atlas.memory.trust import (
    CheckpointVerificationResult,
    ConsistencyCheckpointVerificationRequest,
    ConsistencyRecoveryTrustContext,
    ConsistencyRecoveryVerificationResult,
    ConsistencyTrustAnchor,
    TrustAnchorAdvanceRequest,
    TrustAnchorReadResult,
    TrustAnchorUpdateStatus,
    ReceiptTrustContext,
)


class TrustAnchorPort(Protocol):
    """External monotonic anchor authority, outside journal restore rollback."""

    def load_current_anchor(self, consistency_domain_id: str) -> TrustAnchorReadResult:
        """UNKNOWN/NOT_FOUND never bootstraps recovery."""

    def advance_anchor(
        self,
        request: TrustAnchorAdvanceRequest,
    ) -> TrustAnchorUpdateStatus:
        """Atomic CAS over the complete expected anchor and canonical new anchor."""


class ConsistencyCheckpointVerifierPort(Protocol):
    """Independent verifier for authenticated journal/checkpoint continuity."""

    def verify_checkpoint(
        self,
        request: ConsistencyCheckpointVerificationRequest,
    ) -> CheckpointVerificationResult:
        """Return VERIFIED only after issuer, key, policy, anchor and chain checks."""


class ConsistencyRecoveryVerifierPort(Protocol):
    """Verifies complete recovery state before the reducer can consume it."""

    def verify_recovery_state(
        self,
        state: ConsistencyRecoveryState,
        anchor: ConsistencyTrustAnchor,
        trust_context: ConsistencyRecoveryTrustContext,
    ) -> ConsistencyRecoveryVerificationResult:
        """Reject rollback, forks, gaps, missing tombstones and unresolved continuity."""
