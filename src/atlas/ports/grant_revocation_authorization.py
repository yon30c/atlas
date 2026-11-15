"""Puerto neutral de autorización CAM para revocación de Grants."""

from typing import Protocol

from atlas.authorization.models import (
    GrantRevocationAuthorizationRequest,
    VerifiedGrantRevocationAuthorization,
)


class GrantRevocationAuthorizationPort(Protocol):
    """Solicita a CAM evidencia para una revocación directa del propietario.

    La implementación solo debe emitir evidencia tras aplicar la política CAM
    aprobada. El consumidor no debe tratar la evidencia como auténtica sin
    validarla mediante el mecanismo confiable correspondiente.
    """

    def authorize_revocation(
        self,
        request: GrantRevocationAuthorizationRequest,
    ) -> VerifiedGrantRevocationAuthorization | None:
        """Devuelve evidencia vinculada a la solicitud o None si se deniega."""
