"""Application orchestration for the offline first Platform Admin bootstrap."""

from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from atlas.core.errors import AuthorizationError, ConcurrencyError, ContractError
from atlas.core.identity import IdentityKind, IdentityStatus
from atlas.core.user_identity import CanonicalUserIdentity
from atlas.core.platform_admin import (
    INITIAL_PLATFORM_ADMIN_GRANT_TTL,
    INITIAL_PLATFORM_ADMIN_PERMISSIONS,
    PlatformAdminBootstrapCommand,
    PlatformAdminBootstrapProvenance,
    PlatformAdminBootstrapRequest,
    PlatformAdminGrant,
    PlatformAdminGrantStatus,
    PlatformAdminProvisioningMethod,
)
from atlas.ports.clock import Clock
from atlas.ports.identity_authority import IdentityAuthorityPort
from atlas.ports.platform_admin_authority import PlatformAdminBootstrapPort


class PlatformAdminBootstrapService:
    """Prepare and submit one offline bootstrap command.

    This service is not an HTTP/runtime capability. The SQLite adapter remains
    responsible for re-reading the canonical USER inside its BEGIN IMMEDIATE
    transaction, checking historical bootstrap state and persisting atomically.
    Local UID/TTY values are provenance metadata, not human authentication.
    """

    def __init__(
        self,
        *,
        identity_authority: IdentityAuthorityPort,
        bootstrap_port: PlatformAdminBootstrapPort,
        clock: Clock,
        uuid_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        if not callable(getattr(identity_authority, "get_user", None)):
            raise ContractError("identity_authority debe exponer get_user")
        if (
            not callable(getattr(bootstrap_port, "get_operation", None))
            or not callable(getattr(bootstrap_port, "provision_first_admin", None))
        ):
            raise ContractError(
                "bootstrap_port debe exponer get_operation y provision_first_admin"
            )
        if not callable(getattr(clock, "now", None)):
            raise ContractError("clock debe exponer now")
        if not callable(uuid_factory):
            raise ContractError("uuid_factory debe ser invocable")
        self._identity_authority = identity_authority
        self._bootstrap_port = bootstrap_port
        self._clock = clock
        self._uuid_factory = uuid_factory

    def provision_first_admin(
        self,
        request: PlatformAdminBootstrapRequest,
        *,
        operator_real_uid: int,
        operator_effective_uid: int,
        terminal_id: str,
    ) -> PlatformAdminGrant:
        """Build immutable provenance/grant claims and delegate atomic storage."""
        if not isinstance(request, PlatformAdminBootstrapRequest):
            raise ContractError("request debe ser PlatformAdminBootstrapRequest")
        if request.permissions != INITIAL_PLATFORM_ADMIN_PERMISSIONS:
            raise ContractError("el conjunto de permisos inicial no es válido")

        # Recover a committed operation before resolving current identity or
        # generating fresh provenance. This preserves exact idempotency after
        # a successful commit whose response was lost.
        existing = self._bootstrap_port.get_operation(request.operation_id)
        if existing is not None:
            if (
                existing.request.user_id != request.user_id
                or existing.request.permissions != request.permissions
            ):
                raise ConcurrencyError(
                    "operation_id ya está asociado a otra intención de bootstrap"
                )
            return existing.grant

        canonical = self._identity_authority.get_user(request.user_id)
        if canonical is None:
            raise AuthorizationError("el USER canónico solicitado no existe")
        if not isinstance(canonical, CanonicalUserIdentity):
            raise ContractError("Identity Authority debe devolver CanonicalUserIdentity")
        if (
            canonical.user_id != request.user_id
            or canonical.identity.kind is not IdentityKind.USER
            or canonical.identity.status is not IdentityStatus.ACTIVE
        ):
            raise AuthorizationError("el USER canónico solicitado no está activo")

        confirmed_at = self._clock.now()
        if (
            not isinstance(confirmed_at, datetime)
            or confirmed_at.tzinfo is None
            or confirmed_at.utcoffset() != timedelta(0)
        ):
            raise ContractError("clock.now() debe devolver un instante UTC consciente de zona")

        event_id = self._new_uuid("event_id")
        grant_id = self._new_uuid("grant_id")
        if event_id == grant_id:
            raise ContractError("event_id y grant_id deben ser distintos")

        provenance = PlatformAdminBootstrapProvenance(
            event_id=event_id,
            grant_id=grant_id,
            operator_real_uid=operator_real_uid,
            operator_effective_uid=operator_effective_uid,
            terminal_id=terminal_id,
            confirmed_at=confirmed_at,
        )
        grant = PlatformAdminGrant(
            grant_id=grant_id,
            user_id=canonical.user_id,
            user_identity_id=canonical.identity.identity_id,
            user_identity_revision=canonical.identity.revision,
            permissions=request.permissions,
            provisioning_method=PlatformAdminProvisioningMethod.OFFLINE_BOOTSTRAP,
            bootstrap_event_id=event_id,
            issued_at=confirmed_at,
            not_before=confirmed_at,
            expires_at=confirmed_at + INITIAL_PLATFORM_ADMIN_GRANT_TTL,
            status=PlatformAdminGrantStatus.ACTIVE,
            revision=1,
        )
        command = PlatformAdminBootstrapCommand(
            request=request,
            provenance=provenance,
            grant=grant,
        )
        return self._bootstrap_port.provision_first_admin(command)

    def _new_uuid(self, field: str) -> str:
        value = self._uuid_factory()
        if not isinstance(value, UUID) or value.version != 4:
            raise ContractError(f"uuid_factory debe devolver UUIDv4 para {field}")
        return str(value)
