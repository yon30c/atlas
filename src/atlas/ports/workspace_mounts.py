"""Ports for trusted workspace mount resolution."""

from pathlib import Path
from typing import Protocol


class WorkspaceMountResolver(Protocol):
    """Resolves a canonical symbolic root_ref through trusted configuration."""

    def resolve(self, root_ref: str) -> Path:
        """Return an existing canonical directory for a registered mount ref."""
