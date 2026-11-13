"""Única frontera permitida para leer y proponer memorias."""
from typing import Protocol, Sequence

from atlas.core.context import OperationContext
from atlas.memory.models import (
    Memory,
    MemoryProposal,
    MemoryVersion,
    MemoryVersionId,
)


class MemoryGateway(Protocol):
    def list_visible(self, context: OperationContext) -> Sequence[Memory]:
        """Lista memorias autorizadas para el usuario del contexto."""

    def get_version(
        self,
        context: OperationContext,
        memory_id: str,
        version_id: MemoryVersionId,
    ) -> MemoryVersion | None:
        """Recupera una versión concreta solo después de autorización CAM."""

    def submit_proposal(self, context: OperationContext, proposal: MemoryProposal) -> str:
        """Registra una propuesta pendiente y devuelve su identificador."""
