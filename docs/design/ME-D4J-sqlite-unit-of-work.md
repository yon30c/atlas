# ME-D4J — diseño de unidad de trabajo SQLite compartida

**Estado:** diseño propuesto para revisión. No implementado.  
**Rama objetivo:** `feature/atlas-functional-f1`  
**Precondición:** ME-D4I identificó que `SQLiteConsistencyJournal` abre una transacción privada por operación.

## 1. Problema que resuelve

Actualmente `SQLiteDatabase.write_transaction()` abre una conexión y ejecuta `BEGIN IMMEDIATE`. `SQLiteConsistencyJournal.append_transition()` llama a ese método internamente. Una autoridad que actualice el Recovery Gate y después invoque el append ejecutaría dos transacciones distintas.

La identidad de una instancia `SQLiteConsistencyJournal` no hace que esas transacciones sean atómicas. Tampoco lo resuelve un lock Python: no coordina procesos independientes ni sobrevive reinicios.

## 2. Decisión de diseño

Introducir una unidad de trabajo explícita, propiedad de una instancia `SQLiteDatabase`, que controle el ciclo de vida de una sola conexión y transacción.

API conceptual propuesta:

```python
with database.unit_of_work() as uow:
    journal.append_transition_in(uow, expected_position, append_id, transition)
    authority.apply_gate_change_in(uow, ...)
# commit automático al salir correctamente; rollback ante excepción
```

Los nombres son una propuesta de diseño, no APIs existentes.

### Contrato de SQLiteUnitOfWork

- Se crea exclusivamente por `SQLiteDatabase.unit_of_work()`.
- Adquiere la reserva de escritura mediante `BEGIN IMMEDIATE` antes de leer estado mutable.
- Tiene una conexión configurada y una identidad de propietario que corresponde a la instancia de base de datos que lo creó.
- Solo permanece activo dentro del bloque de contexto.
- Expone una operación interna para comprobar propietario y estado activo antes de cada uso.
- No permite commit/rollback manual por parte de los repositorios o la autoridad.
- No permite anidamiento, reutilización después del cierre ni uso con otra instancia de `SQLiteDatabase`.
- El gestor de contexto es el único responsable de commit o rollback y de cerrar la conexión.

La conexión no debe guardarse en objetos de larga vida ni exponerse a consumidores externos. Los métodos `*_in(uow, ...)` son operaciones internas de infraestructura.

## 3. Compatibilidad con la API actual

Conservar `SQLiteDatabase.write_transaction()` como wrapper compatible que abre una unidad de trabajo y entrega su conexión actual a los consumidores existentes.

Conservar `SQLiteConsistencyJournal.append_transition(...)` como método público. Su flujo sería:

1. Abrir `database.unit_of_work()`.
2. Delegar en `append_transition_in(uow, ...)`.
3. Dejar que la unidad de trabajo confirme o revierta.

El nuevo `append_transition_in` ejecuta el cuerpo actual de append usando la conexión de la unidad de trabajo y **no** abre ni confirma otra transacción.

Aplicar el mismo patrón a operaciones que deban participar en una operación compuesta. No migrar `commit_checkpoint` automáticamente si no forma parte de esa misma frontera; debe conservar sus invariantes y CAS.

## 4. Orden de una operación compuesta

Dentro de una única unidad de trabajo:

1. Validar que UoW pertenece al mismo `SQLiteDatabase` usado por journal y autoridad.
2. Leer dominio, época, head, estado del gate y operación/idempotencia.
3. Resolver reintentos exactos antes de mutar.
4. Comprobar que el gate y las condiciones de admisión permiten la operación.
5. Preparar y autenticar la transición con el signer local configurado.
6. Aplicar cambios de estado de autoridad y registros de admisión/fencing pertinentes.
7. Insertar journal entry y registro de append/idempotencia.
8. Actualizar head mediante compare-and-swap.
9. Verificar que todas las escrituras esperadas afectaron exactamente una fila.
10. Salir del contexto y confirmar una sola vez.

Cualquier fallo, excepción del signer, conflicto de CAS, discrepancia de idempotencia o error SQL debe provocar rollback total. No se devuelve éxito antes del commit.

Para cerrar el Recovery Gate, el estado durable cerrado y la transición autenticada `RECOVERY_CLOSED` deben pertenecer al mismo commit. Para reabrir, `RECOVERY_RECONCILED`, el recibo terminal verificado y la transición a abierto deben pertenecer al mismo commit. Si el resultado del commit es ambiguo por caída o pérdida de conexión, la siguiente operación debe resolver por identidad exacta e idempotencia; hasta demostrar el estado, el gate permanece cerrado.

## 5. Una sola verdad para el Recovery Gate

Los campos existentes en `consistency_domains` (`recovery_gate_state`, `active_recovery_operation_id`, `active_recovery_generation`, `recovery_receipt_id`) pueden servir como proyección materializada para decisiones rápidas, pero no deben convertirse en una autoridad paralela al journal.

La implementación deberá definir y verificar invariantes:

- Gate abierto: no existe recuperación activa y la última transición terminal está autenticada y enlazada a la operación/generación/recibo exactos.
- Gate cerrado: hay un cierre activo identificable o el sistema está en estado fail-closed de recuperación.
- La transición, la proyección y el head deben coincidir después de cada commit.
- Al iniciar el proceso, una discrepancia, ausencia de evidencia o estado desconocido mantiene el gate cerrado.
- Ninguna consulta estructural de SQLite por sí sola acredita autenticidad; se debe ejecutar el verificador local y comprobar continuidad, trust policy y anti-rollback disponible.

No se debe añadir una migración solo para reutilizar campos existentes. Si el análisis de invariantes descubre que faltan datos para reconstrucción o resolución idempotente, documentar el gap y diseñar una migración nueva, sin alterar V1–V3.

## 6. Límite del egress remoto

La unidad de trabajo SQLite no puede hacer atómica la aceptación irreversible de datos por un endpoint externo. El contrato actual de `ProtectedEgressPort.commit_and_emit` exige una relación indivisible entre validar fencing y aceptar la emisión, pero una transacción local no controla un receptor remoto.

Antes de implementar egress real se requiere un protocolo del endpoint con identidad de emisión idempotente, secuencia, generación/fencing y acknowledgement verificable, además de reconciliación de resultado desconocido. Si el receptor no ofrece esa garantía, no se debe declarar que Forget/invalidation impide toda emisión posterior.

ME-D4J diseña la transacción local; no resuelve por sí solo el protocolo distribuido de entrega.

## 7. Cambios mínimos previstos

1. `database.py`: introducir `SQLiteUnitOfWork` y `SQLiteDatabase.unit_of_work()`; mantener `write_transaction()` como wrapper.
2. `consistency_journal.py`: extraer el cuerpo transaccional de append a una operación que reciba UoW y compruebe el propietario.
3. Añadir métodos internos equivalentes solo para las mutaciones de autoridad que deban compartir la transacción.
4. Implementar la autoridad SQLite concreta sobre el mismo objeto `SQLiteDatabase` y journal, sin locks como fuente de verdad.
5. Mantener los puertos públicos y la composición ME-D4H; la raíz debe inyectar exactamente la misma autoridad en Gateway y coordinador.
6. No cambiar la canonicalización, envelope, HMAC, CAS, semántica de idempotencia, reducer ni DTO persistidos durante el refactor.

## 8. Pruebas requeridas antes de activar

No ejecutadas en esta fase. La futura implementación debe incluir:

- Commit y rollback de UoW; rollback al lanzar excepción.
- Rechazo de UoW cerrado, anidado o perteneciente a otra base.
- Compatibilidad de `write_transaction()` y `append_transition()` existentes.
- Fallo inyectado entre mutación del gate, append, registro idempotente y actualización del head: no puede quedar escritura parcial.
- Dos procesos compitiendo por admisión y cierre: un único orden serializable.
- Reintentos exactos y claves idempotentes discordantes.
- Cierre y caída/reinicio en cada punto antes y después del commit.
- Reconciliación y apertura solo con recibo verificado exacto.
- Pruebas separadas del protocolo de fencing/egress con receptor simulado que conserva deduplicación durable.

## 9. Criterio de aceptación

ME-D4J no se considera implementado hasta que autoridad, journal y mutación del gate participen en una sola transacción SQLite comprobable, con rollback completo y pruebas multiproceso. No activar Gateway, Recovery Coordinator ni egress protegido antes de esa validación.

**No se ejecutaron pruebas ni build durante el trabajo de diseño.**


## Implementación preparatoria ME-D4K

La fase ME-D4K añadió en `src/atlas/adapters/sqlite/database.py`:

- `SQLiteUnitOfWork`, con referencia al propietario exacto, conexión privada y estado activo.
- `SQLiteDatabase.unit_of_work()`, que abre una conexión configurada, inicia `BEGIN IMMEDIATE`, confirma al salir normalmente y revierte si se propaga una excepción.
- Rechazo de anidamiento en el mismo hilo.
- `_connection_for(database)` comprueba identidad del propietario y que la transacción siga activa.
- `write_transaction()` ahora delega en la unidad de trabajo y conserva su interfaz legacy de conexión SQLite.
- `SQLiteUnitOfWork` se exporta desde `atlas.adapters.sqlite`.

Se añadieron tests unitarios para commit, rollback, propietario incorrecto, anidamiento y compatibilidad legacy. **No se ejecutaron**.

Esta entrega no modifica `SQLiteConsistencyJournal`: sus métodos siguen abriendo sus propias transacciones a través de `write_transaction()`. La unidad de trabajo es infraestructura disponible, no integración atómica gate+journal. La siguiente etapa deberá extraer un método interno de journal que reciba la unidad de trabajo exacta y demuestre que no abre ni confirma una transacción adicional.


## ME-D4L — integración de append_transition

**Estado: implementación añadida; validación pendiente.**

- Se añadió `SQLiteConsistencyJournal.append_transition_in(unit_of_work, expected_position, append_id, transition)`. La operación valida que la UoW esté activa y pertenezca a la misma instancia `SQLiteDatabase`, y utiliza exclusivamente su conexión.
- La ruta interna conserva validación del dominio y época, detección de replay por append/idempotency key, comparación de solicitud canónica, firma y validación del envelope, inserciones de journal/operación y compare-and-swap del head.
- La ruta interna no captura errores inesperados ni controla el ciclo de vida transaccional. Los propaga al dueño de la UoW para que el contexto revierta la operación compuesta.
- El método público `append_transition(...)` conserva su firma y resultado histórico, envolviendo la operación interna en una UoW propia y devolviendo `None` ante errores ordinarios.
- Se añadieron pruebas para append dentro de una UoW externa y rollback conjunto cuando falla el signer después de una mutación acompañante. Las pruebas no se ejecutaron.
- No se adaptaron `commit_checkpoint`, `create_local_domain` ni otros métodos. No hay todavía autoridad SQLite del Recovery Gate y no se declara atomicidad gate+journal completa.


## ME-D4M — integración de commit_checkpoint

**Estado: implementación añadida; validación pendiente.**

- Se añadió SQLiteConsistencyJournal.commit_checkpoint_in(unit_of_work, expected_position, expected_head_commitment, checkpoint).
- La operación interna valida la UoW exacta y activa y reutiliza su conexión para leer el dominio y los registros previos, verificar replay/conflicto, firmar checkpoint y marcador, insertar checkpoint/journal/operación idempotente y actualizar el head mediante CAS.
- No abre ni confirma transacciones. Los errores inesperados de persistencia se propagan para que el dueño de la UoW revierta todas las mutaciones compuestas.
- commit_checkpoint(...) conserva la API pública y delega en una UoW propia. Ante una excepción transaccional devuelve UNKNOWN; los estados de conflicto y signer no disponible siguen siendo resultados explícitos.
- Se añadieron pruebas de éxito dentro de UoW externa y rollback de una mutación acompañante junto con checkpoint/marker/operation/head ante fallo inyectado del marcador. No se ejecutaron.
- La operación de checkpoint ahora comparte la frontera transaccional local cuando se invoca explícitamente con una UoW. No hay todavía autoridad SQLite concreta para Recovery Gate, ni integración de gate/egress.
