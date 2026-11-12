import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

from atlas.authorization.models import (
    GrantRenewalRequest,
    RenewalStatus,
)
from atlas.core.errors import ContractError


NOW = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)


class GrantRenewalRequestTests(unittest.TestCase):
    def setUp(self):
        self.request = GrantRenewalRequest(
            renewal_id="renewal-001",
            grant_id="grant-001",
            owner_user_id="user-001",
            subject_identity_id="agent-001",
            requested_by_identity_id="agent-001",
            current_expires_at=NOW + timedelta(days=2),
            proposed_expires_at=NOW + timedelta(days=9),
            requested_at=NOW,
        )

    def test_accepts_valid_pending_request(self):
        self.assertEqual(self.request.status, RenewalStatus.PENDING)
        self.assertIsNone(self.request.decided_at)

    def test_request_is_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            self.request.status = RenewalStatus.APPROVED

    def test_version_must_be_a_positive_non_boolean_integer(self):
        self.assertEqual(self.request.version, 1)
        for version in (True, False, 0, -1, 1.0, "1"):
            with self.subTest(version=version):
                with self.assertRaises(ContractError):
                    replace(self.request, version=version)

    def test_required_identifiers_reject_blank_values(self):
        fields = (
            "renewal_id",
            "grant_id",
            "owner_user_id",
            "subject_identity_id",
            "requested_by_identity_id",
        )
        for field in fields:
            with self.subTest(field=field):
                with self.assertRaises(ContractError):
                    replace(self.request, **{field: "  "})

    def test_proposed_expiration_must_be_later(self):
        for proposed_expires_at in (
            self.request.current_expires_at,
            self.request.current_expires_at - timedelta(seconds=1),
        ):
            with self.subTest(proposed_expires_at=proposed_expires_at):
                with self.assertRaises(ContractError):
                    replace(
                        self.request,
                        proposed_expires_at=proposed_expires_at,
                    )

    def test_all_timestamps_must_be_utc_aware(self):
        invalid_timestamps = (
            ("current_expires_at", datetime(2026, 11, 14, 15, 0)),
            (
                "proposed_expires_at",
                datetime(
                    2026,
                    11,
                    21,
                    16,
                    0,
                    tzinfo=timezone(timedelta(hours=1)),
                ),
            ),
            ("requested_at", datetime(2026, 11, 12, 15, 0)),
        )
        for field, value in invalid_timestamps:
            with self.subTest(field=field):
                with self.assertRaises(ContractError):
                    replace(self.request, **{field: value})

        approved = replace(
            self.request,
            status=RenewalStatus.APPROVED,
            decided_at=NOW + timedelta(hours=1),
            decided_by_user_id="user-001",
        )
        with self.assertRaises(ContractError):
            replace(approved, decided_at=datetime(2026, 11, 12, 16, 0))

    def test_status_and_decision_metadata_must_be_consistent(self):
        with self.assertRaises(ContractError):
            replace(self.request, status="approved")
        with self.assertRaises(ContractError):
            replace(self.request, decided_by_user_id="user-001")
        with self.assertRaises(ContractError):
            replace(self.request, status=RenewalStatus.APPROVED)

        for status in (RenewalStatus.APPROVED, RenewalStatus.REJECTED):
            with self.subTest(status=status):
                decided_request = replace(
                    self.request,
                    status=status,
                    decided_at=NOW + timedelta(hours=1),
                    decided_by_user_id="user-001",
                )
                self.assertIs(decided_request.status, status)


if __name__ == "__main__":
    unittest.main()
