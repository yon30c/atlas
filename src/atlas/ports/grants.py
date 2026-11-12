"""Puerto de persistencia para Grants."""
from typing import Protocol

from atlas.authorization.models import Grant


class GrantRepository(Protocol):
    """Contrato de almacenamiento de Grants."""

    def create(self, grant: Grant) -> None:
        """Registra un Grant nuevo."""

    def get(self, grant_id: str) -> Grant | None:
        """Busca un Grant por identificador."""

    def update(self, grant: Grant) -> None:
        """Actualiza un Grant existente."""

    def list_by_owner(self, owner_user_id: str) -> tuple[Grant, ...]:
        """Devuelve los Grants de un propietario."""
