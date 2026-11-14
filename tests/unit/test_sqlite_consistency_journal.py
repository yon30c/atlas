"""Integration tests for the SQLite K01 append identity contract."""
from dataclasses import replace
from datetime import timedelta
import tempfile
import unittest
from pathlib import Path

from atlas.adapters.sqlite.consistency_journal import SQLiteConsistencyJournal
from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.memory.envelope import AuthenticatedConsistencyEnvelope
from atlas.memory.journal import (
    ConsistencyCheckpoint,
    ConsistencyPosition,
    ConsistencyRecordKind,
    ConsistencyRecoveryLoadStatus,
    ConsistencyTransition,
    JournalOperationResolutionStatus,
)
from atlas.memory.local_auth import checkpoint_payload, object_commitment
from unit.test_memory_journal import (
    CHECKPOINT_ID, NOW, RECORD_1, RECORD_2, read_admitted,
)


class FakeSigner:
    """Test-only envelope signer; does not represent production key custody."""

    def sign_envelope(self, envelope, object_value):
        return replace(
            envelope,
            object_commitment=object_commitment(object_value),
            authentication_evidence="test-authentication-evidence",
        )


class SQLiteConsistencyJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
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
        self.assertTrue(self.journal.create_local_domain("domain-a", 1))

    @staticmethod
    def position(sequence):
        return ConsistencyPosition("domain-a", 1, sequence)

    def _seed_checkpoint(self):
        first = read_admitted(record_id=RECORD_1)
        first_commit = self.journal.append_transition(
            self.position(0), "append-before-checkpoint", first
        )
        self.assertIsNotNone(first_commit)
        checkpoint = ConsistencyCheckpoint(
            checkpoint_id=CHECKPOINT_ID,
            position=first_commit.position,
            state_reference="state-reference-checkpoint",
            integrity_reference="integrity-reference-checkpoint",
            created_at=NOW,
        )
        unsigned = AuthenticatedConsistencyEnvelope(
            object_kind="checkpoint",
            envelope_version=1,
            consistency_domain_id="domain-a",
            authority_epoch=1,
            sequence=first_commit.position.sequence,
            object_id=CHECKPOINT_ID,
            schema_version=1,
            reducer_version="reducer-v1",
            previous_commitment=None,
            object_commitment="pending",
            issuer_id="issuer-test",
            issuer_role="service",
            key_reference="key-test",
            trust_policy_version="policy-v1",
            issued_at=NOW,
            authentication_evidence="pending",
        )
        signed = FakeSigner().sign_envelope(unsigned, checkpoint_payload(checkpoint))
        checkpoint = replace(checkpoint, envelope=signed)
        with self.database.write_transaction() as connection:
            connection.execute(
                """
                INSERT INTO checkpoints (
                    checkpoint_id, domain_id, authority_epoch, sequence,
                    state_reference, integrity_reference, created_at,
                    envelope_version, schema_version, reducer_version,
                    previous_commitment, object_commitment, issuer_id, issuer_role,
                    key_reference, trust_policy_version, issued_at,
                    authentication_evidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint.checkpoint_id, "domain-a", 1,
                    checkpoint.position.sequence, checkpoint.state_reference,
                    checkpoint.integrity_reference,
                    checkpoint.created_at.isoformat(timespec="microseconds"),
                    signed.envelope_version, signed.schema_version,
                    signed.reducer_version, signed.previous_commitment,
                    signed.object_commitment, signed.issuer_id, signed.issuer_role,
                    signed.key_reference, signed.trust_policy_version,
                    signed.issued_at.isoformat(timespec="microseconds"),
                    signed.authentication_evidence,
                ),
            )
            connection.execute(
                "UPDATE consistency_domains SET head_commitment=? WHERE domain_id='domain-a'",
                (signed.object_commitment,),
            )
        marker = ConsistencyTransition(
            record_id=CHECKPOINT_ID,
            schema_version=1,
            record_kind=ConsistencyRecordKind.CHECKPOINT_COMMITTED,
            operation_id=f"checkpoint:{CHECKPOINT_ID}",
            occurred_at=NOW,
            checkpoint_reference=checkpoint.state_reference,
        )
        marker_commit = self.journal.append_transition(
            self.position(first_commit.position.sequence),
            "append-checkpoint-marker",
            marker,
        )
        self.assertIsNotNone(marker_commit)
        return checkpoint, marker

    def test_semantic_replay_with_new_append_and_record_ids_returns_original_commit(self):
        original = read_admitted(record_id=RECORD_1, idempotency_key="semantic-key")
        retry = read_admitted(
            record_id=RECORD_2,
            idempotency_key="semantic-key",
            occurred_at=NOW + timedelta(seconds=30),
        )
        first = self.journal.append_transition(self.position(0), "append-first", original)
        replay = self.journal.append_transition(self.position(0), "append-retry", retry)

        self.assertIsNotNone(first)
        self.assertIsNotNone(replay)
        self.assertEqual(first.record_id, RECORD_1)
        self.assertEqual(replay.record_id, RECORD_1)
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.position.sequence, 1)

    def test_same_append_id_and_semantics_without_key_replays_original_commit(self):
        original = read_admitted(record_id=RECORD_1)
        retry = replace(
            original,
            record_id=RECORD_2,
            occurred_at=NOW + timedelta(seconds=20),
        )
        first = self.journal.append_transition(self.position(0), "stable-append", original)
        replay = self.journal.append_transition(self.position(0), "stable-append", retry)

        self.assertIsNotNone(first)
        self.assertIsNotNone(replay)
        self.assertEqual(replay.record_id, RECORD_1)
        self.assertTrue(replay.replayed)

    def test_reused_idempotency_key_with_different_semantics_conflicts(self):
        original = read_admitted(record_id=RECORD_1, idempotency_key="semantic-key")
        changed = replace(
            original,
            record_id=RECORD_2,
            route_ids=frozenset({"different-business-effect"}),
        )
        first = self.journal.append_transition(self.position(0), "append-first", original)
        conflict = self.journal.append_transition(self.position(0), "append-retry", changed)

        self.assertIsNotNone(first)
        self.assertIsNone(conflict)

    def test_operation_id_can_be_reused_for_distinct_appends(self):
        first_transition = read_admitted(record_id=RECORD_1)
        second_transition = replace(
            first_transition,
            record_id=RECORD_2,
            snapshot_id="snapshot-2",
        )
        first = self.journal.append_transition(
            self.position(0), "append-one", first_transition
        )
        second = self.journal.append_transition(
            self.position(1), "append-two", second_transition
        )

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(first.position.sequence, 1)
        self.assertEqual(second.position.sequence, 2)

    def test_resolve_append_finds_exact_commit_by_append_id(self):
        transition = read_admitted(record_id=RECORD_1, idempotency_key="resolve-key")
        self.journal.append_transition(self.position(0), "append-resolve", transition)

        result = self.journal.resolve_append(
            "domain-a", 1, "append-resolve", "resolve-key",
            transition, self.position(0),
        )

        self.assertIs(result.status, JournalOperationResolutionStatus.COMMITTED_EXACT)
        self.assertEqual(result.commit.record_id, RECORD_1)
        self.assertEqual(result.committed_transition, transition)

    def test_resolve_append_finds_semantic_replay_with_regenerated_append_id(self):
        original = read_admitted(record_id=RECORD_1, idempotency_key="resolve-key")
        retry = read_admitted(
            record_id=RECORD_2,
            idempotency_key="resolve-key",
            occurred_at=NOW + timedelta(seconds=10),
        )
        self.journal.append_transition(self.position(0), "append-original", original)

        result = self.journal.resolve_append(
            "domain-a", 1, "append-retry", "resolve-key",
            retry, self.position(0),
        )

        self.assertIs(result.status, JournalOperationResolutionStatus.COMMITTED_EXACT)
        self.assertEqual(result.commit.record_id, RECORD_1)
        self.assertEqual(result.committed_transition, original)

    def test_append_id_reuse_with_different_semantics_conflicts(self):
        original = read_admitted(record_id=RECORD_1)
        changed = replace(
            original,
            record_id=RECORD_2,
            snapshot_id="different-snapshot",
        )
        first = self.journal.append_transition(self.position(0), "stable-append", original)
        conflict = self.journal.append_transition(
            self.position(0), "stable-append", changed
        )
        self.assertIsNotNone(first)
        self.assertIsNone(conflict)

    def test_resolve_semantic_replay_allows_head_to_advance_after_original_commit(self):
        original = read_admitted(record_id=RECORD_1, idempotency_key="replay-key")
        retry = read_admitted(
            record_id=RECORD_2,
            idempotency_key="replay-key",
            occurred_at=NOW + timedelta(seconds=15),
        )
        later = replace(
            read_admitted(record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c073a16"),
            snapshot_id="later-snapshot",
        )
        self.journal.append_transition(self.position(0), "append-original", original)
        self.journal.append_transition(self.position(1), "append-later", later)

        result = self.journal.resolve_append(
            "domain-a", 1, "append-retry", "replay-key", retry, self.position(0)
        )

        self.assertIs(result.status, JournalOperationResolutionStatus.COMMITTED_EXACT)
        self.assertEqual(result.commit.record_id, RECORD_1)
        self.assertEqual(result.current_position.sequence, 2)

    def test_resolve_append_rejects_two_locators_that_point_to_different_commits(self):
        first = read_admitted(record_id=RECORD_1, idempotency_key="key-one")
        second = replace(
            first,
            record_id=RECORD_2,
            idempotency_key="key-two",
            snapshot_id="snapshot-two",
        )
        self.journal.append_transition(self.position(0), "append-one", first)
        self.journal.append_transition(self.position(1), "append-two", second)

        result = self.journal.resolve_append(
            "domain-a", 1, "append-one", "key-two", second, self.position(1)
        )

        self.assertIs(result.status, JournalOperationResolutionStatus.CONFLICT)
        self.assertIsNone(result.commit)

    def test_append_failure_from_signer_leaves_head_and_journal_unchanged(self):
        class FailingSigner:
            def sign_envelope(self, envelope, object_value):
                raise OSError("signer unavailable")

        journal = SQLiteConsistencyJournal(
            self.database,
            FailingSigner(),
            reducer_version="reducer-v1",
            issuer_id="issuer-test",
            issuer_role="service",
            key_reference="key-test",
            trust_policy_version="policy-v1",
        )
        transition = read_admitted(record_id=RECORD_1)
        result = journal.append_transition(self.position(0), "append-failed", transition)
        self.assertIsNone(result)
        with self.database.connection() as connection:
            domain = connection.execute(
                "SELECT head_sequence FROM consistency_domains WHERE domain_id='domain-a'"
            ).fetchone()
            entries = connection.execute(
                "SELECT COUNT(*) FROM journal_entries WHERE domain_id='domain-a'"
            ).fetchone()[0]
        self.assertEqual(domain["head_sequence"], 0)
        self.assertEqual(entries, 0)

    def test_signer_cannot_change_authenticated_issue_time(self):
        class TimestampMutatingSigner:
            def sign_envelope(self, envelope, object_value):
                return replace(
                    envelope,
                    issued_at=envelope.issued_at + timedelta(seconds=1),
                    object_commitment=object_commitment(object_value),
                    authentication_evidence="test-authentication-evidence",
                )

        journal = SQLiteConsistencyJournal(
            self.database,
            TimestampMutatingSigner(),
            reducer_version="reducer-v1",
            issuer_id="issuer-test",
            issuer_role="service",
            key_reference="key-test",
            trust_policy_version="policy-v1",
        )
        result = journal.append_transition(
            self.position(0), "append-mutated-time", read_admitted(record_id=RECORD_1)
        )
        self.assertIsNone(result)
        with self.database.connection() as connection:
            head = connection.execute(
                "SELECT head_sequence FROM consistency_domains WHERE domain_id='domain-a'"
            ).fetchone()[0]
            count = connection.execute(
                "SELECT COUNT(*) FROM journal_entries WHERE domain_id='domain-a'"
            ).fetchone()[0]
        self.assertEqual(head, 0)
        self.assertEqual(count, 0)

    def test_unexpected_signer_exception_fails_closed(self):
        class UnexpectedFailingSigner:
            def sign_envelope(self, envelope, object_value):
                raise Exception("unexpected signer failure")

        journal = SQLiteConsistencyJournal(
            self.database,
            UnexpectedFailingSigner(),
            reducer_version="reducer-v1",
            issuer_id="issuer-test",
            issuer_role="service",
            key_reference="key-test",
            trust_policy_version="policy-v1",
        )
        result = journal.append_transition(
            self.position(0), "append-unexpected-failure",
            read_admitted(record_id=RECORD_1),
        )
        self.assertIsNone(result)
        with self.database.connection() as connection:
            head = connection.execute(
                "SELECT head_sequence FROM consistency_domains WHERE domain_id='domain-a'"
            ).fetchone()[0]
            count = connection.execute(
                "SELECT COUNT(*) FROM journal_entries WHERE domain_id='domain-a'"
            ).fetchone()[0]
        self.assertEqual(head, 0)
        self.assertEqual(count, 0)

    def test_stale_position_does_not_append_or_advance_head(self):
        first = read_admitted(record_id=RECORD_1)
        second = replace(first, record_id=RECORD_2, snapshot_id="snapshot-stale")
        self.assertIsNotNone(
            self.journal.append_transition(self.position(0), "append-first", first)
        )
        stale = self.journal.append_transition(self.position(0), "append-second", second)
        self.assertIsNone(stale)
        with self.database.connection() as connection:
            head = connection.execute(
                "SELECT head_sequence FROM consistency_domains WHERE domain_id='domain-a'"
            ).fetchone()[0]
            count = connection.execute(
                "SELECT COUNT(*) FROM journal_entries WHERE domain_id='domain-a'"
            ).fetchone()[0]
        self.assertEqual(head, 1)
        self.assertEqual(count, 1)

    def test_resolve_append_reports_not_committed_only_when_both_locators_are_absent(self):
        transition = read_admitted(record_id=RECORD_1, idempotency_key="absent-key")
        result = self.journal.resolve_append(
            "domain-a", 1, "absent-append", "absent-key",
            transition, self.position(0),
        )
        self.assertIs(result.status, JournalOperationResolutionStatus.NOT_COMMITTED)
        self.assertEqual(result.current_position.sequence, 0)


    def test_load_recovery_state_reconstructs_durable_entries_and_envelopes(self):
        first = read_admitted(record_id=RECORD_1)
        second = replace(first, record_id=RECORD_2, snapshot_id="snapshot-two")
        self.assertIsNotNone(
            self.journal.append_transition(self.position(0), "read-append-one", first)
        )
        self.assertIsNotNone(
            self.journal.append_transition(self.position(1), "read-append-two", second)
        )

        state = self.journal.load_recovery_state("domain-a")

        self.assertIsNotNone(state)
        self.assertEqual(state.domain_id, "domain-a")
        self.assertEqual(state.authority_epoch, 1)
        self.assertEqual(state.head_sequence, 2)
        self.assertEqual(len(state.entries), 2)
        self.assertEqual(state.entries[0].transition, first)
        self.assertEqual(state.entries[1].transition, second)
        self.assertEqual(state.entries[0].envelope.sequence, 1)
        self.assertEqual(state.entries[1].envelope.sequence, 2)
        self.assertEqual(
            state.continuity_reference,
            state.entries[-1].envelope.object_commitment,
        )

    def test_load_recovery_state_returns_none_for_empty_domain(self):
        self.assertIsNone(self.journal.load_recovery_state("domain-a"))

    def test_load_recovery_state_fails_closed_when_head_disagrees_with_rows(self):
        transition = read_admitted(record_id=RECORD_1)
        self.assertIsNotNone(
            self.journal.append_transition(self.position(0), "read-append", transition)
        )
        with self.database.write_transaction() as connection:
            connection.execute(
                "UPDATE consistency_domains SET head_sequence=2 WHERE domain_id='domain-a'"
            )

        self.assertIsNone(self.journal.load_recovery_state("domain-a"))

    def test_load_recovery_state_fails_closed_on_transition_metadata_mismatch(self):
        transition = read_admitted(record_id=RECORD_1)
        self.assertIsNotNone(
            self.journal.append_transition(self.position(0), "read-append", transition)
        )
        with self.database.write_transaction() as connection:
            connection.execute(
                "UPDATE journal_entries SET record_kind='endpoint_fenced' "
                "WHERE domain_id='domain-a' AND sequence=1"
            )

        self.assertIsNone(self.journal.load_recovery_state("domain-a"))


    def test_typed_recovery_load_distinguishes_loaded_and_unavailable(self):
        transition = read_admitted(record_id=RECORD_1)
        self.assertIsNotNone(
            self.journal.append_transition(self.position(0), "typed-load", transition)
        )
        loaded = self.journal.load_recovery_state_result("domain-a")
        absent = self.journal.load_recovery_state_result("missing-domain")

        self.assertIs(loaded.status, ConsistencyRecoveryLoadStatus.LOADED)
        self.assertIsNotNone(loaded.state)
        self.assertIs(absent.status, ConsistencyRecoveryLoadStatus.UNAVAILABLE)
        self.assertIsNone(absent.state)

    def test_typed_recovery_load_rejects_noncanonical_transition_bytes(self):
        transition = read_admitted(record_id=RECORD_1)
        self.assertIsNotNone(
            self.journal.append_transition(self.position(0), "noncanonical", transition)
        )
        with self.database.write_transaction() as connection:
            raw = bytes(connection.execute(
                "SELECT transition_canonical FROM journal_entries "
                "WHERE domain_id='domain-a' AND sequence=1"
            ).fetchone()[0])
            import json
            noncanonical = json.dumps(
                json.loads(raw.decode("utf-8")), ensure_ascii=False, indent=2
            ).encode("utf-8")
            connection.execute(
                "UPDATE journal_entries SET transition_canonical=? "
                "WHERE domain_id='domain-a' AND sequence=1",
                (noncanonical,),
            )

        result = self.journal.load_recovery_state_result("domain-a")
        self.assertIs(result.status, ConsistencyRecoveryLoadStatus.REJECTED)
        self.assertIsNone(result.state)

    def test_typed_recovery_load_rejects_multiple_operation_rows_for_one_entry(self):
        first = read_admitted(record_id=RECORD_1)
        second = replace(first, record_id=RECORD_2, snapshot_id="snapshot-two")
        self.assertIsNotNone(
            self.journal.append_transition(self.position(0), "one-operation", first)
        )
        self.assertIsNotNone(
            self.journal.append_transition(self.position(1), "second-operation", second)
        )
        with self.database.write_transaction() as connection:
            row = connection.execute(
                "SELECT * FROM journal_operations WHERE domain_id='domain-a' AND sequence=1"
            ).fetchone()
            connection.execute(
                """
                INSERT INTO journal_operations (
                    domain_id, authority_epoch, append_id, operation_id, idempotency_key,
                    request_canonical, request_digest, sequence, record_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["domain_id"], row["authority_epoch"], "duplicate-operation-row",
                    row["operation_id"], None, row["request_canonical"],
                    row["request_digest"], row["sequence"], row["record_id"],
                    row["created_at"],
                ),
            )
            connection.execute(
                "DELETE FROM journal_operations WHERE domain_id='domain-a' AND sequence=2"
            )

        result = self.journal.load_recovery_state_result("domain-a")
        self.assertIs(result.status, ConsistencyRecoveryLoadStatus.REJECTED)
        self.assertIsNone(result.state)

    def test_typed_recovery_load_reconstructs_checkpoint_and_only_its_suffix(self):
        checkpoint, marker = self._seed_checkpoint()
        later = replace(
            read_admitted(record_id=RECORD_2),
            snapshot_id="snapshot-after-checkpoint",
            admission_id="admission-after-checkpoint",
            operation_id="read:admission-after-checkpoint",
        )
        self.assertIsNotNone(
            self.journal.append_transition(self.position(2), "append-after-checkpoint", later)
        )

        result = self.journal.load_recovery_state_result("domain-a")

        self.assertIs(result.status, ConsistencyRecoveryLoadStatus.LOADED)
        self.assertEqual(result.state.checkpoint, checkpoint)
        self.assertEqual(result.state.head_sequence, 3)
        self.assertEqual(len(result.state.entries), 2)
        self.assertEqual(
            result.state.entries[0].transition.record_kind,
            ConsistencyRecordKind.CHECKPOINT_COMMITTED,
        )
        self.assertEqual(result.state.entries[0].transition, marker)
        self.assertEqual(result.state.entries[0].position.sequence, 2)
        self.assertEqual(result.state.entries[1].position.sequence, 3)

    def test_typed_recovery_load_rejects_checkpoint_marker_reference_mismatch(self):
        checkpoint, _ = self._seed_checkpoint()
        changed = replace(checkpoint, state_reference="different-state-reference")
        with self.database.write_transaction() as connection:
            connection.execute(
                "UPDATE checkpoints SET state_reference=?, object_commitment=? "
                "WHERE checkpoint_id=?",
                (
                    changed.state_reference,
                    object_commitment(checkpoint_payload(changed)),
                    CHECKPOINT_ID,
                ),
            )

        result = self.journal.load_recovery_state_result("domain-a")

        self.assertIs(result.status, ConsistencyRecoveryLoadStatus.REJECTED)
        self.assertIsNone(result.state)

    def test_typed_recovery_load_rejects_checkpoint_without_commit_marker(self):
        self._seed_checkpoint()
        with self.database.write_transaction() as connection:
            connection.execute(
                "DELETE FROM journal_operations WHERE domain_id='domain-a' AND sequence=2"
            )
            connection.execute(
                "DELETE FROM journal_entries WHERE domain_id='domain-a' AND sequence=2"
            )

        result = self.journal.load_recovery_state_result("domain-a")

        self.assertIs(result.status, ConsistencyRecoveryLoadStatus.REJECTED)
        self.assertIsNone(result.state)

    def test_typed_recovery_load_rejects_checkpoint_marker_without_checkpoint_row(self):
        marker = ConsistencyTransition(
            record_id=CHECKPOINT_ID,
            schema_version=1,
            record_kind=ConsistencyRecordKind.CHECKPOINT_COMMITTED,
            operation_id=f"checkpoint:{CHECKPOINT_ID}",
            occurred_at=NOW,
            checkpoint_reference="orphan-state-reference",
        )
        self.assertIsNotNone(
            self.journal.append_transition(self.position(0), "orphan-marker", marker)
        )

        result = self.journal.load_recovery_state_result("domain-a")

        self.assertIs(result.status, ConsistencyRecoveryLoadStatus.REJECTED)
        self.assertIsNone(result.state)

    def test_verified_recovery_read_is_unavailable_without_explicit_verifier(self):
        result = self.journal.load_verified_recovery_state("domain-a")
        from atlas.memory.trust import ConsistencyRecoveryVerificationStatus
        self.assertIs(result.status, ConsistencyRecoveryVerificationStatus.UNAVAILABLE)


    def test_typed_recovery_load_rejects_tampered_idempotency_projection_digest(self):
        transition = read_admitted(record_id=RECORD_1)
        self.assertIsNotNone(
            self.journal.append_transition(self.position(0), "tampered-digest", transition)
        )
        with self.database.write_transaction() as connection:
            connection.execute(
                "UPDATE journal_operations SET request_digest=? "
                "WHERE domain_id='domain-a' AND sequence=1",
                ("0" * 64,),
            )

        result = self.journal.load_recovery_state_result("domain-a")
        self.assertIs(result.status, ConsistencyRecoveryLoadStatus.REJECTED)
        self.assertIsNone(result.state)


if __name__ == "__main__":
    unittest.main()
