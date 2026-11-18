"""Persistence and transaction tests for the V26 lifecycle ledger adapter."""

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.identity_authority import SQLiteIdentityAuthority
from atlas.adapters.sqlite.local_authority_unit_of_work import SQLiteLocalAuthorityUnitOfWork
from atlas.adapters.sqlite.project_environment_lifecycle_association_writer import SQLiteProjectEnvironmentLifecycleAssociationWriter
from atlas.adapters.sqlite.local_authority_unit_of_work import SQLiteLocalAuthorityUnitOfWorkFactory
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.adapters.sqlite.project_environment_lifecycle_ledger import (
    SQLiteProjectEnvironmentLifecycleLedger,
)
from atlas.adapters.sqlite.project_environment_repository import SQLiteProjectEnvironmentRepository
from atlas.adapters.sqlite.project_environment_association_repository import SQLiteProjectEnvironmentAssociationRepository
from atlas.core.errors import ContractError
from atlas.core.project_environment_lifecycle import ProjectEnvironmentLifecycleEvent
from atlas.memory.metadata import EnvironmentMetadata, ProjectMetadata
from atlas.memory.models import EnvironmentId, ProjectId
from atlas.workspace.models import ProjectEnvironmentAssociation, ProjectEnvironmentStatus


class SQLiteProjectEnvironmentLifecycleLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "atlas.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.user = SQLiteIdentityAuthority(self.database).create_user()
        projects = SQLiteProjectEnvironmentRepository(self.database)
        projects.create_project(ProjectMetadata(ProjectId("atlas"), "active", 1))
        projects.create_environment(EnvironmentMetadata(EnvironmentId("test"), "active", 1))
        self.associations = SQLiteProjectEnvironmentAssociationRepository(self.database)
        self.association = ProjectEnvironmentAssociation(
            ProjectId("atlas"), EnvironmentId("test"), ProjectEnvironmentStatus.ACTIVE
        )
        self.associations.create_association(self.association)
        self.ledger = SQLiteProjectEnvironmentLifecycleLedger(self.database)

    def _event(self, *, previous, new, previous_revision, occurred_at=None):
        return ProjectEnvironmentLifecycleEvent(
            event_id=str(uuid4()),
            project_id=ProjectId("atlas"),
            environment_id=EnvironmentId("test"),
            previous_status=previous,
            new_status=new,
            previous_revision=previous_revision,
            new_revision=previous_revision + 1,
            actor_user_id=self.user.user_id,
            actor_identity_id=self.user.identity.identity_id,
            verified_identity_context_id=str(uuid4()),
            request_id=str(uuid4()),
            correlation_id=str(uuid4()),
            reason="Administrative lifecycle test",
            occurred_at=occurred_at or datetime.now(timezone.utc),
        )

    def _transition(self, current, target):
        event = self._event(
            previous=current.status,
            new=target,
            previous_revision=current.revision,
        )
        with SQLiteLocalAuthorityUnitOfWork(self.database) as unit:
            ledger = SQLiteProjectEnvironmentLifecycleLedger(
                self.database, unit_of_work=unit
            )
            writer = SQLiteProjectEnvironmentLifecycleAssociationWriter(
                self.database, unit_of_work=unit
            )
            ledger.append_event(event)
            writer.update_association(
                replace(current, status=target, revision=current.revision + 1),
                expected_revision=current.revision,
                lifecycle_event_id=event.event_id,
            )
            unit.commit()
        return event

    def test_append_and_read_event_inside_same_uow_as_association_transition(self):
        event = self._event(
            previous=ProjectEnvironmentStatus.ACTIVE,
            new=ProjectEnvironmentStatus.SUSPENDED,
            previous_revision=1,
        )
        with SQLiteLocalAuthorityUnitOfWork(self.database) as unit:
            ledger = SQLiteProjectEnvironmentLifecycleLedger(
                self.database, unit_of_work=unit
            )
            writer = SQLiteProjectEnvironmentLifecycleAssociationWriter(
                self.database, unit_of_work=unit
            )
            with ledger._write_connection() as write_connection:
                self.assertIs(write_connection, unit._connection)
            with ledger._read_connection() as read_connection:
                self.assertIs(read_connection, unit._connection)
            ledger.append_event(event)
            self.assertEqual(
                unit._connection.execute(
                    """SELECT COUNT(*) FROM atlas_project_environment_lifecycle_events
                       WHERE event_id = ?""",
                    (event.event_id,),
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                ledger.list_events("atlas", "test"),
                (event,),
            )
            writer.update_association(
                replace(
                    self.association,
                    status=ProjectEnvironmentStatus.SUSPENDED,
                    revision=2,
                ),
                expected_revision=1,
                lifecycle_event_id=event.event_id,
            )
        self.assertEqual(self.ledger.list_events("atlas", "test"), (event,))

    def test_history_is_ordered_by_association_revision(self):
        first = self._transition(
            self.association, ProjectEnvironmentStatus.SUSPENDED
        )
        suspended = self.associations.get_association(
            ProjectId("atlas"), EnvironmentId("test")
        )
        second = self._transition(
            suspended, ProjectEnvironmentStatus.ACTIVE
        )
        history = self.ledger.list_events("atlas", "test")
        self.assertEqual(history, (first, second))
        self.assertEqual(
            tuple(event.new_revision for event in history),
            (2, 3),
        )

    def test_event_cannot_commit_without_matching_transition(self):
        event = self._event(
            previous=ProjectEnvironmentStatus.ACTIVE,
            new=ProjectEnvironmentStatus.SUSPENDED,
            previous_revision=1,
        )
        with self.assertRaises(ContractError):
            self.ledger.append_event(event)
        self.assertEqual(self.ledger.list_events("atlas", "test"), ())

    def test_event_and_transition_roll_back_together_in_outer_uow(self):
        event = self._event(
            previous=ProjectEnvironmentStatus.ACTIVE,
            new=ProjectEnvironmentStatus.SUSPENDED,
            previous_revision=1,
        )
        with self.assertRaisesRegex(RuntimeError, "force lifecycle rollback"):
            with SQLiteLocalAuthorityUnitOfWork(self.database) as unit:
                ledger = SQLiteProjectEnvironmentLifecycleLedger(
                    self.database, unit_of_work=unit
                )
                writer = SQLiteProjectEnvironmentLifecycleAssociationWriter(
                    self.database, unit_of_work=unit
                )
                ledger.append_event(event)
                writer.update_association(
                    replace(
                        self.association,
                        status=ProjectEnvironmentStatus.SUSPENDED,
                        revision=2,
                    ),
                    expected_revision=1,
                    lifecycle_event_id=event.event_id,
                )
                raise RuntimeError("force lifecycle rollback")
        self.assertEqual(self.ledger.list_events("atlas", "test"), ())
        self.assertEqual(
            self.associations.get_association(ProjectId("atlas"), EnvironmentId("test")),
            self.association,
        )

    def test_append_rejects_non_event_and_list_requires_normalized_scope(self):
        with self.assertRaises(ContractError):
            self.ledger.append_event(object())
        for project, environment in (("", "test"), ("atlas", ""), (" atlas", "test")):
            with self.subTest(project=project, environment=environment):
                with self.assertRaises(ContractError):
                    self.ledger.list_events(project, environment)

    def test_empty_history_returns_empty_tuple(self):
        self.assertEqual(self.ledger.list_events("atlas", "test"), ())

    def test_runtime_local_authority_uow_does_not_expose_lifecycle_writer(self):
        factory = SQLiteLocalAuthorityUnitOfWorkFactory(self.database)
        with factory() as unit:
            self.assertFalse(hasattr(unit, "lifecycle_ledger"))
            unit.commit()


if __name__ == "__main__":
    unittest.main()
