import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from atlas.core.errors import ContractError
from atlas.core.native_identity import (
    NativeIdentityBinding,
    NativeIdentityBindingStatus,
    NativeIdentityIssuer,
    NativeIssuerProfile,
    NativeIssuerStatus,
)


def _id():
    return str(uuid4())


class NativeIdentityIssuerTests(unittest.TestCase):
    def _issuer(self, **overrides):
        values = {
            "issuer_id": _id(),
            "realm": "atlas.primary",
            "profile": NativeIssuerProfile.NATIVE_AUTHORITY_PROOF,
            "status": NativeIssuerStatus.ACTIVE,
        }
        values.update(overrides)
        return NativeIdentityIssuer(**values)

    def test_accepts_stable_native_realm_and_profile(self):
        issuer = self._issuer()
        self.assertEqual(issuer.realm, "atlas.primary")
        self.assertIs(issuer.profile, NativeIssuerProfile.NATIVE_AUTHORITY_PROOF)
        self.assertEqual(issuer.revision, 1)

    def test_rejects_noncanonical_id_realm_profile_status_and_revision(self):
        invalid = (
            {"issuer_id": "not-a-uuid"},
            {"realm": "Atlas.Primary"},
            {"realm": "host:atlas"},
            {"realm": "x"},
            {"profile": "EXTERNAL_CRYPTOGRAPHIC"},
            {"status": "ACTIVE"},
            {"revision": 0},
            {"revision": True},
        )
        for override in invalid:
            with self.subTest(override=override):
                with self.assertRaises(ContractError):
                    self._issuer(**override)


class NativeIdentityBindingTests(unittest.TestCase):
    def _binding(self, **overrides):
        now = datetime.now(timezone.utc)
        values = {
            "binding_id": _id(),
            "identity_id": _id(),
            "issuer_id": _id(),
            "subject_digest": "a" * 64,
            "status": NativeIdentityBindingStatus.ACTIVE,
            "created_at": now,
            "verified_at": now,
        }
        values.update(overrides)
        return NativeIdentityBinding(**values)

    def test_accepts_active_binding_with_canonical_references(self):
        binding = self._binding()
        self.assertEqual(binding.revision, 1)
        self.assertIsNone(binding.revoked_at)

    def test_accepts_revoked_tombstone(self):
        now = datetime.now(timezone.utc)
        binding = self._binding(
            status=NativeIdentityBindingStatus.REVOKED,
            revoked_at=now + timedelta(seconds=1),
            revision=2,
        )
        self.assertEqual(binding.revision, 2)
        self.assertIsNotNone(binding.revoked_at)

    def test_rejects_invalid_ids_digest_status_revision_and_timestamps(self):
        now = datetime.now(timezone.utc)
        invalid = (
            {"binding_id": "not-a-uuid"},
            {"identity_id": "not-a-uuid"},
            {"issuer_id": "not-a-uuid"},
            {"subject_digest": "A" * 64},
            {"status": "ACTIVE"},
            {"revision": 0},
            {"revision": True},
            {"created_at": None},
            {"verified_at": now.replace(tzinfo=None)},
            {"verified_at": now - timedelta(seconds=1)},
            {"revoked_at": now},
        )
        for override in invalid:
            with self.subTest(override=override):
                with self.assertRaises(ContractError):
                    self._binding(**override)

    def test_active_binding_cannot_have_revocation_timestamp(self):
        now = datetime.now(timezone.utc)
        with self.assertRaises(ContractError):
            self._binding(revoked_at=now + timedelta(seconds=1))


if __name__ == "__main__":
    unittest.main()
