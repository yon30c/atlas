"""Enrutamiento fail-closed hacia resolvers de metadatos por tipo."""
from collections.abc import Mapping
from types import MappingProxyType
from typing import Protocol

from atlas.core.errors import ContractError


class ResourceMetadataReader(Protocol):
    """Lee metadatos de un tipo de recurso desde su fuente autoritativa."""

    def get_metadata(self, resource_id: str) -> object | None:
        """Devuelve solo metadatos mínimos; nunca contenido protegido."""


class ResourceMetadataResolver:
    """Enruta consultas por tipo sin fallback ni resolución por tipo genérico."""

    def __init__(
        self,
        readers: Mapping[str, ResourceMetadataReader],
    ) -> None:
        if not isinstance(readers, Mapping):
            raise ContractError("readers debe ser un Mapping")

        registered: dict[str, ResourceMetadataReader] = {}
        for resource_type, reader in readers.items():
            if not isinstance(resource_type, str) or not resource_type.strip():
                raise ContractError("resource_type debe ser una cadena no vacía")
            if resource_type in registered:
                raise ContractError("resource_type duplicado")
            if not callable(getattr(reader, "get_metadata", None)):
                raise ContractError(
                    "Cada reader debe implementar get_metadata(resource_id)"
                )
            registered[resource_type] = reader

        self._readers = MappingProxyType(registered)

    def resolve(self, resource_type: str, resource_id: str) -> object | None:
        """Devuelve None ante ausencia, error o resultado vacío: nunca permite."""
        if not isinstance(resource_type, str) or not resource_type.strip():
            return None
        if not isinstance(resource_id, str) or not resource_id.strip():
            return None

        reader = self._readers.get(resource_type)
        if reader is None:
            return None

        try:
            metadata = reader.get_metadata(resource_id)
        except Exception:
            return None

        return metadata
