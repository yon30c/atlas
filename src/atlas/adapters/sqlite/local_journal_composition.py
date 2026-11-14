"""Explicit composition of local SQLite persistence and trusted recovery ports.

The neutral persistence adapter and local verified-recovery adapter are kept
separate. Both wrap the exact same SQLiteConsistencyJournal instance so
operational recovery cannot accidentally be composed from another database.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol

from atlas.adapters.sqlite.consistency_journal import SQLiteConsistencyJournal
from atlas.adapters.sqlite.local_consistency_journal import (
    LocalSQLiteConsistencyJournalAdapter,
)
from atlas.core.errors import ContractError
from atlas.memory.recovery_coordinator import RecoveryJournalCoordinator
from atlas.memory.trust import (
    ConsistencyRecoveryVerificationResult,
    ConsistencyRecoveryVerificationStatus,
)
from atlas.ports.memory_consistency_authority import ProtectedMemoryRecoveryAuthorityPort


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


class LocalSQLiteRecoveryAuthorityPort(ProtectedMemoryRecoveryAuthorityPort, Protocol):
    """Local authority bound to the exact SQLite journal used for recovery.

    The implementation must atomically serialize protected admission/egress
    and RecoveryGate operations against this journal's consistency state.
    """

    @property
    def consistency_journal(self) -> SQLiteConsistencyJournal:
        """Exact journal instance whose state this authority serializes."""
        ...


@dataclass(frozen=True, slots=True)
class LocalSQLiteRecoveryCoordinatorComposition:
    """Recovery coordinator and authority composed over one exact journal."""

    journal_ports: LocalSQLiteConsistencyJournalPorts
    consistency_authority: LocalSQLiteRecoveryAuthorityPort
    coordinator: RecoveryJournalCoordinator

    def __post_init__(self) -> None:
        if not isinstance(self.journal_ports, LocalSQLiteConsistencyJournalPorts):
            raise ContractError("journal_ports debe ser LocalSQLiteConsistencyJournalPorts")
        if self.journal_ports.persistence._journal is not self.journal_ports.verified_recovery._journal:
            raise ContractError("los puertos de journal no comparten la misma instancia")
        if getattr(self.consistency_authority, "consistency_journal", None) is not self.journal_ports.persistence._journal:
            raise ContractError("la autoridad y los puertos deben usar la misma instancia SQLite")
        if self.coordinator._journal is not self.journal_ports.persistence:
            raise ContractError("el coordinador no usa el puerto de persistencia compuesto")
        if self.coordinator._verified_recovery is not self.journal_ports.verified_recovery:
            raise ContractError("el coordinador no usa el puerto de recuperación compuesto")
        if self.coordinator._recovery_gate is not self.consistency_authority:
            raise ContractError("el coordinador no usa la autoridad compuesta")


def compose_local_sqlite_recovery_coordinator(
    *,
    journal: SQLiteConsistencyJournal,
    consistency_authority: LocalSQLiteRecoveryAuthorityPort,
    fencer: object,
    verifier: object,
    trust_context_factory: object,
    domain_id: str,
    id_factory: Callable[[], str],
    clock: Callable[[], datetime],
) -> LocalSQLiteRecoveryCoordinatorComposition:
    """Compose local recovery using one SQLite journal and one shared authority.

    The returned consistency_authority is the exact instance that the caller
    must also inject into MemoryGatewayService. Its declared journal binding
    must be the exact journal supplied here; separate gate implementations or
    separate journal instances are rejected.
    """
    if not isinstance(journal, SQLiteConsistencyJournal):
        raise ContractError("journal debe ser SQLiteConsistencyJournal")
    if getattr(consistency_authority, "consistency_journal", None) is not journal:
        raise ContractError("consistency_authority debe estar vinculada al journal exacto")
    required = (
        "admit_read", "begin_forget", "reconcile_forget", "begin_invalidation",
        "record_endpoint_ack", "get_nonterminal_admissions", "reconcile",
        "commit_and_emit", "finish", "fence", "reconcile_endpoint",
        "close_recovery_gate", "ensure_recovery_gate_closed",
    )
    if any(not callable(getattr(consistency_authority, name, None)) for name in required):
        raise ContractError("consistency_authority debe implementar ProtectedMemoryRecoveryAuthorityPort")
    ports = compose_local_sqlite_journal_ports(journal)
    coordinator = RecoveryJournalCoordinator(
        journal=ports.persistence,
        recovery_gate=consistency_authority,
        fencer=fencer,
        verifier=verifier,
        trust_context_factory=trust_context_factory,
        verified_recovery=ports.verified_recovery,
        domain_id=domain_id,
        id_factory=id_factory,
        clock=clock,
    )
    return LocalSQLiteRecoveryCoordinatorComposition(
        journal_ports=ports,
        consistency_authority=consistency_authority,
        coordinator=coordinator,
    )
