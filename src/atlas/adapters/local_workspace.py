"""Adaptador local de lectura para workspaces explícitamente configurados."""

import os
from pathlib import Path
import stat
from typing import Mapping

from atlas.assistant.workspace import (
    WorkspaceEntry,
    WorkspaceEntryKind,
    WorkspaceFile,
    WorkspaceListing,
)
from atlas.core.errors import AtlasError, ContractError, NotFoundError


DEFAULT_MAX_FILE_BYTES = 1024 * 1024


class LocalWorkspaceAdapter:
    """Lee entradas y archivos dentro de raíces locales explícitamente confiables."""

    def __init__(
        self,
        workspaces: Mapping[str, str | Path],
        *,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    ) -> None:
        if not isinstance(workspaces, Mapping) or not workspaces:
            raise ContractError("workspaces debe ser un mapa no vacío")
        if isinstance(max_file_bytes, bool) or not isinstance(max_file_bytes, int) or max_file_bytes <= 0:
            raise ContractError("max_file_bytes debe ser un entero positivo")

        configured: dict[str, Path] = {}
        for workspace_id, root_value in workspaces.items():
            if (
                not isinstance(workspace_id, str)
                or not workspace_id.strip()
                or workspace_id.strip() != workspace_id
            ):
                raise ContractError("workspace_id debe ser una cadena no vacía y normalizada")
            try:
                root = Path(root_value)
            except (TypeError, ValueError) as exc:
                raise ContractError("la raíz del workspace debe ser una ruta válida") from exc
            if not root.is_absolute():
                raise ContractError("la raíz del workspace debe ser absoluta")
            try:
                resolved = root.resolve(strict=True)
                metadata = root.lstat()
            except OSError as exc:
                raise ContractError("la raíz del workspace debe existir") from exc
            if (
                resolved != root
                or not stat.S_ISDIR(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
            ):
                raise ContractError(
                    "la raíz del workspace debe ser un directorio real y canónico"
                )
            configured[workspace_id] = root

        self._workspaces = configured
        self._max_file_bytes = max_file_bytes

    def _workspace_root(self, workspace_id: str) -> Path:
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            raise ContractError("workspace_id debe ser una cadena no vacía")
        root = self._workspaces.get(workspace_id)
        if root is None:
            raise NotFoundError("workspace no configurado")
        return root

    def list_entries(self, workspace_id: str) -> WorkspaceListing:
        """Devuelve nombres, tipos y tamaños sin recorrer subdirectorios."""
        root = self._workspace_root(workspace_id)
        entries: list[WorkspaceEntry] = []
        try:
            with os.scandir(root) as iterator:
                for item in iterator:
                    metadata = item.stat(follow_symlinks=False)
                    mode = metadata.st_mode
                    if stat.S_ISLNK(mode):
                        kind = WorkspaceEntryKind.SYMLINK
                        size_bytes = None
                    elif stat.S_ISREG(mode):
                        kind = WorkspaceEntryKind.FILE
                        size_bytes = metadata.st_size
                    elif stat.S_ISDIR(mode):
                        kind = WorkspaceEntryKind.DIRECTORY
                        size_bytes = None
                    else:
                        kind = WorkspaceEntryKind.OTHER
                        size_bytes = None
                    entries.append(
                        WorkspaceEntry(name=item.name, kind=kind, size_bytes=size_bytes)
                    )
        except OSError as exc:
            raise AtlasError("no se pudo listar el workspace configurado") from exc

        entries.sort(key=lambda entry: (entry.name.casefold(), entry.name))
        return WorkspaceListing(workspace_id, tuple(entries))

    def read_file(self, workspace_id: str, path: str) -> WorkspaceFile:
        """Lee un archivo UTF-8 regular, sin aceptar rutas absolutas ni symlinks."""
        root = self._workspace_root(workspace_id)
        if (
            not isinstance(path, str)
            or not path
            or path.strip() != path
            or "\x00" in path
            or "\\" in path
            or path.startswith("/")
            or (len(path) >= 2 and path[1] == ":")
        ):
            raise ContractError("path debe ser una ruta relativa POSIX normalizada")
        parts = path.split("/")
        if any(part in ("", ".", "..") for part in parts):
            raise ContractError("path contiene componentes no permitidos")

        candidate = root
        try:
            for index, part in enumerate(parts):
                candidate = candidate / part
                metadata = candidate.lstat()
                if stat.S_ISLNK(metadata.st_mode):
                    raise ContractError("no se permite seguir enlaces simbólicos")
                if index < len(parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
                    raise NotFoundError("la ruta intermedia no es un directorio")
                if index == len(parts) - 1 and not stat.S_ISREG(metadata.st_mode):
                    raise ContractError("la ruta debe identificar un archivo regular")
            resolved = candidate.resolve(strict=True)
            if not resolved.is_relative_to(root):
                raise ContractError("la ruta sale del workspace configurado")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(candidate, flags)
            try:
                metadata = os.fstat(descriptor)
                if not stat.S_ISREG(metadata.st_mode):
                    raise ContractError("la ruta debe identificar un archivo regular")
                if metadata.st_size > self._max_file_bytes:
                    raise ContractError("el archivo supera el límite de lectura")
                with os.fdopen(descriptor, "rb", closefd=False) as stream:
                    raw = stream.read(self._max_file_bytes + 1)
                if len(raw) > self._max_file_bytes:
                    raise ContractError("el archivo supera el límite de lectura")
            finally:
                os.close(descriptor)
        except FileNotFoundError as exc:
            raise NotFoundError("archivo no encontrado en el workspace") from exc
        except PermissionError as exc:
            raise AtlasError("no se pudo leer el archivo del workspace") from exc
        except OSError as exc:
            raise AtlasError("falló la lectura del archivo del workspace") from exc

        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ContractError("solo se admiten archivos de texto UTF-8") from exc
        return WorkspaceFile(
            workspace_id=workspace_id,
            path=path,
            content=content,
            size_bytes=len(raw),
        )
