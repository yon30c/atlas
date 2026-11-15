# ME-D4O-I-C.4.1 — Almacén SQLite durable de cambios de autoridad

**Estado:** persistencia de reservas/idempotencia implementada; coordinación transaccional completa pendiente.  
**Rama:** `feature/me-d4o-i-c4-sqlite-durable-authority-store`

## Objetivo

Establecer la base durable LOCAL para operaciones de cambio de autoridad sin crear una segunda autoridad de consistencia ni mezclar modelos de aplicaciones consumidoras con el Memory Engine.

La implementación reutiliza la instancia `SQLiteDatabase` y su `SQLiteUnitOfWork` existentes. No crea otra base ni abre una transacción paralela para reservar una operación.

## Migración v4

`CORE_SCHEMA_V4` añade tablas de control:

- `authority_change_operations`: identidad, consumidor, autoridad exacta, revisiones, intención, estado y resultado fuente.
- `authority_change_idempotency`: namespace `(consumer_id, idempotency_key)`, operación única, digest y representación canónica.
- `authority_change_invalidations`: invalidación, revisiones y generación de fencing.
- `authority_change_affected_admissions`: admisiones capturadas por operación.
- `authority_change_affected_routes`: rutas por admisión y estado de fencing.
- `authority_change_source_results`: resultado canónico y revisión confirmada de la fuente.
- `authority_change_recovery_evidence`: evidencia de recuperación por fase.

Las tablas guardan metadatos del plano de control. No contienen payload de Memory, embeddings ni contenido de negocio. La fuente autoritativa específica sigue detrás de su adaptador.

La migración es aditiva: no modifica las migraciones v1–v3 ni las tablas del journal existente.

## SQLiteAuthorityChangeStore

Ubicación: `src/atlas/adapters/sqlite/authority_changes.py`.

Implementado:

- Reserva REQUESTED y asignación de `operation_id` por el almacén.
- Persistencia atómica de operación + clave idempotente en una sola `SQLiteUnitOfWork`.
- Recuperación por consumidor/clave y por operation_id.
- Reintento semánticamente idéntico recupera la operación original, conservando el `requested_at` original.
- Misma clave con otro consumidor permanece aislada.
- Misma clave y consumidor con otra autoridad/revisión/intención devuelve conflicto (`None`); nunca reutiliza la operación.
- Las lecturas de resultados no convierten registros incompletos en COMPLETED o ABORTED. Estados terminales requieren revisión fuente e invalidación compatibles con el modelo.

La proyección semántica idempotente excluye `requested_at` porque es metadata de la primera solicitud y no debe cambiar al reintentar. Conserva todos los campos semánticos: consumidor, clave, autoridad/recurso, revisiones, tipo de cambio y referencia de contexto.

## Límites explícitos

Esta entrega **no implementa todavía**:

1. El coordinador SQLite completo de ME-D4O-F/H.
2. El cálculo autoritativo de admisiones afectadas desde el estado de admisión.
3. La invalidación y fencing serializados con nuevas admisiones.
4. La aplicación CAS de la fuente y su registro idempotente en la misma transacción.
5. La reconciliación journal + resultado fuente + liberación de admisiones.
6. La recuperación automática de operaciones no terminales antes de reabrir el Recovery Gate.
7. La integración con un adaptador CAM criptográfico real o consumo one-shot durable.

Por tanto, las tablas de invalidación/admisiones/rutas/resultados/evidencia son el esquema para las siguientes fases, no prueba de que esas operaciones estén activas. `SQLiteAuthorityChangeStore` no implementa por sí solo `AuthorityChangeCoordinatorPort` y no debe inyectarse como si fuera el coordinador completo.

## Siguiente fase

**ME-D4O-I-C.4.2 — Coordinador SQLite sobre la autoridad única de consistencia.**

Debe leer y serializar admisiones contra la misma fuente de estado que usa `admit_read`, registrar fencing antes de cambiar la fuente, aplicar CAS mediante un adaptador que participe en la misma UoW, y reconciliar el journal antes de liberar admisiones.

No se permite crear un ledger paralelo que eluda `ProtectedMemoryConsistencyPort`, ni considerar completa la revocación hasta que las pruebas de reinicio, concurrencia, resultado ambiguo, aislamiento y reconciliación pasen.
