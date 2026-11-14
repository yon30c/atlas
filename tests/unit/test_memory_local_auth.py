"""Tests for canonical JSON and local HMAC primitives; run on Debian."""
from dataclasses import replace
from datetime import datetime, timezone
import unittest

from atlas.core.errors import ContractError
from atlas.memory.local_auth import (
    authenticate_envelope, canonical_json_bytes, object_commitment, verify_envelope,
)
from atlas.memory.trust import AuthenticatedConsistencyEnvelope


class CanonicalJsonTests(unittest.TestCase):
    def test_mapping_key_order_does_not_change_bytes(self):
        self.assertEqual(canonical_json_bytes({"b": 2, "a": 1}),
                         canonical_json_bytes({"a": 1, "b": 2}))

    def test_set_order_does_not_change_bytes(self):
        self.assertEqual(canonical_json_bytes({"items": frozenset({"b", "a"})}),
                         canonical_json_bytes({"items": frozenset({"a", "b"})}))

    def test_utc_datetime_is_normalized(self):
        value = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
        self.assertIn(b"2026-11-13T12:00:00.000000Z", canonical_json_bytes(value))

    def test_decimal_values_are_rejected(self):
        with self.assertRaises(ContractError):
            canonical_json_bytes({"amount": 1.25})

    def test_non_string_mapping_keys_are_rejected(self):
        with self.assertRaises(ContractError):
            canonical_json_bytes({1: "value"})


class LocalHmacTests(unittest.TestCase):
    def setUp(self):
        self.key = b"k" * 32
        self.now = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
        self.envelope = AuthenticatedConsistencyEnvelope(
            object_kind="journal_entry", envelope_version=1,
            consistency_domain_id="atlas-main", authority_epoch=1, sequence=1,
            object_id="record-1", schema_version=1, reducer_version="reducer-v1",
            previous_commitment=None, object_commitment="0" * 64,
            issuer_id="local-journal", issuer_role="consistency-journal",
            key_reference="local-key-1", trust_policy_version="local-policy-v1",
            issued_at=self.now, authentication_evidence="pending",
        )

    def test_authenticate_and_verify_exact_object(self):
        value = {"record": "one", "sequence": 1}
        signed = authenticate_envelope(self.envelope, value, self.key)
        self.assertEqual(signed.object_commitment, object_commitment(value))
        self.assertTrue(verify_envelope(signed, value, self.key))

    def test_modified_object_is_rejected(self):
        signed = authenticate_envelope(self.envelope, {"record": "one"}, self.key)
        self.assertFalse(verify_envelope(signed, {"record": "two"}, self.key))

    def test_modified_metadata_is_rejected(self):
        signed = authenticate_envelope(self.envelope, {"record": "one"}, self.key)
        self.assertFalse(verify_envelope(
            replace(signed, issuer_role="other-role"), {"record": "one"}, self.key
        ))

    def test_wrong_key_is_rejected(self):
        signed = authenticate_envelope(self.envelope, {"record": "one"}, self.key)
        self.assertFalse(verify_envelope(signed, {"record": "one"}, b"x" * 32))

    def test_wrong_key_length_is_rejected_when_signing(self):
        with self.assertRaises(ContractError):
            authenticate_envelope(self.envelope, {"record": "one"}, b"short")


if __name__ == "__main__":
    unittest.main()
