"""Atomic recovery-gate closure boundary.

The gate implementation must serialize closure with admission and egress and
persist RECOVERY_CLOSED as part of the same authority operation.
"""
from typing import Protocol

from atlas.memory.journal import ConsistencyPosition, ConsistencyTransition, JournalCommit


class RecoveryGatePort(Protocol):
    def ensure_recovery_gate_closed(
        self,
        operation_id: str,
        generation: int,
    ) -> bool:
        """Restore/confirm the exact persisted recovery gate before endpoint contact.

        Required after process restart. True is returned only when the authority
        has reconstructed the matching closure and is rejecting admissions and
        egress for the domain. A journal record alone is not enough.
        """

    def close_recovery_gate(
        self,
        expected_position: ConsistencyPosition,
        transition: ConsistencyTransition,
    ) -> JournalCommit | None:
        """Atomically close the domain gate and durably append RECOVERY_CLOSED.

        A successful return guarantees that no new read admission or egress can
        pass the authority boundary until RECOVERY_RECONCILED is committed.
        A missing, conflicting or ambiguous result is fail-closed; callers must
        reload the journal and authority state before retrying.
        """
