"""ME-03J-B tests for global recovery completion and atomic gate reopening."""
import unittest
from dataclasses import replace
from datetime import datetime, timezone

from atlas.core.errors import ContractError
from atlas.memory.journal import ConsistencyRecordKind
from atlas.memory.recovery_completion import (
    RecoveryCompletionCoordinator,
    RecoveryCompletionReceipt,
    RecoveryCompletionStatus,
    VerifiedRecoveryCompletionReceipt,
)
from atlas.memory.recovery_finalization import (
    RecoveryAdmissionFinalizationCoordinator,
    RecoveryAdmissionFinalizationStatus,
    RecoveryAdmissionTerminalReceipt,
)
from atlas.memory.journal_reducer import ConsistencyJournalReducer
from atlas.memory.receipt_verification import ReceiptVerificationStatus
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

NOW = datetime(2026, 11, 13, 19, 30, tzinfo=timezone.utc)


class AdmissionFinalizer:
    def finalize_cancelled_admission(self, request):
        return RecoveryAdmissionTerminalReceipt(
            consistency_domain_id=request.consistency_domain_id,
            authority_epoch=request.authority_epoch,
            operation_id=request.operation_id,
            admission_id=request.admission_id,
            generation=request.generation,
            receipt_id=f"admission-terminal:{request.admission_id}",
        )


class CompletionFinalizer:
    def __init__(self, *, wrong_binding=False, raises=False):
        self.wrong_binding = wrong_binding
        self.raises = raises
        self.requests = []

    def finalize_recovery(self, request):
        self.requests.append(request)
        if self.raises:
            raise TimeoutError("recovery finalizer unavailable")
        return RecoveryCompletionReceipt(
            consistency_domain_id=request.consistency_domain_id,
            authority_epoch=request.authority_epoch,
            operation_id=request.operation_id,
            generation=request.generation,
            affected_admission_ids=(
                frozenset({"wrong-admission"})
                if self.wrong_binding else request.affected_admission_ids
            ),
            route_ids=request.route_ids,
            receipt_id="recovery-terminal-receipt",
        )


class CompletionVerifier:
    def __init__(self, *, raises=False):
        self.raises = raises
        self.requests = []

    def verify_recovery_completion(self, request, receipt):
        self.requests.append((request, receipt))
        if self.raises:
            raise TimeoutError("recovery receipt verifier unavailable")
        return VerifiedRecoveryCompletionReceipt(
            verification_id="verified-recovery-terminal",
            issuer_id="trusted:recovery-authority",
            verified_at=NOW,
            receipt=receipt,
        )

    def verify_recovery_completion_with_context(self, request, receipt, trust_context):
        if not trust_context.binds_recovery_completion(request, receipt):
            return None
        return self.verify_recovery_completion(request, receipt)


class AtomicRecoveryGate(CoordinatorRecoveryGateFake):
    def __init__(self, journal):
        super().__init__(journal)
        self.atomic_calls = 0
        self.ambiguous_return = False

    def reconcile_and_open_recovery_gate(self, expected_position, transition, verified_receipt):
        self.atomic_calls += 1
        if (
            not self.closed
            or transition.record_kind is not ConsistencyRecordKind.RECOVERY_RECONCILED
            or verified_receipt.receipt.receipt_id != transition.receipt_id
            or verified_receipt.receipt.operation_id != transition.operation_id
            or verified_receipt.receipt.generation != transition.generation
            or verified_receipt.receipt.affected_admission_ids != transition.affected_admission_ids
            or verified_receipt.receipt.route_ids != transition.route_ids
            or expected_position.sequence != self.journal.state.head_sequence
        ):
            return None
        commit = self.journal.append_transition(
            expected_position, f"append:{transition.record_id}", transition
        )
        if commit is None:
            return None
        self.closed = False
        return None if self.ambiguous_return else commit

    def ensure_recovery_gate_open(self, operation_id, generation, receipt_id):
        projection = ConsistencyJournalReducer().reduce(self.journal.state)
        closure = next(
            (item for item in projection.recovery_closures
             if item.operation_id == operation_id and item.reconciled),
            None,
        )
        if (
            closure is None
            or closure.generation != generation
            or closure.terminal_receipt_id != receipt_id
        ):
            return False
        self.closed = False
        return True


class RecoveryCompletionCoordinatorTests(unittest.TestCase):
    def setUp(self):
        base = make_recovery_journal(include_reconcile=False)
        initial = replace(base, entries=base.entries[:1], head_sequence=1)
        self.journal = CoordinatorJournalFake(initial)
        self.gate = AtomicRecoveryGate(self.journal)
        self.endpoint_fencer = GateAwareEndpointFencer(self.gate)
        self.terminal_verifier = FakeTerminalVerifier()
        ids = iter(
            f"018bcfe5-7b3a-7cc2-98c4-dc0c0c0749{index:02x}"
            for index in range(40)
        )
        recovery = RecoveryJournalCoordinator(
            self.journal, self.gate, self.endpoint_fencer, self.terminal_verifier,
            domain_id="consistency-domain",
            id_factory=lambda: next(ids), clock=lambda: NOW,
        )
        self.assertIs(recovery.run().status, RecoveryCoordinatorStatus.FENCING_RECORDED)
        admission_finalizer = AdmissionFinalizer()
        admission_coordinator = RecoveryAdmissionFinalizationCoordinator(
            self.journal, admission_finalizer, self.terminal_verifier,
            trust_context_factory=FakeReceiptTrustContextFactory(),
            domain_id="consistency-domain",
            id_factory=lambda: next(ids), clock=lambda: NOW,
        )
        self.assertIs(
            admission_coordinator.run().status,
            RecoveryAdmissionFinalizationStatus.ADMISSIONS_TERMINAL,
        )
        self.completion_finalizer = CompletionFinalizer()
        self.completion_verifier = CompletionVerifier()
        self.coordinator = RecoveryCompletionCoordinator(
            self.journal,
            self.gate,
            self.completion_finalizer,
            self.completion_verifier,
            self.terminal_verifier,
            trust_context_factory=FakeReceiptTrustContextFactory(),
            domain_id="consistency-domain",
            id_factory=lambda: next(ids),
            clock=lambda: NOW,
        )

    def test_global_completion_is_verified_and_gate_opens_atomically(self):
        result = self.coordinator.run()
        self.assertIs(result.status, RecoveryCompletionStatus.RECOVERY_RECONCILED)
        self.assertFalse(self.gate.closed)
        self.assertEqual(self.gate.atomic_calls, 1)
        self.assertEqual(len(self.completion_finalizer.requests), 1)
        self.assertEqual(len(self.completion_verifier.requests), 1)
        projection = ConsistencyJournalReducer().reduce(self.journal.state)
        self.assertTrue(projection.recovery_closures[0].reconciled)
        self.assertEqual(
            projection.recovery_closures[0].terminal_receipt_id,
            "recovery-terminal-receipt",
        )


    def test_receipts_reject_empty_inventory_identifiers(self):
        self.coordinator.run()
        valid = self.completion_finalizer.requests[-1]
        with self.assertRaises(ContractError):
            RecoveryCompletionReceipt(
                consistency_domain_id=valid.consistency_domain_id,
                authority_epoch=valid.authority_epoch,
                operation_id=valid.operation_id,
                generation=valid.generation,
                affected_admission_ids=frozenset({""}),
                route_ids=valid.route_ids,
                receipt_id="invalid-empty-admission",
            )
        with self.assertRaises(Exception):
            RecoveryCompletionReceipt(
                consistency_domain_id=valid.consistency_domain_id,
                authority_epoch=valid.authority_epoch,
                operation_id=valid.operation_id,
                generation=valid.generation,
                affected_admission_ids=valid.affected_admission_ids,
                route_ids=frozenset({""}),
                receipt_id="invalid-empty-route",
            )

    def test_finalizer_wrong_inventory_keeps_gate_closed(self):
        self.completion_finalizer.wrong_binding = True
        result = self.coordinator.run()
        self.assertIs(result.status, RecoveryCompletionStatus.PENDING)
        self.assertTrue(self.gate.closed)
        self.assertFalse(any(
            item.record_kind is ConsistencyRecordKind.RECOVERY_RECONCILED
            for item in self.journal.appended
        ))

    def test_global_verifier_timeout_keeps_gate_closed(self):
        self.completion_verifier.raises = True
        result = self.coordinator.run()
        self.assertIs(result.status, RecoveryCompletionStatus.PENDING)
        self.assertTrue(self.gate.closed)
        self.assertFalse(any(
            item.record_kind is ConsistencyRecordKind.RECOVERY_RECONCILED
            for item in self.journal.appended
        ))

    def test_ambiguous_atomic_result_is_reconciled_from_journal_and_gate(self):
        self.gate.ambiguous_return = True
        result = self.coordinator.run()
        self.assertIs(result.status, RecoveryCompletionStatus.RECOVERY_RECONCILED)
        self.assertFalse(self.gate.closed)
        self.assertEqual(self.gate.atomic_calls, 1)

    def test_restart_confirms_only_the_exact_terminal_open_gate(self):
        first = self.coordinator.run()
        second = self.coordinator.run()
        self.assertIs(first.status, RecoveryCompletionStatus.RECOVERY_RECONCILED)
        self.assertIs(second.status, RecoveryCompletionStatus.RECOVERY_RECONCILED)
        self.assertFalse(self.gate.closed)
        self.assertEqual(self.gate.atomic_calls, 1)


if __name__ == "__main__":
    unittest.main()
