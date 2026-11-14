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
    JournalOperationResolution,
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

    def resolve_operation(
        self,
        domain_id: str,
        authority_epoch: int,
        operation_id: str,
        idempotency_key: str | None,
        expected_transition: ConsistencyTransition,
        expected_position: ConsistencyPosition,
    ) -> JournalOperationResolution:
        """Resuelve una escritura ambigua por identidad y solicitud canónica exacta.

        COMMITTED_EXACT solo si existe una transición durable única que coincide
        en todos los campos semánticos esperados. NOT_COMMITTED solo si la
        autoridad demuestra ausencia de commit y devuelve su posición actual.
        Clave/operación asociada a otra solicitud => CONFLICT. Indisponibilidad,
        pérdida de continuidad o imposibilidad de probar ausencia => UNKNOWN.
        UNKNOWN/CONFLICT nunca autorizan reintento nuevo ni apertura de gate.
        La implementación compara la forma canónica versionada; no bytes de
        transporte ni timestamps/IDs regenerados por el caller.
        """

    def load_recovery_state(
        self,
        domain_id: str,
    ) -> ConsistencyRecoveryState | None:
        """Devuelve estado solo después de verificar autenticidad y anti-rollback.

        Debe validar la cadena desde un ancla confiable externa al conjunto
        restaurable, dominio/época/posición monotónica, esquema, checkpoint,
        continuidad, idempotency tombstones y operaciones no terminales.
        Ausencia, corrupción, truncamiento, rollback, época desconocida, ancla
        indisponible o procedencia no verificable => None; gate cerrado.
        El reducer recibe exclusivamente estado cuya autenticidad/continuidad
        ya haya sido verificada por el adaptador.
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
