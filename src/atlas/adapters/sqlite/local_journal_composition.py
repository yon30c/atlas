"""Explicit composition of local SQLite persistence and trusted recovery ports.

The neutral persistence adapter and local verified-recovery adapter are kept
separate. Both wrap the exact same SQLiteConsistencyJournal instance so
operational recovery cannot accidentally be composed from another database.
"""
from dataclasses import dataclass

from atlas.adapters.sqlite.consistency_journal import SQLiteConsistencyJournal
from atlas.adapters.sqlite.local_consistency_journal import (
    LocalSQLiteConsistencyJournalAdapter,
)
from atlas.core.errors import ContractError
from atlas.memory.trust import (
    ConsistencyRecoveryVerificationResult,
    ConsistencyRecoveryVerificationStatus,
)


class LocalSQLiteVerifiedRecoveryAdapter:
    """Expose only the local journal's independently verified recovery result."""

    def __init__(self, journal: SQLiteConsistencyJournal) -> None:
        if not isinstance(journal, SQLiteConsistencyJournal):
            raise ContractError("journal debe ser SQLiteConsistencyJournal")
        if journal.recovery_trust_policy is None:
            raise ContractError(
                "el journal debe tener recovery_verifier y trust_policy configurados"
            )
        self._journal = journal

    def load_verified_recovery_state(
        self, domain_id: str
    ) -> ConsistencyRecoveryVerificationResult:
        """Delegate to the configured local verifier; never read structural state."""
        result = self._journal.load_verified_recovery_state(domain_id)
        if not isinstance(result, ConsistencyRecoveryVerificationResult):
            return ConsistencyRecoveryVerificationResult(
                ConsistencyRecoveryVerificationStatus.UNAVAILABLE
            )
        if (
            result.status is ConsistencyRecoveryVerificationStatus.VERIFIED
            and result.verified_local_state is None
        ):
            return ConsistencyRecoveryVerificationResult(
                ConsistencyRecoveryVerificationStatus.REJECTED
            )
        return result


@dataclass(frozen=True, slots=True)
class LocalSQLiteConsistencyJournalPorts:
    """Paired ports assembled from one exact local journal instance."""

    persistence: LocalSQLiteConsistencyJournalAdapter
    verified_recovery: LocalSQLiteVerifiedRecoveryAdapter

    def __post_init__(self) -> None:
        if not isinstance(self.persistence, LocalSQLiteConsistencyJournalAdapter):
            raise ContractError("persistence debe ser LocalSQLiteConsistencyJournalAdapter")
        if not isinstance(self.verified_recovery, LocalSQLiteVerifiedRecoveryAdapter):
            raise ContractError("verified_recovery debe ser LocalSQLiteVerifiedRecoveryAdapter")
        if self.persistence._journal is not self.verified_recovery._journal:
            raise ContractError(
                "persistencia y recuperación deben usar la misma instancia de journal"
            )


def compose_local_sqlite_journal_ports(
    journal: SQLiteConsistencyJournal,
) -> LocalSQLiteConsistencyJournalPorts:
    """Create the neutral persistence and local trust ports over one journal."""
    if not isinstance(journal, SQLiteConsistencyJournal):
        raise ContractError("journal debe ser SQLiteConsistencyJournal")
    return LocalSQLiteConsistencyJournalPorts(
        persistence=LocalSQLiteConsistencyJournalAdapter(journal),
        verified_recovery=LocalSQLiteVerifiedRecoveryAdapter(journal),
    )
