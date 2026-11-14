"""Adapter exposing the local SQLite journal through the neutral Memory port.

This adapter preserves the Atlas/local DTOs internally. It does not expose
verified recovery: callers needing operational recovery must use the concrete
local journal's profile-specific verification boundary.
"""
from atlas.adapters.sqlite.consistency_journal import SQLiteConsistencyJournal
from atlas.core.errors import ContractError
from atlas.memory.journal import (
    CheckpointCommitResult,
    CheckpointCommitStatus,
    ConsistencyCheckpoint,
    ConsistencyPosition,
    ConsistencyRecoveryState,
    ConsistencyTransition,
    JournalCommit,
    JournalEntry,
    JournalOperationResolution,
)
from atlas.memory.ports.journal import ConsistencyJournalPort


class LocalSQLiteConsistencyJournalAdapter:
    """Translate the neutral checkpoint call into the local journal signature.

    The adapter intentionally reports no endpoint receipt inventory because
    SQLiteConsistencyJournal does not currently provide a complete receipt
    inventory through its journal API. Returning None is fail-closed and must
    not be interpreted as an empty inventory.
    """

    def __init__(self, journal: SQLiteConsistencyJournal) -> None:
        if not isinstance(journal, SQLiteConsistencyJournal):
            raise ContractError("journal debe ser SQLiteConsistencyJournal")
        self._journal = journal

    def append_transition(
        self,
        expected_position: ConsistencyPosition,
        append_id: str,
        transition: ConsistencyTransition,
    ) -> JournalCommit | None:
        return self._journal.append_transition(
            expected_position, append_id, transition
        )

    def resolve_append(
        self,
        domain_id: str,
        authority_epoch: int,
        append_id: str,
        idempotency_key: str | None,
        expected_transition: ConsistencyTransition,
        expected_position: ConsistencyPosition,
    ) -> JournalOperationResolution:
        return self._journal.resolve_append(
            domain_id,
            authority_epoch,
            append_id,
            idempotency_key,
            expected_transition,
            expected_position,
        )

    def load_recovery_state(
        self, domain_id: str
    ) -> ConsistencyRecoveryState | None:
        """Return structural state for diagnostics only, never for replay."""
        return self._journal.load_recovery_state(domain_id)

    @staticmethod
    def load_endpoint_receipts(
        admission_id: str,
    ) -> tuple[JournalEntry, ...] | None:
        """Fail closed until a complete durable receipt inventory is supported."""
        if not isinstance(admission_id, str) or not admission_id.strip():
            return None
        return None

    def commit_checkpoint(
        self,
        checkpoint: ConsistencyCheckpoint,
        expected_position: ConsistencyPosition,
        expected_continuity_reference: str,
    ) -> CheckpointCommitResult:
        """Preserve the local journal's CAS against the exact prior commitment."""
        if (
            not isinstance(checkpoint, ConsistencyCheckpoint)
            or not isinstance(expected_position, ConsistencyPosition)
            or not isinstance(expected_continuity_reference, str)
            or not expected_continuity_reference.strip()
        ):
            return CheckpointCommitResult(CheckpointCommitStatus.CONFLICT)
        return self._journal.commit_checkpoint(
            expected_position,
            expected_continuity_reference,
            checkpoint,
        )
