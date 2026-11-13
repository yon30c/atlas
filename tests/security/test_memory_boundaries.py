from datetime import datetime, timezone
import unittest

from atlas.memory.models import MemoryProposal, MemoryProposalIntent
from atlas.ports.memory import MemoryGateway


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
