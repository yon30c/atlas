"""Servicio de administración del ciclo de vida de Grants."""
from dataclasses import replace
from datetime import datetime, timedelta

from atlas.authorization.models import Grant
from atlas.core.context import OperationContext
from atlas.core.errors import (
    AuthorizationError,
    ContractError,
    NotFoundError,
)
from atlas.core.identity import IdentityKind, IdentityStatus
from atlas.ports.grants import GrantRepository


class GrantManagementService:
    """Administra Grants bajo autoridad explícita del propietario."""

    def __init__(self, repository: GrantRepository) -> None:
        self._repository = repository

    def issue(
        self,
        context: OperationContext,
        grant: Grant,
        now: datetime,
    ) -> Grant:
        """Emite un Grant si el actor es su propietario."""
        self._validate_owner_context(context)
        self._validate_utc(now)
        if not isinstance(grant, Grant):
            raise ContractError("grant debe ser Grant")
        if grant.owner_user_id != context.user_id:
            raise AuthorizationError(
                "No se pueden emitir Grants para otro propietario"
            )
        if grant.project_id != context.project_id:
            raise AuthorizationError(
                "El proyecto del Grant no coincide con el contexto"
            )
        if grant.environment != context.environment:
            raise AuthorizationError(
                "El entorno del Grant no coincide con el contexto"
            )
        if grant.revision != 1:
            raise ContractError("un Grant nuevo debe iniciar en revision 1")
        if grant.issued_at != now:
            raise ContractError(
                "issued_at debe coincidir con el momento de emisión"
            )
        if self._repository.get(grant.grant_id) is not None:
            raise ContractError("El grant_id ya existe")
        self._repository.create(grant)
        return grant

    def revoke(
        self,
        context: OperationContext,
        grant_id: str,
        now: datetime,
    ) -> Grant:
        """Revoca un Grant sin eliminarlo ni alterar una revocación previa."""
        self._validate_owner_context(context)
        self._validate_utc(now)
        if not isinstance(grant_id, str) or not grant_id.strip():
            raise ContractError("grant_id debe ser una cadena no vacía")

        grant = self._repository.get(grant_id)
        if grant is None:
            raise NotFoundError("Grant no encontrado")
        if not isinstance(grant, Grant):
            raise ContractError("El repositorio debe devolver un Grant")
        if grant.owner_user_id != context.user_id:
            raise AuthorizationError(
                "No se pueden revocar Grants de otro propietario"
            )
        if grant.revoked_at is not None:
            return grant

        revoked_grant = replace(grant, revoked_at=now, revision=grant.revision + 1)
        self._repository.update(revoked_grant)
        return revoked_grant

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
    def _validate_utc(value: datetime) -> None:
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ContractError("now debe ser un datetime con zona horaria")
        if value.utcoffset() != timedelta(0):
            raise ContractError("now debe estar en UTC")
