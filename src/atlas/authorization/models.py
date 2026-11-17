"""Modelos del dominio de autorización CAM."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from atlas.core.context import OperationContext
from atlas.core.errors import ContractError
from atlas.memory.consistency import AuthorizationSnapshot


def _validate_utc_datetime(value: datetime, field: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ContractError(
            f"{field} debe ser un datetime con zona horaria"
        )
    if value.utcoffset() != timedelta(0):
        raise ContractError(f"{field} debe estar en UTC")


class AuthorizationDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    context: OperationContext
    action: str
    resource_type: str
    resource_id: str
    resource_owner_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.context, OperationContext):
            raise ContractError("context debe ser OperationContext")

        for field in (
            "action",
            "resource_type",
            "resource_id",
            "resource_owner_id",
        ):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"{field} debe ser una cadena no vacía")


@dataclass(frozen=True, slots=True)
class AuthorizationEvaluation:
    """Resultado interno del evaluador; no constituye autorización pública."""

    decision: AuthorizationDecision
    matched_grant: "Grant | None" = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, AuthorizationDecision):
            raise ContractError("decision debe ser AuthorizationDecision")
        if self.decision is AuthorizationDecision.ALLOW and not isinstance(self.matched_grant, Grant):
            raise ContractError("ALLOW interno requiere el Grant exacto que coincidió")
        if self.decision is not AuthorizationDecision.ALLOW and self.matched_grant is not None:
            raise ContractError("una evaluación no permitida no puede incluir Grant")


@dataclass(frozen=True, slots=True)
class AuthorizationResult:
    """Resultado CAM público: ALLOW solo existe junto a snapshot confiable."""

    decision: AuthorizationDecision
    snapshot: AuthorizationSnapshot | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, AuthorizationDecision):
            raise ContractError("decision debe ser AuthorizationDecision")
        if self.decision is AuthorizationDecision.ALLOW:
            if not isinstance(self.snapshot, AuthorizationSnapshot):
                raise ContractError("ALLOW requiere exactamente un AuthorizationSnapshot")
        elif self.snapshot is not None:
            raise ContractError("DENY/REQUIRE_APPROVAL no pueden incluir snapshot de lectura")


@dataclass(frozen=True, slots=True)
class GrantResourceScope:
    """Conjunto explícito e inmutable de IDs para un tipo de recurso."""

    resource_type: str
    resource_ids: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.resource_type, str) or not self.resource_type.strip():
            raise ContractError("resource_type debe ser una cadena no vacía")
        if not isinstance(self.resource_ids, frozenset):
            raise ContractError("resource_ids debe ser un frozenset")
        if not self.resource_ids:
            raise ContractError("resource_ids no puede estar vacío")
        for resource_id in self.resource_ids:
            if not isinstance(resource_id, str) or not resource_id.strip():
                raise ContractError("Cada resource_id debe ser una cadena no vacía")
            if "*" in resource_id or "?" in resource_id:
                raise ContractError("No se permiten wildcards ni patrones de IDs")


@dataclass(frozen=True, slots=True)
class Grant:
    """Permiso explícito sobre IDs concretos de un tipo de recurso."""

    grant_id: str
    owner_user_id: str
    subject_identity_id: str
    project_id: str
    environment: str
    resource_scope: GrantResourceScope
    actions: frozenset[str]
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    revision: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise ContractError("revision debe ser un entero positivo")

        required_fields = (
            "grant_id",
            "owner_user_id",
            "subject_identity_id",
            "project_id",
            "environment",
        )
        for field in required_fields:
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ContractError(
                    f"{field} debe ser una cadena no vacía"
                )

        if not isinstance(self.resource_scope, GrantResourceScope):
            raise ContractError("resource_scope debe ser GrantResourceScope")
        if not isinstance(self.actions, frozenset):
            raise ContractError("actions debe ser un frozenset")
        if not self.actions:
            raise ContractError("actions no puede estar vacío")
        for action in self.actions:
            if not isinstance(action, str) or not action.strip():
                raise ContractError(
                    "Cada acción debe ser una cadena no vacía"
                )
            if action == "*":
                raise ContractError("No se permiten permisos wildcard")

        _validate_utc_datetime(self.issued_at, "issued_at")
        _validate_utc_datetime(self.expires_at, "expires_at")
        if self.expires_at <= self.issued_at:
            raise ContractError(
                "expires_at debe ser posterior a issued_at"
            )
        if self.revoked_at is not None:
            _validate_utc_datetime(self.revoked_at, "revoked_at")

    @property
    def resource_type(self) -> str:
        return self.resource_scope.resource_type

    @property
    def resource_ids(self) -> frozenset[str]:
        return self.resource_scope.resource_ids


class RenewalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class GrantRenewalRequest:
    """Solicitud explícita de renovación de un Grant."""

    renewal_id: str
    grant_id: str
    owner_user_id: str
    subject_identity_id: str
    requested_by_identity_id: str
    current_expires_at: datetime
    proposed_expires_at: datetime
    requested_at: datetime
    status: RenewalStatus = RenewalStatus.PENDING
    decided_at: datetime | None = None
    decided_by_user_id: str | None = None
    version: int = 1
    grant_revision: int | None = None
    delegation_id: str | None = None
    delegation_revision: int | None = None

    def __post_init__(self) -> None:
        audit_values = (
            self.grant_revision,
            self.delegation_id,
            self.delegation_revision,
        )
        if any(value is not None for value in audit_values):
            if any(value is None for value in audit_values):
                raise ContractError(
                    "la evidencia de solicitud AGENT requiere revisión Grant y delegación completas"
                )
            if (
                isinstance(self.grant_revision, bool)
                or not isinstance(self.grant_revision, int)
                or self.grant_revision < 1
                or isinstance(self.delegation_revision, bool)
                or not isinstance(self.delegation_revision, int)
                or self.delegation_revision < 1
            ):
                raise ContractError("las revisiones de auditoría deben ser enteros positivos")
            if not isinstance(self.delegation_id, str) or not self.delegation_id.strip():
                raise ContractError("delegation_id debe ser texto no vacío")
        if (
            isinstance(self.version, bool)
            or not isinstance(self.version, int)
            or self.version < 1
        ):
            raise ContractError(
                "version debe ser un entero mayor o igual a 1"
            )

        required_fields = (
            "renewal_id",
            "grant_id",
            "owner_user_id",
            "subject_identity_id",
            "requested_by_identity_id",
        )
        for field in required_fields:
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ContractError(
                    f"{field} debe ser una cadena no vacía"
                )

        _validate_utc_datetime(self.current_expires_at, "current_expires_at")
        _validate_utc_datetime(self.proposed_expires_at, "proposed_expires_at")
        _validate_utc_datetime(self.requested_at, "requested_at")
        if self.proposed_expires_at <= self.current_expires_at:
            raise ContractError(
                "proposed_expires_at debe ser posterior a current_expires_at"
            )

        if not isinstance(self.status, RenewalStatus):
            raise ContractError("status debe ser RenewalStatus")

        if self.status is RenewalStatus.PENDING:
            if self.decided_at is not None or self.decided_by_user_id is not None:
                raise ContractError(
                    "Una solicitud pendiente no puede tener datos de decisión"
                )
            return

        if self.decided_at is None or self.decided_by_user_id is None:
            raise ContractError(
                "Una solicitud decidida requiere fecha e identidad decisora"
            )
        if (
            not isinstance(self.decided_by_user_id, str)
            or not self.decided_by_user_id.strip()
        ):
            raise ContractError(
                "decided_by_user_id debe ser una cadena no vacía"
            )
        _validate_utc_datetime(self.decided_at, "decided_at")


@dataclass(frozen=True, slots=True)
class GrantRevocationAuthorizationRequest:
    """Solicitud CAM específica para revocar un Grant propio."""

    request_id: str
    actor_identity_id: str
    owner_user_id: str
    grant_id: str
    expected_revision: int
    requested_at: datetime

    def __post_init__(self) -> None:
        for field in (
            "request_id",
            "actor_identity_id",
            "owner_user_id",
            "grant_id",
        ):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"{field} debe ser una cadena no vacía")

        if (
            isinstance(self.expected_revision, bool)
            or not isinstance(self.expected_revision, int)
            or self.expected_revision < 1
        ):
            raise ContractError("expected_revision debe ser un entero positivo")

        _validate_utc_datetime(self.requested_at, "requested_at")


@dataclass(frozen=True, slots=True)
class VerifiedGrantRevocationAuthorization:
    """Evidencia CAM verificable para una revocación concreta.

    La instancia es un dato contractual, no prueba por sí misma su autenticidad.
    El consumidor debe exigir verificación confiable antes de usarla.
    """

    proof_id: str
    decision_id: str
    request_id: str
    actor_identity_id: str
    owner_user_id: str
    grant_id: str
    expected_revision: int
    issued_at: datetime
    expires_at: datetime
    issuer_id: str

    def __post_init__(self) -> None:
        for field in (
            "proof_id",
            "decision_id",
            "request_id",
            "actor_identity_id",
            "owner_user_id",
            "grant_id",
            "issuer_id",
        ):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"{field} debe ser una cadena no vacía")

        if (
            isinstance(self.expected_revision, bool)
            or not isinstance(self.expected_revision, int)
            or self.expected_revision < 1
        ):
            raise ContractError("expected_revision debe ser un entero positivo")

        _validate_utc_datetime(self.issued_at, "issued_at")
        _validate_utc_datetime(self.expires_at, "expires_at")
        if self.expires_at <= self.issued_at:
            raise ContractError("expires_at debe ser posterior a issued_at")
