"""Read-only port for canonical platform-administrator authority."""

from typing import Protocol

from atlas.core.platform_admin import PlatformAdminGrant


class PlatformAdminAuthorityReaderPort(Protocol):
    """Resolve administrator grants; this port cannot issue or mutate authority."""

    def get_grant(self, grant_id: str) -> PlatformAdminGrant | None:
        """Return the exact canonical grant, including revoked tombstones."""

    def list_grants_for_user(self, user_id: str) -> tuple[PlatformAdminGrant, ...]:
        """Return all grants for the canonical USER, ordered deterministically."""


class PlatformAdminBootstrapPort(Protocol):
    """Offline-only provisioning capability; never expose in request composition.

    Its implementation must be wired exclusively into an operator-controlled
    offline bootstrap command. Runtime application services must receive only
    PlatformAdminAuthorityReaderPort, never this provisioning capability.
    """

    def provision_first_admin(self, grant: PlatformAdminGrant) -> None:
        """Create the initial authority only when no platform admin exists."""
