"""Adaptador local de lectura para workspaces explícitamente configurados."""

import os
from pathlib import Path
import stat
from typing import Mapping

from atlas.assistant.workspace import (
    WorkspaceEntry,
    WorkspaceEntryKind,
    WorkspaceListing,
)
from atlas.core.errors import AtlasError, ContractError, NotFoundError


class LocalWorkspaceAdapter:
    """Lista entradas inmediatas dentro de raíces locales de confianza."""

    def __init__(self, workspaces: Mapping[str, str | Path]) -> None:
        if not isinstance(workspaces, Mapping) or not workspaces:
            raise ContractError("workspaces debe ser un mapa no vacío")

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

    def list_entries(self, workspace_id: str) -> WorkspaceListing:
        """Devuelve nombres, tipos y tamaños sin recorrer subdirectorios."""
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            raise ContractError("workspace_id debe ser una cadena no vacía")
        root = self._workspaces.get(workspace_id)
        if root is None:
            raise NotFoundError("workspace no configurado")

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
                        WorkspaceEntry(
                            name=item.name,
                            kind=kind,
                            size_bytes=size_bytes,
                        )
                    )
        except OSError as exc:
            raise AtlasError("no se pudo listar el workspace configurado") from exc

        entries.sort(key=lambda entry: (entry.name.casefold(), entry.name))
        return WorkspaceListing(workspace_id, tuple(entries))
