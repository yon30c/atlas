"""Puerto de lectura para workspaces configurados."""

from typing import Protocol

from atlas.assistant.workspace import WorkspaceListing


class WorkspaceReader(Protocol):
    """Permite listar entradas dentro de un workspace previamente configurado."""

    def list_entries(self, workspace_id: str) -> WorkspaceListing:
        """Lista únicamente las entradas inmediatas del workspace indicado."""
