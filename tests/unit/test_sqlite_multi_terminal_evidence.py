"""Durable atomic persistence tests for multi-authority terminal evidence."""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from atlas.adapters.sqlite import SQLITE_MIGRATIONS, SQLiteAuthorityChangeStore, SQLiteDatabase
from atlas.core.errors import ContractError
from atlas.memory.authority_changes import (
    AuthorityChangeStatus,
    AuthorityChangeTarget,
    AuthorityChangeTargetKind,
    AuthorityChangeTerminalEvidence,
    AuthorityChangeTerminalOutcome,
    AuthorityChangeTerminalTarget,
    MultiAuthorityChangeIntent,
)


NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


class SQLiteMultiTerminalEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "atlas.sqlite3"
        self.database = SQLiteDatabase(self.database_path)
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.store = SQLiteAuthorityChangeStore(self.database)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _prepare_reconciling(self, *, key="terminal-001"):
        intent = MultiAuthorityChangeIntent(
            idempotency_key=key,
            consumer_id="atlas-consumer",
            action="grant.renewal.approve",
            actor_identity_id="user-001",
            owner_id="user-001",
            project_id="project-001",
            environment_id="development",
            targets=(
                AuthorityChangeTarget(
                    AuthorityChangeTargetKind.GRANT, "grant-001", 4, 5
                ),
                AuthorityChangeTarget(
                    AuthorityChangeTargetKind.GRANT_RENEWAL,
                    "renewal-001", 2, 3,
                ),
            ),
            request_context_ref="request-001",
            requested_at=NOW,
        )
        reservation = self.store.reserve_multi_change(intent)
        self.assertTrue(self.store.acquire_multi_claims(reservation.operation_id))
        with self.database.connection() as connection:
            connection.execute(
                """
                UPDATE multi_authority_change_operations
                SET status = 'RECONCILING'
                WHERE operation_id = ?
                """,
                (reservation.operation_id,),
            )
        return reservation

    @staticmethod
    def _evidence(reservation, *, outcome=AuthorityChangeTerminalOutcome.COMPLETED,
                  evidence_id="receipt-001", evidence_ref="reconciliation://receipt-001"):
        completed = outcome is AuthorityChangeTerminalOutcome.COMPLETED
        targets = tuple(
            AuthorityChangeTerminalTarget(
                target.authority_kind,
                target.authority_id,
                target.expected_revision,
                target.proposed_revision,
                target.proposed_revision if completed else target.expected_revision,
            )
            for target in reservation.intent.targets
        )
        return AuthorityChangeTerminalEvidence(
            evidence_id=evidence_id,
            operation_id=reservation.operation_id,
            outcome=outcome,
            targets=targets,
            evidence_ref=evidence_ref,
            recorded_by="consistency-coordinator",
            recorded_at=NOW,
        )

    def test_completed_receipt_and_terminal_status_are_committed_atomically(self):
        reservation = self._prepare_reconciling()
        evidence = self._evidence(reservation)
        stored = self.store.record_multi_terminal_evidence(evidence)
        self.assertEqual(stored, evidence)
        recovered = self.store.get_multi_reservation(reservation.operation_id)
        self.assertEqual(recovered.status, AuthorityChangeStatus.COMPLETED)
        self.assertEqual(
            self.store.get_multi_terminal_evidence(reservation.operation_id),
            evidence,
        )
        self.assertEqual(
            self.store.get_multi_claims(reservation.operation_id),
            reservation.intent.targets,
        )

    def test_aborted_receipt_requires_all_original_revisions(self):
        reservation = self._prepare_reconciling()
        evidence = self._evidence(
            reservation, outcome=AuthorityChangeTerminalOutcome.ABORTED
        )
        self.store.record_multi_terminal_evidence(evidence)
        self.assertEqual(
            self.store.get_multi_reservation(reservation.operation_id).status,
            AuthorityChangeStatus.ABORTED,
        )

    def test_exact_retry_returns_original_receipt_after_restart(self):
        reservation = self._prepare_reconciling()
        evidence = self._evidence(reservation)
        self.store.record_multi_terminal_evidence(evidence)
        restarted = SQLiteAuthorityChangeStore(SQLiteDatabase(self.database_path))
        self.assertEqual(
            restarted.record_multi_terminal_evidence(evidence),
            evidence,
        )

    def test_different_receipt_for_same_operation_is_rejected(self):
        reservation = self._prepare_reconciling()
        original = self._evidence(reservation)
        self.store.record_multi_terminal_evidence(original)
        conflicting = self._evidence(
            reservation,
            evidence_id="receipt-002",
            evidence_ref="reconciliation://different",
        )
        with self.assertRaises(ContractError):
            self.store.record_multi_terminal_evidence(conflicting)
        self.assertEqual(
            self.store.get_multi_terminal_evidence(reservation.operation_id),
            original,
        )

    def test_unknown_operation_is_rejected(self):
        reservation = self._prepare_reconciling()
        evidence = self._evidence(reservation)
        unknown = AuthorityChangeTerminalEvidence(
            evidence_id=evidence.evidence_id,
            operation_id="unknown-operation",
            outcome=evidence.outcome,
            targets=evidence.targets,
            evidence_ref=evidence.evidence_ref,
            recorded_by=evidence.recorded_by,
            recorded_at=evidence.recorded_at,
        )
        with self.assertRaises(ContractError):
            self.store.record_multi_terminal_evidence(unknown)

    def test_operation_must_be_reconciling(self):
        reservation = self.store.reserve_multi_change(
            MultiAuthorityChangeIntent(
                idempotency_key="not-ready",
                consumer_id="atlas-consumer",
                action="grant.renewal.approve",
                actor_identity_id="user-001",
                owner_id="user-001",
                project_id="project-001",
                environment_id="development",
                targets=(
                    AuthorityChangeTarget(AuthorityChangeTargetKind.GRANT, "grant-001", 4, 5),
                    AuthorityChangeTarget(AuthorityChangeTargetKind.GRANT_RENEWAL, "renewal-001", 2, 3),
                ),
                request_context_ref="request-001",
                requested_at=NOW,
            )
        )
        evidence = self._evidence(reservation)
        with self.assertRaises(ContractError):
            self.store.record_multi_terminal_evidence(evidence)

    def test_complete_claim_set_is_required(self):
        reservation = self.store.reserve_multi_change(
            MultiAuthorityChangeIntent(
                idempotency_key="no-claims",
                consumer_id="atlas-consumer",
                action="grant.renewal.approve",
                actor_identity_id="user-001",
                owner_id="user-001",
                project_id="project-001",
                environment_id="development",
                targets=(
                    AuthorityChangeTarget(AuthorityChangeTargetKind.GRANT, "grant-001", 4, 5),
                    AuthorityChangeTarget(AuthorityChangeTargetKind.GRANT_RENEWAL, "renewal-001", 2, 3),
                ),
                request_context_ref="request-001",
                requested_at=NOW,
            )
        )
        with self.database.connection() as connection:
            connection.execute(
                "UPDATE multi_authority_change_operations SET status='RECONCILING' WHERE operation_id=?",
                (reservation.operation_id,),
            )
        with self.assertRaises(ContractError):
            self.store.record_multi_terminal_evidence(self._evidence(reservation))

    def test_failure_while_inserting_one_target_rolls_back_receipt_and_status(self):
        reservation = self._prepare_reconciling()
        evidence = self._evidence(reservation)
        with self.database.connection() as connection:
            connection.execute(
                """
                CREATE TRIGGER fail_terminal_target_insert
                BEFORE INSERT ON multi_authority_change_terminal_targets
                WHEN NEW.authority_id = 'renewal-001'
                BEGIN
                    SELECT RAISE(ABORT, 'simulated terminal target failure');
                END;
                """
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.record_multi_terminal_evidence(evidence)
        self.assertIsNone(
            self.store.get_multi_terminal_evidence(reservation.operation_id)
        )
        self.assertEqual(
            self.store.get_multi_reservation(reservation.operation_id).status,
            AuthorityChangeStatus.RECONCILING,
        )
        self.assertEqual(
            self.store.get_multi_claims(reservation.operation_id),
            reservation.intent.targets,
        )

    def test_recovery_detects_receipt_digest_or_canonical_payload_corruption(self):
        reservation = self._prepare_reconciling()
        evidence = self._evidence(reservation)
        self.store.record_multi_terminal_evidence(evidence)
        with self.database.connection() as connection:
            connection.execute(
                "DROP TRIGGER multi_terminal_evidence_no_update"
            )
            connection.execute(
                """
                UPDATE multi_authority_change_terminal_evidence
                SET evidence_canonical = ?
                WHERE operation_id = ?
                """,
                (b"tampered", reservation.operation_id),
            )
        with self.assertRaises(sqlite3.DatabaseError):
            self.store.get_multi_terminal_evidence(reservation.operation_id)

    def test_sql_rejects_terminal_status_without_receipt(self):
        reservation = self.store.reserve_multi_change(
            MultiAuthorityChangeIntent(
                idempotency_key="sql-no-receipt",
                consumer_id="atlas-consumer",
                action="grant.renewal.approve",
                actor_identity_id="user-001",
                owner_id="user-001",
                project_id="project-001",
                environment_id="development",
                targets=(
                    AuthorityChangeTarget(AuthorityChangeTargetKind.GRANT, "grant-001", 4, 5),
                    AuthorityChangeTarget(AuthorityChangeTargetKind.GRANT_RENEWAL, "renewal-001", 2, 3),
                ),
                request_context_ref="request-001",
                requested_at=NOW,
            )
        )
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE multi_authority_change_operations SET status='COMPLETED' WHERE operation_id=?",
                    (reservation.operation_id,),
                )

    def test_terminal_receipt_and_targets_are_immutable_and_status_is_final(self):
        reservation = self._prepare_reconciling()
        evidence = self._evidence(reservation)
        self.store.record_multi_terminal_evidence(evidence)
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE multi_authority_change_terminal_evidence SET evidence_ref='changed' WHERE operation_id=?",
                    (reservation.operation_id,),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM multi_authority_change_terminal_evidence WHERE operation_id=?",
                    (reservation.operation_id,),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE multi_authority_change_operations SET status='BLOCKED' WHERE operation_id=?",
                    (reservation.operation_id,),
                )


if __name__ == "__main__":
    unittest.main()
