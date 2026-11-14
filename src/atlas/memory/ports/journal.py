"""Neutral structural contracts for a consumer-owned consistency journal.

These protocols describe the journal boundary without importing Atlas models,
SQLite, envelopes, reducers, or a local trust profile. Concrete consumers keep
ownership of their validated position, transition, checkpoint and recovery DTOs.
"""
from datetime import datetime
from typing import Protocol, TypeVar


class ConsistencyPositionLike(Protocol):
    """A monotonic position inside one consistency authority and epoch."""

    consistency_domain_id: str
    authority_epoch: int
    sequence: int


class ConsistencyTransitionLike(Protocol):
    """Minimal journal transition identity shared by all consumer profiles.

    Domain-specific transition payloads and validation remain owned by the
    consumer. A reducer must validate the complete schema before replay.
    """

    record_id: str
    schema_version: int
    record_kind: str
    operation_id: str
    occurred_at: datetime


class JournalCommitLike(Protocol):
    """Receipt for a committed or idempotently replayed append."""

    position: ConsistencyPositionLike
    record_id: str
    replayed: bool


class JournalOperationResolutionLike(Protocol):
    """Typed outcome for reconciling an append with an uncertain response."""

    status: str


class JournalEntryLike(Protocol):
    """One ordered transition at an exact position."""

    position: ConsistencyPositionLike
    transition: ConsistencyTransitionLike


class ConsistencyCheckpointLike(Protocol):
    """Consumer-owned checkpoint metadata bound to an exact journal position."""

    checkpoint_id: str
    position: ConsistencyPositionLike
    state_reference: str
    integrity_reference: str
    created_at: datetime


class ConsistencyRecoveryStateLike(Protocol):
    """Structural journal state; this type carries no trust attestation."""

    domain_id: str
    authority_epoch: int
    checkpoint: ConsistencyCheckpointLike | None
    entries: tuple[JournalEntryLike, ...]
    head_sequence: int
    continuity_reference: str


PositionT = TypeVar("PositionT", bound=ConsistencyPositionLike)
TransitionT = TypeVar("TransitionT", bound=ConsistencyTransitionLike)
CommitT = TypeVar("CommitT", bound=JournalCommitLike)
ResolutionT = TypeVar("ResolutionT", bound=JournalOperationResolutionLike)
EntryT = TypeVar("EntryT", bound=JournalEntryLike)
CheckpointT = TypeVar("CheckpointT", bound=ConsistencyCheckpointLike)
RecoveryStateT = TypeVar("RecoveryStateT", bound=ConsistencyRecoveryStateLike)


class ConsistencyJournalPort(
    Protocol[
        PositionT,
        TransitionT,
        CommitT,
        ResolutionT,
        EntryT,
        CheckpointT,
        RecoveryStateT,
    ]
):
    """Persistence boundary parameterized by consumer-owned immutable models.

    Structural loading is diagnostic only. Operational recovery must use a
    separate profile-specific verifier and must never treat this port as proof
    of authenticity, completeness, or anti-rollback.
    """

    def append_transition(
        self,
        expected_position: PositionT,
        append_id: str,
        transition: TransitionT,
    ) -> CommitT | None:
        """Append atomically, enforcing position and idempotency semantics."""

    def resolve_append(
        self,
        domain_id: str,
        authority_epoch: int,
        append_id: str,
        idempotency_key: str | None,
        expected_transition: TransitionT,
        expected_position: PositionT,
    ) -> ResolutionT:
        """Resolve an uncertain append by stable append and semantic identifiers."""

    def load_recovery_state(self, domain_id: str) -> RecoveryStateT | None:
        """Load an unauthenticated structural snapshot for diagnostics only."""

    def load_endpoint_receipts(self, admission_id: str) -> tuple[EntryT, ...] | None:
        """Load a complete endpoint receipt set, or None if completeness is unknown."""

    def commit_checkpoint(
        self,
        checkpoint: CheckpointT,
        expected_position: PositionT,
    ) -> CommitT | None:
        """Commit a checkpoint against one exact expected journal position."""
