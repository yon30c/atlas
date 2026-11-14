# ME-03K — SQLite K01 append y resolución

**Estado:** contrato y primera implementación K01 alineados con schema v3; pruebas de integración del adaptador pendientes de ejecución en Debian.

## Alcance

El adaptador local implementará únicamente `append_transition` y `resolve_append`. No declarará todavía conformidad completa con `ConsistencyJournalPort`: recuperación autenticada, checkpoints y recibos de endpoint permanecen fuera de alcance.

**Importante:** el primer borrador de `consistency_journal.py` fue escrito antes de aprobar `append_id` y quedó supersedido. La implementación actual utiliza `append_id` e `idempotency_key`; `operation_id` se conserva únicamente como correlación de negocio.

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

## Estado de implementación

1. `ConsistencyJournalPort.append_transition` recibe `append_id` como argumento independiente.
2. La reconciliación se denomina `resolve_append` y el DTO `JournalOperationResolution` identifica el intento mediante `append_id`, no `operation_id`.
3. `SQLiteConsistencyJournal` consulta por `append_id` y `idempotency_key`, inserta `append_id` en `journal_operations` y conserva el commit original en replay semántico.
4. Los consumidores de recuperación pasan un identificador estable para el mismo objeto de transición (`append:<record_id>`); un nuevo intento semántico con IDs regenerados se resuelve por `idempotency_key`.
5. Los coordinadores aceptan un commit replayed anterior al head actual, pero nunca confunden ese resultado con un append nuevo.
6. `operation_id` no se utiliza para lookup ni unicidad.
7. La implementación todavía requiere validación completa en Debian.
8. Mantener desactivada la custodia real mediante systemd credentials.

## Límites

- No implementa `load_verified_recovery_state`, checkpoints ni recibos.
- No implementa una implementación productiva de `LocalConsistencySignerPort`.
- No configura systemd credentials ni provisiona claves.
- No resuelve anti-rollback frente a restauración de una copia antigua.
- No realiza egress ni abre Recovery Gate.
