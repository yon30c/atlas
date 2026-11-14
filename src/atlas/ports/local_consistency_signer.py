"""Compatibility export for the Memory Engine consistency signing port."""
from atlas.memory.ports.consistency_signing import MemoryConsistencySignerPort

LocalConsistencySignerPort = MemoryConsistencySignerPort

__all__ = ["LocalConsistencySignerPort", "MemoryConsistencySignerPort"]
