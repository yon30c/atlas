"""Port for revalidating owner-consent evidence for one AGENT delegation."""

from typing import Protocol

from atlas.core.agent_delegation import AgentDelegation, VerifiedAgentDelegationContext


class VerifiedAgentDelegationContextVerifierPort(Protocol):
    """Revalidates delegation evidence against current authority state."""

    def verify(
        self, context: VerifiedAgentDelegationContext
    ) -> AgentDelegation:
        """Return the current canonical delegation or fail closed; never grants CAM access."""

    def verify_in_unit_of_work(
        self, context: VerifiedAgentDelegationContext, unit
    ) -> AgentDelegation:
        """Revalidate in a caller-owned shared transaction; never commits it."""
