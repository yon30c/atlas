"""Evaluador puro de autorización CAM."""
from collections.abc import Iterable
from datetime import datetime, timedelta

from atlas.authorization.models import (
    AuthorizationDecision,
    AuthorizationRequest,
    AuthorizationResult,
    Grant,
)
from atlas.core.errors import ContractError
from atlas.core.identity import IdentityStatus


class AuthorizationEvaluator:
    """Evalúa solicitudes contra Grants explícitos."""

    def evaluate(
        self,
        request: AuthorizationRequest,
        grants: Iterable[Grant],
        now: datetime,
    ) -> AuthorizationResult:
        if not isinstance(request, AuthorizationRequest):
            raise ContractError("request debe ser AuthorizationRequest")
        self._validate_utc(now)

        if request.context.actor.status != IdentityStatus.ACTIVE:
            return AuthorizationResult(AuthorizationDecision.DENY)

        for grant in grants:
            if not isinstance(grant, Grant):
                raise ContractError("Todos los elementos deben ser Grant")
            if self._matches(request, grant, now):
                return AuthorizationResult(AuthorizationDecision.ALLOW)

        return AuthorizationResult(AuthorizationDecision.DENY)

    @staticmethod
    def _matches(
        request: AuthorizationRequest,
        grant: Grant,
        now: datetime,
    ) -> bool:
        context = request.context
        return all(
            (
                grant.subject_identity_id == context.actor.identity_id,
                grant.owner_user_id == request.resource_owner_id,
                grant.owner_user_id == context.user_id,
                grant.project_id == context.project_id,
                grant.environment == context.environment,
                grant.resource_type == request.resource_type,
                request.action in grant.actions,
                grant.issued_at <= now < grant.expires_at,
                grant.revoked_at is None or grant.revoked_at > now,
            )
        )

    @staticmethod
    def _validate_utc(value: datetime) -> None:
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ContractError("now debe ser un datetime con zona horaria")
        if value.utcoffset() != timedelta(0):
            raise ContractError("now debe estar en UTC")
