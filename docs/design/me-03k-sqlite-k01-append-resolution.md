# ME-03K — SQLite K01 append y resolución

**Estado:** contrato actualizado a identidad separada; implementación del adaptador pendiente de alineación con schema v3.

## Alcance

El adaptador local implementará únicamente `append_transition` y `resolve_append`. No declarará todavía conformidad completa con `ConsistencyJournalPort`: recuperación autenticada, checkpoints y recibos de endpoint permanecen fuera de alcance.

**Importante:** el primer borrador de `consistency_journal.py` fue escrito antes de aprobar `append_id`. No es compatible con schema v3 y no debe considerarse implementado ni utilizarse hasta que se actualice. Su lookup por `operation_id` queda expresamente supersedido por el contrato de identidad de append.

## Identidades

- `operation_id`: correlación de negocio, no única; puede repetirse en muchas entradas.
- `append_id`: localizador estable de un intento de append, pasado separadamente al repositorio.
- `idempotency_key`: localizador semántico para replay entre distintos append IDs.

API prevista:

```python
append_transition(expected_position, append_id, transition)
resolve_append(
    domain_id,
    authority_epoch,
    append_id,
    idempotency_key,
    expected_transition,
    expected_position,
)
```

El append sin clave idempotente se resuelve exclusivamente por `append_id`. Con clave, el adaptador consulta ambos localizadores y rechaza si conducen a commits distintos.

## Firma desacoplada

`LocalConsistencySignerPort` recibe un envelope aún no autenticado y el objeto canónico exacto, y devuelve el envelope autenticado. El adaptador SQLite nunca recibe bytes de clave. La composición externa decide el firmante activo y su custodia. La verificación histórica sigue usando `LocalConsistencyKeyPort` y la política independiente.

Un firmante ausente, no disponible o que devuelva metadatos inconsistentes no produce un commit. No se genera ni rota ninguna clave automáticamente.

## Append K01

Dentro de una única transacción `BEGIN IMMEDIATE`:

1. Lee dominio, época, head y commitment.
2. Comprueba el perfil local y la autoridad esperada.
3. Canonicaliza la proyección semántica versionada y calcula SHA-256.
4. Consulta por clave idempotente y por `append_id`; nunca usa `operation_id` como localizador.
5. Compara bytes canónicos exactos; un digest coincidente no basta.
6. En replay, devuelve el commit original sin insertar ni avanzar el head.
7. En append nuevo, exige CAS de posición, firma el envelope e inserta journal y resolución.
8. Actualiza el head mediante CAS dentro de la misma transacción.

## Resolución de resultado ambiguo

`resolve_append` busca por los localizadores permitidos y devuelve:

- `COMMITTED_EXACT` cuando la proyección semántica y los localizadores son coherentes;
- `CONFLICT` cuando el mismo localizador corresponde a otra semántica o los dos localizadores apuntan a commits diferentes;
- `NOT_COMMITTED` solo cuando ambos localizadores están ausentes y la posición actual es coherente;
- `UNKNOWN` ante indisponibilidad, corrupción o evidencia insuficiente.

## Siguiente trabajo de implementación

1. Alinear `JournalOperationResolution` y el puerto de journal para expresar `append_id`.
2. Actualizar `SQLiteConsistencyJournal` para usar `append_id` y el schema v3.
3. Añadir pruebas de replay con append IDs regenerados, colisiones, múltiples eventos con un mismo `operation_id`, fallos del firmante, CAS y concurrencia entre procesos.
4. Mantener desactivada la custodia real mediante systemd credentials.

## Límites

- No implementa `load_verified_recovery_state`, checkpoints ni recibos.
- No implementa una implementación productiva de `LocalConsistencySignerPort`.
- No configura systemd credentials ni provisiona claves.
- No resuelve anti-rollback frente a restauración de una copia antigua.
- No realiza egress ni abre Recovery Gate.
