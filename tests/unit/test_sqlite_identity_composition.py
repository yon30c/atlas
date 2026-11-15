"""Contract tests for the explicit SQLite identity composition root."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.identity_authority import SQLiteIdentityAuthority
from atlas.adapters.sqlite.identity_composition import (
    SQLiteIdentityComposition,
    compose_sqlite_identity,
)
from atlas.core.errors import ContractError


class SQLiteIdentityCompositionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "identity.sqlite"

    def test_composition_initializes_schema_and_shares_exact_database(self):
        composition = compose_sqlite_identity(self.database_path)

        self.assertIsInstance(composition.database, SQLiteDatabase)
        self.assertIsInstance(composition.authority, SQLiteIdentityAuthority)
        self.assertIs(composition.authority._database, composition.database)
        self.assertEqual(composition.database.path, self.database_path)

        with composition.database.connection() as connection:
            versions = connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
        self.assertEqual([row["version"] for row in versions], [1, 2, 3, 4, 5, 6])

    def test_composed_authority_can_create_and_read_canonical_user(self):
        composition = compose_sqlite_identity(self.database_path)

        user = composition.authority.create_user()

        self.assertEqual(composition.authority.get_user(user.user_id), user)

    def test_recomposition_is_idempotent_for_an_already_migrated_database(self):
        first = compose_sqlite_identity(self.database_path)
        second = compose_sqlite_identity(self.database_path)

        self.assertIsNot(first.database, second.database)
        self.assertIs(second.authority._database, second.database)
        with second.database.connection() as connection:
            count = connection.execute(
                "SELECT COUNT(*) AS count FROM schema_migrations"
            ).fetchone()["count"]
        self.assertEqual(count, 6)

        user = first.authority.create_user()
        self.assertEqual(second.authority.get_user(user.user_id), user)

    def test_composition_rejects_a_relative_database_path(self):
        with self.assertRaises(ContractError):
            compose_sqlite_identity(Path("relative") / "identity.sqlite")

    def test_composition_rejects_a_missing_parent_directory(self):
        missing_path = Path(self.temp_dir.name) / "missing" / "identity.sqlite"
        with self.assertRaises(ContractError):
            compose_sqlite_identity(missing_path)
        self.assertFalse(missing_path.parent.exists())

    def test_migration_failure_propagates_without_constructing_authority(self):
        with patch.object(
            SQLiteDatabase,
            "apply_migrations",
            side_effect=RuntimeError("migration failure"),
        ) as apply_migrations:
            with patch(
                "atlas.adapters.sqlite.identity_composition.SQLiteIdentityAuthority"
            ) as authority_factory:
                with self.assertRaisesRegex(RuntimeError, "migration failure"):
                    compose_sqlite_identity(self.database_path)

        apply_migrations.assert_called_once()
        authority_factory.assert_not_called()

    def test_composition_rejects_authority_bound_to_another_database(self):
        first_database = SQLiteDatabase(self.database_path)
        second_path = Path(self.temp_dir.name) / "other.sqlite"
        second_database = SQLiteDatabase(second_path)
        authority = SQLiteIdentityAuthority(second_database)

        with self.assertRaises(ContractError):
            SQLiteIdentityComposition(
                database=first_database,
                authority=authority,
            )


if __name__ == "__main__":
    unittest.main()
