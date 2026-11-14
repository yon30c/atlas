"""Adapters from the local Atlas consistency profile to neutral recovery ports.

All profile-specific DTO conversion stays here. Legacy verifiers remain the
authority for authenticating local checkpoint and inventory evidence.
"""
from atlas.core.errors import ContractError
from atlas.memory.ports.recovery import (
    CheckpointProjectionRequest,
    CheckpointProjectionResult,
    RecoveryInventoryRequest,
    RecoveryInventoryResult,
    RecoveryVerificationStatus,
    VerifiedCheckpointProjection,
    VerifiedRecoveryInventories,
    require_verified_checkpoint_projection,
    require_verified_recovery_inventories,
)
from atlas.ports.local_consistency_recovery import (
    CheckpointProjectionResolution,
    LocalCheckpointProjectionRequest,
    LocalConsistencyCheckpointProjectionPort,
    LocalConsistencyInventoryVerificationRequest,
    LocalConsistencyInventoryVerificationResult,
    LocalConsistencyInventoryVerifierPort,
    LocalVerificationStatus,
    require_verified_checkpoint_projection as require_local_checkpoint_projection,
    require_verified_local_inventories,
)


class LocalCheckpointProjectionAdapter:
    """Translate neutral requests to the existing local-profile verifier port."""

    def __init__(self, delegate: LocalConsistencyCheckpointProjectionPort) -> None:
        if delegate is None or not callable(
            getattr(delegate, "resolve_checkpoint_projection", None)
        ):
            raise ContractError("delegate debe implementar resolve_checkpoint_projection")
        self._delegate = delegate

    def resolve_checkpoint_projection(
        self, request: CheckpointProjectionRequest
    ) -> CheckpointProjectionResult:
        local_request = LocalCheckpointProjectionRequest(
            checkpoint=request.checkpoint,
            consistency_domain_id=request.consistency_domain_id,
            authority_epoch=request.authority_epoch,
            trust_policy_version=request.trust_policy_version,
            allowed_schema_versions=request.allowed_schema_versions,
            allowed_reducer_versions=request.allowed_reducer_versions,
        )
        result = self._delegate.resolve_checkpoint_projection(local_request)
        if not isinstance(result, CheckpointProjectionResolution):
            return CheckpointProjectionResult(RecoveryVerificationStatus.REJECTED)
        if result.status is LocalVerificationStatus.UNAVAILABLE:
            return CheckpointProjectionResult(RecoveryVerificationStatus.UNAVAILABLE)
        if result.status is LocalVerificationStatus.REJECTED:
            return CheckpointProjectionResult(RecoveryVerificationStatus.REJECTED)
        try:
            local_evidence = require_local_checkpoint_projection(local_request, result)
            neutral_evidence = VerifiedCheckpointProjection(
            checkpoint_id=local_evidence.checkpoint_id,
            consistency_domain_id=local_evidence.consistency_domain_id,
            authority_epoch=local_evidence.authority_epoch,
            sequence=local_evidence.sequence,
            state_reference=local_evidence.state_reference,
            integrity_reference=local_evidence.integrity_reference,
            state_commitment=local_evidence.state_commitment,
            integrity_commitment=local_evidence.integrity_commitment,
            schema_version=local_evidence.schema_version,
            reducer_version=local_evidence.reducer_version,
            trust_policy_version=local_evidence.trust_policy_version,
            projection=local_evidence.projection,
                verification_id=local_evidence.verification_id,
            )
            neutral_result = CheckpointProjectionResult(
                RecoveryVerificationStatus.VERIFIED, neutral_evidence
            )
            require_verified_checkpoint_projection(request, neutral_result)
            return neutral_result
        except (ContractError, ValueError, TypeError, AttributeError):
            return CheckpointProjectionResult(RecoveryVerificationStatus.REJECTED)


class LocalRecoveryInventoryAdapter:
    """Translate neutral recovery inventory requests to the local-profile verifier."""

    def __init__(self, delegate: LocalConsistencyInventoryVerifierPort) -> None:
        if delegate is None or not callable(
            getattr(delegate, "verify_recovery_inventories", None)
        ):
            raise ContractError("delegate debe implementar verify_recovery_inventories")
        self._delegate = delegate

    def verify_recovery_inventories(
        self, request: RecoveryInventoryRequest
    ) -> RecoveryInventoryResult:
        local_request = LocalConsistencyInventoryVerificationRequest(
            state=request.state,
            projection=request.projection,
            trust_policy_version=request.trust_policy_version,
        )
        result = self._delegate.verify_recovery_inventories(local_request)
        if not isinstance(result, LocalConsistencyInventoryVerificationResult):
            return RecoveryInventoryResult(RecoveryVerificationStatus.REJECTED)
        if result.status is LocalVerificationStatus.UNAVAILABLE:
            return RecoveryInventoryResult(RecoveryVerificationStatus.UNAVAILABLE)
        if result.status is LocalVerificationStatus.REJECTED:
            return RecoveryInventoryResult(RecoveryVerificationStatus.REJECTED)
        try:
            local_evidence = require_verified_local_inventories(local_request, result)
            neutral_evidence = VerifiedRecoveryInventories(
            consistency_domain_id=local_evidence.consistency_domain_id,
            authority_epoch=local_evidence.authority_epoch,
            head_sequence=local_evidence.head_sequence,
            continuity_reference=local_evidence.continuity_reference,
            trust_policy_version=local_evidence.trust_policy_version,
            inventory_commitment=local_evidence.inventory_commitment,
            verified_receipt_ids=local_evidence.verified_receipt_ids,
            verified_tombstone_ids=local_evidence.verified_tombstone_ids,
            verified_reference_ids=local_evidence.verified_reference_ids,
                verification_id=local_evidence.verification_id,
            )
            neutral_result = RecoveryInventoryResult(
                RecoveryVerificationStatus.VERIFIED, neutral_evidence
            )
            require_verified_recovery_inventories(request, neutral_result)
            return neutral_result
        except (ContractError, ValueError, TypeError, AttributeError):
            return RecoveryInventoryResult(RecoveryVerificationStatus.REJECTED)
