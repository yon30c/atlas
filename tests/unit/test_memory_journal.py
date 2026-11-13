"""Pruebas puras del sobre y posiciones del journal de consistencia ME-03."""
import unittest
from datetime import datetime, timezone

from atlas.core.errors import ContractError
from atlas.memory.consistency import (
    AuthorityKind,
    AuthorityRevision,
    AuthorizationRevisionSet,
)
from atlas.memory.journal import (
    ConsistencyCheckpoint,
    ConsistencyPosition,
    ConsistencyRecordKind,
    ConsistencyRecoveryState,
    ConsistencyTransition,
    JournalCommit,
    JournalEntry,
)

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
DOMAIN = "memory-domain-1"
MEMORY_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a11"
VERSION_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a12"
RECORD_1 = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a13"
RECORD_2 = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a14"
CHECKPOINT_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a15"


def read_admitted(record_id=RECORD_1):
    return ConsistencyTransition(
        record_id=record_id,
        schema_version=1,
        record_kind=ConsistencyRecordKind.READ_ADMITTED,
        operation_id="read:admission-1",
        occurred_at=NOW,
        memory_id=MEMORY_ID,
        version_id=VERSION_ID,
        snapshot_id="snapshot-1",
        actor_identity_id="identity-1",
        revisions=AuthorizationRevisionSet(
            memory_revision=AuthorityRevision(AuthorityKind.MEMORY, MEMORY_ID, 1),
            version_revision=AuthorityRevision(AuthorityKind.MEMORY_VERSION, VERSION_ID, 1),
            identity_revision=AuthorityRevision(AuthorityKind.IDENTITY, "identity-1", 1),
        ),
        admission_id="admission-1",
        generation=1,
        route_ids=frozenset({"assistant-response", "api-response"}),
    )


def position(sequence, domain=DOMAIN, epoch=1):
    return ConsistencyPosition(domain, epoch, sequence)


class ConsistencyJournalModelTests(unittest.TestCase):
    def test_position_allows_genesis_sequence_zero(self):
        self.assertEqual(position(0).sequence, 0)

    def test_position_rejects_boolean_or_negative_sequence(self):
        with self.assertRaises(ContractError):
            position(True)
        with self.assertRaises(ContractError):
            position(-1)

    def test_read_admitted_requires_exact_target_and_route(self):
        item = read_admitted()
        self.assertEqual(item.memory_id, MEMORY_ID)
        self.assertEqual(item.route_ids, frozenset({"assistant-response", "api-response"}))
        with self.assertRaises(ContractError):
            ConsistencyTransition(
                record_id=RECORD_2,
                schema_version=1,
                record_kind=ConsistencyRecordKind.READ_ADMITTED,
                operation_id="read:admission-2",
                occurred_at=NOW,
                memory_id=MEMORY_ID,
                version_id=VERSION_ID,
                snapshot_id="snapshot-2",
                actor_identity_id="identity-1",
                revisions=AuthorizationRevisionSet(
                    memory_revision=AuthorityRevision(AuthorityKind.MEMORY, MEMORY_ID, 1),
                    version_revision=AuthorityRevision(AuthorityKind.MEMORY_VERSION, VERSION_ID, 1),
                    identity_revision=AuthorityRevision(AuthorityKind.IDENTITY, "identity-1", 1),
                ),
                admission_id="admission-2",
                generation=1,
            )

    def test_forget_closed_allows_empty_prior_admissions_and_routes(self):
        item = ConsistencyTransition(
            record_id=RECORD_2,
            schema_version=1,
            record_kind=ConsistencyRecordKind.FORGET_CLOSED,
            operation_id="forget:op-1",
            occurred_at=NOW,
            idempotency_key="forget-key-1",
            request_id="forget-request-1",
            actor_identity_id="owner-identity-1",
            subject_user_id="owner-user-1",
            owner_id="owner-user-1",
            memory_id=MEMORY_ID,
            generation=2,
            proof_reference="owner-proof-receipt-1",
        )
        self.assertFalse(item.route_ids)
        self.assertFalse(item.affected_admission_ids)

    def test_forget_closed_rejects_subject_that_is_not_canonical_owner(self):
        with self.assertRaises(ContractError):
            ConsistencyTransition(
                record_id=RECORD_2,
                schema_version=1,
                record_kind=ConsistencyRecordKind.FORGET_CLOSED,
                operation_id="forget:op-mismatch",
                occurred_at=NOW,
                idempotency_key="forget-key-mismatch",
                request_id="forget-request-mismatch",
                actor_identity_id="owner-identity-1",
                subject_user_id="another-user",
                owner_id="owner-user-1",
                memory_id=MEMORY_ID,
                generation=2,
                proof_reference="owner-proof-receipt-mismatch",
            )

    def test_forget_closed_requires_owner_proof_reference_and_idempotency(self):
        with self.assertRaises(ContractError):
            ConsistencyTransition(
                record_id=RECORD_2,
                schema_version=1,
                record_kind=ConsistencyRecordKind.FORGET_CLOSED,
                operation_id="forget:op-2",
                occurred_at=NOW,
                memory_id=MEMORY_ID,
                generation=2,
            )

    def test_egress_commit_requires_durable_endpoint_receipt(self):
        with self.assertRaises(ContractError):
            ConsistencyTransition(
                record_id=RECORD_2,
                schema_version=1,
                record_kind=ConsistencyRecordKind.EGRESS_COMMITTED,
                operation_id="read:admission-1",
                occurred_at=NOW,
                admission_id="admission-1",
                endpoint_id="assistant-response",
                generation=1,
                emission_id="emit-1",
                emission_sequence=1,
            )

    def test_transition_rejects_content_like_untyped_fields(self):
        with self.assertRaises(TypeError):
            ConsistencyTransition(
                record_id=RECORD_2,
                schema_version=1,
                record_kind=ConsistencyRecordKind.READ_ACTIVATED,
                operation_id="read:admission-1",
                occurred_at=NOW,
                admission_id="admission-1",
                generation=1,
                payload="must-not-be-accepted",
            )

    def test_read_admitted_requires_revision_ids_to_match_exact_resources(self):
        with self.assertRaises(ContractError):
            ConsistencyTransition(
                record_id=RECORD_2,
                schema_version=1,
                record_kind=ConsistencyRecordKind.READ_ADMITTED,
                operation_id="read:admission-2",
                occurred_at=NOW,
                memory_id=MEMORY_ID,
                version_id=VERSION_ID,
                snapshot_id="snapshot-2",
                actor_identity_id="another-identity",
                revisions=AuthorizationRevisionSet(
                    memory_revision=AuthorityRevision(AuthorityKind.MEMORY, MEMORY_ID, 1),
                    version_revision=AuthorityRevision(AuthorityKind.MEMORY_VERSION, VERSION_ID, 1),
                    identity_revision=AuthorityRevision(AuthorityKind.IDENTITY, "identity-1", 1),
                ),
                admission_id="admission-2",
                generation=1,
                route_ids=frozenset({"assistant-response"}),
            )

    def test_endpoint_completion_allows_empty_final_sequence(self):
        item = ConsistencyTransition(
            record_id=RECORD_2,
            schema_version=1,
            record_kind=ConsistencyRecordKind.ENDPOINT_COMPLETED,
            operation_id="read:admission-empty",
            occurred_at=NOW,
            admission_id="admission-empty",
            endpoint_id="assistant-response",
            generation=1,
            receipt_id="completion-receipt-1",
            final_sequence=0,
        )
        self.assertEqual(item.final_sequence, 0)

    def test_forget_closed_rejects_route_and_admission_inventory_mismatch(self):
        with self.assertRaises(ContractError):
            ConsistencyTransition(
                record_id=RECORD_2,
                schema_version=1,
                record_kind=ConsistencyRecordKind.FORGET_CLOSED,
                operation_id="forget:op-inventory",
                occurred_at=NOW,
                idempotency_key="forget-key-inventory",
                request_id="forget-request-inventory",
                actor_identity_id="owner-identity-1",
                subject_user_id="owner-user-1",
                owner_id="owner-user-1",
                memory_id=MEMORY_ID,
                generation=2,
                proof_reference="owner-proof-receipt-inventory",
                affected_admission_ids=frozenset({"admission-1"}),
            )

    def test_checkpoint_transition_requires_opaque_checkpoint_reference(self):
        with self.assertRaises(ContractError):
            ConsistencyTransition(
                record_id=RECORD_2,
                schema_version=1,
                record_kind=ConsistencyRecordKind.CHECKPOINT_COMMITTED,
                operation_id="checkpoint:1",
                occurred_at=NOW,
            )
        item = ConsistencyTransition(
            record_id=RECORD_2,
            schema_version=1,
            record_kind=ConsistencyRecordKind.CHECKPOINT_COMMITTED,
            operation_id="checkpoint:1",
            occurred_at=NOW,
            checkpoint_reference="opaque-checkpoint-reference",
        )
        self.assertEqual(item.checkpoint_reference, "opaque-checkpoint-reference")

    def test_transition_requires_utc_timestamp(self):
        with self.assertRaises(ContractError):
            ConsistencyTransition(
                record_id=RECORD_2,
                schema_version=1,
                record_kind=ConsistencyRecordKind.READ_ACTIVATED,
                operation_id="read:admission-1",
                occurred_at=datetime(2026, 11, 13, 12, 0),
                admission_id="admission-1",
                generation=1,
            )

    def test_journal_commit_is_bound_to_atlas_record_id(self):
        commit = JournalCommit(position(1), RECORD_1, False)
        self.assertEqual(commit.position.sequence, 1)
        with self.assertRaises(ContractError):
            JournalCommit(position(1), "not-an-atlas-id", False)

    def test_recovery_state_accepts_contiguous_entries(self):
        first = JournalEntry(position(1), read_admitted())
        second_transition = ConsistencyTransition(
            record_id=RECORD_2,
            schema_version=1,
            record_kind=ConsistencyRecordKind.READ_ACTIVATED,
            operation_id="read:admission-1",
            occurred_at=NOW,
            admission_id="admission-1",
            generation=1,
        )
        second = JournalEntry(position(2), second_transition)
        state = ConsistencyRecoveryState(
            domain_id=DOMAIN,
            authority_epoch=1,
            checkpoint=None,
            entries=(first, second),
            head_sequence=2,
            continuity_reference="trusted-watermark-1",
        )
        self.assertEqual(state.head_sequence, 2)

    def test_recovery_state_rejects_sequence_gap(self):
        entry = JournalEntry(position(2), read_admitted())
        with self.assertRaises(ContractError):
            ConsistencyRecoveryState(
                domain_id=DOMAIN,
                authority_epoch=1,
                checkpoint=None,
                entries=(entry,),
                head_sequence=2,
                continuity_reference="trusted-watermark-1",
            )

    def test_recovery_state_rejects_duplicate_record_ids(self):
        first = JournalEntry(position(1), read_admitted(RECORD_1))
        second = JournalEntry(position(2), read_admitted(RECORD_1))
        with self.assertRaises(ContractError):
            ConsistencyRecoveryState(
                domain_id=DOMAIN,
                authority_epoch=1,
                checkpoint=None,
                entries=(first, second),
                head_sequence=2,
                continuity_reference="trusted-watermark-1",
            )

    def test_recovery_state_rejects_head_mismatch(self):
        entry = JournalEntry(position(1), read_admitted())
        with self.assertRaises(ContractError):
            ConsistencyRecoveryState(
                domain_id=DOMAIN,
                authority_epoch=1,
                checkpoint=None,
                entries=(entry,),
                head_sequence=0,
                continuity_reference="trusted-watermark-1",
            )

    def test_checkpoint_allows_only_entries_after_its_position(self):
        checkpoint = ConsistencyCheckpoint(
            checkpoint_id=CHECKPOINT_ID,
            position=position(10),
            state_reference="opaque-state-reference",
            integrity_reference="trusted-integrity-reference",
            created_at=NOW,
        )
        entry = JournalEntry(position(11), read_admitted())
        state = ConsistencyRecoveryState(
            domain_id=DOMAIN,
            authority_epoch=1,
            checkpoint=checkpoint,
            entries=(entry,),
            head_sequence=11,
            continuity_reference="trusted-watermark-11",
        )
        self.assertEqual(state.checkpoint.position.sequence, 10)

    def test_recovery_state_rejects_checkpoint_from_other_epoch(self):
        checkpoint = ConsistencyCheckpoint(
            checkpoint_id=CHECKPOINT_ID,
            position=position(10, epoch=2),
            state_reference="opaque-state-reference",
            integrity_reference="trusted-integrity-reference",
            created_at=NOW,
        )
        with self.assertRaises(ContractError):
            ConsistencyRecoveryState(
                domain_id=DOMAIN,
                authority_epoch=1,
                checkpoint=checkpoint,
                entries=(),
                head_sequence=10,
                continuity_reference="trusted-watermark-10",
            )

    def test_recovery_state_rejects_entry_from_other_domain(self):
        entry = JournalEntry(position(1, domain="other-domain"), read_admitted())
        with self.assertRaises(ContractError):
            ConsistencyRecoveryState(
                domain_id=DOMAIN,
                authority_epoch=1,
                checkpoint=None,
                entries=(entry,),
                head_sequence=1,
                continuity_reference="trusted-watermark-1",
            )


if __name__ == "__main__":
    unittest.main()
