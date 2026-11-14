"""Deterministic test-only receipt trust-context factory."""
from atlas.memory.trust import ReceiptTrustContext, TrustedReceiptKind


class FakeReceiptTrustContextFactory:
    """Creates contexts only for tests; never represents production trust."""

    def for_terminal_receipt(self, request, *, purpose, verification_time):
        return ReceiptTrustContext(
            consistency_domain_id=request.consistency_domain_id,
            authority_epoch=request.authority_epoch,
            operation_id=request.operation_id,
            expected_receipt_kind=TrustedReceiptKind(request.kind.value),
            canonical_request_reference=(
                f"test-canonical:{request.operation_id}:{request.receipt_id}"
            ),
            trust_policy_version="test-policy-v1",
            verification_time=verification_time,
            purpose=purpose,
            expected_receipt_id=request.receipt_id,
            admission_id=request.admission_id,
            endpoint_id=request.endpoint_id,
            generation=request.generation,
            previous_generation=request.previous_generation,
            final_sequence=request.final_sequence,
            fenced_through_sequence=request.fenced_through_sequence,
        )

    def for_recovery_completion(self, request, receipt, *, purpose, verification_time):
        return ReceiptTrustContext(
            consistency_domain_id=request.consistency_domain_id,
            authority_epoch=request.authority_epoch,
            operation_id=request.operation_id,
            expected_receipt_kind=TrustedReceiptKind.RECOVERY_COMPLETED,
            canonical_request_reference=(
                f"test-canonical:{request.operation_id}:{receipt.receipt_id}"
            ),
            trust_policy_version="test-policy-v1",
            verification_time=verification_time,
            purpose=purpose,
            expected_receipt_id=receipt.receipt_id,
            generation=request.generation,
            affected_admission_ids=request.affected_admission_ids,
            route_ids=request.route_ids,
        )
