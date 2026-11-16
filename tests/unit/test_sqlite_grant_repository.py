"""Contract tests for the canonical SQLite Grant repository."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.grant_repository import SQLiteGrantRepository
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.authorization.models import Grant, GrantResourceScope
from atlas.core.errors import ConcurrencyError, ContractError, NotFoundError


NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


class SQLiteGrantRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "atlas.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.repository = SQLiteGrantRepository(self.database)
        self.grant = Grant(
            grant_id="grant-001",
            owner_user_id="user-001",
            subject_identity_id="agent-001",
            project_id="atlas",
            environment="test",
            resource_scope=GrantResourceScope(
                "workspace", frozenset({"demo", "docs"})
            ),
            actions=frozenset({"read", "list"}),
            issued_at=NOW,
            expires_at=NOW + timedelta(days=7),
        )

    def test_repository_is_bound_to_exact_database_instance(self):
        self.assertIs(self.repository._database, self.database)

    def test_create_and_get_round_trip_exact_grant(self):
        self.repository.create(self.grant)
        self.assertEqual(self.repository.get("grant-001"), self.grant)

    def test_create_rejects_duplicate_grant_id(self):
        self.repository.create(self.grant)
        with self.assertRaises(ContractError):
            self.repository.create(self.grant)

    def test_get_rejects_blank_identifier(self):
        for value in ("", "  ", None):
            with self.subTest(value=value):
                with self.assertRaises(ContractError):
                    self.repository.get(value)

    def test_list_by_owner_is_scoped_and_stably_ordered(self):
        self.repository.create(self.grant)
        second = replace(self.grant, grant_id="grant-000")
        other = replace(
            self.grant,
            grant_id="grant-other",
            owner_user_id="user-002",
        )
        self.repository.create(second)
        self.repository.create(other)
        self.assertEqual(
            self.repository.list_by_owner("user-001"),
            (second, self.grant),
        )
        self.assertEqual(
            self.repository.list_by_owner("user-002"),
            (other,),
        )

    def test_update_requires_exact_next_revision(self):
        self.repository.create(self.grant)
        updated = replace(
            self.grant,
            expires_at=NOW + timedelta(days=14),
            revision=2,
        )
        self.repository.update(updated)
        self.assertEqual(self.repository.get("grant-001"), updated)

    def test_update_rejects_stale_revision_without_overwriting(self):
        self.repository.create(self.grant)
        first = replace(self.grant, revision=2, expires_at=NOW + timedelta(days=10))
        second = replace(self.grant, revision=2, expires_at=NOW + timedelta(days=20))
        self.repository.update(first)
        with self.assertRaises(ConcurrencyError):
            self.repository.update(second)
        self.assertEqual(self.repository.get("grant-001"), first)

    def test_update_of_missing_grant_raises_not_found(self):
        with self.assertRaises(NotFoundError):
            self.repository.update(replace(self.grant, revision=2))

    def test_database_constraints_reject_delete_and_revision_skips(self):
        self.repository.create(self.grant)
        with self.database.connection() as connection:
            with self.assertRaises(Exception):
                connection.execute(
                    "DELETE FROM authorization_grants WHERE grant_id = ?",
                    ("grant-001",),
                )
            with self.assertRaises(Exception):
                connection.execute(
                    """
                    UPDATE authorization_grants SET revision = 3
                    WHERE grant_id = ?
                    """,
                    ("grant-001",),
                )
        self.assertEqual(self.repository.get("grant-001"), self.grant)

    def test_reopen_database_preserves_grant(self):
        self.repository.create(self.grant)
        reopened = SQLiteDatabase(self.database.path)
        reopened.apply_migrations(SQLITE_MIGRATIONS)
        self.assertEqual(SQLiteGrantRepository(reopened).get("grant-001"), self.grant)


if __name__ == "__main__":
    unittest.main()
