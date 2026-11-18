"""Contract tests for the local authority SQLite composition root."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.local_authority_unit_of_work import (
    SQLiteLocalAuthorityUnitOfWorkFactory,
)
from atlas.adapters.sqlite.authority_storage_composition import (
    SQLiteLocalAuthorityStorageComposition,
    compose_sqlite_local_authority_storage,
    compose_sqlite_local_authority_storage_on_database,
)
from atlas.core.errors import ContractError


class SQLiteLocalAuthorityStorageCompositionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "authority.sqlite3"

    def test_path_composition_creates_one_binding_without_opening_or_migrating(self):
        with patch.object(
            SQLiteDatabase,
            "apply_migrations",
            side_effect=AssertionError("composition must not apply migrations"),
        ) as apply_migrations:
            composition = compose_sqlite_local_authority_storage(
                self.database_path,
                busy_timeout_ms=1700,
            )

        apply_migrations.assert_not_called()
        self.assertIsInstance(composition.database, SQLiteDatabase)
        self.assertIsInstance(
            composition.unit_of_work_factory,
            SQLiteLocalAuthorityUnitOfWorkFactory,
        )
        self.assertIs(composition.unit_of_work_factory._database, composition.database)
        self.assertEqual(composition.database.path, self.database_path)
        self.assertEqual(composition.database.busy_timeout_ms, 1700)
        self.assertFalse(self.database_path.exists())

    def test_existing_database_is_reused_without_substitution_or_migration(self):
        database = SQLiteDatabase(self.database_path)

        with patch.object(
            SQLiteDatabase,
            "apply_migrations",
            side_effect=AssertionError("composition must not apply migrations"),
        ) as apply_migrations:
            composition = compose_sqlite_local_authority_storage_on_database(database)

        apply_migrations.assert_not_called()
        self.assertIs(composition.database, database)
        self.assertIs(composition.unit_of_work_factory._database, database)

    def test_factory_opens_a_unit_of_work_owned_by_the_composed_database(self):
        database = SQLiteDatabase(self.database_path)
        composition = compose_sqlite_local_authority_storage_on_database(database)

        with composition.unit_of_work_factory() as unit:
            self.assertIs(unit._database, database)
            self.assertIs(unit._unit._owner, database)
            unit.commit()

        with database.connection() as connection:
            migration_ledger_exists = connection.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table' AND name = 'schema_migrations'
                """
            ).fetchone()
        self.assertIsNone(migration_ledger_exists)

    def test_rejects_non_database_input(self):
        with self.assertRaises(ContractError):
            compose_sqlite_local_authority_storage_on_database(self.database_path)

    def test_composition_rejects_a_factory_bound_to_another_database(self):
        first_database = SQLiteDatabase(self.database_path)
        second_database = SQLiteDatabase(
            Path(self.temp_dir.name) / "other-authority.sqlite3"
        )

        with self.assertRaises(ContractError):
            SQLiteLocalAuthorityStorageComposition(
                database=first_database,
                unit_of_work_factory=SQLiteLocalAuthorityUnitOfWorkFactory(
                    second_database
                ),
            )

    def test_composition_rejects_invalid_components(self):
        with self.assertRaises(ContractError):
            SQLiteLocalAuthorityStorageComposition(
                database=self.database_path,
                unit_of_work_factory=SQLiteLocalAuthorityUnitOfWorkFactory(
                    SQLiteDatabase(self.database_path)
                ),
            )
        with self.assertRaises(ContractError):
            SQLiteLocalAuthorityStorageComposition(
                database=SQLiteDatabase(self.database_path),
                unit_of_work_factory=object(),
            )


if __name__ == "__main__":
    unittest.main()
