"""Adversarial tests for offline Project/Environment association provisioning."""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.adapters.sqlite.project_environment_association_provisioning_writer import (
    SQLiteProjectEnvironmentAssociationProvisioningWriter,
)
from atlas.adapters.sqlite.project_environment_association_repository import (
    SQLiteProjectEnvironmentAssociationRepository,
)
from atlas.adapters.sqlite.project_environment_repository import SQLiteProjectEnvironmentRepository
from atlas.core.errors import ContractError
from atlas.memory.metadata import EnvironmentMetadata, ProjectMetadata
from atlas.memory.models import EnvironmentId, ProjectId
from atlas.workspace.models import ProjectEnvironmentAssociation, ProjectEnvironmentStatus


class SQLiteProjectEnvironmentAssociationProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "authority.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        projects = SQLiteProjectEnvironmentRepository(self.database)
        projects.create_project(ProjectMetadata(ProjectId("atlas"), "active", 1))
        projects.create_environment(EnvironmentMetadata(EnvironmentId("test"), "active", 1))
        self.reader = SQLiteProjectEnvironmentAssociationRepository(self.database)
        self.writer = SQLiteProjectEnvironmentAssociationProvisioningWriter(self.database)
        self.association = ProjectEnvironmentAssociation(
            ProjectId("atlas"), EnvironmentId("test"), ProjectEnvironmentStatus.ACTIVE
        )

    def _write(self, *, operation_id=None, event_id=None, association=None, reason="Approved initial scope"):
        return self.writer.create_association(
            association or self.association,
            event_id=event_id or str(uuid4()),
            operation_id=operation_id or str(uuid4()),
            reason=reason,
            real_uid=1000,
            effective_uid=0,
            terminal_id="/dev/pts/4",
            occurred_at=datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc),
        )

    def test_event_and_active_revision_one_association_commit_together(self):
        result = self._write()
        self.assertEqual(result, self.association)
        with self.database.connection() as connection:
            event = connection.execute(
                """SELECT project_id, environment_id, reason, real_uid, effective_uid,
                          terminal_id
                   FROM atlas_project_environment_provisioning_events"""
            ).fetchone()
            association = connection.execute(
                """SELECT status, revision, provisioning_event_id
                   FROM atlas_project_environments"""
            ).fetchone()
        self.assertEqual(tuple(event), (
            "atlas", "test", "Approved initial scope", 1000, 0, "/dev/pts/4"
        ))
        self.assertEqual((association["status"], association["revision"]), ("active", 1))
        self.assertIsNotNone(association["provisioning_event_id"])

    def test_same_operation_and_intent_is_idempotent(self):
        operation_id = str(uuid4())
        first = self._write(operation_id=operation_id)
        second = self._write(operation_id=operation_id, event_id=str(uuid4()))
        self.assertEqual(first, second)
        with self.database.connection() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM atlas_project_environment_provisioning_events"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM atlas_project_environments").fetchone()[0],
                1,
            )

    def test_reused_operation_id_with_different_reason_is_rejected(self):
        operation_id = str(uuid4())
        self._write(operation_id=operation_id)
        with self.assertRaises(ContractError):
            self._write(operation_id=operation_id, reason="Different intent")

    def test_existing_scope_with_new_operation_is_rejected(self):
        self._write()
        with self.assertRaises(ContractError):
            self._write()

    def test_reused_operation_id_with_different_scope_is_rejected(self):
        operation_id = str(uuid4())
        self._write(operation_id=operation_id)
        projects = SQLiteProjectEnvironmentRepository(self.database)
        projects.create_project(ProjectMetadata(ProjectId("other"), "active", 1))
        projects.create_environment(EnvironmentMetadata(EnvironmentId("other-env"), "active", 1))
        other = ProjectEnvironmentAssociation(
            ProjectId("other"), EnvironmentId("other-env"), ProjectEnvironmentStatus.ACTIVE
        )
        with self.assertRaises(ContractError):
            self._write(operation_id=operation_id, association=other)

    def test_writer_participates_in_outer_transaction_and_rolls_back(self):
        with self.assertRaisesRegex(RuntimeError, "force provisioning rollback"):
            with self.database.unit_of_work() as unit:
                joined = SQLiteProjectEnvironmentAssociationProvisioningWriter(
                    self.database, unit_of_work=unit
                )
                joined.create_association(
                    self.association,
                    event_id=str(uuid4()),
                    operation_id=str(uuid4()),
                    reason="Outer transaction test",
                    real_uid=1000,
                    effective_uid=0,
                    terminal_id="/dev/pts/4",
                    occurred_at=datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc),
                )
                raise RuntimeError("force provisioning rollback")
        with self.database.connection() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM atlas_project_environment_provisioning_events"
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM atlas_project_environments").fetchone()[0],
                0,
            )

    def test_direct_association_insert_without_provisioning_event_is_rejected(self):
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """INSERT INTO atlas_project_environments (
                        project_id, environment_id, status, revision,
                        created_at, updated_at
                    ) VALUES ('atlas', 'test', 'active', 1, 'now', 'now')"""
                )

    def test_orphan_provisioning_event_cannot_commit(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.database.unit_of_work() as unit:
                unit._connection_for(self.database).execute(
                    """INSERT INTO atlas_project_environment_provisioning_events (
                        event_id, operation_id, project_id, environment_id, reason,
                        real_uid, effective_uid, terminal_id, occurred_at
                    ) VALUES (?, ?, 'atlas', 'test', 'orphan', 1000, 0,
                              '/dev/pts/4', '2026-11-18T12:00:00+00:00')""",
                    (str(uuid4()), str(uuid4())),
                )
        with self.database.connection() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM atlas_project_environment_provisioning_events"
                ).fetchone()[0],
                0,
            )

    def test_provisioning_event_is_immutable_and_retained(self):
        self._write()
        with self.database.connection() as connection:
            event_id = connection.execute(
                "SELECT event_id FROM atlas_project_environment_provisioning_events"
            ).fetchone()[0]
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """UPDATE atlas_project_environment_provisioning_events
                       SET reason = 'tampered' WHERE event_id = ?""",
                    (event_id,),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM atlas_project_environment_provisioning_events WHERE event_id = ?",
                    (event_id,),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """UPDATE atlas_project_environments
                       SET provisioning_event_id = NULL
                       WHERE project_id = 'atlas' AND environment_id = 'test'"""
                )

    def test_reader_and_general_uow_do_not_expose_creation_capability(self):
        self.assertFalse(hasattr(self.reader, "create_association"))
        from atlas.adapters.sqlite.local_authority_unit_of_work import (
            SQLiteLocalAuthorityUnitOfWork,
        )
        with SQLiteLocalAuthorityUnitOfWork(self.database) as unit:
            self.assertFalse(hasattr(unit.project_environment_associations, "create_association"))
            self.assertFalse(hasattr(unit, "project_environment_association_provisioning_writer"))

