"""Puerto lógico del registro durable de consistencia ME-03.

La implementación debe preservar el contrato sin exponer el journal a consumidores
de memoria, Assistant o Skills.
"""
from typing import Protocol

from atlas.memory.journal import (
    ConsistencyCheckpoint,
    ConsistencyRecoveryState,
    ConsistencyTransition,
    ConsistencyPosition,
    JournalCommit,
    JournalEntry,
)


class ConsistencyJournalPort(Protocol):
    """Frontera de escritura/recuperación usada exclusivamente por la autoridad."""

    def append_transition(
        self,
        expected_position: ConsistencyPosition,
        transition: ConsistencyTransition,
    ) -> JournalCommit | None:
        """Confirma transición y secuencia como una unidad lógica.

        Misma idempotency_key + misma solicitud canónica devuelve el commit
        existente. Clave reutilizada con otra solicitud, posición obsoleta,
        transición ilegal o resultado no verificable => None/conflicto fail-closed.
        Un resultado ambiguo debe poder consultarse por operación/clave antes
        de reintentar; no se presupone que el append haya fallado.
        """

    def load_recovery_state(
        self,
        domain_id: str,
    ) -> ConsistencyRecoveryState | None:
        """Devuelve solo estado estructuralmente completo y con continuidad verificada.

        Ausencia, corrupción, truncamiento, rollback, época desconocida o
        procedencia no verificable => None; la autoridad mantiene el dominio cerrado.
        """

    def load_endpoint_receipts(
        self,
        admission_id: str,
    ) -> tuple[JournalEntry, ...] | None:
        """Recupera recibos de egress/finalización/fencing correlacionados.

        None significa que no puede demostrarse un inventario completo. Una
        tupla vacía es válida solo cuando el endpoint/operación confirma que no
        existen recibos para esa admisión.
        """

    def commit_checkpoint(
        self,
        checkpoint: ConsistencyCheckpoint,
        expected_position: ConsistencyPosition,
    ) -> JournalCommit | None:
        """Confirma checkpoint y su referencia de continuidad.

        No puede descartar registros necesarios para operaciones activas,
        endpoints no reconciliados o idempotencia/replay todavía vigente.
        """
