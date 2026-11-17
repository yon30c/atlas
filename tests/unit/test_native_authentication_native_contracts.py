import hashlib
import re
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from atlas.authentication.credentials import LoginHandle
from atlas.authentication.native import (
    NativeAuthenticationProof,
    NativeAuthenticationProofStatus,
    NativeAuthenticator,
    NativeAuthenticatorStatus,
    NativeProofReference,
    NativeSubject,
)
from atlas.core.errors import ContractError


def _id():
    return str(uuid4())


class NativeOpaqueValueTests(unittest.TestCase):
    def test_subject_is_random_256_bit_value_with_digest(self):
        first = NativeSubject.generate()
        second = NativeSubject.generate()
        self.assertNotEqual(first.value, second.value)
        self.assertEqual(len(first.value), 43)
        self.assertRegex(first.digest, re.compile(r"^[0-9a-f]{64}$"))
        self.assertEqual(first.digest, hashlib.sha256(first.value.encode("ascii")).hexdigest())
        self.assertNotIn(first.value, repr(first))

    def test_subject_rejects_noncanonical_or_short_values(self):
        for value in ("short", "a" * 42 + "=", "ñ" * 43):
            with self.subTest(value=value):
                with self.assertRaises(ContractError):
                    NativeSubject(value)

    def test_proof_reference_is_random_and_redacted(self):
        first = NativeProofReference.generate()
        second = NativeProofReference.generate()
        self.assertNotEqual(first.value, second.value)
        self.assertEqual(
            first.digest,
            hashlib.sha256(first.value.encode("ascii")).hexdigest(),
        )
        self.assertNotIn(first.value, repr(first))


class NativeAuthenticatorTests(unittest.TestCase):
    def _authenticator(self, **overrides):
        values = {
            "authenticator_id": _id(),
            "issuer_id": _id(),
            "native_subject": NativeSubject.generate(),
            "login_handle": LoginHandle("Atlas.Admin"),
            "password_hash_phc": "$argon2id$v=19$m=8192,t=1,p=1$c2FsdHNhbHRzYWx0c2FsdA$"
                                "aGFzaGFzaGFzaGFzaGFzaGFzaGFzaGFzaGFzaGFzaGFzaGFzaGFzaA",
        }
        values.update(overrides)
        return NativeAuthenticator(**values)

    def test_accepts_canonical_authenticator_without_identity_or_grant_fields(self):
        item = self._authenticator()
        self.assertEqual(item.login_handle.value, "atlas.admin")
        self.assertEqual(item.credential_revision, 1)
        self.assertIs(item.status, NativeAuthenticatorStatus.ACTIVE)
        self.assertNotIn("password_hash_phc", repr(item))

    def test_rejects_non_uuid4_ids_wrong_subject_hash_revision_and_status(self):
        invalid = (
            {"authenticator_id": "not-a-uuid"},
            {"issuer_id": "not-a-uuid"},
            {"native_subject": "subject"},
            {"password_hash_phc": "plaintext"},
            {"credential_revision": 0},
            {"credential_revision": True},
            {"status": "ACTIVE"},
        )
        for override in invalid:
            with self.subTest(override=override):
                with self.assertRaises(ContractError):
                    self._authenticator(**override)


class NativeAuthenticationProofTests(unittest.TestCase):
    def _proof(self, **overrides):
        now = datetime.now(timezone.utc)
        values = {
            "proof_id": _id(),
            "reference_digest": NativeProofReference.generate().digest,
            "issuer_id": _id(),
            "native_subject": NativeSubject.generate(),
            "authenticator_id": _id(),
            "credential_revision": 1,
            "authenticated_at": now,
            "expires_at": now + timedelta(minutes=2),
            "audience": "atlas.identity.consume-native-proof",
        }
        values.update(overrides)
        return NativeAuthenticationProof(**values)

    def test_persists_digest_not_raw_reference_and_defaults_pending(self):
        reference = NativeProofReference.generate()
        proof = self._proof(reference_digest=reference.digest)
        self.assertEqual(proof.reference_digest, reference.digest)
        self.assertIs(proof.status, NativeAuthenticationProofStatus.PENDING)
        self.assertFalse(hasattr(proof, "reference"))

    def test_rejects_invalid_digest_ids_revision_time_audience_and_status(self):
        now = datetime.now(timezone.utc)
        invalid = (
            {"proof_id": "not-a-uuid"},
            {"reference_digest": "A" * 64},
            {"issuer_id": "not-a-uuid"},
            {"authenticator_id": "not-a-uuid"},
            {"credential_revision": 0},
            {"authenticated_at": now.replace(tzinfo=None)},
            {"expires_at": now},
            {"audience": "https://untrusted.example"},
            {"status": "CONSUMED"},
        )
        for override in invalid:
            with self.subTest(override=override):
                with self.assertRaises(ContractError):
                    self._proof(**override)


if __name__ == "__main__":
    unittest.main()
