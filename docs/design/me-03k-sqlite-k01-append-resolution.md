# ME-03K — SQLite K01 append y resolución de operaciones

**Estado:** contrato de implementación inicial; pendiente de validación del propietario en Debian.

## Alcance

El adaptador local implementa únicamente `append_transition` y `resolve_operation`. No declara todavía conformidad completa con `ConsistencyJournalPort`: recuperación autenticada, checkpoints y recibos de endpoint permanecen fuera de alcance.

## Firma desacoplada

`LocalConsistencySignerPort` recibe un envelope aún no autenticado y el objeto canónico exacto, y devuelve el envelope autenticado. El adaptador SQLite nunca recibe bytes de clave. La composición externa decide el firmante activo y su custodia. La verificación histórica sigue usando `LocalConsistencyKeyPort` y la política independiente.

Un firmante ausente, no disponible o que devuelva metadatos inconsistentes no produce un commit. No se genera ni rota ninguna clave automáticamente.

## Append K01

Dentro de una única transacción `BEGIN IMMEDIATE`:

1. Lee dominio, época, head y commitment.
2. Comprueba que el dominio existe, usa perfil local y coincide con la época/posición esperada.
3. Canonicaliza la proyección semántica versionada y calcula SHA-256.
4. Busca primero la clave idempotente y luego el `operation_id`.
5. Reutiliza el commit original únicamente si los bytes canónicos coinciden exactamente; de lo contrario devuelve conflicto (`None`).
6. Construye el envelope enlazado al commitment anterior, solicita firma al puerto y valida que el resultado cubra el objeto exacto.
7. Inserta entrada y resolución; actualiza el head mediante compare-and-swap dentro de la misma transacción.

Los campos técnicos regenerables se excluyen solo de la proyección semántica, no de los bytes de la transición persistida. El registro original se conserva al reproducir una solicitud.

## Resolución de resultado ambiguo

Busca por clave idempotente y por `operation_id`. Si ambos localizadores apuntan a filas diferentes, devuelve CONFLICT. Si una fila coincide exactamente en los bytes semánticos, devuelve COMMITTED_EXACT con la transición original. Si no existe ninguna y el dominio/época/head se pueden leer coherentemente, devuelve NOT_COMMITTED. Errores de lectura o evidencia incoherente producen UNKNOWN.

## Límites de esta entrega

- No implementa `load_verified_recovery_state`, checkpoints ni recibos.
- No implementa una implementación productiva de `LocalConsistencySignerPort`.
- No configura systemd credentials ni provisiona claves.
- No resuelve anti-rollback frente a restauración de una copia antigua.
- No realiza egress ni abre Recovery Gate.
