"""Ports for read-only runtime and isolated offline Platform Admin bootstrap."""

from typing import Protocol

from atlas.core.platform_admin import (
    PlatformAdminBootstrapCommand,
    PlatformAdminGrant,
)


class PlatformAdminAuthorityReaderPort(Protocol):
    """Resolve administrator grants; this port cannot issue or mutate authority."""

    def get_grant(self, grant_id: str) -> PlatformAdminGrant | None:
        """Return the exact canonical grant, including revoked tombstones."""

    def list_grants_for_user(self, user_id: str) -> tuple[PlatformAdminGrant, ...]:
        """Return all grants for the canonical USER, ordered deterministically."""


class PlatformAdminBootstrapPort(Protocol):
    """Offline-only provisioning capability; never expose in request composition.

    Implementations must receive a validated command carrying the original
    request, immutable local provenance and the exact grant to persist. The
    adapter must still enforce operation-id idempotency and first-admin
    exclusivity transactionally; this domain object is not a substitute for
    canonical Identity Authority checks inside that transaction.
    """

    def provision_first_admin(
        self,
        command: PlatformAdminBootstrapCommand,
    ) -> PlatformAdminGrant:
        """Persist the first grant and its provenance atomically.

        An exact replay of the same operation returns the persisted grant.
        A conflicting replay or any prior bootstrap operation is rejected.
        """
