"""Pruebas del caso de uso WorkspaceFileReadingService."""

import tempfile
from pathlib import Path
import unittest

from atlas.adapters.local_workspace import LocalWorkspaceAdapter
from atlas.application.workspace_file_reading import WorkspaceFileReadingService
from atlas.assistant.workspace import WorkspaceFile
from atlas.core.errors import ContractError, NotFoundError


class FakeWorkspaceFileReader:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def read_file(self, workspace_id, path):
        self.calls.append((workspace_id, path))
        if self.error is not None:
            raise self.error
        return self.result


class WorkspaceFileReadingServiceTests(unittest.TestCase):
    def test_returns_file_from_reader(self):
        result = WorkspaceFile("demo", "notes.txt", "Atlas", 5)
        reader = FakeWorkspaceFileReader(result=result)
        service = WorkspaceFileReadingService(reader)
        self.assertIs(service.read("demo", "notes.txt"), result)
        self.assertEqual(reader.calls, [("demo", "notes.txt")])

    def test_rejects_invalid_arguments_before_calling_reader(self):
        reader = FakeWorkspaceFileReader()
        service = WorkspaceFileReadingService(reader)
        for workspace_id, path in (("", "a.txt"), ("demo", "")):
            with self.subTest(workspace_id=workspace_id, path=path), self.assertRaises(ContractError):
                service.read(workspace_id, path)
        self.assertEqual(reader.calls, [])

    def test_rejects_malformed_or_mismatched_result(self):
        for result in ({"content": "x"}, WorkspaceFile("other", "a.txt", "x", 1), WorkspaceFile("demo", "other.txt", "x", 1)):
            with self.subTest(result=result), self.assertRaises(ContractError):
                WorkspaceFileReadingService(FakeWorkspaceFileReader(result=result)).read("demo", "a.txt")

    def test_propagates_missing_file(self):
        service = WorkspaceFileReadingService(FakeWorkspaceFileReader(error=NotFoundError("missing")))
        with self.assertRaises(NotFoundError):
            service.read("demo", "missing.txt")

    def test_integrates_with_local_adapter(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "readme.txt").write_text("Atlas", encoding="utf-8")
            service = WorkspaceFileReadingService(LocalWorkspaceAdapter({"demo": root}))
            result = service.read("demo", "readme.txt")
            self.assertEqual(result.content, "Atlas")
            self.assertEqual(result.size_bytes, 5)

    def test_rejects_invalid_reader(self):
        with self.assertRaises(ContractError):
            WorkspaceFileReadingService(object())


if __name__ == "__main__":
    unittest.main()
