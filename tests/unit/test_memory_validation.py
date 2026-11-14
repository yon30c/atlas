from datetime import datetime, timedelta, timezone
import unittest

from atlas.core.errors import ContractError
from atlas.memory.models import (
    Memory, MemoryClassification, MemoryProposal, MemoryProposalIntent,
    MemoryScope, MemoryScopeKind, MemoryVersion, MemoryVersionStatus,
)
from atlas.memory.validation import (
    validate_memory_aggregate, validate_proposal_links, validate_version_transition,
)
from tests.unit.test_memory_models import M1, V1, P1, NOW, provenance, version


M2 = "018f0f00-0000-7000-8000-000000000010"
V2 = "018f0f00-0000-7000-8000-000000000011"
V3 = "018f0f00-0000-7000-8000-000000000012"
P2 = "018f0f00-0000-7000-8000-000000000013"


def memory(pointer=None):
    return Memory(M1, "owner-1", MemoryScope(MemoryScopeKind.PRIVATE), pointer, NOW, NOW)


def reviewed_version(version_id, number, status, parent=None):
    return version(
        version_id=version_id, version_number=number, status=status,
        parent_version_id=parent,
        reviewed_at=NOW + timedelta(seconds=number),
        reviewed_by="owner-1",
    )


class MemoryValidationTests(unittest.TestCase):
    def test_empty_and_valid_aggregate(self):
        validate_memory_aggregate(memory(), ())
        first = reviewed_version(V1, 1, MemoryVersionStatus.APPROVED)
        second = version(version_id=V2, version_number=2, parent_version_id=V1)
        validate_memory_aggregate(memory(V1), (first, second))

    def test_aggregate_rejects_duplicate_ids_numbers_and_foreign_memory(self):
        first = version()
        with self.assertRaises(ContractError):
            validate_memory_aggregate(memory(), (first, first))
        duplicate_number = version(version_id=V2)
        with self.assertRaises(ContractError):
            validate_memory_aggregate(memory(), (first, duplicate_number))
        foreign = version(memory_id=M2)
        with self.assertRaises(ContractError):
            validate_memory_aggregate(memory(), (foreign,))

    def test_aggregate_rejects_invalid_parent_chains(self):
        missing = version(version_id=V2, version_number=2, parent_version_id=V3)
        with self.assertRaises(ContractError):
            validate_memory_aggregate(memory(), (version(), missing))
        no_parent = version(version_id=V2, version_number=2)
        with self.assertRaises(ContractError):
            validate_memory_aggregate(memory(), (version(), no_parent))
        backwards = version(version_id=V2, version_number=2, parent_version_id=V1)
        later_parent = version(version_id=V3, version_number=3, parent_version_id=V2)
        validate_memory_aggregate(memory(), (version(), backwards, later_parent))

    def test_aggregate_requires_first_number_and_consistent_approved_pointer(self):
        starts_at_two = version(version_number=2)
        with self.assertRaises(ContractError):
            validate_memory_aggregate(memory(), (starts_at_two,))
        approved = reviewed_version(V1, 1, MemoryVersionStatus.APPROVED)
        with self.assertRaises(ContractError):
            validate_memory_aggregate(memory(), (approved,))
        with self.assertRaises(ContractError):
            validate_memory_aggregate(memory(V2), (approved,))
        validate_memory_aggregate(memory(V1), (approved,))

    def test_create_memory_proposal_links(self):
        pending = version()
        proposal = MemoryProposal(P1, MemoryProposalIntent.CREATE_MEMORY, M1, V1, "agent-1", NOW)
        validate_proposal_links(memory(), pending, proposal)
        with self.assertRaises(ContractError):
            validate_proposal_links(memory(), pending, proposal, (pending,))

    def test_new_version_proposal_requires_current_parent_and_next_number(self):
        approved = reviewed_version(V1, 1, MemoryVersionStatus.APPROVED)
        current_memory = memory(V1)
        pending = version(version_id=V2, version_number=2, parent_version_id=V1)
        proposal = MemoryProposal(P2, MemoryProposalIntent.NEW_VERSION, M1, V2, "agent-1", NOW)
        validate_proposal_links(current_memory, pending, proposal, (approved,))
        wrong_number = version(version_id=V3, version_number=3, parent_version_id=V1)
        wrong_proposal = MemoryProposal(P2, MemoryProposalIntent.NEW_VERSION, M1, V3, "agent-1", NOW)
        with self.assertRaises(ContractError):
            validate_proposal_links(current_memory, wrong_number, wrong_proposal, (approved,))
        wrong_parent = version(version_id=V3, version_number=2, parent_version_id=None)
        wrong_parent_proposal = MemoryProposal(P2, MemoryProposalIntent.NEW_VERSION, M1, V3, "agent-1", NOW)
        with self.assertRaises(ContractError):
            validate_proposal_links(current_memory, wrong_parent, wrong_parent_proposal, (approved,))

    def test_proposal_rejects_crossed_ids_and_timestamp(self):
        pending = version()
        proposal = MemoryProposal(P1, MemoryProposalIntent.CREATE_MEMORY, M1, V2, "agent-1", NOW)
        with self.assertRaises(ContractError):
            validate_proposal_links(memory(), pending, proposal)
        later = MemoryProposal(P1, MemoryProposalIntent.CREATE_MEMORY, M1, V1, "agent-1",
                               NOW + timedelta(seconds=1))
        with self.assertRaises(ContractError):
            validate_proposal_links(memory(), pending, later)

    def test_only_contractual_transitions_are_allowed(self):
        allowed = (
            (MemoryVersionStatus.PENDING_REVIEW, MemoryVersionStatus.APPROVED),
            (MemoryVersionStatus.PENDING_REVIEW, MemoryVersionStatus.REJECTED),
            (MemoryVersionStatus.APPROVED, MemoryVersionStatus.SUPERSEDED),
            (MemoryVersionStatus.APPROVED, MemoryVersionStatus.FORGOTTEN),
        )
        for current, target in allowed:
            validate_version_transition(current, target)
        for current in MemoryVersionStatus:
            for target in MemoryVersionStatus:
                if (current, target) not in allowed:
                    with self.subTest(current=current, target=target), self.assertRaises(ContractError):
                        validate_version_transition(current, target)
