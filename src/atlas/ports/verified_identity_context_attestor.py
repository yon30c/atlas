"""Cryptographic attestation port for ephemeral verified identity contexts."""

from typing import Protocol


class VerifiedIdentityContextAttestorPort(Protocol):
    """Attests canonical context claims using a trusted composition secret."""

    def sign(self, payload: bytes) -> str:
        """Return a base64url HMAC-SHA256 tag."""

    def verify(self, payload: bytes, attestation: str) -> bool:
        """Verify a tag in constant time; fail closed on malformed input."""
