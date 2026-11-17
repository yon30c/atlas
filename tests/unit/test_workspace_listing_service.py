"""Pruebas del caso de uso WorkspaceListingService."""

import tempfile
from pathlib import Path
import unittest

from atlas.adapters.local_workspace import LocalWorkspaceAdapter
from atlas.application.workspace_listing import WorkspaceListingService
from atlas.assistant.workspace import WorkspaceEntry, WorkspaceEntryKind, WorkspaceListing
from atlas.core.errors import ContractError, NotFoundError


class FakeWorkspaceReader:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def list_entries(self, workspace_id):
        self.calls.append(workspace_id)
        if self.error is not None:
            raise self.error
        return self.result


class WorkspaceListingServiceTests(unittest.TestCase):
    def test_returns_listing_from_reader(self):
        listing = WorkspaceListing(
            "demo",
            (WorkspaceEntry("readme.md", WorkspaceEntryKind.FILE, 12),),
        )
        reader = FakeWorkspaceReader(result=listing)
        service = WorkspaceListingService(reader)

        result = service.list("demo")

        self.assertIs(result, listing)
        self.assertEqual(reader.calls, ["demo"])

    def test_rejects_empty_workspace_id_without_calling_reader(self):
        reader = FakeWorkspaceReader()
        service = WorkspaceListingService(reader)

        with self.assertRaises(ContractError):
            service.list(" ")

        self.assertEqual(reader.calls, [])

    def test_rejects_reader_with_invalid_result(self):
        service = WorkspaceListingService(FakeWorkspaceReader(result={"entries": []}))

        with self.assertRaises(ContractError):
            service.list("demo")

    def test_rejects_result_for_different_workspace(self):
        listing = WorkspaceListing("other", ())
        service = WorkspaceListingService(FakeWorkspaceReader(result=listing))

        with self.assertRaises(ContractError):
            service.list("demo")

    def test_propagates_unknown_workspace_error(self):
        reader = FakeWorkspaceReader(error=NotFoundError("workspace no configurado"))
        service = WorkspaceListingService(reader)

        with self.assertRaises(NotFoundError):
            service.list("demo")

        self.assertEqual(reader.calls, ["demo"])

    def test_integrates_with_local_workspace_adapter(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "hello.txt").write_text("Atlas", encoding="utf-8")
            adapter = LocalWorkspaceAdapter({"demo": root})
            service = WorkspaceListingService(adapter)

            result = service.list("demo")

            self.assertEqual(result.workspace_id, "demo")
            self.assertEqual(len(result.entries), 1)
            self.assertEqual(result.entries[0].name, "hello.txt")
            self.assertEqual(result.entries[0].size_bytes, 5)

    def test_rejects_invalid_reader(self):
        with self.assertRaises(ContractError):
            WorkspaceListingService(object())


if __name__ == "__main__":
    unittest.main()
