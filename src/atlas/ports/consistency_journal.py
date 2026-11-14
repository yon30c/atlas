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
from atlas.memory.trust import ConsistencyRecoveryVerificationResult


class ConsistencyJournalPort(Protocol):
    """Frontera de escritura/recuperación usada exclusivamente por la autoridad."""

    def append_transition(
        self,
        expected_position: ConsistencyPosition,
        append_id: str,
        transition: ConsistencyTransition,
    ) -> JournalCommit | None:
        """Confirma transición y secuencia como una unidad lógica.

        Misma idempotency_key + misma solicitud canónica devuelve el commit
        existente. Clave reutilizada con otra solicitud, posición obsoleta,
        transición ilegal o resultado no verificable => None/conflicto fail-closed.
        append_id es estable durante los reintentos de este append y único
        dentro del dominio/época. operation_id es solo correlación de negocio.
        Un resultado ambiguo se consulta por append_id y, si existe, por
        idempotency_key; nunca por operation_id.
        """

    def resolve_append(
        self,
        domain_id: str,
        authority_epoch: int,
        append_id: str,
        idempotency_key: str | None,
        expected_transition: ConsistencyTransition,
        expected_position: ConsistencyPosition,
    ) -> JournalOperationResolution:
        """Resuelve una escritura ambigua por append_id y clave semántica.

        operation_id nunca es localizador único. Si ambos localizadores
        identifican commits distintos, o uno identifica otra semántica => CONFLICT.
        NOT_COMMITTED requiere ausencia por ambos localizadores y posición coherente.
        Indisponibilidad o evidencia insuficiente => UNKNOWN.
        UNKNOWN/CONFLICT nunca autorizan reintento nuevo ni apertura de gate.
        La implementación compara la forma canónica versionada; no bytes de
        transporte ni timestamps/IDs regenerados por el caller.
        """

    def load_verified_recovery_state(
        self,
        domain_id: str,
    ) -> ConsistencyRecoveryVerificationResult:
        """Carga estado autenticado y continuo según el perfil explícitamente configurado.

        VERIFIED puede contener VerifiedLocalConsistencyRecoveryState o
        VerifiedConsistencyRecoveryState. El resultado identifica el perfil.
        El perfil local valida autenticidad disponible, estructura, secuencias,
        referencias, inventarios, tombstones y operaciones no terminales, pero
        no afirma anti-rollback externo. El perfil anclado exige un Trust Anchor
        vigente y no puede degradarse silenciosamente al perfil local.
        REJECTED/UNAVAILABLE nunca permiten entregar estado al reducer ni abrir
        el gate. La carga estructural desnuda queda limitada a diagnóstico.
        """

    def load_recovery_state(
        self,
        domain_id: str,
    ) -> ConsistencyRecoveryState | None:
        """Carga estructural sin atestación de confianza; solo diagnóstico/migración.

        Este método no puede usarse para alimentar el reducer en recuperación
        operativa, admitir lecturas, emitir contenido ni abrir el recovery gate.
        Los flujos operativos deben usar exclusivamente
        load_verified_recovery_state().
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
