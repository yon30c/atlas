"""Tests for canonical Project and Environment metadata persistence."""

from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.project_environment_repository import (
    SQLiteProjectEnvironmentRepository,
)
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.core.errors import ConcurrencyError, ContractError, NotFoundError
from atlas.memory.metadata import EnvironmentMetadata, ProjectMetadata
from atlas.memory.models import EnvironmentId, ProjectId


class SQLiteProjectEnvironmentRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "authority.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.repository = SQLiteProjectEnvironmentRepository(self.database)
        self.project = ProjectMetadata(ProjectId("atlas"), "active", 1)
        self.environment = EnvironmentMetadata(EnvironmentId("test"), "active", 1)

    def test_repository_implements_both_metadata_ports_on_exact_database(self):
        self.assertIs(self.repository._database, self.database)
        self.assertTrue(callable(self.repository.get_project))
        self.assertTrue(callable(self.repository.get_environment))

    def test_project_create_read_update_round_trip(self):
        self.repository.create_project(self.project)
        self.assertEqual(self.repository.get_project("atlas"), self.project)
        updated = replace(self.project, status="suspended", revision=2)
        self.repository.update_project(updated, expected_revision=1)
        self.assertEqual(self.repository.get_project("atlas"), updated)

    def test_environment_create_read_update_round_trip(self):
        self.repository.create_environment(self.environment)
        self.assertEqual(self.repository.get_environment("test"), self.environment)
        updated = replace(self.environment, status="disabled", revision=2)
        self.repository.update_environment(updated, expected_revision=1)
        self.assertEqual(self.repository.get_environment("test"), updated)

    def test_missing_authorities_return_none(self):
        self.assertIsNone(self.repository.get_project("missing"))
        self.assertIsNone(self.repository.get_environment("missing"))

    def test_duplicate_project_and_environment_ids_are_rejected(self):
        self.repository.create_project(self.project)
        self.repository.create_environment(self.environment)
        with self.assertRaises(ContractError):
            self.repository.create_project(self.project)
        with self.assertRaises(ContractError):
            self.repository.create_environment(self.environment)

    def test_updates_reject_stale_revisions_without_overwriting(self):
        self.repository.create_project(self.project)
        first = replace(self.project, status="suspended", revision=2)
        stale = replace(self.project, status="closed", revision=2)
        self.repository.update_project(first, expected_revision=1)
        with self.assertRaises(ConcurrencyError):
            self.repository.update_project(stale, expected_revision=1)
        self.assertEqual(self.repository.get_project("atlas"), first)

        self.repository.create_environment(self.environment)
        first_environment = replace(self.environment, status="disabled", revision=2)
        stale_environment = replace(self.environment, status="closed", revision=2)
        self.repository.update_environment(first_environment, expected_revision=1)
        with self.assertRaises(ConcurrencyError):
            self.repository.update_environment(stale_environment, expected_revision=1)
        self.assertEqual(self.repository.get_environment("test"), first_environment)

    def test_update_of_missing_authority_raises_not_found(self):
        with self.assertRaises(NotFoundError):
            self.repository.update_project(
                replace(self.project, revision=2),
                expected_revision=1,
            )
        with self.assertRaises(NotFoundError):
            self.repository.update_environment(
                replace(self.environment, revision=2),
                expected_revision=1,
            )

    def test_updates_require_exact_next_revision(self):
        with self.assertRaises(ContractError):
            self.repository.update_project(
                replace(self.project, revision=3),
                expected_revision=1,
            )
        with self.assertRaises(ContractError):
            self.repository.update_environment(
                replace(self.environment, revision=3),
                expected_revision=1,
            )

    def test_database_rejects_identity_change_revision_skip_and_delete(self):
        self.repository.create_project(self.project)
        self.repository.create_environment(self.environment)
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE atlas_projects SET project_id = 'other', revision = 2 WHERE project_id = 'atlas'"
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE atlas_projects SET status = 'closed', revision = 3 WHERE project_id = 'atlas'"
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM atlas_projects WHERE project_id = 'atlas'")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE atlas_environments SET environment_id = 'other', revision = 2 WHERE environment_id = 'test'"
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE atlas_environments SET status = 'closed', revision = 3 WHERE environment_id = 'test'"
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM atlas_environments WHERE environment_id = 'test'")

    def test_reopened_database_preserves_project_and_environment(self):
        self.repository.create_project(self.project)
        self.repository.create_environment(self.environment)
        reopened = SQLiteDatabase(self.database.path)
        reopened.apply_migrations(SQLITE_MIGRATIONS)
        repository = SQLiteProjectEnvironmentRepository(reopened)
        self.assertEqual(repository.get_project("atlas"), self.project)
        self.assertEqual(repository.get_environment("test"), self.environment)


    def test_project_and_environment_creates_join_outer_transaction(self):
        with self.assertRaisesRegex(RuntimeError, "force outer rollback"):
            with self.database.unit_of_work() as unit:
                joined = SQLiteProjectEnvironmentRepository(
                    self.database,
                    unit_of_work=unit,
                )
                joined.create_project(self.project)
                joined.create_environment(self.environment)
                raise RuntimeError("force outer rollback")
        self.assertIsNone(self.repository.get_project("atlas"))
        self.assertIsNone(self.repository.get_environment("test"))

    def test_project_and_environment_updates_join_outer_transaction(self):
        self.repository.create_project(self.project)
        self.repository.create_environment(self.environment)
        with self.assertRaisesRegex(RuntimeError, "force outer rollback"):
            with self.database.unit_of_work() as unit:
                joined = SQLiteProjectEnvironmentRepository(
                    self.database,
                    unit_of_work=unit,
                )
                joined.update_project(
                    replace(self.project, status="suspended", revision=2),
                    expected_revision=1,
                )
                joined.update_environment(
                    replace(self.environment, status="disabled", revision=2),
                    expected_revision=1,
                )
                raise RuntimeError("force outer rollback")
        self.assertEqual(self.repository.get_project("atlas"), self.project)
        self.assertEqual(self.repository.get_environment("test"), self.environment)

    def test_project_environment_repository_rejects_foreign_unit_of_work(self):
        other = SQLiteDatabase(Path(self.temp_dir.name) / "other.sqlite")
        other.apply_migrations(SQLITE_MIGRATIONS)
        with other.unit_of_work() as unit:
            joined = SQLiteProjectEnvironmentRepository(
                self.database,
                unit_of_work=unit,
            )
            with self.assertRaises(ContractError):
                joined.create_project(self.project)


if __name__ == "__main__":
    unittest.main()
