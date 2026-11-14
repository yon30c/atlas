"""Typed trust boundary for verifying terminal consistency receipts."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from atlas.core.errors import ContractError
from atlas.memory.consistency import ReadAdmissionStatus


def _required(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacía")


def _positive(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractError(f"{field} debe ser un entero positivo")


def _non_negative(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractError(f"{field} debe ser un entero no negativo")


def _utc(value: object, field: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ContractError(f"{field} debe ser datetime UTC")


class TerminalReceiptKind(str, Enum):
    ENDPOINT_COMPLETED = "endpoint_completed"
    ENDPOINT_FENCED = "endpoint_fenced"
    ADMISSION_COMPLETED = "admission_completed"
    ADMISSION_CANCELLED = "admission_cancelled"


class ReceiptVerificationStatus(str, Enum):
    VERIFIED = "verified"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class TerminalReceiptVerificationRequest:
    consistency_domain_id: str
    authority_epoch: int
    operation_id: str
    admission_id: str
    receipt_id: str
    kind: TerminalReceiptKind
    generation: int
    endpoint_id: str | None = None
    previous_generation: int | None = None
    final_sequence: int | None = None
    fenced_through_sequence: int | None = None

    def __post_init__(self) -> None:
        for field in (
            "consistency_domain_id", "operation_id", "admission_id", "receipt_id"
        ):
            _required(getattr(self, field), field)
        _positive(self.authority_epoch, "authority_epoch")
        _positive(self.generation, "generation")
        if not isinstance(self.kind, TerminalReceiptKind):
            raise ContractError("kind debe ser TerminalReceiptKind")
        endpoint_kind = self.kind in (
            TerminalReceiptKind.ENDPOINT_COMPLETED,
            TerminalReceiptKind.ENDPOINT_FENCED,
        )
        if endpoint_kind:
            _required(self.endpoint_id, "endpoint_id")
        elif self.endpoint_id is not None:
            raise ContractError("receipt de admisión no admite endpoint_id")
        if self.kind is TerminalReceiptKind.ENDPOINT_FENCED:
            _positive(self.previous_generation, "previous_generation")
            if self.generation <= self.previous_generation:
                raise ContractError("fencing debe avanzar la generación")
            if self.final_sequence is not None:
                raise ContractError("fencing no admite final_sequence")
        elif self.previous_generation is not None:
            raise ContractError("previous_generation solo aplica a fencing")
        if self.kind is TerminalReceiptKind.ENDPOINT_COMPLETED:
            _non_negative(self.final_sequence, "final_sequence")
        elif self.final_sequence is not None:
            raise ContractError("final_sequence solo aplica a endpoint completion")
        if self.kind is TerminalReceiptKind.ENDPOINT_FENCED:
            _non_negative(self.fenced_through_sequence, "fenced_through_sequence")
        elif self.fenced_through_sequence is not None:
            raise ContractError("fenced_through_sequence solo aplica a endpoint fencing")


@dataclass(frozen=True, slots=True)
class VerifiedTerminalReceipt:
    """Verifier-attested binding; not a serialized signature or user capability."""

    verification_id: str
    issuer_id: str
    verified_at: datetime
    consistency_domain_id: str
    authority_epoch: int
    operation_id: str
    admission_id: str
    receipt_id: str
    kind: TerminalReceiptKind
    generation: int
    endpoint_id: str | None = None
    previous_generation: int | None = None
    final_sequence: int | None = None
    fenced_through_sequence: int | None = None

    def __post_init__(self) -> None:
        _required(self.verification_id, "verification_id")
        _required(self.issuer_id, "issuer_id")
        _utc(self.verified_at, "verified_at")
        # Reuse the request's closed-field and cross-field validation.
        TerminalReceiptVerificationRequest(
            consistency_domain_id=self.consistency_domain_id,
            authority_epoch=self.authority_epoch,
            operation_id=self.operation_id,
            admission_id=self.admission_id,
            receipt_id=self.receipt_id,
            kind=self.kind,
            generation=self.generation,
            endpoint_id=self.endpoint_id,
            previous_generation=self.previous_generation,
            final_sequence=self.final_sequence,
            fenced_through_sequence=self.fenced_through_sequence,
        )

    def matches(self, request: TerminalReceiptVerificationRequest) -> bool:
        return all(
            getattr(self, field) == getattr(request, field)
            for field in (
                "consistency_domain_id", "authority_epoch", "operation_id",
                "admission_id", "receipt_id", "kind", "generation",
                "endpoint_id", "previous_generation", "final_sequence",
                "fenced_through_sequence",
            )
        )


@dataclass(frozen=True, slots=True)
class ReceiptVerificationResult:
    status: ReceiptVerificationStatus
    verified_receipt: VerifiedTerminalReceipt | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ReceiptVerificationStatus):
            raise ContractError("status debe ser ReceiptVerificationStatus")
        if self.status is ReceiptVerificationStatus.VERIFIED:
            if not isinstance(self.verified_receipt, VerifiedTerminalReceipt):
                raise ContractError("VERIFIED requiere VerifiedTerminalReceipt")
        elif self.verified_receipt is not None:
            raise ContractError("solo VERIFIED puede incluir recibo verificado")


@dataclass(frozen=True, slots=True)
class VerifiedAdmissionTerminalEvidence:
    admission_id: str
    terminal_status: ReadAdmissionStatus
    endpoint_receipts: tuple[VerifiedTerminalReceipt, ...]
    admission_receipt: VerifiedTerminalReceipt

    def __post_init__(self) -> None:
        _required(self.admission_id, "admission_id")
        if self.terminal_status not in (
            ReadAdmissionStatus.COMPLETED, ReadAdmissionStatus.CANCELLED
        ):
            raise ContractError("terminal_status debe ser COMPLETED o CANCELLED")
        if not isinstance(self.endpoint_receipts, tuple) or not self.endpoint_receipts:
            raise ContractError("endpoint_receipts debe ser una tupla no vacía")
        if any(not isinstance(item, VerifiedTerminalReceipt) for item in self.endpoint_receipts):
            raise ContractError("endpoint_receipts contiene evidencia inválida")
        if not isinstance(self.admission_receipt, VerifiedTerminalReceipt):
            raise ContractError("admission_receipt debe estar verificado")
        expected_admission_kind = (
            TerminalReceiptKind.ADMISSION_COMPLETED
            if self.terminal_status is ReadAdmissionStatus.COMPLETED
            else TerminalReceiptKind.ADMISSION_CANCELLED
        )
        if (
            self.admission_receipt.admission_id != self.admission_id
            or self.admission_receipt.kind is not expected_admission_kind
        ):
            raise ContractError("admission_receipt no corresponde al estado terminal")
        endpoint_receipt_ids = set()
        verification_ids = {self.admission_receipt.verification_id}
        for receipt in self.endpoint_receipts:
            if (
                receipt.admission_id != self.admission_id
                or receipt.kind not in (
                    TerminalReceiptKind.ENDPOINT_COMPLETED,
                    TerminalReceiptKind.ENDPOINT_FENCED,
                )
                or receipt.endpoint_id is None
                or receipt.receipt_id in endpoint_receipt_ids
                or receipt.verification_id in verification_ids
            ):
                raise ContractError("endpoint receipt duplicado o no corresponde a la admisión")
            endpoint_receipt_ids.add(receipt.receipt_id)
            verification_ids.add(receipt.verification_id)


def match_verified_receipt(
    request: TerminalReceiptVerificationRequest,
    result: ReceiptVerificationResult,
) -> VerifiedTerminalReceipt | None:
    """Accept only VERIFIED evidence with an exact field-for-field binding."""
    if not isinstance(request, TerminalReceiptVerificationRequest):
        return None
    if not isinstance(result, ReceiptVerificationResult):
        return None
    if result.status is not ReceiptVerificationStatus.VERIFIED:
        return None
    receipt = result.verified_receipt
    if receipt is None or not receipt.matches(request):
        return None
    return receipt
