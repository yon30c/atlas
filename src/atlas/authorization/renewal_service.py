
"""Servicio de solicitudes, aprobación y rechazo de renovaciones."""
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta

from atlas.authorization.models import (
    Grant,
    GrantRenewalRequest,
    RenewalStatus,
)
from atlas.core.context import OperationContext
from atlas.core.enums import DelegationMode
from atlas.core.errors import (
    AuthorizationError,
    ConcurrencyError,
    ContractError,
    NotFoundError,
)
from atlas.core.identity import IdentityKind, IdentityStatus
from atlas.ports.authorization_unit_of_work import AuthorizationUnitOfWork
from atlas.ports.grant_renewals import GrantRenewalRepository
from atlas.ports.grants import GrantRepository


class GrantRenewalService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], AuthorizationUnitOfWork],
    ) -> None:
        if not callable(unit_of_work_factory):
            raise ContractError("unit_of_work_factory debe ser invocable")
        self._unit_of_work_factory = unit_of_work_factory

    def request_renewal(
        self,
        context: OperationContext,
        renewal_id: str,
        grant_id: str,
        proposed_expires_at: datetime,
        now: datetime,
    ) -> GrantRenewalRequest:
        self._validate_requester_context(context)
        self._validate_utc(now, "now")
        self._validate_utc(proposed_expires_at, "proposed_expires_at")
        self._validate_identifier(renewal_id, "renewal_id")
        self._validate_identifier(grant_id, "grant_id")

        with self._unit_of_work_factory() as uow:
            grant = self._get_grant(uow.grants, grant_id)
            self._validate_scope(context, grant)

            if (
                context.user_id != grant.owner_user_id
                or context.actor.identity_id != grant.subject_identity_id
            ):
                raise AuthorizationError(
                    "Solo la identidad destinataria puede solicitar la renovación"
                )

            self._validate_grant_active(grant, now)

            if proposed_expires_at <= grant.expires_at:
                raise ContractError(
                    "La nueva fecha debe ser posterior al vencimiento actual"
                )

            if self._get_existing_renewal(uow.renewals, renewal_id):
                raise ContractError("El renewal_id ya existe")

            request = GrantRenewalRequest(
                renewal_id=renewal_id,
                grant_id=grant.grant_id,
                owner_user_id=grant.owner_user_id,
                subject_identity_id=grant.subject_identity_id,
                requested_by_identity_id=context.actor.identity_id,
                current_expires_at=grant.expires_at,
                proposed_expires_at=proposed_expires_at,
                requested_at=now,
            )

            uow.renewals.create(request)
            uow.commit()

        return request

    def approve_renewal(
        self,
        context: OperationContext,
        renewal_id: str,
        now: datetime,
    ) -> Grant:
        self._validate_owner_context(context)
        self._validate_utc(now, "now")
        self._validate_identifier(renewal_id, "renewal_id")

        with self._unit_of_work_factory() as uow:
            request = self._get_renewal(uow.renewals, renewal_id)
            grant = self._get_grant(uow.grants, request.grant_id)

            self._validate_owner_and_scope(context, request, grant)
            self._require_pending(request)
            self._validate_renewal_grant_binding(request, grant)

            if grant.expires_at != request.current_expires_at:
                raise ContractError(
                    "El vencimiento del Grant cambió desde la solicitud"
                )

            self._validate_grant_active(grant, now)

            expected_version = request.version
            updated_grant = replace(
                grant,
                expires_at=request.proposed_expires_at,
            )
            approved_request = replace(
                request,
                status=RenewalStatus.APPROVED,
                decided_at=now,
                decided_by_user_id=context.user_id,
                version=expected_version + 1,
            )

            uow.grants.update(updated_grant)
            updated = uow.renewals.update_if_version(
                approved_request,
                expected_version,
            )
            if not updated:
                raise ConcurrencyError(
                    "La solicitud cambió durante la aprobación"
                )
            uow.commit()

        return updated_grant

    def reject_renewal(
        self,
        context: OperationContext,
        renewal_id: str,
        now: datetime,
    ) -> GrantRenewalRequest:
        self._validate_owner_context(context)
        self._validate_utc(now, "now")
        self._validate_identifier(renewal_id, "renewal_id")

        with self._unit_of_work_factory() as uow:
            request = self._get_renewal(uow.renewals, renewal_id)
            grant = self._get_grant(uow.grants, request.grant_id)

            self._validate_owner_and_scope(context, request, grant)
            self._require_pending(request)
            self._validate_renewal_grant_binding(request, grant)

            expected_version = request.version
            rejected_request = replace(
                request,
                status=RenewalStatus.REJECTED,
                decided_at=now,
                decided_by_user_id=context.user_id,
                version=expected_version + 1,
            )

            updated = uow.renewals.update_if_version(
                rejected_request,
                expected_version,
            )
            if not updated:
                raise ConcurrencyError(
                    "La solicitud cambió durante el rechazo"
                )
            uow.commit()

        return rejected_request

    @staticmethod
    def _get_grant(
        repository: GrantRepository,
        grant_id: str,
    ) -> Grant:
        grant = repository.get(grant_id)
        if grant is None:
            raise NotFoundError("Grant no encontrado")
        if not isinstance(grant, Grant):
            raise ContractError("El repositorio debe devolver un Grant")
        return grant

    @staticmethod
    def _get_renewal(
        repository: GrantRenewalRepository,
        renewal_id: str,
    ) -> GrantRenewalRequest:
        request = repository.get(renewal_id)
        if request is None:
            raise NotFoundError("Solicitud de renovación no encontrada")
        if not isinstance(request, GrantRenewalRequest):
            raise ContractError(
                "El repositorio debe devolver una solicitud de renovación"
            )
        return request

    @staticmethod
    def _get_existing_renewal(
        repository: GrantRenewalRepository,
        renewal_id: str,
    ) -> GrantRenewalRequest | None:
        request = repository.get(renewal_id)
        if request is not None and not isinstance(
            request, GrantRenewalRequest
        ):
            raise ContractError(
                "El repositorio debe devolver una solicitud de renovación"
            )
        return request

    @staticmethod
    def _validate_requester_context(context: OperationContext) -> None:
        if not isinstance(context, OperationContext):
            raise ContractError("context debe ser OperationContext")

        actor = context.actor
        if (
            actor.kind is not IdentityKind.AGENT
            or actor.status is not IdentityStatus.ACTIVE
        ):
            raise AuthorizationError(
                "Solo un agente activo puede solicitar la renovación"
            )
        if context.delegation is not DelegationMode.DELEGATED:
            raise AuthorizationError(
                "El agente debe actuar bajo delegación explícita para renovar el Grant"
            )

    @staticmethod
    def _validate_owner_context(context: OperationContext) -> None:
        if not isinstance(context, OperationContext):
            raise ContractError("context debe ser OperationContext")

        actor = context.actor
        if (
            actor.kind is not IdentityKind.USER
            or actor.status is not IdentityStatus.ACTIVE
            or actor.identity_id != context.user_id
        ):
            raise AuthorizationError(
                "Se requiere un usuario propietario activo"
            )

    @staticmethod
    def _validate_scope(
        context: OperationContext,
        grant: Grant,
    ) -> None:
        if context.project_id != grant.project_id:
            raise AuthorizationError(
                "El proyecto del contexto no coincide con el Grant"
            )
        if context.environment != grant.environment:
            raise AuthorizationError(
                "El entorno del contexto no coincide con el Grant"
            )

    def _validate_owner_and_scope(
        self,
        context: OperationContext,
        request: GrantRenewalRequest,
        grant: Grant,
    ) -> None:
        if (
            context.user_id != request.owner_user_id
            or context.user_id != grant.owner_user_id
        ):
            raise AuthorizationError(
                "Solo el propietario puede decidir la renovación"
            )
        self._validate_scope(context, grant)

    @staticmethod
    def _validate_renewal_grant_binding(
        request: GrantRenewalRequest,
        grant: Grant,
    ) -> None:
        if (
            request.grant_id != grant.grant_id
            or request.owner_user_id != grant.owner_user_id
            or request.subject_identity_id != grant.subject_identity_id
            or request.requested_by_identity_id != grant.subject_identity_id
        ):
            raise ContractError(
                "El Grant ya no corresponde a la solicitud de renovación"
            )

    @staticmethod
    def _validate_grant_active(grant: Grant, now: datetime) -> None:
        if not (
            grant.issued_at <= now < grant.expires_at
            and (grant.revoked_at is None or grant.revoked_at > now)
        ):
            raise AuthorizationError(
                "El Grant debe estar vigente y no revocado"
            )

    @staticmethod
    def _require_pending(request: GrantRenewalRequest) -> None:
        if request.status is not RenewalStatus.PENDING:
            raise ContractError(
                "La solicitud de renovación ya fue decidida"
            )

    @staticmethod
    def _validate_identifier(value: str, field: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ContractError(f"{field} debe ser una cadena no vacía")

    @staticmethod
    def _validate_utc(value: datetime, field: str) -> None:
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ContractError(
                f"{field} debe ser un datetime con zona horaria"
            )
        if value.utcoffset() != timedelta(0):
            raise ContractError(f"{field} debe estar en UTC")
