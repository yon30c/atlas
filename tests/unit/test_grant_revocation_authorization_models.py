from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import unittest

from atlas.authorization.models import (
    GrantRevocationAuthorizationRequest,
    VerifiedGrantRevocationAuthorization,
)
from atlas.core.errors import ContractError


NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


class GrantRevocationAuthorizationModelTests(unittest.TestCase):
    def setUp(self):
        self.request = GrantRevocationAuthorizationRequest(
            request_id="request-001",
            actor_identity_id="user-001",
            owner_user_id="user-001",
            grant_id="grant-001",
            expected_revision=3,
            requested_at=NOW,
        )
        self.proof = VerifiedGrantRevocationAuthorization(
            proof_id="proof-001",
            decision_id="decision-001",
            request_id="request-001",
            actor_identity_id="user-001",
            owner_user_id="user-001",
            grant_id="grant-001",
            expected_revision=3,
            issued_at=NOW,
            expires_at=NOW + timedelta(minutes=5),
            issuer_id="cam-authority-001",
        )

    def test_request_accepts_exact_grant_owner_and_revision_context(self):
        self.assertEqual(self.request.grant_id, "grant-001")
        self.assertEqual(self.request.expected_revision, 3)

    def test_request_rejects_blank_identifiers(self):
        for field in (
            "request_id",
            "actor_identity_id",
            "owner_user_id",
            "grant_id",
        ):
            with self.subTest(field=field):
                with self.assertRaises(ContractError):
                    replace(self.request, **{field: " "})

    def test_request_requires_positive_non_boolean_revision(self):
        for revision in (0, -1, True, 1.5):
            with self.subTest(revision=revision):
                with self.assertRaises(ContractError):
                    replace(self.request, expected_revision=revision)

    def test_request_requires_utc_timestamp(self):
        invalid_times = (
            datetime(2026, 11, 14, 12, 0),
            datetime(2026, 11, 14, 13, 0, tzinfo=timezone(timedelta(hours=1))),
        )
        for requested_at in invalid_times:
            with self.subTest(requested_at=requested_at):
                with self.assertRaises(ContractError):
                    replace(self.request, requested_at=requested_at)

    def test_evidence_accepts_valid_immutable_claims(self):
        self.assertEqual(self.proof.request_id, self.request.request_id)
        self.assertEqual(self.proof.grant_id, self.request.grant_id)
        self.assertEqual(self.proof.expected_revision, self.request.expected_revision)
        with self.assertRaises(FrozenInstanceError):
            self.proof.grant_id = "other-grant"

    def test_evidence_rejects_blank_identifiers(self):
        for field in (
            "proof_id",
            "decision_id",
            "request_id",
            "actor_identity_id",
            "owner_user_id",
            "grant_id",
            "issuer_id",
        ):
            with self.subTest(field=field):
                with self.assertRaises(ContractError):
                    replace(self.proof, **{field: " "})

    def test_evidence_requires_positive_non_boolean_revision(self):
        for revision in (0, -1, True, 2.5):
            with self.subTest(revision=revision):
                with self.assertRaises(ContractError):
                    replace(self.proof, expected_revision=revision)

    def test_evidence_requires_utc_timestamps(self):
        invalid_times = (
            datetime(2026, 11, 14, 12, 0),
            datetime(2026, 11, 14, 13, 0, tzinfo=timezone(timedelta(hours=1))),
        )
        for field in ("issued_at", "expires_at"):
            for value in invalid_times:
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ContractError):
                        replace(self.proof, **{field: value})

    def test_evidence_expiration_must_follow_issuance(self):
        with self.assertRaises(ContractError):
            replace(self.proof, expires_at=NOW)
        with self.assertRaises(ContractError):
            replace(self.proof, expires_at=NOW - timedelta(seconds=1))


if __name__ == "__main__":
    unittest.main()
