"""Tests for the dedicated systemd Identity HMAC credential adapter."""
from pathlib import Path
import tempfile
import unittest

from atlas.adapters.systemd_identity_attestor import (
    SystemdCredentialVerifiedIdentityContextAttestor,
)
from atlas.core.errors import ContractError


class SystemdCredentialVerifiedIdentityContextAttestorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.credentials = self.root / "credentials"
        self.credentials.mkdir()
        self.key = b"I" * 32
        (self.credentials / "atlas-identity-hmac-v1").write_bytes(self.key)

    def tearDown(self):
        self.temporary.cleanup()

    def build(self, directory=None, name="atlas-identity-hmac-v1"):
        return SystemdCredentialVerifiedIdentityContextAttestor(
            directory or self.credentials,
            name,
        )

    def test_sign_and_verify_uses_loaded_identity_credential(self):
        attestor = self.build()
        payload = b"verified-identity-context-v1"
        signature = attestor.sign(payload)
        self.assertTrue(attestor.verify(payload, signature))
        self.assertFalse(attestor.verify(payload + b"-changed", signature))

    def test_missing_credential_fails_composition(self):
        (self.credentials / "atlas-identity-hmac-v1").unlink()
        with self.assertRaises(ContractError):
            self.build()

    def test_wrong_length_credential_fails_composition(self):
        (self.credentials / "atlas-identity-hmac-v1").write_bytes(b"short")
        with self.assertRaises(ContractError):
            self.build()

    def test_symlink_credential_is_rejected(self):
        target = self.root / "outside"
        target.write_bytes(self.key)
        (self.credentials / "atlas-identity-hmac-v1").unlink()
        (self.credentials / "atlas-identity-hmac-v1").symlink_to(target)
        with self.assertRaises(ContractError):
            self.build()

    def test_non_regular_credential_is_rejected(self):
        (self.credentials / "atlas-identity-hmac-v1").unlink()
        (self.credentials / "atlas-identity-hmac-v1").mkdir()
        with self.assertRaises(ContractError):
            self.build()

    def test_symlink_credentials_directory_is_rejected(self):
        alias = self.root / "credentials-link"
        alias.symlink_to(self.credentials, target_is_directory=True)
        with self.assertRaises(ContractError):
            self.build(directory=alias)

    def test_symlinked_parent_of_credentials_directory_is_rejected(self):
        parent = self.root / "parent"
        parent.mkdir()
        (parent / "credentials").mkdir()
        alias = self.root / "parent-link"
        alias.symlink_to(parent, target_is_directory=True)
        with self.assertRaises(ContractError):
            self.build(directory=alias / "credentials")

    def test_credential_name_must_be_a_single_safe_component(self):
        for name in ("../key", "/tmp/key", "nested/key", "", ".", ".."):
            with self.subTest(name=name):
                with self.assertRaises(ContractError):
                    self.build(name=name)

    def test_key_material_is_not_exposed_by_repr(self):
        attestor = self.build()
        self.assertNotIn(self.key.decode("ascii"), repr(attestor))


if __name__ == "__main__":
    unittest.main()
