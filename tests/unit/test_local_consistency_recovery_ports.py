"""Contract tests for the independent local recovery ports."""
from datetime import datetime, timezone
import unittest

from atlas.core.errors import ContractError
from atlas.memory.journal import (
    ConsistencyCheckpoint,
    ConsistencyPosition,
    ConsistencyRecoveryState,
)
from atlas.memory.journal_reducer import ConsistencyProjection
from atlas.ports.local_consistency_recovery import (
    CheckpointProjectionResolution,
    LocalConsistencyInventoryVerificationRequest,
    LocalConsistencyInventoryVerificationResult,
    LocalCheckpointProjectionRequest,
    LocalVerificationStatus,
    VerifiedCheckpointProjection,
    VerifiedLocalConsistencyInventories,
)


class LocalRecoveryPortContractTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 14, tzinfo=timezone.utc)
        self.checkpoint = ConsistencyCheckpoint(
            checkpoint_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074501",
            position=ConsistencyPosition("atlas-main", 2, 7),
            state_reference="checkpoint-state-ref",
            integrity_reference="checkpoint-integrity-ref",
            created_at=self.now,
        )
        self.projection = ConsistencyProjection(
            domain_id="atlas-main",
            authority_epoch=2,
            head_sequence=7,
            admissions=(),
            forget_closures=(),
            invalidations=(),
            idempotency_records=(),
            receipt_ids=frozenset(),
            recovery_closures=(),
        )
        self.state = ConsistencyRecoveryState(
            domain_id="atlas-main",
            authority_epoch=2,
            checkpoint=self.checkpoint,
            entries=(),
            head_sequence=7,
            continuity_reference="head-commitment",
        )

    def test_checkpoint_request_binds_checkpoint_to_trusted_policy_and_versions(self):
        request = LocalCheckpointProjectionRequest(
            checkpoint=self.checkpoint,
            consistency_domain_id="atlas-main",
            authority_epoch=2,
            trust_policy_version="local-policy-v1",
            allowed_schema_versions=frozenset({1, 2}),
            allowed_reducer_versions=frozenset({"reducer-v1"}),
        )
        self.assertEqual(request.checkpoint.checkpoint_id, self.checkpoint.checkpoint_id)

    def test_checkpoint_request_rejects_wrong_domain_or_epoch(self):
        with self.assertRaises(ContractError):
            LocalCheckpointProjectionRequest(
                checkpoint=self.checkpoint,
                consistency_domain_id="other-domain",
                authority_epoch=2,
                trust_policy_version="local-policy-v1",
                allowed_schema_versions=frozenset({1}),
                allowed_reducer_versions=frozenset({"reducer-v1"}),
            )
        with self.assertRaises(ContractError):
            LocalCheckpointProjectionRequest(
                checkpoint=self.checkpoint,
                consistency_domain_id="atlas-main",
                authority_epoch=3,
                trust_policy_version="local-policy-v1",
                allowed_schema_versions=frozenset({1}),
                allowed_reducer_versions=frozenset({"reducer-v1"}),
            )

    def test_verified_checkpoint_projection_binds_base_to_exact_checkpoint_position(self):
        evidence = VerifiedCheckpointProjection(
            checkpoint_id=self.checkpoint.checkpoint_id,
            consistency_domain_id="atlas-main",
            authority_epoch=2,
            sequence=7,
            state_commitment="state-commitment",
            integrity_commitment="integrity-commitment",
            schema_version=1,
            reducer_version="reducer-v1",
            projection=self.projection,
            verification_id="checkpoint-verification-1",
        )
        result = CheckpointProjectionResolution(
            LocalVerificationStatus.VERIFIED, evidence
        )
        self.assertIs(result.verified_projection, evidence)

    def test_checkpoint_projection_rejects_projection_at_another_head(self):
        with self.assertRaises(ContractError):
            VerifiedCheckpointProjection(
                checkpoint_id=self.checkpoint.checkpoint_id,
                consistency_domain_id="atlas-main",
                authority_epoch=2,
                sequence=6,
                state_commitment="state-commitment",
                integrity_commitment="integrity-commitment",
                schema_version=1,
                reducer_version="reducer-v1",
                projection=self.projection,
                verification_id="checkpoint-verification-1",
            )

    def test_checkpoint_resolution_enforces_status_evidence_pairing(self):
        with self.assertRaises(ContractError):
            CheckpointProjectionResolution(LocalVerificationStatus.VERIFIED, None)
        with self.assertRaises(ContractError):
            CheckpointProjectionResolution(LocalVerificationStatus.REJECTED, object())

    def test_inventory_request_binds_exact_recovery_projection(self):
        request = LocalConsistencyInventoryVerificationRequest(
            state=self.state,
            projection=self.projection,
            trust_policy_version="local-policy-v1",
        )
        self.assertEqual(request.state.head_sequence, 7)

    def test_inventory_request_rejects_projection_from_other_head(self):
        from dataclasses import replace
        with self.assertRaises(ContractError):
            LocalConsistencyInventoryVerificationRequest(
                state=self.state,
                projection=replace(self.projection, head_sequence=6),
                trust_policy_version="local-policy-v1",
            )

    def test_verified_inventory_attestation_binds_complete_inventory_identity(self):
        evidence = VerifiedLocalConsistencyInventories(
            consistency_domain_id="atlas-main",
            authority_epoch=2,
            head_sequence=7,
            continuity_reference="head-commitment",
            trust_policy_version="local-policy-v1",
            inventory_commitment="inventory-commitment",
            verified_receipt_ids=frozenset({"receipt-1"}),
            verified_tombstone_ids=frozenset({"forget-op-1"}),
            verified_reference_ids=frozenset({"snapshot-1", "memory-version-1"}),
            verification_id="inventory-verification-1",
        )
        result = LocalConsistencyInventoryVerificationResult(
            LocalVerificationStatus.VERIFIED, evidence
        )
        self.assertEqual(result.verified_inventories.verified_receipt_ids, frozenset({"receipt-1"}))

    def test_inventory_result_fails_closed_without_verified_evidence(self):
        with self.assertRaises(ContractError):
            LocalConsistencyInventoryVerificationResult(LocalVerificationStatus.VERIFIED)
        with self.assertRaises(ContractError):
            LocalConsistencyInventoryVerificationResult(LocalVerificationStatus.UNAVAILABLE, object())


if __name__ == "__main__":
    unittest.main()
