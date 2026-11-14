"""Única frontera permitida para leer y proponer memorias."""
from typing import Protocol, Sequence

from atlas.core.context import OperationContext
from atlas.memory.consistency import EgressReceipt, ReconciliationResult
from atlas.memory.models import Memory, MemoryProposal, MemoryVersionId
from atlas.ports.protected_memory_read import ProtectedMemoryRead


class MemoryGateway(Protocol):
    def list_visible(self, context: OperationContext) -> Sequence[Memory]:
        """Lista memorias autorizadas para el usuario del contexto."""

    def get_version(
        self,
        context: OperationContext,
        memory_id: str,
        version_id: MemoryVersionId,
    ) -> ProtectedMemoryRead | None:
        """Abre una lectura protegida; nunca devuelve contenido crudo."""

    def emit_version(
        self,
        read: ProtectedMemoryRead,
        endpoint_id: str,
        emission_id: str,
        sequence: int,
    ) -> EgressReceipt | None:
        """Compromete una unidad mediante el último punto de entrega controlado."""

    def finish_version(
        self,
        read: ProtectedMemoryRead,
        endpoint_id: str,
        final_sequence: int,
    ) -> bool:
        """Registra la finalización verificable de un endpoint."""

    def reconcile_version(
        self, read: ProtectedMemoryRead
    ) -> ReconciliationResult | None:
        """Consulta el estado terminal verificable de la lectura."""

    def submit_proposal(self, context: OperationContext, proposal: MemoryProposal) -> str:
        """Registra una propuesta pendiente y devuelve su identificador."""
