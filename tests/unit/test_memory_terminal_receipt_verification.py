"""G01-G15 acceptance tests for terminal receipt verification."""
import unittest
from dataclasses import replace
from datetime import datetime, timezone

from atlas.core.errors import ContractError
from atlas.memory.consistency import (
    AuthorityKind,
    AuthorityRevision,
    AuthorizationRevisionSet,
    ReadAdmissionStatus,
)
from atlas.memory.journal_reducer import (
    AdmissionProjection,
    EndpointProjection,
    EndpointProjectionStatus,
)
from atlas.memory.models import MemoryScopeKind
from atlas.memory.receipt_verification import (
    ReceiptVerificationResult,
    ReceiptVerificationStatus,
    TerminalReceiptKind,
    TerminalReceiptVerificationRequest,
    VerifiedTerminalReceipt,
    match_verified_receipt,
)
from atlas.memory.terminal_recovery import verify_terminal_admission_projection

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
MEMORY = "018bcfe5-7b3a-7cc2-98c4-dc0c0c074401"
VERSION = "018bcfe5-7b3a-7cc2-98c4-dc0c0c074402"


def endpoint(endpoint_id, status, receipt_id, operation_id, generation, sequence=0):
    return EndpointProjection(
        endpoint_id=endpoint_id,
        last_emission_sequence=sequence,
        status=status,
        receipt_ids=frozenset({receipt_id}),
        terminal_receipt_id=receipt_id,
        terminal_operation_id=operation_id,
        terminal_generation=generation,
        final_sequence=sequence if status is EndpointProjectionStatus.COMPLETED else None,
    )


def admission(status=ReadAdmissionStatus.COMPLETED, recoverable=True):
    if status is ReadAdmissionStatus.COMPLETED:
        endpoints = (
            endpoint("assistant-response", EndpointProjectionStatus.COMPLETED,
                     "receipt-assistant", "read:admission-1", 1, 2),
            endpoint("api-response", EndpointProjectionStatus.COMPLETED,
                     "receipt-api", "read:admission-1", 1, 0),
        )
        terminal_operation = "read:admission-1"
    elif status is ReadAdmissionStatus.CANCELLED:
        endpoints = (
            endpoint("assistant-response", EndpointProjectionStatus.COMPLETED,
                     "receipt-assistant", "read:admission-1", 1, 2),
            endpoint("api-response", EndpointProjectionStatus.FENCED,
                     "receipt-api-fence", "forget:op-1", 2, 0),
        )
        terminal_operation = "forget:op-1"
    else:
        endpoints = (
            endpoint("assistant-response", EndpointProjectionStatus.OPEN,
                     "unused", "read:admission-1", 1, 0),
        )
        terminal_operation = None
    return AdmissionProjection(
        admission_id="admission-1",
        operation_id="read:admission-1",
        memory_id=MEMORY,
        version_id=VERSION,
        snapshot_id="snapshot-1",
        owner_id="owner-1",
        scope_kind=MemoryScopeKind.PRIVATE,
        scope_project_id=None,
        admitted_at=NOW,
        recoverable=recoverable,
        generation=1,
        revisions=AuthorizationRevisionSet(
            memory_revision=AuthorityRevision(AuthorityKind.MEMORY, MEMORY, 1),
            version_revision=AuthorityRevision(AuthorityKind.MEMORY_VERSION, VERSION, 1),
            identity_revision=AuthorityRevision(AuthorityKind.IDENTITY, "identity-1", 1),
        ),
        route_ids=frozenset(item.endpoint_id for item in endpoints),
        status=status,
        terminal_receipt_id="receipt-admission" if terminal_operation else None,
        terminal_operation_id=terminal_operation,
        terminal_generation=1 if terminal_operation else None,
        endpoints=endpoints,
    )


class FakeVerifier:
    def __init__(self, status=ReceiptVerificationStatus.VERIFIED,
                 mismatch_field=None, raises=False):
        self.status = status
        self.mismatch_field = mismatch_field
        self.raises = raises
        self.requests = []

    def verify_terminal_receipt(self, request):
        self.requests.append(request)
        if self.raises:
            raise TimeoutError("verifier unavailable")
        if self.status is not ReceiptVerificationStatus.VERIFIED:
            return ReceiptVerificationResult(self.status)
        values = {
            "verification_id": f"verification-{len(self.requests)}",
            "issuer_id": "trusted-endpoint-or-consistency-authority",
            "verified_at": NOW,
            "consistency_domain_id": request.consistency_domain_id,
            "authority_epoch": request.authority_epoch,
            "operation_id": request.operation_id,
            "admission_id": request.admission_id,
            "receipt_id": request.receipt_id,
            "kind": request.kind,
            "generation": request.generation,
            "endpoint_id": request.endpoint_id,
            "previous_generation": request.previous_generation,
            "final_sequence": request.final_sequence,
        }
        if self.mismatch_field:
            values[self.mismatch_field] = "mismatched-value"
        verified = VerifiedTerminalReceipt(**values)
        return ReceiptVerificationResult(
            ReceiptVerificationStatus.VERIFIED, verified
        )


class TerminalReceiptVerificationTests(unittest.TestCase):
    def test_exact_completed_endpoint_and_admission_receipts_are_accepted(self):
        verifier = FakeVerifier()
        result = verify_terminal_admission_projection(
            admission(), "consistency-domain", 7, verifier
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.terminal_status, ReadAdmissionStatus.COMPLETED)
        self.assertEqual(len(result.endpoint_receipts), 2)
        self.assertEqual(len(verifier.requests), 3)
        self.assertIs(
            verifier.requests[0].kind, TerminalReceiptKind.ENDPOINT_COMPLETED
        )
        self.assertIs(
            verifier.requests[-1].kind, TerminalReceiptKind.ADMISSION_COMPLETED
        )

    def test_exact_fence_receipt_binds_old_and_new_generation(self):
        verifier = FakeVerifier()
        result = verify_terminal_admission_projection(
            admission(ReadAdmissionStatus.CANCELLED),
            "consistency-domain", 7, verifier
        )
        self.assertIsNotNone(result)
        fence = next(
            request for request in verifier.requests
            if request.kind is TerminalReceiptKind.ENDPOINT_FENCED
        )
        self.assertEqual(fence.previous_generation, 1)
        self.assertEqual(fence.generation, 2)
        self.assertIs(
            verifier.requests[-1].kind, TerminalReceiptKind.ADMISSION_CANCELLED
        )

    def test_receipt_id_without_independent_verification_is_insufficient(self):
        verifier = FakeVerifier(ReceiptVerificationStatus.UNAVAILABLE)
        self.assertIsNone(verify_terminal_admission_projection(
            admission(), "consistency-domain", 7, verifier
        ))

    def test_rejected_receipt_fails_closed(self):
        verifier = FakeVerifier(ReceiptVerificationStatus.REJECTED)
        self.assertIsNone(verify_terminal_admission_projection(
            admission(), "consistency-domain", 7, verifier
        ))

    def test_verifier_exception_fails_closed(self):
        verifier = FakeVerifier(raises=True)
        self.assertIsNone(verify_terminal_admission_projection(
            admission(), "consistency-domain", 7, verifier
        ))

    def test_wrong_receipt_binding_fails_closed(self):
        verifier = FakeVerifier(mismatch_field="consistency_domain_id")
        self.assertIsNone(verify_terminal_admission_projection(
            admission(), "consistency-domain", 7, verifier
        ))

    def test_wrong_operation_binding_fails_closed(self):
        verifier = FakeVerifier(mismatch_field="operation_id")
        self.assertIsNone(verify_terminal_admission_projection(
            admission(), "consistency-domain", 7, verifier
        ))

    def test_wrong_admission_binding_fails_closed(self):
        verifier = FakeVerifier(mismatch_field="admission_id")
        self.assertIsNone(verify_terminal_admission_projection(
            admission(), "consistency-domain", 7, verifier
        ))

    def test_wrong_endpoint_binding_fails_closed(self):
        verifier = FakeVerifier(mismatch_field="endpoint_id")
        self.assertIsNone(verify_terminal_admission_projection(
            admission(), "consistency-domain", 7, verifier
        ))

    def test_wrong_generation_binding_fails_closed(self):
        verifier = FakeVerifier(mismatch_field="generation")
        self.assertIsNone(verify_terminal_admission_projection(
            admission(), "consistency-domain", 7, verifier
        ))

    def test_missing_verifier_fails_closed(self):
        self.assertIsNone(verify_terminal_admission_projection(
            admission(), "consistency-domain", 7, object()
        ))

    def test_missing_endpoint_receipt_prevents_terminal_recovery(self):
        item = admission()
        endpoints = (replace(item.endpoints[0], terminal_receipt_id=None), item.endpoints[1])
        self.assertIsNone(verify_terminal_admission_projection(
            replace(item, endpoints=endpoints), "consistency-domain", 7, FakeVerifier()
        ))

    def test_missing_admission_receipt_prevents_terminal_recovery(self):
        item = replace(admission(), terminal_receipt_id=None)
        self.assertIsNone(verify_terminal_admission_projection(
            item, "consistency-domain", 7, FakeVerifier()
        ))

    def test_contradictory_endpoint_state_prevents_completed_recovery(self):
        item = admission()
        endpoints = (
            item.endpoints[0],
            replace(item.endpoints[1], status=EndpointProjectionStatus.FENCED,
                    terminal_generation=2, terminal_operation_id="forget:op-1",
                    final_sequence=None),
        )
        self.assertIsNone(verify_terminal_admission_projection(
            replace(item, endpoints=endpoints), "consistency-domain", 7, FakeVerifier()
        ))

    def test_nonterminal_admission_cannot_be_terminal_restored(self):
        self.assertIsNone(verify_terminal_admission_projection(
            admission(ReadAdmissionStatus.UNRESOLVED),
            "consistency-domain", 7, FakeVerifier()
        ))

    def test_legacy_v1_projection_cannot_be_terminal_restored(self):
        self.assertIsNone(verify_terminal_admission_projection(
            admission(recoverable=False),
            "consistency-domain", 7, FakeVerifier()
        ))

    def test_endpoint_inventory_must_exactly_match_route_inventory(self):
        item = admission()
        self.assertIsNone(verify_terminal_admission_projection(
            replace(item, endpoints=item.endpoints[:1]),
            "consistency-domain", 7, FakeVerifier()
        ))

    def test_completion_sequence_cannot_precede_committed_emission(self):
        item = admission()
        endpoint_item = replace(item.endpoints[0], final_sequence=1)
        self.assertIsNone(verify_terminal_admission_projection(
            replace(item, endpoints=(endpoint_item, item.endpoints[1])),
            "consistency-domain", 7, FakeVerifier()
        ))

    def test_request_rejects_fence_without_generation_advance(self):
        with self.assertRaises(ContractError):
            TerminalReceiptVerificationRequest(
                consistency_domain_id="domain",
                authority_epoch=1,
                operation_id="forget:op",
                admission_id="admission-1",
                receipt_id="receipt",
                kind=TerminalReceiptKind.ENDPOINT_FENCED,
                generation=1,
                endpoint_id="endpoint",
                previous_generation=1,
            )

    def test_verified_result_must_match_every_request_field(self):
        request = TerminalReceiptVerificationRequest(
            consistency_domain_id="domain",
            authority_epoch=1,
            operation_id="read:admission-1",
            admission_id="admission-1",
            receipt_id="receipt",
            kind=TerminalReceiptKind.ENDPOINT_COMPLETED,
            generation=1,
            endpoint_id="assistant-response",
            final_sequence=2,
        )
        verifier = FakeVerifier(mismatch_field="final_sequence")
        result = verifier.verify_terminal_receipt(request)
        self.assertIsNone(match_verified_receipt(request, result))

    def test_verified_metadata_is_not_a_content_capability_or_authorization(self):
        result = verify_terminal_admission_projection(
            admission(), "consistency-domain", 7, FakeVerifier()
        )
        self.assertIsNotNone(result)
        self.assertNotIn("read_id", result.__dataclass_fields__)
        self.assertNotIn("payload", result.__dataclass_fields__)
        self.assertNotIn("content", result.__dataclass_fields__)


if __name__ == "__main__":
    unittest.main()
