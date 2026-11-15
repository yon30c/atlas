"""Puerto neutral de coordinación durable de cambios de autoridad."""

from datetime import datetime
from typing import Protocol

from atlas.memory.authority_changes import (
    AuthorityChangeIntent,
    AuthorityChangeReservation,
    AuthorityChangeResult,
    VerifiedAuthorityChangeAuthorization,
)


class AuthorityChangeCoordinatorPort(Protocol):
    """Coordina invalidación/fencing, cambio de fuente y reconciliación.

    reserve_change debe asignar operation_id e imponer idempotencia por
    (consumer_id, idempotency_key). Una misma clave con intención distinta
    nunca puede reutilizar una operación anterior.

    apply_change solo acepta evidencia CAM ya verificada y consumida, vinculada
    al operation_id, autoridad y revisiones exactas de la reserva. El coordinador
    no concede autorización: controla el orden durable del cambio.

    abort_unstarted solo puede devolver ABORTED cuando verifica que la fuente
    permanece en expected_revision y que la operación no podrá ejecutarse luego.
    La incertidumbre conserva BLOCKED/fencing; timeout no significa ABORTED.
    """

    def reserve_change(
        self,
        intent: AuthorityChangeIntent,
    ) -> AuthorityChangeReservation | None:
        """Registra REQUESTED y asigna operation_id de forma idempotente."""

    def apply_change(
        self,
        reservation: AuthorityChangeReservation,
        authorization: VerifiedAuthorityChangeAuthorization,
        now: datetime,
    ) -> AuthorityChangeResult | None:
        """Ejecuta Fases A/B/C y devuelve solo el estado demostrado."""

    def abort_unstarted(
        self,
        reservation: AuthorityChangeReservation,
        now: datetime,
    ) -> AuthorityChangeResult | None:
        """Cierra una reserva no iniciada solo si puede demostrar ABORTED."""
