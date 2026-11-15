"""Puertos de verificación confiable y consumo de evidencia CAM."""

from datetime import datetime
from typing import Protocol

from atlas.authorization.grant_revocation import ProofConsumptionResult
from atlas.authorization.models import (
    GrantRevocationAuthorizationRequest,
    VerifiedGrantRevocationAuthorization,
)


class GrantRevocationProofVerifierPort(Protocol):
    """Verifica autenticidad y emisor contra una fuente CAM confiable.

    La implementación debe comprobar que proof_id identifica una decisión
    CAM auténtica, emitida por un emisor permitido, para una acción directa
    grant.revoke de un usuario activo que corresponde al propietario canónico.
    Debe verificar todos los claims y la vigencia. No debe considerar el mero
    dataclass como prueba criptográfica ni autoridad por sí sola.

    La verificación de autenticidad no consume la prueba ni debe rechazarla
    únicamente porque ya fue consumida: los reintentos exactos se resuelven
    exclusivamente mediante el puerto de consumo idempotente.
    """

    def verify(
        self,
        request: GrantRevocationAuthorizationRequest,
        evidence: VerifiedGrantRevocationAuthorization,
        now: datetime,
    ) -> bool:
        """True solo ante verificación completa; False ante evidencia inválida."""


class GrantRevocationProofConsumptionPort(Protocol):
    """Consume proof_id una sola vez con recuperación idempotente.

    La implementación debe serializar por proof_id y persistir atómicamente
    proof_id, operation_id e idempotency_key. Repetir exactamente la misma
    pareja operación/clave devuelve REPLAY_SAME_OPERATION. Cualquier otro
    uso devuelve REPLAY_CONFLICT. Incertidumbre nunca significa disponible.
    """

    def consume(
        self,
        *,
        proof_id: str,
        operation_id: str,
        idempotency_key: str,
        consumed_at: datetime,
    ) -> ProofConsumptionResult:
        """Registra el consumo o devuelve el resultado idempotente existente."""
