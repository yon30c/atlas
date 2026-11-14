"""Key-custody port for local consistency HMAC verification."""
from typing import Protocol


class LocalConsistencyKeyPort(Protocol):
    """Resolve a historical 256-bit key by opaque reference.

    Implementations keep keys outside the journal and ordinary backups, enforce
    access control, and retain historical keys while evidence remains verifiable.
    None means unavailable; callers must fail closed.
    """

    def load_key(self, key_reference: str) -> bytes | None:
        """Return exactly 32 key bytes or None when unavailable."""
