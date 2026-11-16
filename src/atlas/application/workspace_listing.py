"""Caso de uso para listar un workspace previamente configurado."""

from atlas.assistant.workspace import WorkspaceListing
from atlas.core.errors import ContractError
from atlas.ports.workspace import WorkspaceReader


class WorkspaceListingService:
    """Coordina el listado sin conocer rutas ni detalles del sistema de archivos."""

    def __init__(self, reader: WorkspaceReader) -> None:
        if not callable(getattr(reader, "list_entries", None)):
            raise ContractError("reader debe implementar list_entries(workspace_id)")
        self._reader = reader

    def list(self, workspace_id: str) -> WorkspaceListing:
        """Solicita el listado del workspace registrado y valida el resultado."""
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            raise ContractError("workspace_id debe ser una cadena no vacía")

        result = self._reader.list_entries(workspace_id)
        if not isinstance(result, WorkspaceListing):
            raise ContractError("reader debe devolver WorkspaceListing")
        if result.workspace_id != workspace_id:
            raise ContractError("el resultado pertenece a otro workspace")
        return result
