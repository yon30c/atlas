"""H01-H15 tests for unresolved admission recovery fencing."""
import unittest
from dataclasses import replace
from datetime import datetime, timezone

from atlas.core.errors import ContractError
from atlas.memory.consistency import (
    AuthorityKind,
    AuthorityRevision,
    AuthorizationRevisionSet,
    ReadAdmissionStatus,
    ReadTarget,
)
from atlas.memory.journal_reducer import (
    AdmissionProjection,
    ConsistencyProjection,
    EndpointProjection,
    EndpointProjectionStatus,
)
from atlas.memory.models import MemoryScopeKind
from atlas.memory.journal import (
    ConsistencyPosition,
    ConsistencyRecordKind,
    ConsistencyRecoveryState,
    ConsistencyTransition,
    JournalEntry,
)
from atlas.memory.journal_reducer import ConsistencyJournalReducer
from atlas.memory.receipt_verification import (
    ReceiptVerificationResult,
    ReceiptVerificationStatus,
    TerminalReceiptKind,
    VerifiedTerminalReceipt,
)
from atlas.memory.recovery import (
    RecoveryEndpointFenceReceipt,
    RecoveryFencePlan,
    build_recovery_fence_plan,
    build_recovery_fence_requests,
    execute_recovery_fencing,
)

NOW = datetime(2026, 11, 13, 18, 0, tzinfo=timezone.utc)
MEMORY = "018bcfe5-7b3a-7cc2-98c4-dc0c0c074501"
VERSION = "018bcfe5-7b3a-7cc2-98c4-dc0c0c074502"


def make_admission(
    admission_id,
    generation,
    *,
    recoverable=True,
    status=ReadAdmissionStatus.ACTIVE,
    endpoints=("assistant-response", "api-response"),
):
    endpoint_projections = tuple(
        EndpointProjection(
            endpoint_id=endpoint_id,
            last_emission_sequence=index,
            status=EndpointProjectionStatus.OPEN,
            receipt_ids=frozenset(),
        )
        for index, endpoint_id in enumerate(endpoints)
    )
    return AdmissionProjection(
        admission_id=admission_id,
        operation_id=f"read:{admission_id}",
        memory_id=MEMORY,
        version_id=VERSION,
        snapshot_id=f"snapshot:{admission_id}",
        owner_id="owner-1" if recoverable else None,
        scope_kind=MemoryScopeKind.PRIVATE if recoverable else None,
        scope_project_id=None,
        admitted_at=NOW,
        recoverable=recoverable,
        generation=generation,
        revisions=AuthorizationRevisionSet(
            memory_revision=AuthorityRevision(AuthorityKind.MEMORY, MEMORY, 1),
            version_revision=AuthorityRevision(AuthorityKind.MEMORY_VERSION, VERSION, 1),
            identity_revision=AuthorityRevision(AuthorityKind.IDENTITY, "identity-1", 1),
        ),
        route_ids=frozenset(endpoints),
        status=status,
        terminal_receipt_id=None,
        terminal_operation_id=None,
        terminal_generation=None,
        endpoints=endpoint_projections,
    )


def make_projection(*admissions):
    return ConsistencyProjection(
        domain_id="consistency-domain",
        authority_epoch=4,
        head_sequence=20,
        admissions=tuple(admissions),
        forget_closures=(),
        invalidations=(),
        idempotency_records=(),
        receipt_ids=frozenset(),
    )


class FakeEndpointFencer:
    def __init__(self, *, fail_endpoint=None, mismatch_field=None, raises=False):
        self.fail_endpoint = fail_endpoint
        self.mismatch_field = mismatch_field
        self.raises = raises
        self.requests = []

    def fence_endpoint(self, request):
        self.requests.append(request)
        if self.raises:
            raise TimeoutError("endpoint not reachable")
        if request.endpoint_id == self.fail_endpoint:
            return None
        values = {
            "operation_id": request.operation_id,
            "admission_id": request.admission_id,
            "endpoint_id": request.endpoint_id,
            "previous_generation": request.previous_generation,
            "generation": request.generation,
            "receipt_id": f"fence:{request.admission_id}:{request.endpoint_id}",
            "confirmed": True,
            "fenced_through_sequence": request.last_committed_sequence,
        }
        if self.mismatch_field:
            values[self.mismatch_field] = (
                values[self.mismatch_field] + 1
                if self.mismatch_field == "fenced_through_sequence"
                else "wrong-binding"
            )
        return RecoveryEndpointFenceReceipt(**values)


class FakeTerminalVerifier:
    def __init__(self, *, status=ReceiptVerificationStatus.VERIFIED,
                 mismatch_field=None, fail_after=None, raises=False):
        self.status = status
        self.mismatch_field = mismatch_field
        self.fail_after = fail_after
        self.raises = raises
        self.requests = []

    def verify_terminal_receipt(self, request):
        self.requests.append(request)
        if self.raises or (
            self.fail_after is not None and len(self.requests) > self.fail_after
        ):
            raise TimeoutError("verification unavailable")
        if self.status is not ReceiptVerificationStatus.VERIFIED:
            return ReceiptVerificationResult(self.status)
        values = {
            "verification_id": f"verified:{len(self.requests)}",
            "issuer_id": f"trusted:{request.endpoint_id}",
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
            "fenced_through_sequence": request.fenced_through_sequence,
        }
        if self.mismatch_field:
            values[self.mismatch_field] = "wrong-binding"
        return ReceiptVerificationResult(
            ReceiptVerificationStatus.VERIFIED,
            VerifiedTerminalReceipt(**values),
        )


class UnresolvedAdmissionRecoveryTests(unittest.TestCase):
    def test_plan_preserves_every_pending_v1_and_v2_admission(self):
        v1 = make_admission("legacy-v1", 2, recoverable=False)
        v2 = make_admission("current-v2", 3, recoverable=True)
        plan = build_recovery_fence_plan(make_projection(v1, v2), 4)
        self.assertIsNotNone(plan)
        self.assertEqual(
            {item.admission_id for item in plan.admissions},
            {"legacy-v1", "current-v2"},
        )
        legacy = next(item for item in plan.admissions if item.admission_id == "legacy-v1")
        current = next(item for item in plan.admissions if item.admission_id == "current-v2")
        self.assertFalse(legacy.recoverable)
        self.assertIsNone(legacy.target)
        self.assertTrue(current.recoverable)
        self.assertIsInstance(current.target, ReadTarget)

    def test_plan_preserves_all_routes_exactly_once(self):
        plan = build_recovery_fence_plan(
            make_projection(make_admission("read-1", 2)), 3
        )
        requests = build_recovery_fence_requests(plan)
        self.assertEqual(
            {(item.admission_id, item.endpoint_id) for item in requests},
            {
                ("read-1", "assistant-response"),
                ("read-1", "api-response"),
            },
        )

    def test_plan_captures_last_committed_sequence(self):
        plan = build_recovery_fence_plan(
            make_projection(make_admission("read-1", 2)), 3
        )
        requests = build_recovery_fence_requests(plan)
        self.assertEqual(
            {item.endpoint_id: item.last_committed_sequence for item in requests},
            {"assistant-response": 0, "api-response": 1},
        )

    def test_generation_must_exceed_every_admission_generation(self):
        projection = make_projection(
            make_admission("read-1", 2),
            make_admission("read-2", 4),
        )
        self.assertIsNone(build_recovery_fence_plan(projection, 4))
        self.assertIsNotNone(build_recovery_fence_plan(projection, 5))

    def test_plan_rejects_incomplete_endpoint_inventory(self):
        item = make_admission("read-1", 2)
        projection = replace(
            make_projection(item),
            admissions=(replace(item, endpoints=item.endpoints[:1]),),
        )
        self.assertIsNone(build_recovery_fence_plan(projection, 3))

    def test_terminal_admissions_are_not_reopened_as_unresolved(self):
        terminal = make_admission(
            "already-terminal", 2, status=ReadAdmissionStatus.CANCELLED
        )
        plan = build_recovery_fence_plan(make_projection(terminal), 3)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.admissions, ())

    def test_recovery_plan_is_metadata_only_and_not_a_read_capability(self):
        plan = build_recovery_fence_plan(
            make_projection(make_admission("read-1", 2)), 3
        )
        self.assertNotIn("read_id", plan.__dataclass_fields__)
        self.assertNotIn("content", plan.__dataclass_fields__)
        self.assertNotIn("payload", plan.__dataclass_fields__)
        self.assertNotIn("handle", plan.__dataclass_fields__)

    def test_every_endpoint_must_be_fenced_and_verified(self):
        plan = build_recovery_fence_plan(
            make_projection(make_admission("read-1", 2)), 3
        )
        fencer, verifier = FakeEndpointFencer(), FakeTerminalVerifier()
        batch = execute_recovery_fencing(plan, fencer, verifier)
        self.assertIsNotNone(batch)
        self.assertEqual(len(batch.requests), 2)
        self.assertEqual(len(batch.verified_receipts), 2)
        self.assertTrue(all(
            request.kind is TerminalReceiptKind.ENDPOINT_FENCED
            for request in verifier.requests
        ))

    def test_fencing_requests_bind_old_and_new_generation(self):
        plan = build_recovery_fence_plan(
            make_projection(make_admission("read-1", 2)), 7
        )
        fencer, verifier = FakeEndpointFencer(), FakeTerminalVerifier()
        batch = execute_recovery_fencing(plan, fencer, verifier)
        self.assertIsNotNone(batch)
        self.assertEqual(
            {(r.previous_generation, r.generation) for r in fencer.requests},
            {(2, 7)},
        )

    def test_wrong_endpoint_receipt_binding_fails_closed(self):
        plan = build_recovery_fence_plan(
            make_projection(make_admission("read-1", 2)), 3
        )
        self.assertIsNone(execute_recovery_fencing(
            plan, FakeEndpointFencer(mismatch_field="endpoint_id"),
            FakeTerminalVerifier()
        ))

    def test_unconfirmed_endpoint_fence_fails_closed(self):
        plan = build_recovery_fence_plan(
            make_projection(make_admission("read-1", 2)), 3
        )
        self.assertIsNone(execute_recovery_fencing(
            plan, FakeEndpointFencer(fail_endpoint="api-response"),
            FakeTerminalVerifier()
        ))

    def test_endpoint_timeout_fails_closed(self):
        plan = build_recovery_fence_plan(
            make_projection(make_admission("read-1", 2)), 3
        )
        self.assertIsNone(execute_recovery_fencing(
            plan, FakeEndpointFencer(raises=True), FakeTerminalVerifier()
        ))

    def test_verifier_unavailable_fails_closed(self):
        plan = build_recovery_fence_plan(
            make_projection(make_admission("read-1", 2)), 3
        )
        self.assertIsNone(execute_recovery_fencing(
            plan, FakeEndpointFencer(),
            FakeTerminalVerifier(status=ReceiptVerificationStatus.UNAVAILABLE)
        ))

    def test_verifier_rejection_fails_closed(self):
        plan = build_recovery_fence_plan(
            make_projection(make_admission("read-1", 2)), 3
        )
        self.assertIsNone(execute_recovery_fencing(
            plan, FakeEndpointFencer(),
            FakeTerminalVerifier(status=ReceiptVerificationStatus.REJECTED)
        ))

    def test_verifier_timeout_after_partial_success_returns_no_batch(self):
        plan = build_recovery_fence_plan(
            make_projection(make_admission("read-1", 2)), 3
        )
        self.assertIsNone(execute_recovery_fencing(
            plan, FakeEndpointFencer(),
            FakeTerminalVerifier(fail_after=1)
        ))

    def test_verifier_wrong_fenced_sequence_binding_fails_closed(self):
        plan = build_recovery_fence_plan(
            make_projection(make_admission("read-1", 2)), 3
        )
        self.assertIsNone(execute_recovery_fencing(
            plan, FakeEndpointFencer(),
            FakeTerminalVerifier(mismatch_field="fenced_through_sequence")
        ))

    def test_verifier_wrong_generation_binding_fails_closed(self):
        plan = build_recovery_fence_plan(
            make_projection(make_admission("read-1", 2)), 3
        )
        self.assertIsNone(execute_recovery_fencing(
            plan, FakeEndpointFencer(),
            FakeTerminalVerifier(mismatch_field="generation")
        ))

    def test_verified_batch_cannot_be_built_from_partial_receipts(self):
        plan = build_recovery_fence_plan(
            make_projection(make_admission("read-1", 2)), 3
        )
        requests = build_recovery_fence_requests(plan)
        receipt = VerifiedTerminalReceipt(
            verification_id="verification-1",
            issuer_id="trusted:assistant-response",
            verified_at=NOW,
            consistency_domain_id=plan.consistency_domain_id,
            authority_epoch=plan.authority_epoch,
            operation_id=plan.operation_id,
            admission_id=requests[0].admission_id,
            receipt_id="receipt-1",
            kind=TerminalReceiptKind.ENDPOINT_FENCED,
            generation=plan.generation,
            endpoint_id=requests[0].endpoint_id,
            previous_generation=requests[0].previous_generation,
            fenced_through_sequence=requests[0].last_committed_sequence,
        )
        with self.assertRaises(ContractError):
            from atlas.memory.recovery import VerifiedRecoveryFenceBatch
            VerifiedRecoveryFenceBatch(
                consistency_domain_id=plan.consistency_domain_id,
                authority_epoch=plan.authority_epoch,
                operation_id=plan.operation_id,
                generation=plan.generation,
                requests=requests,
                verified_receipts=(receipt,),
            )

    def test_old_generation_is_never_restored_by_recovery_plan(self):
        admission = make_admission("read-1", 2)
        plan = build_recovery_fence_plan(make_projection(admission), 3)
        self.assertIsNotNone(plan)
        self.assertGreater(plan.generation, admission.generation)
        self.assertFalse(any(
            item.generation == admission.generation
            for item in build_recovery_fence_requests(plan)
        ))



def make_recovery_journal(*, include_reconcile=True, include_egress=False):
    admission_id = "journal-recovery-admission"
    operation_id = "recovery:consistency-domain:4:5"
    routes = frozenset({"assistant-response", "api-response"})
    revisions = AuthorizationRevisionSet(
        memory_revision=AuthorityRevision(AuthorityKind.MEMORY, MEMORY, 1),
        version_revision=AuthorityRevision(AuthorityKind.MEMORY_VERSION, VERSION, 1),
        identity_revision=AuthorityRevision(AuthorityKind.IDENTITY, "identity-1", 1),
    )
    transitions = [
        ConsistencyTransition(
            record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074510",
            schema_version=2,
            record_kind=ConsistencyRecordKind.READ_ADMITTED,
            operation_id=f"read:{admission_id}",
            occurred_at=NOW,
            request_id="request-recovery",
            actor_identity_id="identity-1",
            subject_user_id="owner-1",
            owner_id="owner-1",
            memory_id=MEMORY,
            version_id=VERSION,
            snapshot_id="snapshot-recovery",
            revisions=revisions,
            admission_id=admission_id,
            generation=2,
            route_ids=routes,
            scope_kind=MemoryScopeKind.PRIVATE,
        ),
        ConsistencyTransition(
            record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074511",
            schema_version=1,
            record_kind=ConsistencyRecordKind.RECOVERY_CLOSED,
            operation_id=operation_id,
            occurred_at=NOW,
            generation=5,
            affected_admission_ids=frozenset({admission_id}),
            route_ids=routes,
        ),
    ]
    if include_egress:
        transitions.append(ConsistencyTransition(
            record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074512",
            schema_version=1,
            record_kind=ConsistencyRecordKind.EGRESS_COMMITTED,
            operation_id=f"read:{admission_id}",
            occurred_at=NOW,
            admission_id=admission_id,
            endpoint_id="assistant-response",
            generation=2,
            emission_id="stale-emission",
            emission_sequence=1,
            receipt_id="stale-egress-receipt",
        ))
    if include_reconcile:
        for index, endpoint_id in enumerate(sorted(routes), start=13):
            transitions.append(ConsistencyTransition(
                record_id=f"018bcfe5-7b3a-7cc2-98c4-dc0c0c0745{index:02x}",
                schema_version=1,
                record_kind=ConsistencyRecordKind.ENDPOINT_FENCED,
                operation_id=operation_id,
                occurred_at=NOW,
                admission_id=admission_id,
                endpoint_id=endpoint_id,
                generation=5,
                receipt_id=f"fence-receipt-{endpoint_id}",
            ))
        transitions.append(ConsistencyTransition(
            record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074515",
            schema_version=1,
            record_kind=ConsistencyRecordKind.ADMISSION_RECONCILED,
            operation_id=operation_id,
            occurred_at=NOW,
            admission_id=admission_id,
            generation=5,
            receipt_id="admission-terminal-receipt",
            admission_terminal_status=ReadAdmissionStatus.CANCELLED,
        ))
        transitions.append(ConsistencyTransition(
            record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074516",
            schema_version=1,
            record_kind=ConsistencyRecordKind.RECOVERY_RECONCILED,
            operation_id=operation_id,
            occurred_at=NOW,
            generation=5,
            receipt_id="recovery-terminal-receipt",
            affected_admission_ids=frozenset({admission_id}),
            route_ids=routes,
        ))
    entries = tuple(
        JournalEntry(
            ConsistencyPosition("consistency-domain", 4, sequence),
            transition,
        )
        for sequence, transition in enumerate(transitions, start=1)
    )
    return ConsistencyRecoveryState(
        domain_id="consistency-domain",
        authority_epoch=4,
        checkpoint=None,
        entries=entries,
        head_sequence=len(entries),
        continuity_reference="verified-chain-reference",
    )


class RecoveryJournalReducerTests(unittest.TestCase):
    def test_recovery_closed_marks_all_pending_admissions_unresolved(self):
        projection = ConsistencyJournalReducer().reduce(
            make_recovery_journal(include_reconcile=False)
        )
        self.assertIs(projection.admissions[0].status, ReadAdmissionStatus.UNRESOLVED)
        self.assertEqual(len(projection.recovery_closures), 1)
        self.assertFalse(projection.recovery_closures[0].reconciled)

    def test_egress_after_recovery_closed_is_rejected(self):
        with self.assertRaises(ContractError):
            ConsistencyJournalReducer().reduce(
                make_recovery_journal(include_reconcile=False, include_egress=True)
            )

    def test_all_endpoint_fences_reconcile_admission_and_recovery(self):
        projection = ConsistencyJournalReducer().reduce(make_recovery_journal())
        self.assertIs(projection.admissions[0].status, ReadAdmissionStatus.CANCELLED)
        self.assertTrue(projection.recovery_closures[0].reconciled)
        self.assertEqual(
            projection.recovery_closures[0].terminal_receipt_id,
            "recovery-terminal-receipt",
        )

    def test_recovery_cannot_reconcile_before_every_endpoint_is_fenced(self):
        journal = make_recovery_journal()
        transitions = tuple(
            entry.transition for entry in journal.entries
            if entry.transition.record_kind is not ConsistencyRecordKind.ENDPOINT_FENCED
            or entry.transition.endpoint_id == "assistant-response"
        )
        entries = tuple(
            JournalEntry(
                ConsistencyPosition("consistency-domain", 4, sequence),
                transition,
            )
            for sequence, transition in enumerate(transitions, start=1)
        )
        with self.assertRaises(ContractError):
            ConsistencyJournalReducer().reduce(replace(
                journal, entries=entries, head_sequence=len(entries)
            ))

    def test_recovery_close_must_cover_exact_admission_and_route_inventories(self):
        journal = make_recovery_journal(include_reconcile=False)
        transitions = list(entry.transition for entry in journal.entries)
        transitions[1] = replace(
            transitions[1], affected_admission_ids=frozenset()
        )
        entries = tuple(
            JournalEntry(
                ConsistencyPosition("consistency-domain", 4, sequence),
                transition,
            )
            for sequence, transition in enumerate(transitions, start=1)
        )
        with self.assertRaises(ContractError):
            ConsistencyJournalReducer().reduce(replace(
                journal, entries=entries, head_sequence=len(entries)
            ))

if __name__ == "__main__":
    unittest.main()
