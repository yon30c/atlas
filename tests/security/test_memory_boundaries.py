import unittest

from atlas.core.errors import ContractError
from atlas.memory.models import MemoryProposal
from atlas.ports.memory import MemoryGateway
from tests.fixtures.contexts import user_context


class MemoryBoundarySecurityTests(unittest.TestCase):
    def test_proposal_cannot_claim_another_users_ownership(self):
        context = user_context("alice")
        with self.assertRaises(ContractError):
            MemoryProposal("bob", "private fact", context)

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
