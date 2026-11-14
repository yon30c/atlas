"""Tests for the production local HMAC signer boundary."""
from dataclasses import replace
from datetime import datetime, timezone
import unittest

from atlas.core.errors import ContractError
from atlas.adapters.local_hmac_signer import HmacLocalConsistencySigner
from atlas.memory.envelope import AuthenticatedConsistencyEnvelope
from atlas.memory.local_auth import verify_envelope
from atlas.memory.local_keys import ActiveLocalConsistencyKey


class FakeActiveKeyProvider:
    def __init__(self, result):
        self.result = result

    def load_active_key(self):
        return self.result


class HmacLocalConsistencySignerTests(unittest.TestCase):
    def setUp(self):
        self.key = b"\xa7" * 32
        self.now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
        self.envelope = AuthenticatedConsistencyEnvelope(
            object_kind="journal_entry",
            envelope_version=1,
            consistency_domain_id="atlas-local",
            authority_epoch=1,
            sequence=1,
            object_id="record-1",
            schema_version=1,
            reducer_version="reducer-v1",
            previous_commitment=None,
            object_commitment="pending",
            issuer_id="atlas-journal",
            issuer_role="consistency-journal",
            key_reference="local-key-v1",
            trust_policy_version="local-policy-v1",
            issued_at=self.now,
            authentication_evidence="pending",
        )
        self.object_value = {"position": 1, "record": "opaque"}

    def test_signs_exact_envelope_and_object(self):
        provider = FakeActiveKeyProvider(
            ActiveLocalConsistencyKey("local-key-v1", self.key)
        )
        signer = HmacLocalConsistencySigner(provider)
        signed = signer.sign_envelope(self.envelope, self.object_value)
        self.assertEqual(signed.issued_at, self.now)
        self.assertEqual(signed.key_reference, "local-key-v1")
        self.assertTrue(verify_envelope(signed, self.object_value, self.key))

    def test_non_envelope_input_is_rejected(self):
        provider = FakeActiveKeyProvider(
            ActiveLocalConsistencyKey("local-key-v1", self.key)
        )
        signer = HmacLocalConsistencySigner(provider)
        with self.assertRaises(ContractError):
            signer.sign_envelope(None, self.object_value)

    def test_missing_active_key_aborts_signing(self):
        signer = HmacLocalConsistencySigner(FakeActiveKeyProvider(None))
        with self.assertRaises(OSError):
            signer.sign_envelope(self.envelope, self.object_value)

    def test_active_key_reference_must_match_envelope(self):
        provider = FakeActiveKeyProvider(
            ActiveLocalConsistencyKey("different-key", self.key)
        )
        signer = HmacLocalConsistencySigner(provider)
        with self.assertRaises(ContractError):
            signer.sign_envelope(self.envelope, self.object_value)

    def test_invalid_provider_result_is_rejected(self):
        signer = HmacLocalConsistencySigner(FakeActiveKeyProvider(b"not-a-key-object"))
        with self.assertRaises(ContractError):
            signer.sign_envelope(self.envelope, self.object_value)

    def test_provider_exception_propagates_to_journal_boundary(self):
        class BrokenProvider:
            def load_active_key(self):
                raise OSError("credential unavailable")

        signer = HmacLocalConsistencySigner(BrokenProvider())
        with self.assertRaises(OSError):
            signer.sign_envelope(self.envelope, self.object_value)


if __name__ == "__main__":
    unittest.main()
