"""Composed single authority for protected reads and recovery gate operations."""
from typing import Protocol

from atlas.ports.protected_memory_read import ProtectedMemoryConsistencyPort
from atlas.ports.recovery_gate import RecoveryGatePort


class ProtectedMemoryRecoveryAuthorityPort(
    ProtectedMemoryConsistencyPort, RecoveryGatePort, Protocol
):
    """Single implementation boundary for runtime reads and crash recovery.

    The composition root must inject the same authority instance into the
    MemoryGateway and recovery coordinators. Separate implementations for
    these inherited facets do not satisfy the contract: admission/egress and
    recovery closure/reopening must share one serializable state and order.
    """
