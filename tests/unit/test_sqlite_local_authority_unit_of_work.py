"""Tests for one transaction spanning canonical local authority repositories."""

from pathlib import Path
from datetime import datetime, timezone
import tempfile
import unittest

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.identity_authority import SQLiteIdentityAuthority
from atlas.adapters.sqlite.project_environment_repository import SQLiteProjectEnvironmentRepository
from atlas.adapters.sqlite.local_authority_unit_of_work import (
    SQLiteLocalAuthorityUnitOfWorkFactory,
)
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.core.errors import ContractError
from atlas.core.identity import IdentityStatus
from atlas.memory.authority_changes import (
    AuthorityChangeTarget,
    AuthorityChangeTargetKind,
    MultiAuthorityChangeIntent,
)
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
            self.assertIsNotNone(unit.agent_identity)
            self.assertIsNotNone(unit.native_identity)
            self.assertIsNotNone(unit.native_agent_identity)
            self.assertIsNotNone(unit.agent_delegations)
            self.assertIsNotNone(unit.native_authentication)
            self.assertIsNotNone(unit.grants)
            self.assertIsNotNone(unit.renewals)
            self.assertIsNotNone(unit.project_environments)
            self.assertIsNotNone(unit.authority_changes)
            self.assertIs(unit.authority_changes._unit_of_work, unit._unit)
            self.assertIs(unit.identity._unit_of_work, unit._unit)
            self.assertIs(unit.agent_identity._unit_of_work, unit._unit)
            self.assertIs(unit.native_identity._unit_of_work, unit._unit)
            self.assertIs(unit.native_agent_identity._unit_of_work, unit._unit)
            self.assertIs(unit.agent_delegations._unit_of_work, unit._unit)
            self.assertIs(unit.native_authentication._unit_of_work, unit._unit)
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

        identity = SQLiteIdentityAuthority(self.database)
        project_environments = SQLiteProjectEnvironmentRepository(self.database)
        self.assertEqual(identity.get_user(user.user_id), user)
        self.assertEqual(project_environments.get_project("atlas"), project)
        self.assertEqual(
            project_environments.get_environment("local"),
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
        with self.assertRaises(ContractError):
            unit.identity.update_user_status(
                user.user_id,
                expected_revision=1,
                status=IdentityStatus.SUSPENDED,
            )


    @staticmethod
    def _multi_change_intent(key="shared-uow-change"):
        return MultiAuthorityChangeIntent(
            idempotency_key=key,
            consumer_id="atlas-local",
            action="grant.renewal.approve",
            actor_identity_id="user-001",
            owner_id="user-001",
            project_id="project-001",
            environment_id="development",
            targets=(
                AuthorityChangeTarget(
                    AuthorityChangeTargetKind.GRANT, "grant-001", 4, 5
                ),
                AuthorityChangeTarget(
                    AuthorityChangeTargetKind.GRANT_RENEWAL, "renewal-001", 2, 3
                ),
            ),
            request_context_ref="request-shared-uow",
            requested_at=datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc),
        )

    def test_authority_change_ledger_commits_with_canonical_authorities(self):
        with self.factory() as unit:
            user = unit.identity.create_user()
            intent = self._multi_change_intent()
            reservation = unit.authority_changes.reserve_multi_change(intent)
            unit.project_environments.create_project(
                ProjectMetadata(ProjectId("shared-project"), "active", 1)
            )
            unit.commit()

        from atlas.adapters.sqlite.authority_changes import SQLiteAuthorityChangeStore
        from atlas.adapters.sqlite.identity_authority import SQLiteIdentityAuthority
        self.assertEqual(
            SQLiteIdentityAuthority(self.database).get_user(user.user_id),
            user,
        )
        self.assertIsNotNone(
            SQLiteAuthorityChangeStore(self.database).get_multi_reservation(
                reservation.operation_id
            )
        )

    def test_authority_change_ledger_rolls_back_with_canonical_authorities(self):
        operation_id = None
        with self.assertRaisesRegex(RuntimeError, "force full authority rollback"):
            with self.factory() as unit:
                user = unit.identity.create_user()
                reservation = unit.authority_changes.reserve_multi_change(
                    self._multi_change_intent("shared-uow-rollback")
                )
                operation_id = reservation.operation_id
                unit.project_environments.create_project(
                    ProjectMetadata(ProjectId("rollback-shared"), "active", 1)
                )
                raise RuntimeError("force full authority rollback")

        from atlas.adapters.sqlite.authority_changes import SQLiteAuthorityChangeStore
        from atlas.adapters.sqlite.identity_authority import SQLiteIdentityAuthority
        self.assertIsNone(
            SQLiteAuthorityChangeStore(self.database).get_multi_reservation(
                operation_id
            )
        )
        with self.database.connection() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM atlas_users"
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM atlas_projects WHERE project_id = 'rollback-shared'"
                ).fetchone()[0],
                0,
            )

    def test_authority_change_store_rejects_use_after_shared_unit_exit(self):
        with self.factory() as unit:
            reservation = unit.authority_changes.reserve_multi_change(
                self._multi_change_intent("shared-uow-expired")
            )
            unit.commit()
        with self.assertRaises(ContractError):
            unit.authority_changes.get_multi_reservation(
                reservation.operation_id
            )


if __name__ == "__main__":
    unittest.main()
