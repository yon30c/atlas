"""Orchestrator for local-profile consistency recovery verification.

This verifier composes cryptographic chain verification, checkpoint projection
resolution, semantic replay and independent inventory verification. It does not
provide storage adapters or external anti-rollback protection.
"""
from atlas.core.errors import ContractError
from atlas.memory.journal import ConsistencyRecoveryState
from atlas.memory.journal_reducer import ConsistencyJournalReducer
from atlas.memory.local_auth import verify_recovery_chain_with_policy
from atlas.memory.local_trust_policy import LocalConsistencyTrustPolicy
from atlas.memory.trust import (
    ConsistencyRecoveryTrustContext,
    ConsistencyRecoveryVerificationResult,
    ConsistencyRecoveryVerificationStatus,
    VerifiedLocalConsistencyRecoveryState,
)
from atlas.ports.local_consistency_keys import LocalConsistencyKeyPort
from atlas.ports.local_consistency_recovery import (
    CheckpointProjectionResolution,
    LocalCheckpointProjectionRequest,
    LocalConsistencyCheckpointProjectionPort,
    LocalConsistencyInventoryVerificationRequest,
    LocalConsistencyInventoryVerificationResult,
    LocalConsistencyInventoryVerifierPort,
    LocalVerificationStatus,
    require_verified_checkpoint_projection,
    require_verified_local_inventories,
)


class LocalConsistencyRecoveryVerifier:
    """Verify a local recovery set without claiming external anti-rollback."""

    def __init__(
        self,
        *,
        trust_policy: LocalConsistencyTrustPolicy,
        key_port: LocalConsistencyKeyPort,
        inventory_verifier: LocalConsistencyInventoryVerifierPort,
        verifier_id: str,
        checkpoint_projection_port: LocalConsistencyCheckpointProjectionPort | None = None,
        reducer: ConsistencyJournalReducer | None = None,
    ) -> None:
        if not isinstance(trust_policy, LocalConsistencyTrustPolicy):
            raise ContractError("trust_policy debe ser LocalConsistencyTrustPolicy")
        if not isinstance(verifier_id, str) or not verifier_id.strip():
            raise ContractError("verifier_id debe ser una cadena no vacía")
        self._trust_policy = trust_policy
        self._key_port = key_port
        self._inventory_verifier = inventory_verifier
        self._checkpoint_projection_port = checkpoint_projection_port
        self._verifier_id = verifier_id
        self._reducer = reducer or ConsistencyJournalReducer()

    @staticmethod
    def _result(
        status: ConsistencyRecoveryVerificationStatus,
    ) -> ConsistencyRecoveryVerificationResult:
        return ConsistencyRecoveryVerificationResult(status=status)

    def verify_recovery_state(
        self,
        state: ConsistencyRecoveryState,
        trust_context: ConsistencyRecoveryTrustContext,
    ) -> ConsistencyRecoveryVerificationResult:
        """Return VERIFIED only after every local verification boundary succeeds."""
        if not isinstance(state, ConsistencyRecoveryState) or not isinstance(
            trust_context, ConsistencyRecoveryTrustContext
        ):
            return self._result(ConsistencyRecoveryVerificationStatus.REJECTED)
        if (
            state.domain_id != self._trust_policy.consistency_domain_id
            or trust_context.consistency_domain_id != state.domain_id
            or trust_context.authority_epoch != state.authority_epoch
            or trust_context.trust_policy_version != self._trust_policy.policy_version
        ):
            return self._result(ConsistencyRecoveryVerificationStatus.REJECTED)

        if not verify_recovery_chain_with_policy(
            state, self._key_port, self._trust_policy
        ):
            return self._result(ConsistencyRecoveryVerificationStatus.REJECTED)

        base_projection = None
        if state.checkpoint is not None:
            if self._checkpoint_projection_port is None:
                return self._result(ConsistencyRecoveryVerificationStatus.UNAVAILABLE)
            try:
                request = LocalCheckpointProjectionRequest(
                    checkpoint=state.checkpoint,
                    consistency_domain_id=state.domain_id,
                    authority_epoch=state.authority_epoch,
                    trust_policy_version=self._trust_policy.policy_version,
                    allowed_schema_versions=self._trust_policy.allowed_schema_versions,
                    allowed_reducer_versions=self._trust_policy.allowed_reducer_versions,
                )
                resolution = self._checkpoint_projection_port.resolve_checkpoint_projection(
                    request
                )
            except Exception:
                return self._result(ConsistencyRecoveryVerificationStatus.UNAVAILABLE)
            if not isinstance(resolution, CheckpointProjectionResolution):
                return self._result(ConsistencyRecoveryVerificationStatus.REJECTED)
            if resolution.status is LocalVerificationStatus.UNAVAILABLE:
                return self._result(ConsistencyRecoveryVerificationStatus.UNAVAILABLE)
            if resolution.status is LocalVerificationStatus.REJECTED:
                return self._result(ConsistencyRecoveryVerificationStatus.REJECTED)
            try:
                base_projection = require_verified_checkpoint_projection(
                    request, resolution
                ).projection
            except ContractError:
                return self._result(ConsistencyRecoveryVerificationStatus.REJECTED)

        try:
            projection = (
                self._reducer.reduce_from_projection(state, base_projection)
                if state.checkpoint is not None
                else self._reducer.reduce(state)
            )
        except ContractError:
            return self._result(ConsistencyRecoveryVerificationStatus.REJECTED)
        except Exception:
            return self._result(ConsistencyRecoveryVerificationStatus.REJECTED)

        try:
            inventory_request = LocalConsistencyInventoryVerificationRequest(
                state=state,
                projection=projection,
                trust_policy_version=self._trust_policy.policy_version,
            )
            inventory_result = self._inventory_verifier.verify_recovery_inventories(
                inventory_request
            )
        except Exception:
            return self._result(ConsistencyRecoveryVerificationStatus.UNAVAILABLE)
        if not isinstance(
            inventory_result, LocalConsistencyInventoryVerificationResult
        ):
            return self._result(ConsistencyRecoveryVerificationStatus.REJECTED)
        if inventory_result.status is LocalVerificationStatus.UNAVAILABLE:
            return self._result(ConsistencyRecoveryVerificationStatus.UNAVAILABLE)
        if inventory_result.status is LocalVerificationStatus.REJECTED:
            return self._result(ConsistencyRecoveryVerificationStatus.REJECTED)
        try:
            inventories = require_verified_local_inventories(
                inventory_request, inventory_result
            )
        except ContractError:
            return self._result(ConsistencyRecoveryVerificationStatus.REJECTED)

        if not projection.receipt_ids.issubset(inventories.verified_receipt_ids):
            return self._result(ConsistencyRecoveryVerificationStatus.REJECTED)

        verified = VerifiedLocalConsistencyRecoveryState(
            state=state,
            consistency_domain_id=state.domain_id,
            authority_epoch=state.authority_epoch,
            head_sequence=state.head_sequence,
            local_state_commitment=state.continuity_reference,
            verification_id=(
                f"local-recovery:{inventories.verification_id}:"
                f"{inventories.inventory_commitment}"
            ),
            verifier_id=self._verifier_id,
            trust_policy_version=self._trust_policy.policy_version,
            verified_at=trust_context.verification_time,
        )
        return ConsistencyRecoveryVerificationResult(
            status=ConsistencyRecoveryVerificationStatus.VERIFIED,
            verified_local_state=verified,
        )
