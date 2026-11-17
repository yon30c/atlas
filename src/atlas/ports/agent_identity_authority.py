"""Canonical authority port for AGENT principals; it never creates USER accounts."""

from typing import Protocol

from atlas.core.agent_identity import CanonicalAgentIdentity
from atlas.core.identity import IdentityStatus


class AgentIdentityAuthorityPort(Protocol):
    """Creates and resolves canonical Identity(AGENT) aggregates."""

    def create_agent(self) -> CanonicalAgentIdentity:
        """Create one canonical AGENT identity."""

    def get_agent_by_identity_id(
        self, identity_id: str
    ) -> CanonicalAgentIdentity | None:
        """Resolve an AGENT identity; USER and other kinds must return None."""

    def update_agent_status(
        self,
        identity_id: str,
        *,
        expected_revision: int,
        status: IdentityStatus,
    ) -> CanonicalAgentIdentity:
        """Update AGENT status using compare-and-swap."""
