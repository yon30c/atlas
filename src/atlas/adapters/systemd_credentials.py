"""Read local consistency keys from systemd's private credential directory.

The directory and key-reference mapping are supplied by trusted composition
configuration. This module never provisions, decrypts, generates, or rotates
credentials; systemd handles encrypted-credential delivery.
"""
from collections.abc import Mapping
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType

from atlas.core.errors import ContractError
from atlas.memory.local_keys import ActiveLocalConsistencyKey
from atlas.ports.active_local_consistency_keys import ActiveLocalConsistencyKeyProvider
from atlas.ports.local_consistency_keys import LocalConsistencyKeyPort


_CREDENTIAL_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
_KEY_LENGTH_BYTES = 32


class SystemdCredentialKeyProvider(LocalConsistencyKeyPort):
    """Resolve historical key references to files delivered by systemd."""

    def __init__(
        self,
        credentials_directory: str | Path,
        credential_names: Mapping[str, str],
    ) -> None:
        try:
            directory = Path(credentials_directory).expanduser()
        except (TypeError, ValueError) as exc:
            raise ContractError("credentials_directory inválido") from exc
        if not directory.is_absolute() or not directory.exists() or not directory.is_dir():
            raise ContractError("credentials_directory debe ser un directorio absoluto existente")
        if not isinstance(credential_names, Mapping) or not credential_names:
            raise ContractError("credential_names debe ser un mapa no vacío")

        normalized: dict[str, str] = {}
        for reference, name in credential_names.items():
            if not isinstance(reference, str) or not reference.strip():
                raise ContractError("key_reference debe ser no vacío")
            if (
                not isinstance(name, str)
                or not _CREDENTIAL_NAME.fullmatch(name)
                or name in (".", "..")
            ):
                raise ContractError("credential_name no es un nombre de archivo permitido")
            if name in normalized.values():
                raise ContractError("credential_name duplicado")
            normalized[reference] = name

        self._directory = directory
        self._credential_names = MappingProxyType(normalized)

    def load_key(self, key_reference: str) -> bytes | None:
        """Return exactly 32 bytes; all missing or malformed credentials are unavailable."""
        if not isinstance(key_reference, str) or not key_reference.strip():
            return None
        credential_name = self._credential_names.get(key_reference)
        if credential_name is None:
            return None

        path = self._directory / credential_name
        flags = os.O_RDONLY
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
            try:
                metadata = os.fstat(descriptor)
                if not stat.S_ISREG(metadata.st_mode):
                    return None
                with os.fdopen(descriptor, "rb", closefd=True) as stream:
                    descriptor = -1
                    key = stream.read(_KEY_LENGTH_BYTES + 1)
                if len(key) != _KEY_LENGTH_BYTES:
                    return None
                return key
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
        except OSError:
            return None


class ConfiguredActiveLocalConsistencyKeyProvider(ActiveLocalConsistencyKeyProvider):
    """Select one active reference explicitly; never infer it from persisted data."""

    def __init__(
        self,
        key_provider: LocalConsistencyKeyPort,
        active_key_reference: str,
    ) -> None:
        if key_provider is None or not callable(getattr(key_provider, "load_key", None)):
            raise ContractError("key_provider debe implementar load_key")
        if not isinstance(active_key_reference, str) or not active_key_reference.strip():
            raise ContractError("active_key_reference debe ser no vacío")
        self._key_provider = key_provider
        self._active_key_reference = active_key_reference

    def load_active_key(self) -> ActiveLocalConsistencyKey | None:
        key = self._key_provider.load_key(self._active_key_reference)
        if not isinstance(key, bytes) or len(key) != _KEY_LENGTH_BYTES:
            return None
        return ActiveLocalConsistencyKey(self._active_key_reference, key)
