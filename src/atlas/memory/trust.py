"""Typed trust, anti-rollback and verified-recovery contracts for ME-03K.

These value objects describe evidence and trust decisions. They do not implement
cryptography, key custody, durable anchoring or distributed consensus.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from atlas.core.errors import ContractError
from atlas.memory.journal import (
    ConsistencyCheckpoint,
    ConsistencyPosition,
    ConsistencyRecoveryState,
)


def _required(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacía")


def _positive(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractError(f"{field} debe ser un entero positivo")


def _utc(value: object, field: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ContractError(f"{field} debe ser datetime UTC")


@dataclass(frozen=True, slots=True)
class ConsistencyTrustAnchor:
    """Externally maintained monotonic anti-rollback anchor.

    authenticated_state_commitment is a commitment to control-plane journal
    state only. It must never be a memory-content hash or content derivative.
    """

    anchor_id: str
    consistency_domain_id: str
    authority_epoch: int
    maximum_committed_sequence: int
    authenticated_state_commitment: str
    issuer_id: str
    key_reference: str
    trust_policy_version: str
    anchor_revision: int
    issued_at: datetime
    valid_until: datetime | None = None

    def __post_init__(self) -> None:
        for field in (
            "anchor_id", "consistency_domain_id", "authenticated_state_commitment",
            "issuer_id", "key_reference", "trust_policy_version",
        ):
            _required(getattr(self, field), field)
        _positive(self.authority_epoch, "authority_epoch")
        if (
            isinstance(self.maximum_committed_sequence, bool)
            or not isinstance(self.maximum_committed_sequence, int)
            or self.maximum_committed_sequence < 0
        ):
            raise ContractError("maximum_committed_sequence debe ser no negativo")
        _positive(self.anchor_revision, "anchor_revision")
        _utc(self.issued_at, "issued_at")
        if self.valid_until is not None:
            _utc(self.valid_until, "valid_until")
            if self.valid_until <= self.issued_at:
                raise ContractError("valid_until debe ser posterior a issued_at")


class TrustAnchorReadStatus(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"


class TrustAnchorUpdateStatus(str, Enum):
    UPDATED = "updated"
    REPLAYED = "replayed"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class TrustAnchorReadResult:
    status: TrustAnchorReadStatus
    anchor: ConsistencyTrustAnchor | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, TrustAnchorReadStatus):
            raise ContractError("status debe ser TrustAnchorReadStatus")
        if self.status is TrustAnchorReadStatus.FOUND:
            if not isinstance(self.anchor, ConsistencyTrustAnchor):
                raise ContractError("FOUND requiere ancla")
        elif self.anchor is not None:
            raise ContractError("NOT_FOUND/UNKNOWN no pueden incluir ancla")


@dataclass(frozen=True, slots=True)
class TrustAnchorAdvanceRequest:
    expected_anchor: ConsistencyTrustAnchor
    new_anchor: ConsistencyTrustAnchor
    epoch_handoff_reference: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.expected_anchor, ConsistencyTrustAnchor):
            raise ContractError("expected_anchor debe ser ConsistencyTrustAnchor")
        if not isinstance(self.new_anchor, ConsistencyTrustAnchor):
            raise ContractError("new_anchor debe ser ConsistencyTrustAnchor")
        old = self.expected_anchor
        new = self.new_anchor
        if new.consistency_domain_id != old.consistency_domain_id:
            raise ContractError("no se puede cambiar el dominio del ancla")
        if new.anchor_revision != old.anchor_revision + 1:
            raise ContractError("anchor_revision debe avanzar exactamente una unidad")
        if new.issued_at < old.issued_at:
            raise ContractError("issued_at del ancla no puede retroceder")
        if new.anchor_id == old.anchor_id:
            raise ContractError("cada revisión requiere un anchor_id distinto")
        if new.authority_epoch == old.authority_epoch:
            if new.maximum_committed_sequence < old.maximum_committed_sequence:
                raise ContractError("la secuencia del ancla no puede retroceder")
            if (
                new.maximum_committed_sequence == old.maximum_committed_sequence
                and new.authenticated_state_commitment != old.authenticated_state_commitment
            ):
                raise ContractError("no puede cambiar el commitment sin avanzar secuencia")
            if self.epoch_handoff_reference is not None:
                raise ContractError("handoff no aplica dentro de la misma época")
        elif new.authority_epoch == old.authority_epoch + 1:
            _required(self.epoch_handoff_reference, "epoch_handoff_reference")
            if new.maximum_committed_sequence != 0:
                raise ContractError("una época nueva comienza en secuencia cero")
        else:
            raise ContractError("cambio de época debe ser exactamente +1")


@dataclass(frozen=True, slots=True)
class AuthenticatedConsistencyEnvelope:
    """Opaque authentication envelope bound to one exact journal/checkpoint object."""

    object_kind: str
    envelope_version: int
    consistency_domain_id: str
    authority_epoch: int
    sequence: int
    object_id: str
    schema_version: int
    reducer_version: str
    previous_commitment: str | None
    object_commitment: str
    issuer_id: str
    issuer_role: str
    key_reference: str
    trust_policy_version: str
    issued_at: datetime
    authentication_evidence: str

    def __post_init__(self) -> None:
        for field in (
            "object_kind", "consistency_domain_id", "object_id", "reducer_version",
            "object_commitment", "issuer_id", "issuer_role", "key_reference",
            "trust_policy_version", "authentication_evidence",
        ):
            _required(getattr(self, field), field)
        _positive(self.envelope_version, "envelope_version")
        _positive(self.authority_epoch, "authority_epoch")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 0:
            raise ContractError("sequence debe ser no negativo")
        _positive(self.schema_version, "schema_version")
        if self.previous_commitment is not None:
            _required(self.previous_commitment, "previous_commitment")
        _utc(self.issued_at, "issued_at")


@dataclass(frozen=True, slots=True)
class ConsistencyCheckpointVerificationRequest:
    expected_domain_id: str
    expected_authority_epoch: int
    expected_position: ConsistencyPosition
    checkpoint: ConsistencyCheckpoint
    anchor: ConsistencyTrustAnchor
    envelope: AuthenticatedConsistencyEnvelope
    trust_policy_version: str
    verification_time: datetime

    def __post_init__(self) -> None:
        _required(self.expected_domain_id, "expected_domain_id")
        _positive(self.expected_authority_epoch, "expected_authority_epoch")
        _required(self.trust_policy_version, "trust_policy_version")
        _utc(self.verification_time, "verification_time")
        if not isinstance(self.expected_position, ConsistencyPosition):
            raise ContractError("expected_position debe ser ConsistencyPosition")
        if not isinstance(self.checkpoint, ConsistencyCheckpoint):
            raise ContractError("checkpoint debe ser ConsistencyCheckpoint")
        if not isinstance(self.anchor, ConsistencyTrustAnchor):
            raise ContractError("anchor debe ser ConsistencyTrustAnchor")
        if not isinstance(self.envelope, AuthenticatedConsistencyEnvelope):
            raise ContractError("envelope debe ser AuthenticatedConsistencyEnvelope")
        if (
            self.expected_position.consistency_domain_id != self.expected_domain_id
            or self.expected_position.authority_epoch != self.expected_authority_epoch
            or self.checkpoint.position.consistency_domain_id != self.expected_domain_id
            or self.checkpoint.position.authority_epoch != self.expected_authority_epoch
            or self.checkpoint.position.sequence > self.expected_position.sequence
            or self.envelope.object_id != self.checkpoint.checkpoint_id
            or self.anchor.consistency_domain_id != self.expected_domain_id
            or self.anchor.authority_epoch != self.expected_authority_epoch
        ):
            raise ContractError("dominio/época no coinciden entre solicitud y ancla")
        if (
            self.envelope.consistency_domain_id != self.expected_domain_id
            or self.envelope.authority_epoch != self.expected_authority_epoch
            or self.envelope.sequence != self.checkpoint.position.sequence
            or self.envelope.trust_policy_version != self.trust_policy_version
            or self.envelope.object_kind != "checkpoint"
        ):
            raise ContractError("envelope no coincide con la solicitud exacta")
        if self.expected_position.sequence != self.anchor.maximum_committed_sequence:
            raise ContractError("posición recuperada debe coincidir con la secuencia máxima del ancla")
        if self.anchor.trust_policy_version != self.trust_policy_version:
            raise ContractError("política de confianza no coincide con el ancla")
        if self.anchor.issued_at > self.verification_time:
            raise ContractError("ancla emitida después del instante de verificación")
        if self.anchor.valid_until is not None and self.verification_time >= self.anchor.valid_until:
            raise ContractError("ancla expirada")
        if self.envelope.issued_at > self.verification_time:
            raise ContractError("envelope emitido después del instante de verificación")


class CheckpointVerificationStatus(str, Enum):
    VERIFIED = "verified"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class VerifiedConsistencyCheckpoint:
    checkpoint: ConsistencyCheckpoint
    anchor: ConsistencyTrustAnchor
    checkpoint_commitment: str
    verification_id: str
    verifier_id: str
    trust_policy_version: str
    verified_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.checkpoint, ConsistencyCheckpoint):
            raise ContractError("checkpoint debe ser ConsistencyCheckpoint")
        if not isinstance(self.anchor, ConsistencyTrustAnchor):
            raise ContractError("anchor debe ser ConsistencyTrustAnchor")
        for field in (
            "checkpoint_commitment", "verification_id",
            "verifier_id", "trust_policy_version",
        ):
            _required(getattr(self, field), field)
        if (
            self.checkpoint.position.consistency_domain_id != self.anchor.consistency_domain_id
            or self.checkpoint.position.authority_epoch != self.anchor.authority_epoch
            or self.checkpoint.position.sequence > self.anchor.maximum_committed_sequence
        ):
            raise ContractError("checkpoint no satisface la posición del ancla")
        if self.trust_policy_version != self.anchor.trust_policy_version:
            raise ContractError("trust policy no coincide con el ancla")
        if (
            self.checkpoint.position.sequence == self.anchor.maximum_committed_sequence
            and self.checkpoint_commitment != self.anchor.authenticated_state_commitment
        ):
            raise ContractError("checkpoint en head debe coincidir con commitment del ancla")
        _utc(self.verified_at, "verified_at")
        if self.verified_at < self.anchor.issued_at:
            raise ContractError("verified_at no puede preceder la emisión del ancla")
        if self.anchor.valid_until is not None and self.verified_at >= self.anchor.valid_until:
            raise ContractError("ancla expirada al verificar checkpoint")


@dataclass(frozen=True, slots=True)
class CheckpointVerificationResult:
    status: CheckpointVerificationStatus
    verified_checkpoint: VerifiedConsistencyCheckpoint | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, CheckpointVerificationStatus):
            raise ContractError("status debe ser CheckpointVerificationStatus")
        if self.status is CheckpointVerificationStatus.VERIFIED:
            if not isinstance(self.verified_checkpoint, VerifiedConsistencyCheckpoint):
                raise ContractError("VERIFIED requiere VerifiedConsistencyCheckpoint")
        elif self.verified_checkpoint is not None:
            raise ContractError("REJECTED/UNAVAILABLE no pueden incluir checkpoint verificado")


@dataclass(frozen=True, slots=True)
class VerifiedConsistencyRecoveryState:
    """State admitted to the reducer only after independent trust verification."""

    state: ConsistencyRecoveryState
    anchor: ConsistencyTrustAnchor
    authenticated_state_commitment: str
    verification_id: str
    verifier_id: str
    trust_policy_version: str
    verified_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.state, ConsistencyRecoveryState):
            raise ContractError("state debe ser ConsistencyRecoveryState")
        if not isinstance(self.anchor, ConsistencyTrustAnchor):
            raise ContractError("anchor debe ser ConsistencyTrustAnchor")
        for field in (
            "authenticated_state_commitment", "verification_id",
            "verifier_id", "trust_policy_version",
        ):
            _required(getattr(self, field), field)
        if self.anchor.consistency_domain_id != self.state.domain_id:
            raise ContractError("ancla y estado pertenecen a dominios distintos")
        if self.anchor.authority_epoch != self.state.authority_epoch:
            raise ContractError("ancla y estado pertenecen a épocas distintas")
        if self.anchor.maximum_committed_sequence != self.state.head_sequence:
            raise ContractError("head_sequence no coincide con la posición máxima del ancla")
        if self.anchor.authenticated_state_commitment != self.authenticated_state_commitment:
            raise ContractError("commitment no coincide con el ancla")
        if self.state.continuity_reference != self.authenticated_state_commitment:
            raise ContractError("continuity_reference no coincide con el commitment verificado")
        if self.trust_policy_version != self.anchor.trust_policy_version:
            raise ContractError("trust policy no coincide con el ancla")
        _utc(self.verified_at, "verified_at")
        if self.verified_at < self.anchor.issued_at:
            raise ContractError("verified_at no puede preceder la emisión del ancla")
        if self.anchor.valid_until is not None and self.verified_at >= self.anchor.valid_until:
            raise ContractError("ancla expirada al verificar el estado")


class ConsistencyRecoveryVerificationStatus(str, Enum):
    VERIFIED = "verified"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ConsistencyRecoveryVerificationResult:
    status: ConsistencyRecoveryVerificationStatus
    verified_state: VerifiedConsistencyRecoveryState | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ConsistencyRecoveryVerificationStatus):
            raise ContractError("status debe ser ConsistencyRecoveryVerificationStatus")
        if self.status is ConsistencyRecoveryVerificationStatus.VERIFIED:
            if not isinstance(self.verified_state, VerifiedConsistencyRecoveryState):
                raise ContractError("VERIFIED requiere VerifiedConsistencyRecoveryState")
        elif self.verified_state is not None:
            raise ContractError("REJECTED/UNAVAILABLE no pueden incluir estado verificado")


@dataclass(frozen=True, slots=True)
class ConsistencyRecoveryTrustContext:
    consistency_domain_id: str
    authority_epoch: int
    trust_policy_version: str
    verification_time: datetime
    purpose: str

    def __post_init__(self) -> None:
        for field in (
            "consistency_domain_id", "trust_policy_version", "purpose",
        ):
            _required(getattr(self, field), field)
        _positive(self.authority_epoch, "authority_epoch")
        _utc(self.verification_time, "verification_time")


class TrustedReceiptKind(str, Enum):
    ENDPOINT_COMPLETED = "endpoint_completed"
    ENDPOINT_FENCED = "endpoint_fenced"
    ADMISSION_COMPLETED = "admission_completed"
    ADMISSION_CANCELLED = "admission_cancelled"
    RECOVERY_COMPLETED = "recovery_completed"


@dataclass(frozen=True, slots=True)
class ReceiptTrustContext:
    consistency_domain_id: str
    authority_epoch: int
    operation_id: str
    expected_receipt_kind: TrustedReceiptKind
    canonical_request_reference: str
    trust_policy_version: str
    verification_time: datetime
    purpose: str
    expected_receipt_id: str | None = None
    admission_id: str | None = None
    endpoint_id: str | None = None
    generation: int | None = None
    previous_generation: int | None = None
    final_sequence: int | None = None
    fenced_through_sequence: int | None = None
    affected_admission_ids: frozenset[str] = frozenset()
    route_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        for field in (
            "consistency_domain_id", "operation_id", "canonical_request_reference",
            "trust_policy_version", "purpose",
        ):
            _required(getattr(self, field), field)
        _positive(self.authority_epoch, "authority_epoch")
        if not isinstance(self.expected_receipt_kind, TrustedReceiptKind):
            raise ContractError("expected_receipt_kind debe ser TrustedReceiptKind")
        _utc(self.verification_time, "verification_time")
        _required(self.expected_receipt_id, "expected_receipt_id")
        for field in ("admission_id", "endpoint_id"):
            value = getattr(self, field)
            if value is not None:
                _required(value, field)
        for field in ("generation", "previous_generation"):
            value = getattr(self, field)
            if value is not None:
                _positive(value, field)
        for field in ("final_sequence", "fenced_through_sequence"):
            value = getattr(self, field)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ContractError(f"{field} debe ser entero no negativo")
        for field in ("affected_admission_ids", "route_ids"):
            values = getattr(self, field)
            if not isinstance(values, frozenset):
                raise ContractError(f"{field} debe ser frozenset")
            for value in values:
                _required(value, field)
        if self.expected_receipt_kind is not TrustedReceiptKind.RECOVERY_COMPLETED:
            _positive(self.generation, "generation")
        if self.expected_receipt_kind in (
            TrustedReceiptKind.ENDPOINT_COMPLETED,
            TrustedReceiptKind.ENDPOINT_FENCED,
        ):
            _required(self.admission_id, "admission_id")
            _required(self.endpoint_id, "endpoint_id")
        elif self.expected_receipt_kind in (
            TrustedReceiptKind.ADMISSION_COMPLETED,
            TrustedReceiptKind.ADMISSION_CANCELLED,
        ):
            _required(self.admission_id, "admission_id")
            if self.endpoint_id is not None:
                raise ContractError("recibo de admisión no admite endpoint_id")
        elif self.expected_receipt_kind is TrustedReceiptKind.RECOVERY_COMPLETED:
            if any(value is not None for value in (
                self.admission_id, self.endpoint_id, self.previous_generation,
                self.final_sequence, self.fenced_through_sequence,
            )):
                raise ContractError("recibo global no admite claims de endpoint/admisión") 
        if self.expected_receipt_kind is TrustedReceiptKind.ENDPOINT_FENCED:
            _positive(self.previous_generation, "previous_generation")
            if self.generation <= self.previous_generation:
                raise ContractError("fencing debe avanzar generación")
            if self.fenced_through_sequence is None:
                raise ContractError("ENDPOINT_FENCED requiere fenced_through_sequence")
            if self.final_sequence is not None:
                raise ContractError("fencing no admite final_sequence")
        elif self.previous_generation is not None or self.fenced_through_sequence is not None:
            raise ContractError("claims de fencing solo aplican a ENDPOINT_FENCED")
        if self.expected_receipt_kind is TrustedReceiptKind.ENDPOINT_COMPLETED:
            if self.final_sequence is None:
                raise ContractError("ENDPOINT_COMPLETED requiere final_sequence")
        elif self.final_sequence is not None:
            raise ContractError("final_sequence solo aplica a ENDPOINT_COMPLETED")
        if self.expected_receipt_kind is TrustedReceiptKind.RECOVERY_COMPLETED:
            _positive(self.generation, "generation")
            if not self.affected_admission_ids or not self.route_ids:
                raise ContractError("recibo global requiere inventarios exactos no vacíos")
        elif self.affected_admission_ids or self.route_ids:
            raise ContractError("inventarios solo aplican al recibo global de recuperación")

    def binds_terminal_request(self, request: object) -> bool:
        fields = (
            ("consistency_domain_id", self.consistency_domain_id),
            ("authority_epoch", self.authority_epoch),
            ("operation_id", self.operation_id),
            ("receipt_id", self.expected_receipt_id),
            ("admission_id", self.admission_id),
            ("endpoint_id", self.endpoint_id),
            ("generation", self.generation),
            ("previous_generation", self.previous_generation),
            ("final_sequence", self.final_sequence),
            ("fenced_through_sequence", self.fenced_through_sequence),
        )
        if self.expected_receipt_kind is TrustedReceiptKind.RECOVERY_COMPLETED:
            return False
        return all(
            getattr(request, name, object()) == expected
            for name, expected in fields
            if expected is not None
        ) and getattr(getattr(request, "kind", None), "value", None) == self.expected_receipt_kind.value

    def binds_recovery_completion(self, request: object, receipt: object) -> bool:
        if self.expected_receipt_kind is not TrustedReceiptKind.RECOVERY_COMPLETED:
            return False
        return all((
            getattr(request, "consistency_domain_id", None) == self.consistency_domain_id,
            getattr(request, "authority_epoch", None) == self.authority_epoch,
            getattr(request, "operation_id", None) == self.operation_id,
            getattr(request, "generation", None) == self.generation,
            getattr(request, "affected_admission_ids", None) == self.affected_admission_ids,
            getattr(request, "route_ids", None) == self.route_ids,
            getattr(receipt, "receipt_id", None) == self.expected_receipt_id,
            getattr(receipt, "consistency_domain_id", None) == self.consistency_domain_id,
            getattr(receipt, "authority_epoch", None) == self.authority_epoch,
            getattr(receipt, "operation_id", None) == self.operation_id,
            getattr(receipt, "generation", None) == self.generation,
            getattr(receipt, "affected_admission_ids", None) == self.affected_admission_ids,
            getattr(receipt, "route_ids", None) == self.route_ids,
        ))
