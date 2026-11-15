"""Integration tests for immutable filesystem checkpoint projection storage."""
from datetime import datetime, timezone
import os
import tempfile
from pathlib import Path
import unittest

from atlas.core.errors import ContractError
from atlas.adapters.filesystem_checkpoint_projection_store import (
    FilesystemCheckpointProjectionStore,
)
from atlas.memory.checkpoint_projection_codec import (
    build_checkpoint_projection_artifacts,
)
from atlas.memory.journal import ConsistencyCheckpoint, ConsistencyPosition
from atlas.memory.journal_reducer import ConsistencyProjection
from atlas.memory.ports.recovery import (
    CheckpointProjectionRequest,
    RecoveryVerificationStatus,
)


CHECKPOINT_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c074501"
POLICY = "local-policy-v1"
REDUCER = "reducer-v1"


def projection():
    return ConsistencyProjection(
        domain_id="atlas-main",
        authority_epoch=2,
        head_sequence=7,
        admissions=(),
        forget_closures=(),
        invalidations=(),
        idempotency_records=(),
        receipt_ids=frozenset(),
        recovery_closures=(),
        replay_metadata_version=1,
    )


class FilesystemCheckpointProjectionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "checkpoint-store"
        self.root.mkdir()
        self.store = FilesystemCheckpointProjectionStore(self.root)
        self.artifacts = build_checkpoint_projection_artifacts(
            projection(),
            checkpoint_id=CHECKPOINT_ID,
            schema_version=1,
            reducer_version=REDUCER,
            trust_policy_version=POLICY,
        )
        self.checkpoint = ConsistencyCheckpoint(
            checkpoint_id=CHECKPOINT_ID,
            position=ConsistencyPosition("atlas-main", 2, 7),
            state_reference=self.artifacts.state_reference,
            integrity_reference=self.artifacts.integrity_reference,
            created_at=datetime(2026, 11, 14, tzinfo=timezone.utc),
        )
        self.request = CheckpointProjectionRequest(
            checkpoint=self.checkpoint,
            consistency_domain_id="atlas-main",
            authority_epoch=2,
            trust_policy_version=POLICY,
            allowed_schema_versions=frozenset({1}),
            allowed_reducer_versions=frozenset({REDUCER}),
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_publish_and_resolve_returns_exact_verified_projection(self):
        self.store.publish_checkpoint_projection(self.artifacts)
        result = self.store.resolve_checkpoint_projection(self.request)
        self.assertIs(result.status, RecoveryVerificationStatus.VERIFIED)
        evidence = result.verified_projection
        self.assertEqual(evidence.checkpoint_id, CHECKPOINT_ID)
        self.assertEqual(evidence.projection, projection())
        self.assertEqual(evidence.state_reference, self.artifacts.state_reference)
        self.assertEqual(evidence.integrity_reference, self.artifacts.integrity_reference)
        self.assertEqual(evidence.schema_version, 1)
        self.assertEqual(evidence.reducer_version, REDUCER)

    def test_republishing_identical_objects_is_idempotent(self):
        self.store.publish_checkpoint_projection(self.artifacts)
        self.store.publish_checkpoint_projection(self.artifacts)
        self.assertIs(
            self.store.resolve_checkpoint_projection(self.request).status,
            RecoveryVerificationStatus.VERIFIED,
        )

    def test_missing_object_is_unavailable(self):
        result = self.store.resolve_checkpoint_projection(self.request)
        self.assertIs(result.status, RecoveryVerificationStatus.UNAVAILABLE)

    def test_corrupt_state_object_is_rejected(self):
        self.store.publish_checkpoint_projection(self.artifacts)
        digest = self.artifacts.state_reference.removeprefix("sha256:")
        (self.root / "state" / digest).write_bytes(b"tampered")
        result = self.store.resolve_checkpoint_projection(self.request)
        self.assertIs(result.status, RecoveryVerificationStatus.REJECTED)

    def test_existing_content_address_collision_is_not_overwritten(self):
        self.store.publish_checkpoint_projection(self.artifacts)
        digest = self.artifacts.state_reference.removeprefix("sha256:")
        (self.root / "state" / digest).write_bytes(b"tampered")
        with self.assertRaises(ContractError):
            self.store.publish_checkpoint_projection(self.artifacts)
        self.assertEqual((self.root / "state" / digest).read_bytes(), b"tampered")

    def test_manifest_bound_to_another_policy_is_rejected(self):
        wrong_request = CheckpointProjectionRequest(
            checkpoint=self.checkpoint,
            consistency_domain_id="atlas-main",
            authority_epoch=2,
            trust_policy_version="different-policy",
            allowed_schema_versions=frozenset({1}),
            allowed_reducer_versions=frozenset({REDUCER}),
        )
        self.store.publish_checkpoint_projection(self.artifacts)
        result = self.store.resolve_checkpoint_projection(wrong_request)
        self.assertIs(result.status, RecoveryVerificationStatus.REJECTED)

    def test_unsupported_schema_or_reducer_is_rejected(self):
        wrong_request = CheckpointProjectionRequest(
            checkpoint=self.checkpoint,
            consistency_domain_id="atlas-main",
            authority_epoch=2,
            trust_policy_version=POLICY,
            allowed_schema_versions=frozenset({2}),
            allowed_reducer_versions=frozenset({"reducer-v2"}),
        )
        self.store.publish_checkpoint_projection(self.artifacts)
        result = self.store.resolve_checkpoint_projection(wrong_request)
        self.assertIs(result.status, RecoveryVerificationStatus.REJECTED)

    def test_preexisting_storage_directory_with_permissive_mode_is_rejected(self):
        insecure_root = Path(self.temporary.name) / "insecure-checkpoint-store"
        insecure_root.mkdir()
        state_dir = insecure_root / "state"
        state_dir.mkdir(mode=0o700)
        os.chmod(state_dir, 0o755)

        with self.assertRaises(ContractError):
            FilesystemCheckpointProjectionStore(insecure_root)

    def test_reopening_store_accepts_private_existing_directories(self):
        reopened = FilesystemCheckpointProjectionStore(self.root)
        self.assertTrue(reopened._state_dir.is_dir())
        self.assertTrue(reopened._manifest_dir.is_dir())

    def test_relative_or_missing_root_is_rejected(self):
        with self.assertRaises(ContractError):
            FilesystemCheckpointProjectionStore("relative/path")
        with self.assertRaises(ContractError):
            FilesystemCheckpointProjectionStore(self.root / "missing")


if __name__ == "__main__":
    unittest.main()
