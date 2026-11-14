"""Puerto de autorización de memoria independiente del proyecto consumidor."""
from datetime import datetime
from typing import Protocol

from atlas.authorization.models import AuthorizationResult
from atlas.memory.context import MemoryRequestContext
from atlas.memory.models import MemoryId, MemoryVersionId


class MemoryAuthorizationPort(Protocol):
    """Solicita una decisión de acceso; no concede autoridad por sí mismo."""

    def authorize_read(
        self,
        context: MemoryRequestContext,
        memory_id: MemoryId,
        now: datetime,
        version_id: MemoryVersionId | None = None,
    ) -> AuthorizationResult:
        """Autoriza la memoria/versión exacta y devuelve evidencia CAM verificable."""
