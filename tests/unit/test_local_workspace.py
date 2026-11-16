"""Pruebas del adaptador local de workspace."""

import tempfile
from pathlib import Path
import unittest

from atlas.assistant.workspace import WorkspaceEntryKind, WorkspaceListing
from atlas.adapters.local_workspace import LocalWorkspaceAdapter
from atlas.core.errors import AtlasError, ContractError, NotFoundError


class LocalWorkspaceAdapterTests(unittest.TestCase):
    def test_lists_only_immediate_entries_in_stable_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "zeta.txt").write_text("hello", encoding="utf-8")
            (root / "Alpha.txt").write_text("123", encoding="utf-8")
            (root / "folder").mkdir()
            (root / "folder" / "nested.txt").write_text("hidden from listing", encoding="utf-8")

            adapter = LocalWorkspaceAdapter({"demo": root})
            result = adapter.list_entries("demo")

            self.assertIsInstance(result, WorkspaceListing)
            self.assertEqual(result.workspace_id, "demo")
            self.assertEqual([entry.name for entry in result.entries], ["Alpha.txt", "folder", "zeta.txt"])
            by_name = {entry.name: entry for entry in result.entries}
            self.assertIs(by_name["Alpha.txt"].kind, WorkspaceEntryKind.FILE)
            self.assertEqual(by_name["Alpha.txt"].size_bytes, 3)
            self.assertIs(by_name["folder"].kind, WorkspaceEntryKind.DIRECTORY)
            self.assertIsNone(by_name["folder"].size_bytes)
            self.assertNotIn("nested.txt", [entry.name for entry in result.entries])

    def test_empty_workspace_returns_empty_tuple(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = LocalWorkspaceAdapter({"demo": temporary}).list_entries("demo")
            self.assertEqual(result.entries, ())

    def test_symlink_is_reported_without_following_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "workspace"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            (outside / "secret.txt").write_text("secret", encoding="utf-8")
            link = root / "external"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("el entorno no permite crear symlinks")
            result = LocalWorkspaceAdapter({"demo": root}).list_entries("demo")
            self.assertEqual(len(result.entries), 1)
            self.assertEqual(result.entries[0].name, "external")
            self.assertIs(result.entries[0].kind, WorkspaceEntryKind.SYMLINK)

    def test_rejects_unknown_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(NotFoundError):
                LocalWorkspaceAdapter({"demo": temporary}).list_entries("other")

    def test_rejects_invalid_roots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(ContractError):
                LocalWorkspaceAdapter({"demo": "relative/path"})
            with self.assertRaises(ContractError):
                LocalWorkspaceAdapter({"demo": root / "missing"})
            with self.assertRaises(ContractError):
                LocalWorkspaceAdapter({})

    def test_rejects_symlink_as_workspace_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            real_root = base / "real"
            real_root.mkdir()
            alias = base / "alias"
            try:
                alias.symlink_to(real_root, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("el entorno no permite crear symlinks")
            with self.assertRaises(ContractError):
                LocalWorkspaceAdapter({"demo": alias})

    def test_rejects_invalid_workspace_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            adapter = LocalWorkspaceAdapter({"demo": temporary})
            with self.assertRaises(ContractError):
                adapter.list_entries(" ")

    def test_reads_utf8_file_with_relative_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "docs").mkdir()
            content = "Atlas\nlectura segura: ñ"
            (root / "docs" / "readme.md").write_text(content, encoding="utf-8")
            result = LocalWorkspaceAdapter({"demo": root}).read_file("demo", "docs/readme.md")
            self.assertEqual(result.content, content)
            self.assertEqual(result.path, "docs/readme.md")
            self.assertEqual(result.size_bytes, len(content.encode("utf-8")))

    def test_rejects_absolute_traversal_and_non_normalized_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            adapter = LocalWorkspaceAdapter({"demo": temporary})
            for path in ("../secret", "folder/../../secret", "/etc/passwd", "C:/secret", "a//b", "./a", "a/../b", "a\\b"):
                with self.subTest(path=path), self.assertRaises(ContractError):
                    adapter.read_file("demo", path)

    def test_rejects_symlink_in_any_path_component(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "workspace"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            (outside / "secret.txt").write_text("secret", encoding="utf-8")
            (root / "alias").symlink_to(outside, target_is_directory=True)
            adapter = LocalWorkspaceAdapter({"demo": root})
            with self.assertRaises(ContractError):
                adapter.read_file("demo", "alias/secret.txt")

    def test_rejects_final_file_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "workspace"
            root.mkdir()
            outside = base / "outside.txt"
            outside.write_text("secret", encoding="utf-8")
            (root / "alias.txt").symlink_to(outside)
            adapter = LocalWorkspaceAdapter({"demo": root})
            with self.assertRaises(ContractError):
                adapter.read_file("demo", "alias.txt")

    def test_rejects_missing_directory_and_unknown_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            adapter = LocalWorkspaceAdapter({"demo": temporary})
            with self.assertRaises(NotFoundError):
                adapter.read_file("demo", "missing.txt")
            with self.assertRaises(NotFoundError):
                adapter.read_file("unknown", "file.txt")

    def test_rejects_oversized_and_binary_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "large.txt").write_bytes(b"x" * 9)
            (root / "binary.bin").write_bytes(b"\xff\xfe")
            adapter = LocalWorkspaceAdapter({"demo": root}, max_file_bytes=8)
            with self.assertRaises(ContractError):
                adapter.read_file("demo", "large.txt")
            with self.assertRaises(ContractError):
                adapter.read_file("demo", "binary.bin")

    def test_rejects_directory_as_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "folder").mkdir()
            with self.assertRaises(ContractError):
                LocalWorkspaceAdapter({"demo": root}).read_file("demo", "folder")


if __name__ == "__main__":
    unittest.main()
