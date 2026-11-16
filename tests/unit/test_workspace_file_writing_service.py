"""Pruebas del servicio de escritura controlada de workspace."""

import tempfile
from pathlib import Path
from uuid import uuid4
import unittest

from atlas.adapters.local_workspace_write import LocalWorkspaceWriteAdapter
from atlas.application.workspace_file_writing import WorkspaceFileWritingService
from atlas.assistant.workspace_write import (
    WorkspaceRecoveryAssessment,
    WorkspaceRecoveryStatus,
    WorkspaceWriteCommit,
    WorkspaceWriteStage,
)
from atlas.core.errors import ContractError


class FakeWriter:
    def __init__(self):
        self.calls = []
        self.stage_result = WorkspaceWriteStage(
            "demo", str(uuid4()), "notes.txt", "a" * 64, 1, None
        )
        self.commit_result = WorkspaceWriteCommit(
            "demo", self.stage_result.operation_id, "notes.txt", "a" * 64, 1, True
        )
        self.recovery_result = WorkspaceRecoveryAssessment(
            "demo", self.stage_result.operation_id, WorkspaceRecoveryStatus.STAGED_READY
        )

    def stage_write(self, *args):
        self.calls.append(("stage", args))
        return self.stage_result

    def commit_write(self, *args):
        self.calls.append(("commit", args))
        return self.commit_result

    def assess_recovery(self, *args):
        self.calls.append(("recovery", args))
        return self.recovery_result


class WorkspaceFileWritingServiceTests(unittest.TestCase):
    def test_coordinates_stage_commit_and_recovery(self):
        writer = FakeWriter()
        service = WorkspaceFileWritingService(writer)
        operation_id = writer.stage_result.operation_id
        self.assertIs(
            service.stage("demo", "notes.txt", "x", operation_id),
            writer.stage_result,
        )
        self.assertIs(service.commit("demo", operation_id), writer.commit_result)
        self.assertIs(
            service.assess_recovery("demo", operation_id), writer.recovery_result
        )
        self.assertEqual([call[0] for call in writer.calls], ["stage", "commit", "recovery"])

    def test_rejects_invalid_arguments_before_calling_writer(self):
        writer = FakeWriter()
        service = WorkspaceFileWritingService(writer)
        with self.assertRaises(ContractError):
            service.stage("", "notes.txt", "x", str(uuid4()))
        with self.assertRaises(ContractError):
            service.stage("demo", "notes.txt", "x", "")
        with self.assertRaises(ContractError):
            service.commit("demo", "")
        self.assertEqual(writer.calls, [])

    def test_rejects_mismatched_stage_binding(self):
        writer = FakeWriter()
        writer.stage_result = WorkspaceWriteStage(
            "other", str(uuid4()), "notes.txt", "a" * 64, 1, None
        )
        with self.assertRaises(ContractError):
            WorkspaceFileWritingService(writer).stage(
                "demo", "notes.txt", "x", writer.stage_result.operation_id
            )

    def test_rejects_mismatched_commit_binding_and_false_commit(self):
        writer = FakeWriter()
        writer.commit_result = WorkspaceWriteCommit(
            "other", writer.stage_result.operation_id, "notes.txt", "a" * 64, 1, True
        )
        with self.assertRaises(ContractError):
            WorkspaceFileWritingService(writer).commit("demo", writer.stage_result.operation_id)
        writer.commit_result = WorkspaceWriteCommit(
            "demo", writer.stage_result.operation_id, "notes.txt", "a" * 64, 1, False
        )
        with self.assertRaises(ContractError):
            WorkspaceFileWritingService(writer).commit("demo", writer.stage_result.operation_id)

    def test_integrates_with_local_adapter(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            writer = LocalWorkspaceWriteAdapter({"demo": root})
            service = WorkspaceFileWritingService(writer)
            operation_id = str(uuid4())
            service.stage("demo", "new.txt", "Atlas", operation_id)
            result = service.commit("demo", operation_id)
            self.assertTrue(result.committed)
            self.assertEqual((root / "new.txt").read_text(encoding="utf-8"), "Atlas")

    def test_rejects_invalid_writer(self):
        with self.assertRaises(ContractError):
            WorkspaceFileWritingService(object())


if __name__ == "__main__":
    unittest.main()
