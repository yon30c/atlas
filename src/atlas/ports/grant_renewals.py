"""Puerto de persistencia para solicitudes de renovación."""
from typing import Protocol

from atlas.authorization.models import GrantRenewalRequest


class GrantRenewalRepository(Protocol):

    def create(self, request: GrantRenewalRequest) -> None:
        """Registra una solicitud."""
        ...

    def get(self, renewal_id: str) -> GrantRenewalRequest | None:
        """Busca una solicitud por identificador."""
        ...

    def update(self, request: GrantRenewalRequest) -> None:
        """Actualiza una solicitud."""
        ...

    def update_if_version(
        self,
        request: GrantRenewalRequest,
        expected_version: int,
    ) -> bool:
        """Actualiza solo si la versión almacenada coincide."""
        ...

    def list_by_grant(
        self,
        grant_id: str,
    ) -> tuple[GrantRenewalRequest, ...]:
        """Lista las solicitudes asociadas a un Grant."""
        ...