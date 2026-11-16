"""Pruebas del protocolo local de staging/commit/recovery."""

import hashlib
import json
import tempfile
from pathlib import Path
from uuid import uuid4
import unittest

from atlas.adapters.local_workspace_write import LocalWorkspaceWriteAdapter
from atlas.assistant.workspace_write import WorkspaceRecoveryStatus
from atlas.core.errors import ConcurrencyError, ContractError, NotFoundError


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class LocalWorkspaceWriteAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "workspace"
        self.root.mkdir()
        self.adapter = LocalWorkspaceWriteAdapter({"demo": self.root})
        self.operation_id = str(uuid4())

    def tearDown(self):
        self.temp.cleanup()

    def test_stage_does_not_modify_final_destination(self):
        stage = self.adapter.stage_write(
            "demo", "notes.txt", "Atlas", self.operation_id
        )
        self.assertFalse((self.root / "notes.txt").exists())
        self.assertEqual(stage.content_sha256, digest("Atlas"))
        self.assertEqual(
            self.adapter.assess_recovery("demo", self.operation_id).status,
            WorkspaceRecoveryStatus.STAGED_READY,
        )

    def test_commit_creates_file_and_is_idempotent(self):
        self.adapter.stage_write("demo", "notes.txt", "Atlas", self.operation_id)
        first = self.adapter.commit_write("demo", self.operation_id)
        second = self.adapter.commit_write("demo", self.operation_id)
        self.assertTrue(first.committed)
        self.assertEqual(first, second)
        self.assertEqual((self.root / "notes.txt").read_text(encoding="utf-8"), "Atlas")
        self.assertEqual(
            self.adapter.assess_recovery("demo", self.operation_id).status,
            WorkspaceRecoveryStatus.COMMITTED,
        )

    def test_stage_retry_after_commit_returns_original_operation(self):
        first = self.adapter.stage_write("demo", "notes.txt", "Atlas", self.operation_id)
        self.adapter.commit_write("demo", self.operation_id)
        second = self.adapter.stage_write("demo", "notes.txt", "Atlas", self.operation_id)
        self.assertEqual(first, second)

    def test_detects_destination_created_after_stage(self):
        self.adapter.stage_write("demo", "notes.txt", "Atlas", self.operation_id)
        (self.root / "notes.txt").write_text("external", encoding="utf-8")
        with self.assertRaises(ConcurrencyError):
            self.adapter.commit_write("demo", self.operation_id)

    def test_does_not_claim_external_matching_file_as_its_commit(self):
        self.adapter.stage_write("demo", "notes.txt", "Atlas", self.operation_id)
        (self.root / "notes.txt").write_text("Atlas", encoding="utf-8")
        with self.assertRaises(ConcurrencyError):
            self.adapter.commit_write("demo", self.operation_id)

    def test_update_requires_exact_expected_hash(self):
        target = self.root / "notes.txt"
        target.write_text("before", encoding="utf-8")
        stage = self.adapter.stage_write(
            "demo", "notes.txt", "after", self.operation_id, digest("before")
        )
        self.assertEqual(stage.expected_sha256, digest("before"))
        self.adapter.commit_write("demo", self.operation_id)
        self.assertEqual(target.read_text(encoding="utf-8"), "after")

    def test_rejects_stale_expected_hash_during_stage(self):
        (self.root / "notes.txt").write_text("current", encoding="utf-8")
        with self.assertRaises(ConcurrencyError):
            self.adapter.stage_write(
                "demo", "notes.txt", "replacement", self.operation_id, digest("old")
            )

    def test_detects_target_changed_after_stage(self):
        target = self.root / "notes.txt"
        target.write_text("before", encoding="utf-8")
        self.adapter.stage_write(
            "demo", "notes.txt", "after", self.operation_id, digest("before")
        )
        target.write_text("external change", encoding="utf-8")
        with self.assertRaises(ConcurrencyError):
            self.adapter.commit_write("demo", self.operation_id)
        self.assertEqual(
            self.adapter.assess_recovery("demo", self.operation_id).status,
            WorkspaceRecoveryStatus.CONFLICT,
        )

    def test_stage_retry_with_same_operation_is_idempotent(self):
        first = self.adapter.stage_write("demo", "notes.txt", "Atlas", self.operation_id)
        second = self.adapter.stage_write("demo", "notes.txt", "Atlas", self.operation_id)
        self.assertEqual(first, second)

    def test_rejects_reusing_operation_id_for_different_payload(self):
        self.adapter.stage_write("demo", "notes.txt", "Atlas", self.operation_id)
        with self.assertRaises(ConcurrencyError):
            self.adapter.stage_write("demo", "notes.txt", "different", self.operation_id)

    def test_recovery_confirms_crash_after_atomic_replace(self):
        target = self.root / "notes.txt"
        target.write_text("before", encoding="utf-8")
        self.adapter.stage_write(
            "demo", "notes.txt", "after", self.operation_id, digest("before")
        )
        operation_dir = self.root / ".atlas-staging" / self.operation_id
        manifest_path = operation_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["state"] = "committing"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        (operation_dir / "payload").replace(target)
        assessment = self.adapter.assess_recovery("demo", self.operation_id)
        self.assertEqual(assessment.status, WorkspaceRecoveryStatus.COMMIT_CONFIRMED)
        result = self.adapter.commit_write("demo", self.operation_id)
        self.assertTrue(result.committed)
        self.assertEqual(
            self.adapter.assess_recovery("demo", self.operation_id).status,
            WorkspaceRecoveryStatus.COMMITTED,
        )

    def test_recovery_detects_corrupt_manifest(self):
        self.adapter.stage_write("demo", "notes.txt", "Atlas", self.operation_id)
        manifest = self.root / ".atlas-staging" / self.operation_id / "manifest.json"
        manifest.write_text("{broken", encoding="utf-8")
        self.assertEqual(
            self.adapter.assess_recovery("demo", self.operation_id).status,
            WorkspaceRecoveryStatus.CORRUPT,
        )

    def test_rejects_unsafe_paths_and_reserved_staging_path(self):
        for path in ("../secret", "/etc/passwd", "a//b", "a/../b", ".atlas-staging/x"):
            with self.subTest(path=path), self.assertRaises(ContractError):
                self.adapter.stage_write("demo", path, "x", self.operation_id)

    def test_rejects_symlink_target(self):
        outside = Path(self.temp.name) / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        (self.root / "link.txt").symlink_to(outside)
        with self.assertRaises(ContractError):
            self.adapter.stage_write("demo", "link.txt", "replace", self.operation_id, digest("secret"))

    def test_rejects_oversized_content_and_invalid_operation_id(self):
        adapter = LocalWorkspaceWriteAdapter({"demo": self.root}, max_write_bytes=3)
        with self.assertRaises(ContractError):
            adapter.stage_write("demo", "a.txt", "four", self.operation_id)
        with self.assertRaises(ContractError):
            self.adapter.stage_write("demo", "a.txt", "x", "../bad")

    def test_rejects_missing_parent_and_unknown_workspace(self):
        with self.assertRaises(NotFoundError):
            self.adapter.stage_write("demo", "missing/file.txt", "x", self.operation_id)
        with self.assertRaises(NotFoundError):
            self.adapter.stage_write("unknown", "file.txt", "x", self.operation_id)


if __name__ == "__main__":
    unittest.main()
