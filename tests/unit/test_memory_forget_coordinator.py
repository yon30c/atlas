"""Pure ME-03D Forget Coordinator state-machine tests."""
import unittest
from dataclasses import replace

from atlas.core.errors import ContractError
from atlas.memory.forget import ForgetClosure, ForgetClosureStatus, ForgetTarget
from atlas.memory.forget_coordinator import (
    ForgetBlockReason,
    ForgetCanonicalStateReceipt,
    ForgetCoordinatorReducer,
    ForgetDeletionAttempt,
    ForgetDeletionOutcome,
    ForgetDestination,
    ForgetDestinationInventory,
    ForgetDestinationKind,
    ForgetOperation,
    ForgetOperationState,
    ForgetVerificationOutcome,
    ForgetVerificationReceipt,
)

MEMORY_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a11"
OTHER_MEMORY_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a14"
CLOSURE_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a13"


def make_closure(status=ForgetClosureStatus.CLOSING, unresolved=None):
    if unresolved is None:
        unresolved = frozenset({"admission-1"}) if status is ForgetClosureStatus.CLOSING else frozenset()
    return ForgetClosure(
        closure_id=CLOSURE_ID,
        operation_id="forget-op-1",
        idempotency_key="forget-key-1",
        target=ForgetTarget(MEMORY_ID),
        generation=2,
        affected_admission_ids=frozenset({"admission-1"}),
        unresolved_admission_ids=unresolved,
        delivery_route_ids=frozenset({"assistant-response", "api-response"}),
        status=status,
    )


def suppressed_operation():
    reducer = ForgetCoordinatorReducer()
    closing = ForgetOperation(make_closure(), ForgetOperationState.CLOSING)
    suppressed = reducer.mark_suppressed(
        closing, make_closure(ForgetClosureStatus.SUPPRESSED)
    )
    return reducer, suppressed


def inventory(
    revision=1,
    destinations=None,
    complete=True,
    retention_policy_reference=None,
    memory_id=MEMORY_ID,
    operation_id="forget-op-1",
):
    if destinations is None:
        destinations = (
            ForgetDestination("primary-store", ForgetDestinationKind.PRIMARY_STORAGE),
            ForgetDestination("history-store", ForgetDestinationKind.VERSION_HISTORY),
        )
    return ForgetDestinationInventory(
        inventory_id=f"inventory-{revision}",
        operation_id=operation_id,
        target=ForgetTarget(memory_id),
        revision=revision,
        destinations=destinations,
        coverage_reference=f"coverage-{revision}",
        complete=complete,
        retention_policy_reference=retention_policy_reference,
    )


def begin_purging(inv=None):
    reducer, operation = suppressed_operation()
    operation = reducer.request_inventory(operation)
    operation = reducer.accept_inventory(operation, inv or inventory())
    return reducer, operation


def delete_all(reducer, operation):
    for index, destination in enumerate(operation.inventory.destinations, start=1):
        operation = reducer.record_deletion_attempt(
            operation,
            ForgetDeletionAttempt(
                operation_id=operation.closure.operation_id,
                destination_id=destination.destination_id,
                inventory_revision=operation.inventory.revision,
                attempt_id=f"attempt-{index}",
                outcome=ForgetDeletionOutcome.ACKNOWLEDGED,
                receipt_id=f"delete-receipt-{index}",
            ),
        )
    return operation


def verify_all(reducer, operation):
    operation = reducer.begin_verification(operation)
    for index, destination in enumerate(operation.inventory.destinations, start=1):
        operation = reducer.record_verification(
            operation,
            ForgetVerificationReceipt(
                operation_id=operation.closure.operation_id,
                destination_id=destination.destination_id,
                inventory_revision=operation.inventory.revision,
                verification_id=f"verify-{index}",
                outcome=ForgetVerificationOutcome.ABSENT,
                evidence_reference=f"absence-evidence-{index}",
            ),
        )
    return operation


def canonical_receipt(operation, new_revision=7, tombstone="opaque-tombstone-reference", receipt_id="canonical-receipt"):
    return ForgetCanonicalStateReceipt(
        operation_id=operation.closure.operation_id,
        memory_id=operation.closure.target.memory_id,
        expected_revision=6,
        new_revision=new_revision,
        tombstone_reference=tombstone,
        receipt_id=receipt_id,
    )


def canonical_and_complete(reducer, operation):
    receipt = canonical_receipt(operation)
    operation = reducer.mark_canonical_forgotten(
        operation,
        expected_inventory_revision=operation.inventory.revision,
        expected_canonical_revision=6,
        receipt=receipt,
    )
    return reducer.complete(
        operation,
        current_inventory_revision=operation.inventory.revision,
        canonical_receipt=receipt,
    )


class ForgetCoordinatorReducerTests(unittest.TestCase):
    def setUp(self):
        self.reducer = ForgetCoordinatorReducer()

    def test_d01_logical_suppression_requires_authority_closure_terminal(self):
        operation = ForgetOperation(make_closure(), ForgetOperationState.CLOSING)
        with self.assertRaises(ContractError):
            self.reducer.mark_suppressed(operation, make_closure())

    def test_d02_inventory_cannot_be_requested_before_suppression(self):
        operation = ForgetOperation(make_closure(), ForgetOperationState.CLOSING)
        with self.assertRaises(ContractError):
            self.reducer.request_inventory(operation)

    def test_d03_suppression_transition_preserves_exact_target_and_scope(self):
        _, operation = suppressed_operation()
        wrong = replace(
            operation.closure,
            target=ForgetTarget(OTHER_MEMORY_ID),
        )
        with self.assertRaises(ContractError):
            self.reducer.mark_suppressed(
                ForgetOperation(make_closure(), ForgetOperationState.CLOSING),
                wrong,
            )

    def test_d04_inventory_target_must_match_forget_target(self):
        reducer, operation = suppressed_operation()
        operation = reducer.request_inventory(operation)
        with self.assertRaises(ContractError):
            reducer.accept_inventory(operation, inventory(memory_id=OTHER_MEMORY_ID))

    def test_d05_incomplete_inventory_blocks_purge(self):
        reducer, operation = suppressed_operation()
        operation = reducer.request_inventory(operation)
        operation = reducer.accept_inventory(operation, inventory(complete=False))
        self.assertIs(operation.state, ForgetOperationState.BLOCKED)
        self.assertIs(operation.block_reason, ForgetBlockReason.INVENTORY_INCOMPLETE)

    def test_d06_delete_acknowledgement_is_not_absence_verification(self):
        reducer, operation = begin_purging()
        operation = delete_all(reducer, operation)
        with self.assertRaises(ContractError):
            reducer.mark_canonical_forgotten(
                operation,
                operation.inventory.revision,
                6,
                canonical_receipt(operation),
            )

    def test_d07_all_destinations_absent_allows_canonical_mark_and_completion(self):
        reducer, operation = begin_purging()
        operation = delete_all(reducer, operation)
        operation = verify_all(reducer, operation)
        operation = canonical_and_complete(reducer, operation)
        self.assertIs(operation.state, ForgetOperationState.COMPLETED)
        self.assertEqual(operation.canonical_state_revision, 7)

    def test_d08_present_destination_keeps_operation_blocked(self):
        reducer, operation = begin_purging()
        operation = delete_all(reducer, operation)
        operation = reducer.begin_verification(operation)
        operation = reducer.record_verification(
            operation,
            ForgetVerificationReceipt(
                operation.closure.operation_id, "primary-store", 1, "verify-present",
                ForgetVerificationOutcome.PRESENT, "present-evidence",
            ),
        )
        self.assertIs(operation.state, ForgetOperationState.BLOCKED)
        self.assertIs(operation.block_reason, ForgetBlockReason.DESTINATION_PRESENT)

    def test_d09_unavailable_destination_keeps_operation_blocked(self):
        reducer, operation = begin_purging()
        operation = delete_all(reducer, operation)
        operation = reducer.begin_verification(operation)
        operation = reducer.record_verification(
            operation,
            ForgetVerificationReceipt(
                operation.closure.operation_id, "primary-store", 1, "verify-unavailable",
                ForgetVerificationOutcome.UNAVAILABLE,
            ),
        )
        self.assertIs(operation.block_reason, ForgetBlockReason.DESTINATION_UNAVAILABLE)

    def test_d10_unknown_delete_outcome_requires_reconciliation_before_retry(self):
        reducer, operation = begin_purging()
        operation = reducer.record_deletion_attempt(
            operation,
            ForgetDeletionAttempt(
                operation.closure.operation_id, "primary-store", 1, "attempt-unknown",
                ForgetDeletionOutcome.UNKNOWN,
            ),
        )
        self.assertIs(operation.state, ForgetOperationState.BLOCKED)
        with self.assertRaises(ContractError):
            reducer.record_deletion_attempt(
                operation,
                ForgetDeletionAttempt(
                    operation.closure.operation_id, "primary-store", 1, "attempt-retry",
                    ForgetDeletionOutcome.ACKNOWLEDGED, "receipt-retry",
                ),
            )
        operation = reducer.reconcile_unknown_attempt(
            operation, "attempt-unknown", ForgetDeletionOutcome.ACKNOWLEDGED,
            "reconciled-receipt",
        )
        self.assertIs(operation.state, ForgetOperationState.PURGING)

    def test_d11_same_deletion_attempt_is_idempotent(self):
        reducer, operation = begin_purging()
        attempt = ForgetDeletionAttempt(
            operation.closure.operation_id, "primary-store", 1, "attempt-1",
            ForgetDeletionOutcome.ACKNOWLEDGED, "receipt-1",
        )
        operation = reducer.record_deletion_attempt(operation, attempt)
        self.assertIs(reducer.record_deletion_attempt(operation, attempt), operation)

    def test_d12_attempt_id_cannot_be_reused_with_different_result(self):
        reducer, operation = begin_purging()
        operation = reducer.record_deletion_attempt(
            operation,
            ForgetDeletionAttempt(
                operation.closure.operation_id, "primary-store", 1, "attempt-1",
                ForgetDeletionOutcome.ACKNOWLEDGED, "receipt-1",
            ),
        )
        with self.assertRaises(ContractError):
            reducer.record_deletion_attempt(
                operation,
                ForgetDeletionAttempt(
                    operation.closure.operation_id, "primary-store", 1, "attempt-1",
                    ForgetDeletionOutcome.REJECTED, "receipt-2",
                ),
            )

    def test_d13_new_inventory_revision_resets_verification_scope(self):
        reducer, operation = begin_purging()
        operation = delete_all(reducer, operation)
        operation = verify_all(reducer, operation)
        operation = reducer.accept_inventory(
            operation,
            inventory(
                revision=2,
                destinations=(
                    ForgetDestination("primary-store", ForgetDestinationKind.PRIMARY_STORAGE),
                    ForgetDestination("history-store", ForgetDestinationKind.VERSION_HISTORY),
                    ForgetDestination("backup-store", ForgetDestinationKind.BACKUP),
                ),
                retention_policy_reference="approved-backup-policy",
            ),
        )
        self.assertIs(operation.state, ForgetOperationState.PURGING)
        self.assertIsNone(operation.canonical_state_revision)
        with self.assertRaises(ContractError):
            reducer.begin_verification(operation)

    def test_d14_inventory_revision_cannot_roll_back(self):
        reducer, operation = begin_purging()
        with self.assertRaises(ContractError):
            reducer.accept_inventory(operation, inventory(revision=0))

    def test_d15_inventory_cannot_silently_drop_previous_destination(self):
        reducer, operation = begin_purging()
        with self.assertRaises(ContractError):
            reducer.accept_inventory(
                operation,
                inventory(
                    revision=2,
                    destinations=(ForgetDestination(
                        "primary-store", ForgetDestinationKind.PRIMARY_STORAGE
                    ),),
                ),
            )

    def test_d16_backup_without_retention_policy_blocks_completion(self):
        reducer, operation = suppressed_operation()
        operation = reducer.request_inventory(operation)
        operation = reducer.accept_inventory(
            operation,
            inventory(destinations=(
                ForgetDestination("backup-store", ForgetDestinationKind.BACKUP),
            )),
        )
        self.assertIs(operation.state, ForgetOperationState.BLOCKED)
        self.assertIs(operation.block_reason, ForgetBlockReason.RETENTION_POLICY_UNDEFINED)

    def test_d17_backup_with_explicit_policy_can_enter_purge(self):
        reducer, operation = suppressed_operation()
        operation = reducer.request_inventory(operation)
        operation = reducer.accept_inventory(
            operation,
            inventory(
                destinations=(ForgetDestination("backup-store", ForgetDestinationKind.BACKUP),),
                retention_policy_reference="approved-backup-policy",
            ),
        )
        self.assertIs(operation.state, ForgetOperationState.PURGING)

    def test_d18_same_verification_receipt_is_idempotent(self):
        reducer, operation = begin_purging()
        operation = delete_all(reducer, operation)
        operation = reducer.begin_verification(operation)
        receipt = ForgetVerificationReceipt(
            operation.closure.operation_id, "primary-store", 1, "verify-1",
            ForgetVerificationOutcome.ABSENT, "absence-1",
        )
        operation = reducer.record_verification(operation, receipt)
        self.assertIs(reducer.record_verification(operation, receipt), operation)

    def test_d19_verification_id_cannot_be_reused_with_other_evidence(self):
        reducer, operation = begin_purging()
        operation = delete_all(reducer, operation)
        operation = reducer.begin_verification(operation)
        receipt = ForgetVerificationReceipt(
            operation.closure.operation_id, "primary-store", 1, "verify-1",
            ForgetVerificationOutcome.ABSENT, "absence-1",
        )
        operation = reducer.record_verification(operation, receipt)
        with self.assertRaises(ContractError):
            reducer.record_verification(
                operation,
                replace(receipt, outcome=ForgetVerificationOutcome.PRESENT,
                        evidence_reference="present-2"),
            )

    def test_d20_canonical_mark_is_idempotent_but_not_mutable(self):
        reducer, operation = begin_purging()
        operation = delete_all(reducer, operation)
        operation = verify_all(reducer, operation)
        receipt = canonical_receipt(operation, tombstone="tombstone-1")
        operation = reducer.mark_canonical_forgotten(operation, 1, 6, receipt)
        self.assertIs(
            reducer.mark_canonical_forgotten(operation, 1, 6, receipt),
            operation,
        )
        with self.assertRaises(ContractError):
            reducer.mark_canonical_forgotten(
                operation, 1, 6,
                canonical_receipt(operation, new_revision=8, tombstone="tombstone-2"),
            )

    def test_d21_completed_operation_is_idempotent(self):
        reducer, operation = begin_purging()
        operation = delete_all(reducer, operation)
        operation = verify_all(reducer, operation)
        operation = canonical_and_complete(reducer, operation)
        self.assertIs(
            reducer.complete(
                operation, 1, canonical_receipt(operation)
            ),
            operation,
        )

    def test_d22_empty_inventory_requires_complete_attestation(self):
        reducer, operation = suppressed_operation()
        operation = reducer.request_inventory(operation)
        operation = reducer.accept_inventory(
            operation,
            inventory(destinations=(), complete=True),
        )
        operation = reducer.begin_verification(operation)
        operation = canonical_and_complete(reducer, operation)
        self.assertIs(operation.state, ForgetOperationState.COMPLETED)

    def test_d23_empty_but_unattested_inventory_blocks(self):
        reducer, operation = suppressed_operation()
        operation = reducer.request_inventory(operation)
        operation = reducer.accept_inventory(
            operation,
            inventory(destinations=(), complete=False),
        )
        self.assertIs(operation.state, ForgetOperationState.BLOCKED)

    def test_d24_receipt_from_another_operation_is_rejected(self):
        reducer, operation = begin_purging()
        with self.assertRaises(ContractError):
            reducer.record_deletion_attempt(
                operation,
                ForgetDeletionAttempt(
                    "other-operation", "primary-store", 1, "attempt-1",
                    ForgetDeletionOutcome.ACKNOWLEDGED, "receipt-1",
                ),
            )

    def test_d25_receipt_for_unknown_destination_is_rejected(self):
        reducer, operation = begin_purging()
        with self.assertRaises(ContractError):
            reducer.record_deletion_attempt(
                operation,
                ForgetDeletionAttempt(
                    operation.closure.operation_id, "unknown-store", 1, "attempt-1",
                    ForgetDeletionOutcome.ACKNOWLEDGED, "receipt-1",
                ),
            )

    def test_d26_future_inventory_revision_receipt_is_rejected(self):
        reducer, operation = begin_purging()
        with self.assertRaises(ContractError):
            reducer.record_deletion_attempt(
                operation,
                ForgetDeletionAttempt(
                    operation.closure.operation_id, "primary-store", 2, "attempt-1",
                    ForgetDeletionOutcome.ACKNOWLEDGED, "receipt-1",
                ),
            )

    def test_d27_completed_state_requires_verified_destinations(self):
        reducer, operation = begin_purging()
        operation = delete_all(reducer, operation)
        with self.assertRaises(ContractError):
            replace(
                operation,
                state=ForgetOperationState.COMPLETED,
                canonical_state_revision=7,
                tombstone_reference="tombstone",
            )

    def test_d28_completed_state_requires_tombstone_and_canonical_revision(self):
        reducer, operation = begin_purging()
        operation = delete_all(reducer, operation)
        operation = verify_all(reducer, operation)
        with self.assertRaises(ContractError):
            replace(operation, state=ForgetOperationState.COMPLETED)

    def test_d29_inventory_change_after_canonical_mark_blocks_completion(self):
        reducer, operation = begin_purging()
        operation = delete_all(reducer, operation)
        operation = verify_all(reducer, operation)
        receipt = canonical_receipt(operation, tombstone="tombstone")
        operation = reducer.mark_canonical_forgotten(operation, 1, 6, receipt)
        blocked = reducer.complete(operation, 2, receipt)
        self.assertIs(blocked.state, ForgetOperationState.BLOCKED)
        self.assertIs(blocked.block_reason, ForgetBlockReason.INVENTORY_CHANGED)




    def test_d34_unknown_attempt_must_be_reconciled_before_inventory_refresh(self):
        reducer, operation = begin_purging()
        operation = reducer.record_deletion_attempt(
            operation,
            ForgetDeletionAttempt(
                operation.closure.operation_id, "primary-store", 1, "attempt-unknown",
                ForgetDeletionOutcome.UNKNOWN,
            ),
        )
        with self.assertRaises(ContractError):
            reducer.accept_inventory(
                operation,
                inventory(
                    revision=2,
                    destinations=(
                        ForgetDestination("primary-store", ForgetDestinationKind.PRIMARY_STORAGE),
                        ForgetDestination("history-store", ForgetDestinationKind.VERSION_HISTORY),
                    ),
                ),
            )

    def test_d32_inventory_must_be_bound_to_exact_forget_operation(self):
        reducer, operation = suppressed_operation()
        operation = reducer.request_inventory(operation)
        with self.assertRaises(ContractError):
            reducer.accept_inventory(
                operation, inventory(operation_id="another-forget-operation")
            )

    def test_d33_destination_id_cannot_change_kind_between_inventory_revisions(self):
        reducer, operation = begin_purging()
        with self.assertRaises(ContractError):
            reducer.accept_inventory(
                operation,
                inventory(
                    revision=2,
                    destinations=(
                        ForgetDestination("primary-store", ForgetDestinationKind.BACKUP),
                        ForgetDestination("history-store", ForgetDestinationKind.VERSION_HISTORY),
                    ),
                    retention_policy_reference="backup-policy",
                ),
            )

    def test_d31_canonical_receipt_must_match_expected_compare_and_swap_revision(self):
        reducer, operation = begin_purging()
        operation = delete_all(reducer, operation)
        operation = verify_all(reducer, operation)
        with self.assertRaises(ContractError):
            reducer.mark_canonical_forgotten(
                operation, 1, 5, canonical_receipt(operation)
            )

    def test_d30_evidence_models_do_not_store_content_or_hashes(self):
        reducer, operation = begin_purging()
        attempt = ForgetDeletionAttempt(
            operation.closure.operation_id, "primary-store", 1, "attempt-1",
            ForgetDeletionOutcome.ACKNOWLEDGED, "receipt-1",
        )
        operation = reducer.record_deletion_attempt(operation, attempt)
        self.assertFalse(hasattr(attempt, "content"))
        self.assertFalse(hasattr(attempt, "content_hash"))
        self.assertFalse(hasattr(operation, "payload"))


if __name__ == "__main__":
    unittest.main()
