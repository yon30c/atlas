"""Adversarial tests for the V26 Project/Environment lifecycle schema."""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.identity_authority import SQLiteIdentityAuthority
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.adapters.sqlite.project_environment_repository import SQLiteProjectEnvironmentRepository
from atlas.adapters.sqlite.project_environment_association_repository import SQLiteProjectEnvironmentAssociationRepository
from atlas.memory.metadata import EnvironmentMetadata, ProjectMetadata
from atlas.memory.models import EnvironmentId, ProjectId
from atlas.workspace.models import ProjectEnvironmentAssociation, ProjectEnvironmentStatus


class SQLiteProjectEnvironmentLifecycleMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "authority.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS[:-1])
        self.identity = SQLiteIdentityAuthority(self.database).create_user()
        projects = SQLiteProjectEnvironmentRepository(self.database)
        projects.create_project(ProjectMetadata(ProjectId("atlas"), "active", 1))
        projects.create_environment(EnvironmentMetadata(EnvironmentId("test"), "active", 1))
        self.registry = SQLiteProjectEnvironmentAssociationRepository(self.database)
        self.association = ProjectEnvironmentAssociation(
            ProjectId("atlas"), EnvironmentId("test"), ProjectEnvironmentStatus.ACTIVE
        )
        self.registry.create_association(self.association)
        self.database.apply_migrations(SQLITE_MIGRATIONS)

    def _insert_event(self, connection, *, previous_status, new_status,
                      previous_revision=1, event_id=None, actor_user_id=None,
                      actor_identity_id=None):
        event_id = event_id or str(uuid4())
        connection.execute(
            """INSERT INTO atlas_project_environment_lifecycle_events (
                event_id, project_id, environment_id, previous_status, new_status,
                previous_revision, new_revision, actor_user_id, actor_identity_id,
                verified_identity_context_id, request_id, correlation_id, reason, occurred_at
            ) VALUES (?, 'atlas', 'test', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id, previous_status, new_status, previous_revision,
                previous_revision + 1, actor_user_id or self.identity.user_id,
                actor_identity_id or self.identity.identity.identity_id, str(uuid4()),
                str(uuid4()), str(uuid4()), "Approved lifecycle transition",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return event_id

    def test_existing_association_is_preserved_without_synthetic_history(self):
        with self.database.connection() as connection:
            row = connection.execute(
                """SELECT status, revision, last_lifecycle_event_id
                   FROM atlas_project_environments
                   WHERE project_id = 'atlas' AND environment_id = 'test'"""
            ).fetchone()
            count = connection.execute(
                "SELECT COUNT(*) FROM atlas_project_environment_lifecycle_events"
            ).fetchone()[0]
        self.assertEqual((row["status"], row["revision"], row["last_lifecycle_event_id"]),
                         ("active", 1, None))
        self.assertEqual(count, 0)

    def test_orphan_event_cannot_commit_without_completed_transition(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.database.unit_of_work() as unit:
                self._insert_event(
                    unit._connection_for(self.database),
                    previous_status="active", new_status="suspended",
                )
        with self.database.connection() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM atlas_project_environment_lifecycle_events"
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_transition_without_matching_event_is_rejected(self):
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """UPDATE atlas_project_environments
                       SET status = 'suspended', revision = 2, updated_at = ?,
                           last_lifecycle_event_id = ?
                       WHERE project_id = 'atlas' AND environment_id = 'test'""",
                    (datetime.now(timezone.utc).isoformat(), str(uuid4())),
                )

    def test_matching_event_and_association_transition_commit_together(self):
        event_id = str(uuid4())
        with self.database.unit_of_work() as unit:
            connection = unit._connection_for(self.database)
            inserted = self._insert_event(
                connection, previous_status="active", new_status="suspended",
                event_id=event_id,
            )
            connection.execute(
                """UPDATE atlas_project_environments
                   SET status = 'suspended', revision = 2, updated_at = ?,
                       last_lifecycle_event_id = ?
                   WHERE project_id = 'atlas' AND environment_id = 'test' AND revision = 1""",
                (datetime.now(timezone.utc).isoformat(), inserted),
            )
        with self.database.connection() as connection:
            association = connection.execute(
                """SELECT status, revision, last_lifecycle_event_id
                   FROM atlas_project_environments
                   WHERE project_id = 'atlas' AND environment_id = 'test'"""
            ).fetchone()
            event = connection.execute(
                """SELECT previous_status, new_status, previous_revision, new_revision
                   FROM atlas_project_environment_lifecycle_events WHERE event_id = ?""",
                (event_id,),
            ).fetchone()
        self.assertEqual((association["status"], association["revision"],
                          association["last_lifecycle_event_id"]),
                         ("suspended", 2, event_id))
        self.assertEqual(tuple(event), ("active", "suspended", 1, 2))

    def test_event_and_transition_roll_back_together(self):
        with self.assertRaisesRegex(RuntimeError, "force lifecycle rollback"):
            with self.database.unit_of_work() as unit:
                connection = unit._connection_for(self.database)
                event_id = self._insert_event(
                    connection, previous_status="active", new_status="suspended"
                )
                connection.execute(
                    """UPDATE atlas_project_environments
                       SET status = 'suspended', revision = 2, updated_at = ?,
                           last_lifecycle_event_id = ?
                       WHERE project_id = 'atlas' AND environment_id = 'test'""",
                    (datetime.now(timezone.utc).isoformat(), event_id),
                )
                raise RuntimeError("force lifecycle rollback")
        with self.database.connection() as connection:
            association = connection.execute(
                """SELECT status, revision FROM atlas_project_environments
                   WHERE project_id = 'atlas' AND environment_id = 'test'"""
            ).fetchone()
            count = connection.execute(
                "SELECT COUNT(*) FROM atlas_project_environment_lifecycle_events"
            ).fetchone()[0]
            marker_count = connection.execute(
                "SELECT COUNT(*) FROM atlas_project_environment_lifecycle_commits"
            ).fetchone()[0]
        self.assertEqual(tuple(association), ("active", 1))
        self.assertEqual((count, marker_count), (0, 0))

    def test_stale_event_is_rejected(self):
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                self._insert_event(
                    connection, previous_status="suspended", new_status="active",
                    previous_revision=2,
                )

    def test_event_requires_exact_active_canonical_user_actor(self):
        other = SQLiteIdentityAuthority(self.database).create_user()
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                self._insert_event(
                    connection, previous_status="active", new_status="suspended",
                    actor_user_id=self.identity.user_id, actor_identity_id=other.identity.identity_id,
                )

    def test_events_are_immutable_and_retained(self):
        with self.database.unit_of_work() as unit:
            connection = unit._connection_for(self.database)
            event_id = self._insert_event(
                connection, previous_status="active", new_status="suspended"
            )
            connection.execute(
                """UPDATE atlas_project_environments
                   SET status = 'suspended', revision = 2, updated_at = ?,
                       last_lifecycle_event_id = ?
                   WHERE project_id = 'atlas' AND environment_id = 'test'""",
                (datetime.now(timezone.utc).isoformat(), event_id),
            )
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE atlas_project_environment_lifecycle_events SET reason = 'tampered' WHERE event_id = ?",
                    (event_id,),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM atlas_project_environment_lifecycle_events WHERE event_id = ?",
                    (event_id,),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE atlas_project_environment_lifecycle_commits SET new_revision = 99 WHERE event_id = ?",
                    (event_id,),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM atlas_project_environment_lifecycle_commits WHERE event_id = ?",
                    (event_id,),
                )

    def test_association_cannot_advance_revision_without_a_real_transition(self):
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """UPDATE atlas_project_environments
                       SET revision = 2, updated_at = ?
                       WHERE project_id = 'atlas' AND environment_id = 'test'""",
                    (datetime.now(timezone.utc).isoformat(),),
                )


if __name__ == "__main__":
    unittest.main()
