"""Acceptance tests C65-C84 for the pure ME-03C journal reducer."""
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
from atlas.memory.journal import (
    ConsistencyPosition,
    ConsistencyRecordKind,
    ConsistencyRecoveryState,
    ConsistencyTransition,
    JournalEntry,
)
from atlas.memory.journal_reducer import ConsistencyJournalReducer

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
DOMAIN = "memory-domain-me03c"
MEMORY = "018bcfe5-7b3a-7cc2-98c4-dc0c0c074101"
VERSION = "018bcfe5-7b3a-7cc2-98c4-dc0c0c074102"
RECORDS = tuple(
    f"018bcfe5-7b3a-7cc2-98c4-dc0c0c074{n:03d}" for n in range(103, 160)
)


def read_admitted(
    record_id=RECORDS[0],
    admission_id="admission-1",
    memory_id=MEMORY,
    generation=1,
    routes=frozenset({"assistant-response", "api-response"}),
    identity_revision=1,
):
    return ConsistencyTransition(
        record_id=record_id,
        schema_version=1,
        record_kind=ConsistencyRecordKind.READ_ADMITTED,
        operation_id=f"read:{admission_id}",
        occurred_at=NOW,
        request_id=f"request:{admission_id}",
        actor_identity_id="identity-1",
        owner_id="owner-1",
        memory_id=memory_id,
        version_id=VERSION,
        snapshot_id=f"snapshot:{admission_id}",
        revisions=AuthorizationRevisionSet(
            memory_revision=AuthorityRevision(AuthorityKind.MEMORY, memory_id, 1),
            version_revision=AuthorityRevision(AuthorityKind.MEMORY_VERSION, VERSION, 1),
            identity_revision=AuthorityRevision(
                AuthorityKind.IDENTITY, "identity-1", identity_revision
            ),
        ),
        admission_id=admission_id,
        generation=generation,
        route_ids=routes,
    )


def activated(record_id, admission_id="admission-1", generation=1):
    return ConsistencyTransition(
        record_id=record_id,
        schema_version=1,
        record_kind=ConsistencyRecordKind.READ_ACTIVATED,
        operation_id=f"read:{admission_id}",
        occurred_at=NOW,
        admission_id=admission_id,
        generation=generation,
    )


def egress(
    record_id,
    sequence,
    endpoint="assistant-response",
    admission_id="admission-1",
    generation=1,
    emission_id=None,
    receipt_id=None,
    operation_id=None,
):
    return ConsistencyTransition(
        record_id=record_id,
        schema_version=1,
        record_kind=ConsistencyRecordKind.EGRESS_COMMITTED,
        operation_id=operation_id or f"read:{admission_id}",
        occurred_at=NOW,
        admission_id=admission_id,
        endpoint_id=endpoint,
        generation=generation,
        emission_id=emission_id or f"emission-{sequence}",
        emission_sequence=sequence,
        receipt_id=receipt_id or f"egress-receipt-{sequence}",
    )


def endpoint_completed(
    record_id,
    endpoint="assistant-response",
    final_sequence=0,
    admission_id="admission-1",
    generation=1,
    operation_id=None,
    receipt_id="completion-receipt",
):
    return ConsistencyTransition(
        record_id=record_id,
        schema_version=1,
        record_kind=ConsistencyRecordKind.ENDPOINT_COMPLETED,
        operation_id=operation_id or f"read:{admission_id}",
        occurred_at=NOW,
        admission_id=admission_id,
        endpoint_id=endpoint,
        generation=generation,
        receipt_id=receipt_id,
        final_sequence=final_sequence,
    )


def endpoint_fenced(
    record_id,
    operation_id,
    generation=2,
    endpoint="assistant-response",
    admission_id="admission-1",
    receipt_id="fence-receipt",
):
    return ConsistencyTransition(
        record_id=record_id,
        schema_version=1,
        record_kind=ConsistencyRecordKind.ENDPOINT_FENCED,
        operation_id=operation_id,
        occurred_at=NOW,
        admission_id=admission_id,
        endpoint_id=endpoint,
        generation=generation,
        receipt_id=receipt_id,
    )


def admission_reconciled(
    record_id,
    operation_id="read:admission-1",
    generation=1,
    terminal=ReadAdmissionStatus.COMPLETED,
    admission_id="admission-1",
    receipt_id="terminal-receipt",
):
    return ConsistencyTransition(
        record_id=record_id,
        schema_version=1,
        record_kind=ConsistencyRecordKind.ADMISSION_RECONCILED,
        operation_id=operation_id,
        occurred_at=NOW,
        admission_id=admission_id,
        generation=generation,
        receipt_id=receipt_id,
        admission_terminal_status=terminal,
    )


def forget_closed(
    record_id,
    operation_id="forget:op-1",
    memory_id=MEMORY,
    generation=2,
    affected=frozenset(),
    routes=frozenset(),
):
    return ConsistencyTransition(
        record_id=record_id,
        schema_version=1,
        record_kind=ConsistencyRecordKind.FORGET_CLOSED,
        operation_id=operation_id,
        occurred_at=NOW,
        idempotency_key=f"idempotency:{operation_id}",
        request_id=f"request:{operation_id}",
        actor_identity_id="owner-identity",
        subject_user_id="owner-1",
        owner_id="owner-1",
        memory_id=memory_id,
        generation=generation,
        proof_reference="verified-proof-reference",
        affected_admission_ids=affected,
        route_ids=routes,
    )


def forget_suppressed(record_id, closure):
    return ConsistencyTransition(
        record_id=record_id,
        schema_version=1,
        record_kind=ConsistencyRecordKind.FORGET_SUPPRESSED,
        operation_id=closure.operation_id,
        occurred_at=NOW,
        memory_id=closure.memory_id,
        generation=closure.generation,
        affected_admission_ids=closure.affected_admission_ids,
        route_ids=closure.route_ids,
    )


def invalidation_closed(
    record_id,
    affected=frozenset({"admission-1"}),
    routes=frozenset({"assistant-response", "api-response"}),
):
    return ConsistencyTransition(
        record_id=record_id,
        schema_version=1,
        record_kind=ConsistencyRecordKind.INVALIDATION_CLOSED,
        operation_id="invalidation-1",
        occurred_at=NOW,
        authority_kind=AuthorityKind.IDENTITY,
        authority_id="identity-1",
        generation=2,
        previous_revision=1,
        new_revision=2,
        affected_admission_ids=affected,
        route_ids=routes,
    )


def invalidation_reconciled(record_id, closure):
    return ConsistencyTransition(
        record_id=record_id,
        schema_version=1,
        record_kind=ConsistencyRecordKind.INVALIDATION_RECONCILED,
        operation_id=closure.operation_id,
        occurred_at=NOW,
        authority_kind=closure.authority_kind,
        authority_id=closure.authority_id,
        generation=closure.generation,
        affected_admission_ids=closure.affected_admission_ids,
        route_ids=closure.route_ids,
    )


def recovery(transitions):
    entries = tuple(
        JournalEntry(
            ConsistencyPosition(DOMAIN, 1, index),
            transition,
        )
        for index, transition in enumerate(transitions, start=1)
    )
    return ConsistencyRecoveryState(
        domain_id=DOMAIN,
        authority_epoch=1,
        checkpoint=None,
        entries=entries,
        head_sequence=len(entries),
        continuity_reference="opaque-continuity-reference",
    )


class ConsistencyJournalReducerTests(unittest.TestCase):
    def setUp(self):
        self.reducer = ConsistencyJournalReducer()

    def test_c66_read_activation_without_admission_is_rejected(self):
        with self.assertRaises(ContractError):
            self.reducer.reduce(recovery([activated(RECORDS[0])]))

    def test_c67_duplicate_admission_is_rejected(self):
        first = read_admitted()
        second = replace(first, record_id=RECORDS[1])
        with self.assertRaises(ContractError):
            self.reducer.reduce(recovery([first, second]))

    def test_c68_egress_for_unregistered_endpoint_is_rejected(self):
        with self.assertRaises(ContractError):
            self.reducer.reduce(recovery([
                read_admitted(routes=frozenset({"assistant-response"})),
                egress(RECORDS[1], 1, endpoint="api-response"),
            ]))

    def test_c69_egress_after_endpoint_completion_is_rejected(self):
        with self.assertRaises(ContractError):
            self.reducer.reduce(recovery([
                read_admitted(routes=frozenset({"assistant-response"})),
                endpoint_completed(RECORDS[1]),
                egress(RECORDS[2], 1),
            ]))

    def test_c70_duplicate_emission_sequence_is_rejected(self):
        with self.assertRaises(ContractError):
            self.reducer.reduce(recovery([
                read_admitted(routes=frozenset({"assistant-response"})),
                egress(RECORDS[1], 1),
                egress(RECORDS[2], 1, emission_id="another-emission", receipt_id="another-receipt"),
            ]))

    def test_c71_completion_before_last_committed_sequence_is_rejected(self):
        with self.assertRaises(ContractError):
            self.reducer.reduce(recovery([
                read_admitted(routes=frozenset({"assistant-response"})),
                egress(RECORDS[1], 2),
                endpoint_completed(RECORDS[2], final_sequence=1),
            ]))

    def test_c72_admission_reconciliation_before_all_endpoints_is_rejected(self):
        with self.assertRaises(ContractError):
            self.reducer.reduce(recovery([
                read_admitted(),
                endpoint_completed(RECORDS[1], endpoint="assistant-response"),
                admission_reconciled(RECORDS[2]),
            ]))

    def test_c73_forget_close_must_capture_every_prior_nonterminal_admission(self):
        with self.assertRaises(ContractError):
            self.reducer.reduce(recovery([
                read_admitted(),
                forget_closed(RECORDS[1], affected=frozenset(), routes=frozenset()),
            ]))

    def test_c74_read_admission_after_forget_close_is_rejected(self):
        closure = forget_closed(RECORDS[1])
        with self.assertRaises(ContractError):
            self.reducer.reduce(recovery([closure, read_admitted(RECORDS[2])]))

    def test_c75_forget_suppression_waits_for_all_affected_admissions(self):
        admission = read_admitted(routes=frozenset({"assistant-response"}))
        closure = forget_closed(
            RECORDS[1],
            affected=frozenset({"admission-1"}),
            routes=frozenset({"assistant-response"}),
        )
        with self.assertRaises(ContractError):
            self.reducer.reduce(recovery([admission, closure, forget_suppressed(RECORDS[2], closure)]))

    def test_c76_invalidation_requires_exact_affected_inventory(self):
        with self.assertRaises(ContractError):
            self.reducer.reduce(recovery([
                read_admitted(),
                invalidation_closed(RECORDS[1], affected=frozenset(), routes=frozenset()),
            ]))

    def test_c77_invalidation_reconciliation_waits_for_endpoints(self):
        admission = read_admitted(routes=frozenset({"assistant-response"}))
        closure = invalidation_closed(
            RECORDS[1],
            affected=frozenset({"admission-1"}),
            routes=frozenset({"assistant-response"}),
        )
        with self.assertRaises(ContractError):
            self.reducer.reduce(recovery([
                admission, closure, invalidation_reconciled(RECORDS[2], closure)
            ]))

    def test_c78_identical_receipt_replay_as_second_record_is_rejected(self):
        with self.assertRaises(ContractError):
            self.reducer.reduce(recovery([
                read_admitted(routes=frozenset({"assistant-response"})),
                egress(RECORDS[1], 1, receipt_id="same-receipt"),
                egress(RECORDS[2], 2, receipt_id="same-receipt"),
            ]))

    def test_c79_receipt_cannot_be_reused_for_another_fact(self):
        with self.assertRaises(ContractError):
            self.reducer.reduce(recovery([
                read_admitted(routes=frozenset({"assistant-response"})),
                egress(RECORDS[1], 1, receipt_id="reused-receipt"),
                endpoint_completed(RECORDS[2], final_sequence=1, receipt_id="reused-receipt"),
            ]))

    def test_c80_checkpoint_must_match_recovery_domain_and_epoch(self):
        from atlas.memory.journal import ConsistencyCheckpoint
        checkpoint = ConsistencyCheckpoint(
            checkpoint_id=RECORDS[0],
            position=ConsistencyPosition("other-domain", 1, 0),
            state_reference="opaque-state",
            integrity_reference="opaque-integrity",
            created_at=NOW,
        )
        with self.assertRaises(ContractError):
            ConsistencyRecoveryState(
                domain_id=DOMAIN,
                authority_epoch=1,
                checkpoint=checkpoint,
                entries=(),
                head_sequence=0,
                continuity_reference="opaque-continuity",
            )

    def test_c81_opaque_continuity_reference_does_not_claim_verification(self):
        projection = self.reducer.reduce(recovery([read_admitted()]))
        self.assertEqual(projection.head_sequence, 1)
        self.assertFalse(hasattr(projection, "continuity_verified"))

    def test_c82_unknown_schema_version_is_rejected_before_reduction(self):
        with self.assertRaises(ContractError):
            replace(read_admitted(), schema_version=2)

    def test_c83_admission_cannot_be_reconciled_twice(self):
        with self.assertRaises(ContractError):
            self.reducer.reduce(recovery([
                read_admitted(routes=frozenset({"assistant-response"})),
                endpoint_completed(RECORDS[1]),
                admission_reconciled(RECORDS[2]),
                admission_reconciled(
                    RECORDS[3], terminal=ReadAdmissionStatus.CANCELLED,
                    receipt_id="second-terminal-receipt",
                ),
            ]))

    def test_c84_fence_must_use_the_generation_of_the_exact_closure(self):
        admission = read_admitted(routes=frozenset({"assistant-response"}))
        closure = forget_closed(
            RECORDS[1],
            affected=frozenset({"admission-1"}),
            routes=frozenset({"assistant-response"}),
        )
        wrong_fence = endpoint_fenced(
            RECORDS[2], closure.operation_id, generation=1
        )
        with self.assertRaises(ContractError):
            self.reducer.reduce(recovery([admission, closure, wrong_fence]))


if __name__ == "__main__":
    unittest.main()
