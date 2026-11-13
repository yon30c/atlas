"""Servicio CAM para autorizar lecturas de memoria sin exponer contenido."""

from datetime import datetime, timedelta
from collections.abc import Iterable

from atlas.authorization.evaluator import AuthorizationEvaluator
from atlas.authorization.identity_binding import (
    IdentitySubjectBindingPort,
    resolve_authenticated_user_subject,
)
from atlas.authorization.memory_metadata_resolver import MemoryMetadataResolver
from atlas.authorization.models import (
    AuthorizationDecision,
    AuthorizationRequest,
    AuthorizationResult,
    Grant,
)
from atlas.core.context import OperationContext
from atlas.core.identity import IdentityStatus
from atlas.memory.models import (
    MemoryClassification,
    MemoryId,
    MemoryScopeKind,
    MemoryVersionId,
    MemoryVersionStatus,
)


class MemoryAuthorizationService:
    """Evalúa acceso a una memoria usando solo metadatos autoritativos."""

    READ_ACTION = "memory.read"

    def __init__(
        self,
        metadata_resolver: MemoryMetadataResolver,
        identity_binding_port: IdentitySubjectBindingPort,
        evaluator: AuthorizationEvaluator | None = None,
    ) -> None:
        self._metadata = metadata_resolver
        self._identity_binding = identity_binding_port
        self._evaluator = evaluator or AuthorizationEvaluator()

    @staticmethod
    def _deny() -> AuthorizationResult:
        return AuthorizationResult(AuthorizationDecision.DENY)

    @staticmethod
    def _valid_utc(value: datetime) -> bool:
        return (
            isinstance(value, datetime)
            and value.tzinfo is not None
            and value.utcoffset() == timedelta(0)
        )

    def authorize_read(
        self,
        context: OperationContext,
        memory_id: MemoryId,
        now: datetime,
        grants: Iterable[Grant] = (),
        version_id: MemoryVersionId | None = None,
    ) -> AuthorizationResult:
        """Autoriza la memoria exacta y, opcionalmente, su versión exacta.

        Este método no devuelve ni consulta contenido. Un fallo de identidad,
        metadatos, scope, clasificación o CAM produce DENY.
        """
        if not isinstance(context, OperationContext) or not self._valid_utc(now):
            return self._deny()
        if context.actor.status is not IdentityStatus.ACTIVE:
            return self._deny()

        try:
            memory = self._metadata.resolve_memory(memory_id)
            if memory is None:
                return self._deny()

            target_version_id = (
                version_id
                if version_id is not None
                else memory.current_approved_version_id
            )
            if target_version_id is None:
                return self._deny()

            version = self._metadata.resolve_version(memory_id, target_version_id)
            if version is None:
                return self._deny()
            if version.status is not MemoryVersionStatus.APPROVED:
                return self._deny()
            if version.classification is MemoryClassification.RESTRICTED:
                return self._deny()

            if memory.scope.kind is MemoryScopeKind.PRIVATE:
                if memory.scope.project_id is not None:
                    return self._deny()
                if context.actor.kind.value != "user":
                    return self._deny()
                subject_user_id = resolve_authenticated_user_subject(
                    context, self._identity_binding
                )
                if subject_user_id is None or subject_user_id != memory.owner_id:
                    return self._deny()
                return AuthorizationResult(AuthorizationDecision.ALLOW)

            if memory.scope.kind is not MemoryScopeKind.PROJECT:
                return self._deny()
            project_id = memory.scope.project_id
            if project_id is None or context.project_id != project_id:
                return self._deny()
            if context.environment is None:
                return self._deny()

            project = self._metadata.resolve_project(project_id)
            if project is None or project.status != "active":
                return self._deny()
            environment = self._metadata.resolve_environment(context.environment)
            if environment is None or environment.status != "active":
                return self._deny()

            request = AuthorizationRequest(
                context=context,
                action=self.READ_ACTION,
                resource_type="memory",
                resource_id=memory_id,
                resource_owner_id=memory.owner_id,
            )
            return self._evaluator.evaluate(request, grants, now)
        except Exception:
            return self._deny()
