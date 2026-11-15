"""Contratos neutrales para coordinar cambios de autoridades del Memory Engine."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Protocol

from atlas.core.errors import ContractError
from atlas.memory.consistency import AuthorityKind


class AuthorityChangeStatus(str, Enum):
    REQUESTED = "REQUESTED"
    INVALIDATION_PENDING = "INVALIDATION_PENDING"
    SOURCE_PENDING = "SOURCE_PENDING"
    SOURCE_CONFIRMED = "SOURCE_CONFIRMED"
    RECONCILING = "RECONCILING"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    BLOCKED = "BLOCKED"


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
        raise ContractError(f"{field} debe ser un datetime UTC")


@dataclass(frozen=True, slots=True)
class AuthorityChangeIntent:
    """Intención sin operation_id; la autoridad coordinadora asigna ese ID."""

    idempotency_key: str
    consumer_id: str
    authority_kind: AuthorityKind
    authority_id: str
    expected_revision: int
    proposed_revision: int
    change_kind: str
    request_context_ref: str
    requested_at: datetime

    def __post_init__(self) -> None:
        for field in (
            "idempotency_key",
            "consumer_id",
            "authority_id",
            "change_kind",
            "request_context_ref",
        ):
            _required(getattr(self, field), field)
        if not isinstance(self.authority_kind, AuthorityKind):
            raise ContractError("authority_kind debe ser AuthorityKind")
        _positive(self.expected_revision, "expected_revision")
        _positive(self.proposed_revision, "proposed_revision")
        if self.proposed_revision <= self.expected_revision:
            raise ContractError("proposed_revision debe superar expected_revision")
        _utc(self.requested_at, "requested_at")


@dataclass(frozen=True, slots=True)
class AuthorityChangeReservation:
    """Identidad durable asignada a una intención por el coordinador."""

    operation_id: str
    intent: AuthorityChangeIntent
    status: AuthorityChangeStatus

    def __post_init__(self) -> None:
        _required(self.operation_id, "operation_id")
        if not isinstance(self.intent, AuthorityChangeIntent):
            raise ContractError("intent debe ser AuthorityChangeIntent")
        if not isinstance(self.status, AuthorityChangeStatus):
            raise ContractError("status debe ser AuthorityChangeStatus")


@dataclass(frozen=True, slots=True)
class AuthorityChangeResult:
    """Resultado reconciliado de una operación sobre una autoridad."""

    operation_id: str
    authority_kind: AuthorityKind
    authority_id: str
    status: AuthorityChangeStatus
    previous_revision: int
    proposed_revision: int
    source_revision: int | None = None
    invalidation_id: str | None = None

    def __post_init__(self) -> None:
        _required(self.operation_id, "operation_id")
        _required(self.authority_id, "authority_id")
        if not isinstance(self.authority_kind, AuthorityKind):
            raise ContractError("authority_kind debe ser AuthorityKind")
        if not isinstance(self.status, AuthorityChangeStatus):
            raise ContractError("status debe ser AuthorityChangeStatus")
        _positive(self.previous_revision, "previous_revision")
        _positive(self.proposed_revision, "proposed_revision")
        if self.proposed_revision <= self.previous_revision:
            raise ContractError("proposed_revision debe superar previous_revision")
        if self.source_revision is not None:
            _positive(self.source_revision, "source_revision")
        if self.invalidation_id is not None:
            _required(self.invalidation_id, "invalidation_id")
        if self.status is AuthorityChangeStatus.COMPLETED:
            if self.source_revision != self.proposed_revision:
                raise ContractError(
                    "COMPLETED requiere source_revision igual a proposed_revision"
                )
            if self.invalidation_id is None:
                raise ContractError("COMPLETED requiere invalidation_id reconciliado")
        elif self.status is AuthorityChangeStatus.ABORTED:
            if self.source_revision != self.previous_revision:
                raise ContractError(
                    "ABORTED requiere evidencia de que la fuente sigue en previous_revision"
                )


class VerifiedAuthorityChangeAuthorization(Protocol):
    """Evidencia CAM ya verificada y consumida, adaptada al cambio exacto."""

    @property
    def operation_id(self) -> str: ...

    @property
    def proof_id(self) -> str: ...

    @property
    def decision_id(self) -> str: ...

    @property
    def request_id(self) -> str: ...

    @property
    def actor_identity_id(self) -> str: ...

    @property
    def owner_id(self) -> str: ...

    @property
    def authority_kind(self) -> AuthorityKind: ...

    @property
    def authority_id(self) -> str: ...

    @property
    def expected_revision(self) -> int: ...

    @property
    def proposed_revision(self) -> int: ...

    @property
    def issuer_id(self) -> str: ...

    @property
    def issued_at(self) -> datetime: ...

    @property
    def consumed_at(self) -> datetime: ...
