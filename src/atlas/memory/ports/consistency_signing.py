"""Signing port for authenticated Memory Engine consistency evidence.

The journal adapter never receives raw key material. A composition-root
signer owns active-key selection and custody; verification is a separate port.
"""
from typing import Any, Protocol

from atlas.memory.envelope import AuthenticatedConsistencyEnvelope


class MemoryConsistencySignerPort(Protocol):
    """Authenticate one exact envelope/object pair using an active trusted key."""

    def sign_envelope(
        self,
        envelope: AuthenticatedConsistencyEnvelope,
        object_value: Any,
    ) -> AuthenticatedConsistencyEnvelope:
        """Return the authenticated envelope or raise when signing is unavailable."""
