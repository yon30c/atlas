# ME-03D — Forget Coordinator y eliminación verificable

**Estado:** diseño técnico para implementación incremental  
**Rama:** `implementation/me-01-to-me-04-memory-engine`  
**Dependencias:** CT-03, CT-05, CT-08; DM-01; ME-03; ME-03B; ME-03C.  
**No objetivos:** elección de base de datos, inventario real de producción, adaptadores de almacenamiento, políticas de retención no aprobadas, despliegue, SecurityAudit completo o ejecución de eliminación física en esta etapa.

## 1. Propósito

ME-03D define la orquestación completa de Forget sin confundir sus hitos:

1. solicitud autorizada por decisión directa del propietario;
2. cierre de nuevas admisiones y fencing de lecturas previas;
3. supresión lógica confirmada;
4. inventario completo y estable de destinos;
5. eliminación en cada destino;
6. verificación independiente de ausencia en cada destino;
7. actualización canónica de versiones a `forgotten`;
8. conservación de la marca mínima que impide restauración/reaparición.

El estado `SUPPRESSED` significa únicamente que las rutas protegidas ya no pueden entregar contenido. No significa eliminación física ni permite marcar versiones `forgotten`.

## 2. Reglas normativas que no se pueden relajar

- Forget requiere decisión directa, explícita y no delegable del propietario, verificada por CAM y evidencia confiable de un solo uso.
- `MemoryGateway` y CAM son obligatorios. Una solicitud no equivale a operación completada.
- La supresión lógica debe bloquear de inmediato las rutas ordinarias de lectura, índices, búsquedas, cachés, exportaciones y recuperación.
- El registro de supresión conserva solo identificadores opacos/metadatos mínimos; no contenido ni hashes vulnerables a diccionario.
- Deben cubrirse todos los destinos donde persista o pueda derivarse el contenido.
- Destino desconocido, no disponible, no inspeccionable o no verificable impide completar Forget.
- `forgotten` solo se asigna después de verificar ausencia en todos los destinos aplicables.
- Restauración, reindexación, replicación e importación consultan la supresión antes de exponer datos.
- Backups y retención siguen siendo decisiones pendientes; mientras no exista una política verificable para ellos, no se puede declarar Forget completado si pueden conservar el contenido.

Referencias: `docs/contracts/memory.md` §9.1–§9.6, CT-05, DM-01 §§4.3–4.4 y 9.3.8–9.3.9.

## 3. Decisión ME-03D-01 — Máquina de estados monotónica

El Forget Coordinator administra una operación por `operation_id` e idempotency key. Estados:

| Estado | Significado | ¿Permite nuevas lecturas de la memoria? |
|---|---|---:|
| CLOSING | Gate cerrado; se drenan/fencean admisiones anteriores. | No |
| SUPPRESSED | Todas las admisiones anteriores son terminales y todas las rutas están cercadas/completadas. | No |
| INVENTORY_PENDING | Se está obteniendo/verificando inventario de persistencia. | No |
| PURGING | Se ejecutan intentos de eliminación idempotentes por destino. | No |
| VERIFYING | Se comprueba ausencia en todos los destinos del inventario. | No |
| BLOCKED | Falta evidencia, un destino falla, cambia el inventario o existe contradicción. | No |
| COMPLETED | Todos los destinos están verificados ausentes y el estado canónico fue actualizado a forgotten. | No; el tombstone sigue bloqueando |

No existe transición hacia atrás que reabra la memoria. `BLOCKED` conserva el último hito alcanzado y permite reintentar la misma operación cuando la causa se resuelva. `COMPLETED` es terminal.

`REQUESTED` no es un estado operativo de Forget: antes de crear una operación se verifica identidad, propiedad, recurso exacto y decisión directa del propietario. Si CAM no devuelve una autorización verificada/consumida, no se crea cierre ni se toca el inventario.

## 4. Decisión ME-03D-02 — Separación entre consistencia y persistencia

El Coordinator usa dos fronteras distintas con responsabilidades explícitas:

### 4.1 ProtectedMemoryConsistencyPort

- `begin_forget` cierra atómicamente admisiones y avanza fencing respecto de nuevas admisiones y emisiones.
- `reconcile_forget` solo llega a SUPPRESSED cuando todas las admisiones afectadas y endpoints están terminalmente resueltos.
- Mantiene la supresión vigente durante purga, verificación, fallos y recuperación.
- No declara eliminación física ni cambia MemoryVersion a forgotten.

### 4.2 Forget destination boundary

Una futura frontera de inventario/eliminación:
- devuelve el inventario autoritativo y versionado de destinos;
- permite ejecutar eliminación idempotente por destino;
- entrega recibos correlacionados por operación/destino/revisión de inventario;
- permite consultar y verificar ausencia de forma independiente;
- permite comprobar si el inventario cambió durante el proceso.

Esta frontera no autoriza Forget ni puede abrir rutas. La autorización proviene de CAM y el cierre lógico de la autoridad de consistencia.

## 5. Decisión ME-03D-03 — Inventario completo, versionado y estable

El inventario cubre, cuando existan, los destinos establecidos por CT-05 y ME-03:

- almacenamiento primario;
- versiones y copias históricas;
- índices de búsqueda y estructuras derivadas;
- embeddings e índices vectoriales;
- cachés;
- réplicas;
- backups;
- exportaciones y copias operativas;
- fuentes de restauración, reindexación, replicación e importación.

No se presupone que todas estas clases estén desplegadas. La ausencia de una clase debe quedar acreditada por el inventario autoritativo, no inferida por el Coordinator.

Cada destino se identifica con un ID opaco estable y una clase cerrada. El inventario lleva una revisión/versión y una atestación de cobertura del responsable lógico. No incluye contenido, fragmentos ni hashes.

El Coordinator fija una revisión de inventario para la operación. Antes de completar:
1. consulta todos los destinos de esa revisión;
2. obtiene eliminación y verificación para cada uno;
3. vuelve a comprobar que la revisión de inventario sigue siendo vigente;
4. si el inventario cambió, incorpora los nuevos destinos y repite la purga/verificación necesaria;
5. si no puede demostrar estabilidad o cobertura, queda BLOCKED.

Una respuesta vacía no demuestra que no existan destinos, salvo que la fuente de inventario confiable atestigüe explícitamente inventario completo y vacío.

## 6. Decisión ME-03D-04 — Eliminación y verificación son evidencias distintas

Por cada destino se conservan dos hechos separados:

**DeletionAttempt / DeletionReceipt**
- operación Forget;
- destino opaco;
- revisión de inventario;
- ID de intento idempotente;
- resultado de la solicitud de eliminación (aceptada, ya ausente, rechazada o desconocida);
- referencia opaca del recibo.

**AbsenceVerification / VerificationReceipt**
- operación Forget;
- destino opaco;
- revisión de inventario;
- ID de verificación;
- resultado (ABSENT, PRESENT, UNAVAILABLE, INDETERMINATE);
- referencia opaca de evidencia.

Una respuesta HTTP exitosa, un ACK de borrado, un timeout o un proceso que terminó no demuestran ausencia. Solo una verificación autoritativa ABSENT para el destino y revisión exactos cuenta como evidencia de eliminación verificada. PRESENT, UNAVAILABLE, INDETERMINATE, evidencia contradictoria o falta de recibo mantienen BLOCKED.

Los recibos no contienen payload, nombre de archivo privado, contenido, fragmentos ni hashes del contenido eliminado.

## 7. Decisión ME-03D-05 — Reintentos e idempotencia

- Una idempotency key crea como máximo una operación Forget para el mismo objetivo.
- La misma clave con objetivo distinto se rechaza.
- Los reintentos reutilizan el mismo `operation_id`, inventario y attempt ID cuando consultan el mismo intento; no crean una operación paralela.
- Un resultado ambiguo se reconcilia consultando el recibo/estado del destino antes de emitir otro intento.
- No se interpreta timeout como ausencia ni como fallo seguro de eliminación.
- Una verificación ABSENT es válida solo para el destino y revisión exactos; un cambio de inventario obliga a cubrir el nuevo alcance.

## 8. Decisión ME-03D-06 — Actualización canónica final

Solo después de que:
- el estado sea SUPPRESSED;
- exista inventario completo y estable;
- cada destino tenga evidencia ABSENT para la revisión vigente;
- no existan operaciones o recibos ambiguos;

el Coordinator solicita a la frontera canónica que marque de forma atómica todas las versiones y elementos lógicos afectados como `forgotten`. La operación debe ser idempotente y condicionada a la revisión canónica esperada.

Si la actualización canónica falla o es ambigua:
- el gate permanece cerrado;
- no se comunica COMPLETED;
- la recuperación reconcilia la transacción/estado canónico antes de repetir;
- no se crea un nuevo Forget.

`COMPLETED` se registra únicamente después de confirmar esa actualización y conservar el tombstone mínimo de supresión.

## 9. Decisión ME-03D-07 — Tombstone y protección contra resurrección

La supresión mínima persiste después de COMPLETED para que restauraciones, backups, importaciones, replicación y reindexación no revivan la memoria.

El tombstone contiene únicamente lo necesario para identificar el objetivo lógico, la generación/época de supresión, el estado terminal y la referencia opaca de operación. No conserva contenido, texto derivado, nombre privado ni hash de contenido.

La duración/retención del tombstone y de la evidencia operativa requiere una política explícita. No se elimina ni se compacta mientras pueda existir una fuente de restauración que lo necesite; tampoco se decide aquí un plazo legal o técnico no aprobado.

## 10. Recuperación tras caída

Antes de reabrir tráfico, Atlas restaura primero:
1. cierres/generaciones de la autoridad de consistencia;
2. operaciones Forget y su estado monotónico;
3. inventario/revisión de destinos y recibos conocidos;
4. intentos de eliminación y verificaciones pendientes;
5. estado canónico de versiones/tombstone.

La recuperación no infiere que una operación se completó por ausencia de proceso, timeout o falta de registro local. Si journal, inventario, recibos o estado canónico no coinciden, mantiene BLOCKED y las rutas cerradas.

Un checkpoint sin proyección base verificada no puede usarse como estado inicial. El reducer ME-03C debe validar el journal; la continuidad/anti-rollback y la autenticidad del inventario/recibos dependen de fuentes confiables aún no implementadas.

## 11. Contratos/puertos futuros (sin adaptadores en esta fase)

Dirección conceptual:

- `ForgetDestinationInventoryPort.snapshot(target, operation_id)` → inventario verificado, revisión y cobertura.
- `ForgetDestinationDeletionPort.delete(destination, operation_id, inventory_revision, attempt_id)` → recibo de intento.
- `ForgetDestinationVerificationPort.verify_absent(destination, operation_id, inventory_revision, verification_id)` → recibo de verificación.
- `ForgetCanonicalStatePort.mark_forgotten(target, expected_revision, operation_id)` → confirmación idempotente de actualización canónica.
- `ForgetOperationJournalPort` registra estados, inventario opaco, recibos y verificaciones mediante journal append-only.

Los nombres expresan responsabilidades y no fijan todavía firmas finales, storage ni transporte. El único puerto ya existente que se conserva como contrato actual es `ProtectedMemoryConsistencyPort` para el cierre lógico.

## 12. Pruebas de aceptación propuestas

| ID | Escenario | Resultado |
|---|---|---|
| D01 | Falta autorización directa del propietario | No se crea operación ni cierre. |
| D02 | Decisión delegada o prueba reutilizada | DENY; no se inicia Forget. |
| D03 | memory_id/owner no coincide con metadatos canónicos | DENY. |
| D04 | Reintento con misma idempotency key/objetivo | Devuelve la misma operación. |
| D05 | Admisión concurrente con Forget | Un único orden; admisión posterior al cierre denegada. |
| D06 | Lectura previa sin terminalidad | CLOSING; no SUPPRESSED. |
| D07 | Todas las admisiones/endpoints terminales | Puede avanzar a SUPPRESSED. |
| D08 | Timeout de endpoint | Sigue CLOSING/BLOCKED; nunca se interpreta como cancelación. |
| D09 | Destino no inventariado/desconocido | BLOCKED. |
| D10 | Inventario no atestigua completitud | BLOCKED. |
| D11 | Inventario cambia durante purga | Añadir alcance nuevo y repetir verificación. |
| D12 | ACK de eliminación sin verificación | No COMPLETED. |
| D13 | Verificación ABSENT en todos los destinos | Avanza a actualización canónica. |
| D14 | Destino PRESENT | BLOCKED. |
| D15 | Destino UNAVAILABLE/INDETERMINATE | BLOCKED. |
| D16 | Reintento de eliminación ambiguo | Consultar intento existente; no duplicar operación. |
| D17 | Recibos contradictorios | BLOCKED/cuarentena. |
| D18 | Backup/retención sin política verificable | No COMPLETED. |
| D19 | Estado canónico cambia antes de verificación completa | Rechazado; no marcar forgotten. |
| D20 | Todas las versiones se marcan forgotten | Actualización canónica atómica. |
| D21 | Restauración con tombstone existente | Contenido permanece suprimido. |
| D22 | Reindexación/importación sin consulta de supresión | Publicación bloqueada. |
| D23 | Caída durante purga | Recupera cierre y recibos; rutas cerradas. |
| D24 | Evidencia de Forget | No contiene contenido ni hashes. |
| D25 | Inventario vacío sin atestación | BLOCKED. |
| D26 | Operación COMPLETED repetida | Idempotente; no revierte estado. |
| D27 | Mismo idempotency key con otra memoria | Conflicto; no nueva operación. |
| D28 | Falla actualización canónica tras ABSENT | BLOCKED; gate sigue cerrado. |
| D29 | Tombstone eliminado mientras existe backup recuperable | Prohibido. |
| D30 | Forget de una memoria con múltiples versiones/propuestas | Alcance completo y exacto; no omitir subrecursos. |

Las pruebas D01–D37 serán inicialmente pruebas puras/fakes. No demuestran eliminación real ni inventario de producción.

## 13. Límites pendientes explícitos

- No hay inventario real de destinos.
- La política de retención y backups sigue pendiente.
- No existe implementación de firma/validación de inventario ni recibos de destinos reales.
- No hay adaptadores de eliminación/verificación.
- No existe transacción durable del Coordinator.
- No se ha probado concurrencia distribuida, crash recovery real ni anti-rollback.
- No se marca ninguna MemoryVersion como forgotten desde este diseño.
- No se declara ningún Forget completado.

## 14. Secuencia de implementación

1. Añadir modelos puros para estados de operación, inventario, intentos y recibos de verificación.
2. Añadir reducer/validador de estados monotónicos del Coordinator.
3. Definir puertos tipados para inventario, eliminación, verificación y estado canónico.
4. Integrar con `ProtectedMemoryConsistencyPort` sin crear una segunda autoridad de admisión/fencing.
5. Implementar fakes deterministas y D01–D37.
6. Revisar la política pendiente de backups/retención antes de cualquier adaptador real.
7. No elegir storage ni desplegar; no declarar Forget físico completo sin destinos reales y evidencia.

## 15. Criterios de salida

ME-03D solo puede declararse completo como diseño/modelos cuando:
- las transiciones son monotónicas y fail-closed;
- SUPPRESSED y COMPLETED no se confunden;
- cada destino exige intento y verificación separados;
- el inventario es completo, versionado y estable;
- tombstones e idempotencia sobreviven recuperación;
- D01–D37 están representados y ejecutados;
- el diseño mantiene explícitos los límites de backups/retención.

La implementación real de Forget seguirá pendiente hasta disponer de inventario aprobado, política de backups/retención, adaptadores verificables y pruebas de recuperación.


## 16. Implementación parcial y validación

Se implementó una primera capa pura en `src/atlas/memory/forget_coordinator.py`:

- estados monotónicos CLOSING, SUPPRESSED, INVENTORY_PENDING, PURGING, VERIFYING, BLOCKED y COMPLETED;
- inventario de destinos versionado y con atestación de cobertura;
- clases cerradas de destinos, resultados de eliminación y resultados de verificación;
- intentos idempotentes y reconciliación explícita de resultados UNKNOWN;
- verificación ABSENT separada del ACK de eliminación;
- gate de política de retención cuando el inventario incluye BACKUP/RESTORE_SOURCE;
- actualización canónica y tombstone obligatorios antes de COMPLETED;
- inventario nuevo no puede retroceder ni omitir destinos anteriores sin evidencia de retiro;
- reintentos de COMPLETED son idempotentes y no reabren la memoria;
- inventario y recibo canónico quedan ligados a la operación/objetivo exactos;
- el recibo canónico valida expected_revision y new_revision;
- destino estable no puede cambiar de clase entre revisiones;
- intentos UNKNOWN deben reconciliarse antes de refresh o reintento.

Se exportaron los modelos desde `atlas.memory` y se añadieron 37 métodos de prueba D01–D37 en `tests/unit/test_memory_forget_coordinator.py`.

En el commit `49244706a3f93f09ec7b1f2b7e350124b2715216`, GitHub Actions ejecutó la suite completa: Python 3.10, 3.11, 3.12 y 3.13 finalizaron correctamente. Python 3.11 reportó `Ran 360 tests`, `OK`. Workflow: [Atlas CI #43526491006](https://github.com/yon30c/atlas/actions/runs/43526491006).

**Alcance de esa validación:** modelos, reducer puro y fakes. No demuestra inventario real, retención/backups aprobados, eliminación física, verificación contra almacenes reales, transacciones durables, recuperación distribuida ni Forget completado. No se han añadido adaptadores ni se ha marcado ninguna memoria/version como forgotten.


## Decisión posterior — Trust Anchor opcional y límite de restauración

**APROBADO — 13 de noviembre de 2026.** El Trust Anchor externo es opcional y su implementación queda postergada hasta la etapa final de Atlas. El perfil local no puede demostrar que un backup restaurado sea posterior a un Forget ya completado ni que su registro local de supresión sea el más reciente.

Por tanto, la regla de conservar una marca mínima que impida la reaparición requiere una fuente de supresión/continuidad independiente del backup restaurado o una reconciliación explícita aprobada. Si esa fuente no está disponible, una restauración que pueda contener datos anteriores al Forget no puede exponerse ni declararse segura. La opcionalidad de Trust Anchor no autoriza a relajar el requisito de no reintroducir memorias olvidadas; la garantía permanece pendiente/bloqueante para ese escenario hasta contar con un mecanismo verificable.
