"""Puertos de lectura para workspaces configurados."""

from typing import Protocol

from atlas.assistant.workspace import WorkspaceFile, WorkspaceListing


class WorkspaceReader(Protocol):
    """Permite listar entradas inmediatas de un workspace configurado."""

    def list_entries(self, workspace_id: str) -> WorkspaceListing:
        """Lista únicamente las entradas inmediatas del workspace indicado."""


class WorkspaceFileReader(Protocol):
    """Permite leer archivos UTF-8 mediante rutas relativas confinadas."""

    def read_file(self, workspace_id: str, path: str) -> WorkspaceFile:
        """Lee un archivo regular sin seguir enlaces simbólicos."""
