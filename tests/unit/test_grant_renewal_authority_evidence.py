from datetime import datetime, timedelta, timezone
import unittest

from atlas.authorization.models import GrantRenewalRequest
from atlas.core.errors import ContractError


NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)


class GrantRenewalAuthorityEvidenceModelTests(unittest.TestCase):
    def base(self):
        return dict(
            renewal_id="renewal-001",
            grant_id="grant-001",
            owner_user_id="owner-001",
            subject_identity_id="agent-001",
            requested_by_identity_id="agent-001",
            current_expires_at=NOW + timedelta(days=1),
            proposed_expires_at=NOW + timedelta(days=2),
            requested_at=NOW,
        )

    def test_legacy_owner_request_may_omit_agent_evidence(self):
        request = GrantRenewalRequest(**self.base())
        self.assertIsNone(request.grant_revision)
        self.assertIsNone(request.delegation_id)
        self.assertIsNone(request.delegation_revision)

    def test_agent_evidence_requires_all_immutable_bindings(self):
        for values in (
            {"grant_revision": 4},
            {"delegation_id": "delegation-001"},
            {"delegation_revision": 2},
            {"grant_revision": 4, "delegation_id": "delegation-001"},
            {"grant_revision": 4, "delegation_revision": 2},
        ):
            with self.subTest(values=values):
                with self.assertRaises(ContractError):
                    GrantRenewalRequest(**self.base(), **values)

    def test_complete_agent_evidence_is_accepted(self):
        request = GrantRenewalRequest(
            **self.base(),
            grant_revision=4,
            delegation_id="22222222-2222-4222-8222-222222222222",
            delegation_revision=2,
        )
        self.assertEqual(request.grant_revision, 4)
        self.assertEqual(request.delegation_revision, 2)


if __name__ == "__main__":
    unittest.main()
