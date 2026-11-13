"""Servicio CAM para autorizar lecturas de memoria sin exponer contenido."""

from datetime import datetime, timedelta
from uuid import uuid4

from atlas.authorization.evaluator import AuthorizationEvaluator
from atlas.authorization.identity_binding import (
    IdentitySubjectBindingPort,
    resolve_authenticated_user_binding,
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
from atlas.memory.consistency import (
    AuthorityKind,
    AuthorityRevision,
    AuthorizationRevisionSet,
    AuthorizationSnapshot,
)
from atlas.memory.models import (
    MemoryClassification,
    MemoryId,
    MemoryScopeKind,
    MemoryVersionId,
    MemoryVersionStatus,
)
from atlas.ports.grants import GrantRepository


class MemoryAuthorizationService:
    """Evalúa acceso a una memoria usando metadatos y Grants autoritativos."""

    READ_ACTION = "memory.read"

    def __init__(
        self,
        metadata_resolver: MemoryMetadataResolver,
        identity_binding_port: IdentitySubjectBindingPort,
        evaluator: AuthorizationEvaluator | None = None,
        grant_repository: GrantRepository | None = None,
    ) -> None:
        self._metadata = metadata_resolver
        self._identity_binding = identity_binding_port
        self._evaluator = evaluator or AuthorizationEvaluator()
        self._grant_repository = grant_repository

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
        version_id: MemoryVersionId | None = None,
    ) -> AuthorizationResult:
        """Autoriza la memoria exacta y, opcionalmente, su versión exacta.

        Los Grants se obtienen internamente desde el repositorio confiable,
        utilizando el owner_id canónico de Memory. El solicitante no puede
        suministrar permisos. Este método nunca recupera contenido.
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
                binding = resolve_authenticated_user_binding(
                    context, self._identity_binding
                )
                if binding is None or binding.subject_user_id != memory.owner_id:
                    return self._deny()
                revisions = AuthorizationRevisionSet(
                    memory_revision=AuthorityRevision(
                        AuthorityKind.MEMORY, memory.memory_id, memory.revision
                    ),
                    version_revision=AuthorityRevision(
                        AuthorityKind.MEMORY_VERSION, version.version_id, version.revision
                    ),
                    identity_revision=AuthorityRevision(
                        AuthorityKind.IDENTITY, context.actor.identity_id, context.actor.revision
                    ),
                )
                snapshot = AuthorizationSnapshot(
                    snapshot_id=uuid4().hex,
                    decision_id=uuid4().hex,
                    request_id=context.request_id,
                    action=self.READ_ACTION,
                    actor_identity_id=context.actor.identity_id,
                    subject_user_id=binding.subject_user_id,
                    memory_id=memory.memory_id,
                    version_id=version.version_id,
                    owner_id=memory.owner_id,
                    scope=memory.scope,
                    revisions=revisions,
                    version_status=version.status,
                    classification=version.classification,
                    issued_at=now,
                )
                return AuthorizationResult(AuthorizationDecision.ALLOW, snapshot)

            if memory.scope.kind is not MemoryScopeKind.PROJECT:
                return self._deny()
            project_id = memory.scope.project_id
            if project_id is None or context.project_id != project_id:
                return self._deny()
            if context.environment is None or self._grant_repository is None:
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
            grants = self._grant_repository.list_by_owner(memory.owner_id)
            if not isinstance(grants, tuple) or any(
                not isinstance(grant, Grant) for grant in grants
            ):
                return self._deny()
            evaluation = self._evaluator.evaluate(request, grants, now)
            if evaluation.decision is not AuthorizationDecision.ALLOW:
                return self._deny()
            grant = evaluation.matched_grant
            if not isinstance(grant, Grant):
                return self._deny()
            revisions = AuthorizationRevisionSet(
                memory_revision=AuthorityRevision(
                    AuthorityKind.MEMORY, memory.memory_id, memory.revision
                ),
                version_revision=AuthorityRevision(
                    AuthorityKind.MEMORY_VERSION, version.version_id, version.revision
                ),
                identity_revision=AuthorityRevision(
                    AuthorityKind.IDENTITY, context.actor.identity_id, context.actor.revision
                ),
                project_revision=AuthorityRevision(
                    AuthorityKind.PROJECT, project.project_id, project.revision
                ),
                environment_revision=AuthorityRevision(
                    AuthorityKind.ENVIRONMENT, environment.environment_id, environment.revision
                ),
                grant_revision=AuthorityRevision(
                    AuthorityKind.GRANT, grant.grant_id, grant.revision
                ),
            )
            snapshot = AuthorizationSnapshot(
                snapshot_id=uuid4().hex,
                decision_id=uuid4().hex,
                request_id=context.request_id,
                action=self.READ_ACTION,
                actor_identity_id=context.actor.identity_id,
                subject_user_id=None,
                memory_id=memory.memory_id,
                version_id=version.version_id,
                owner_id=memory.owner_id,
                scope=memory.scope,
                revisions=revisions,
                version_status=version.status,
                classification=version.classification,
                issued_at=now,
                project_id=project.project_id,
                environment_id=environment.environment_id,
                grant_expires_at=grant.expires_at,
            )
            return AuthorizationResult(AuthorizationDecision.ALLOW, snapshot)
        except Exception:
            return self._deny()
