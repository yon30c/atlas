"""Tests for one transaction spanning canonical local authority repositories."""

from pathlib import Path
import tempfile
import unittest

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.local_authority_unit_of_work import (
    SQLiteLocalAuthorityUnitOfWorkFactory,
)
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.core.identity import IdentityStatus
from atlas.memory.metadata import EnvironmentMetadata, ProjectMetadata
from atlas.memory.models import EnvironmentId, ProjectId


class SQLiteLocalAuthorityUnitOfWorkTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "authority.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.factory = SQLiteLocalAuthorityUnitOfWorkFactory(self.database)

    def test_one_unit_exposes_all_canonical_authority_repositories(self):
        with self.factory() as unit:
            self.assertIsNotNone(unit.identity)
            self.assertIsNotNone(unit.grants)
            self.assertIsNotNone(unit.renewals)
            self.assertIsNotNone(unit.project_environments)
            self.assertIs(unit.identity._unit_of_work, unit._unit)
            self.assertIs(unit.project_environments._unit_of_work, unit._unit)
            self.assertIs(unit.grants._unit_of_work, unit._unit)
            self.assertIs(unit.renewals._unit_of_work, unit._unit)
            unit.commit()

    def test_identity_project_and_environment_commit_atomically(self):
        with self.factory() as unit:
            user = unit.identity.create_user()
            project = ProjectMetadata(ProjectId("atlas"), "active", 1)
            environment = EnvironmentMetadata(EnvironmentId("local"), "active", 1)
            unit.project_environments.create_project(project)
            unit.project_environments.create_environment(environment)
            unit.commit()

        self.assertEqual(unit.identity.get_user(user.user_id), user)
        self.assertEqual(unit.project_environments.get_project("atlas"), project)
        self.assertEqual(
            unit.project_environments.get_environment("local"),
            environment,
        )

    def test_exception_rolls_back_changes_across_authority_repositories(self):
        created_user_id = None
        with self.assertRaisesRegex(RuntimeError, "force shared rollback"):
            with self.factory() as unit:
                user = unit.identity.create_user()
                created_user_id = user.user_id
                unit.project_environments.create_project(
                    ProjectMetadata(ProjectId("rollback-project"), "active", 1)
                )
                unit.project_environments.create_environment(
                    EnvironmentMetadata(EnvironmentId("rollback-env"), "active", 1)
                )
                raise RuntimeError("force shared rollback")

        with self.database.connection() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM atlas_users WHERE user_id = ?",
                    (created_user_id,),
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM atlas_projects WHERE project_id = 'rollback-project'"
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM atlas_environments WHERE environment_id = 'rollback-env'"
                ).fetchone()[0],
                0,
            )

    def test_shared_unit_rejects_use_after_exit(self):
        with self.factory() as unit:
            user = unit.identity.create_user()
            unit.commit()
        with self.assertRaises(Exception):
            unit.identity.update_user_status(
                user.user_id,
                expected_revision=1,
                status=IdentityStatus.SUSPENDED,
            )


if __name__ == "__main__":
    unittest.main()
