"""HMAC attestor backed by one dedicated systemd credential.

This adapter loads an Identity-only key at composition time. It deliberately
does not share or infer the Local Consistency key reference.
"""
import os
import re
import stat
from pathlib import Path

from atlas.adapters.hmac_verified_identity_context_attestor import (
    HmacVerifiedIdentityContextAttestor,
)
from atlas.core.errors import ContractError
from atlas.ports.verified_identity_context_attestor import (
    VerifiedIdentityContextAttestorPort,
)


_CREDENTIAL_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
_IDENTITY_KEY_BYTES = 32


class SystemdCredentialVerifiedIdentityContextAttestor(
    VerifiedIdentityContextAttestorPort
):
    """Load a dedicated 256-bit Identity HMAC key from systemd credentials.

    The credential is read once when the trusted composition is built. Missing,
    malformed, linked, or non-regular credentials abort composition; there is
    no environment, file, or Local Consistency key fallback. Rotation requires
    an explicit credential/configuration update and process restart.
    """

    def __init__(
        self,
        credentials_directory: str | Path,
        credential_name: str,
    ) -> None:
        if not isinstance(credential_name, str) or not _CREDENTIAL_NAME.fullmatch(
            credential_name
        ) or credential_name in (".", ".."):
            raise ContractError("credential_name debe ser un nombre simple permitido")

        try:
            directory = Path(credentials_directory)
        except (TypeError, ValueError) as exc:
            raise ContractError("credentials_directory inválido") from exc
        if not directory.is_absolute():
            raise ContractError("credentials_directory debe ser absoluto")

        self._attestor = HmacVerifiedIdentityContextAttestor(
            self._read_identity_key(directory, credential_name)
        )

    @staticmethod
    def _read_identity_key(directory: Path, credential_name: str) -> bytes:
        directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        directory_flags |= getattr(os, "O_DIRECTORY", 0)
        directory_flags |= getattr(os, "O_NOFOLLOW", 0)
        credential_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        credential_flags |= getattr(os, "O_NOFOLLOW", 0)
        credential_flags |= getattr(os, "O_NONBLOCK", 0)

        directory_fd = -1
        credential_fd = -1
        try:
            directory_fd = os.open(directory, directory_flags)
            credential_fd = os.open(
                credential_name,
                credential_flags,
                dir_fd=directory_fd,
            )
            metadata = os.fstat(credential_fd)
            if not stat.S_ISREG(metadata.st_mode):
                raise ContractError("la credencial Identity no es un archivo regular")
            with os.fdopen(credential_fd, "rb", closefd=True) as stream:
                credential_fd = -1
                key = stream.read(_IDENTITY_KEY_BYTES + 1)
            if len(key) != _IDENTITY_KEY_BYTES:
                raise ContractError("la credencial Identity debe contener exactamente 32 bytes")
            return key
        except OSError as exc:
            raise ContractError("la credencial HMAC de Identity no está disponible") from exc
        finally:
            if credential_fd >= 0:
                os.close(credential_fd)
            if directory_fd >= 0:
                os.close(directory_fd)

    def sign(self, payload: bytes) -> str:
        return self._attestor.sign(payload)

    def verify(self, payload: bytes, attestation: str) -> bool:
        return self._attestor.verify(payload, attestation)
