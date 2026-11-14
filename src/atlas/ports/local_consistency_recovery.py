"""Independent ports for checkpoint projection and recovery inventory verification.

These ports are trust boundaries. Their implementations must use sources and
policies independent of the restored journal. Merely constructing one of the
result DTOs does not authenticate it; only the configured port implementation
may return VERIFIED results to the recovery verifier.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from atlas.core.errors import ContractError
from atlas.memory.journal import ConsistencyCheckpoint, ConsistencyRecoveryState
from atlas.memory.journal_reducer import ConsistencyProjection


def _required(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacía")


def _non_negative(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractError(f"{field} debe ser entero no negativo")


class LocalVerificationStatus(str, Enum):
    VERIFIED = "verified"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class LocalCheckpointProjectionRequest:
    checkpoint: ConsistencyCheckpoint
    consistency_domain_id: str
    authority_epoch: int
    trust_policy_version: str
    allowed_schema_versions: frozenset[int]
    allowed_reducer_versions: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.checkpoint, ConsistencyCheckpoint):
            raise ContractError("checkpoint debe ser ConsistencyCheckpoint")
        _required(self.consistency_domain_id, "consistency_domain_id")
        _required(self.trust_policy_version, "trust_policy_version")
        if self.checkpoint.position.consistency_domain_id != self.consistency_domain_id:
            raise ContractError("checkpoint request pertenece a otro dominio")
        if self.checkpoint.position.authority_epoch != self.authority_epoch:
            raise ContractError("checkpoint request pertenece a otra época")
        if isinstance(self.authority_epoch, bool) or not isinstance(self.authority_epoch, int) or self.authority_epoch < 1:
            raise ContractError("authority_epoch debe ser positivo")
        if not isinstance(self.allowed_schema_versions, frozenset) or not self.allowed_schema_versions:
            raise ContractError("allowed_schema_versions debe ser frozenset no vacío")
        if not isinstance(self.allowed_reducer_versions, frozenset) or not self.allowed_reducer_versions:
            raise ContractError("allowed_reducer_versions debe ser frozenset no vacío")


@dataclass(frozen=True, slots=True)
class VerifiedCheckpointProjection:
    """Projection reconstructed from checkpoint state and integrity references."""

    checkpoint_id: str
    consistency_domain_id: str
    authority_epoch: int
    sequence: int
    state_reference: str
    integrity_reference: str
    state_commitment: str
    integrity_commitment: str
    schema_version: int
    reducer_version: str
    trust_policy_version: str
    projection: ConsistencyProjection
    verification_id: str

    def __post_init__(self) -> None:
        for field in (
            "checkpoint_id", "consistency_domain_id", "state_reference",
            "integrity_reference", "state_commitment", "integrity_commitment",
            "reducer_version", "trust_policy_version", "verification_id",
        ):
            _required(getattr(self, field), field)
        _non_negative(self.sequence, "sequence")
        if not isinstance(self.projection, ConsistencyProjection):
            raise ContractError("projection debe ser ConsistencyProjection")
        if (
            self.projection.domain_id != self.consistency_domain_id
            or self.projection.authority_epoch != self.authority_epoch
            or self.projection.head_sequence != self.sequence
        ):
            raise ContractError("proyección base no coincide con checkpoint")
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int) or self.schema_version < 1:
            raise ContractError("schema_version debe ser positivo")
        if isinstance(self.authority_epoch, bool) or not isinstance(self.authority_epoch, int) or self.authority_epoch < 1:
            raise ContractError("authority_epoch debe ser positivo")


@dataclass(frozen=True, slots=True)
class CheckpointProjectionResolution:
    status: LocalVerificationStatus
    verified_projection: VerifiedCheckpointProjection | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, LocalVerificationStatus):
            raise ContractError("status debe ser LocalVerificationStatus")
        if self.status is LocalVerificationStatus.VERIFIED:
            if not isinstance(self.verified_projection, VerifiedCheckpointProjection):
                raise ContractError("VERIFIED requiere VerifiedCheckpointProjection")
        elif self.verified_projection is not None:
            raise ContractError("REJECTED/UNAVAILABLE no pueden incluir proyección")


def require_verified_checkpoint_projection(
    request: LocalCheckpointProjectionRequest,
    resolution: CheckpointProjectionResolution,
) -> VerifiedCheckpointProjection:
    """Return evidence only when it is bound to the exact trusted request."""
    if not isinstance(request, LocalCheckpointProjectionRequest):
        raise ContractError("request debe ser LocalCheckpointProjectionRequest")
    if not isinstance(resolution, CheckpointProjectionResolution):
        raise ContractError("resolution debe ser CheckpointProjectionResolution")
    if resolution.status is not LocalVerificationStatus.VERIFIED:
        raise ContractError("resolución de checkpoint no está VERIFIED")
    evidence = resolution.verified_projection
    checkpoint = request.checkpoint
    if (
        evidence.checkpoint_id != checkpoint.checkpoint_id
        or evidence.consistency_domain_id != request.consistency_domain_id
        or evidence.authority_epoch != request.authority_epoch
        or evidence.sequence != checkpoint.position.sequence
        or evidence.state_reference != checkpoint.state_reference
        or evidence.integrity_reference != checkpoint.integrity_reference
        or evidence.trust_policy_version != request.trust_policy_version
        or evidence.schema_version not in request.allowed_schema_versions
        or evidence.reducer_version not in request.allowed_reducer_versions
        or evidence.projection.replay_metadata_version != 1
    ):
        raise ContractError("evidencia VERIFIED no corresponde a la solicitud exacta")
    return evidence


class LocalConsistencyCheckpointProjectionPort(Protocol):
    """Resolve and authenticate a checkpoint's opaque base-state references."""

    def resolve_checkpoint_projection(
        self, request: LocalCheckpointProjectionRequest
    ) -> CheckpointProjectionResolution:
        """Return VERIFIED only after validating state and integrity references.

        The implementation must not trust the restored journal to supply or
        broaden the trust policy. Missing references, unsupported versions,
        incomplete state, mismatched commitment or unavailable source fail closed.
        """


@dataclass(frozen=True, slots=True)
class LocalConsistencyInventoryVerificationRequest:
    state: ConsistencyRecoveryState
    projection: ConsistencyProjection
    trust_policy_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.state, ConsistencyRecoveryState):
            raise ContractError("state debe ser ConsistencyRecoveryState")
        if not isinstance(self.projection, ConsistencyProjection):
            raise ContractError("projection debe ser ConsistencyProjection")
        _required(self.trust_policy_version, "trust_policy_version")
        if (
            self.projection.domain_id != self.state.domain_id
            or self.projection.authority_epoch != self.state.authority_epoch
            or self.projection.head_sequence != self.state.head_sequence
        ):
            raise ContractError("projection no corresponde al estado recuperado")


@dataclass(frozen=True, slots=True)
class VerifiedLocalConsistencyInventories:
    """Attestation that all externally referenced recovery inventories are complete."""

    consistency_domain_id: str
    authority_epoch: int
    head_sequence: int
    continuity_reference: str
    trust_policy_version: str
    inventory_commitment: str
    verified_receipt_ids: frozenset[str]
    verified_tombstone_ids: frozenset[str]
    verified_reference_ids: frozenset[str]
    verification_id: str

    def __post_init__(self) -> None:
        for field in (
            "consistency_domain_id", "continuity_reference",
            "trust_policy_version", "inventory_commitment", "verification_id",
        ):
            _required(getattr(self, field), field)
        _non_negative(self.head_sequence, "head_sequence")
        if isinstance(self.authority_epoch, bool) or not isinstance(self.authority_epoch, int) or self.authority_epoch < 1:
            raise ContractError("authority_epoch debe ser positivo")
        for field in (
            "verified_receipt_ids", "verified_tombstone_ids", "verified_reference_ids"
        ):
            values = getattr(self, field)
            if not isinstance(values, frozenset):
                raise ContractError(f"{field} debe ser frozenset")
            for value in values:
                _required(value, field)


@dataclass(frozen=True, slots=True)
class LocalConsistencyInventoryVerificationResult:
    status: LocalVerificationStatus
    verified_inventories: VerifiedLocalConsistencyInventories | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, LocalVerificationStatus):
            raise ContractError("status debe ser LocalVerificationStatus")
        if self.status is LocalVerificationStatus.VERIFIED:
            if not isinstance(self.verified_inventories, VerifiedLocalConsistencyInventories):
                raise ContractError("VERIFIED requiere inventarios autenticados")
        elif self.verified_inventories is not None:
            raise ContractError("REJECTED/UNAVAILABLE no pueden incluir inventarios")


class LocalConsistencyInventoryVerifierPort(Protocol):
    """Verify completeness and authenticity of every external recovery inventory."""

    def verify_recovery_inventories(
        self, request: LocalConsistencyInventoryVerificationRequest
    ) -> LocalConsistencyInventoryVerificationResult:
        """Verify receipts, tombstones, referenced objects and pending operations.

        VERIFIED must bind the exact domain, epoch, head, continuity commitment
        and policy version from the request. It must prove completeness, not
        merely validate the IDs listed by the restored journal. Any missing,
        extra, duplicate, unauthenticated or unresolvable item fails closed.
        """
