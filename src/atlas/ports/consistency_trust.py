"""Provider-agnostic ports for external anchors and consistency verification."""
from enum import Enum
from typing import Protocol

from atlas.memory.trust import (
    ConsistencyCheckpointVerificationRequest,
    ConsistencyRecoveryVerificationResult,
    ConsistencyTrustAnchor,
    ReceiptTrustContext,
)


class TrustAnchorReadStatus(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"


class TrustAnchorUpdateStatus(str, Enum):
    UPDATED = "updated"
    REPLAYED = "replayed"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


class TrustAnchorPort(Protocol):
    """External monotonic anchor authority, outside journal restore rollback."""

    def load_current_anchor(
        self, consistency_domain_id: str
    ) -> tuple[TrustAnchorReadStatus, ConsistencyTrustAnchor | None]:
        """Return FOUND/NOT_FOUND/UNKNOWN; NOT_FOUND never bootstraps recovery."""

    def advance_anchor(
        self,
        expected_anchor_revision: int,
        expected_position_sequence: int,
        new_anchor: ConsistencyTrustAnchor,
    ) -> TrustAnchorUpdateStatus:
        """CAS advance; same canonical update replays, incompatible update conflicts."""


class ConsistencyCheckpointVerifierPort(Protocol):
    """Independent verifier for authenticated journal/checkpoint continuity."""

    def verify_checkpoint(
        self,
        request: ConsistencyCheckpointVerificationRequest,
    ) -> ConsistencyRecoveryVerificationResult:
        """Return VERIFIED only after issuer, key, policy, anchor and chain checks."""


class ConsistencyRecoveryVerifierPort(Protocol):
    """Verifies complete recovery state before the reducer can consume it."""

    def verify_recovery_state(
        self,
        consistency_domain_id: str,
        anchor: ConsistencyTrustAnchor,
        trust_context: ReceiptTrustContext,
    ) -> ConsistencyRecoveryVerificationResult:
        """Reject rollback, forks, gaps, missing tombstones and unresolved continuity."""
