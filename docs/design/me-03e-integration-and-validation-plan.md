# ME-03E — Integración, concurrencia, recuperación y seguridad

**Estado:** plan de integración y validación; parte de las pruebas con fakes está implementada.  
**Rama:** `implementation/me-01-to-me-04-memory-engine`  
**Dependencias:** ME-03A, ME-03B, ME-03C, ME-03D; CT-01 a CT-08; DM-01; QA-01.  
**No objetivos:** elegir PostgreSQL/SQLite/Redis/broker, crear adaptadores de producción, desplegar, abrir PR/merge o declarar Forget real.

## 1. Objetivo

ME-03E comprueba que los contratos de Gateway, CAM, autoridad de consistencia, egress, journal y Forget Coordinator funcionan juntos. Debe demostrar que el sistema no se reabre ante carreras, fallos, recuperación incompleta o evidencia contradictoria.

La validación se divide en tres niveles que no deben confundirse:

1. **Pruebas puras/modelos:** validan invariantes locales.
2. **Fakes integrados y concurrencia de proceso:** validan la composición y el orden dentro del proceso de prueba.
3. **Adaptadores reales/distribuidos:** validan persistencia, fencing, recuperación y transporte concretos. Este nivel sigue bloqueado por decisiones e inventarios pendientes.

## 2. Estado actual

### Implementado en código/pruebas
- ME-03B: `ProtectedMemoryConsistencyPort` es la única frontera inyectada en Gateway.
- Gateway/CAM: prueba integrada de lectura autorizada, emisión, finalización y reconciliación usando la misma instancia fake.
- Autoridad fake: usa un lock compartido para admisión, Forget, invalidación y egress.
- Concurrencia de proceso: pruebas con barreras, sin sleeps, para:
  - admisión contra Forget;
  - emisión contra invalidación;
  - emisión contra Forget;
  - dos emisiones con la misma secuencia;
  - Forget contra invalidación sobre la misma admisión.
- ME-03C: reducer de journal, schemas cerrados, inventarios exactos, generaciones, secuencias, idempotencia y fail-closed con checkpoint sin base.
- ME-03D: reducer puro de Forget, inventario versionado, recibos de eliminación/verificación, política de backup, recibo canónico y estados monotónicos.

### No implementado
- Journal durable ni checkpoint base autenticado.
- Autoridad compartida entre procesos/nodos.
- Egress real con commit/release atómico y fencing del transporte.
- Inventario real de destinos y atestación de completitud.
- Política aprobada de backups/retención.
- Adaptadores de eliminación/verificación.
- Recuperación real de procesos y nodos.
- Forget físico completado.

## 3. Decisión ME-03E-01 — No mezclar niveles de evidencia

Una prueba de fake no demuestra una propiedad distribuida. Una prueba de integración en un proceso no demuestra durabilidad. Una respuesta de un adaptador no prueba que los datos hayan desaparecido si no existe una verificación independiente.

Cada resultado de prueba debe identificar:
- nivel (pure, fake-in-process, adapter-integration, distributed);
- componentes reales vs fakes;
- orden de operaciones;
- fallos inyectados;
- garantías demostradas;
- límites que siguen sin probarse.

No se permite describir los fakes actuales como autoridad durable o egress real.

## 4. Decisión ME-03E-02 — Pruebas de carrera sin temporizadores

Las pruebas concurrentes deben usar barreras/eventos controlados, no `sleep()` ni ventanas de tiempo probabilísticas. El resultado debe pertenecer a uno de los órdenes linealizables permitidos.

Para cada carrera:
- se define la operación que puede ganar;
- se registra el resultado de cada hilo;
- se comprueba el estado final;
- se intenta una operación tardía y se verifica que el cierre la rechaza;
- no se acepta que ambas operaciones ganen si sus alcances se solapan.

Las pruebas de proceso actual validan el lock compartido del fake. No prueban inter-proceso ni inter-nodo.

## 5. Decisión ME-03E-03 — Integración de extremo a extremo

El flujo mínimo que debe probarse con una misma instancia de consistencia:

1. CAM emite snapshot exacto solo en ALLOW.
2. Gateway solicita admisión.
3. ContentPort entrega handle solo para snapshot/admisión exactos.
4. Gateway crea capacidad opaca.
5. Gateway compromete cada emisión a través de la misma frontera.
6. Finalización/ack se registra en esa frontera.
7. Reconciliación solo retira la capacidad después de evidencia terminal.
8. Forget/invalidation cierran la misma autoridad y bloquean egress posterior.
9. Recuperación no reabre si falta evidencia.

La integración actual cubre lectura CAM → Gateway → fake de consistencia → egress → finalización → reconciliación. También se añadió una carrera de hilos entre una sesión Gateway real de prueba y Forget sobre la misma instancia fake; el contenido no puede emitirse después del cierre.

## 6. Decisión ME-03E-04 — Recuperación como operación de seguridad

La recuperación debe reconstruir:
- último head/epoch y continuidad del journal;
- admisiones no terminales;
- cierres Forget e invalidaciones;
- recibos por endpoint;
- idempotency tombstones;
- operaciones Forget y estado por destino;
- revisiones de inventario y recibos de eliminación/verificación.

Si el checkpoint no trae base autenticada, si hay secuencia/recibo contradictorio o si falta un endpoint, el sistema queda cerrado. No se acepta “no hay proceso activo” como evidencia de cancelación.

ME-03C ya falla cerrado cuando el checkpoint no tiene proyección base reconstruida. La recuperación integrada durable queda pendiente.

## 7. Decisión ME-03E-05 — Adaptadores reales bloqueados por prerrequisitos

No se implementarán adaptadores reales hasta disponer de:
1. inventario aprobado de todos los destinos y fuentes de restauración;
2. política verificable de backups/retención;
3. responsable y formato de atestación del inventario;
4. recibos verificables de eliminación y ausencia por destino;
5. autoridad/journal durable con anti-rollback y recuperación;
6. egress que pruebe fencing y commit/release atómico;
7. puerto canónico con CAS para marcar todas las versiones forgotten;
8. plan de concurrencia y recuperación contra los adaptadores seleccionados.

Estos prerrequisitos no autorizan a seleccionar tecnología. La selección de persistencia y transporte sigue fuera de alcance.

## 8. Matriz de aceptación

| ID | Escenario | Evidencia esperada |
|---|---|---|
| E01 | CAM DENY | No admission ni lectura de contenido. |
| E02 | CAM ALLOW | Snapshot exacto, admisión y handle exactos. |
| E03 | Gateway emite por la misma frontera | Una instancia recibe admit/egress/finish/reconcile. |
| E04 | Capacidad falsificada | No emite ni finaliza. |
| E05 | Ruta no registrada | Rechazo antes de egress. |
| E06 | Admisión vs Forget concurrentes | Un único orden; nueva admisión después del cierre rechazada. |
| E07 | Egress vs invalidación concurrentes | Egress antes del cierre o rechazado; nunca después. |
| E08 | Egress vs Forget concurrentes | Egress antes del cierre o rechazado; Forget captura la admisión previa. |
| E09 | Dos emisiones con misma secuencia | Como máximo una se compromete. |
| E10 | Forget vs invalidación solapados | Como máximo un cierre gana sobre la admisión compartida. |
| E11 | Grant expira entre fragmentos | Fragmento posterior rechazado. |
| E12 | Revisión cambia entre admisión y egress | Egress rechazado. |
| E13 | Un endpoint no responde | Admisión no terminal; no SUPPRESSED. |
| E14 | Recibo de endpoint contradictorio | Cuarentena/fail-closed. |
| E15 | Reconciliación de admisión incompleta | Capacidad local no se retira ni se declara terminal. |
| E16 | Journal append ambiguo | No crear segunda operación ni leer contenido. |
| E17 | Journal con gap/rollback/schema desconocido | Recuperación rechazada. |
| E18 | Checkpoint sin base autenticada | Gate permanece cerrado. |
| E19 | Recuperación con tombstone de idempotencia | Replay no crea otra operación. |
| E20 | Inventario Forget incompleto | No PURGING/COMPLETED. |
| E21 | ACK de borrado sin ABSENT | No marcar forgotten. |
| E22 | Backup sin política verificable | No COMPLETED. |
| E23 | Inventario cambia durante purga | Nuevo destino incorporado; re-verificación. |
| E24 | Caída durante Forget | Cierre permanece; reconciliar recibos antes de continuar. |
| E25 | Restauración/reindexación con tombstone | No reaparición ni exposición. |
| E26 | Evidencia de operación | Sin payload, fragmentos ni hashes de contenido. |

E01–E10 tienen cobertura parcial o completa a nivel fake-in-process con tests actuales de CAM/Gateway/autoridad fake; no son evidencia distribuida. E11–E26 requieren ampliar pruebas o integrar adaptadores para poder declararse demostrados.

## 9. Secuencia de trabajo

1. Ejecutar CI completa después de los tests concurrentes y Gateway añadidos.
2. [x] Añadir prueba Gateway-session vs Forget race usando la frontera única.
3. [~] Se añadió replay journal → reducer → restauración del gate Forget en el fake. Falta reconstruir admisiones no terminales y conectar un journal durable.
4. [x parcial] Añadir seguridad estática: frontera única en Gateway y modelos de evidencia sin payload/hash. La auditoría de rutas reales, capacidades entre procesos y recibos de adaptadores queda pendiente.
5. Ejecutar suite y revisar los resultados por versión Python.
6. Mantener bloqueados adaptadores reales hasta resolver prerrequisitos de §7.

## 10. Criterio de salida

ME-03E no se declara completo porque pasen los tests de fakes. La fase se reporta por nivel de evidencia. El nivel adapter-integration/distributed permanece pendiente hasta que existan adaptadores reales, inventario aprobado, política de retención y pruebas de recuperación en el entorno seleccionado.


## 11. Primera integración y validación ejecutada

Se amplió la integración Gateway/CAM para comprobar que la misma instancia de `ProtectedMemoryConsistencyPort` recibe admisión, emisión, finalización y reconciliación. Se añadió además una carrera real de hilos entre una sesión Gateway y `begin_forget`: la emisión puede ganar antes del cierre o ser rechazada si el cierre gana; nunca puede emitirse una unidad posterior al cierre.

En `tests/unit/test_memory_consistency_authority.py` se añadieron tres pruebas concurrentes con barreras:
- emisión contra Forget;
- dos emisiones con la misma secuencia;
- Forget contra invalidación solapada.

En `tests/unit/test_memory_gateway_authorization_integration.py` se añadió la carrera de sesión Gateway contra Forget y la integración de emisión/finalización/reconciliación en la misma frontera.

El commit de código `a1e58b0f148cebf9e3f9c0b817b113fdd083ef4c` pasó GitHub Actions en Python 3.10, 3.11, 3.12 y 3.13. Python 3.11 reportó `Ran 366 tests`, `OK`. Workflow: [Atlas CI #43527225373](https://github.com/yon30c/atlas/actions/runs/43527225373).

**Nivel demostrado:** fake integrado y concurrencia dentro de un proceso. No demuestra orden entre procesos/nodos, durabilidad, recuperación tras reinicio ni transporte real. Siguen pendientes E11–E26 y el nivel adapter-integration/distributed.


## 12. Recuperación integrada parcial y validación actualizada

Se añadió una prueba que construye una secuencia journal válida (`READ_ADMITTED`, `FORGET_CLOSED`, fencing de endpoint, `ADMISSION_RECONCILED`, `FORGET_SUPPRESSED`), ejecuta `ConsistencyJournalReducer`, restaura el gate de un fake desde la proyección y comprueba que una nueva admisión para esa memoria se rechaza.

La prueba demuestra que la proyección reducida conserva suficiente información para reestablecer el cierre lógico de Forget en el fake. No reconstruye todos los detalles de admisiones activas, recibos externos ni operaciones de purga; tampoco prueba persistencia o recuperación tras reinicio real.

El commit de código `9ff06d402e182bb3f488ade3248ea11a087e7ad3` pasó la suite completa en Python 3.10, 3.11, 3.12 y 3.13. Python 3.11 reportó `Ran 367 tests`, `OK`. Workflow: [Atlas CI #43527488512](https://github.com/yon30c/atlas/actions/runs/43527488512).


## 13. Seguridad estática y CI actualizados

Se añadieron dos pruebas de seguridad:
- el constructor de Gateway recibe una sola frontera de consistencia y no permite inyectar autoridad/egress por separado;
- los modelos de Forget y journal no contienen campos para payload, contenido, fragmentos, embeddings ni hashes del contenido.

El commit de código `3cf9febb22fb7214f7ada30c56883606d33882e2` pasó la suite completa en Python 3.10–3.13. Python 3.11 reportó `Ran 369 tests`, `OK`. Workflow: [Atlas CI #43527681299](https://github.com/yon30c/atlas/actions/runs/43527681299).

Esta comprobación es estructural y de proceso. No sustituye una auditoría de rutas de transporte, aislamiento entre procesos, autenticidad de recibos, almacenamiento real ni seguridad distribuida.

## 14. Recuperación parcial: rechazo explícito de proyecciones incompletas

La inspección del reducer confirmó que AdmissionProjection conserva generación, revisiones, rutas, secuencias y recibos por endpoint, pero el journal actual no persiste todos los campos de ReadTarget necesarios para reconstruir una admisión viva (en particular, el scope canónico completo). Tampoco existe todavía una autoridad durable que pueda volver a validar recibos externos.

Por tanto, el fake de recuperación ahora:
- rechaza la restauración si existe cualquier admisión no terminal, en vez de descartarla y tratar el dominio como vacío;
- rechaza invalidaciones aún no reconciliadas;
- comprueba que las referencias de los cierres Forget correspondan a admisiones presentes en la proyección;
- conserva las claves de idempotencia como tombstones opacos y bloquea su reutilización;
- solo restaura gates/revisiones cuando la proyección no requiere reanudar emisores o endpoints pendientes.

Se añadieron pruebas para verificar el rechazo de una proyección con una admisión ADMITTED sin resolver y la conservación de la clave de idempotencia de Forget tras restaurar un cierre terminal.

**Límite deliberado:** esto mejora el comportamiento fail-closed del fake; no completa la recuperación de admisiones activas. El siguiente trabajo de diseño debe ampliar el sobre journalizado de READ_ADMITTED con los datos mínimos de target/scope, definir cómo se revalidan recibos y reconstruir estados de endpoint/admisión sin confiar únicamente en el reducer. El esquema actual no se considera suficiente para recuperación durable.

## 15. Validación del límite de recuperación fail-closed

El commit de pruebas `619e7d8345437f78a341b4e38d647dc836b7a912` añadió la comprobación de que una proyección con una admisión no terminal no puede restaurarse descartando esa admisión. También verifica que una clave de idempotencia de Forget sobreviva como tombstone opaco al restaurar una proyección terminal.

GitHub Actions ejecutó correctamente la matriz completa:
- Python 3.10: éxito.
- Python 3.11: éxito.
- Python 3.12: éxito.
- Python 3.13: éxito.

Workflow de pruebas: [Atlas CI #43529302568](https://github.com/yon30c/atlas/actions/runs/43529302568).

El commit documental actual `e2e2d31cb407b9deb33c401ff74bb32457e6b40c` también pasó la misma matriz: [Atlas CI #43529334129](https://github.com/yon30c/atlas/actions/runs/43529334129).

Esto valida los tests puros y el fake de proceso único. No valida recuperación durable ni reconstrucción de admisiones activas.

## 16. ME-03F — Diseño de schema v2 para recuperación exacta de admisiones

La inspección de `ConsistencyTransition`, `ConsistencyProjection` y `ReadTarget` confirmó que `READ_ADMITTED` v1 no conserva el scope canónico. El reducer no puede reconstruir `ReadTarget(memory_id, version_id, owner_id, scope)` sin inferir PRIVATE/PROJECT. Además, la proyección no conservaba el recibo terminal de la admisión como campo específico.

Se añadió `docs/design/me-03f-journal-admission-recovery-schema-design.md` con una propuesta aditiva:

- schema v2 añade `scope_kind` y `scope_project_id`, exige `owner_id`, `actor_identity_id` y `request_id`, y valida PRIVATE/PROJECT contra las revisiones canónicas;
- schema v1 sigue siendo legible para replay histórico, pero sus admisiones sin scope explícito se marcan no recuperables y no pueden restaurarse como lecturas vivas;
- la proyección conserva owner, scope, admitted_at, clasificación de recuperabilidad y recibo terminal de admisión;
- las admisiones no terminales recuperadas se mantienen unresolved/fenced; no reviven como emisores activos;
- los IDs de recibos no se consideran prueba: un verificador independiente debe validar emisor, endpoint, generación, secuencia y vínculo con la admisión;
- cualquier nueva entrega de contenido exige una autorización CAM y admisión nuevas.

La propuesta incluye 21 escenarios F01–F21 y una secuencia de implementación por etapas. No modifica contratos normativos ni código; no selecciona almacenamiento, transporte o mecanismo criptográfico. La recuperación durable y el runtime siguen bloqueados.

### 16.1 Implementación inicial del schema v2 y proyección exacta

Se implementó la primera parte de ME-03F, sin adaptadores ni activación de runtime:

- `ConsistencyTransition` acepta schema v1 y v2; schema v2 se limita a `READ_ADMITTED`.
- v1 conserva su allowlist y semántica histórica; no puede incluir los campos de scope v2.
- v2 añade `scope_kind` y `scope_project_id`, exige owner, actor y request, y valida las combinaciones PRIVATE/PROJECT contra las revisiones de autorización.
- `AdmissionProjection` conserva owner, scope, instante de admisión, marca explícita de recuperabilidad y recibo terminal de admisión.
- `reconstruct_read_target()` reconstruye el `ReadTarget` exacto solo desde una proyección v2 válida. Para v1 o datos incompletos devuelve `None`; no infiere el scope.

Pruebas nuevas:
- `tests/unit/test_memory_journal_schema_v2.py`: 12 casos de validación y compatibilidad.
- `tests/unit/test_memory_journal_recovery_projection_v2.py`: 7 casos de proyección, reconstrucción PRIVATE/PROJECT, rechazo de inferencia v1 y recibo terminal.

CI de la reconstrucción exacta: [Atlas CI #43529942908](https://github.com/yon30c/atlas/actions/runs/43529942908), Python 3.10, 3.11, 3.12 y 3.13: éxito.

**Pendiente:** clasificar y recuperar estados de endpoint con verificación independiente de recibos. La reconstrucción de `ReadTarget` no crea una sesión de lectura, no autoriza contenido y no reactiva emisores antiguos. No se ha implementado recuperación distribuida ni persistencia durable.

## 17. ME-03G — Verificación independiente de recibos terminales

Se implementó la frontera tipada para verificar recibos terminales sin confundir una referencia del journal con prueba de que un endpoint terminó o fue cercado.

Componentes:
- `src/atlas/memory/receipt_verification.py`: solicitudes cerradas por tipo, resultados VERIFIED/REJECTED/UNAVAILABLE, recibos atestados y comparación exacta de todos los campos.
- `src/atlas/ports/terminal_receipt_verifier.py`: puerto cuya implementación resuelve emisores confiables desde su propia configuración; el journal no elige el emisor confiable.
- `src/atlas/memory/terminal_recovery.py`: valida admisiones terminales solo después de verificar individualmente todos los recibos de endpoints y el recibo terminal de la admisión.
- `journal_reducer.py`: ahora conserva operación, generación y secuencia final exactas de cada endpoint, además de la operación/generación del recibo terminal de admisión.

Los recibos de fencing vinculan la generación anterior con la nueva. Las finalizaciones vinculan la secuencia final. Se exige que la lista de endpoints coincida exactamente con las rutas persistidas. Recibos ausentes, no confiables, rechazados, ambiguos, contradictorios o con campos diferentes dejan la recuperación sin evidencia aceptada.

Pruebas:
- 22 casos en `tests/unit/test_memory_terminal_receipt_verification.py`.
- Pruebas de proyección ampliadas en `tests/unit/test_memory_journal_recovery_projection_v2.py`.
- CI [#43530661316](https://github.com/yon30c/atlas/actions/runs/43530661316): Python 3.10–3.13, todos exitosos.

**Límite:** la implementación no verifica firmas criptográficas ni contacta endpoints reales. Tampoco restaura admisiones no terminales. La evidencia verificada no es una capacidad de lectura ni una autorización CAM. La siguiente etapa es recuperar las admisiones pendientes como UNRESOLVED, mantener cerrado el gate y exigir fencing real de todos los endpoints con generación nueva y recibos verificados.

## 18. ME-03H — Recuperación de admisiones pendientes y fencing tras reinicio

Se añadió `docs/design/me-03h-unresolved-admission-recovery-design.md` y una implementación incremental del modelo de recuperación.

### Modelo y coordinación de fencing

- `src/atlas/memory/recovery.py` conserva todas las admisiones no terminales, tanto v1 como v2, con inventario exacto de endpoints y última secuencia comprometida.
- Las admisiones v2 pueden reconstruir un `ReadTarget` solo como metadato; las v1 mantienen `target=None`, sin inferencia de scope.
- El plan exige una generación estrictamente superior a todas las generaciones previas de admisiones, Forget e invalidaciones.
- Cada endpoint recibe una solicitud de fencing ligada a dominio, época, operación, admisión, endpoint, generación anterior/nueva y última secuencia comprometida.
- Cada recibo se verifica mediante el puerto ME-03G. Se agregó `fenced_through_sequence` al recibo terminal para probar que el endpoint cercó también toda la secuencia ya comprometida.
- El lote solo se considera verificado cuando todos los endpoints de todas las admisiones pendientes están cercados y verificados. Resultados parciales o ambiguos no producen un lote aceptado.

### Journal y reducer

Se agregaron `RECOVERY_CLOSED` y `RECOVERY_RECONCILED`:
- `RECOVERY_CLOSED` exige el inventario exacto de todas las admisiones y rutas no terminales y avanza la generación.
- El reducer marca las admisiones capturadas como UNRESOLVED.
- Mientras la recuperación siga pendiente, rechaza nuevas admisiones y cualquier egress.
- `ENDPOINT_FENCED` solo acepta el operation ID exacto y la generación nueva de recuperación.
- `ADMISSION_RECONCILED` requiere que todos los endpoints de esa admisión estén terminales.
- `RECOVERY_RECONCILED` exige que todas las admisiones afectadas estén terminales antes de cerrar la recuperación.

### Validación

- 25 pruebas en `tests/unit/test_memory_unresolved_admission_recovery.py`.
- Se amplió el fake de autoridad en `tests/unit/test_memory_consistency_authority.py`: tras restaurar una admisión pendiente, el emisor de generación antigua no puede entregar, nuevas lecturas permanecen bloqueadas y solo se admite una lectura nueva después de confirmar el fencing de todos los endpoints.
- CI [#43532495188](https://github.com/yon30c/atlas/actions/runs/43532495188): Python 3.10, 3.11, 3.12 y 3.13, todos exitosos.

**Límite vigente:** esto valida modelos, reducer y fakes. No existe todavía un coordinador durable que confirme `RECOVERY_CLOSED` antes de contactar endpoints y que escriba de forma atómica todos los recibos verificados, las reconciliaciones y el cierre final. No hay fencing real de procesos/transporte ni recuperación distribuida demostrada. No habilitar producción.
