"""Puerto de acceso al contenido de versiones de memoria.

Este puerto es infraestructura interna: el acceso de lectura debe realizarse
exclusivamente después de la autorización de MemoryGateway.
"""
from typing import Protocol

from atlas.memory.models import MemoryId, MemoryVersion, MemoryVersionId


class MemoryVersionContentPort(Protocol):
    """Recupera el contenido completo de una versión concreta."""

    def get_version_content(
        self,
        memory_id: MemoryId,
        version_id: MemoryVersionId,
    ) -> MemoryVersion | None:
        """Devuelve la versión exacta, o None si no está disponible."""
