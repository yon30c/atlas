
"""Servicio de solicitudes, aprobación y rechazo de renovaciones."""
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta

from atlas.authorization.identity_evidence import require_verified_owner_context
from atlas.authorization.models import (
    Grant,
    GrantRenewalRequest,
    RenewalStatus,
)
from atlas.core.context import OperationContext
from atlas.core.errors import (
    AuthorizationError,
    ConcurrencyError,
    ContractError,
    NotFoundError,
)
from atlas.core.user_identity import CanonicalUserIdentity
from atlas.core.verified_identity_context import VerifiedIdentityContext
from atlas.ports.verified_identity_context_verifier import (
    VerifiedIdentityContextVerifierPort,
)
from atlas.ports.authorization_unit_of_work import AuthorizationUnitOfWork
from atlas.ports.grant_renewals import GrantRenewalRepository
from atlas.ports.grants import GrantRepository


class GrantRenewalService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], AuthorizationUnitOfWork],
        *,
        identity_verifier: VerifiedIdentityContextVerifierPort | None = None,
    ) -> None:
        if not callable(unit_of_work_factory):
            raise ContractError("unit_of_work_factory debe ser invocable")
        self._unit_of_work_factory = unit_of_work_factory
        self._identity_verifier = identity_verifier

    def request_renewal(
        self,
        context: OperationContext,
        renewal_id: str,
        grant_id: str,
        proposed_expires_at: datetime,
        now: datetime,
    ) -> GrantRenewalRequest:
        """Fail closed until independent AGENT proof and delegation authority exist.

        The current native identity pipeline attests USER identities only.
        OperationContext and DelegationMode.DELEGATED are caller-controlled
        metadata and cannot authorize an agent renewal request.
        """
        raise AuthorizationError(
            "Solicitud de renovación por AGENT deshabilitada: "
            "requiere autenticación AGENT y delegación verificable"
        )

    def approve_renewal(
        self,
        context: OperationContext,
        renewal_id: str,
        now: datetime,
        *,
        verified_identity: VerifiedIdentityContext | None = None,
    ) -> Grant:
        canonical = self._validate_owner_context(context, verified_identity)
        self._validate_utc(now, "now")
        self._validate_identifier(renewal_id, "renewal_id")

        with self._unit_of_work_factory() as uow:
            request = self._get_renewal(uow.renewals, renewal_id)
            grant = self._get_grant(uow.grants, request.grant_id)

            self._validate_owner_and_scope(context, request, grant, canonical)
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
                revision=grant.revision + 1,
            )
            approved_request = replace(
                request,
                status=RenewalStatus.APPROVED,
                decided_at=now,
                decided_by_user_id=canonical.user_id,
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
        *,
        verified_identity: VerifiedIdentityContext | None = None,
    ) -> GrantRenewalRequest:
        canonical = self._validate_owner_context(context, verified_identity)
        self._validate_utc(now, "now")
        self._validate_identifier(renewal_id, "renewal_id")

        with self._unit_of_work_factory() as uow:
            request = self._get_renewal(uow.renewals, renewal_id)
            grant = self._get_grant(uow.grants, request.grant_id)

            self._validate_owner_and_scope(context, request, grant, canonical)
            self._require_pending(request)
            self._validate_renewal_grant_binding(request, grant)

            expected_version = request.version
            rejected_request = replace(
                request,
                status=RenewalStatus.REJECTED,
                decided_at=now,
                decided_by_user_id=canonical.user_id,
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

    def _validate_owner_context(
        self,
        context: OperationContext,
        verified_identity: VerifiedIdentityContext | None,
    ) -> CanonicalUserIdentity:
        return require_verified_owner_context(
            context,
            verified_identity,
            self._identity_verifier,
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
        canonical: CanonicalUserIdentity,
    ) -> None:
        if (
            canonical.user_id != request.owner_user_id
            or canonical.user_id != grant.owner_user_id
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
