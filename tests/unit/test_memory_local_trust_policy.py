"""Tests for the independent local recovery trust policy."""
from dataclasses import replace
from datetime import datetime, timezone
import unittest

from atlas.core.errors import ContractError
from atlas.memory.envelope import AuthenticatedConsistencyEnvelope
from atlas.memory.local_trust_policy import (
    LocalConsistencyTrustPolicy,
    LocalIssuerAuthorization,
)


class LocalConsistencyTrustPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = LocalConsistencyTrustPolicy(
            policy_version="local-policy-v1",
            consistency_domain_id="atlas-main",
            issuer_authorizations=frozenset({
                LocalIssuerAuthorization(
                    "journal_entry", "journal-writer", "consistency-journal"
                ),
                LocalIssuerAuthorization(
                    "checkpoint", "checkpoint-writer", "consistency-checkpoint"
                ),
            }),
            allowed_key_references=frozenset({"key-journal-1", "key-checkpoint-1"}),
            allowed_envelope_versions=frozenset({1}),
            allowed_canonicalization_versions=frozenset({1}),
            allowed_schema_versions=frozenset({1, 2}),
            allowed_reducer_versions=frozenset({"reducer-v1"}),
        )
        self.envelope = AuthenticatedConsistencyEnvelope(
            object_kind="journal_entry",
            envelope_version=1,
            consistency_domain_id="atlas-main",
            authority_epoch=1,
            sequence=1,
            object_id="record-1",
            schema_version=1,
            reducer_version="reducer-v1",
            previous_commitment=None,
            object_commitment="0" * 64,
            issuer_id="journal-writer",
            issuer_role="consistency-journal",
            key_reference="key-journal-1",
            trust_policy_version="local-policy-v1",
            issued_at=datetime(2026, 11, 14, tzinfo=timezone.utc),
            authentication_evidence="pending",
        )

    def test_accepts_exact_authorized_envelope_claims(self):
        self.assertTrue(self.policy.authorizes_envelope(self.envelope))

    def test_rejects_unapproved_issuer_role_pair_even_if_each_value_exists(self):
        forged_pair = replace(
            self.envelope,
            issuer_id="checkpoint-writer",
            issuer_role="consistency-journal",
        )
        self.assertFalse(self.policy.authorizes_envelope(forged_pair))

    def test_rejects_unapproved_key_reference(self):
        self.assertFalse(self.policy.authorizes_envelope(
            replace(self.envelope, key_reference="key-from-backup")
        ))

    def test_rejects_policy_version_mismatch(self):
        self.assertFalse(self.policy.authorizes_envelope(
            replace(self.envelope, trust_policy_version="policy-from-backup")
        ))

    def test_rejects_unapproved_reducer_schema_or_domain(self):
        for changed in (
            replace(self.envelope, reducer_version="reducer-v2"),
            replace(self.envelope, schema_version=9),
            replace(self.envelope, consistency_domain_id="other-domain"),
            replace(self.envelope, envelope_version=2),
        ):
            with self.subTest(changed=changed):
                self.assertFalse(self.policy.authorizes_envelope(changed))

    def test_canonicalization_version_must_be_explicitly_allowed(self):
        self.assertTrue(self.policy.supports_canonicalization(1))
        self.assertFalse(self.policy.supports_canonicalization(2))
        self.assertFalse(self.policy.supports_canonicalization(True))

    def test_empty_authorization_or_key_allowlist_is_rejected(self):
        with self.assertRaises(ContractError):
            replace(self.policy, issuer_authorizations=frozenset())
        with self.assertRaises(ContractError):
            replace(self.policy, allowed_key_references=frozenset())

    def test_non_positive_versions_are_rejected(self):
        with self.assertRaises(ContractError):
            replace(self.policy, allowed_reducer_versions=frozenset({"reducer-v1"}),
                    allowed_envelope_versions=frozenset({0}))


if __name__ == "__main__":
    unittest.main()
