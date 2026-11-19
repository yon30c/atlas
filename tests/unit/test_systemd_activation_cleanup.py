"""Unit tests for identity-aware cleanup in the opt-in systemd probe.

These tests exercise local temporary filesystem objects only. They do not
start systemd units or run the integration probe.
"""

import importlib.util
from pathlib import Path
import stat
import tempfile
import unittest


PROBE_PATH = (
    Path(__file__).resolve().parents[1]
    / "integration"
    / "systemd_socket_activation"
    / "run_user_manager_test.py"
)
SPEC = importlib.util.spec_from_file_location("atlas_systemd_activation_probe", PROBE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load systemd probe helpers from {PROBE_PATH}")
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


class SystemdActivationCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="atlas-systemd-cleanup-")
        self.addCleanup(self.temp_dir.cleanup)
        self.directory = Path(self.temp_dir.name)

    def test_unit_file_creation_is_exclusive_and_private(self):
        path = self.directory / "probe.service"
        identity = PROBE._create_exclusive_file(path, "[Service]\\n")
        self.assertEqual(path.read_text(encoding="utf-8"), "[Service]\\n")
        self.assertEqual(stat.S_IMODE(path.lstat().st_mode), 0o600)
        self.assertTrue(PROBE._identity_matches(path, identity, "file"))

    def test_exclusive_creation_preserves_preexisting_regular_file(self):
        path = self.directory / "probe.service"
        path.write_bytes(b"sentinel")
        with self.assertRaises(FileExistsError):
            PROBE._create_exclusive_file(path, "replacement")
        self.assertEqual(path.read_bytes(), b"sentinel")

    def test_exclusive_creation_preserves_preexisting_symlink(self):
        target = self.directory / "target"
        target.write_bytes(b"sentinel")
        path = self.directory / "probe.service"
        path.symlink_to(target)
        with self.assertRaises(FileExistsError):
            PROBE._create_exclusive_file(path, "replacement")
        self.assertTrue(path.is_symlink())
        self.assertEqual(target.read_bytes(), b"sentinel")

    def test_directory_creation_rejects_symlinked_components(self):
        real_parent = self.directory / "real-parent"
        real_parent.mkdir()
        linked_parent = self.directory / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)

        with self.assertRaises(RuntimeError):
            PROBE._ensure_directory_chain(linked_parent / "systemd" / "user")

    def test_cleanup_refuses_to_unlink_replacement_symlink(self):
        path = self.directory / "probe.service"
        target = self.directory / "target"
        held_original = self.directory / "original.service"
        path.write_text("original", encoding="utf-8")
        original_identity = PROBE._path_identity(path)
        path.rename(held_original)
        target.write_text("target", encoding="utf-8")
        path.symlink_to(target)

        self.assertFalse(
            PROBE._unlink_if_same_identity(path, original_identity, "file")
        )
        self.assertTrue(path.is_symlink())
        self.assertEqual(target.read_text(encoding="utf-8"), "target")

    def test_cleanup_refuses_to_unlink_replacement_file(self):
        path = self.directory / "probe.service"
        held_original = self.directory / "original.service"
        path.write_text("original", encoding="utf-8")
        original_identity = PROBE._path_identity(path)
        path.rename(held_original)
        path.write_text("replacement", encoding="utf-8")

        self.assertFalse(
            PROBE._unlink_if_same_identity(path, original_identity, "file")
        )
        self.assertEqual(path.read_text(encoding="utf-8"), "replacement")
        self.assertEqual(held_original.read_text(encoding="utf-8"), "original")

    def test_cleanup_refuses_to_remove_replacement_directory(self):
        path = self.directory / "runtime"
        held_original = self.directory / "original-runtime"
        path.mkdir()
        original_identity = PROBE._path_identity(path)
        path.rename(held_original)
        path.mkdir()

        self.assertFalse(PROBE._rmdir_if_same_identity(path, original_identity))
        self.assertTrue(path.is_dir())
        self.assertTrue(held_original.is_dir())

    def test_cleanup_removes_the_recorded_file(self):
        path = self.directory / "probe.service"
        identity = PROBE._create_exclusive_file(path, "owned")
        self.assertTrue(PROBE._unlink_if_same_identity(path, identity, "file"))
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
