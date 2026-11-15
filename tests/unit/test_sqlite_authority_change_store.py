"""Contract tests for durable generic authority-change reservation storage."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from atlas.adapters.sqlite import (
    SQLITE_MIGRATIONS,
    SQLiteAuthorityChangeStore,
    SQLiteDatabase,
)
from atlas.memory.authority_changes import (
    AuthorityChangeIntent,
    AuthorityChangeStatus,
)
from atlas.memory.consistency import AuthorityKind


NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


class SQLiteAuthorityChangeStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "atlas.sqlite3"
        self.database = SQLiteDatabase(self.database_path)
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.store = SQLiteAuthorityChangeStore(self.database)

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def intent(
        *,
        consumer_id="consumer-a",
        idempotency_key="revoke-001",
        authority_id="grant-001",
        requested_at=NOW,
    ):
        return AuthorityChangeIntent(
            idempotency_key=idempotency_key,
            consumer_id=consumer_id,
            authority_kind=AuthorityKind.GRANT,
            authority_id=authority_id,
            expected_revision=7,
            proposed_revision=8,
            change_kind="revoke",
            request_context_ref="request-001",
            requested_at=requested_at,
        )

    def test_reservation_is_durable_and_recovered_after_store_recreation(self):
        first = self.store.reserve_change(self.intent())
        self.assertIsNotNone(first)
        self.assertEqual(first.status, AuthorityChangeStatus.REQUESTED)

        restarted_store = SQLiteAuthorityChangeStore(
            SQLiteDatabase(self.database_path)
        )
        recovered = restarted_store.get_reservation(first.operation_id)
        self.assertEqual(recovered, first)

        result = restarted_store.get_result(first.operation_id)
        self.assertEqual(result.status, AuthorityChangeStatus.REQUESTED)
        self.assertIsNone(result.source_revision)
        self.assertIsNone(result.invalidation_id)

    def test_same_semantic_retry_reuses_operation_and_original_timestamp(self):
        first = self.store.reserve_change(self.intent())
        retry = self.store.reserve_change(
            self.intent(requested_at=NOW + timedelta(minutes=3))
        )
        self.assertEqual(retry.operation_id, first.operation_id)
        self.assertEqual(retry.intent.requested_at, NOW)

    def test_same_key_with_different_resource_is_rejected(self):
        first = self.store.reserve_change(self.intent())
        conflict = self.store.reserve_change(
            self.intent(authority_id="grant-002")
        )
        self.assertIsNone(conflict)
        self.assertEqual(
            self.store.get_reservation(first.operation_id).intent.authority_id,
            "grant-001",
        )

    def test_idempotency_namespace_isolated_by_consumer(self):
        first = self.store.reserve_change(self.intent(consumer_id="consumer-a"))
        second = self.store.reserve_change(self.intent(consumer_id="consumer-b"))
        self.assertNotEqual(first.operation_id, second.operation_id)

    def test_same_consumer_key_returns_durable_result(self):
        first = self.store.reserve_change(self.intent())
        result = self.store.get_by_idempotency_key("consumer-a", "revoke-001")
        self.assertEqual(result.operation_id, first.operation_id)
        self.assertEqual(result.status, AuthorityChangeStatus.REQUESTED)

    def test_unknown_operation_and_idempotency_key_return_none(self):
        self.assertIsNone(self.store.get_result("missing-operation"))
        self.assertIsNone(
            self.store.get_by_idempotency_key("consumer-a", "missing-key")
        )

    def test_schema_has_separate_control_plane_records(self):
        with self.database.connection() as connection:
            names = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        self.assertTrue({
            "authority_change_operations",
            "authority_change_idempotency",
            "authority_change_invalidations",
            "authority_change_affected_admissions",
            "authority_change_affected_routes",
            "authority_change_source_results",
            "authority_change_recovery_evidence",
        }.issubset(names))


if __name__ == "__main__":
    unittest.main()
