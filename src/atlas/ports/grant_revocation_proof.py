"""Puerto de verificación confiable de evidencia CAM."""

from typing import Protocol

from atlas.authorization.grant_revocation import (
    ProofConsumptionResult,
)
from atlas.authorization.models import (
    GrantRevocationAuthorizationRequest,
    VerifiedGrantRevocationAuthorization,
)


class GrantRevocationProofVerifierPort(Protocol):
    """Verifica autenticidad y emisor contra una fuente CAM confiable.

    La implementación debe comprobar que proof_id identifica una decisión
    CAM auténtica y vigente, que el emisor está permitido y que todos los
    claims coinciden con la evidencia recibida. La forma del dataclass no
    constituye prueba criptográfica ni autoridad por sí sola.
    """

    def verify(
        self,
        request: GrantRevocationAuthorizationRequest,
        evidence: VerifiedGrantRevocationAuthorization,
        now,
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
        consumed_at,
    ) -> ProofConsumptionResult:
        """Registra el consumo o devuelve el resultado idempotente existente."""
