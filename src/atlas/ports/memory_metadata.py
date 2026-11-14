"""Compatibilidad: los puertos canónicos viven en atlas.memory.ports.metadata."""

from atlas.memory.ports.metadata import (
    EnvironmentMetadataPort,
    MemoryMetadataPort,
    ProjectMetadataPort,
)

__all__ = [
    "EnvironmentMetadataPort",
    "MemoryMetadataPort",
    "ProjectMetadataPort",
]
