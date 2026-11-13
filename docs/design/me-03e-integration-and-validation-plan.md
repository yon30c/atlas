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

La integración actual cubre lectura CAM → Gateway → fake de consistencia → egress → finalización → reconciliación. Las carreras Gateway/Forget se validan actualmente en la autoridad fake; el siguiente paso es unir esa carrera a una sesión Gateway real de prueba.

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

E01–E10 tienen cobertura parcial con tests actuales de CAM/Gateway/autoridad fake. E11–E26 requieren ampliar pruebas o integrar adaptadores para poder declararse demostrados.

## 9. Secuencia de trabajo

1. Ejecutar CI completa después de los tests concurrentes y Gateway añadidos.
2. Añadir prueba Gateway-session vs Forget race usando la frontera única.
3. Añadir recuperación integrada journal → reducer → autoridad fake, sin checkpoint no verificado.
4. Añadir seguridad: rutas de contenido, capacidades, recibos, ids y payload ausentes.
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
