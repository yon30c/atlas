"""Tests for the local consistency recovery verifier orchestration."""
from dataclasses import replace
from datetime import datetime, timezone
import unittest

from atlas.memory.consistency import (
    AuthorityKind,
    AuthorityRevision,
    AuthorizationRevisionSet,
)
from atlas.memory.envelope import AuthenticatedConsistencyEnvelope
from atlas.memory.journal import (
    ConsistencyCheckpoint,
    ConsistencyPosition,
    ConsistencyRecordKind,
    ConsistencyRecoveryState,
    ConsistencyTransition,
    JournalEntry,
)
from atlas.memory.local_auth import (
    authenticate_envelope, checkpoint_payload, journal_entry_payload,
)
from atlas.memory.local_recovery_verifier import LocalConsistencyRecoveryVerifier
from atlas.memory.local_trust_policy import (
    LocalConsistencyTrustPolicy,
    LocalIssuerAuthorization,
)
from atlas.memory.trust import (
    ConsistencyRecoveryTrustContext,
    ConsistencyRecoveryVerificationStatus,
)
from atlas.ports.local_consistency_recovery import (
    LocalConsistencyInventoryVerificationResult,
    LocalVerificationStatus,
    VerifiedLocalConsistencyInventories,
)

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
DOMAIN = "local-verifier-domain"
KEY = b"v" * 32
MEMORY = "018bcfe5-7b3a-7cc2-98c4-dc0c0c074701"
VERSION = "018bcfe5-7b3a-7cc2-98c4-dc0c0c074702"


def build_recovery_state(with_receipt=False):
    admission_id = "admission-local-verifier"
    admitted = ConsistencyTransition(
        record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074703",
        schema_version=1,
        record_kind=ConsistencyRecordKind.READ_ADMITTED,
        operation_id=f"read:{admission_id}",
        occurred_at=NOW,
        actor_identity_id="identity-local",
        memory_id=MEMORY,
        version_id=VERSION,
        snapshot_id="snapshot-local",
        revisions=AuthorizationRevisionSet(
            memory_revision=AuthorityRevision(AuthorityKind.MEMORY, MEMORY, 1),
            version_revision=AuthorityRevision(AuthorityKind.MEMORY_VERSION, VERSION, 1),
            identity_revision=AuthorityRevision(AuthorityKind.IDENTITY, "identity-local", 1),
        ),
        admission_id=admission_id,
        generation=1,
        route_ids=frozenset({"assistant-response"}),
    )
    plain = JournalEntry(
        ConsistencyPosition(DOMAIN, 1, 1),
        admitted,
    )
    unsigned = AuthenticatedConsistencyEnvelope(
        object_kind="journal_entry",
        envelope_version=1,
        consistency_domain_id=DOMAIN,
        authority_epoch=1,
        sequence=1,
        object_id=admitted.record_id,
        schema_version=1,
        reducer_version="reducer-v1",
        previous_commitment=None,
        object_commitment="0" * 64,
        issuer_id="local-journal",
        issuer_role="consistency-journal",
        key_reference="local-key-1",
        trust_policy_version="local-policy-v1",
        issued_at=NOW,
        authentication_evidence="pending",
    )
    signed = authenticate_envelope(unsigned, journal_entry_payload(plain), KEY)
    entries = [replace(plain, envelope=signed)]
    if with_receipt:
        transition = ConsistencyTransition(
            record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074704",
            schema_version=1,
            record_kind=ConsistencyRecordKind.EGRESS_COMMITTED,
            operation_id=f"read:{admission_id}",
            occurred_at=NOW,
            admission_id=admission_id,
            endpoint_id="assistant-response",
            generation=1,
            emission_id="emission-local-1",
            emission_sequence=1,
            receipt_id="receipt-local-1",
        )
        plain_tail = JournalEntry(
            ConsistencyPosition(DOMAIN, 1, 2),
            transition,
        )
        unsigned_tail = replace(
            unsigned,
            sequence=2,
            object_id=transition.record_id,
            previous_commitment=signed.object_commitment,
            object_commitment="0" * 64,
        )
        signed_tail = authenticate_envelope(
            unsigned_tail, journal_entry_payload(plain_tail), KEY
        )
        entries.append(replace(plain_tail, envelope=signed_tail))
    return ConsistencyRecoveryState(
        domain_id=DOMAIN,
        authority_epoch=1,
        checkpoint=None,
        entries=tuple(entries),
        head_sequence=len(entries),
        continuity_reference=entries[-1].envelope.object_commitment,
    )


class LocalConsistencyRecoveryVerifierTests(unittest.TestCase):
    def setUp(self):
        self.policy = LocalConsistencyTrustPolicy(
            policy_version="local-policy-v1",
            consistency_domain_id=DOMAIN,
            issuer_authorizations=frozenset({
                LocalIssuerAuthorization(
                    "journal_entry", "local-journal", "consistency-journal"
                ),
                LocalIssuerAuthorization(
                    "checkpoint", "local-checkpoint", "consistency-checkpoint"
                ),
            }),
            allowed_key_references=frozenset({"local-key-1"}),
            allowed_envelope_versions=frozenset({1}),
            allowed_canonicalization_versions=frozenset({1}),
            allowed_schema_versions=frozenset({1}),
            allowed_reducer_versions=frozenset({"reducer-v1"}),
        )

        class Keys:
            def load_key(inner_self, key_reference):
                return KEY if key_reference == "local-key-1" else None

        self.keys = Keys()
        self.inventory_status = LocalVerificationStatus.VERIFIED
        self.inventory_receipts = frozenset()

        class Inventory:
            def verify_recovery_inventories(inner_self, request):
                if self.inventory_status is not LocalVerificationStatus.VERIFIED:
                    return LocalConsistencyInventoryVerificationResult(
                        self.inventory_status
                    )
                evidence = VerifiedLocalConsistencyInventories(
                    consistency_domain_id=request.state.domain_id,
                    authority_epoch=request.state.authority_epoch,
                    head_sequence=request.state.head_sequence,
                    continuity_reference=request.state.continuity_reference,
                    trust_policy_version=request.trust_policy_version,
                    inventory_commitment="inventory-commitment",
                    verified_receipt_ids=self.inventory_receipts,
                    verified_tombstone_ids=frozenset(),
                    verified_reference_ids=frozenset({"snapshot-local"}),
                    verification_id="inventory-check-1",
                )
                return LocalConsistencyInventoryVerificationResult(
                    LocalVerificationStatus.VERIFIED, evidence
                )

        self.inventory = Inventory()
        self.verifier = LocalConsistencyRecoveryVerifier(
            trust_policy=self.policy,
            key_port=self.keys,
            inventory_verifier=self.inventory,
            verifier_id="local-recovery-verifier",
        )
        self.context = ConsistencyRecoveryTrustContext(
            consistency_domain_id=DOMAIN,
            authority_epoch=1,
            trust_policy_version="local-policy-v1",
            verification_time=NOW,
            purpose="local-recovery",
        )

    def test_verifies_authenticated_chain_and_complete_inventory(self):
        state = build_recovery_state(with_receipt=True)
        self.inventory_receipts = frozenset({"receipt-local-1"})
        result = self.verifier.verify_recovery_state(state, self.context)
        self.assertIs(result.status, ConsistencyRecoveryVerificationStatus.VERIFIED)
        self.assertIsNotNone(result.verified_local_state)
        self.assertFalse(result.verified_local_state.external_anti_rollback_protected)

    def test_rejects_inventory_missing_a_journal_receipt(self):
        state = build_recovery_state(with_receipt=True)
        self.inventory_receipts = frozenset()
        result = self.verifier.verify_recovery_state(state, self.context)
        self.assertIs(result.status, ConsistencyRecoveryVerificationStatus.REJECTED)

    def test_reports_inventory_unavailable_without_opening_verification(self):
        state = build_recovery_state()
        self.inventory_status = LocalVerificationStatus.UNAVAILABLE
        result = self.verifier.verify_recovery_state(state, self.context)
        self.assertIs(result.status, ConsistencyRecoveryVerificationStatus.UNAVAILABLE)

    def test_reports_missing_historical_key_as_unavailable(self):
        class MissingKey:
            def load_key(inner_self, key_reference):
                return None

        self.verifier = LocalConsistencyRecoveryVerifier(
            trust_policy=self.policy,
            key_port=MissingKey(),
            inventory_verifier=self.inventory,
            verifier_id="local-recovery-verifier",
        )
        result = self.verifier.verify_recovery_state(
            build_recovery_state(), self.context
        )
        self.assertIs(
            result.status,
            ConsistencyRecoveryVerificationStatus.UNAVAILABLE,
        )

    def test_rejects_invalid_chain_commitment(self):
        state = build_recovery_state()
        result = self.verifier.verify_recovery_state(
            replace(state, continuity_reference="wrong-commitment"),
            self.context,
        )
        self.assertIs(result.status, ConsistencyRecoveryVerificationStatus.REJECTED)

    def test_rejects_context_for_another_policy_or_domain(self):
        state = build_recovery_state()
        wrong = replace(self.context, trust_policy_version="other-policy")
        result = self.verifier.verify_recovery_state(state, wrong)
        self.assertIs(result.status, ConsistencyRecoveryVerificationStatus.REJECTED)


    def test_verifies_checkpoint_projection_before_replaying_tail(self):
        from atlas.memory.journal_reducer import ConsistencyJournalReducer
        from atlas.ports.local_consistency_recovery import (
            CheckpointProjectionResolution,
            LocalVerificationStatus,
            VerifiedCheckpointProjection,
        )

        prefix_state = build_recovery_state()
        base_projection = ConsistencyJournalReducer().reduce(prefix_state)
        checkpoint = ConsistencyCheckpoint(
            checkpoint_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074705",
            position=ConsistencyPosition(DOMAIN, 1, 1),
            state_reference="checkpoint-state",
            integrity_reference="checkpoint-integrity",
            created_at=NOW,
        )
        unsigned = AuthenticatedConsistencyEnvelope(
            object_kind="checkpoint",
            envelope_version=1,
            consistency_domain_id=DOMAIN,
            authority_epoch=1,
            sequence=1,
            object_id=checkpoint.checkpoint_id,
            schema_version=1,
            reducer_version="reducer-v1",
            previous_commitment=None,
            object_commitment="0" * 64,
            issuer_id="local-checkpoint",
            issuer_role="consistency-checkpoint",
            key_reference="local-key-1",
            trust_policy_version="local-policy-v1",
            issued_at=NOW,
            authentication_evidence="pending",
        )
        signed = authenticate_envelope(unsigned, checkpoint_payload(checkpoint), KEY)
        checkpoint = replace(checkpoint, envelope=signed)
        state = ConsistencyRecoveryState(
            domain_id=DOMAIN,
            authority_epoch=1,
            checkpoint=checkpoint,
            entries=(),
            head_sequence=1,
            continuity_reference=signed.object_commitment,
        )

        class Checkpoints:
            def resolve_checkpoint_projection(inner_self, request):
                evidence = VerifiedCheckpointProjection(
                    checkpoint_id=checkpoint.checkpoint_id,
                    consistency_domain_id=DOMAIN,
                    authority_epoch=1,
                    sequence=1,
                    state_reference=checkpoint.state_reference,
                    integrity_reference=checkpoint.integrity_reference,
                    state_commitment="checkpoint-state-commitment",
                    integrity_commitment="checkpoint-integrity-commitment",
                    schema_version=1,
                    reducer_version="reducer-v1",
                    trust_policy_version="local-policy-v1",
                    projection=base_projection,
                    verification_id="checkpoint-verification",
                )
                return CheckpointProjectionResolution(
                    LocalVerificationStatus.VERIFIED, evidence
                )

        verifier = LocalConsistencyRecoveryVerifier(
            trust_policy=self.policy,
            key_port=self.keys,
            inventory_verifier=self.inventory,
            checkpoint_projection_port=Checkpoints(),
            verifier_id="local-recovery-verifier",
        )
        result = verifier.verify_recovery_state(state, self.context)
        self.assertIs(result.status, ConsistencyRecoveryVerificationStatus.VERIFIED)

    def test_checkpoint_without_resolver_is_unavailable(self):
        from atlas.memory.local_auth import checkpoint_payload

        checkpoint = ConsistencyCheckpoint(
            checkpoint_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074706",
            position=ConsistencyPosition(DOMAIN, 1, 1),
            state_reference="checkpoint-state",
            integrity_reference="checkpoint-integrity",
            created_at=NOW,
        )
        unsigned = AuthenticatedConsistencyEnvelope(
            object_kind="checkpoint",
            envelope_version=1,
            consistency_domain_id=DOMAIN,
            authority_epoch=1,
            sequence=1,
            object_id=checkpoint.checkpoint_id,
            schema_version=1,
            reducer_version="reducer-v1",
            previous_commitment=None,
            object_commitment="0" * 64,
            issuer_id="local-checkpoint",
            issuer_role="consistency-checkpoint",
            key_reference="local-key-1",
            trust_policy_version="local-policy-v1",
            issued_at=NOW,
            authentication_evidence="pending",
        )
        signed = authenticate_envelope(unsigned, checkpoint_payload(checkpoint), KEY)
        state = ConsistencyRecoveryState(
            domain_id=DOMAIN,
            authority_epoch=1,
            checkpoint=replace(checkpoint, envelope=signed),
            entries=(),
            head_sequence=1,
            continuity_reference=signed.object_commitment,
        )
        result = self.verifier.verify_recovery_state(state, self.context)
        self.assertIs(result.status, ConsistencyRecoveryVerificationStatus.UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
