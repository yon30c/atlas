"""Port for revalidating short-lived AGENT identity evidence."""

from typing import Protocol

from atlas.core.agent_identity import CanonicalAgentIdentity
from atlas.core.verified_agent_identity_context import VerifiedAgentIdentityContext


class VerifiedAgentIdentityContextVerifierPort(Protocol):
    """Revalidates AGENT evidence against its canonical identity authority."""

    def verify(
        self, context: VerifiedAgentIdentityContext
    ) -> CanonicalAgentIdentity:
        """Return the current canonical AGENT aggregate or fail closed."""
