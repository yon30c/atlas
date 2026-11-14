"""Typed local consistency key material; never persist or log this object."""
from dataclasses import dataclass, field

from atlas.core.errors import ContractError


@dataclass(frozen=True, slots=True)
class ActiveLocalConsistencyKey:
    """One explicitly selected active HMAC key.

    The key bytes are deliberately excluded from repr to reduce accidental
    disclosure in diagnostics. Callers must never serialize this object.
    """

    key_reference: str
    key: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.key_reference, str) or not self.key_reference.strip():
            raise ContractError("key_reference debe ser una cadena no vacía")
        if not isinstance(self.key, bytes) or len(self.key) != 32:
            raise ContractError("la clave HMAC local debe contener exactamente 32 bytes")
