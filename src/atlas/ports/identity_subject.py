"""Puerto para vincular identidad Atlas con sujeto autenticado."""
from typing import Protocol

from atlas.authorization.identity_binding import AuthenticatedUserSubject


class IdentitySubjectBindingPort(Protocol):
    """Consulta una fuente de identidad confiable."""

    def resolve_user_subject(
        self,
        actor_identity_id: str,
    ) -> AuthenticatedUserSubject | None:
        """Devuelve la vinculación autenticada o None si no puede verificarla."""
