"""Contrato de verificación y consumo de evidencia de revocación CAM."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING

from atlas.authorization.models import (
    GrantRevocationAuthorizationRequest,
    VerifiedGrantRevocationAuthorization,
)
from atlas.core.errors import ContractError

if TYPE_CHECKING:
    from atlas.ports.grant_revocation_proof import (
        GrantRevocationProofConsumptionPort,
        GrantRevocationProofVerifierPort,
    )


class ProofConsumptionStatus(str, Enum):
    CONSUMED = "consumed"
    REPLAY_SAME_OPERATION = "replay_same_operation"
    REPLAY_CONFLICT = "replay_conflict"
    INDETERMINATE = "indeterminate"


class GrantRevocationAuthorizationStatus(str, Enum):
    AUTHORIZED = "authorized"
    DENIED = "denied"
    VERIFIER_UNAVAILABLE = "verifier_unavailable"
    PROOF_REPLAY_CONFLICT = "proof_replay_conflict"
    CONSUMPTION_UNCERTAIN = "consumption_uncertain"


@dataclass(frozen=True, slots=True)
class ProofConsumptionResult:
    """Resultado durable esperado del consumo de una prueba one-shot."""

    proof_id: str
    operation_id: str
    idempotency_key: str
    status: ProofConsumptionStatus

    def __post_init__(self) -> None:
        for field in ("proof_id", "operation_id", "idempotency_key"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"{field} debe ser una cadena no vacía")
        if not isinstance(self.status, ProofConsumptionStatus):
            raise ContractError("status debe ser ProofConsumptionStatus")


@dataclass(frozen=True, slots=True)
class GrantRevocationAuthorizationResult:
    """Resultado de verificar y consumir evidencia para una operación."""

    operation_id: str
    grant_id: str
    proof_id: str | None
    status: GrantRevocationAuthorizationStatus

    def __post_init__(self) -> None:
        for field in ("operation_id", "grant_id"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"{field} debe ser una cadena no vacía")
        if self.proof_id is not None and (
            not isinstance(self.proof_id, str) or not self.proof_id.strip()
        ):
            raise ContractError("proof_id debe ser None o una cadena no vacía")
        if not isinstance(self.status, GrantRevocationAuthorizationStatus):
            raise ContractError(
                "status debe ser GrantRevocationAuthorizationStatus"
            )

    @property
    def authorized(self) -> bool:
        return self.status is GrantRevocationAuthorizationStatus.AUTHORIZED


def _validate_utc(value: datetime, field: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ContractError(f"{field} debe ser un datetime con zona horaria")
    if value.utcoffset() != timedelta(0):
        raise ContractError(f"{field} debe estar en UTC")


class GrantRevocationProofAuthorizationService:
    """Verifica claims y consume evidencia CAM mediante puertos confiables.

    No autentica firmas por sí mismo ni implementa almacenamiento de consumo.
    El verificador debe validar la autoridad emisora y la evidencia original.
    El consumidor debe proporcionar consumo atómico, durable y recuperable.
    """

    def __init__(
        self,
        verifier: GrantRevocationProofVerifierPort,
        consumer: GrantRevocationProofConsumptionPort,
    ) -> None:
        if verifier is None or consumer is None:
            raise ContractError("verifier y consumer son obligatorios")
        self._verifier = verifier
        self._consumer = consumer

    def verify_and_consume(
        self,
        request: GrantRevocationAuthorizationRequest,
        evidence: VerifiedGrantRevocationAuthorization,
        operation_id: str,
        idempotency_key: str,
        now: datetime,
    ) -> GrantRevocationAuthorizationResult:
        """Autoriza solo después de verificar y consumir la prueba one-shot."""
        if not isinstance(request, GrantRevocationAuthorizationRequest):
            raise ContractError(
                "request debe ser GrantRevocationAuthorizationRequest"
            )
        if not isinstance(evidence, VerifiedGrantRevocationAuthorization):
            raise ContractError(
                "evidence debe ser VerifiedGrantRevocationAuthorization"
            )
        for field, value in (
            ("operation_id", operation_id),
            ("idempotency_key", idempotency_key),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"{field} debe ser una cadena no vacía")
        _validate_utc(now, "now")

        if not self._matches_request(request, evidence):
            return self._result(
                operation_id, request.grant_id, evidence.proof_id,
                GrantRevocationAuthorizationStatus.DENIED,
            )
        if evidence.issued_at < request.requested_at or not (
            evidence.issued_at <= now < evidence.expires_at
        ):
            return self._result(
                operation_id, request.grant_id, evidence.proof_id,
                GrantRevocationAuthorizationStatus.DENIED,
            )

        try:
            verified = self._verifier.verify(request, evidence, now)
        except Exception:
            return self._result(
                operation_id, request.grant_id, evidence.proof_id,
                GrantRevocationAuthorizationStatus.VERIFIER_UNAVAILABLE,
            )
        if verified is not True:
            return self._result(
                operation_id, request.grant_id, evidence.proof_id,
                GrantRevocationAuthorizationStatus.DENIED,
            )

        try:
            consumed = self._consumer.consume(
                proof_id=evidence.proof_id,
                operation_id=operation_id,
                idempotency_key=idempotency_key,
                consumed_at=now,
            )
        except Exception:
            # No se puede inferir que la prueba siga libre: el resultado puede
            # haberse confirmado antes de perderse la respuesta.
            return self._result(
                operation_id, request.grant_id, evidence.proof_id,
                GrantRevocationAuthorizationStatus.CONSUMPTION_UNCERTAIN,
            )

        if not isinstance(consumed, ProofConsumptionResult):
            return self._result(
                operation_id, request.grant_id, evidence.proof_id,
                GrantRevocationAuthorizationStatus.CONSUMPTION_UNCERTAIN,
            )
        if (
            consumed.proof_id != evidence.proof_id
            or consumed.operation_id != operation_id
            or consumed.idempotency_key != idempotency_key
        ):
            return self._result(
                operation_id, request.grant_id, evidence.proof_id,
                GrantRevocationAuthorizationStatus.PROOF_REPLAY_CONFLICT,
            )

        if consumed.status in (
            ProofConsumptionStatus.CONSUMED,
            ProofConsumptionStatus.REPLAY_SAME_OPERATION,
        ):
            return self._result(
                operation_id, request.grant_id, evidence.proof_id,
                GrantRevocationAuthorizationStatus.AUTHORIZED,
            )
        if consumed.status is ProofConsumptionStatus.REPLAY_CONFLICT:
            status = GrantRevocationAuthorizationStatus.PROOF_REPLAY_CONFLICT
        else:
            status = GrantRevocationAuthorizationStatus.CONSUMPTION_UNCERTAIN
        return self._result(operation_id, request.grant_id, evidence.proof_id, status)

    @staticmethod
    def _matches_request(
        request: GrantRevocationAuthorizationRequest,
        evidence: VerifiedGrantRevocationAuthorization,
    ) -> bool:
        return (
            evidence.request_id == request.request_id
            and evidence.actor_identity_id == request.actor_identity_id
            and evidence.owner_user_id == request.owner_user_id
            and evidence.grant_id == request.grant_id
            and evidence.expected_revision == request.expected_revision
        )

    @staticmethod
    def _result(
        operation_id: str,
        grant_id: str,
        proof_id: str | None,
        status: GrantRevocationAuthorizationStatus,
    ) -> GrantRevocationAuthorizationResult:
        return GrantRevocationAuthorizationResult(
            operation_id=operation_id,
            grant_id=grant_id,
            proof_id=proof_id,
            status=status,
        )


@dataclass(frozen=True, slots=True)
class GrantRevocationAuthorityChangeAuthorization:
    """Adapta evidencia CAM consumida al contrato neutral del coordinador."""

    operation_id: str
    request: GrantRevocationAuthorizationRequest
    evidence: VerifiedGrantRevocationAuthorization
    authorization_result: GrantRevocationAuthorizationResult
    proposed_revision: int
    consumed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.operation_id, str) or not self.operation_id.strip():
            raise ContractError("operation_id debe ser una cadena no vacía")
        if not isinstance(self.request, GrantRevocationAuthorizationRequest):
            raise ContractError("request debe ser GrantRevocationAuthorizationRequest")
        if not isinstance(self.evidence, VerifiedGrantRevocationAuthorization):
            raise ContractError("evidence debe ser VerifiedGrantRevocationAuthorization")
        if not isinstance(
            self.authorization_result, GrantRevocationAuthorizationResult
        ) or not self.authorization_result.authorized:
            raise ContractError("se requiere autorización CAM verificada y consumida")
        if (
            self.authorization_result.operation_id != self.operation_id
            or self.authorization_result.grant_id != self.evidence.grant_id
            or self.authorization_result.proof_id != self.evidence.proof_id
            or self.request.request_id != self.evidence.request_id
            or self.request.actor_identity_id != self.evidence.actor_identity_id
            or self.request.owner_user_id != self.evidence.owner_user_id
            or self.request.grant_id != self.evidence.grant_id
            or self.request.expected_revision != self.evidence.expected_revision
        ):
            raise ContractError("evidencia CAM no corresponde a la operación exacta")
        if (
            isinstance(self.proposed_revision, bool)
            or not isinstance(self.proposed_revision, int)
            or self.proposed_revision != self.request.expected_revision + 1
        ):
            raise ContractError("proposed_revision debe ser expected_revision + 1")
        _validate_utc(self.consumed_at, "consumed_at")
        if not (
            self.evidence.issued_at <= self.consumed_at < self.evidence.expires_at
        ):
            raise ContractError("la evidencia no estaba vigente al consumirse")

    @property
    def proof_id(self) -> str:
        return self.evidence.proof_id

    @property
    def decision_id(self) -> str:
        return self.evidence.decision_id

    @property
    def request_id(self) -> str:
        return self.evidence.request_id

    @property
    def actor_identity_id(self) -> str:
        return self.evidence.actor_identity_id

    @property
    def owner_id(self) -> str:
        return self.evidence.owner_user_id

    @property
    def authority_kind(self):
        from atlas.memory.consistency import AuthorityKind
        return AuthorityKind.GRANT

    @property
    def authority_id(self) -> str:
        return self.evidence.grant_id

    @property
    def expected_revision(self) -> int:
        return self.evidence.expected_revision

    @property
    def issuer_id(self) -> str:
        return self.evidence.issuer_id

    @property
    def issued_at(self) -> datetime:
        return self.evidence.issued_at

