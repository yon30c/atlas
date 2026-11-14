"""Integration tests for the verified local checkpoint coordinator."""
from datetime import datetime, timezone
import tempfile
import unittest
from pathlib import Path

from atlas.adapters.filesystem_checkpoint_projection_store import (
    FilesystemCheckpointProjectionStore,
)
from atlas.adapters.local_hmac_signer import HmacLocalConsistencySigner
from atlas.adapters.sqlite.consistency_journal import SQLiteConsistencyJournal
from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.memory.checkpoint_coordinator import LocalCheckpointCoordinator
from atlas.memory.journal import (
    CheckpointCommitStatus,
    ConsistencyPosition,
    ConsistencyRecordKind,
    ConsistencyTransition,
)
from atlas.memory.local_keys import ActiveLocalConsistencyKey
from atlas.memory.local_recovery_verifier import LocalConsistencyRecoveryVerifier
from atlas.memory.local_trust_policy import (
    LocalConsistencyTrustPolicy,
    LocalIssuerAuthorization,
)
from atlas.memory.trust import ConsistencyRecoveryVerificationStatus
from atlas.ports.local_consistency_recovery import (
    CheckpointProjectionResolution,
    LocalConsistencyInventoryVerificationResult,
    LocalVerificationStatus,
    VerifiedLocalConsistencyInventories,
)
from unit.test_memory_journal import CHECKPOINT_ID, NOW, RECORD_1, RECORD_2, read_admitted


KEY_REFERENCE = "local-key-v1"
POLICY_VERSION = "local-policy-v1"
REDUCER_VERSION = "reducer-v1"


class FakeActiveKeyProvider:
    def __init__(self, key):
        self.key = key

    def load_active_key(self):
        return ActiveLocalConsistencyKey(KEY_REFERENCE, self.key)


class HistoricalKeys:
    def __init__(self, key):
        self.key = key

    def load_key(self, key_reference):
        return self.key if key_reference == KEY_REFERENCE else None


class VerifiedInventory:
    def verify_recovery_inventories(self, request):
        evidence = VerifiedLocalConsistencyInventories(
            consistency_domain_id=request.state.domain_id,
            authority_epoch=request.state.authority_epoch,
            head_sequence=request.state.head_sequence,
            continuity_reference=request.state.continuity_reference,
            trust_policy_version=request.trust_policy_version,
            inventory_commitment="checkpoint-coordinator-inventory",
            verified_receipt_ids=frozenset(request.projection.receipt_ids),
            verified_tombstone_ids=frozenset(),
            verified_reference_ids=frozenset(request.projection.emission_ids),
            verification_id="checkpoint-coordinator-inventory-verification",
        )
        return LocalConsistencyInventoryVerificationResult(
            LocalVerificationStatus.VERIFIED, evidence
        )


class LocalCheckpointCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = SQLiteDatabase(Path(self.temporary.name) / "atlas.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.key = bytes.fromhex("6d" * 32)

        projection_root = Path(self.temporary.name) / "checkpoint-projections"
        projection_root.mkdir()
        self.store = FilesystemCheckpointProjectionStore(projection_root)

        self.policy = LocalConsistencyTrustPolicy(
            policy_version=POLICY_VERSION,
            consistency_domain_id="atlas-local",
            issuer_authorizations=frozenset({
                LocalIssuerAuthorization(
                    "checkpoint", "atlas-journal", "consistency-journal"
                ),
                LocalIssuerAuthorization(
                    "journal_entry", "atlas-journal", "consistency-journal"
                ),
            }),
            allowed_key_references=frozenset({KEY_REFERENCE}),
            allowed_envelope_versions=frozenset({1}),
            allowed_canonicalization_versions=frozenset({1}),
            allowed_schema_versions=frozenset({1}),
            allowed_reducer_versions=frozenset({REDUCER_VERSION}),
        )

        verifier = LocalConsistencyRecoveryVerifier(
            trust_policy=self.policy,
            key_port=HistoricalKeys(self.key),
            inventory_verifier=VerifiedInventory(),
            verifier_id="checkpoint-coordinator-verifier",
            checkpoint_projection_port=self.store,
        )
        self.journal = SQLiteConsistencyJournal(
            self.database,
            HmacLocalConsistencySigner(FakeActiveKeyProvider(self.key)),
            reducer_version=REDUCER_VERSION,
            issuer_id="atlas-journal",
            issuer_role="consistency-journal",
            key_reference=KEY_REFERENCE,
            trust_policy_version=POLICY_VERSION,
            recovery_verifier=verifier,
            recovery_trust_policy=self.policy,
        )
        self.assertTrue(self.journal.create_local_domain("atlas-local", 1))
        self.first_commit = self.journal.append_transition(
            ConsistencyPosition("atlas-local", 1, 0),
            "coordinator-base-append",
            read_admitted(record_id=RECORD_1),
        )
        self.assertIsNotNone(self.first_commit)

        self.coordinator = LocalCheckpointCoordinator(
            self.journal,
            self.store,
            self.store,
            self.policy,
            reducer_version=REDUCER_VERSION,
        )

    def _checkpoint_count(self):
        with self.database.connection() as connection:
            return connection.execute(
                "SELECT COUNT(*) FROM checkpoints WHERE domain_id='atlas-local'"
            ).fetchone()[0]

    def _head(self):
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT head_sequence FROM consistency_domains "
                "WHERE domain_id='atlas-local'"
            ).fetchone()
            return row[0]

    def test_checkpoint_publishes_verifies_then_commits_and_recovers(self):
        result = self.coordinator.commit_checkpoint(
            CHECKPOINT_ID, self.first_commit.position, NOW
        )

        self.assertIs(result.status, CheckpointCommitStatus.COMMITTED)
        self.assertEqual(result.checkpoint.position, self.first_commit.position)
        self.assertEqual(result.marker_commit.position.sequence, 2)
        self.assertEqual(self._checkpoint_count(), 1)
        self.assertEqual(self._head(), 2)

        recovered = self.journal.load_verified_recovery_state("atlas-local")
        self.assertIs(
            recovered.status, ConsistencyRecoveryVerificationStatus.VERIFIED
        )
        self.assertEqual(recovered.verified_local_state.head_sequence, 2)
        self.assertEqual(
            recovered.verified_local_state.projection.head_sequence, 2
        )
        self.assertEqual(len(recovered.verified_local_state.projection.admissions), 1)

    def test_exact_retry_after_commit_returns_replayed_without_duplicate(self):
        first = self.coordinator.commit_checkpoint(
            CHECKPOINT_ID, self.first_commit.position, NOW
        )
        self.assertIs(first.status, CheckpointCommitStatus.COMMITTED)

        retried = self.coordinator.commit_checkpoint(
            CHECKPOINT_ID, self.first_commit.position, NOW
        )

        self.assertIs(retried.status, CheckpointCommitStatus.REPLAYED)
        self.assertTrue(retried.marker_commit.replayed)
        self.assertEqual(self._checkpoint_count(), 1)
        self.assertEqual(self._head(), 2)

    def test_same_id_with_changed_timestamp_is_conflict(self):
        first = self.coordinator.commit_checkpoint(
            CHECKPOINT_ID, self.first_commit.position, NOW
        )
        self.assertIs(first.status, CheckpointCommitStatus.COMMITTED)

        changed = self.coordinator.commit_checkpoint(
            CHECKPOINT_ID,
            self.first_commit.position,
            datetime(2026, 11, 14, tzinfo=timezone.utc),
        )

        self.assertIs(changed.status, CheckpointCommitStatus.CONFLICT)
        self.assertEqual(self._checkpoint_count(), 1)
        self.assertEqual(self._head(), 2)

    def test_concurrent_append_after_projection_publish_makes_checkpoint_stale(self):
        class RacingPublisher:
            def publish_checkpoint_projection(inner_self, artifacts):
                self.store.publish_checkpoint_projection(artifacts)
                raced = ConsistencyTransition(
                    record_id=RECORD_2,
                    schema_version=1,
                    record_kind=ConsistencyRecordKind.READ_ACTIVATED,
                    operation_id="activate:admission-1",
                    occurred_at=NOW,
                    admission_id="admission-1",
                    generation=1,
                )
                commit = self.journal.append_transition(
                    ConsistencyPosition("atlas-local", 1, 1),
                    "coordinator-racing-append",
                    raced,
                )
                self.assertIsNotNone(commit)

        racing = LocalCheckpointCoordinator(
            self.journal,
            RacingPublisher(),
            self.store,
            self.policy,
            reducer_version=REDUCER_VERSION,
        )

        result = racing.commit_checkpoint(
            CHECKPOINT_ID, self.first_commit.position, NOW
        )

        self.assertIs(result.status, CheckpointCommitStatus.CONFLICT)
        self.assertEqual(self._checkpoint_count(), 0)
        self.assertEqual(self._head(), 2)

    def test_projection_readback_unavailable_prevents_sqlite_mutation(self):
        class UnavailableResolver:
            def resolve_checkpoint_projection(inner_self, request):
                return CheckpointProjectionResolution(
                    LocalVerificationStatus.UNAVAILABLE
                )

        coordinator = LocalCheckpointCoordinator(
            self.journal,
            self.store,
            UnavailableResolver(),
            self.policy,
            reducer_version=REDUCER_VERSION,
        )

        result = coordinator.commit_checkpoint(
            CHECKPOINT_ID, self.first_commit.position, NOW
        )

        self.assertIs(result.status, CheckpointCommitStatus.UNAVAILABLE)
        self.assertEqual(self._checkpoint_count(), 0)
        self.assertEqual(self._head(), 1)

    def test_projection_publication_failure_prevents_sqlite_mutation(self):
        class FailingPublisher:
            def publish_checkpoint_projection(inner_self, artifacts):
                raise OSError("simulated projection store failure")

        coordinator = LocalCheckpointCoordinator(
            self.journal,
            FailingPublisher(),
            self.store,
            self.policy,
            reducer_version=REDUCER_VERSION,
        )

        result = coordinator.commit_checkpoint(
            CHECKPOINT_ID, self.first_commit.position, NOW
        )

        self.assertIs(result.status, CheckpointCommitStatus.UNAVAILABLE)
        self.assertEqual(self._checkpoint_count(), 0)
        self.assertEqual(self._head(), 1)


if __name__ == "__main__":
    unittest.main()
