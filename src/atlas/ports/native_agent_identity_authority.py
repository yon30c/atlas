"""Authority port for issuer bindings to canonical AGENT identities."""

from datetime import datetime
from typing import Protocol

from atlas.core.agent_identity import CanonicalAgentIdentity
from atlas.core.native_agent_identity import NativeAgentIdentityBinding


class NativeAgentIdentityAuthorityPort(Protocol):
    """Owns AGENT subject bindings without broadening USER binding contracts."""

    def get_native_agent_binding(
        self, issuer_id: str, subject_digest: str
    ) -> NativeAgentIdentityBinding | None:
        """Resolve active or revoked binding, retaining tombstone visibility."""

    def get_native_agent_binding_by_id(
        self, binding_id: str
    ) -> NativeAgentIdentityBinding | None:
        """Resolve an AGENT binding by immutable identifier."""

    def create_native_agent_binding(
        self,
        identity: CanonicalAgentIdentity,
        issuer_id: str,
        subject_digest: str,
        *,
        verified_at: datetime,
    ) -> NativeAgentIdentityBinding:
        """Bind an existing canonical AGENT to a previously registered issuer ID."""

    def revoke_native_agent_binding(
        self,
        binding_id: str,
        *,
        expected_revision: int,
        revoked_at: datetime,
    ) -> NativeAgentIdentityBinding:
        """Revoke with CAS; revocation is terminal."""
