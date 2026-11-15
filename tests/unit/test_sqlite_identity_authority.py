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
                        created_at, updated_at
                    ) VALUES ('NOT-A-UUID', 'user', 'active', 1, 'now', 'now')
                    """
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO identity_records (
                        identity_id, identity_kind, identity_status, revision,
                        created_at, updated_at
                    ) VALUES (
                        '11111111-1111-1111-8111-111111111111',
                        'user', 'active', 1, 'now', 'now'
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

    def test_v6_migration_preserves_existing_user_pairs(self):
        legacy = SQLiteDatabase(Path(self.temp_dir.name) / "legacy-valid.sqlite")
        legacy.apply_migrations(SQLITE_MIGRATIONS[:-1])
        user_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        identity_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        with legacy.connection() as connection:
            connection.execute("BEGIN")
            connection.execute(
                """
                INSERT INTO identity_records (
                    identity_id, identity_kind, identity_status, revision,
                    created_at, updated_at
                ) VALUES (?, 'user', 'active', 1, 'legacy', 'legacy')
                """,
                (identity_id,),
            )
            connection.execute(
                "INSERT INTO atlas_users (user_id, identity_id, created_at) VALUES (?, ?, 'legacy')",
                (user_id, identity_id),
            )
            connection.commit()

        legacy.apply_migrations(SQLITE_MIGRATIONS)
        with legacy.connection() as connection:
            row = connection.execute(
                "SELECT user_id FROM identity_records WHERE identity_id = ?",
                (identity_id,),
            ).fetchone()
            versions = connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
            violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        self.assertEqual(row["user_id"], user_id)
        self.assertEqual([item[0] for item in versions], [1, 2, 3, 4, 5, 6])
        self.assertEqual(violations, [])

    def test_v6_migration_rejects_legacy_orphan_user_identity_atomically(self):
        legacy = SQLiteDatabase(Path(self.temp_dir.name) / "legacy-orphan.sqlite")
        legacy.apply_migrations(SQLITE_MIGRATIONS[:-1])
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


if __name__ == "__main__":
    unittest.main()
