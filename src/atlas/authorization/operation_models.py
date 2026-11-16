"""Contratos CAM para autorización de operaciones generales.

Estos modelos expresan claims de autorización. La construcción de una instancia
no autentica al emisor ni sustituye la verificación por un consumidor confiable.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from atlas.authorization.models import AuthorizationDecision, AuthorizationRequest
from atlas.core.errors import ContractError


def _require_utc(value: datetime, field: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ContractError(f"{field} debe ser un datetime con zona horaria")
    if value.utcoffset() != timedelta(0):
        raise ContractError(f"{field} debe estar en UTC")


@dataclass(frozen=True, slots=True)
class OperationAuthorizationEvidence:
    """Claims CAM ligados a una solicitud de operación exacta.

    Esta evidencia no es una firma ni un token auto-verificable. El consumidor
    debe obtenerla desde un puerto CAM confiable y verificar vigencia y
    correspondencia antes de admitir una operación.
    """

    evidence_id: str
    decision_id: str
    request_id: str
    actor_identity_id: str
    actor_revision: int
    project_id: str
    environment: str
    action: str
    resource_type: str
    resource_id: str
    resource_owner_id: str
    grant_id: str
    grant_revision: int
    issued_at: datetime
    expires_at: datetime
    issuer_id: str

    def __post_init__(self) -> None:
        for field in (
            "evidence_id",
            "decision_id",
            "request_id",
            "actor_identity_id",
            "project_id",
            "environment",
            "action",
            "resource_type",
            "resource_id",
            "resource_owner_id",
            "grant_id",
            "issuer_id",
        ):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"{field} debe ser una cadena no vacía")

        for field in ("actor_revision", "grant_revision"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ContractError(f"{field} debe ser un entero positivo")

        _require_utc(self.issued_at, "issued_at")
        _require_utc(self.expires_at, "expires_at")
        if self.expires_at <= self.issued_at:
            raise ContractError("expires_at debe ser posterior a issued_at")

    def matches(self, request: AuthorizationRequest) -> bool:
        """Comprueba que los claims cubren exactamente la solicitud recibida."""
        if not isinstance(request, AuthorizationRequest):
            return False
        context = request.context
        return all(
            (
                self.request_id == context.request_id,
                self.actor_identity_id == context.actor.identity_id,
                self.actor_revision == context.actor.revision,
                self.project_id == context.project_id,
                self.environment == context.environment,
                self.action == request.action,
                self.resource_type == request.resource_type,
                self.resource_id == request.resource_id,
                self.resource_owner_id == request.resource_owner_id,
            )
        )

    def is_current_at(self, now: datetime) -> bool:
        """Comprueba la ventana temporal; no verifica revocación ni autenticidad."""
        _require_utc(now, "now")
        return self.issued_at <= now < self.expires_at


@dataclass(frozen=True, slots=True)
class OperationAuthorizationResult:
    """Decisión pública para una operación, separada de las lecturas de Memory."""

    decision: AuthorizationDecision
    evidence: OperationAuthorizationEvidence | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, AuthorizationDecision):
            raise ContractError("decision debe ser AuthorizationDecision")
        if self.decision is AuthorizationDecision.ALLOW:
            if not isinstance(self.evidence, OperationAuthorizationEvidence):
                raise ContractError("ALLOW requiere evidencia de operación")
        elif self.evidence is not None:
            raise ContractError("DENY/REQUIRE_APPROVAL no pueden incluir evidencia ALLOW")
