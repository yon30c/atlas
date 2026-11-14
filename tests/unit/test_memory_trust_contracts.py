from dataclasses import replace
from datetime import datetime, timezone
import unittest

from atlas.core.errors import ContractError
from atlas.memory.journal import ConsistencyPosition, ConsistencyRecoveryState
from atlas.memory.trust import (
    AuthenticatedConsistencyEnvelope,
    ConsistencyCheckpointVerificationRequest,
    ConsistencyRecoveryVerificationResult,
    ConsistencyRecoveryVerificationStatus,
    ConsistencyTrustAnchor,
    ReceiptTrustContext,
    VerifiedConsistencyRecoveryState,
)


class ConsistencyTrustContractTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
        self.anchor = ConsistencyTrustAnchor(
            anchor_id="anchor-1",
            consistency_domain_id="atlas-main",
            authority_epoch=4,
            maximum_committed_sequence=3,
            authenticated_state_commitment="control-state-commitment",
            issuer_id="trust-authority",
            key_reference="key-ref-7",
            trust_policy_version="policy-v2",
            anchor_revision=9,
            issued_at=self.now,
        )
        self.envelope = AuthenticatedConsistencyEnvelope(
            object_kind="checkpoint",
            envelope_version=1,
            consistency_domain_id="atlas-main",
            authority_epoch=4,
            sequence=3,
            object_id="checkpoint-3",
            schema_version=2,
            reducer_version="reducer-v1",
            previous_commitment="previous-control-commitment",
            object_commitment="control-state-commitment",
            issuer_id="journal-authority",
            issuer_role="consistency-journal",
            key_reference="journal-key-2",
            trust_policy_version="policy-v2",
            issued_at=self.now,
            authentication_evidence="opaque-auth-evidence",
        )

    def test_valid_checkpoint_verification_request_binds_domain_epoch_and_anchor(self):
        request = ConsistencyCheckpointVerificationRequest(
            expected_domain_id="atlas-main",
            expected_authority_epoch=4,
            expected_position=ConsistencyPosition("atlas-main", 4, 3),
            anchor=self.anchor,
            envelope=self.envelope,
            trust_policy_version="policy-v2",
            verification_time=self.now,
        )
        self.assertEqual(request.expected_position.sequence, 3)

    def test_checkpoint_behind_external_anchor_is_rejected(self):
        with self.assertRaises(ContractError):
            ConsistencyCheckpointVerificationRequest(
                expected_domain_id="atlas-main",
                expected_authority_epoch=4,
                expected_position=ConsistencyPosition("atlas-main", 4, 2),
                anchor=self.anchor,
                envelope=self.envelope,
                trust_policy_version="policy-v2",
                verification_time=self.now,
            )

    def test_envelope_wrong_domain_is_rejected(self):
        wrong = replace(self.envelope, consistency_domain_id="other-domain")
        with self.assertRaises(ContractError):
            ConsistencyCheckpointVerificationRequest(
                expected_domain_id="atlas-main",
                expected_authority_epoch=4,
                expected_position=ConsistencyPosition("atlas-main", 4, 3),
                anchor=self.anchor,
                envelope=wrong,
                trust_policy_version="policy-v2",
                verification_time=self.now,
            )

    def test_envelope_wrong_epoch_is_rejected(self):
        wrong = replace(self.envelope, authority_epoch=3)
        with self.assertRaises(ContractError):
            ConsistencyCheckpointVerificationRequest(
                expected_domain_id="atlas-main",
                expected_authority_epoch=4,
                expected_position=ConsistencyPosition("atlas-main", 4, 3),
                anchor=self.anchor,
                envelope=wrong,
                trust_policy_version="policy-v2",
                verification_time=self.now,
            )

    def test_wrong_trust_policy_is_rejected(self):
        with self.assertRaises(ContractError):
            ConsistencyCheckpointVerificationRequest(
                expected_domain_id="atlas-main",
                expected_authority_epoch=4,
                expected_position=ConsistencyPosition("atlas-main", 4, 3),
                anchor=self.anchor,
                envelope=self.envelope,
                trust_policy_version="policy-v3",
                verification_time=self.now,
            )

    def test_unknown_or_invalid_algorithm_material_is_not_interpreted_by_model(self):
        # The model carries opaque evidence; algorithm/key trust belongs to verifier.
        self.assertEqual(self.envelope.authentication_evidence, "opaque-auth-evidence")

    def test_verified_state_requires_exact_anchor_position_and_commitment(self):
        state = ConsistencyRecoveryState(
            domain_id="atlas-main",
            authority_epoch=4,
            checkpoint=None,
            entries=(),
            head_sequence=3,
            continuity_reference="structural-reference",
        )
        verified = VerifiedConsistencyRecoveryState(
            state=state,
            anchor=self.anchor,
            authenticated_state_commitment="control-state-commitment",
            verification_id="verification-123",
            verifier_id="checkpoint-verifier",
            trust_policy_version="policy-v2",
            verified_at=self.now,
        )
        self.assertEqual(verified.anchor.anchor_revision, 9)

    def test_verified_state_rejects_rollback_position(self):
        state = ConsistencyRecoveryState(
            domain_id="atlas-main",
            authority_epoch=4,
            checkpoint=None,
            entries=(),
            head_sequence=2,
            continuity_reference="structural-reference",
        )
        with self.assertRaises(ContractError):
            VerifiedConsistencyRecoveryState(
                state=state,
                anchor=self.anchor,
                authenticated_state_commitment="control-state-commitment",
                verification_id="verification-123",
                verifier_id="checkpoint-verifier",
                trust_policy_version="policy-v2",
                verified_at=self.now,
            )

    def test_verified_state_rejects_commitment_mismatch(self):
        state = ConsistencyRecoveryState(
            domain_id="atlas-main",
            authority_epoch=4,
            checkpoint=None,
            entries=(),
            head_sequence=3,
            continuity_reference="structural-reference",
        )
        with self.assertRaises(ContractError):
            VerifiedConsistencyRecoveryState(
                state=state,
                anchor=self.anchor,
                authenticated_state_commitment="different-commitment",
                verification_id="verification-123",
                verifier_id="checkpoint-verifier",
                trust_policy_version="policy-v2",
                verified_at=self.now,
            )

    def test_verification_result_rejects_unverified_state(self):
        with self.assertRaises(ContractError):
            ConsistencyRecoveryVerificationResult(
                ConsistencyRecoveryVerificationStatus.VERIFIED,
                None,
            )

    def test_rejected_result_cannot_carry_verified_state(self):
        state = ConsistencyRecoveryState(
            domain_id="atlas-main",
            authority_epoch=4,
            checkpoint=None,
            entries=(),
            head_sequence=3,
            continuity_reference="structural-reference",
        )
        verified = VerifiedConsistencyRecoveryState(
            state=state,
            anchor=self.anchor,
            authenticated_state_commitment="control-state-commitment",
            verification_id="verification-123",
            verifier_id="checkpoint-verifier",
            trust_policy_version="policy-v2",
            verified_at=self.now,
        )
        with self.assertRaises(ContractError):
            ConsistencyRecoveryVerificationResult(
                ConsistencyRecoveryVerificationStatus.REJECTED,
                verified,
            )

    def test_receipt_trust_context_requires_utc_time_and_exact_purpose(self):
        context = ReceiptTrustContext(
            consistency_domain_id="atlas-main",
            authority_epoch=4,
            canonical_request_reference="request-canonical-17",
            trust_policy_version="policy-v2",
            verification_time=self.now,
            purpose="terminal-admission-reconciliation",
        )
        self.assertEqual(context.purpose, "terminal-admission-reconciliation")


if __name__ == "__main__":
    unittest.main()
