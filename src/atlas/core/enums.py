"""Enumeraciones compartidas por los modelos del dominio."""
from enum import Enum


class MemoryStatus(str, Enum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    ARCHIVED = "archived"
    REJECTED = "rejected"

class DelegationMode(str, Enum):
    DELEGATED = "delegated"
    INDEPENDENT = "independent"