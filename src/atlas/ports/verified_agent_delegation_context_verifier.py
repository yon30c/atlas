"""Port for revalidating owner-consent evidence for one AGENT delegation."""

from typing import Protocol

from atlas.core.agent_delegation import VerifiedAgentDelegationContext


class VerifiedAgentDelegationContextVerifierPort(Protocol):
    """Revalidates delegation evidence against current authority state."""

    def verify(
        self, context: VerifiedAgentDelegationContext
    ) -> VerifiedAgentDelegationContext:
        """Return current verified claims or fail closed; never grants CAM access."""
