"""Port for explicit active local consistency signing-key selection."""
from typing import Protocol

from atlas.memory.local_keys import ActiveLocalConsistencyKey


class ActiveLocalConsistencyKeyProvider(Protocol):
    """Resolve the one active key selected by trusted composition configuration."""

    def load_active_key(self) -> ActiveLocalConsistencyKey | None:
        """Return the configured active key, or None when unavailable."""
