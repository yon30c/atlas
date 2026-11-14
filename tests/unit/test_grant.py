from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import unittest

from atlas.authorization.models import Grant, GrantResourceScope
from atlas.core.errors import ContractError


class GrantTests(unittest.TestCase):
    def setUp(self):
        self.issued_at = datetime(
            2026, 11, 12, 10, 0, tzinfo=timezone.utc
        )
        self.grant = Grant(
            grant_id="grant-001",
            owner_user_id="user-001",
            subject_identity_id="agent-001",
            project_id="atlas",
            environment="development",
            resource_scope=GrantResourceScope("files", frozenset({"file-001"})),
            actions=frozenset({"read", "write"}),
            issued_at=self.issued_at,
            expires_at=self.issued_at + timedelta(days=7),
        )

    def test_accepts_valid_grant(self):
        self.assertEqual(self.grant.resource_type, "files")
        self.assertEqual(
            self.grant.actions,
            frozenset({"read", "write"}),
        )
        self.assertIsNone(self.grant.revoked_at)
        self.assertEqual(self.grant.resource_ids, frozenset({"file-001"}))

    def test_resource_scope_rejects_empty_mutable_and_pattern_ids(self):
        for invalid in (frozenset(), {"file-001"}, frozenset({"*"}), frozenset({"file-?"})):
            with self.subTest(invalid=invalid), self.assertRaises(ContractError):
                GrantResourceScope("files", invalid)

    def test_grant_revision_must_be_positive(self):
        with self.assertRaises(ContractError):
            replace(self.grant, revision=0)
        with self.assertRaises(ContractError):
            replace(self.grant, revision=True)

    def test_grant_is_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            self.grant.owner_user_id = "user-002"

    def test_required_fields_reject_blank_values(self):
        fields = (
            "grant_id",
            "owner_user_id",
            "subject_identity_id",
            "project_id",
            "environment",
        )
        for field in fields:
            with self.subTest(field=field):
                with self.assertRaises(ContractError):
                    replace(self.grant, **{field: "  "})

    def test_actions_must_be_a_nonempty_frozenset(self):
        with self.assertRaises(ContractError):
            replace(self.grant, actions={"read"})

        with self.assertRaises(ContractError):
            Grant(
                grant_id="grant-001",
                owner_user_id="user-001",
                subject_identity_id="agent-001",
                project_id="atlas",
                environment="development",
                resource_scope=GrantResourceScope("files", frozenset({"file-001"})),
                actions=frozenset(),
                issued_at=self.issued_at,
                expires_at=self.issued_at + timedelta(days=7),
            )

    def test_actions_reject_blank_and_wildcard_values(self):
        for actions in (frozenset({" "}), frozenset({"*"})):
            with self.subTest(actions=actions):
                with self.assertRaises(ContractError):
                    replace(self.grant, actions=actions)

    def test_issued_at_and_expires_at_must_be_utc_aware(self):
        invalid_times = (
            ("issued_at", datetime(2026, 11, 12, 10, 0)),
            (
                "issued_at",
                datetime(
                    2026,
                    11,
                    12,
                    10,
                    0,
                    tzinfo=timezone(timedelta(hours=1)),
                ),
            ),
            ("expires_at", datetime(2026, 11, 19, 10, 0)),
            (
                "expires_at",
                datetime(
                    2026,
                    11,
                    19,
                    10,
                    0,
                    tzinfo=timezone(timedelta(hours=1)),
                ),
            ),
        )
        for field, value in invalid_times:
            with self.subTest(field=field, value=value):
                with self.assertRaises(ContractError):
                    replace(self.grant, **{field: value})

    def test_expiration_must_be_after_issue_time(self):
        with self.assertRaises(ContractError):
            replace(self.grant, expires_at=self.issued_at)

    def test_revoked_at_must_be_utc_aware_when_present(self):
        revoked_at = self.issued_at + timedelta(days=1)
        self.assertEqual(
            replace(self.grant, revoked_at=revoked_at).revoked_at,
            revoked_at,
        )

        with self.assertRaises(ContractError):
            replace(
                self.grant,
                revoked_at=datetime(2026, 11, 13, 10, 0),
            )


if __name__ == "__main__":
    unittest.main()
