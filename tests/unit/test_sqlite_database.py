"""Tests for the file-backed SQLite infrastructure foundation."""
from pathlib import Path
import sqlite3
import tempfile
import unittest

from atlas.core.errors import ContractError
from atlas.adapters.sqlite import SQLiteDatabase, SQLiteMigration


class SQLiteDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "atlas.sqlite3"
        self.database = SQLiteDatabase(self.database_path, busy_timeout_ms=1200)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_rejects_memory_and_relative_database_paths(self):
        with self.assertRaises(ContractError):
            SQLiteDatabase(":memory:")
        with self.assertRaises(ContractError):
            SQLiteDatabase("relative.sqlite3")

    def test_rejects_invalid_busy_timeout(self):
        with self.assertRaises(ContractError):
            SQLiteDatabase(self.database_path, busy_timeout_ms=True)
        with self.assertRaises(ContractError):
            SQLiteDatabase(self.database_path, busy_timeout_ms=-1)

    def test_initialize_enables_wal_and_creates_migration_ledger(self):
        self.database.initialize()
        with self.database.connection() as connection:
            mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
            synchronous = connection.execute("PRAGMA synchronous").fetchone()[0]
            busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
            ledger = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()
        self.assertEqual(mode.lower(), "wal")
        self.assertEqual(foreign_keys, 1)
        self.assertEqual(synchronous, 2)
        self.assertEqual(busy_timeout, 1200)
        self.assertIsNotNone(ledger)

    def test_write_transaction_commits(self):
        self.database.initialize()
        with self.database.write_transaction() as connection:
            connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
            connection.execute("INSERT INTO sample(value) VALUES ('durable')")
        with self.database.connection() as connection:
            row = connection.execute("SELECT value FROM sample").fetchone()
        self.assertEqual(row["value"], "durable")

    def test_write_transaction_rolls_back_on_error(self):
        self.database.initialize()
        with self.assertRaises(RuntimeError):
            with self.database.write_transaction() as connection:
                connection.execute("CREATE TABLE rolled_back (value TEXT)")
                raise RuntimeError("injected failure")
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='rolled_back'"
            ).fetchone()
        self.assertIsNone(row)


    def test_unit_of_work_commits_and_exposes_only_its_owned_connection(self):
        self.database.initialize()
        with self.database.unit_of_work() as unit:
            connection = unit._connection_for(self.database)
            self.assertTrue(connection.in_transaction)
            connection.execute("CREATE TABLE unit_commit (value TEXT NOT NULL)")
            connection.execute("INSERT INTO unit_commit(value) VALUES ('committed')")
        with self.database.connection() as connection:
            row = connection.execute("SELECT value FROM unit_commit").fetchone()
        self.assertEqual(row["value"], "committed")
        with self.assertRaises(ContractError):
            unit._connection_for(self.database)

    def test_unit_of_work_rolls_back_on_error(self):
        self.database.initialize()
        with self.assertRaises(RuntimeError):
            with self.database.unit_of_work() as unit:
                unit._connection_for(self.database).execute(
                    "CREATE TABLE unit_rollback (value TEXT)"
                )
                raise RuntimeError("injected unit-of-work failure")
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='unit_rollback'"
            ).fetchone()
        self.assertIsNone(row)

    def test_unit_of_work_rejects_another_database_owner(self):
        other_database = SQLiteDatabase(self.database_path, busy_timeout_ms=1200)
        with self.database.unit_of_work() as unit:
            with self.assertRaises(ContractError):
                unit._connection_for(other_database)

    def test_unit_of_work_rejects_nesting_on_same_thread(self):
        with self.database.unit_of_work() as outer:
            with self.assertRaises(ContractError):
                with self.database.unit_of_work():
                    self.fail("la unidad anidada no debe abrirse")
            self.assertTrue(outer._connection_for(self.database).in_transaction)

    def test_legacy_write_transaction_remains_compatible(self):
        self.database.initialize()
        with self.database.write_transaction() as connection:
            connection.execute("CREATE TABLE legacy_compat (value TEXT NOT NULL)")
            connection.execute("INSERT INTO legacy_compat(value) VALUES ('legacy')")
        with self.database.connection() as connection:
            row = connection.execute("SELECT value FROM legacy_compat").fetchone()
        self.assertEqual(row["value"], "legacy")

    def test_applies_ordered_migrations_and_is_idempotent(self):
        migrations = (
            SQLiteMigration(1, "initial", "CREATE TABLE first_table (id INTEGER PRIMARY KEY);"),
            SQLiteMigration(2, "second", "CREATE TABLE second_table (id INTEGER PRIMARY KEY);"),
        )
        self.assertEqual(self.database.apply_migrations(migrations), 2)
        self.assertEqual(self.database.apply_migrations(migrations), 2)
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT version, name FROM schema_migrations ORDER BY version"
            ).fetchall()
        self.assertEqual([(row["version"], row["name"]) for row in rows], [
            (1, "initial"), (2, "second")
        ])

    def test_rejects_changed_migration_checksum(self):
        original = (SQLiteMigration(1, "initial", "CREATE TABLE stable (id INTEGER);"),)
        changed = (SQLiteMigration(1, "initial", "CREATE TABLE changed (id INTEGER);"),)
        self.database.apply_migrations(original)
        with self.assertRaises(sqlite3.DatabaseError):
            self.database.apply_migrations(changed)

    def test_rejects_incomplete_migration_history(self):
        with self.assertRaises(ContractError):
            self.database.apply_migrations((
                SQLiteMigration(2, "second", "CREATE TABLE second_table (id INTEGER);"),
            ))

    def test_migration_failure_rolls_back_schema_and_ledger(self):
        migrations = (
            SQLiteMigration(1, "initial", "CREATE TABLE first_table (id INTEGER);"),
            SQLiteMigration(2, "broken", "CREATE TABLE broken_table (id INTEGER); INVALID SQL;"),
        )
        with self.assertRaises(sqlite3.Error):
            self.database.apply_migrations(migrations)
        with self.database.connection() as connection:
            first = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='first_table'"
            ).fetchone()
            rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
        self.assertIsNone(first)
        self.assertEqual(rows, [])

    def test_write_transaction_uses_immediate_lock(self):
        self.database.initialize()
        with self.database.write_transaction() as connection:
            mode = connection.execute("PRAGMA locking_mode").fetchone()[0]
            transaction_state = connection.in_transaction
            self.assertTrue(transaction_state)
            self.assertEqual(mode.lower(), "normal")


if __name__ == "__main__":
    unittest.main()
