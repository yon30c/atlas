"""Authority port for owner-issued AGENT delegation records."""

from datetime import datetime
from typing import Protocol

from atlas.core.agent_delegation import (
    AgentDelegation,
    AgentDelegationScope,
    VerifiedAgentDelegationContext,
)
from atlas.core.verified_identity_context import VerifiedIdentityContext
from atlas.core.verified_agent_identity_context import VerifiedAgentIdentityContext


class AgentDelegationAuthorityPort(Protocol):
    """Owns delegation lifecycle; this authority is not a CAM decision engine."""

    def create_for_grant(
        self,
        *,
        grant_id: str,
        agent_identity_id: str,
        scope: AgentDelegationScope,
        not_before: datetime,
        expires_at: datetime,
        verified_owner_identity: VerifiedIdentityContext,
    ) -> AgentDelegation:
        """Create only after revalidating owner evidence and the current Grant."""

    def get_delegation(self, delegation_id: str) -> AgentDelegation | None:
        """Resolve canonical record, including revoked tombstones."""

    def revoke_delegation(
        self,
        delegation_id: str,
        *,
        expected_revision: int,
        verified_owner_identity: VerifiedIdentityContext,
    ) -> AgentDelegation:
        """Owner-only terminal revocation guarded by compare-and-swap.

        Implementations must load the canonical current row, apply
        validate_agent_delegation_transition(current, updated), derive the
        revocation timestamp from a trusted clock, and persist within one
        transaction/fencing boundary. A revoked row is terminal; callers
        cannot reactivate it by submitting a replacement snapshot.
        """

    def verify_for_operation(
        self,
        delegation_id: str,
        *,
        expected_revision: int,
        verified_agent_identity: VerifiedAgentIdentityContext,
    ) -> VerifiedAgentDelegationContext:
        """Revalidate the requesting AGENT and live delegation/Grant bindings.

        The AGENT context must resolve to the delegation's exact agent_identity_id;
        possession of delegation_id alone is never sufficient. Trusted clock,
        realm, audience, attestor and context TTL are composition-root
        dependencies, never caller-supplied values. Implementations must reject
        revoked delegations and stale Grant or delegation revisions on every
        operation; this is not a CAM decision.
        """
