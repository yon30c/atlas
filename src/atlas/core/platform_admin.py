"""Domain contracts for narrowly scoped platform-administrator authority."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from atlas.core.errors import AuthorizationError, ContractError
from atlas.core.user_identity import validate_canonical_uuid4


class PlatformAdminPermission(str, Enum):
    """Independent permissions for Project/Environment association lifecycle."""

    ASSOCIATION_SUSPEND = "association.suspend"
    ASSOCIATION_REACTIVATE = "association.reactivate"


class PlatformAdminGrantStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


class PlatformAdminProvisioningMethod(str, Enum):
    """Only the operator-controlled offline bootstrap is currently defined."""

    OFFLINE_BOOTSTRAP = "offline_bootstrap"


def _utc(value: object, field: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ContractError(f"{field} debe ser datetime UTC")


def _revision(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractError(f"{field} debe ser un entero positivo")


@dataclass(frozen=True, slots=True)
class PlatformAdminGrant:
    """Canonical, non-transitive platform-admin authority for one USER identity.

    This record is not an authenticated identity and is not sufficient by
    itself to authorize an operation. Consumers must resolve the canonical
    USER identity and this grant inside the same trusted unit of work.
    """

    grant_id: str
    user_id: str
    user_identity_id: str
    user_identity_revision: int
    permissions: frozenset[PlatformAdminPermission]
    provisioning_method: PlatformAdminProvisioningMethod
    bootstrap_event_id: str
    issued_at: datetime
    not_before: datetime
    expires_at: datetime
    status: PlatformAdminGrantStatus = PlatformAdminGrantStatus.ACTIVE
    revision: int = 1
    revoked_at: datetime | None = None
    revoked_by_user_id: str | None = None

    def __post_init__(self) -> None:
        for field in ("grant_id", "user_id", "user_identity_id", "bootstrap_event_id"):
            validate_canonical_uuid4(getattr(self, field), field)
        _revision(self.user_identity_revision, "user_identity_revision")
        _revision(self.revision, "revision")
        if not isinstance(self.permissions, frozenset) or not self.permissions:
            raise ContractError("permissions debe ser un frozenset no vacío")
        if any(not isinstance(item, PlatformAdminPermission) for item in self.permissions):
            raise ContractError("permissions contiene permisos no reconocidos")
        if not isinstance(self.provisioning_method, PlatformAdminProvisioningMethod):
            raise ContractError("provisioning_method no reconocido")
        if not isinstance(self.status, PlatformAdminGrantStatus):
            raise ContractError("status no reconocido")
        for field in ("issued_at", "not_before", "expires_at"):
            _utc(getattr(self, field), field)
        if self.not_before < self.issued_at:
            raise ContractError("not_before no puede preceder issued_at")
        if self.expires_at <= self.not_before:
            raise ContractError("expires_at debe ser posterior a not_before")
        if self.revoked_at is not None:
            _utc(self.revoked_at, "revoked_at")
        if self.status is PlatformAdminGrantStatus.ACTIVE:
            if self.revoked_at is not None or self.revoked_by_user_id is not None:
                raise ContractError("una concesión activa no puede tener datos de revocación")
        else:
            if self.revoked_at is None or self.revoked_by_user_id is None:
                raise ContractError("una concesión revocada requiere auditoría completa")
            validate_canonical_uuid4(self.revoked_by_user_id, "revoked_by_user_id")


def require_platform_admin_permission(
    grant: PlatformAdminGrant,
    *,
    permission: PlatformAdminPermission,
    user_id: str,
    user_identity_id: str,
    user_identity_revision: int,
    now: datetime,
) -> None:
    """Apply the grant's local claims; canonical identity lookup remains caller-owned."""
    if not isinstance(grant, PlatformAdminGrant):
        raise ContractError("grant debe ser PlatformAdminGrant")
    if not isinstance(permission, PlatformAdminPermission):
        raise ContractError("permission debe ser PlatformAdminPermission")
    validate_canonical_uuid4(user_id, "user_id")
    validate_canonical_uuid4(user_identity_id, "user_identity_id")
    _revision(user_identity_revision, "user_identity_revision")
    _utc(now, "now")
    if grant.status is not PlatformAdminGrantStatus.ACTIVE:
        raise AuthorizationError("la autoridad administrativa no está activa")
    if (
        grant.user_id != user_id
        or grant.user_identity_id != user_identity_id
        or grant.user_identity_revision != user_identity_revision
    ):
        raise AuthorizationError("la autoridad administrativa no coincide con la identidad USER")
    if now < grant.not_before or now >= grant.expires_at:
        raise AuthorizationError("la autoridad administrativa está fuera de su ventana temporal")
    if permission not in grant.permissions:
        raise AuthorizationError("la autoridad administrativa no concede la acción solicitada")
