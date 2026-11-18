"""Transactional Platform Admin lifecycle service for Project/Environment links."""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import uuid4

from atlas.authorization.identity_evidence import (
    require_verified_owner_context_in_unit_of_work,
)
from atlas.core.context import OperationContext
from atlas.core.errors import (
    AuthorizationError,
    ConcurrencyError,
    ContractError,
    NotFoundError,
)
from atlas.core.platform_admin import (
    PlatformAdminGrantStatus,
    PlatformAdminPermission,
    require_platform_admin_permission,
)
from atlas.core.project_environment_lifecycle import (
    ProjectEnvironmentLifecycleEvent,
    ProjectEnvironmentLifecycleRequest,
)
from atlas.core.verified_identity_context import VerifiedIdentityContext
from atlas.ports.clock import Clock
from atlas.ports.project_environment_lifecycle import (
    ProjectEnvironmentLifecycleLedgerPort,
)
from atlas.workspace.models import ProjectEnvironmentStatus


class ProjectEnvironmentLifecycleService:
    """Apply one explicitly authorized association transition atomically.

    The service receives a ledger factory rather than exposing its writer in
    the general-purpose runtime UoW. Trusted composition binds that factory
    to the active SQLite transaction.
    """

    def __init__(
        self,
        unit_of_work_factory: Callable[[], object],
        *,
        identity_verifier,
        clock: Clock,
        ledger_factory: Callable[[object], ProjectEnvironmentLifecycleLedgerPort],
    ) -> None:
        if not callable(unit_of_work_factory):
            raise ContractError("unit_of_work_factory debe ser invocable")
        if not callable(getattr(identity_verifier, "verify_in_unit_of_work", None)):
            raise ContractError("identity_verifier debe verificar dentro de la UoW")
        if not callable(getattr(clock, "now", None)):
            raise ContractError("clock debe implementar now()")
        if not callable(ledger_factory):
            raise ContractError("ledger_factory debe ser invocable")
        self._unit_of_work_factory = unit_of_work_factory
        self._identity_verifier = identity_verifier
        self._clock = clock
        self._ledger_factory = ledger_factory

    @staticmethod
    def _validate_now(value: datetime) -> None:
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() != timedelta(0)
        ):
            raise ContractError("clock.now() debe devolver datetime UTC")

    @staticmethod
    def _required_uow_capabilities(unit) -> None:
        required = ("identity", "platform_admin", "workspaces", "commit")
        if any(getattr(unit, name, None) is None for name in required):
            raise AuthorizationError(
                "Se requiere una UoW local con Identity, Platform Admin y asociaciones"
            )

    @staticmethod
    def _required_permission(target: ProjectEnvironmentStatus) -> PlatformAdminPermission:
        if target is ProjectEnvironmentStatus.SUSPENDED:
            return PlatformAdminPermission.ASSOCIATION_SUSPEND
        if target is ProjectEnvironmentStatus.ACTIVE:
            return PlatformAdminPermission.ASSOCIATION_REACTIVATE
        raise ContractError("estado objetivo de asociación no admitido")

    def transition(
        self,
        context: OperationContext,
        verified_identity: VerifiedIdentityContext,
        request: ProjectEnvironmentLifecycleRequest,
    ) -> ProjectEnvironmentLifecycleEvent:
        if not isinstance(context, OperationContext):
            raise ContractError("context debe ser OperationContext")
        if not isinstance(verified_identity, VerifiedIdentityContext):
            raise AuthorizationError("Se requiere VerifiedIdentityContext")
        if not isinstance(request, ProjectEnvironmentLifecycleRequest):
            raise ContractError("request debe ser ProjectEnvironmentLifecycleRequest")
        permission = self._required_permission(request.target_status)
        with self._unit_of_work_factory() as unit:
            self._required_uow_capabilities(unit)
            # BEGIN IMMEDIATE may wait for another writer. Capture trusted time
            # only after the transaction lock is acquired so grant expiry is
            # evaluated at the start of the protected operation, not pre-lock.
            now = self._clock.now()
            self._validate_now(now)
            canonical = require_verified_owner_context_in_unit_of_work(
                context,
                verified_identity,
                self._identity_verifier,
                unit,
            )

            grants = unit.platform_admin.list_grants_for_user(canonical.user_id)
            active_grants = tuple(
                grant for grant in grants
                if grant.status is PlatformAdminGrantStatus.ACTIVE
            )
            if len(active_grants) != 1:
                raise AuthorizationError(
                    "El usuario no tiene exactamente una autoridad Platform Admin activa"
                )
            admin_grant = active_grants[0]
            require_platform_admin_permission(
                admin_grant,
                permission=permission,
                user_id=canonical.user_id,
                user_identity_id=canonical.identity.identity_id,
                user_identity_revision=canonical.identity.revision,
                now=now,
            )

            association = unit.workspaces.get_association(
                request.project_id, request.environment_id
            )
            if association is None:
                raise NotFoundError("asociación Project/Environment no encontrada")
            if association.revision != request.expected_revision:
                raise ConcurrencyError("la revisión de la asociación cambió")
            if association.status is request.target_status:
                raise ContractError("la asociación ya tiene el estado solicitado")

            event = ProjectEnvironmentLifecycleEvent(
                event_id=str(uuid4()),
                project_id=request.project_id,
                environment_id=request.environment_id,
                previous_status=association.status,
                new_status=request.target_status,
                previous_revision=association.revision,
                new_revision=association.revision + 1,
                actor_user_id=canonical.user_id,
                actor_identity_id=canonical.identity.identity_id,
                verified_identity_context_id=verified_identity.context_id,
                request_id=context.request_id,
                correlation_id=context.correlation_id,
                reason=request.reason,
                occurred_at=now,
            )
            ledger = self._ledger_factory(unit)
            if not callable(getattr(ledger, "append_event", None)):
                raise ContractError("ledger_factory no devolvió un ledger compatible")
            ledger.append_event(event)
            unit.workspaces.update_association(
                replace(
                    association,
                    status=request.target_status,
                    revision=association.revision + 1,
                ),
                expected_revision=request.expected_revision,
                lifecycle_event_id=event.event_id,
            )
            unit.commit()
            return event
