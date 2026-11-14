# ME-D4N — Recovery Gate SQLite: implementación de la frontera local

**Estado:** adaptador gate-only implementado; pruebas añadidas y pendientes de ejecución.  
**Rama:** `feature/atlas-functional-f1`.  
**Dependencias:** ME-D4D–ME-D4M, ME-03H, ME-03I, ME-03J-B y esquema SQLite V1–V3.

## 1. Objetivo y alcance

Implementar una primera autoridad durable para el contrato `RecoveryGatePort`, vinculada a la instancia exacta de `SQLiteConsistencyJournal`. El cierre/apertura del gate y su transición autenticada deben participar en una única transacción SQLite.

La clase `LocalSQLiteRecoveryGateAdapter` implementa exclusivamente `RecoveryGatePort`. **No** implementa `ProtectedMemoryConsistencyPort` ni `ProtectedMemoryRecoveryAuthorityPort`; por tanto, todavía no es la autoridad completa que debe compartir orden con admisión de lecturas y egress protegido.

## 2. Fuente de evidencia y fail-closed

Antes de cada operación, el adaptador solicita `load_verified_recovery_state(domain_id)` y exige:

- resultado tipado `VERIFIED`;
- evidencia `VerifiedLocalConsistencyRecoveryState` presente;
- dominio, época, head, política de confianza y proyección coincidentes;
- proyección semántica validada por el verificador local.

No usa `load_recovery_state()` ni una lectura estructural como autoridad operativa. Una excepción, estado no verificado, proyección ausente o discrepancia bloquea la operación.

El adaptador compara dentro de la transacción el dominio, época, secuencia y commitment del head contra el snapshot verificado. Si otra operación cambió el journal entre la lectura verificada y `BEGIN IMMEDIATE`, no escribe.

## 3. Cierre atómico

`close_recovery_gate(expected_position, transition)`:

1. exige `RECOVERY_CLOSED` y la posición verificada exacta;
2. rechaza una recuperación que ya esté activa; esa ruta debe pasar por `ensure_recovery_gate_closed`;
3. calcula desde la proyección todas las admisiones no terminales y su unión exacta de rutas;
4. exige que la transición declare esos inventarios y la operación canónica `recovery:{domain}:{epoch}:{generation}`;
5. exige una generación superior a las generaciones previas y ausencia de invalidaciones pendientes; las admisiones afectadas por Forget deben estar terminales;
6. abre una `SQLiteUnitOfWork`, revalida el head, ejecuta `append_transition_in` y actualiza la proyección materializada del gate a cerrado;
7. confirma ambas escrituras en el mismo commit.

Si el append devuelve rechazo o la actualización del gate no afecta exactamente una fila, una excepción interna fuerza rollback. La ruta nunca confirma el cierre si no puede confirmar también `RECOVERY_CLOSED`, ni viceversa.

## 4. Restauración del cierre

`ensure_recovery_gate_closed(operation_id, generation)` solo acepta la única recuperación activa más reciente demostrada por la proyección verificada. Dentro de una UoW revalida el head y materializa:

- `recovery_gate_state = closed`;
- operación y generación exactas;
- `recovery_receipt_id = NULL`.

Permite reparar una proyección local abierta o incompleta cuando el journal autenticado demuestra un cierre activo. No crea una transición nueva ni inventa una recuperación.

## 5. Reconciliación y apertura atómica

`reconcile_and_open_recovery_gate(..., verified_receipt)` exige:

- `VerifiedRecoveryCompletionReceipt` tipado;
- coincidencia exacta de dominio, época, operación, generación, recibo, admisiones y rutas;
- cierre activo más reciente;
- todas las admisiones afectadas en estado terminal;
- proyección materializada cerrada para la operación/generación exactas.

Dentro de una sola UoW ejecuta `append_transition_in` con `RECOVERY_RECONCILED` y cambia la proyección a abierta, elimina operación/generación activa y conserva el recibo terminal. Un fallo de cualquiera de las dos escrituras revierte ambas.

`ensure_recovery_gate_open` solo restaura apertura si la proyección verificada contiene el cierre reconciliado más reciente, con operación, generación y recibo exactos y sin otra recuperación activa. Una recuperación antigua nunca puede reabrir el gate después de una generación posterior.

## 6. Composición y límite de autoridad

Se añadió `compose_local_sqlite_recovery_gate_coordinator(...)`, que compone el journal, los puertos de persistencia/verificación y el adaptador gate-only para `RecoveryJournalCoordinator`.

Esta composición se distingue deliberadamente de `compose_local_sqlite_recovery_coordinator(...)`, que sigue exigiendo una única autoridad completa compatible con `ProtectedMemoryRecoveryAuthorityPort` y que además debe ser la misma instancia inyectada en MemoryGateway.

La implementación gate-only **no** serializa todavía:
- `admit_read`;
- `begin_forget` / `begin_invalidation`;
- `commit_and_emit`, `finish` o `fence`;
- otras mutaciones de admisión/egress.

Por tanto, el cierre/apertura y journal son atómicos localmente, pero no se declara que las lecturas o emisiones protegidas ya compartan este mismo orden linealizable.

## 7. Esquema, anti-rollback y operación

No se añadió migración. Los campos `recovery_gate_state`, `active_recovery_operation_id`, `active_recovery_generation` y `recovery_receipt_id` ya existen en `consistency_domains` desde V1 y se usan como proyección materializada del journal, no como autoridad paralela.

El verificador del perfil local autentica la cadena, valida replay e inventarios, pero `VerifiedLocalConsistencyRecoveryState` declara explícitamente que no tiene protección anti-rollback externa. Un backup SQLite antiguo restaurado no puede demostrarse como el estado más reciente sin un ancla independiente.

No se conectó este adaptador a un servicio en ejecución, MemoryGateway ni egress protegido. No se modificó Broker, Registry, Docker, systemd ni producción.

## 8. Pruebas añadidas

`tests/unit/test_local_sqlite_recovery_gate.py` cubre:

- cierre y proyección del gate en una operación;
- rollback del append si falla la actualización de la proyección;
- concurrencia de dos cierres contra el mismo head;
- reconciliación y apertura con recibo verificado exacto;
- rollback de `RECOVERY_RECONCILED` si falla la actualización a abierto;
- rechazo de recibo con inventario incorrecto;
- restauración del gate cerrado/abierto desde la proyección verificada.

`tests/unit/test_local_sqlite_recovery_composition.py` comprueba la composición gate-only y la identidad exacta del journal.

**Las pruebas no se ejecutaron. No se ejecutó build ni CI.** Los fixtures de esta suite sustituyen el proveedor de evidencia verificada para probar la frontera transaccional; no demuestran custodia real de claves, anti-rollback ni verificación criptográfica de producción.

## 9. Siguiente frontera

ME-D4N completa únicamente la primera implementación de `RecoveryGatePort`. El siguiente trabajo debe unificar la autoridad de admisión, Forget/invalidation y egress con esta misma base y unidad de trabajo. Solo entonces podrá afirmarse que Recovery Gate, admisión y punto de emisión comparten una única autoridad serializable. Las pruebas multiproceso y de caída/reinicio deberán ejecutarse antes de considerar el Memory Engine validado.
