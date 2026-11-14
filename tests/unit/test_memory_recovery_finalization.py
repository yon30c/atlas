"""ME-03J tests for verified terminal admission finalization."""
import unittest
from dataclasses import replace
from datetime import datetime, timezone

from atlas.memory.consistency import ReadAdmissionStatus
from atlas.memory.journal import ConsistencyRecordKind
from atlas.memory.journal_reducer import ConsistencyJournalReducer
from atlas.memory.receipt_verification import (
    ReceiptVerificationStatus,
)
from atlas.memory.recovery_finalization import (
    RecoveryAdmissionFinalizationCoordinator,
    RecoveryAdmissionFinalizationStatus,
    RecoveryAdmissionTerminalReceipt,
)
from unit.test_memory_unresolved_admission_recovery import (
    CoordinatorJournalFake,
    CoordinatorRecoveryGateFake,
    FakeTerminalVerifier,
    GateAwareEndpointFencer,
    RecoveryJournalCoordinator,
    RecoveryCoordinatorStatus,
    make_recovery_journal,
)

from tests.fakes.receipt_trust import FakeReceiptTrustContextFactory

NOW = datetime(2026, 11, 13, 19, 0, tzinfo=timezone.utc)


class FakeAdmissionFinalizer:
    def __init__(self, *, wrong_binding=False, raises=False):
        self.wrong_binding = wrong_binding
        self.raises = raises
        self.requests = []

    def finalize_cancelled_admission(self, request):
        self.requests.append(request)
        if self.raises:
            raise TimeoutError("finalizer unavailable")
        return RecoveryAdmissionTerminalReceipt(
            consistency_domain_id=request.consistency_domain_id,
            authority_epoch=request.authority_epoch,
            operation_id=request.operation_id,
            admission_id=("wrong-admission" if self.wrong_binding else request.admission_id),
            generation=request.generation,
            receipt_id=f"admission-terminal:{request.admission_id}",
        )


class RecoveryAdmissionFinalizationTests(unittest.TestCase):
    def setUp(self):
        base = make_recovery_journal(include_reconcile=False)
        initial = replace(base, entries=base.entries[:1], head_sequence=1)
        self.journal = CoordinatorJournalFake(initial)
        self.gate = CoordinatorRecoveryGateFake(self.journal)
        self.fencer = GateAwareEndpointFencer(self.gate)
        self.verifier = FakeTerminalVerifier()
        self.ids = iter(
            f"018bcfe5-7b3a-7cc2-98c4-dc0c0c0748{index:02x}"
            for index in range(30)
        )
        recovery = RecoveryJournalCoordinator(
            self.journal,
            self.gate,
            self.fencer,
            self.verifier,
            trust_context_factory=FakeReceiptTrustContextFactory(),
            domain_id="consistency-domain",
            id_factory=lambda: next(self.ids),
            clock=lambda: NOW,
        )
        result = recovery.run()
        self.assertIs(result.status, RecoveryCoordinatorStatus.FENCING_RECORDED)
        self.finalizer = FakeAdmissionFinalizer()
        self.coordinator = RecoveryAdmissionFinalizationCoordinator(
            self.journal,
            self.finalizer,
            self.verifier,
            domain_id="consistency-domain",
            id_factory=lambda: next(self.ids),
            clock=lambda: NOW,
        )

    def test_finalizes_only_after_every_endpoint_receipt_is_verified(self):
        result = self.coordinator.run()
        self.assertIs(result.status, RecoveryAdmissionFinalizationStatus.ADMISSIONS_TERMINAL)
        self.assertEqual(result.reconciled_admission_ids, ("journal-recovery-admission",))
        self.assertEqual(len(self.finalizer.requests), 1)
        request = self.finalizer.requests[0]
        self.assertEqual(
            {item.endpoint_id for item in request.endpoint_receipts},
            {"assistant-response", "api-response"},
        )
        self.assertEqual(request.route_ids, frozenset({"assistant-response", "api-response"}))
        self.assertEqual(
            [item.record_kind for item in self.journal.appended].count(
                ConsistencyRecordKind.ADMISSION_RECONCILED
            ),
            1,
        )
        projection = ConsistencyJournalReducer().reduce(self.journal.state)
        admission = projection.admissions[0]
        self.assertIs(admission.status, ReadAdmissionStatus.CANCELLED)
        self.assertEqual(admission.terminal_operation_id, "recovery:consistency-domain:4:5")

    def test_retries_are_idempotent_and_do_not_reconcile_twice(self):
        first = self.coordinator.run()
        second = self.coordinator.run()
        self.assertIs(first.status, RecoveryAdmissionFinalizationStatus.ADMISSIONS_TERMINAL)
        self.assertIs(second.status, RecoveryAdmissionFinalizationStatus.ADMISSIONS_TERMINAL)
        self.assertEqual(len(self.finalizer.requests), 1)
        self.assertEqual(
            [item.record_kind for item in self.journal.appended].count(
                ConsistencyRecordKind.ADMISSION_RECONCILED
            ),
            1,
        )

    def test_wrong_admission_receipt_binding_fails_closed(self):
        self.finalizer.wrong_binding = True
        result = self.coordinator.run()
        self.assertIs(result.status, RecoveryAdmissionFinalizationStatus.PENDING)
        self.assertEqual(result.pending_admission_ids, ("journal-recovery-admission",))
        self.assertFalse(any(
            item.record_kind is ConsistencyRecordKind.ADMISSION_RECONCILED
            for item in self.journal.appended
        ))

    def test_verifier_unavailable_fails_closed(self):
        self.verifier.status = ReceiptVerificationStatus.UNAVAILABLE
        result = self.coordinator.run()
        self.assertIs(result.status, RecoveryAdmissionFinalizationStatus.PENDING)
        self.assertFalse(any(
            item.record_kind is ConsistencyRecordKind.ADMISSION_RECONCILED
            for item in self.journal.appended
        ))

    def test_finalizer_timeout_keeps_admission_unresolved(self):
        self.finalizer.raises = True
        result = self.coordinator.run()
        self.assertIs(result.status, RecoveryAdmissionFinalizationStatus.PENDING)
        projection = ConsistencyJournalReducer().reduce(self.journal.state)
        self.assertIs(projection.admissions[0].status, ReadAdmissionStatus.UNRESOLVED)

    def test_recovery_gate_remains_closed_after_admission_finalization(self):
        result = self.coordinator.run()
        self.assertIs(result.status, RecoveryAdmissionFinalizationStatus.ADMISSIONS_TERMINAL)
        self.assertTrue(self.gate.closed)
        self.assertFalse(any(
            item.record_kind is ConsistencyRecordKind.RECOVERY_RECONCILED
            for item in self.journal.appended
        ))


if __name__ == "__main__":
    unittest.main()
