"""Custody port for keys used by Memory Engine consistency evidence.

The core receives only opaque key references. Implementations keep raw key
material outside journals and ordinary backups and fail closed when unavailable.
"""
from typing import Protocol


class MemoryConsistencyKeyPort(Protocol):
    """Resolve one historical 256-bit key by its opaque reference."""

    def load_key(self, key_reference: str) -> bytes | None:
        """Return exactly 32 key bytes, or None when the key is unavailable."""
