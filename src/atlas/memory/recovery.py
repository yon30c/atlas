"""Fail-closed planning and verification for unresolved admission recovery.

This module never restores a read capability or authorizes content delivery.
"""
from dataclasses import dataclass

from atlas.core.errors import ContractError
from atlas.memory.consistency import ReadTarget
from atlas.memory.journal_reducer import (
    ConsistencyProjection,
    reconstruct_read_target,
)
from atlas.memory.receipt_verification import (
    TerminalReceiptKind,
    TerminalReceiptVerificationRequest,
    VerifiedTerminalReceipt,
)
from atlas.memory.receipt_trust import verify_terminal_receipt_with_context


def _required(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacía")


def _positive(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractError(f"{field} debe ser un entero positivo")


@dataclass(frozen=True, slots=True)
class RecoveryEndpointSequence:
    endpoint_id: str
    last_committed_sequence: int

    def __post_init__(self) -> None:
        _required(self.endpoint_id, "endpoint_id")
        if (
            isinstance(self.last_committed_sequence, bool)
            or not isinstance(self.last_committed_sequence, int)
            or self.last_committed_sequence < 0
        ):
            raise ContractError("last_committed_sequence debe ser entero no negativo")


@dataclass(frozen=True, slots=True)
class UnresolvedAdmissionRecovery:
    admission_id: str
    old_generation: int
    route_ids: frozenset[str]
    endpoint_sequences: tuple[RecoveryEndpointSequence, ...]
    target: ReadTarget | None
    recoverable: bool

    def __post_init__(self) -> None:
        _required(self.admission_id, "admission_id")
        _positive(self.old_generation, "old_generation")
        if not isinstance(self.route_ids, frozenset) or not self.route_ids:
            raise ContractError("route_ids debe ser frozenset no vacío")
        if not isinstance(self.endpoint_sequences, tuple) or not self.endpoint_sequences:
            raise ContractError("endpoint_sequences debe ser tupla no vacía")
        ids = tuple(item.endpoint_id for item in self.endpoint_sequences)
        if len(ids) != len(set(ids)) or frozenset(ids) != self.route_ids:
            raise ContractError("endpoint_sequences debe coincidir exactamente con route_ids")
        if not isinstance(self.recoverable, bool):
            raise ContractError("recoverable debe ser bool")
        if self.recoverable != (self.target is not None):
            raise ContractError("target solo existe para admisiones recuperables v2")


@dataclass(frozen=True, slots=True)
class RecoveryFencePlan:
    consistency_domain_id: str
    authority_epoch: int
    operation_id: str
    generation: int
    admissions: tuple[UnresolvedAdmissionRecovery, ...]

    def __post_init__(self) -> None:
        _required(self.consistency_domain_id, "consistency_domain_id")
        _positive(self.authority_epoch, "authority_epoch")
        _required(self.operation_id, "operation_id")
        _positive(self.generation, "generation")
        if not isinstance(self.admissions, tuple):
            raise ContractError("admissions debe ser tupla")
        admission_ids = tuple(item.admission_id for item in self.admissions)
        if len(admission_ids) != len(set(admission_ids)):
            raise ContractError("admission_id duplicado en recovery plan")
        if any(self.generation <= item.old_generation for item in self.admissions):
            raise ContractError("recovery generation debe superar cada generación previa")


@dataclass(frozen=True, slots=True)
class RecoveryEndpointFenceRequest:
    consistency_domain_id: str
    authority_epoch: int
    operation_id: str
    admission_id: str
    endpoint_id: str
    previous_generation: int
    generation: int
    last_committed_sequence: int

    def __post_init__(self) -> None:
        for field in (
            "consistency_domain_id", "operation_id", "admission_id", "endpoint_id"
        ):
            _required(getattr(self, field), field)
        _positive(self.authority_epoch, "authority_epoch")
        _positive(self.previous_generation, "previous_generation")
        _positive(self.generation, "generation")
        if self.generation <= self.previous_generation:
            raise ContractError("recovery fence debe avanzar generación")
        if (
            isinstance(self.last_committed_sequence, bool)
            or not isinstance(self.last_committed_sequence, int)
            or self.last_committed_sequence < 0
        ):
            raise ContractError("last_committed_sequence debe ser entero no negativo")


@dataclass(frozen=True, slots=True)
class RecoveryEndpointFenceReceipt:
    operation_id: str
    admission_id: str
    endpoint_id: str
    previous_generation: int
    generation: int
    receipt_id: str
    confirmed: bool
    fenced_through_sequence: int

    def __post_init__(self) -> None:
        for field in ("operation_id", "admission_id", "endpoint_id", "receipt_id"):
            _required(getattr(self, field), field)
        _positive(self.previous_generation, "previous_generation")
        _positive(self.generation, "generation")
        if self.generation <= self.previous_generation:
            raise ContractError("receipt de fencing no avanza generación")
        if not isinstance(self.confirmed, bool):
            raise ContractError("confirmed debe ser bool")
        if (
            isinstance(self.fenced_through_sequence, bool)
            or not isinstance(self.fenced_through_sequence, int)
            or self.fenced_through_sequence < 0
        ):
            raise ContractError("fenced_through_sequence debe ser entero no negativo")


@dataclass(frozen=True, slots=True)
class VerifiedRecoveryFenceBatch:
    consistency_domain_id: str
    authority_epoch: int
    operation_id: str
    generation: int
    requests: tuple[RecoveryEndpointFenceRequest, ...]
    verified_receipts: tuple[VerifiedTerminalReceipt, ...]

    def __post_init__(self) -> None:
        _required(self.consistency_domain_id, "consistency_domain_id")
        _positive(self.authority_epoch, "authority_epoch")
        _required(self.operation_id, "operation_id")
        _positive(self.generation, "generation")
        if not isinstance(self.requests, tuple) or not self.requests:
            raise ContractError("requests debe ser tupla no vacía")
        if not isinstance(self.verified_receipts, tuple):
            raise ContractError("verified_receipts debe ser tupla")
        if len(self.requests) != len(self.verified_receipts):
            raise ContractError("cada request requiere exactamente un recibo")
        keys = tuple((r.admission_id, r.endpoint_id) for r in self.requests)
        if len(keys) != len(set(keys)):
            raise ContractError("endpoint duplicado en recovery batch")
        receipt_ids = tuple(r.receipt_id for r in self.verified_receipts)
        verification_ids = tuple(r.verification_id for r in self.verified_receipts)
        if len(receipt_ids) != len(set(receipt_ids)):
            raise ContractError("receipt_id duplicado en recovery batch")
        if len(verification_ids) != len(set(verification_ids)):
            raise ContractError("verification_id duplicado en recovery batch")
        for request, receipt in zip(self.requests, self.verified_receipts):
            if (
                request.consistency_domain_id != self.consistency_domain_id
                or request.authority_epoch != self.authority_epoch
                or request.operation_id != self.operation_id
                or request.generation != self.generation
                or receipt.kind is not TerminalReceiptKind.ENDPOINT_FENCED
                or receipt.consistency_domain_id != request.consistency_domain_id
                or receipt.authority_epoch != request.authority_epoch
                or receipt.operation_id != request.operation_id
                or receipt.admission_id != request.admission_id
                or receipt.endpoint_id != request.endpoint_id
                or receipt.previous_generation != request.previous_generation
                or receipt.generation != request.generation
                or receipt.fenced_through_sequence != request.last_committed_sequence
            ):
                raise ContractError("recibo no corresponde exactamente al recovery request")


def build_recovery_fence_plan(
    projection: ConsistencyProjection,
    new_generation: int,
) -> RecoveryFencePlan | None:
    """Preserve all nonterminal v1/v2 admissions and plan fresh fencing."""
    if not isinstance(projection, ConsistencyProjection):
        return None
    try:
        _positive(new_generation, "new_generation")
        prior_generations = [
            admission.generation for admission in projection.admissions
        ]
        prior_generations.extend(item.generation for item in projection.forget_closures)
        prior_generations.extend(item.generation for item in projection.invalidations)
        if prior_generations and new_generation <= max(prior_generations):
            return None

        unresolved = []
        for admission in projection.admissions:
            if admission.status.value in ("completed", "cancelled"):
                continue
            if (
                not admission.route_ids
                or {endpoint.endpoint_id for endpoint in admission.endpoints}
                != admission.route_ids
                or len(admission.endpoints) != len(admission.route_ids)
            ):
                return None
            target = reconstruct_read_target(admission)
            unresolved.append(
                UnresolvedAdmissionRecovery(
                    admission_id=admission.admission_id,
                    old_generation=admission.generation,
                    route_ids=admission.route_ids,
                    endpoint_sequences=tuple(
                        RecoveryEndpointSequence(
                            endpoint_id=endpoint.endpoint_id,
                            last_committed_sequence=endpoint.last_emission_sequence,
                        )
                        for endpoint in sorted(
                            admission.endpoints, key=lambda item: item.endpoint_id
                        )
                    ),
                    target=target,
                    recoverable=admission.recoverable and target is not None,
                )
            )
        operation_id = (
            f"recovery:{projection.domain_id}:{projection.authority_epoch}:{new_generation}"
        )
        return RecoveryFencePlan(
            consistency_domain_id=projection.domain_id,
            authority_epoch=projection.authority_epoch,
            operation_id=operation_id,
            generation=new_generation,
            admissions=tuple(unresolved),
        )
    except (ContractError, AttributeError, TypeError, ValueError):
        return None


def build_recovery_fence_requests(
    plan: RecoveryFencePlan,
) -> tuple[RecoveryEndpointFenceRequest, ...]:
    if not isinstance(plan, RecoveryFencePlan):
        return ()
    return tuple(
        RecoveryEndpointFenceRequest(
            consistency_domain_id=plan.consistency_domain_id,
            authority_epoch=plan.authority_epoch,
            operation_id=plan.operation_id,
            admission_id=admission.admission_id,
            endpoint_id=endpoint.endpoint_id,
            previous_generation=admission.old_generation,
            generation=plan.generation,
            last_committed_sequence=endpoint.last_committed_sequence,
        )
        for admission in plan.admissions
        for endpoint in admission.endpoint_sequences
    )


def execute_recovery_fencing(
    plan: RecoveryFencePlan,
    fencer: object,
    verifier: object,
    trust_context_factory: object,
    verification_time: object,
) -> VerifiedRecoveryFenceBatch | None:
    """Fence every endpoint and verify every receipt; partial batches fail closed."""
    if (
        not isinstance(plan, RecoveryFencePlan)
        or not callable(getattr(fencer, "fence_endpoint", None))
        or not callable(getattr(verifier, "verify_terminal_receipt_with_context", None))
        or not callable(getattr(trust_context_factory, "for_terminal_receipt", None))
    ):
        return None
    requests = build_recovery_fence_requests(plan)
    if not requests:
        return None
    verified_receipts = []
    for request in requests:
        try:
            raw_receipt = fencer.fence_endpoint(request)
        except Exception:
            return None
        if not isinstance(raw_receipt, RecoveryEndpointFenceReceipt):
            return None
        if (
            not raw_receipt.confirmed
            or raw_receipt.operation_id != request.operation_id
            or raw_receipt.admission_id != request.admission_id
            or raw_receipt.endpoint_id != request.endpoint_id
            or raw_receipt.previous_generation != request.previous_generation
            or raw_receipt.generation != request.generation
            or raw_receipt.fenced_through_sequence != request.last_committed_sequence
        ):
            return None
        verification_request = TerminalReceiptVerificationRequest(
            consistency_domain_id=request.consistency_domain_id,
            authority_epoch=request.authority_epoch,
            operation_id=request.operation_id,
            admission_id=request.admission_id,
            receipt_id=raw_receipt.receipt_id,
            kind=TerminalReceiptKind.ENDPOINT_FENCED,
            generation=request.generation,
            endpoint_id=request.endpoint_id,
            previous_generation=request.previous_generation,
            fenced_through_sequence=request.last_committed_sequence,
        )
        verified = verify_terminal_receipt_with_context(
            verifier,
            trust_context_factory,
            verification_request,
            purpose="recovery-endpoint-fencing",
            verification_time=verification_time,
        )
        if verified is None:
            return None
        verified_receipts.append(verified)
    try:
        return VerifiedRecoveryFenceBatch(
            consistency_domain_id=plan.consistency_domain_id,
            authority_epoch=plan.authority_epoch,
            operation_id=plan.operation_id,
            generation=plan.generation,
            requests=requests,
            verified_receipts=tuple(verified_receipts),
        )
    except ContractError:
        return None
