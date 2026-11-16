"Modelos de resultado para capacidades de workspace."""

from dataclasses import dataclass
from enum import Enum

from atlas.core.errors import ContractError


class WorkspaceEntryKind(str, Enum):
    """Tipo de entrada observado sin seguir enlaces simbólicos."""

    FILE = "file"
    DIRECTORY = "directory"
    SYMLINK = "symlink"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class WorkspaceEntry:
    """Entrada inmediata de un workspace, expresada con ruta relativa."""

    name: str
    kind: WorkspaceEntryKind
    size_bytes: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name or self.name in (".", ".."):
            raise ContractError("name debe ser un nombre de entrada válido")
        if "/" in self.name or "\\" in self.name or "\x00" in self.name:
            raise ContractError("name no puede contener separadores ni NUL")
        if not isinstance(self.kind, WorkspaceEntryKind):
            raise ContractError("kind debe ser WorkspaceEntryKind")
        if self.kind is WorkspaceEntryKind.FILE:
            if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int) or self.size_bytes < 0:
                raise ContractError("un archivo requiere size_bytes no negativo")
        elif self.size_bytes is not None:
            raise ContractError("solo los archivos exponen size_bytes")


@dataclass(frozen=True, slots=True)
class WorkspaceListing:
    """Resultado inmutable del listado no recursivo de un workspace."""

    workspace_id: str
    entries: tuple[WorkspaceEntry, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_id, str) or not self.workspace_id.strip():
            raise ContractError("workspace_id debe ser una cadena no vacía")
        if not isinstance(self.entries, tuple) or any(
            not isinstance(entry, WorkspaceEntry) for entry in self.entries
        ):
            raise ContractError("entries debe ser una tupla de WorkspaceEntry")
        names = [entry.name for entry in self.entries]
        if len(names) != len(set(names)):
            raise ContractError("entries no puede contener nombres duplicados")


@dataclass(frozen=True, slots=True)
class WorkspaceFile:
    """Contenido UTF-8 leído desde una ruta relativa del workspace."""

    workspace_id: str
    path: str
    content: str
    size_bytes: int

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_id, str) or not self.workspace_id.strip():
            raise ContractError("workspace_id debe ser una cadena no vacía")
        if not isinstance(self.path, str) or not self.path.strip():
            raise ContractError("path debe ser una cadena no vacía")
        if not isinstance(self.content, str):
            raise ContractError("content debe ser texto UTF-8")
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int) or self.size_bytes < 0:
            raise ContractError("size_bytes debe ser un entero no negativo")
        if len(self.content.encode("utf-8")) != self.size_bytes:
            raise ContractError("size_bytes debe coincidir con el contenido UTF-8")
