"""Puerto de autoridad para identidades canónicas de usuario."""
from typing import Protocol

from atlas.core.identity import IdentityStatus
from atlas.core.user_identity import CanonicalUserIdentity


class IdentityAuthorityPort(Protocol):
    """Crea y administra la relación canónica UserId <-> Identity(USER)."""

    def create_user(self) -> CanonicalUserIdentity:
        """Create one user and its USER identity atomically."""

    def get_user(self, user_id: str) -> CanonicalUserIdentity | None:
        """Resolve a canonical UserId, returning None when it does not exist."""

    def get_user_by_identity_id(
        self, identity_id: str
    ) -> CanonicalUserIdentity | None:
        """Resolve the canonical UserId/Identity(USER) pair by identity UUID."""

    def update_user_status(
        self,
        user_id: str,
        *,
        expected_revision: int,
        status: IdentityStatus,
    ) -> CanonicalUserIdentity:
        """Update status using compare-and-swap against the identity revision."""
