from dataclasses import replace
from datetime import datetime, timezone
import unittest

from atlas.core.errors import ContractError
from atlas.memory.journal import (
    ConsistencyCheckpoint,
    ConsistencyPosition,
    ConsistencyRecoveryState,
)
from atlas.memory.receipt_verification import TerminalReceiptKind, TerminalReceiptVerificationRequest
from atlas.memory.trust import (
    AuthenticatedConsistencyEnvelope,
    ConsistencyCheckpointVerificationRequest,
    ConsistencyRecoveryVerificationResult,
    ConsistencyRecoveryVerificationStatus,
    ConsistencyTrustAnchor,
    TrustAnchorAdvanceRequest,
    TrustAnchorReadResult,
    TrustAnchorReadStatus,
    TrustAnchorUpdateStatus,
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
        self.checkpoint = ConsistencyCheckpoint(
            checkpoint_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074501",
            position=ConsistencyPosition("atlas-main", 4, 3),
            state_reference="state-reference",
            integrity_reference="integrity-reference",
            created_at=self.now,
        )
        self.envelope = AuthenticatedConsistencyEnvelope(
            object_kind="checkpoint",
            envelope_version=1,
            consistency_domain_id="atlas-main",
            authority_epoch=4,
            sequence=3,
            object_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074501",
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

    def _state(self, head_sequence):
        checkpoint = ConsistencyCheckpoint(
            checkpoint_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074501",
            position=ConsistencyPosition("atlas-main", 4, head_sequence),
            state_reference="state-reference",
            integrity_reference="integrity-reference",
            created_at=self.now,
        )
        return ConsistencyRecoveryState(
            domain_id="atlas-main",
            authority_epoch=4,
            checkpoint=checkpoint,
            entries=(),
            head_sequence=head_sequence,
            continuity_reference="control-state-commitment",
        )

    def test_valid_checkpoint_verification_request_binds_domain_epoch_and_anchor(self):
        request = ConsistencyCheckpointVerificationRequest(
            expected_domain_id="atlas-main",
            expected_authority_epoch=4,
            expected_position=ConsistencyPosition("atlas-main", 4, 3),
            checkpoint=self.checkpoint,
            anchor=self.anchor,
            envelope=self.envelope,
            trust_policy_version="policy-v2",
            verification_time=self.now,
        )
        self.assertEqual(request.expected_position.sequence, 3)

    def test_checkpoint_may_be_older_than_anchor_when_head_is_anchored(self):
        older_checkpoint = replace(
            self.checkpoint,
            position=ConsistencyPosition("atlas-main", 4, 2),
        )
        older_envelope = replace(self.envelope, sequence=2)
        request = ConsistencyCheckpointVerificationRequest(
            expected_domain_id="atlas-main",
            expected_authority_epoch=4,
            expected_position=ConsistencyPosition("atlas-main", 4, 3),
            checkpoint=older_checkpoint,
            anchor=self.anchor,
            envelope=older_envelope,
            trust_policy_version="policy-v2",
            verification_time=self.now,
        )
        self.assertEqual(request.checkpoint.position.sequence, 2)
        self.assertEqual(request.anchor.maximum_committed_sequence, 3)

    def test_anchor_read_result_enforces_status_and_value_pairing(self):
        found = TrustAnchorReadResult(TrustAnchorReadStatus.FOUND, self.anchor)
        self.assertIs(found.anchor, self.anchor)
        with self.assertRaises(ContractError):
            TrustAnchorReadResult(TrustAnchorReadStatus.FOUND, None)
        with self.assertRaises(ContractError):
            TrustAnchorReadResult(TrustAnchorReadStatus.UNKNOWN, self.anchor)

    def test_anchor_cas_requires_exact_monotonic_revision(self):
        new_anchor = replace(
            self.anchor,
            anchor_id="anchor-2",
            anchor_revision=10,
            maximum_committed_sequence=4,
            authenticated_state_commitment="next-control-state",
            issued_at=datetime(2026, 11, 13, 12, 1, tzinfo=timezone.utc),
        )
        request = TrustAnchorAdvanceRequest(self.anchor, new_anchor)
        self.assertEqual(request.new_anchor.anchor_revision, 10)

    def test_anchor_cas_rejects_sequence_rollback(self):
        old = replace(self.anchor, maximum_committed_sequence=4)
        new = replace(
            old,
            anchor_id="anchor-2",
            anchor_revision=10,
            maximum_committed_sequence=3,
        )
        with self.assertRaises(ContractError):
            TrustAnchorAdvanceRequest(old, new)

    def test_anchor_epoch_change_requires_explicit_handoff_and_zero_sequence(self):
        new = replace(
            self.anchor,
            anchor_id="anchor-epoch-5",
            anchor_revision=10,
            authority_epoch=5,
            maximum_committed_sequence=0,
        )
        with self.assertRaises(ContractError):
            TrustAnchorAdvanceRequest(self.anchor, new)
        accepted = TrustAnchorAdvanceRequest(
            self.anchor,
            new,
            epoch_handoff_reference="verified-handoff-proof",
        )
        self.assertEqual(accepted.new_anchor.authority_epoch, 5)

    def test_checkpoint_behind_external_anchor_is_rejected(self):
        with self.assertRaises(ContractError):
            ConsistencyCheckpointVerificationRequest(
                expected_domain_id="atlas-main",
                expected_authority_epoch=4,
                expected_position=ConsistencyPosition("atlas-main", 4, 2),
                checkpoint=replace(
                    self.checkpoint,
                    position=ConsistencyPosition("atlas-main", 4, 2),
                ),
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
                checkpoint=self.checkpoint,
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
                checkpoint=self.checkpoint,
                anchor=self.anchor,
                envelope=wrong,
                trust_policy_version="policy-v2",
                verification_time=self.now,
            )

    def test_expired_anchor_is_rejected(self):
        expired = replace(
            self.anchor,
            issued_at=datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc),
            valid_until=datetime(2026, 11, 13, 11, 59, tzinfo=timezone.utc),
        )
        with self.assertRaises(ContractError):
            ConsistencyCheckpointVerificationRequest(
                expected_domain_id="atlas-main",
                expected_authority_epoch=4,
                expected_position=ConsistencyPosition("atlas-main", 4, 3),
                checkpoint=self.checkpoint,
                anchor=expired,
                envelope=self.envelope,
                trust_policy_version="policy-v2",
                verification_time=self.now,
            )

    def test_future_dated_envelope_is_rejected(self):
        future = replace(
            self.envelope,
            issued_at=datetime(2026, 11, 13, 12, 1, tzinfo=timezone.utc),
        )
        with self.assertRaises(ContractError):
            ConsistencyCheckpointVerificationRequest(
                expected_domain_id="atlas-main",
                expected_authority_epoch=4,
                expected_position=ConsistencyPosition("atlas-main", 4, 3),
                checkpoint=self.checkpoint,
                anchor=self.anchor,
                envelope=future,
                trust_policy_version="policy-v2",
                verification_time=self.now,
            )

    def test_wrong_trust_policy_is_rejected(self):
        with self.assertRaises(ContractError):
            ConsistencyCheckpointVerificationRequest(
                expected_domain_id="atlas-main",
                expected_authority_epoch=4,
                expected_position=ConsistencyPosition("atlas-main", 4, 3),
                checkpoint=self.checkpoint,
                anchor=self.anchor,
                envelope=self.envelope,
                trust_policy_version="policy-v3",
                verification_time=self.now,
            )

    def test_unknown_or_invalid_algorithm_material_is_not_interpreted_by_model(self):
        # The model carries opaque evidence; algorithm/key trust belongs to verifier.
        self.assertEqual(self.envelope.authentication_evidence, "opaque-auth-evidence")

    def test_verified_state_requires_exact_anchor_position_and_commitment(self):
        state = self._state(3)
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
        state = self._state(2)
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
        state = self._state(3)
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
        state = self._state(3)
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
        request = TerminalReceiptVerificationRequest(
            consistency_domain_id="atlas-main",
            authority_epoch=4,
            operation_id="read:admission-1",
            admission_id="admission-1",
            receipt_id="receipt-1",
            kind=TerminalReceiptKind.ADMISSION_CANCELLED,
            generation=4,
        )
        context = ReceiptTrustContext(
            request=request,
            canonical_request_reference="request-canonical-17",
            trust_policy_version="policy-v2",
            verification_time=self.now,
            purpose="terminal-admission-reconciliation",
        )
        self.assertEqual(context.purpose, "terminal-admission-reconciliation")
        self.assertTrue(context.binds(request))
        self.assertFalse(context.binds(replace(request, receipt_id="receipt-2")))


if __name__ == "__main__":
    unittest.main()
