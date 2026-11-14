# ME-03K — Migración SQLite v2: vínculo exacto de operación

**Estado:** implementada en `feature/me-03k-local-profile`; pendiente de validación por el propietario en Debian.

## Objetivo

La v1 vinculaba `journal_operations` con `journal_entries` usando dominio, época, secuencia y `record_id`, pero no incluía `operation_id` en la clave foránea. Por tanto, una fila de resolución podía declarar un identificador de operación diferente al de la entrada del journal a la que apuntaba.

La v2 exige que la resolución identifique exactamente el mismo commit y la misma operación.

## Cambio estructural

1. Añade el índice único `journal_entries_operation_commit_unique` sobre:
   `(domain_id, authority_epoch, sequence, record_id, operation_id)`.
2. Reconstruye únicamente la tabla hija `journal_operations`, incorporando una FK compuesta con las cinco columnas.
3. Copia todas las filas existentes a la tabla nueva.
4. Reemplaza la tabla anterior y restaura el índice parcial único de `idempotency_key`.

No reconstruye ni modifica `journal_entries`, `consistency_domains`, checkpoints ni proyecciones. La v1 permanece inmutable.

## Comportamiento de actualización

- Las filas v1 coherentes se conservan, incluidos sus bytes canónicos, digest, clave idempotente, posición, identidad y timestamp.
- Si una fila histórica v1 enlaza una operación con una entrada cuyo `operation_id` es diferente, la copia viola la nueva FK y la migración falla.
- La migración completa y el registro de versión se ejecutan dentro de la transacción de migraciones existente. Un fallo revierte el índice, la tabla temporal y el ledger; no se corrige ni reconcilia evidencia automáticamente.
- La migración se aplica como versión 2; no se edita el SQL de v1.

## Validaciones añadidas

- La FK de v2 contiene las cinco columnas de identidad del commit.
- Una resolución nueva no puede usar un `operation_id` distinto al de la entrada referenciada.
- Una actualización desde v1 conserva una fila válida y registra las versiones 1 y 2.
- Una base v1 con un enlace inconsistente rechaza v2 y permanece en versión 1, sin tabla temporal residual.

## Límites

Esta migración solo refuerza integridad referencial. No implementa el repositorio SQLite, append K01, firma HMAC, custodia de claves, recibos, tombstones, referencias externas, Recovery Gate ni protección anti-rollback.