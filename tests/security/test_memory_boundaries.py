from datetime import datetime, timezone
import importlib.util
import inspect
import unittest
from typing import get_type_hints

from atlas.memory.models import MemoryProposal, MemoryProposalIntent
from atlas.memory.forget_coordinator import (
    ForgetCanonicalStateReceipt,
    ForgetDeletionAttempt,
    ForgetDestinationInventory,
    ForgetOperation,
    ForgetVerificationReceipt,
)
from atlas.memory.journal import ConsistencyTransition
from atlas.memory.journal_reducer import ConsistencyProjection
from atlas.memory.gateway import MemoryGatewayService
from atlas.ports.memory import MemoryGateway
from atlas.ports.protected_memory_read import ProtectedMemoryRead


M1 = "018f0f00-0000-7000-8000-000000000001"
V1 = "018f0f00-0000-7000-8000-000000000002"
P1 = "018f0f00-0000-7000-8000-000000000003"


class MemoryBoundarySecurityTests(unittest.TestCase):
    def test_proposal_does_not_claim_or_carry_memory_ownership(self):
        proposal = MemoryProposal(
            P1, MemoryProposalIntent.CREATE_MEMORY, M1, V1, "agent:delegate",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(proposal.submitted_by, "agent:delegate")
        self.assertNotIn("owner_id", MemoryProposal.__dataclass_fields__)
        self.assertNotIn("context", MemoryProposal.__dataclass_fields__)

    def test_gateway_never_returns_raw_memory_versions(self):
        return_type = get_type_hints(MemoryGateway.get_version)["return"]
        self.assertEqual(return_type, ProtectedMemoryRead | None)
        self.assertTrue(hasattr(MemoryGateway, "emit_version"))
        self.assertTrue(hasattr(MemoryGateway, "finish_version"))
        self.assertIsNone(importlib.util.find_spec("atlas.ports.memory_content"))


    def test_gateway_injects_one_consistency_boundary_not_split_authority_and_egress(self):
        parameters = inspect.signature(MemoryGatewayService.__init__).parameters
        self.assertIn("consistency", parameters)
        self.assertNotIn("consistency_authority", parameters)
        self.assertNotIn("egress", parameters)

    def test_forget_and_journal_evidence_models_cannot_carry_memory_payloads(self):
        forbidden = {
            "content", "payload", "content_hash", "snippet", "embedding",
            "raw_text", "memory_body",
        }
        evidence_types = (
            ForgetCanonicalStateReceipt,
            ForgetDeletionAttempt,
            ForgetDestinationInventory,
            ForgetOperation,
            ForgetVerificationReceipt,
            ConsistencyTransition,
            ConsistencyProjection,
        )
        for evidence_type in evidence_types:
            self.assertFalse(
                forbidden.intersection(evidence_type.__dataclass_fields__),
                evidence_type.__name__,
            )

    def test_gateway_is_the_explicit_memory_port(self):
        self.assertTrue(hasattr(MemoryGateway, "list_visible"))
        self.assertTrue(hasattr(MemoryGateway, "submit_proposal"))
        # Domain models expose no storage/session/SQL handles.
        from atlas.memory.models import Memory

        self.assertFalse(
            any(
                "connection" in field
                or "session" in field
                or "repository" in field
                for field in Memory.__dataclass_fields__
            )
        )
