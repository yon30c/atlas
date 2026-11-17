"""Preparación segura del almacenamiento local de conversaciones."""

import os
import stat
from pathlib import Path

from atlas.core.errors import ContractError


def prepare_conversation_database_path(path: str | Path | None = None) -> Path:
    """Crea el directorio privado y un archivo SQLite regular, sin seguir symlinks.

    Solo modifica los permisos del directorio dedicado de Atlas y del archivo
    SQLite; no cambia permisos de ~/.local ni ~/.local/state.
    """
    target = (
        Path.home() / ".local" / "state" / "atlas" / "conversations.sqlite3"
        if path is None
        else Path(path).expanduser()
    )
    if not target.is_absolute():
        raise ContractError("la ruta de conversaciones debe ser absoluta")

    directory = target.parent
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory_info = directory.lstat()
        if not stat.S_ISDIR(directory_info.st_mode):
            raise ContractError("el directorio de conversaciones no puede ser symlink")
        if hasattr(os, "getuid") and directory_info.st_uid != os.getuid():
            raise ContractError("el directorio de conversaciones pertenece a otro usuario")

        directory_fd = os.open(
            directory,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fchmod(directory_fd, 0o700)
        finally:
            os.close(directory_fd)

        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        file_fd = os.open(target, flags, 0o600)
        try:
            file_info = os.fstat(file_fd)
            if not stat.S_ISREG(file_info.st_mode):
                raise ContractError("la base de conversaciones debe ser un archivo regular")
            if hasattr(os, "getuid") and file_info.st_uid != os.getuid():
                raise ContractError("la base de conversaciones pertenece a otro usuario")
            os.fchmod(file_fd, 0o600)
        finally:
            os.close(file_fd)
    except OSError as exc:
        raise ContractError("no se pudo preparar el almacenamiento privado de conversaciones") from exc

    return target
