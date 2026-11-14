from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import unittest

from atlas.core.errors import ContractError
from atlas.core import enums as core_enums
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


M1 = "018f0f00-0000-7000-8000-000000000001"
V1 = "018f0f00-0000-7000-8000-000000000002"
P1 = "018f0f00-0000-7000-8000-000000000003"
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def provenance(evidence_refs=()):
    context = ProvenanceContext("chat", "identity-1", "request-1", "correlation-1")
    return MemoryProvenance(
        SourceKind.USER_INPUT, None, NOW, "identity-1", context,
        transformation="captured from user input", evidence_refs=evidence_refs,
    )


def version(**overrides):
    values = dict(
        version_id=V1, memory_id=M1, version_number=1, content="fact",
        classification=MemoryClassification.CONFIDENTIAL,
        status=MemoryVersionStatus.PENDING_REVIEW, provenance=provenance(),
        parent_version_id=None, created_at=NOW, submitted_at=NOW,
    )
    values.update(overrides)
    return MemoryVersion(**values)


class MemoryModelTests(unittest.TestCase):
    def test_scope_private_and_project(self):
        self.assertEqual(MemoryScope(MemoryScopeKind.PRIVATE).project_id, None)
        self.assertEqual(MemoryScope(MemoryScopeKind.PROJECT, "project:opaque").project_id, "project:opaque")
        with self.assertRaises(ContractError):
            MemoryScope(MemoryScopeKind.PRIVATE, "project-1")
        with self.assertRaises(ContractError):
            MemoryScope(MemoryScopeKind.PROJECT)

    def test_ids_require_canonical_uuid7_but_external_ids_are_opaque(self):
        Memory(M1, "external:user/42", MemoryScope(MemoryScopeKind.PRIVATE), None, NOW, NOW)
        for invalid in ("", "not-a-uuid", "018f0f00-0000-4000-8000-000000000001",
                        "018F0F00-0000-7000-8000-000000000001"):
            with self.subTest(invalid=invalid), self.assertRaises(ContractError):
                Memory(invalid, "user-1", MemoryScope(MemoryScopeKind.PRIVATE), None, NOW, NOW)

    def test_memory_timestamps_and_pointer(self):
        with self.assertRaises(ContractError):
            Memory(M1, "user-1", MemoryScope(MemoryScopeKind.PRIVATE), None, NOW, NOW - timedelta(seconds=1))
        with self.assertRaises(ContractError):
            Memory(M1, "user-1", MemoryScope(MemoryScopeKind.PRIVATE),
                   "018f0f00-0000-4000-8000-000000000002", NOW, NOW)

    def test_version_validates_content_number_status_and_review(self):
        self.assertEqual(version().version_number, 1)
        for invalid_number in (0, -1, True, 1.0):
            with self.subTest(number=invalid_number), self.assertRaises(ContractError):
                version(version_number=invalid_number)
        for content in ("", "  \n"):
            with self.subTest(content=content), self.assertRaises(ContractError):
                version(content=content)
        with self.assertRaises(ContractError):
            version(status=MemoryVersionStatus.APPROVED)
        with self.assertRaises(ContractError):
            version(status=MemoryVersionStatus.PENDING_REVIEW, reviewed_by="user-1")

    def test_reviewed_status_requires_review_metadata(self):
        reviewed = version(
            status=MemoryVersionStatus.APPROVED,
            reviewed_at=NOW + timedelta(seconds=1),
            reviewed_by="user-owner",
        )
        self.assertEqual(reviewed.status, MemoryVersionStatus.APPROVED)

    def test_models_and_nested_collections_are_immutable(self):
        ref = OpaqueReference("file", "file-id-1", ReferenceAvailability.AVAILABLE)
        model = provenance((ref,))
        with self.assertRaises(FrozenInstanceError):
            model.captured_by = "other"
        with self.assertRaises(ContractError):
            MemoryProvenance(SourceKind.FILE, None, NOW, "identity-1",
                             model.origin_context, evidence_refs=[ref])
        with self.assertRaises(ContractError):
            MemoryProvenance(SourceKind.FILE, None, NOW, "identity-1",
                             model.origin_context, evidence_refs=({"payload": "x"},))
        self.assertEqual(model.evidence_refs, (ref,))

    def test_provenance_catalog_references_and_urls(self):
        ref = OpaqueReference("file", "opaque-id", ReferenceAvailability.UNAVAILABLE)
        self.assertEqual(ref.availability, ReferenceAvailability.UNAVAILABLE)
        with self.assertRaises(ContractError):
            OpaqueReference("file", "https://user:secret@example.com/file", ReferenceAvailability.AVAILABLE)
        with self.assertRaises(ContractError):
            MemoryProvenance("UNKNOWN", None, NOW, "identity-1", provenance().origin_context)
        with self.assertRaises(ContractError):
            MemoryProvenance(SourceKind.FILE, None, NOW, "identity-1",
                             provenance().origin_context, transformation=" ")

    def test_proposal_uses_identity_not_owner_or_operation_context(self):
        proposal = MemoryProposal(P1, MemoryProposalIntent.CREATE_MEMORY, M1, V1, "agent-7", NOW)
        self.assertEqual(proposal.submitted_by, "agent-7")
        with self.assertRaises(ContractError):
            MemoryProposal("not-uuid7", MemoryProposalIntent.CREATE_MEMORY, M1, V1, "agent-7", NOW)

    def test_timestamps_must_be_explicit_utc(self):
        with self.assertRaises(ContractError):
            Memory(M1, "user-1", MemoryScope(MemoryScopeKind.PRIVATE), None,
                   datetime(2026, 1, 1), NOW)
        with self.assertRaises(ContractError):
            version(submitted_at=datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=2))))

    def test_legacy_memory_status_is_not_part_of_the_new_domain(self):
        self.assertFalse(hasattr(core_enums, "MemoryStatus"))
