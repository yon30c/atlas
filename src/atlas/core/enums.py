"""Enumeraciones compartidas por los modelos del dominio."""
from enum import Enum


class DelegationMode(str, Enum):
    DELEGATED = "delegated"
    INDEPENDENT = "independent"
