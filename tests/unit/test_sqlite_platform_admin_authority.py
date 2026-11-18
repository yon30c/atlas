"""SQLite persistence and shared-UoW tests for Platform Admin grants."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.local_authority_unit_of_work import (
    SQLiteLocalAuthorityUnitOfWorkFactory,
)
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.adapters.sqlite.platform_admin_authority import (
    SQLitePlatformAdminAuthorityReader,
)
from atlas.core.identity import IdentityStatus
from atlas.core.platform_admin import (
    PlatformAdminGrantStatus,
    PlatformAdminPermission,
)


def _uuid():
    return str(uuid4())


class SQLitePlatformAdminAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "atlas.sqlite")
        self.assertEqual(self.database.apply_migrations(SQLITE_MIGRATIONS), 26)
        self.factory = SQLiteLocalAuthorityUnitOfWorkFactory(self.database)

    def _insert_grant(self, unit, user, *, permissions=None):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        grant_id = _uuid()
        event_id = _uuid()
        operation_id = _uuid()
        connection = unit._unit._connection_for(self.database)
        connection.execute(
            """INSERT INTO platform_admin_bootstrap_events (
                event_id, grant_id, user_id, user_identity_id,
                user_identity_revision, operation_id, operator_real_uid,
                operator_effective_uid, terminal_id, confirmed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id, grant_id, user.user_id, user.identity.identity_id,
                user.identity.revision, operation_id, 1000, 1000,
                "/dev/pts/3", now.isoformat(),
            ),
        )
        connection.execute(
            """INSERT INTO platform_admin_grants (
                grant_id, user_id, user_identity_id, user_identity_revision,
                permissions_json, provisioning_method, bootstrap_event_id,
                issued_at, not_before, expires_at, status, revision
            ) VALUES (?, ?, ?, ?, ?, 'offline_bootstrap', ?, ?, ?, ?, 'active', 1)""",
            (
                grant_id, user.user_id, user.identity.identity_id,
                user.identity.revision,
                json.dumps(permissions or ["association.suspend"]),
                event_id, now.isoformat(), now.isoformat(),
                (now + timedelta(days=30)).isoformat(),
            ),
        )
        return grant_id

    def test_migration_v25_is_registered_and_idempotently_reapplied(self):
        self.assertEqual(self.database.apply_migrations(SQLITE_MIGRATIONS), 25)
        with self.database.connection() as connection:
            version = connection.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()[0]
        self.assertEqual(version, 26)

    def test_reader_returns_empty_for_user_without_admin_grant(self):
        with self.factory() as unit:
            user = unit.identity.create_user()
            unit.commit()
        self.assertEqual(SQLitePlatformAdminAuthorityReader(self.database).list_grants_for_user(user.user_id), ())

    def test_grant_is_readable_inside_shared_uow_and_after_commit(self):
        with self.factory() as unit:
            user = unit.identity.create_user()
            grant_id = self._insert_grant(unit, user)
            grant = unit.platform_admin.get_grant(grant_id)
            self.assertEqual(grant.user_id, user.user_id)
            self.assertEqual(grant.user_identity_revision, user.identity.revision)
            self.assertEqual(grant.permissions, frozenset({PlatformAdminPermission.ASSOCIATION_SUSPEND}))
            self.assertIs(unit.platform_admin._unit_of_work, unit._unit)
            unit.commit()
        persisted = SQLitePlatformAdminAuthorityReader(self.database).get_grant(grant_id)
        self.assertEqual(persisted, grant)

    def test_shared_uow_rolls_back_bootstrap_event_and_grant_together(self):
        grant_id = None
        with self.assertRaisesRegex(RuntimeError, "rollback"):
            with self.factory() as unit:
                user = unit.identity.create_user()
                grant_id = self._insert_grant(unit, user)
                raise RuntimeError("rollback")
        self.assertIsNone(SQLitePlatformAdminAuthorityReader(self.database).get_grant(grant_id))
        with self.database.connection() as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM platform_admin_bootstrap_events"
            ).fetchone()[0], 0)

    def test_deferred_event_grant_foreign_key_rejects_orphan_event(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.factory() as unit:
                user = unit.identity.create_user()
                now = datetime.now(timezone.utc).isoformat()
                connection = unit._unit._connection_for(self.database)
                connection.execute(
                    """INSERT INTO platform_admin_bootstrap_events (
                        event_id, grant_id, user_id, user_identity_id,
                        user_identity_revision, operation_id, operator_real_uid,
                        operator_effective_uid, terminal_id, confirmed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1000, 1000, '/dev/pts/1', ?)""",
                    (_uuid(), _uuid(), user.user_id, user.identity.identity_id,
                     user.identity.revision, _uuid(), now),
                )
                unit.commit()

    def test_unknown_or_duplicate_permission_is_rejected_by_sql(self):
        for permissions in (["*"], ["association.suspend", "association.suspend"]):
            with self.subTest(permissions=permissions):
                with self.factory() as unit:
                    user = unit.identity.create_user()
                    with self.assertRaises(sqlite3.IntegrityError):
                        self._insert_grant(unit, user, permissions=permissions)

    def test_bootstrap_requires_exact_active_user_identity_revision(self):
        with self.factory() as unit:
            user = unit.identity.create_user()
            unit.identity.update_user_status(
                user.user_id,
                expected_revision=user.identity.revision,
                status=IdentityStatus.SUSPENDED,
            )
            with self.assertRaises(sqlite3.IntegrityError):
                self._insert_grant(unit, user)

    def test_runtime_uow_exposes_reader_but_no_bootstrap_writer(self):
        with self.factory() as unit:
            self.assertIsNotNone(unit.platform_admin)
            self.assertFalse(hasattr(unit.platform_admin, "provision_first_admin"))
            unit.commit()


if __name__ == "__main__":
    unittest.main()
