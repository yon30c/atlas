"""Caso de uso para leer archivos de un workspace configurado."""

from atlas.assistant.workspace import WorkspaceFile
from atlas.core.errors import ContractError
from atlas.ports.workspace import WorkspaceFileReader


class WorkspaceFileReadingService:
    """Coordina la lectura sin conocer rutas físicas ni detalles del sistema."""

    def __init__(self, reader: WorkspaceFileReader) -> None:
        if not callable(getattr(reader, "read_file", None)):
            raise ContractError("reader debe implementar read_file(workspace_id, path)")
        self._reader = reader

    def read(self, workspace_id: str, path: str) -> WorkspaceFile:
        """Lee un archivo relativo y comprueba el binding del resultado."""
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            raise ContractError("workspace_id debe ser una cadena no vacía")
        if not isinstance(path, str) or not path.strip():
            raise ContractError("path debe ser una cadena no vacía")
        result = self._reader.read_file(workspace_id, path)
        if not isinstance(result, WorkspaceFile):
            raise ContractError("reader debe devolver WorkspaceFile")
        if result.workspace_id != workspace_id or result.path != path:
            raise ContractError("el resultado no corresponde al recurso solicitado")
        return result
