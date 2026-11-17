"""Port and configuration value object for password hashing."""

from dataclasses import dataclass
from typing import Protocol

from atlas.core.errors import ContractError


@dataclass(frozen=True, slots=True)
class Argon2idParameters:
    """Explicit Argon2id parameters; production values require target-hardware calibration."""

    time_cost: int
    memory_cost_kib: int
    parallelism: int
    hash_len: int
    salt_len: int

    def __post_init__(self) -> None:
        for name in ("time_cost", "memory_cost_kib", "parallelism", "hash_len", "salt_len"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ContractError(f"{name} debe ser un entero positivo")
        if self.memory_cost_kib < 8 * self.parallelism:
            raise ContractError("memory_cost_kib debe ser al menos 8 * parallelism")
        if self.hash_len < 16:
            raise ContractError("hash_len debe ser al menos 16 bytes")
        if self.salt_len < 16:
            raise ContractError("salt_len debe ser al menos 16 bytes")


class PasswordHasherPort(Protocol):
    """Authentication-owned password hashing boundary."""

    def hash_password(self, password: str) -> str:
        """Hash a new password using the configured password hashing policy."""

    def verify_password(self, encoded_hash: str, password: str) -> bool:
        """Verify a supplied password; malformed hashes fail closed."""

    def needs_rehash(self, encoded_hash: str) -> bool:
        """Return whether the encoded hash no longer matches configured parameters."""
