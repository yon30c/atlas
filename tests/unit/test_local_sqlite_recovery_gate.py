"""ME-D4N tests for the SQLite RecoveryGatePort adapter.

The recovery loader below is a test-only verified-evidence fixture. It validates
the adapter's transaction behavior, not cryptographic key custody or anti-rollback.
"""
from dataclasses import replace
from datetime import timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Thread
from types import SimpleNamespace
import unittest

from atlas.adapters.sqlite.consistency_journal import SQLiteConsistencyJournal
from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.adapters.sqlite.recovery_gate import LocalSQLiteRecoveryGateAdapter
from atlas.memory.journal import (
    ConsistencyPosition,
    ConsistencyRecordKind,
    ConsistencyTransition,
)
from atlas.memory.journal_reducer import ConsistencyJournalReducer
from atlas.memory.recovery_completion import (
    RecoveryCompletionReceipt,
    VerifiedRecoveryCompletionReceipt,
)
from atlas.memory.trust import (
    ConsistencyRecoveryVerificationResult,
    ConsistencyRecoveryVerificationStatus,
    VerifiedLocalConsistencyRecoveryState,
)
from atlas.memory.consistency import ReadAdmissionStatus
from atlas.memory.local_auth import object_commitment
from unit.test_memory_journal import NOW, RECORD_1, read_admitted


DOMAIN = "domain-a"
EPOCH = 1
RECOVERY_OPERATION = "recovery:domain-a:1:2"
RECOVERY_CLOSED_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a40"
FENCE_A_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a41"
FENCE_B_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a42"
ADMISSION_RECONCILED_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a43"
RECOVERY_RECONCILED_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a44"
ROUTES = frozenset({"assistant-response", "api-response"})
ADMISSIONS = frozenset({"admission-1"})


class FakeSigner:
    def sign_envelope(self, envelope, object_value):
        return replace(
            envelope,
            object_commitment=object_commitment(object_value),
            authentication_evidence="test-authentication-evidence",
        )


class LocalSQLiteRecoveryGateAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "atlas.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.journal = SQLiteConsistencyJournal(
            self.database,
            FakeSigner(),
            reducer_version="reducer-v1",
            issuer_id="issuer-test",
            issuer_role="service",
            key_reference="key-test",
            trust_policy_version="policy-v1",
        )
        self.assertTrue(self.journal.create_local_domain(DOMAIN, EPOCH))
        initial = self.journal.append_transition(
            ConsistencyPosition(DOMAIN, EPOCH, 0),
            "append:" + RECORD_1,
            read_admitted(record_id=RECORD_1),
        )
        self.assertIsNotNone(initial)

        # The production verifier is intentionally replaced with a deterministic
        # test fixture. The journal still performs real SQLite reads and writes.
        self.journal._recovery_trust_policy = SimpleNamespace(
            consistency_domain_id=DOMAIN
        )

        def verified_loader(domain_id):
            loaded = self.journal.load_recovery_state_result(domain_id)
            if loaded.state is None:
                return ConsistencyRecoveryVerificationResult(
                    ConsistencyRecoveryVerificationStatus.UNAVAILABLE
                )
            state = loaded.state
            projection = ConsistencyJournalReducer().reduce(state)
            verified = VerifiedLocalConsistencyRecoveryState(
                state=state,
                consistency_domain_id=domain_id,
                authority_epoch=state.authority_epoch,
                head_sequence=state.head_sequence,
                local_state_commitment=state.continuity_reference,
                verification_id="test-verification",
                verifier_id="test-verifier",
                trust_policy_version="policy-v1",
                verified_at=NOW,
                projection=projection,
            )
            return ConsistencyRecoveryVerificationResult(
                ConsistencyRecoveryVerificationStatus.VERIFIED,
                verified_local_state=verified,
            )

        self.journal.load_verified_recovery_state = verified_loader
        self.adapter = LocalSQLiteRecoveryGateAdapter(self.journal)

    def _close_transition(self):
        return ConsistencyTransition(
            record_id=RECOVERY_CLOSED_ID,
            schema_version=1,
            record_kind=ConsistencyRecordKind.RECOVERY_CLOSED,
            operation_id=RECOVERY_OPERATION,
            occurred_at=NOW,
            generation=2,
            route_ids=ROUTES,
            affected_admission_ids=ADMISSIONS,
        )

    def _current_position(self):
        state = self.journal.load_recovery_state(DOMAIN)
        return ConsistencyPosition(DOMAIN, EPOCH, state.head_sequence)

    def _close(self):
        result = self.adapter.close_recovery_gate(
            ConsistencyPosition(DOMAIN, EPOCH, 1),
            self._close_transition(),
        )
        self.assertIsNotNone(result)
        return result

    def _append(self, transition):
        result = self.journal.append_transition(
            self._current_position(),
            "append:" + transition.record_id,
            transition,
        )
        self.assertIsNotNone(result)
        return result

    def _complete_recovery(self):
        self._close()
        for endpoint_id, record_id in (
            ("assistant-response", FENCE_A_ID),
            ("api-response", FENCE_B_ID),
        ):
            self._append(
                ConsistencyTransition(
                    record_id=record_id,
                    schema_version=1,
                    record_kind=ConsistencyRecordKind.ENDPOINT_FENCED,
                    operation_id=RECOVERY_OPERATION,
                    occurred_at=NOW,
                    admission_id="admission-1",
                    endpoint_id=endpoint_id,
                    generation=2,
                    receipt_id="fence-receipt:" + endpoint_id,
                )
            )
        self._append(
            ConsistencyTransition(
                record_id=ADMISSION_RECONCILED_ID,
                schema_version=1,
                record_kind=ConsistencyRecordKind.ADMISSION_RECONCILED,
                operation_id=RECOVERY_OPERATION,
                occurred_at=NOW,
                admission_id="admission-1",
                generation=2,
                receipt_id="admission-terminal-receipt",
                admission_terminal_status=ReadAdmissionStatus.CANCELLED,
            )
        )

    def test_close_commits_recovery_event_and_gate_projection_together(self):
        commit = self._close()
        self.assertEqual(commit.position.sequence, 2)
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT recovery_gate_state, active_recovery_operation_id, "
                "active_recovery_generation, recovery_receipt_id "
                "FROM consistency_domains WHERE domain_id=?",
                (DOMAIN,),
            ).fetchone()
        self.assertEqual(row["recovery_gate_state"], "closed")
        self.assertEqual(row["active_recovery_operation_id"], RECOVERY_OPERATION)
        self.assertEqual(row["active_recovery_generation"], 2)
        self.assertIsNone(row["recovery_receipt_id"])
        self.assertTrue(
            self.adapter.ensure_recovery_gate_closed(RECOVERY_OPERATION, 2)
        )

    def test_gate_projection_failure_rolls_back_recovery_journal_append(self):
        self.adapter._update_projection = lambda *args, **kwargs: False
        result = self.adapter.close_recovery_gate(
            ConsistencyPosition(DOMAIN, EPOCH, 1),
            self._close_transition(),
        )
        self.assertIsNone(result)
        state = self.journal.load_recovery_state(DOMAIN)
        self.assertEqual(state.head_sequence, 1)
        self.assertFalse(state.entries[-1].transition.record_kind is ConsistencyRecordKind.RECOVERY_CLOSED)
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT active_recovery_operation_id, active_recovery_generation "
                "FROM consistency_domains WHERE domain_id=?",
                (DOMAIN,),
            ).fetchone()
        self.assertIsNone(row["active_recovery_operation_id"])
        self.assertIsNone(row["active_recovery_generation"])

    def test_concurrent_closures_have_only_one_commit(self):
        barrier = Barrier(2)
        original = self.adapter._verified_snapshot

        def synchronized_snapshot(domain_id):
            result = original(domain_id)
            barrier.wait()
            return result

        self.adapter._verified_snapshot = synchronized_snapshot
        results = []

        def close():
            results.append(
                self.adapter.close_recovery_gate(
                    ConsistencyPosition(DOMAIN, EPOCH, 1),
                    self._close_transition(),
                )
            )

        first = Thread(target=close)
        second = Thread(target=close)
        first.start()
        second.start()
        first.join()
        second.join()
        self.assertEqual(sum(item is not None for item in results), 1)
        self.assertEqual(self.journal.load_recovery_state(DOMAIN).head_sequence, 2)

    def test_reconcile_and_open_requires_exact_verified_receipt_and_is_atomic(self):
        self._complete_recovery()
        receipt = RecoveryCompletionReceipt(
            consistency_domain_id=DOMAIN,
            authority_epoch=EPOCH,
            operation_id=RECOVERY_OPERATION,
            generation=2,
            affected_admission_ids=ADMISSIONS,
            route_ids=ROUTES,
            receipt_id="recovery-terminal-receipt",
        )
        verified = VerifiedRecoveryCompletionReceipt(
            verification_id="verified-recovery",
            issuer_id="trusted-recovery-finalizer",
            verified_at=NOW,
            receipt=receipt,
        )
        transition = ConsistencyTransition(
            record_id=RECOVERY_RECONCILED_ID,
            schema_version=1,
            record_kind=ConsistencyRecordKind.RECOVERY_RECONCILED,
            operation_id=RECOVERY_OPERATION,
            occurred_at=NOW,
            generation=2,
            receipt_id=receipt.receipt_id,
            route_ids=ROUTES,
            affected_admission_ids=ADMISSIONS,
        )
        commit = self.adapter.reconcile_and_open_recovery_gate(
            self._current_position(), transition, verified
        )
        self.assertIsNotNone(commit)
        self.assertTrue(
            self.adapter.ensure_recovery_gate_open(
                RECOVERY_OPERATION, 2, receipt.receipt_id
            )
        )
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT recovery_gate_state, active_recovery_operation_id, "
                "active_recovery_generation, recovery_receipt_id "
                "FROM consistency_domains WHERE domain_id=?",
                (DOMAIN,),
            ).fetchone()
        self.assertEqual(row["recovery_gate_state"], "open")
        self.assertIsNone(row["active_recovery_operation_id"])
        self.assertIsNone(row["active_recovery_generation"])
        self.assertEqual(row["recovery_receipt_id"], receipt.receipt_id)

    def test_ensure_open_restores_only_the_latest_reconciled_closure(self):
        self._complete_recovery()
        receipt = RecoveryCompletionReceipt(
            consistency_domain_id=DOMAIN,
            authority_epoch=EPOCH,
            operation_id=RECOVERY_OPERATION,
            generation=2,
            affected_admission_ids=ADMISSIONS,
            route_ids=ROUTES,
            receipt_id="recovery-terminal-receipt",
        )
        transition = ConsistencyTransition(
            record_id=RECOVERY_RECONCILED_ID,
            schema_version=1,
            record_kind=ConsistencyRecordKind.RECOVERY_RECONCILED,
            operation_id=RECOVERY_OPERATION,
            occurred_at=NOW,
            generation=2,
            receipt_id=receipt.receipt_id,
            route_ids=ROUTES,
            affected_admission_ids=ADMISSIONS,
        )
        verified = VerifiedRecoveryCompletionReceipt(
            verification_id="verified-recovery",
            issuer_id="trusted-recovery-finalizer",
            verified_at=NOW,
            receipt=receipt,
        )
        self.assertIsNotNone(
            self.adapter.reconcile_and_open_recovery_gate(
                self._current_position(), transition, verified
            )
        )
        with self.database.write_transaction() as connection:
            connection.execute(
                "UPDATE consistency_domains SET recovery_gate_state='closed', "
                "recovery_receipt_id=NULL WHERE domain_id=?",
                (DOMAIN,),
            )
        self.assertTrue(
            self.adapter.ensure_recovery_gate_open(
                RECOVERY_OPERATION, 2, receipt.receipt_id
            )
        )


if __name__ == "__main__":
    unittest.main()
