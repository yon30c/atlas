"""Contract tests for durable generic authority-change reservation storage."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import sqlite3
import unittest

from atlas.core.errors import ContractError
from atlas.adapters.sqlite import (
    SQLITE_MIGRATIONS,
    SQLiteAuthorityChangeStore,
    SQLiteDatabase,
)
from atlas.memory.authority_changes import (
    AuthorityChangeIntent,
    AuthorityChangeStatus,
    AuthorityChangeTarget,
    AuthorityChangeTargetKind,
    MultiAuthorityChangeIntent,
    MultiAuthorityRecoveryDisposition,
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




class SQLiteMultiAuthorityChangeStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.database_path = Path(cls.temp_dir.name) / "multi-authority.sqlite3"
        cls.database = SQLiteDatabase(cls.database_path)
        cls.database.apply_migrations(SQLITE_MIGRATIONS)
        cls.store = SQLiteAuthorityChangeStore(cls.database)

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def setUp(self):
        # Each test gets an isolated database and store.
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "atlas.sqlite3"
        self.database = SQLiteDatabase(self.database_path)
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.store = SQLiteAuthorityChangeStore(self.database)

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def intent(*, consumer_id="atlas-consumer", key="renewal-001",
               requested_at=NOW, reverse=False):
        grant = AuthorityChangeTarget(
            AuthorityChangeTargetKind.GRANT, "grant-001", 4, 5
        )
        renewal = AuthorityChangeTarget(
            AuthorityChangeTargetKind.GRANT_RENEWAL, "renewal-001", 2, 3
        )
        targets = (renewal, grant) if reverse else (grant, renewal)
        return MultiAuthorityChangeIntent(
            idempotency_key=key,
            consumer_id=consumer_id,
            action="grant.renewal.approve",
            actor_identity_id="user-001",
            owner_id="user-001",
            project_id="project-001",
            environment_id="development",
            targets=targets,
            request_context_ref="request-001",
            requested_at=requested_at,
        )

    def _operation_at(self, status, key):
        base = self.intent(key=key)
        unique_intent = MultiAuthorityChangeIntent(
            idempotency_key=base.idempotency_key,
            consumer_id=base.consumer_id,
            action=base.action,
            actor_identity_id=base.actor_identity_id,
            owner_id=base.owner_id,
            project_id=base.project_id,
            environment_id=base.environment_id,
            targets=(
                AuthorityChangeTarget(
                    AuthorityChangeTargetKind.GRANT,
                    f"grant-{key}",
                    4,
                    5,
                ),
                AuthorityChangeTarget(
                    AuthorityChangeTargetKind.GRANT_RENEWAL,
                    f"renewal-{key}",
                    2,
                    3,
                ),
            ),
            request_context_ref=base.request_context_ref,
            requested_at=base.requested_at,
        )
        reservation = self.store.reserve_multi_change(unique_intent)
        self.assertTrue(self.store.acquire_multi_claims(reservation.operation_id))
        stages = (
            (AuthorityChangeStatus.REQUESTED, AuthorityChangeStatus.INVALIDATION_PENDING),
            (AuthorityChangeStatus.INVALIDATION_PENDING, AuthorityChangeStatus.SOURCE_PENDING),
            (AuthorityChangeStatus.SOURCE_PENDING, AuthorityChangeStatus.SOURCE_CONFIRMED),
            (AuthorityChangeStatus.SOURCE_CONFIRMED, AuthorityChangeStatus.RECONCILING),
        )
        for expected, target in stages:
            if target.value == status.value:
                self.assertTrue(self.store.transition_multi_status(
                    reservation.operation_id, expected, target
                ))
                break
            if expected.value == status.value:
                break
            self.assertTrue(self.store.transition_multi_status(
                reservation.operation_id, expected, target
            ))
        return reservation

    def test_multi_reservation_persists_complete_target_set(self):
        first = self.store.reserve_multi_change(self.intent())
        self.assertIsNotNone(first)
        self.assertEqual(first.status, AuthorityChangeStatus.REQUESTED)
        self.assertEqual(
            {target.authority_id for target in first.intent.targets},
            {"grant-001", "renewal-001"},
        )

    def test_multi_reservation_survives_store_recreation(self):
        first = self.store.reserve_multi_change(self.intent())
        restarted = SQLiteAuthorityChangeStore(SQLiteDatabase(self.database_path))
        self.assertEqual(
            restarted.get_multi_reservation(first.operation_id), first
        )

    def test_multi_exact_replay_uses_same_operation_and_original_timestamp(self):
        first = self.store.reserve_multi_change(self.intent())
        replay = self.store.reserve_multi_change(
            self.intent(
                requested_at=NOW + timedelta(minutes=2),
                reverse=True,
            )
        )
        self.assertEqual(replay.operation_id, first.operation_id)
        self.assertEqual(replay.intent.requested_at, NOW)

    def test_multi_same_key_with_changed_target_is_rejected(self):
        first = self.store.reserve_multi_change(self.intent())
        changed = MultiAuthorityChangeIntent(
            idempotency_key="renewal-001",
            consumer_id="atlas-consumer",
            action="grant.renewal.approve",
            actor_identity_id="user-001",
            owner_id="user-001",
            project_id="project-001",
            environment_id="development",
            targets=(
                AuthorityChangeTarget(AuthorityChangeTargetKind.GRANT, "grant-002", 4, 5),
                AuthorityChangeTarget(AuthorityChangeTargetKind.GRANT_RENEWAL, "renewal-001", 2, 3),
            ),
            request_context_ref="request-001",
            requested_at=NOW,
        )
        self.assertIsNone(self.store.reserve_multi_change(changed))
        self.assertEqual(
            self.store.get_multi_reservation(first.operation_id).intent.targets,
            first.intent.targets,
        )

    def test_multi_idempotency_is_namespaced_by_consumer(self):
        first = self.store.reserve_multi_change(self.intent(consumer_id="consumer-a"))
        second = self.store.reserve_multi_change(self.intent(consumer_id="consumer-b"))
        self.assertNotEqual(first.operation_id, second.operation_id)

    def test_multi_lookup_by_idempotency_key_returns_full_reservation(self):
        first = self.store.reserve_multi_change(self.intent())
        self.assertEqual(
            self.store.get_multi_by_idempotency_key("atlas-consumer", "renewal-001"),
            first,
        )

    def test_multi_unknown_lookups_return_none(self):
        self.assertIsNone(self.store.get_multi_reservation("missing"))
        self.assertIsNone(
            self.store.get_multi_by_idempotency_key("atlas-consumer", "missing")
        )

    def test_multi_target_rows_cannot_be_updated_or_deleted(self):
        first = self.store.reserve_multi_change(self.intent())
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """UPDATE multi_authority_change_targets
                       SET expected_revision = 8 WHERE operation_id = ?""",
                    (first.operation_id,),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM multi_authority_change_targets WHERE operation_id = ?",
                    (first.operation_id,),
                )

    def test_multi_target_set_cannot_be_extended_after_reservation(self):
        first = self.store.reserve_multi_change(self.intent())
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """INSERT INTO multi_authority_change_targets
                       (operation_id, authority_kind, authority_id,
                        expected_revision, proposed_revision)
                       VALUES (?, 'grant', 'late-grant', 1, 2)""",
                    (first.operation_id,),
                )

    def test_multi_reservation_rolls_back_operation_and_all_targets_on_partial_failure(self):
        with self.database.connection() as connection:
            connection.execute(
                """
                CREATE TRIGGER fail_second_multi_target
                BEFORE INSERT ON multi_authority_change_targets
                WHEN NEW.authority_id = 'renewal-001'
                BEGIN
                    SELECT RAISE(ABORT, 'simulated target insert failure');
                END;
                """
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.reserve_multi_change(self.intent())
        with self.database.connection() as connection:
            operation_count = connection.execute(
                "SELECT COUNT(*) FROM multi_authority_change_operations"
            ).fetchone()[0]
            target_count = connection.execute(
                "SELECT COUNT(*) FROM multi_authority_change_targets"
            ).fetchone()[0]
            idempotency_count = connection.execute(
                "SELECT COUNT(*) FROM multi_authority_change_idempotency"
            ).fetchone()[0]
        self.assertEqual(operation_count, 0)
        self.assertEqual(target_count, 0)
        self.assertEqual(idempotency_count, 0)

    def test_multi_idempotency_binding_cannot_be_updated_or_deleted(self):
        first = self.store.reserve_multi_change(self.intent())
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """UPDATE multi_authority_change_idempotency
                       SET intent_digest = ? WHERE operation_id = ?""",
                    ("0" * 64, first.operation_id),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM multi_authority_change_idempotency WHERE operation_id = ?",
                    (first.operation_id,),
                )


    def test_multi_claims_acquire_complete_target_set_and_exact_retry(self):
        reservation = self.store.reserve_multi_change(self.intent())
        self.assertTrue(self.store.acquire_multi_claims(reservation.operation_id))
        self.assertEqual(
            self.store.get_multi_claims(reservation.operation_id),
            reservation.intent.targets,
        )
        self.assertTrue(self.store.acquire_multi_claims(reservation.operation_id))

    def test_multi_claim_conflict_does_not_acquire_any_part_of_second_set(self):
        first = self.store.reserve_multi_change(self.intent(key="claim-first"))
        second_intent = MultiAuthorityChangeIntent(
            idempotency_key="claim-second",
            consumer_id="atlas-consumer",
            action="grant.renewal.approve",
            actor_identity_id="user-001",
            owner_id="user-001",
            project_id="project-001",
            environment_id="development",
            targets=(
                AuthorityChangeTarget(AuthorityChangeTargetKind.GRANT, "grant-001", 4, 5),
                AuthorityChangeTarget(AuthorityChangeTargetKind.GRANT_RENEWAL, "renewal-002", 2, 3),
            ),
            request_context_ref="request-002",
            requested_at=NOW,
        )
        second = self.store.reserve_multi_change(second_intent)
        self.assertTrue(self.store.acquire_multi_claims(first.operation_id))
        self.assertFalse(self.store.acquire_multi_claims(second.operation_id))
        self.assertEqual(
            self.store.get_multi_claims(first.operation_id),
            first.intent.targets,
        )
        self.assertEqual(self.store.get_multi_claims(second.operation_id), ())

    def test_multi_claims_are_exclusive_under_competing_connections(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        first = self.store.reserve_multi_change(self.intent(key="race-first"))
        second_intent = MultiAuthorityChangeIntent(
            idempotency_key="race-second",
            consumer_id="atlas-consumer",
            action="grant.renewal.approve",
            actor_identity_id="user-001",
            owner_id="user-001",
            project_id="project-001",
            environment_id="development",
            targets=(
                AuthorityChangeTarget(AuthorityChangeTargetKind.GRANT, "grant-001", 4, 5),
                AuthorityChangeTarget(AuthorityChangeTargetKind.GRANT_RENEWAL, "renewal-003", 2, 3),
            ),
            request_context_ref="request-003",
            requested_at=NOW,
        )
        second = self.store.reserve_multi_change(second_intent)
        barrier = Barrier(2)

        def acquire(operation_id):
            barrier.wait(timeout=5)
            return self.store.acquire_multi_claims(operation_id)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                acquire, (first.operation_id, second.operation_id)
            ))
        self.assertEqual(sum(results), 1)
        self.assertEqual(
            sum(bool(self.store.get_multi_claims(item.operation_id))
                for item in (first, second)),
            1,
        )

    def test_multi_claims_cannot_be_updated_or_deleted(self):
        reservation = self.store.reserve_multi_change(self.intent())
        self.assertTrue(self.store.acquire_multi_claims(reservation.operation_id))
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """UPDATE multi_authority_change_claims
                       SET acquired_at = 'changed' WHERE operation_id = ?""",
                    (reservation.operation_id,),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM multi_authority_change_claims WHERE operation_id = ?",
                    (reservation.operation_id,),
                )

    def test_multi_claims_require_a_matching_requested_target(self):
        reservation = self.store.reserve_multi_change(self.intent())
        with self.assertRaises(sqlite3.IntegrityError):
            with self.database.connection() as connection:
                connection.execute(
                    """
                    INSERT INTO multi_authority_change_claims (
                        authority_kind, authority_id, operation_id, acquired_at
                    ) VALUES ('grant', 'not-a-target', ?, '2026-11-16T00:00:00+00:00')
                    """,
                    (reservation.operation_id,),
                )


    def test_multi_status_advances_only_through_ordered_lifecycle(self):
        reservation = self.store.reserve_multi_change(self.intent(key="lifecycle-forward"))
        self.assertFalse(self.store.transition_multi_status(
            reservation.operation_id,
            AuthorityChangeStatus.REQUESTED,
            AuthorityChangeStatus.INVALIDATION_PENDING,
        ))
        self.assertTrue(self.store.acquire_multi_claims(reservation.operation_id))

        stages = (
            (AuthorityChangeStatus.REQUESTED, AuthorityChangeStatus.INVALIDATION_PENDING),
            (AuthorityChangeStatus.INVALIDATION_PENDING, AuthorityChangeStatus.SOURCE_PENDING),
            (AuthorityChangeStatus.SOURCE_PENDING, AuthorityChangeStatus.SOURCE_CONFIRMED),
            (AuthorityChangeStatus.SOURCE_CONFIRMED, AuthorityChangeStatus.RECONCILING),
        )
        for expected, target in stages:
            self.assertTrue(self.store.transition_multi_status(
                reservation.operation_id, expected, target
            ))
            self.assertFalse(self.store.transition_multi_status(
                reservation.operation_id, expected, target
            ))
            self.assertEqual(
                self.store.get_multi_reservation(reservation.operation_id).status,
                target,
            )

    def test_multi_status_compare_and_set_rejects_stale_or_unknown_operation(self):
        reservation = self.store.reserve_multi_change(self.intent(key="lifecycle-cas"))
        self.assertFalse(self.store.transition_multi_status(
            "missing-operation",
            AuthorityChangeStatus.REQUESTED,
            AuthorityChangeStatus.INVALIDATION_PENDING,
        ))
        self.assertTrue(self.store.acquire_multi_claims(reservation.operation_id))
        self.assertTrue(self.store.transition_multi_status(
            reservation.operation_id,
            AuthorityChangeStatus.REQUESTED,
            AuthorityChangeStatus.INVALIDATION_PENDING,
        ))
        self.assertFalse(self.store.transition_multi_status(
            reservation.operation_id,
            AuthorityChangeStatus.REQUESTED,
            AuthorityChangeStatus.INVALIDATION_PENDING,
        ))

    def test_multi_status_rejects_skipped_reverse_and_terminal_transitions(self):
        reservation = self.store.reserve_multi_change(self.intent(key="lifecycle-invalid"))
        invalid = (
            (AuthorityChangeStatus.REQUESTED, AuthorityChangeStatus.SOURCE_PENDING),
            (AuthorityChangeStatus.SOURCE_PENDING, AuthorityChangeStatus.INVALIDATION_PENDING),
            (AuthorityChangeStatus.RECONCILING, AuthorityChangeStatus.COMPLETED),
            (AuthorityChangeStatus.REQUESTED, AuthorityChangeStatus.ABORTED),
        )
        for expected, target in invalid:
            with self.assertRaises(ContractError):
                self.store.transition_multi_status(
                    reservation.operation_id, expected, target
                )

    def test_sqlite_trigger_rejects_status_skips_even_without_store_api(self):
        reservation = self.store.reserve_multi_change(self.intent(key="lifecycle-sql-guard"))
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    UPDATE multi_authority_change_operations
                    SET status = 'SOURCE_PENDING'
                    WHERE operation_id = ?
                    """,
                    (reservation.operation_id,),
                )

    def test_sqlite_trigger_requires_complete_claims_for_progression(self):
        reservation = self.store.reserve_multi_change(self.intent(key="lifecycle-no-claims"))
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    UPDATE multi_authority_change_operations
                    SET status = 'INVALIDATION_PENDING'
                    WHERE operation_id = ?
                    """,
                    (reservation.operation_id,),
                )


    def test_recovery_assessment_classifies_unclaimed_request_as_not_started(self):
        reservation = self.store.reserve_multi_change(self.intent(key="recovery-new"))
        assessment = self.store.assess_multi_recovery(reservation.operation_id)
        self.assertEqual(
            assessment.disposition,
            MultiAuthorityRecoveryDisposition.NOT_STARTED,
        )
        self.assertEqual(
            assessment.claim_audit.operation_status,
            AuthorityChangeStatus.REQUESTED,
        )
        self.assertEqual(self.store.get_multi_claims(reservation.operation_id), ())

    def test_recovery_assessment_marks_invalidation_as_outcome_unknown(self):
        reservation = self._operation_at(
            AuthorityChangeStatus.INVALIDATION_PENDING, "recovery-invalidation"
        )
        assessment = self.store.assess_multi_recovery(reservation.operation_id)
        self.assertEqual(
            assessment.disposition,
            MultiAuthorityRecoveryDisposition.INVALIDATION_OUTCOME_UNKNOWN,
        )

    def test_recovery_assessment_never_assumes_source_pending_was_not_applied(self):
        reservation = self._operation_at(
            AuthorityChangeStatus.SOURCE_PENDING, "recovery-source-pending"
        )
        assessment = self.store.assess_multi_recovery(reservation.operation_id)
        self.assertEqual(
            assessment.disposition,
            MultiAuthorityRecoveryDisposition.SOURCE_OUTCOME_UNKNOWN,
        )
        self.assertEqual(
            len(assessment.claim_audit.claimed_targets),
            len(reservation.intent.targets),
        )

    def test_recovery_assessment_distinguishes_confirmed_source_and_reconciling(self):
        confirmed = self._operation_at(
            AuthorityChangeStatus.SOURCE_CONFIRMED, "recovery-confirmed"
        )
        reconciling = self._operation_at(
            AuthorityChangeStatus.RECONCILING, "recovery-reconciling"
        )
        self.assertEqual(
            self.store.assess_multi_recovery(confirmed.operation_id).disposition,
            MultiAuthorityRecoveryDisposition.SOURCE_CONFIRMATION_RECORDED,
        )
        self.assertEqual(
            self.store.assess_multi_recovery(reconciling.operation_id).disposition,
            MultiAuthorityRecoveryDisposition.RECONCILIATION_IN_PROGRESS,
        )

    def test_recovery_assessment_unknown_operation_returns_none(self):
        self.assertIsNone(self.store.assess_multi_recovery("missing-operation"))

    def test_recovery_assessment_is_read_only(self):
        reservation = self._operation_at(
            AuthorityChangeStatus.SOURCE_PENDING, "recovery-read-only"
        )
        before = self.store.get_multi_reservation(reservation.operation_id)
        claims_before = self.store.get_multi_claims(reservation.operation_id)
        self.store.assess_multi_recovery(reservation.operation_id)
        after = self.store.get_multi_reservation(reservation.operation_id)
        self.assertEqual(after, before)
        self.assertEqual(
            self.store.get_multi_claims(reservation.operation_id),
            claims_before,
        )




if __name__ == "__main__":
    unittest.main()
