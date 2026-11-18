import unittest

from atlas.adapters import sqlite


class SQLitePackageExportTests(unittest.TestCase):
    def test_workspace_registry_repository_is_exported(self) -> None:
        self.assertIn("SQLiteWorkspaceRegistryRepository", sqlite.__all__)
        self.assertEqual(
            sqlite.SQLiteWorkspaceRegistryRepository.__module__,
            "atlas.adapters.sqlite.workspace_registry_repository",
        )
