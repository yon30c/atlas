"""Offline-only SQLite Platform Admin bootstrap adapter tests."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.identity_authority import SQLiteIdentityAuthority
from atlas.adapters.sqlite.local_authority_unit_of_work import (
    SQLiteLocalAuthorityUnitOfWorkFactory,
)
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.adapters.sqlite.platform_admin_authority import (
    SQLitePlatformAdminAuthorityReader,
)
from atlas.adapters.sqlite.platform_admin_bootstrap import (
    SQLitePlatformAdminBootstrapAdapter,
)
from atlas.core.errors import AuthorizationError, ConcurrencyError, ContractError
from atlas.core.identity import IdentityStatus
from atlas.core.platform_admin import (
    INITIAL_PLATFORM_ADMIN_PERMISSIONS,
    PlatformAdminBootstrapCommand,
    PlatformAdminBootstrapProvenance,
    PlatformAdminBootstrapRequest,
    PlatformAdminGrant,
    PlatformAdminProvisioningMethod,
)


def _uuid():
    return str(uuid4())


class SQLitePlatformAdminBootstrapAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "atlas.sqlite")
        self.assertEqual(self.database.apply_migrations(SQLITE_MIGRATIONS[:-1]), 27)
        self.identity = SQLiteIdentityAuthority(self.database)
        self.adapter = SQLitePlatformAdminBootstrapAdapter(self.database)
        self.now = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)

    def _command(self, user_id, *, operation_id=None, event_id=None, grant_id=None,
                 terminal="/dev/pts/4", real_uid=1000, effective_uid=1000):
        canonical = self.identity.get_user(user_id)
        operation_id = operation_id or _uuid()
        event_id = event_id or _uuid()
        grant_id = grant_id or _uuid()
        request = PlatformAdminBootstrapRequest(
            operation_id=operation_id,
            user_id=user_id,
            permissions=INITIAL_PLATFORM_ADMIN_PERMISSIONS,
        )
        provenance = PlatformAdminBootstrapProvenance(
            event_id=event_id,
            grant_id=grant_id,
            operator_real_uid=real_uid,
            operator_effective_uid=effective_uid,
            terminal_id=terminal,
            confirmed_at=self.now,
        )
        grant = PlatformAdminGrant(
            grant_id=grant_id,
            user_id=user_id,
            user_identity_id=canonical.identity.identity_id,
            user_identity_revision=canonical.identity.revision,
            permissions=INITIAL_PLATFORM_ADMIN_PERMISSIONS,
            provisioning_method=PlatformAdminProvisioningMethod.OFFLINE_BOOTSTRAP,
            bootstrap_event_id=event_id,
            issued_at=self.now,
            not_before=self.now,
            expires_at=self.now + timedelta(days=90),
        )
        return PlatformAdminBootstrapCommand(request, provenance, grant)

    def _new_user(self):
        return self.identity.create_user()

    def test_provisions_first_admin_and_persists_event_atomically(self):
        user = self._new_user()
        command = self._command(user.user_id)
        result = self.adapter.provision_first_admin(command)
        self.assertEqual(result, command.grant)
        reader = SQLitePlatformAdminAuthorityReader(self.database)
        self.assertEqual(reader.get_grant(command.grant.grant_id), command.grant)
        self.assertEqual(reader.list_grants_for_user(user.user_id), (command.grant,))
        with self.database.connection() as connection:
            event = connection.execute(
                "SELECT * FROM platform_admin_bootstrap_events WHERE operation_id = ?",
                (command.request.operation_id,),
            ).fetchone()
        self.assertEqual(event["event_id"], command.provenance.event_id)
        self.assertEqual(event["operator_real_uid"], 1000)

    def test_exact_operation_replay_returns_existing_grant_without_duplicate_rows(self):
        user = self._new_user()
        command = self._command(user.user_id)
        first = self.adapter.provision_first_admin(command)
        second = self.adapter.provision_first_admin(command)
        self.assertEqual(first, second)
        with self.database.connection() as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM platform_admin_bootstrap_events"
            ).fetchone()[0], 1)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM platform_admin_grants"
            ).fetchone()[0], 1)


    def test_get_operation_recovers_exact_persisted_command_for_service_retry(self):
        user = self._new_user()
        command = self._command(user.user_id)
        self.adapter.provision_first_admin(command)
        recovered = self.adapter.get_operation(command.request.operation_id)
        self.assertEqual(recovered, command)
        self.assertEqual(
            self.adapter.get_operation(_uuid()),
            None,
        )

    def test_operation_id_replay_with_changed_provenance_is_conflict(self):
        user = self._new_user()
        command = self._command(user.user_id)
        self.adapter.provision_first_admin(command)
        changed = self._command(
            user.user_id,
            operation_id=command.request.operation_id,
            event_id=command.provenance.event_id,
            grant_id=command.grant.grant_id,
            terminal="/dev/pts/9",
        )
        with self.assertRaises(ConcurrencyError):
            self.adapter.provision_first_admin(changed)

    def test_operation_id_replay_with_changed_user_or_grant_claims_is_conflict(self):
        first_user = self._new_user()
        second_user = self._new_user()
        command = self._command(first_user.user_id)
        self.adapter.provision_first_admin(command)
        changed = self._command(
            second_user.user_id,
            operation_id=command.request.operation_id,
            event_id=command.provenance.event_id,
            grant_id=command.grant.grant_id,
        )
        with self.assertRaises(ConcurrencyError):
            self.adapter.provision_first_admin(changed)

    def test_different_operation_is_rejected_after_any_bootstrap_history(self):
        first_user = self._new_user()
        second_user = self._new_user()
        self.adapter.provision_first_admin(self._command(first_user.user_id))
        with self.assertRaises(AuthorizationError):
            self.adapter.provision_first_admin(self._command(second_user.user_id))

    def test_suspended_user_is_rejected_without_bootstrap_writes(self):
        user = self._new_user()
        self.identity.update_user_status(
            user.user_id,
            expected_revision=user.identity.revision,
            status=IdentityStatus.SUSPENDED,
        )
        # Build a structurally valid command against the now-current revision.
        command = self._command(user.user_id)
        with self.assertRaises(AuthorizationError):
            self.adapter.provision_first_admin(command)
        with self.database.connection() as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM platform_admin_bootstrap_events"
            ).fetchone()[0], 0)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM platform_admin_grants"
            ).fetchone()[0], 0)

    def test_stale_identity_revision_is_rejected_without_writes(self):
        user = self._new_user()
        command = self._command(user.user_id)
        self.identity.update_user_status(
            user.user_id,
            expected_revision=user.identity.revision,
            status=IdentityStatus.SUSPENDED,
        )
        with self.assertRaises(AuthorizationError):
            self.adapter.provision_first_admin(command)
        with self.database.connection() as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM platform_admin_bootstrap_events"
            ).fetchone()[0], 0)

    def test_failure_after_both_inserts_rolls_back_event_and_grant(self):
        user = self._new_user()
        command = self._command(user.user_id)
        with patch.object(
            SQLitePlatformAdminBootstrapAdapter,
            "_load_grant",
            side_effect=RuntimeError("forced post-insert verification failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "forced post-insert"):
                self.adapter.provision_first_admin(command)
        with self.database.connection() as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM platform_admin_bootstrap_events"
            ).fetchone()[0], 0)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM platform_admin_grants"
            ).fetchone()[0], 0)

    def test_runtime_uow_does_not_expose_offline_bootstrap_adapter(self):
        with SQLiteLocalAuthorityUnitOfWorkFactory(self.database)() as unit:
            self.assertIsNotNone(unit.platform_admin)
            self.assertFalse(hasattr(unit, "platform_admin_bootstrap"))
            self.assertFalse(hasattr(unit.platform_admin, "provision_first_admin"))
            unit.commit()

    def test_two_concurrent_first_bootstraps_cannot_both_succeed(self):
        users = (self._new_user(), self._new_user())
        commands = tuple(self._command(user.user_id) for user in users)

        def attempt(command):
            try:
                self.adapter.provision_first_admin(command)
                return "created"
            except AuthorizationError:
                return "denied"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = tuple(pool.map(attempt, commands))
        self.assertCountEqual(results, ("created", "denied"))
        with self.database.connection() as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM platform_admin_bootstrap_events"
            ).fetchone()[0], 1)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM platform_admin_grants WHERE status = 'active'"
            ).fetchone()[0], 1)


    def test_bootstrap_event_cannot_be_updated_or_deleted(self):
        user = self._new_user()
        command = self._command(user.user_id)
        self.adapter.provision_first_admin(command)

        with self.assertRaises(sqlite3.IntegrityError):
            with self.database.unit_of_work() as unit:
                connection = unit._connection_for(self.database)
                connection.execute(
                    """
                    UPDATE platform_admin_bootstrap_events
                    SET terminal_id = ?
                    WHERE event_id = ?
                    """,
                    ("/dev/pts/99", command.provenance.event_id),
                )

        with self.assertRaises(sqlite3.IntegrityError):
            with self.database.unit_of_work() as unit:
                connection = unit._connection_for(self.database)
                connection.execute(
                    "DELETE FROM platform_admin_bootstrap_events WHERE event_id = ?",
                    (command.provenance.event_id,),
                )

        recovered = self.adapter.get_operation(command.request.operation_id)
        self.assertEqual(recovered, command)

    def test_grant_claims_and_tombstone_cannot_be_deleted(self):
        user = self._new_user()
        command = self._command(user.user_id)
        self.adapter.provision_first_admin(command)

        with self.assertRaises(sqlite3.IntegrityError):
            with self.database.unit_of_work() as unit:
                connection = unit._connection_for(self.database)
                connection.execute(
                    """
                    UPDATE platform_admin_grants
                    SET permissions_json = '["association.suspend"]'
                    WHERE grant_id = ?
                    """,
                    (command.grant.grant_id,),
                )

        with self.assertRaises(sqlite3.IntegrityError):
            with self.database.unit_of_work() as unit:
                connection = unit._connection_for(self.database)
                connection.execute(
                    "DELETE FROM platform_admin_grants WHERE grant_id = ?",
                    (command.grant.grant_id,),
                )

        self.assertEqual(
            SQLitePlatformAdminAuthorityReader(self.database).get_grant(
                command.grant.grant_id
            ),
            command.grant,
        )

    def test_grant_revocation_is_terminal_and_revisioned(self):
        user = self._new_user()
        revoker = self._new_user()
        command = self._command(user.user_id)
        self.adapter.provision_first_admin(command)
        revoked_at = self.now + timedelta(days=1)

        with self.database.unit_of_work() as unit:
            connection = unit._connection_for(self.database)
            connection.execute(
                """
                UPDATE platform_admin_grants
                SET status = 'revoked',
                    revision = revision + 1,
                    revoked_at = ?,
                    revoked_by_user_id = ?
                WHERE grant_id = ?
                """,
                (
                    revoked_at.isoformat(timespec="microseconds"),
                    revoker.user_id,
                    command.grant.grant_id,
                ),
            )

        reader = SQLitePlatformAdminAuthorityReader(self.database)
        revoked = reader.get_grant(command.grant.grant_id)
        self.assertEqual(revoked.status.value, "revoked")
        self.assertEqual(revoked.revision, 2)
        self.assertEqual(revoked.revoked_at, revoked_at)
        self.assertEqual(revoked.revoked_by_user_id, revoker.user_id)

        with self.assertRaises(sqlite3.IntegrityError):
            with self.database.unit_of_work() as unit:
                connection = unit._connection_for(self.database)
                connection.execute(
                    """
                    UPDATE platform_admin_grants
                    SET status = 'active',
                        revision = revision + 1,
                        revoked_at = NULL,
                        revoked_by_user_id = NULL
                    WHERE grant_id = ?
                    """,
                    (command.grant.grant_id,),
                )

        with self.assertRaises(sqlite3.IntegrityError):
            with self.database.unit_of_work() as unit:
                connection = unit._connection_for(self.database)
                connection.execute(
                    "DELETE FROM platform_admin_grants WHERE grant_id = ?",
                    (command.grant.grant_id,),
                )

        self.assertEqual(reader.get_grant(command.grant.grant_id), revoked)

    def test_revoked_bootstrap_history_cannot_be_replaced_by_new_bootstrap(self):
        first_user = self._new_user()
        revoker = self._new_user()
        replacement_user = self._new_user()
        command = self._command(first_user.user_id)
        self.adapter.provision_first_admin(command)

        with self.database.unit_of_work() as unit:
            connection = unit._connection_for(self.database)
            connection.execute(
                """
                UPDATE platform_admin_grants
                SET status = 'revoked',
                    revision = revision + 1,
                    revoked_at = ?,
                    revoked_by_user_id = ?
                WHERE grant_id = ?
                """,
                (
                    (self.now + timedelta(days=1)).isoformat(timespec="microseconds"),
                    revoker.user_id,
                    command.grant.grant_id,
                ),
            )

        with self.assertRaises(AuthorizationError):
            self.adapter.provision_first_admin(self._command(replacement_user.user_id))

        with self.database.connection() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM platform_admin_bootstrap_events"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM platform_admin_grants"
                ).fetchone()[0],
                1,
            )


if __name__ == "__main__":
    unittest.main()
