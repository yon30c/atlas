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
    MultiAuthorityClaimAuditStatus,
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
        transitions = (
            (AuthorityChangeStatus.REQUESTED, AuthorityChangeStatus.INVALIDATION_PENDING),
            (AuthorityChangeStatus.INVALIDATION_PENDING, AuthorityChangeStatus.SOURCE_PENDING),
            (AuthorityChangeStatus.SOURCE_PENDING, AuthorityChangeStatus.SOURCE_CONFIRMED),
            (AuthorityChangeStatus.SOURCE_CONFIRMED, AuthorityChangeStatus.RECONCILING),
        )
        for expected, new in transitions:
            self.assertTrue(
                self.store.transition_multi_status(
                    reservation.operation_id, expected, new
                )
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
        self.assertFalse(
            self.store.transition_multi_status(
                reservation.operation_id,
                AuthorityChangeStatus.REQUESTED,
                AuthorityChangeStatus.INVALIDATION_PENDING,
            )
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


    def test_completed_operation_releases_all_claims_with_durable_receipt(self):
        reservation = self._prepare_reconciling(key="release-completed")
        self.store.record_multi_terminal_evidence(self._evidence(reservation))
        self.assertTrue(self.store.release_multi_claims(reservation.operation_id))
        self.assertEqual(self.store.get_multi_claims(reservation.operation_id), ())
        with self.database.connection() as connection:
            release = connection.execute(
                """
                SELECT evidence_digest FROM multi_authority_change_claim_releases
                WHERE operation_id = ?
                """,
                (reservation.operation_id,),
            ).fetchone()
            terminal = connection.execute(
                """
                SELECT evidence_digest FROM multi_authority_change_terminal_evidence
                WHERE operation_id = ?
                """,
                (reservation.operation_id,),
            ).fetchone()
        self.assertIsNotNone(release)
        self.assertEqual(release["evidence_digest"], terminal["evidence_digest"])

    def test_aborted_operation_can_release_only_after_terminal_receipt(self):
        reservation = self._prepare_reconciling(key="release-aborted")
        self.store.record_multi_terminal_evidence(
            self._evidence(
                reservation, outcome=AuthorityChangeTerminalOutcome.ABORTED
            )
        )
        self.assertTrue(self.store.release_multi_claims(reservation.operation_id))
        self.assertEqual(self.store.get_multi_claims(reservation.operation_id), ())

    def test_nonterminal_operation_cannot_release_claims(self):
        reservation = self.store.reserve_multi_change(
            MultiAuthorityChangeIntent(
                idempotency_key="release-not-terminal",
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
        self.assertTrue(self.store.acquire_multi_claims(reservation.operation_id))
        self.assertFalse(self.store.release_multi_claims(reservation.operation_id))
        self.assertEqual(
            self.store.get_multi_claims(reservation.operation_id),
            reservation.intent.targets,
        )

    def test_release_is_idempotent_after_store_restart(self):
        reservation = self._prepare_reconciling(key="release-retry")
        self.store.record_multi_terminal_evidence(self._evidence(reservation))
        self.assertTrue(self.store.release_multi_claims(reservation.operation_id))
        restarted = SQLiteAuthorityChangeStore(SQLiteDatabase(self.database_path))
        self.assertTrue(restarted.release_multi_claims(reservation.operation_id))
        self.assertEqual(restarted.get_multi_claims(reservation.operation_id), ())

    def test_release_fails_closed_when_claim_set_is_incomplete(self):
        reservation = self._prepare_reconciling(key="release-incomplete")
        self.store.record_multi_terminal_evidence(self._evidence(reservation))
        with self.database.connection() as connection:
            connection.execute("DROP TRIGGER multi_authority_change_claims_no_delete")
            connection.execute(
                """
                DELETE FROM multi_authority_change_claims
                WHERE operation_id = ? AND authority_kind = 'grant_renewal'
                """,
                (reservation.operation_id,),
            )
        with self.assertRaises(sqlite3.DatabaseError):
            self.store.release_multi_claims(reservation.operation_id)
        with self.database.connection() as connection:
            release = connection.execute(
                "SELECT 1 FROM multi_authority_change_claim_releases WHERE operation_id = ?",
                (reservation.operation_id,),
            ).fetchone()
        self.assertIsNone(release)

    def test_claim_delete_requires_release_receipt_and_release_receipt_is_immutable(self):
        reservation = self._prepare_reconciling(key="release-sql-guard")
        self.store.record_multi_terminal_evidence(self._evidence(reservation))
        with self.assertRaises(sqlite3.IntegrityError):
            with self.database.connection() as connection:
                connection.execute(
                    "DELETE FROM multi_authority_change_claims WHERE operation_id = ?",
                    (reservation.operation_id,),
                )
        self.assertTrue(self.store.release_multi_claims(reservation.operation_id))
        with self.assertRaises(sqlite3.IntegrityError):
            with self.database.connection() as connection:
                connection.execute(
                    "UPDATE multi_authority_change_claim_releases SET released_at = 'tampered' WHERE operation_id = ?",
                    (reservation.operation_id,),
                )
        with self.assertRaises(sqlite3.IntegrityError):
            with self.database.connection() as connection:
                connection.execute(
                    "DELETE FROM multi_authority_change_claim_releases WHERE operation_id = ?",
                    (reservation.operation_id,),
                )

    def test_released_resource_can_be_claimed_by_a_new_operation(self):
        first = self._prepare_reconciling(key="release-reuse-first")
        self.store.record_multi_terminal_evidence(self._evidence(first))
        self.assertTrue(self.store.release_multi_claims(first.operation_id))
        second_intent = MultiAuthorityChangeIntent(
            idempotency_key="release-reuse-second",
            consumer_id="atlas-consumer",
            action="grant.renewal.approve",
            actor_identity_id="user-001",
            owner_id="user-001",
            project_id="project-001",
            environment_id="development",
            targets=(
                AuthorityChangeTarget(AuthorityChangeTargetKind.GRANT, "grant-001", 5, 6),
                AuthorityChangeTarget(AuthorityChangeTargetKind.GRANT_RENEWAL, "renewal-002", 1, 2),
            ),
            request_context_ref="request-002",
            requested_at=NOW,
        )
        second = self.store.reserve_multi_change(second_intent)
        self.assertTrue(self.store.acquire_multi_claims(second.operation_id))
        self.assertEqual(
            self.store.get_multi_claims(second.operation_id),
            second_intent.targets,
        )


    def test_claim_audit_classifies_unclaimed_operation(self):
        reservation = self.store.reserve_multi_change(
            MultiAuthorityChangeIntent(
                idempotency_key="audit-unclaimed",
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
                request_context_ref="request-audit",
                requested_at=NOW,
            )
        )
        audit = self.store.audit_multi_claims(reservation.operation_id)
        self.assertEqual(audit.audit_status, MultiAuthorityClaimAuditStatus.UNCLAIMED)
        self.assertEqual(audit.reserved_targets, reservation.intent.targets)
        self.assertEqual(audit.claimed_targets, ())

    def test_claim_audit_classifies_active_claims(self):
        reservation = self._prepare_reconciling(key="audit-claimed")
        audit = self.store.audit_multi_claims(reservation.operation_id)
        self.assertEqual(audit.audit_status, MultiAuthorityClaimAuditStatus.CLAIMED)
        self.assertEqual(audit.claimed_targets, reservation.intent.targets)

    def test_claim_audit_classifies_terminal_claims_held(self):
        reservation = self._prepare_reconciling(key="audit-terminal-held")
        evidence = self._evidence(reservation)
        self.store.record_multi_terminal_evidence(evidence)
        audit = self.store.audit_multi_claims(reservation.operation_id)
        self.assertEqual(
            audit.audit_status,
            MultiAuthorityClaimAuditStatus.TERMINAL_CLAIMS_HELD,
        )
        self.assertEqual(audit.terminal_evidence, evidence)
        self.assertEqual(audit.claimed_targets, reservation.intent.targets)

    def test_claim_audit_classifies_released_operation_after_restart(self):
        reservation = self._prepare_reconciling(key="audit-released")
        self.store.record_multi_terminal_evidence(self._evidence(reservation))
        self.store.release_multi_claims(reservation.operation_id)
        restarted = SQLiteAuthorityChangeStore(SQLiteDatabase(self.database_path))
        audit = restarted.audit_multi_claims(reservation.operation_id)
        self.assertEqual(audit.audit_status, MultiAuthorityClaimAuditStatus.RELEASED)
        self.assertEqual(audit.claimed_targets, ())
        self.assertEqual(len(audit.release_digest), 64)

    def test_claim_audit_detects_partial_claim_set(self):
        reservation = self._prepare_reconciling(key="audit-partial")
        with self.database.connection() as connection:
            connection.execute("DROP TRIGGER multi_authority_change_claims_no_delete")
            connection.execute(
                """
                DELETE FROM multi_authority_change_claims
                WHERE operation_id = ? AND authority_kind = 'grant_renewal'
                """,
                (reservation.operation_id,),
            )
        audit = self.store.audit_multi_claims(reservation.operation_id)
        self.assertEqual(
            audit.audit_status,
            MultiAuthorityClaimAuditStatus.INCONSISTENT,
        )

    def test_claim_audit_detects_corrupt_terminal_receipt(self):
        reservation = self._prepare_reconciling(key="audit-corrupt-receipt")
        self.store.record_multi_terminal_evidence(self._evidence(reservation))
        with self.database.connection() as connection:
            connection.execute("DROP TRIGGER multi_terminal_evidence_no_update")
            connection.execute(
                """
                UPDATE multi_authority_change_terminal_evidence
                SET evidence_digest = ?
                WHERE operation_id = ?
                """,
                ("0" * 64, reservation.operation_id),
            )
        audit = self.store.audit_multi_claims(reservation.operation_id)
        self.assertEqual(
            audit.audit_status,
            MultiAuthorityClaimAuditStatus.INCONSISTENT,
        )
        self.assertIsNone(audit.terminal_evidence)

    def test_claim_audit_returns_none_for_unknown_operation(self):
        self.assertIsNone(self.store.audit_multi_claims("missing-operation"))


    def test_claim_audit_detects_release_receipt_with_claims_still_present(self):
        reservation = self._prepare_reconciling(key="audit-release-with-claims")
        self.store.record_multi_terminal_evidence(self._evidence(reservation))
        with self.database.connection() as connection:
            terminal = connection.execute(
                """
                SELECT evidence_digest FROM multi_authority_change_terminal_evidence
                WHERE operation_id = ?
                """,
                (reservation.operation_id,),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO multi_authority_change_claim_releases (
                    operation_id, evidence_digest, released_at
                ) VALUES (?, ?, ?)
                """,
                (reservation.operation_id, terminal["evidence_digest"], NOW.isoformat()),
            )
        audit = self.store.audit_multi_claims(reservation.operation_id)
        self.assertEqual(
            audit.audit_status,
            MultiAuthorityClaimAuditStatus.INCONSISTENT,
        )
        self.assertEqual(audit.claimed_targets, reservation.intent.targets)

    def test_claim_audit_does_not_mutate_or_release_anything(self):
        reservation = self._prepare_reconciling(key="audit-read-only")
        self.store.record_multi_terminal_evidence(self._evidence(reservation))
        before = self.store.get_multi_claims(reservation.operation_id)
        first = self.store.audit_multi_claims(reservation.operation_id)
        second = self.store.audit_multi_claims(reservation.operation_id)
        after = self.store.get_multi_claims(reservation.operation_id)
        self.assertEqual(first, second)
        self.assertEqual(before, after)
        self.assertEqual(
            first.audit_status,
            MultiAuthorityClaimAuditStatus.TERMINAL_CLAIMS_HELD,
        )


if __name__ == "__main__":
    unittest.main()
