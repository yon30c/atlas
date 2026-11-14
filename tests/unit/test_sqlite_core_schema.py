"""Integration tests for the initial SQLite consistency schema."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from atlas.adapters.sqlite import SQLiteDatabase, SQLITE_MIGRATIONS


class SQLiteCoreSchemaTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "atlas.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)

    def _insert_domain(self, domain_id="domain-a", profile="local"):
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO consistency_domains (
                    domain_id, authority_epoch, head_sequence, profile,
                    trust_policy_version, created_at, updated_at
                ) VALUES (?, 1, 0, ?, 'policy-v1', '2026-11-14T00:00:00+00:00',
                          '2026-11-14T00:00:00+00:00')
                """,
                (domain_id, profile),
            )

    def _insert_journal_entry(self, domain_id="domain-a", record_id="record-a",
                              operation_id="operation-a", sequence=1):
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO journal_entries (
                    domain_id, authority_epoch, sequence, record_id, operation_id,
                    record_kind, schema_version, transition_canonical,
                    envelope_version, reducer_version, object_commitment,
                    issuer_id, issuer_role, key_reference, trust_policy_version,
                    issued_at, authentication_evidence
                ) VALUES (?, 1, ?, ?, ?, 'read_admitted', 1, X'7B7D', 1, 'reducer-v1',
                          'commitment', 'issuer', 'service', 'key-v1', 'policy-v1',
                          '2026-11-14T00:00:00+00:00', 'mac')
                """,
                (domain_id, sequence, record_id, operation_id),
            )

    def test_migration_creates_core_tables_and_indexes(self):
        with self.database.connection() as connection:
            tables = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            indexes = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                )
            }
        self.assertTrue({
            "consistency_domains", "journal_entries", "journal_operations",
            "checkpoints", "checkpoint_projections", "schema_migrations",
        }.issubset(tables))
        self.assertIn("journal_operations_idempotency_unique", indexes)

    def test_domain_rejects_non_local_profile(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self._insert_domain(profile="anchored")

    def test_journal_position_and_record_identity_are_unique(self):
        self._insert_domain()
        self._insert_journal_entry()
        with self.assertRaises(sqlite3.IntegrityError):
            self._insert_journal_entry(record_id="record-b", operation_id="operation-b")
        with self.assertRaises(sqlite3.IntegrityError):
            self._insert_journal_entry(
                record_id="record-a", operation_id="operation-c", sequence=2
            )

    def test_operation_must_reference_exact_journal_commit(self):
        self._insert_domain()
        with self.assertRaises(sqlite3.IntegrityError):
            with self.database.connection() as connection:
                connection.execute(
                    """
                    INSERT INTO journal_operations (
                        domain_id, authority_epoch, operation_id, request_canonical,
                        request_digest, sequence, record_id, created_at
                    ) VALUES ('domain-a', 1, 'operation-a', X'7B7D', ?, 1, 'missing',
                              '2026-11-14T00:00:00+00:00')
                    """,
                    ("a" * 64,),
                )

    def test_idempotency_key_cannot_bind_two_operations(self):
        self._insert_domain()
        self._insert_journal_entry()
        self._insert_journal_entry(
            record_id="record-b", operation_id="operation-b", sequence=2
        )
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO journal_operations (
                    domain_id, authority_epoch, operation_id, idempotency_key,
                    request_canonical, request_digest, sequence, record_id, created_at
                ) VALUES ('domain-a', 1, 'operation-a', 'idem-1', X'7B7D', ?, 1,
                          'record-a', '2026-11-14T00:00:00+00:00')
                """,
                ("a" * 64,),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            with self.database.connection() as connection:
                connection.execute(
                    """
                    INSERT INTO journal_operations (
                        domain_id, authority_epoch, operation_id, idempotency_key,
                        request_canonical, request_digest, sequence, record_id, created_at
                    ) VALUES ('domain-a', 1, 'operation-b', 'idem-1', X'7B7D', ?, 2,
                              'record-b', '2026-11-14T00:00:00+00:00')
                    """,
                    ("b" * 64,),
                )

    def test_checkpoint_projection_requires_existing_checkpoint(self):
        self._insert_domain()
        with self.assertRaises(sqlite3.IntegrityError):
            with self.database.connection() as connection:
                connection.execute(
                    """
                    INSERT INTO checkpoint_projections (
                        checkpoint_id, schema_version, reducer_version,
                        trust_policy_version, state_commitment, integrity_commitment,
                        projection_canonical, verification_id, created_at
                    ) VALUES ('missing', 1, 'reducer-v1', 'policy-v1', 'state',
                              'integrity', X'7B7D', 'verification',
                              '2026-11-14T00:00:00+00:00')
                    """
                )

    def test_schema_does_not_create_memory_content_storage(self):
        with self.database.connection() as connection:
            tables = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        self.assertFalse({
            "memories", "memory_versions", "memory_content", "embeddings",
        }.intersection(tables))


if __name__ == "__main__":
    unittest.main()
