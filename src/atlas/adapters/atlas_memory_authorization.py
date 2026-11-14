"""Adaptador de compatibilidad entre el contexto neutral y CAM de Atlas."""
from datetime import datetime

from atlas.authorization.memory_service import MemoryAuthorizationService
from atlas.authorization.models import AuthorizationDecision, AuthorizationResult
from atlas.core.context import OperationContext
from atlas.core.enums import DelegationMode
from atlas.core.identity import Identity, IdentityKind, IdentityStatus
from atlas.memory.context import MemoryRequestContext
from atlas.memory.models import MemoryId, MemoryVersionId


class AtlasMemoryAuthorizationAdapter:
    """Traduce el contrato neutral al contexto heredado de AtlasCore.

    Debe recibir exclusivamente contextos emitidos por la frontera de identidad
    confiable de la aplicación consumidora. La traducción no autentica ni eleva
    la confianza de los atributos recibidos.
    """

    def __init__(self, service: MemoryAuthorizationService) -> None:
        self._service = service

    @staticmethod
    def _deny() -> AuthorizationResult:
        return AuthorizationResult(AuthorizationDecision.DENY)

    def authorize_read(
        self,
        context: MemoryRequestContext,
        memory_id: MemoryId,
        now: datetime,
        version_id: MemoryVersionId | None = None,
    ) -> AuthorizationResult:
        if not isinstance(context, MemoryRequestContext):
            return self._deny()
        try:
            actor = Identity(
                identity_id=context.actor_id,
                kind=IdentityKind(context.actor_kind),
                status=IdentityStatus(context.actor_status),
                revision=context.actor_revision,
            )
            delegation = (
                DelegationMode(context.delegation)
                if context.delegation is not None
                else None
            )
            atlas_context = OperationContext(
                request_id=context.request_id,
                correlation_id=context.correlation_id,
                actor=actor,
                user_id=context.user_id,
                origin=context.origin,
                delegation=delegation,
                project_id=context.project_id,
                environment=context.environment,
                purpose=context.purpose,
                classification=context.classification,
                created_at=context.created_at,
            )
        except (TypeError, ValueError):
            return self._deny()
        return self._service.authorize_read(
            atlas_context, memory_id, now, version_id
        )
