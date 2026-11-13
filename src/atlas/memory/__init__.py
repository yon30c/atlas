"""Modelos y validación pura de memoria; el acceso pasa por MemoryGateway."""
from atlas.memory.models import (
    Memory,
    MemoryClassification,
    MemoryProposal,
    MemoryProposalIntent,
    MemoryProvenance,
    MemoryScope,
    MemoryScopeKind,
    MemoryVersion,
    MemoryVersionStatus,
    OpaqueReference,
    ProvenanceContext,
    ReferenceAvailability,
    SourceKind,
)
from atlas.memory.validation import (
    validate_memory_aggregate,
    validate_proposal_links,
    validate_version_transition,
)

__all__ = [
    "Memory",
    "MemoryClassification",
    "MemoryProposal",
    "MemoryProposalIntent",
    "MemoryProvenance",
    "MemoryScope",
    "MemoryScopeKind",
    "MemoryVersion",
    "MemoryVersionStatus",
    "OpaqueReference",
    "ProvenanceContext",
    "ReferenceAvailability",
    "SourceKind",
    "validate_memory_aggregate",
    "validate_proposal_links",
    "validate_version_transition",
]
