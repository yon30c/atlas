"""Tests for trusted symbolic workspace mount resolution."""

from pathlib import Path
import tempfile
import unittest

from atlas.adapters.trusted_workspace_mount_resolver import (
    TrustedWorkspaceMountResolver,
)
from atlas.core.errors import ContractError


class TrustedWorkspaceMountResolverTests(unittest.TestCase):
    def test_resolves_known_symbolic_mount(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            resolver = TrustedWorkspaceMountResolver({"data": root})
            self.assertEqual(resolver.resolve("mount:data"), root)

    def test_rejects_empty_mount_configuration(self):
        with self.assertRaises(ContractError):
            TrustedWorkspaceMountResolver({})

    def test_rejects_invalid_mount_ids(self):
        with tempfile.TemporaryDirectory() as temporary:
            for mount_id in ("", "Upper", "../escape", "a/b", "with space", "a\\b"):
                with self.subTest(mount_id=mount_id), self.assertRaises(ContractError):
                    TrustedWorkspaceMountResolver({mount_id: temporary})

    def test_rejects_relative_missing_and_non_directory_roots(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            file_path = base / "file.txt"
            file_path.write_text("x", encoding="utf-8")
            cases = (
                {"data": "relative"},
                {"data": base / "missing"},
                {"data": file_path},
            )
            for mounts in cases:
                with self.subTest(mounts=mounts), self.assertRaises(ContractError):
                    TrustedWorkspaceMountResolver(mounts)

    def test_rejects_symlink_as_configured_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            real = base / "real"
            real.mkdir()
            alias = base / "alias"
            try:
                alias.symlink_to(real, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("el entorno no permite crear symlinks")
            with self.assertRaises(ContractError):
                TrustedWorkspaceMountResolver({"data": alias})

    def test_rejects_non_symbolic_or_malformed_root_refs(self):
        with tempfile.TemporaryDirectory() as temporary:
            resolver = TrustedWorkspaceMountResolver({"data": temporary})
            for root_ref in (
                "",
                "/srv/atlas",
                "file:///srv/atlas",
                "mount:",
                "mount:../escape",
                "mount:Upper",
                "mount:a/b",
                "mount:a\\b",
                "mount:with space",
            ):
                with self.subTest(root_ref=root_ref), self.assertRaises(ContractError):
                    resolver.resolve(root_ref)

    def test_revalidates_root_after_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "mount"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            resolver = TrustedWorkspaceMountResolver({"data": root})
            root.rename(base / "original")
            root.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ContractError):
                resolver.resolve("mount:data")


if __name__ == "__main__":
    unittest.main()
