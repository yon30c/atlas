"""argon2-cffi adapter configured explicitly for Argon2id."""

from argon2 import PasswordHasher, Type
from argon2.exceptions import (
    HashingError,
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

from atlas.authentication.credentials import (
    validate_new_password,
    validate_password_for_verification,
)
from atlas.authentication.password_hashing import Argon2idParameters
from atlas.core.errors import ContractError


class Argon2idPasswordHasher:
    """Argon2id adapter; no production parameters are selected implicitly."""

    def __init__(self, parameters: Argon2idParameters) -> None:
        if not isinstance(parameters, Argon2idParameters):
            raise ContractError("parameters debe ser Argon2idParameters")
        self._parameters = parameters
        self._hasher = PasswordHasher(
            time_cost=parameters.time_cost,
            memory_cost=parameters.memory_cost_kib,
            parallelism=parameters.parallelism,
            hash_len=parameters.hash_len,
            salt_len=parameters.salt_len,
            type=Type.ID,
        )

    @property
    def parameters(self) -> Argon2idParameters:
        return self._parameters

    def hash_password(self, password: str) -> str:
        validate_new_password(password)
        try:
            return self._hasher.hash(password)
        except (HashingError, TypeError, ValueError) as exc:
            raise ContractError("no se pudo generar el verificador Argon2id") from exc

    def verify_password(self, encoded_hash: str, password: str) -> bool:
        validate_password_for_verification(password)
        if not isinstance(encoded_hash, str) or not encoded_hash:
            raise ContractError("encoded_hash debe ser una cadena PHC no vacía")
        try:
            return bool(self._hasher.verify(encoded_hash, password))
        except VerifyMismatchError:
            return False
        except (VerificationError, InvalidHashError, TypeError, ValueError):
            return False

    def needs_rehash(self, encoded_hash: str) -> bool:
        if not isinstance(encoded_hash, str) or not encoded_hash:
            raise ContractError("encoded_hash debe ser una cadena PHC no vacía")
        try:
            return self._hasher.check_needs_rehash(encoded_hash)
        except (VerificationError, InvalidHashError, TypeError, ValueError) as exc:
            raise ContractError("encoded_hash no es un PHC Argon2 válido") from exc
