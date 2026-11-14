"""Atomic authority boundary for recovery closure and terminal gate reopening."""
from __future__ import annotations

from typing import Protocol, TYPE_CHECKING

from atlas.memory.journal import ConsistencyPosition, ConsistencyTransition, JournalCommit

if TYPE_CHECKING:
    from atlas.memory.recovery_completion import VerifiedRecoveryCompletionReceipt


class RecoveryGatePort(Protocol):
    """Serializa admisiones, egress, recuperación y reapertura del dominio."""

    def ensure_recovery_gate_closed(
        self,
        operation_id: str,
        generation: int,
    ) -> bool:
        """Confirma que el cierre exacto está restaurado tras un reinicio."""

    def close_recovery_gate(
        self,
        expected_position: ConsistencyPosition,
        transition: ConsistencyTransition,
    ) -> JournalCommit | None:
        """Cierra gate y persiste RECOVERY_CLOSED como una operación atómica."""

    def reconcile_and_open_recovery_gate(
        self,
        expected_position: ConsistencyPosition,
        transition: ConsistencyTransition,
        verified_receipt: VerifiedRecoveryCompletionReceipt,
    ) -> JournalCommit | None:
        """Persiste RECOVERY_RECONCILED y abre el gate en un único punto linealizable.

        Debe validar que el recibo verificado coincide con la transición y que
        el inventario terminal cubre exactamente el cierre activo. No puede
        persistir el evento y abrir el gate en operaciones independientes.
        Un resultado ambiguo deja el gate cerrado hasta reconciliar el estado.
        """

    def ensure_recovery_gate_open(
        self,
        operation_id: str,
        generation: int,
        receipt_id: str | None,
    ) -> bool:
        """Restaura/confirma el gate abierto solo para el cierre terminal exacto.

        Tras reinicio, exige RECOVERY_RECONCILED verificado y coincidencia exacta
        de operación, generación y recibo global. Si no puede demostrarlo,
        conserva el gate cerrado.
        """
