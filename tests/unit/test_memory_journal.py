"""Pruebas puras del sobre y posiciones del journal de consistencia ME-03."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from atlas.core.errors import ContractError
from atlas.memory.consistency import (
    AuthorityKind,
    AuthorityRevision,
    AuthorizationRevisionSet,
    ReadAdmissionStatus,
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


def read_admitted(record_id=RECORD_1, idempotency_key=None, occurred_at=NOW):
    return ConsistencyTransition(
        record_id=record_id,
        schema_version=1,
        record_kind=ConsistencyRecordKind.READ_ADMITTED,
        operation_id="read:admission-1",
        occurred_at=occurred_at,
        idempotency_key=idempotency_key,
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


class InMemoryConsistencyJournalFake:
    """Fake determinista de proceso único; no demuestra durabilidad real."""

    def __init__(self, domain=DOMAIN, epoch=1):
        self.domain = domain
        self.epoch = epoch
        self.sequence = 0
        self.entries = []
        self.checkpoint = None
        self.idempotency = {}
        self.record_ids = {}

    def _position(self):
        return ConsistencyPosition(self.domain, self.epoch, self.sequence)

    @staticmethod
    def _canonical(transition):
        return replace(
            transition,
            record_id=RECORD_1,
            occurred_at=NOW,
        )

    def append_transition(self, expected_position, transition):
        if not isinstance(transition, ConsistencyTransition):
            return None
        if not isinstance(expected_position, ConsistencyPosition):
            return None
        if (
            expected_position.consistency_domain_id != self.domain
            or expected_position.authority_epoch != self.epoch
        ):
            return None

        if transition.idempotency_key is not None:
            existing = self.idempotency.get(transition.idempotency_key)
            if existing is not None:
                canonical, commit = existing
                if canonical != self._canonical(transition):
                    return None
                return replace(commit, replayed=True)

        existing_record = self.record_ids.get(transition.record_id)
        if existing_record is not None:
            return None
        if expected_position != self._position():
            return None

        self.sequence += 1
        position = self._position()
        entry = JournalEntry(position, transition)
        commit = JournalCommit(position, transition.record_id, False)
        self.entries.append(entry)
        self.record_ids[transition.record_id] = entry
        if transition.idempotency_key is not None:
            self.idempotency[transition.idempotency_key] = (
                self._canonical(transition), commit
            )
        return commit

    def load_recovery_state(self, domain_id):
        if domain_id != self.domain:
            return None
        checkpoint_sequence = (
            self.checkpoint.position.sequence if self.checkpoint else 0
        )
        entries = tuple(
            entry for entry in self.entries
            if entry.position.sequence > checkpoint_sequence
        )
        return ConsistencyRecoveryState(
            domain_id=self.domain,
            authority_epoch=self.epoch,
            checkpoint=self.checkpoint,
            entries=entries,
            head_sequence=self.sequence,
            continuity_reference="fake-only-untrusted-watermark",
        )

    def load_endpoint_receipts(self, admission_id):
        receipt_kinds = {
            ConsistencyRecordKind.EGRESS_COMMITTED,
            ConsistencyRecordKind.ENDPOINT_COMPLETED,
            ConsistencyRecordKind.ENDPOINT_FENCED,
        }
        return tuple(
            entry for entry in self.entries
            if entry.transition.admission_id == admission_id
            and entry.transition.record_kind in receipt_kinds
        )

    def commit_checkpoint(self, checkpoint, expected_position):
        if not isinstance(checkpoint, ConsistencyCheckpoint):
            return None
        existing = self.record_ids.get(checkpoint.checkpoint_id)
        if existing is not None:
            transition = existing.transition
            if (
                transition.record_kind is ConsistencyRecordKind.CHECKPOINT_COMMITTED
                and transition.checkpoint_reference == checkpoint.state_reference
                and self.checkpoint == checkpoint
            ):
                return JournalCommit(existing.position, checkpoint.checkpoint_id, True)
            return None
        if expected_position != self._position() or checkpoint.position != expected_position:
            return None
        if (
            checkpoint.position.consistency_domain_id != self.domain
            or checkpoint.position.authority_epoch != self.epoch
        ):
            return None
        transition = ConsistencyTransition(
            record_id=checkpoint.checkpoint_id,
            schema_version=1,
            record_kind=ConsistencyRecordKind.CHECKPOINT_COMMITTED,
            operation_id=f"checkpoint:{checkpoint.checkpoint_id}",
            occurred_at=checkpoint.created_at,
            checkpoint_reference=checkpoint.state_reference,
        )
        self.sequence += 1
        position = self._position()
        entry = JournalEntry(position, transition)
        self.entries.append(entry)
        self.record_ids[checkpoint.checkpoint_id] = entry
        self.checkpoint = checkpoint
        return JournalCommit(position, checkpoint.checkpoint_id, False)


class ConsistencyJournalModelTests(unittest.TestCase):


    def test_transition_rejects_fields_not_allowed_for_record_kind(self):
        with self.assertRaises(ContractError):
            replace(read_admitted(), receipt_id="not-applicable-to-read-admitted")

    def test_transition_rejects_unsupported_schema_version(self):
        # The schema is closed: unknown versions cannot enter a recovery state.
        with self.assertRaises(ContractError):
            replace(read_admitted(), schema_version=2)



    def test_invalidation_closed_requires_monotonic_revision_interval(self):
        base = dict(
            record_id=RECORD_1,
            schema_version=1,
            record_kind=ConsistencyRecordKind.INVALIDATION_CLOSED,
            operation_id="invalidation:identity-1",
            occurred_at=NOW,
            authority_kind=AuthorityKind.IDENTITY,
            authority_id="identity-1",
            generation=2,
            previous_revision=4,
            new_revision=5,
        )
        self.assertIsInstance(ConsistencyTransition(**base), ConsistencyTransition)
        with self.assertRaises(ContractError):
            ConsistencyTransition(**{**base, "new_revision": 4})
        with self.assertRaises(ContractError):
            ConsistencyTransition(**{k: v for k, v in base.items() if k != "new_revision"})

    def test_admission_reconciled_requires_explicit_terminal_outcome(self):
        base = dict(
            record_id=RECORD_1,
            schema_version=1,
            record_kind=ConsistencyRecordKind.ADMISSION_RECONCILED,
            operation_id="read:admission-1",
            occurred_at=NOW,
            admission_id="admission-1",
            generation=1,
            receipt_id="terminal-receipt-1",
        )
        with self.assertRaises(ContractError):
            ConsistencyTransition(**base)
        completed = ConsistencyTransition(
            **base, admission_terminal_status=ReadAdmissionStatus.COMPLETED
        )
        self.assertEqual(
            completed.admission_terminal_status, ReadAdmissionStatus.COMPLETED
        )
        with self.assertRaises(ContractError):
            ConsistencyTransition(
                **base, admission_terminal_status=ReadAdmissionStatus.ACTIVE
            )


    def test_fake_journal_appends_with_compare_and_swap_position(self):
        journal = InMemoryConsistencyJournalFake()
        first = journal.append_transition(position(0), read_admitted())
        self.assertEqual(first.position.sequence, 1)
        self.assertIsNone(
            journal.append_transition(position(0), read_admitted(RECORD_2))
        )
        second_transition = ConsistencyTransition(
            record_id=RECORD_2,
            schema_version=1,
            record_kind=ConsistencyRecordKind.READ_ACTIVATED,
            operation_id="read:admission-1",
            occurred_at=NOW,
            admission_id="admission-1",
            generation=1,
        )
        second = journal.append_transition(position(1), second_transition)
        self.assertEqual(second.position.sequence, 2)

    def test_fake_journal_replays_same_idempotent_request(self):
        journal = InMemoryConsistencyJournalFake()
        first_transition = read_admitted(idempotency_key="read-key-1")
        first = journal.append_transition(position(0), first_transition)
        later = ConsistencyTransition(
            record_id=RECORD_2,
            schema_version=1,
            record_kind=ConsistencyRecordKind.READ_ACTIVATED,
            operation_id="read:admission-1",
            occurred_at=NOW,
            admission_id="admission-1",
            generation=1,
        )
        journal.append_transition(first.position, later)
        retry = read_admitted(
            record_id=RECORD_2,
            idempotency_key="read-key-1",
            occurred_at=NOW + timedelta(seconds=5),
        )
        repeated = journal.append_transition(position(0), retry)
        self.assertEqual(repeated.position, first.position)
        self.assertEqual(repeated.record_id, first.record_id)
        self.assertTrue(repeated.replayed)
        self.assertEqual(len(journal.entries), 1)

    def test_fake_journal_rejects_idempotency_key_reuse_for_other_request(self):
        journal = InMemoryConsistencyJournalFake()
        journal.append_transition(
            position(0), read_admitted(idempotency_key="read-key-conflict")
        )
        changed = replace(
            read_admitted(record_id=RECORD_2, idempotency_key="read-key-conflict"),
            route_ids=frozenset({"assistant-response"}),
        )
        self.assertIsNone(journal.append_transition(position(0), changed))
        self.assertEqual(len(journal.entries), 1)

    def test_fake_journal_recovers_only_entries_after_checkpoint(self):
        journal = InMemoryConsistencyJournalFake()
        first = journal.append_transition(position(0), read_admitted())
        checkpoint = ConsistencyCheckpoint(
            checkpoint_id=CHECKPOINT_ID,
            position=first.position,
            state_reference="opaque-state-reference",
            integrity_reference="fake-integrity-reference",
            created_at=NOW,
        )
        checkpoint_commit = journal.commit_checkpoint(checkpoint, first.position)
        self.assertEqual(checkpoint_commit.position.sequence, 2)
        second_transition = ConsistencyTransition(
            record_id=RECORD_2,
            schema_version=1,
            record_kind=ConsistencyRecordKind.READ_ACTIVATED,
            operation_id="read:admission-1",
            occurred_at=NOW,
            admission_id="admission-1",
            generation=1,
        )
        journal.append_transition(checkpoint_commit.position, second_transition)
        state = journal.load_recovery_state(DOMAIN)
        self.assertEqual(state.checkpoint, checkpoint)
        self.assertEqual(len(state.entries), 2)
        self.assertEqual(state.entries[0].transition.record_kind, ConsistencyRecordKind.CHECKPOINT_COMMITTED)
        self.assertEqual(state.entries[0].position.sequence, 2)
        self.assertEqual(state.entries[1].position.sequence, 3)
        self.assertEqual(state.head_sequence, 3)

    def test_fake_journal_rejects_checkpoint_behind_current_head(self):
        journal = InMemoryConsistencyJournalFake()
        first = journal.append_transition(position(0), read_admitted())
        stale_checkpoint = ConsistencyCheckpoint(
            checkpoint_id=CHECKPOINT_ID,
            position=position(0),
            state_reference="opaque-state-reference",
            integrity_reference="fake-integrity-reference",
            created_at=NOW,
        )
        self.assertIsNone(journal.commit_checkpoint(stale_checkpoint, first.position))

    def test_fake_journal_loads_endpoint_receipts_by_exact_admission(self):
        journal = InMemoryConsistencyJournalFake()
        admitted = journal.append_transition(position(0), read_admitted())
        egress = ConsistencyTransition(
            record_id=RECORD_2,
            schema_version=1,
            record_kind=ConsistencyRecordKind.EGRESS_COMMITTED,
            operation_id="read:admission-1",
            occurred_at=NOW,
            admission_id="admission-1",
            endpoint_id="assistant-response",
            generation=1,
            emission_id="emission-1",
            emission_sequence=1,
            receipt_id="durable-egress-receipt-1",
        )
        journal.append_transition(admitted.position, egress)
        receipts = journal.load_endpoint_receipts("admission-1")
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0].transition.receipt_id, "durable-egress-receipt-1")

    def test_fake_journal_checkpoint_commit_is_idempotent(self):
        journal = InMemoryConsistencyJournalFake()
        first = journal.append_transition(position(0), read_admitted())
        checkpoint = ConsistencyCheckpoint(
            checkpoint_id=CHECKPOINT_ID,
            position=first.position,
            state_reference="opaque-state-reference",
            integrity_reference="fake-integrity-reference",
            created_at=NOW,
        )
        committed = journal.commit_checkpoint(checkpoint, first.position)
        repeated = journal.commit_checkpoint(checkpoint, first.position)
        self.assertEqual(repeated.position, committed.position)
        self.assertTrue(repeated.replayed)
        self.assertEqual(len(journal.entries), 2)

    def test_fake_journal_load_rejects_unknown_domain(self):
        journal = InMemoryConsistencyJournalFake()
        self.assertIsNone(journal.load_recovery_state("unknown-domain"))

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
