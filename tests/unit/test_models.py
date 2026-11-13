from dataclasses import replace
from datetime import datetime, timezone
import unittest
from uuid import uuid4

from atlas.assistant.models import DomainEvent
from atlas.core.errors import ContractError
from atlas.core.identity import Identity, IdentityKind, IdentityStatus
from atlas.proactivity.models import ProactiveProposal
from tests.fixtures.contexts import user_context


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.context = user_context()

    def test_identity_and_context_reject_blank_values(self):
        with self.assertRaises(ContractError):
            Identity("  ", IdentityKind.AGENT, IdentityStatus.ACTIVE)
        with self.assertRaises(ContractError):
            replace(self.context, purpose=" ")

    def test_event_and_proactive_proposal_require_utc_and_context(self):
        event = DomainEvent(
            uuid4(),
            "assistant.responded",
            datetime.now(timezone.utc),
            self.context,
            {"result": "ok"},
        )
        self.assertEqual(event.context.correlation_id, "test-correlation")
        proposal = ProactiveProposal(
            uuid4(),
            "user-1",
            "reason",
            "suggest",
            self.context,
        )
        self.assertEqual(proposal.owner_id, "user-1")

    def test_naive_event_time_is_rejected(self):
        with self.assertRaises(ContractError):
            DomainEvent(
                uuid4(),
                "event",
                datetime(2026, 1, 1),
                self.context,
                {},
            )
