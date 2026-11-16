"""Tests for canonical UserId <-> Identity(USER) SQLite persistence."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import UUID

from atlas.adapters.sqlite import SQLiteDatabase, SQLITE_MIGRATIONS
from atlas.adapters.sqlite.identity_authority import SQLiteIdentityAuthority
from atlas.core.errors import (
    ConcurrencyError,
    ContractError,
    IdentityConflictError,
)
from atlas.core.identity import IdentityStatus


class SQLiteIdentityAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "atlas.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.authority = SQLiteIdentityAuthority(self.database)

    def test_create_user_generates_canonical_uuid4_pair(self):
        user = self.authority.create_user()
        self.assertEqual(user.identity.kind.value, "user")
        self.assertEqual(user.identity.status, IdentityStatus.ACTIVE)
        self.assertEqual(user.identity.revision, 1)
        self.assertEqual(str(UUID(user.user_id)), user.user_id)
        self.assertEqual(UUID(user.user_id).version, 4)
        self.assertEqual(str(UUID(user.identity.identity_id)), user.identity.identity_id)
        self.assertEqual(UUID(user.identity.identity_id).version, 4)
        self.assertEqual(self.authority.get_user(user.user_id), user)

    def test_duplicate_user_id_is_rejected_without_orphan_identity(self):
        ids = [
            UUID("11111111-1111-4111-8111-111111111111"),
            UUID("22222222-2222-4222-8222-222222222222"),
            UUID("11111111-1111-4111-8111-111111111111"),
            UUID("33333333-3333-4333-8333-333333333333"),
        ]
        with patch("atlas.adapters.sqlite.identity_authority.uuid4", side_effect=ids):
            self.authority.create_user()
            with self.assertRaises(IdentityConflictError):
                self.authority.create_user()
        with self.database.connection() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM identity_records").fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM atlas_users").fetchone()[0],
                1,
            )

    def test_stale_compare_and_swap_does_not_overwrite(self):
        user = self.authority.create_user()
        updated = self.authority.update_user_status(
            user.user_id,
            expected_revision=1,
            status=IdentityStatus.SUSPENDED,
        )
        self.assertEqual(updated.identity.revision, 2)
        self.assertEqual(updated.identity.status, IdentityStatus.SUSPENDED)
        with self.assertRaises(ConcurrencyError):
            self.authority.update_user_status(
                user.user_id,
                expected_revision=1,
                status=IdentityStatus.ACTIVE,
            )
        self.assertEqual(self.authority.get_user(user.user_id), updated)

    def test_revoked_identity_is_terminal(self):
        user = self.authority.create_user()
        revoked = self.authority.update_user_status(
            user.user_id,
            expected_revision=1,
            status=IdentityStatus.REVOKED,
        )
        with self.assertRaises(ContractError):
            self.authority.update_user_status(
                user.user_id,
                expected_revision=2,
                status=IdentityStatus.ACTIVE,
            )
        self.assertEqual(self.authority.get_user(user.user_id), revoked)

    def test_concurrent_updates_allow_only_one_expected_revision(self):
        user = self.authority.create_user()
        barrier = threading.Barrier(2)

        def update(status):
            barrier.wait(timeout=5)
            try:
                return self.authority.update_user_status(
                    user.user_id,
                    expected_revision=1,
                    status=status,
                )
            except ConcurrencyError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(update, (IdentityStatus.SUSPENDED, IdentityStatus.REVOKED)))
        self.assertEqual(sum(result is not None for result in results), 1)
        persisted = self.authority.get_user(user.user_id)
        self.assertEqual(persisted.identity.revision, 2)

    def test_failed_second_insert_rolls_back_identity_insert(self):
        with self.database.connection() as connection:
            connection.execute(
                """
                CREATE TRIGGER test_abort_user_insert
                BEFORE INSERT ON atlas_users
                BEGIN
                    SELECT RAISE(ABORT, 'forced test failure');
                END;
                """
            )
        with self.assertRaises(IdentityConflictError):
            self.authority.create_user()
        with self.database.connection() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM identity_records").fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM atlas_users").fetchone()[0],
                0,
            )

    def test_schema_rejects_noncanonical_or_non_v4_identity_id(self):
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO identity_records (
                        identity_id, identity_kind, identity_status, revision,
                        created_at, updated_at, user_id
                    ) VALUES (
                        'NOT-A-UUID', 'user', 'active', 1, 'now', 'now',
                        '77777777-7777-4777-8777-777777777777'
                    )
                    """
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO identity_records (
                        identity_id, identity_kind, identity_status, revision,
                        created_at, updated_at, user_id
                    ) VALUES (
                        '11111111-1111-1111-8111-111111111111',
                        'user', 'active', 1, 'now', 'now',
                        '77777777-7777-4777-8777-777777777777'
                    )
                    """
                )

    def test_schema_enforces_user_kind_and_one_to_one_identity_relation(self):
        agent_identity = "22222222-2222-4222-8222-222222222222"
        user_id = "33333333-3333-4333-8333-333333333333"
        canonical_identity = "44444444-4444-4444-8444-444444444444"
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO identity_records (
                    identity_id, identity_kind, identity_status, revision,
                    created_at, updated_at
                ) VALUES (?, 'agent', 'active', 1, 'now', 'now')
                """,
                (agent_identity,),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO atlas_users (user_id, identity_id, created_at) VALUES (?, ?, 'now')",
                    (user_id, agent_identity),
                )

            connection.execute("BEGIN")
            connection.execute(
                """
                INSERT INTO identity_records (
                    identity_id, identity_kind, identity_status, revision,
                    created_at, updated_at, user_id
                ) VALUES (?, 'user', 'active', 1, 'now', 'now', ?)
                """,
                (canonical_identity, user_id),
            )
            connection.execute(
                "INSERT INTO atlas_users (user_id, identity_id, created_at) VALUES (?, ?, 'now')",
                (user_id, canonical_identity),
            )
            connection.commit()

            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO atlas_users (user_id, identity_id, created_at)
                    VALUES ('55555555-5555-4555-8555-555555555555', ?, 'now')
                    """,
                    (canonical_identity,),
                )


    def test_direct_sql_cannot_insert_user_without_identity(self):
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO atlas_users (user_id, identity_id, created_at)
                    VALUES (
                        'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
                        'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
                        'now'
                    )
                    """
                )

    def test_direct_sql_cannot_insert_user_identity_without_user_id(self):
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO identity_records (
                        identity_id, identity_kind, identity_status, revision,
                        created_at, updated_at
                    ) VALUES (
                        'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
                        'user', 'active', 1, 'now', 'now'
                    )
                    """
                )

    def test_direct_sql_cannot_commit_an_orphan_user_identity(self):
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO identity_records (
                        identity_id, identity_kind, identity_status, revision,
                        created_at, updated_at, user_id
                    ) VALUES (
                        '66666666-6666-4666-8666-666666666666',
                        'user', 'active', 1, 'now', 'now',
                        '77777777-7777-4777-8777-777777777777'
                    )
                    """
                )

    def test_direct_sql_cannot_commit_a_mismatched_user_identity_pair(self):
        with self.database.connection() as connection:
            connection.execute("BEGIN")
            connection.execute(
                """
                INSERT INTO identity_records (
                    identity_id, identity_kind, identity_status, revision,
                    created_at, updated_at, user_id
                ) VALUES (
                    '66666666-6666-4666-8666-666666666666',
                    'user', 'active', 1, 'now', 'now',
                    '77777777-7777-4777-8777-777777777777'
                )
                """
            )
            connection.execute(
                """
                INSERT INTO atlas_users (user_id, identity_id, created_at)
                VALUES (
                    '88888888-8888-4888-8888-888888888888',
                    '66666666-6666-4666-8666-666666666666',
                    'now'
                )
                """
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.commit()
            connection.rollback()

    def test_non_user_identity_cannot_carry_user_id(self):
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO identity_records (
                        identity_id, identity_kind, identity_status, revision,
                        created_at, updated_at, user_id
                    ) VALUES (
                        '99999999-9999-4999-8999-999999999999',
                        'agent', 'active', 1, 'now', 'now',
                        '77777777-7777-4777-8777-777777777777'
                    )
                    """
                )

    def test_sql_triggers_preserve_identity_immutability_revocation_and_tombstones(self):
        user = self.authority.create_user()
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE identity_records SET user_id = ? WHERE identity_id = ?",
                    ("88888888-8888-4888-8888-888888888888", user.identity.identity_id),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE atlas_users SET user_id = ? WHERE user_id = ?",
                    ("88888888-8888-4888-8888-888888888888", user.user_id),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT OR REPLACE INTO identity_records (
                        identity_id, identity_kind, identity_status, revision,
                        created_at, updated_at, user_id
                    ) VALUES (?, 'user', 'active', 1, 'now', 'now', ?)
                    """,
                    (user.identity.identity_id, user.user_id),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT OR REPLACE INTO atlas_users (user_id, identity_id, created_at)
                    VALUES (?, ?, 'now')
                    """,
                    (user.user_id, user.identity.identity_id),
                )
            connection.execute(
                """
                UPDATE identity_records
                SET identity_status = 'revoked', revision = revision + 1
                WHERE identity_id = ?
                """,
                (user.identity.identity_id,),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    UPDATE identity_records
                    SET identity_status = 'active', revision = revision + 1
                    WHERE identity_id = ?
                    """,
                    (user.identity.identity_id,),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM atlas_users WHERE user_id = ?", (user.user_id,))
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM identity_records WHERE identity_id = ?",
                    (user.identity.identity_id,),
                )

    def test_v6_migration_preserves_user_pair_and_all_non_user_identity_fields(self):
        legacy = SQLiteDatabase(Path(self.temp_dir.name) / "legacy-valid.sqlite")
        legacy.apply_migrations(SQLITE_MIGRATIONS[:-8])
        records = (
            ("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "user", "suspended", 3,
             "user-created", "user-updated"),
            ("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "agent", "active", 7,
             "agent-created", "agent-updated"),
            ("cccccccc-cccc-4ccc-8ccc-cccccccccccc", "service", "revoked", 9,
             "service-created", "service-updated"),
            ("dddddddd-dddd-4ddd-8ddd-dddddddddddd", "watcher", "suspended", 4,
             "watcher-created", "watcher-updated"),
            ("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee", "system", "active", 2,
             "system-created", "system-updated"),
        )
        user_id = "11111111-1111-4111-8111-111111111111"
        user_created_at = "user-row-created"
        with legacy.connection() as connection:
            connection.execute("BEGIN")
            connection.executemany(
                """
                INSERT INTO identity_records (
                    identity_id, identity_kind, identity_status, revision,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                records,
            )
            connection.execute(
                """
                INSERT INTO atlas_users (user_id, identity_id, created_at)
                VALUES (?, ?, ?)
                """,
                (user_id, records[0][0], user_created_at),
            )
            connection.commit()

        legacy.apply_migrations(SQLITE_MIGRATIONS)
        with legacy.connection() as connection:
            migrated = connection.execute(
                """
                SELECT identity_id, identity_kind, identity_status, revision,
                       created_at, updated_at, user_id
                FROM identity_records ORDER BY identity_kind
                """
            ).fetchall()
            user_row = connection.execute(
                "SELECT user_id, identity_id, created_at FROM atlas_users"
            ).fetchone()
            versions = connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
            violations = connection.execute("PRAGMA foreign_key_check").fetchall()
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]

        expected_by_kind = {
            kind: (identity_id, kind, status, revision, created_at, updated_at,
                   user_id if kind == "user" else None)
            for identity_id, kind, status, revision, created_at, updated_at in records
        }
        expected_identity_rows = {
            kind: values for kind, values in expected_by_kind.items()
        }
        expected_user_row = (user_id, records[0][0], user_created_at)
        self.assertEqual(
            {row["identity_kind"]: tuple(row) for row in migrated},
            expected_identity_rows,
        )
        self.assertEqual(tuple(user_row), expected_user_row)
        self.assertEqual([item[0] for item in versions], [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14])
        self.assertEqual(violations, [])
        self.assertEqual(integrity, "ok")

        # Reapplying the complete migration history must not mutate v6 data.
        legacy.apply_migrations(SQLITE_MIGRATIONS)
        with legacy.connection() as connection:
            rerun_identity_rows = {
                row["identity_kind"]: tuple(row)
                for row in connection.execute(
                    """
                    SELECT identity_id, identity_kind, identity_status, revision,
                           created_at, updated_at, user_id
                    FROM identity_records ORDER BY identity_kind
                    """
                )
            }
            rerun_user_row = tuple(connection.execute(
                "SELECT user_id, identity_id, created_at FROM atlas_users"
            ).fetchone())
            rerun_versions = [
                row[0] for row in connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                )
            ]
            rerun_violations = connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
            rerun_integrity = connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]

        self.assertEqual(rerun_identity_rows, expected_identity_rows)
        self.assertEqual(rerun_user_row, expected_user_row)
        self.assertEqual(rerun_versions, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13])
        self.assertEqual(rerun_violations, [])
        self.assertEqual(rerun_integrity, "ok")

    def test_v6_migration_rejects_legacy_orphan_atlas_user_atomically(self):
        database_path = Path(self.temp_dir.name) / "legacy-orphan-user.sqlite"
        legacy = SQLiteDatabase(database_path)
        legacy.apply_migrations(SQLITE_MIGRATIONS[:-8])

        user_id = "22222222-2222-4222-8222-222222222222"
        missing_identity_id = "33333333-3333-4333-8333-333333333333"

        # Simulate legacy corruption that normal v5 FK enforcement prevents.
        # Disable FK checks before the transaction and remove the v5 kind guard
        # so the intentionally dangling atlas_users row can be represented.
        raw = sqlite3.connect(database_path)
        try:
            raw.execute("PRAGMA foreign_keys = OFF")
            raw.execute("DROP TRIGGER atlas_users_require_user_identity")
            raw.execute(
                """
                INSERT INTO atlas_users (user_id, identity_id, created_at)
                VALUES (?, ?, 'orphan-user-created')
                """,
                (user_id, missing_identity_id),
            )
            raw.commit()
        finally:
            raw.close()

        with self.assertRaises(sqlite3.IntegrityError):
            legacy.apply_migrations(SQLITE_MIGRATIONS)

        with legacy.connection() as connection:
            versions = connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
            orphan = connection.execute(
                "SELECT user_id, identity_id, created_at FROM atlas_users"
            ).fetchone()
            columns = {
                item["name"]
                for item in connection.execute("PRAGMA table_info(identity_records)")
            }
            temporary_tables = {
                row["name"]
                for row in connection.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'table'
                      AND name IN ('identity_records_v6', 'atlas_users_v6')
                    """
                )
            }
            violations = connection.execute("PRAGMA foreign_key_check").fetchall()

        self.assertEqual([item[0] for item in versions], [1, 2, 3, 4, 5])
        self.assertEqual(
            tuple(orphan),
            (user_id, missing_identity_id, "orphan-user-created"),
        )
        self.assertNotIn("user_id", columns)
        self.assertEqual(temporary_tables, set())
        self.assertTrue(violations)
        self.assertEqual(violations[0][0], "atlas_users")

    def test_v6_migration_rebuilds_reciprocal_foreign_keys_after_table_renames(self):
        legacy = SQLiteDatabase(Path(self.temp_dir.name) / "legacy-fk-rename.sqlite")
        legacy.apply_migrations(SQLITE_MIGRATIONS[:-8])
        user_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        identity_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        with legacy.connection() as connection:
            connection.execute("BEGIN")
            connection.execute(
                """
                INSERT INTO identity_records (
                    identity_id, identity_kind, identity_status, revision,
                    created_at, updated_at
                ) VALUES (?, 'user', 'active', 1, 'created', 'updated')
                """,
                (identity_id,),
            )
            connection.execute(
                "INSERT INTO atlas_users (user_id, identity_id, created_at) VALUES (?, ?, 'created')",
                (user_id, identity_id),
            )
            connection.commit()

        legacy.apply_migrations(SQLITE_MIGRATIONS)
        with legacy.connection() as connection:
            identity_fks = connection.execute(
                "PRAGMA foreign_key_list(identity_records)"
            ).fetchall()
            user_fks = connection.execute(
                "PRAGMA foreign_key_list(atlas_users)"
            ).fetchall()
            violations = connection.execute("PRAGMA foreign_key_check").fetchall()

            self.assertEqual(
                {(row["table"], row["from"], row["to"]) for row in identity_fks},
                {("atlas_users", "user_id", "user_id")},
            )
            self.assertEqual(
                {(row["table"], row["from"], row["to"]) for row in user_fks},
                {
                    ("identity_records", "identity_id", "identity_id"),
                    ("identity_records", "user_id", "user_id"),
                },
            )
            self.assertEqual(violations, [])

            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO identity_records (
                        identity_id, identity_kind, identity_status, revision,
                        created_at, updated_at, user_id
                    ) VALUES (
                        'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
                        'user', 'active', 1, 'created', 'updated',
                        'dddddddd-dddd-4ddd-8ddd-dddddddddddd'
                    )
                    """
                )

    def test_v6_migration_rejects_legacy_orphan_user_identity_atomically(self):
        legacy = SQLiteDatabase(Path(self.temp_dir.name) / "legacy-orphan.sqlite")
        legacy.apply_migrations(SQLITE_MIGRATIONS[:-8])
        identity_id = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        with legacy.connection() as connection:
            connection.execute(
                """
                INSERT INTO identity_records (
                    identity_id, identity_kind, identity_status, revision,
                    created_at, updated_at
                ) VALUES (?, 'user', 'active', 1, 'legacy', 'legacy')
                """,
                (identity_id,),
            )

        with self.assertRaises(sqlite3.IntegrityError):
            legacy.apply_migrations(SQLITE_MIGRATIONS)
        with legacy.connection() as connection:
            versions = connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
            row = connection.execute(
                "SELECT identity_id FROM identity_records WHERE identity_id = ?",
                (identity_id,),
            ).fetchone()
            columns = {
                item["name"] for item in connection.execute("PRAGMA table_info(identity_records)")
            }
        self.assertEqual([item[0] for item in versions], [1, 2, 3, 4, 5])
        self.assertEqual(row["identity_id"], identity_id)
        self.assertNotIn("user_id", columns)

    def test_identity_revision_must_advance_exactly_one(self):
        user = self.authority.create_user()
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    UPDATE identity_records SET identity_status = 'suspended',
                        revision = 3 WHERE identity_id = ?
                    """,
                    (user.identity.identity_id,),
                )


    def test_create_user_joins_outer_unit_of_work_and_rolls_back(self):
        created = None
        with self.assertRaisesRegex(RuntimeError, "force outer rollback"):
            with self.database.unit_of_work() as unit:
                joined = SQLiteIdentityAuthority(
                    self.database,
                    unit_of_work=unit,
                )
                created = joined.create_user()
                raise RuntimeError("force outer rollback")
        self.assertIsNotNone(created)
        self.assertIsNone(self.authority.get_user(created.user_id))
        with self.database.connection() as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM identity_records"
            ).fetchone()[0], 0)

    def test_update_user_status_joins_outer_unit_of_work_and_rolls_back(self):
        user = self.authority.create_user()
        with self.assertRaisesRegex(RuntimeError, "force outer rollback"):
            with self.database.unit_of_work() as unit:
                joined = SQLiteIdentityAuthority(
                    self.database,
                    unit_of_work=unit,
                )
                joined.update_user_status(
                    user.user_id,
                    expected_revision=1,
                    status=IdentityStatus.SUSPENDED,
                )
                raise RuntimeError("force outer rollback")
        self.assertEqual(self.authority.get_user(user.user_id), user)

    def test_identity_authority_rejects_unit_of_work_from_another_database(self):
        other_database = SQLiteDatabase(
            Path(self.temp_dir.name) / "other.sqlite"
        )
        other_database.apply_migrations(SQLITE_MIGRATIONS)
        with other_database.unit_of_work() as unit:
            joined = SQLiteIdentityAuthority(
                self.database,
                unit_of_work=unit,
            )
            with self.assertRaises(ContractError):
                joined.create_user()


if __name__ == "__main__":
    unittest.main()
