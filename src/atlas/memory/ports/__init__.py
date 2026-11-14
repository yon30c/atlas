"""Puertos externos del dominio Memory Engine."""

from atlas.memory.ports.consistency_keys import MemoryConsistencyKeyPort
from atlas.memory.ports.consistency_signing import MemoryConsistencySignerPort
from atlas.memory.ports.journal import (
    ConsistencyCheckpointLike,
    ConsistencyJournalPort,
    ConsistencyPositionLike,
    ConsistencyRecoveryStateLike,
    ConsistencyTransitionLike,
    JournalCommitLike,
    JournalEntryLike,
    JournalOperationResolutionLike,
)
from atlas.memory.ports.metadata import (
    EnvironmentMetadataPort,
    MemoryMetadataPort,
    ProjectMetadataPort,
)
from atlas.memory.ports.recovery import (
    CheckpointProjectionPort,
    RecoveryInventoryVerifierPort,
)

__all__ = [
    "CheckpointProjectionPort",
    "ConsistencyCheckpointLike",
    "ConsistencyJournalPort",
    "ConsistencyPositionLike",
    "ConsistencyRecoveryStateLike",
    "ConsistencyTransitionLike",
    "EnvironmentMetadataPort",
    "JournalCommitLike",
    "JournalEntryLike",
    "JournalOperationResolutionLike",
    "MemoryConsistencyKeyPort",
    "MemoryConsistencySignerPort",
    "MemoryMetadataPort",
    "ProjectMetadataPort",
    "RecoveryInventoryVerifierPort",
]
