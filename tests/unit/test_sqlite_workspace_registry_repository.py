"""Tests for the canonical SQLite workspace registry and explicit scope links."""

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.identity_authority import SQLiteIdentityAuthority
from atlas.adapters.sqlite.local_authority_unit_of_work import SQLiteLocalAuthorityUnitOfWork
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.adapters.sqlite.project_environment_repository import SQLiteProjectEnvironmentRepository
from atlas.adapters.sqlite.workspace_registry_repository import SQLiteWorkspaceRegistryRepository
from atlas.adapters.sqlite.project_environment_association_repository import SQLiteProjectEnvironmentAssociationRepository
from atlas.adapters.sqlite.project_environment_lifecycle_association_writer import SQLiteProjectEnvironmentLifecycleAssociationWriter
from atlas.core.errors import ConcurrencyError, ContractError, NotFoundError
from atlas.memory.metadata import EnvironmentMetadata, ProjectMetadata
from atlas.memory.models import EnvironmentId, ProjectId
from atlas.workspace.models import (
    ProjectEnvironmentAssociation,
    ProjectEnvironmentStatus,
    WorkspaceRecord,
    WorkspaceStatus,
)


class SQLiteWorkspaceRegistryRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "authority.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.identity = SQLiteIdentityAuthority(self.database).create_user()
        self.project_environment = SQLiteProjectEnvironmentRepository(self.database)
        self.project = ProjectMetadata(ProjectId("atlas"), "active", 1)
        self.environment = EnvironmentMetadata(EnvironmentId("test"), "active", 1)
        self.project_environment.create_project(self.project)
        self.project_environment.create_environment(self.environment)
        self.repository = SQLiteWorkspaceRegistryRepository(self.database)
        self.associations = SQLiteProjectEnvironmentAssociationRepository(self.database)
        self.association = ProjectEnvironmentAssociation(
            ProjectId("atlas"), EnvironmentId("test"), ProjectEnvironmentStatus.ACTIVE
        )
        self.workspace = WorkspaceRecord(
            "workspace-main", self.identity.user_id, ProjectId("atlas"),
            EnvironmentId("test"), "mount:atlas-main"
        )

    def _transition_association(self, target_status):
        current = self.associations.get_association(ProjectId("atlas"), EnvironmentId("test"))
        event_id = str(uuid4())
        with SQLiteLocalAuthorityUnitOfWork(self.database) as unit:
            connection = unit._connection
            connection.execute(
                """INSERT INTO atlas_project_environment_lifecycle_events (
                    event_id, project_id, environment_id, previous_status, new_status,
                    previous_revision, new_revision, actor_user_id, actor_identity_id,
                    verified_identity_context_id, request_id, correlation_id, reason, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id, current.project_id, current.environment_id,
                    current.status.value, target_status.value, current.revision,
                    current.revision + 1, self.identity.user_id, self.identity.identity.identity_id,
                    str(uuid4()), str(uuid4()), str(uuid4()), "Administrative lifecycle test",
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            writer = SQLiteProjectEnvironmentLifecycleAssociationWriter(
                self.database, unit_of_work=unit
            )
            writer.update_association(
                replace(current, status=target_status, revision=current.revision + 1),
                expected_revision=current.revision,
                lifecycle_event_id=event_id,
            )
            unit.commit()
        return self.associations.get_association(ProjectId("atlas"), EnvironmentId("test"))

    def test_create_and_read_explicit_project_environment_association(self):
        self.associations.create_association(self.association)
        self.assertEqual(
            self.associations.get_association(ProjectId("atlas"), EnvironmentId("test")),
            self.association,
        )

    def test_association_requires_existing_project_and_environment(self):
        invalid = ProjectEnvironmentAssociation(
            ProjectId("missing"), EnvironmentId("test"), ProjectEnvironmentStatus.ACTIVE
        )
        with self.assertRaises(ContractError):
            self.associations.create_association(invalid)

    def test_association_status_uses_compare_and_swap_revision(self):
        self.associations.create_association(self.association)
        suspended = self._transition_association(ProjectEnvironmentStatus.SUSPENDED)
        self.assertEqual(
            self.associations.get_association(ProjectId("atlas"), EnvironmentId("test")),
            suspended,
        )
        with self.assertRaises(ConcurrencyError):
            with SQLiteLocalAuthorityUnitOfWork(self.database) as unit:
                writer = SQLiteProjectEnvironmentLifecycleAssociationWriter(
                    self.database, unit_of_work=unit
                )
                writer.update_association(
                    replace(self.association, revision=2), expected_revision=1,
                    lifecycle_event_id=str(uuid4()),
                )

    def test_create_and_read_workspace_with_canonical_owner_and_scope(self):
        self.associations.create_association(self.association)
        self.repository.create_workspace(self.workspace)
        self.assertEqual(
            self.repository.get_workspace("workspace-main"), self.workspace
        )
        self.assertEqual(
            self.repository.list_workspaces_by_owner(self.identity.user_id),
            (self.workspace,),
        )

    def test_workspace_requires_existing_owner_and_active_association(self):
        self.associations.create_association(self.association)
        invalid_owner = replace(self.workspace, owner_user_id="missing-user")
        with self.assertRaises(ContractError):
            self.repository.create_workspace(invalid_owner)

        self._transition_association(ProjectEnvironmentStatus.SUSPENDED)
        with self.assertRaises(ContractError):
            self.repository.create_workspace(self.workspace)

    def test_workspace_requires_an_explicit_project_environment_association(self):
        with self.assertRaises(ContractError):
            self.repository.create_workspace(self.workspace)

    def test_workspace_status_cas_and_immutable_scope(self):
        self.associations.create_association(self.association)
        self.repository.create_workspace(self.workspace)
        suspended = replace(self.workspace, status=WorkspaceStatus.SUSPENDED, revision=2)
        self.repository.update_workspace(suspended, expected_revision=1)
        self.assertEqual(self.repository.get_workspace("workspace-main"), suspended)
        with self.assertRaises(ConcurrencyError):
            self.repository.update_workspace(
                replace(self.workspace, revision=2), expected_revision=1
            )
        with self.assertRaises(ContractError):
            self.repository.update_workspace(
                replace(suspended, root_ref="mount:other", revision=3),
                expected_revision=2,
            )

    def test_database_rejects_workspace_identity_change_and_delete(self):
        self.associations.create_association(self.association)
        self.repository.create_workspace(self.workspace)
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """UPDATE atlas_workspaces SET root_ref = 'mount:other', revision = 2
                       WHERE workspace_id = 'workspace-main'"""
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM atlas_workspaces WHERE workspace_id = 'workspace-main'"
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """UPDATE atlas_project_environments
                       SET project_id = 'other', revision = 2
                       WHERE project_id = 'atlas' AND environment_id = 'test'"""
                )

    def test_registry_joins_outer_unit_of_work(self):
        self.associations.create_association(self.association)
        with self.assertRaisesRegex(RuntimeError, "force outer rollback"):
            with self.database.unit_of_work() as unit:
                joined = SQLiteWorkspaceRegistryRepository(
                    self.database, unit_of_work=unit
                )
                joined.create_workspace(self.workspace)
                self.assertEqual(
                    joined.get_workspace("workspace-main"), self.workspace
                )
                raise RuntimeError("force outer rollback")
        self.assertIsNone(self.repository.get_workspace("workspace-main"))

    def test_local_authority_uow_exposes_workspace_registry_on_same_transaction(self):
        self.associations.create_association(self.association)
        with self.assertRaisesRegex(RuntimeError, "force outer rollback"):
            with SQLiteLocalAuthorityUnitOfWork(self.database) as unit:
                self.assertIs(unit.workspaces._database, self.database)
                self.assertFalse(hasattr(unit.workspaces, "get_association"))
                self.assertFalse(hasattr(unit.workspaces, "create_association"))
                self.assertFalse(hasattr(unit.workspaces, "update_association"))
                self.assertTrue(hasattr(unit.project_environment_associations, "get_association"))
                self.assertTrue(hasattr(unit.project_environment_associations, "create_association"))
                self.assertFalse(hasattr(unit.project_environment_associations, "update_association"))
                self.assertIs(unit.project_environment_associations._unit_of_work, unit._unit)
                unit.workspaces.create_workspace(self.workspace)
                self.assertEqual(
                    unit.workspaces.get_workspace("workspace-main"), self.workspace
                )
                raise RuntimeError("force outer rollback")
        self.assertIsNone(self.repository.get_workspace("workspace-main"))

    def test_lifecycle_writer_is_bound_to_one_active_local_authority_uow(self):
        unit = SQLiteLocalAuthorityUnitOfWork(self.database)
        with unit as active:
            writer = SQLiteProjectEnvironmentLifecycleAssociationWriter(
                self.database, unit_of_work=active
            )
            with writer._write_connection() as connection:
                self.assertIs(connection, active._connection)
        with self.assertRaises(ContractError):
            with writer._write_connection():
                pass

        other_dir = tempfile.TemporaryDirectory()
        self.addCleanup(other_dir.cleanup)
        other_database = SQLiteDatabase(Path(other_dir.name) / "other.sqlite")
        other_database.apply_migrations(SQLITE_MIGRATIONS)
        with SQLiteLocalAuthorityUnitOfWork(other_database) as other_unit:
            mismatched = SQLiteProjectEnvironmentLifecycleAssociationWriter(
                self.database, unit_of_work=other_unit
            )
            with self.assertRaises(ContractError):
                with mismatched._write_connection():
                    pass

    def test_workspace_root_ref_must_be_symbolic_not_a_filesystem_path(self):
        with self.assertRaises(ContractError):
            replace(self.workspace, root_ref="/srv/atlas/workspace")
        with self.assertRaises(ContractError):
            replace(self.workspace, root_ref="file:///srv/atlas/workspace")
        with self.assertRaises(ContractError):
            replace(self.workspace, root_ref="../outside")
        with self.assertRaises(ContractError):
            replace(self.workspace, root_ref="mount:../outside")


if __name__ == "__main__":
    unittest.main()
