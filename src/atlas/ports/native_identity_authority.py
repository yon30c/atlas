"""Identity Authority port for native issuer and subject bindings."""

from datetime import datetime
from typing import Protocol

from atlas.core.native_identity import (
    NativeIdentityBinding,
    NativeIdentityIssuer,
)
from atlas.core.user_identity import CanonicalUserIdentity


class NativeIdentityAuthorityPort(Protocol):
    """Owns native issuer metadata and immutable Identity(USER) bindings.

    This port never authenticates credentials, issues proofs, or grants CAM
    permissions. Binding creation accepts a canonical USER aggregate rather
    than a caller-selected identity identifier.
    """

    def get_native_issuer(self, realm: str) -> NativeIdentityIssuer | None:
        """Resolve the issuer registered for one stable logical realm."""

    def create_native_issuer(self, realm: str) -> NativeIdentityIssuer:
        """Create the unique native issuer for a realm; never replace an existing issuer."""

    def get_native_binding(
        self,
        issuer_id: str,
        subject_digest: str,
    ) -> NativeIdentityBinding | None:
        """Resolve active or revoked binding, retaining tombstone visibility."""

    def get_native_binding_by_id(
        self, binding_id: str
    ) -> NativeIdentityBinding | None:
        """Resolve a binding by its immutable canonical identifier."""

    def create_native_binding(
        self,
        identity: CanonicalUserIdentity,
        issuer_id: str,
        subject_digest: str,
        *,
        verified_at: datetime,
    ) -> NativeIdentityBinding:
        """Bind an existing canonical USER identity to a previously registered issuer."""

    def revoke_native_binding(
        self,
        binding_id: str,
        *,
        expected_revision: int,
        revoked_at: datetime,
    ) -> NativeIdentityBinding:
        """Revoke with CAS; a revoked binding is terminal and never reassigned."""
