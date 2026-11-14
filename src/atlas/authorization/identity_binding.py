"""Vinculación fail-closed entre actores USER y sujetos autenticados."""
from dataclasses import dataclass
from typing import Protocol

from atlas.core.context import OperationContext
from atlas.core.errors import ContractError
from atlas.core.identity import IdentityKind, IdentityStatus


@dataclass(frozen=True, slots=True)
class AuthenticatedUserSubject:
    """Vinculación emitida por una frontera de identidad confiable."""

    actor_identity_id: str
    subject_user_id: str
    is_active: bool
    revision: int

    def __post_init__(self) -> None:
        for field in ("actor_identity_id", "subject_user_id"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"{field} debe ser una cadena no vacía")
        if not isinstance(self.is_active, bool):
            raise ContractError("is_active debe ser bool")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise ContractError("revision debe ser un entero positivo")


class IdentitySubjectBindingPort(Protocol):
    """Resuelve la vinculación desde evidencia autenticada, no del contexto."""

    def resolve_user_subject(
        self,
        actor_identity_id: str,
    ) -> AuthenticatedUserSubject | None:
        """Devuelve la vinculación verificada para el actor indicado."""


def resolve_authenticated_user_binding(
    context: OperationContext,
    binding_port: IdentitySubjectBindingPort,
) -> AuthenticatedUserSubject | None:
    """Devuelve la vinculación completa y versionada desde la fuente confiable."""
    if not isinstance(context, OperationContext):
        return None
    if context.actor.kind is not IdentityKind.USER:
        return None
    if context.actor.status is not IdentityStatus.ACTIVE:
        return None
    if not callable(getattr(binding_port, "resolve_user_subject", None)):
        return None
    try:
        binding = binding_port.resolve_user_subject(context.actor.identity_id)
    except Exception:
        return None
    if not isinstance(binding, AuthenticatedUserSubject):
        return None
    if not binding.is_active or binding.actor_identity_id != context.actor.identity_id:
        return None
    if binding.revision != context.actor.revision:
        return None
    return binding


def resolve_authenticated_user_subject(
    context: OperationContext,
    binding_port: IdentitySubjectBindingPort,
) -> str | None:
    """Devuelve el sujeto solo si la frontera confiable confirma la vinculación."""
    binding = resolve_authenticated_user_binding(context, binding_port)
    return binding.subject_user_id if binding is not None else None
