"""Compatibility export for the Memory Engine consistency key port."""
from atlas.memory.ports.consistency_keys import MemoryConsistencyKeyPort

LocalConsistencyKeyPort = MemoryConsistencyKeyPort

__all__ = ["LocalConsistencyKeyPort", "MemoryConsistencyKeyPort"]
