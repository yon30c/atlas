"""Consumer-neutral recovery contracts for Memory Engine.

These contracts describe evidence boundaries without importing Atlas journal,
SQLite, reducer or local-profile DTOs. Projection and recovery objects are
structural ports: a consumer adapter supplies its own immutable domain values.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class RecoveryPosition(Protocol):
    consistency_domain_id: str
    authority_epoch: int
    sequence: int


class RecoveryCheckpoint(Protocol):
    checkpoint_id: str
    position: RecoveryPosition
    state_reference: str
    integrity_reference: str


class RecoveryState(Protocol):
    domain_id: str
    authority_epoch: int
    checkpoint: RecoveryCheckpoint | None
    head_sequence: int
    continuity_reference: str


class RecoveryProjection(Protocol):
    domain_id: str
    authority_epoch: int
    head_sequence: int
    replay_metadata_version: int
    receipt_ids: frozenset[str]


class RecoveryVerificationStatus(str, Enum):
    VERIFIED = "verified"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class CheckpointProjectionRequest:
    checkpoint: RecoveryCheckpoint
    consistency_domain_id: str
    authority_epoch: int
    trust_policy_version: str
    allowed_schema_versions: frozenset[int]
    allowed_reducer_versions: frozenset[str]

    def __post_init__(self) -> None:
        _required(self.consistency_domain_id, "consistency_domain_id")
        _required(self.trust_policy_version, "trust_policy_version")
        _positive(self.authority_epoch, "authority_epoch")
        if (
            self.checkpoint.position.consistency_domain_id != self.consistency_domain_id
            or self.checkpoint.position.authority_epoch != self.authority_epoch
        ):
            raise ValueError("checkpoint request pertenece a otro dominio o época")
        if not isinstance(self.allowed_schema_versions, frozenset) or not self.allowed_schema_versions:
            raise ValueError("allowed_schema_versions debe ser frozenset no vacío")
        if not isinstance(self.allowed_reducer_versions, frozenset) or not self.allowed_reducer_versions:
            raise ValueError("allowed_reducer_versions debe ser frozenset no vacío")


@dataclass(frozen=True, slots=True)
class VerifiedCheckpointProjection:
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
    projection: RecoveryProjection
    verification_id: str

    def __post_init__(self) -> None:
        for field in (
            "checkpoint_id", "consistency_domain_id", "state_reference",
            "integrity_reference", "state_commitment", "integrity_commitment",
            "reducer_version", "trust_policy_version", "verification_id",
        ):
            _required(getattr(self, field), field)
        _non_negative(self.sequence, "sequence")
        _positive(self.authority_epoch, "authority_epoch")
        _positive(self.schema_version, "schema_version")
        if (
            self.projection.domain_id != self.consistency_domain_id
            or self.projection.authority_epoch != self.authority_epoch
            or self.projection.head_sequence != self.sequence
            or self.projection.replay_metadata_version != 1
        ):
            raise ValueError("proyección no corresponde exactamente al checkpoint")


@dataclass(frozen=True, slots=True)
class CheckpointProjectionResult:
    status: RecoveryVerificationStatus
    verified_projection: VerifiedCheckpointProjection | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, RecoveryVerificationStatus):
            raise ValueError("status no válido")
        if self.status is RecoveryVerificationStatus.VERIFIED:
            if not isinstance(self.verified_projection, VerifiedCheckpointProjection):
                raise ValueError("VERIFIED requiere proyección")
        elif self.verified_projection is not None:
            raise ValueError("resultado no verificado no puede incluir proyección")


@dataclass(frozen=True, slots=True)
class RecoveryInventoryRequest:
    state: RecoveryState
    projection: RecoveryProjection
    trust_policy_version: str

    def __post_init__(self) -> None:
        _required(self.trust_policy_version, "trust_policy_version")
        if (
            self.projection.domain_id != self.state.domain_id
            or self.projection.authority_epoch != self.state.authority_epoch
            or self.projection.head_sequence != self.state.head_sequence
        ):
            raise ValueError("projection no corresponde al estado recuperado")


@dataclass(frozen=True, slots=True)
class VerifiedRecoveryInventories:
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
            "consistency_domain_id", "continuity_reference", "trust_policy_version",
            "inventory_commitment", "verification_id",
        ):
            _required(getattr(self, field), field)
        _positive(self.authority_epoch, "authority_epoch")
        _non_negative(self.head_sequence, "head_sequence")
        for field in (
            "verified_receipt_ids", "verified_tombstone_ids", "verified_reference_ids"
        ):
            values = getattr(self, field)
            if not isinstance(values, frozenset):
                raise ValueError(f"{field} debe ser frozenset")
            for value in values:
                _required(value, field)


@dataclass(frozen=True, slots=True)
class RecoveryInventoryResult:
    status: RecoveryVerificationStatus
    verified_inventories: VerifiedRecoveryInventories | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, RecoveryVerificationStatus):
            raise ValueError("status no válido")
        if self.status is RecoveryVerificationStatus.VERIFIED:
            if not isinstance(self.verified_inventories, VerifiedRecoveryInventories):
                raise ValueError("VERIFIED requiere inventarios")
        elif self.verified_inventories is not None:
            raise ValueError("resultado no verificado no puede incluir inventarios")


class CheckpointProjectionPort(Protocol):
    def resolve_checkpoint_projection(
        self, request: CheckpointProjectionRequest
    ) -> CheckpointProjectionResult:
        """Authenticate independent checkpoint state and integrity references."""


class RecoveryInventoryVerifierPort(Protocol):
    def verify_recovery_inventories(
        self, request: RecoveryInventoryRequest
    ) -> RecoveryInventoryResult:
        """Prove complete, authenticated inventories for the exact recovered head."""


def require_verified_checkpoint_projection(
    request: CheckpointProjectionRequest,
    result: CheckpointProjectionResult,
) -> VerifiedCheckpointProjection:
    if not isinstance(result, CheckpointProjectionResult):
        raise ValueError("result debe ser CheckpointProjectionResult")
    if result.status is not RecoveryVerificationStatus.VERIFIED:
        raise ValueError("checkpoint projection no está VERIFIED")
    evidence = result.verified_projection
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
    ):
        raise ValueError("evidencia no corresponde a la solicitud exacta")
    return evidence


def require_verified_recovery_inventories(
    request: RecoveryInventoryRequest,
    result: RecoveryInventoryResult,
) -> VerifiedRecoveryInventories:
    if not isinstance(result, RecoveryInventoryResult):
        raise ValueError("result debe ser RecoveryInventoryResult")
    if result.status is not RecoveryVerificationStatus.VERIFIED:
        raise ValueError("inventarios no están VERIFIED")
    evidence = result.verified_inventories
    state = request.state
    if (
        evidence.consistency_domain_id != state.domain_id
        or evidence.authority_epoch != state.authority_epoch
        or evidence.head_sequence != state.head_sequence
        or evidence.continuity_reference != state.continuity_reference
        or evidence.trust_policy_version != request.trust_policy_version
    ):
        raise ValueError("atestación no corresponde al estado exacto")
    return evidence


def _required(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} debe ser una cadena no vacía")


def _positive(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} debe ser entero positivo")


def _non_negative(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} debe ser entero no negativo")
