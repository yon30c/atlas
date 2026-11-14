"""Tests for strict systemd credential key resolution without systemd runtime."""
import tempfile
import unittest
from pathlib import Path

from atlas.core.errors import ContractError
from atlas.adapters.systemd_credentials import (
    ConfiguredActiveLocalConsistencyKeyProvider,
    SystemdCredentialKeyProvider,
)
from atlas.memory.local_keys import ActiveLocalConsistencyKey


class SystemdCredentialKeyProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.directory = Path(self.temp_dir.name)
        self.key = b"\x91" * 32
        (self.directory / "atlas-key-v1").write_bytes(self.key)
        self.provider = SystemdCredentialKeyProvider(
            self.directory,
            {"atlas-local-key-v1": "atlas-key-v1"},
        )

    def test_loads_exact_historical_key_by_reference(self):
        self.assertEqual(self.provider.load_key("atlas-local-key-v1"), self.key)

    def test_unknown_reference_is_unavailable(self):
        self.assertIsNone(self.provider.load_key("unknown-key"))

    def test_missing_credential_is_unavailable(self):
        provider = SystemdCredentialKeyProvider(
            self.directory, {"missing-key": "not-present"}
        )
        self.assertIsNone(provider.load_key("missing-key"))

    def test_wrong_length_credential_is_unavailable(self):
        (self.directory / "short-key").write_bytes(b"short")
        provider = SystemdCredentialKeyProvider(
            self.directory, {"short-key-ref": "short-key"}
        )
        self.assertIsNone(provider.load_key("short-key-ref"))

    def test_oversized_credential_is_unavailable(self):
        (self.directory / "long-key").write_bytes(b"x" * 33)
        provider = SystemdCredentialKeyProvider(
            self.directory, {"long-key-ref": "long-key"}
        )
        self.assertIsNone(provider.load_key("long-key-ref"))

    def test_symlink_credential_is_not_followed(self):
        (self.directory / "key-link").symlink_to(self.directory / "atlas-key-v1")
        provider = SystemdCredentialKeyProvider(
            self.directory, {"linked-key-ref": "key-link"}
        )
        self.assertIsNone(provider.load_key("linked-key-ref"))

    def test_directory_is_not_accepted_as_credential(self):
        (self.directory / "key-directory").mkdir()
        provider = SystemdCredentialKeyProvider(
            self.directory, {"directory-key-ref": "key-directory"}
        )
        self.assertIsNone(provider.load_key("directory-key-ref"))

    def test_credential_name_path_traversal_is_rejected(self):
        for name in ("../secret", "/tmp/secret", "folder/key", ".", ".."):
            with self.subTest(name=name):
                with self.assertRaises(ContractError):
                    SystemdCredentialKeyProvider(
                        self.directory, {"key-ref": name}
                    )

    def test_empty_or_duplicate_credential_mapping_is_rejected(self):
        with self.assertRaises(ContractError):
            SystemdCredentialKeyProvider(self.directory, {})
        with self.assertRaises(ContractError):
            SystemdCredentialKeyProvider(
                self.directory,
                {"key-a": "same-file", "key-b": "same-file"},
            )

    def test_active_key_reference_is_selected_explicitly(self):
        active = ConfiguredActiveLocalConsistencyKeyProvider(
            self.provider, "atlas-local-key-v1"
        )
        result = active.load_active_key()
        self.assertIsInstance(result, ActiveLocalConsistencyKey)
        self.assertEqual(result.key_reference, "atlas-local-key-v1")
        self.assertEqual(result.key, self.key)
        self.assertNotIn(repr(self.key), repr(result))

    def test_missing_active_key_is_not_replaced_with_another_key(self):
        active = ConfiguredActiveLocalConsistencyKeyProvider(
            self.provider, "missing-active-key"
        )
        self.assertIsNone(active.load_active_key())


if __name__ == "__main__":
    unittest.main()
