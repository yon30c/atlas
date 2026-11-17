"""Value objects and validation rules for native login credentials."""

from dataclasses import dataclass
import re

from atlas.core.errors import ContractError


_LOGIN_HANDLE = re.compile(r"[a-z0-9][a-z0-9._-]{2,63}", re.ASCII)
MIN_PASSWORD_CODEPOINTS = 12
MAX_PASSWORD_UTF8_BYTES = 1024


@dataclass(frozen=True, slots=True)
class LoginHandle:
    """Canonical, realm-scoped lookup handle; never an identity or subject."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise ContractError("login_handle debe ser una cadena")
        try:
            self.value.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ContractError("login_handle solo admite ASCII") from exc

        normalized = self.value.lower()
        if _LOGIN_HANDLE.fullmatch(normalized) is None:
            raise ContractError("login_handle debe cumplir el formato ASCII de 3 a 64 caracteres")
        object.__setattr__(self, "value", normalized)


def validate_new_password(password: str) -> bytes:
    """Validate a new password and return its UTF-8 bytes for boundary checks.

    The returned bytes are transient and must never be persisted or logged.
    Callers should discard them immediately after validation.
    """
    encoded = _validate_password_input(password)
    if len(password) < MIN_PASSWORD_CODEPOINTS:
        raise ContractError("password debe contener al menos 12 puntos de código")
    return encoded


def validate_password_for_verification(password: str) -> None:
    """Validate a supplied login password without applying new-password minimums."""
    _validate_password_input(password)


def _validate_password_input(password: str) -> bytes:
    if not isinstance(password, str):
        raise ContractError("password debe ser una cadena")
    if "\x00" in password:
        raise ContractError("password no puede contener NUL")
    try:
        encoded = password.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ContractError("password contiene Unicode no codificable en UTF-8") from exc
    if len(encoded) > MAX_PASSWORD_UTF8_BYTES:
        raise ContractError("password excede el máximo de 1024 bytes UTF-8")
    return encoded
