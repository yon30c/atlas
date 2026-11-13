# ME-03C — Journal cerrado, reducer y recuperación semántica

**Estado:** diseño para implementación incremental  
**Rama:** `implementation/me-01-to-me-04-memory-engine`  
**Dependencias:** CT-03, CT-05, CT-08; DM-01; ME-03; ME-03B; `me-03-durable-consistency-journal-design.md`.  
**No objetivos:** adaptador durable, elección de motor/DB, algoritmo criptográfico, watermark externo, despliegue, endpoint real o finalización física de Forget.

## 1. Propósito

Los modelos iniciales del journal ya validan tipos, campos obligatorios, IDs, UTC, schema version 1, secuencias contiguas y unicidad de record IDs dentro del tramo recuperado. Eso no basta para reconstruir un estado seguro: un registro puede tener campos válidos individualmente y aun así ser incompatible con su tipo o contradecir transiciones anteriores.

ME-03C define tres capas separadas:

1. **Sobre cerrado:** cada tipo de transición acepta solo los campos explícitamente autorizados para ese tipo.
2. **Validador semántico/reducer puro:** reproduce las transiciones en orden y rechaza relaciones imposibles o contradictorias.
3. **Frontera de recuperación:** distingue integridad estructural de autenticidad/continuidad confiable. Un reducer correcto no autentica por sí mismo el origen del journal.

## 2. Decisiones

### ME-03C-01 — Allowlist por tipo de registro

Cada `ConsistencyRecordKind` tendrá un conjunto cerrado de campos permitidos. Un campo no aplicable debe permanecer ausente/None (o vacío solo para colecciones definidas expresamente). No se aceptan campos sobrantes por conveniencia ni mapas arbitrarios.

Campos comunes: `record_id`, `schema_version`, `record_kind`, `operation_id`, `occurred_at`. Los demás se permiten únicamente según el catálogo de §3.

### ME-03C-02 — Transiciones correlacionadas exactas

El reducer exige que cada operación use IDs y relaciones coherentes:
- `READ_ADMITTED` crea una admisión única y `operation_id == read:{admission_id}`.
- `READ_ACTIVATED`, egress, finalización, fencing y reconciliación deben referirse a esa admisión y a su generación exacta.
- Cada endpoint debe pertenecer al inventario de rutas de la admisión.
- Cada emisión debe tener secuencia positiva y única por endpoint; la secuencia no puede retroceder ni duplicarse con otro recibo.
- Los recibos deben ser únicos y correlacionados con el hecho que prueban.
- No se admiten emisiones después de finalización/fencing/reconciliación terminal.
- La admisión no se resuelve como COMPLETED/CANCELLED sin evidencia terminal consistente de todos sus endpoints.

### ME-03C-03 — Cierres e invalidaciones son monotónicos

- `FORGET_CLOSED` bloquea admisiones posteriores para esa memoria; el cierre nunca se revierte mediante replay.
- `FORGET_SUPPRESSED` solo se acepta cuando todas las admisiones capturadas por el cierre están terminalmente resueltas y la cobertura de rutas coincide.
- Una invalidación exige autoridad, ID, generación y revisión exactos; la nueva revisión es estrictamente mayor que la anterior.
- `INVALIDATION_RECONCILED` solo se acepta después de verificar todas las admisiones/rutas afectadas.
- Una segunda operación incompatible o un cierre duplicado con distinta solicitud es contradicción, no una oportunidad de elegir una versión.

### ME-03C-04 — Reducer determinista y puro

El reducer consume un `ConsistencyRecoveryState` estructuralmente válido y devuelve una proyección inmutable, o falla con `ContractError`. No accede a red, reloj, DB, endpoints, memoria ni identidad.

La proyección conserva únicamente metadatos opacos necesarios para:
- admisiones y estado;
- tombstones de idempotencia (clave, operación y registro), sin payload de solicitud;
- inventario de endpoints y últimas secuencias;
- recibos y operaciones ya aplicadas;
- cierres Forget e invalidaciones activos/terminales;
- generación/revisión máxima observada.

El reducer no emite permisos, no reabre rutas y no confirma que un endpoint real haya aplicado fencing.

### ME-03C-05 — Sin recuperación optimista

Cualquier transición desconocida, fuera de orden, duplicada contradictoriamente, con referencia faltante, inventario incompleto o relación imposible invalida la proyección completa del dominio afectado. No se devuelve una proyección parcial que pueda confundirse con estado operativo válido.

### ME-03C-06 — Checkpoint no sustituye la continuidad confiable

La validación estructural de un checkpoint y sus entradas no prueba autenticidad, anti-rollback ni que la fuente haya entregado el último estado confirmado. `continuity_reference` es una referencia opaca, no una prueba criptográfica por sí misma. Como `ConsistencyRecoveryState` aún no incluye una proyección base decodificada/verificada del checkpoint, el reducer rechaza cualquier recuperación con checkpoint en lugar de reproducir únicamente las entradas posteriores como si el historial anterior estuviera vacío.

La autoridad solo puede reabrir el dominio después de validar el resultado del reducer y obtener una verificación de continuidad/anti-rollback desde una fuente confiable definida por la futura implementación. ME-03C no inventa ni implementa esa fuente.

## 3. Matriz cerrada de campos por transición

Además de los cinco campos comunes, el diseño limita campos así:

| Tipo | Campos específicos permitidos |
|---|---|
| READ_ADMITTED | idempotency_key, request_id, correlation_id, actor_identity_id, subject_user_id, owner_id, memory_id, version_id, snapshot_id, revisions, admission_id, generation, route_ids |
| READ_ACTIVATED | admission_id, generation |
| EGRESS_COMMITTED | admission_id, endpoint_id, generation, emission_id, emission_sequence, receipt_id |
| ENDPOINT_COMPLETED | admission_id, endpoint_id, generation, receipt_id, final_sequence |
| ENDPOINT_FENCED | admission_id, endpoint_id, generation, receipt_id |
| FORGET_CLOSED | idempotency_key, request_id, correlation_id, actor_identity_id, subject_user_id, owner_id, memory_id, generation, proof_reference, route_ids, affected_admission_ids |
| INVALIDATION_CLOSED | authority_kind, authority_id, generation, previous_revision, new_revision, route_ids, affected_admission_ids |
| ADMISSION_RECONCILED | admission_id, generation, receipt_id, admission_terminal_status |
| FORGET_SUPPRESSED | memory_id, generation, route_ids, affected_admission_ids |
| INVALIDATION_RECONCILED | authority_kind, authority_id, generation, route_ids, affected_admission_ids |
| CHECKPOINT_COMMITTED | checkpoint_reference |

Colecciones vacías solo se aceptan cuando el tipo permite inventario vacío y ambos conjuntos de rutas/admisiones están vacíos. Los tipos de transición no admiten campos de contenido, hashes, payload, fragmentos ni campos arbitrarios.

## 4. Reglas del reducer

### 4.1 Admisión y entrega

- `READ_ADMITTED` crea el estado inicial ADMITTED.
- `READ_ACTIVATED` es opcional solo si el flujo no necesita persistir ACTIVE por separado; si aparece, debe ser la única activación de una admisión ADMITTED.
- Egress requiere admisión conocida, endpoint incluido y generación exacta.
- Secuencias por endpoint son estrictamente crecientes. El contrato del endpoint determina si deben ser contiguas; el reducer no inventará contigüidad si el contrato de emisión permite secuencias no consecutivas.
- `ENDPOINT_COMPLETED` requiere que `final_sequence` no sea menor que la última secuencia comprometida. No puede aparecer otra emisión para ese endpoint después.
- `ENDPOINT_FENCED.generation` identifica la nueva generación de fencing de la operación de cierre, y debe coincidir con `FORGET_CLOSED.generation` o `INVALIDATION_CLOSED.generation`; no con la generación original de la admisión. `ENDPOINT_COMPLETED.generation` coincide con la generación de la operación que emite el recibo (lectura normal o cierre). `ADMISSION_RECONCILED.generation` identifica la generación original de la admisión.
- `ADMISSION_RECONCILED` solo puede ser terminal una vez y cuando todos los endpoints estén COMPLETED para resultado COMPLETED o FENCED para resultado CANCELLED.

### 4.2 Forget

- `FORGET_CLOSED` captura el conjunto exacto de admisiones previas para una memoria y el conjunto unión de sus rutas. La fuente de la captura es el estado replayado, no una lista declarada que pueda omitir admisiones conocidas.
- Todas las admisiones capturadas deben tener generación anterior al nuevo fencing.
- Ninguna nueva admisión para la memoria puede aparecer después del cierre.
- `FORGET_SUPPRESSED` debe referenciar el mismo alcance, generación, admisiones y rutas; solo se acepta si cada admisión capturada está terminalmente resuelta.
- SUPPRESSED es supresión lógica; no cambia MemoryVersion a FORGOTTEN ni afirma purga física.

### 4.3 Invalidación

- La transición debe identificar la autoridad y revisión anterior/nueva.
- Las admisiones afectadas se derivan del snapshot de revisiones replayado; la lista declarada debe coincidir exactamente.
- El cierre invalida la generación/revisión anterior para todas las admisiones del alcance.
- `INVALIDATION_RECONCILED` solo termina cuando todas las admisiones/endpoints del inventario están resueltos y las referencias coinciden.

## 5. Modelos de proyección

La implementación añade modelos inmutables y sin payload para la proyección reducida:
- estado de endpoint (última secuencia, recibos, COMPLETED/FENCED/UNRESOLVED);
- estado de admisión (target, generación, rutas, estado);
- estado de cierre Forget e invalidación;
- tombstones de idempotencia (clave, operación y registro);
- proyección del dominio (dominio, época, posición, admisiones, cierres, invalidaciones y tombstones).

Las colecciones se exponen como tuplas ordenadas o frozensets, nunca como diccionarios mutables. El reducer no conservará el contenido ni hashes.

## 6. Integridad estructural frente a confianza

Se mantienen separados estos resultados:

- **Estructuralmente válido:** IDs, tipos, allowlists, posiciones, unicidad y transiciones coherentes.
- **Continuidad verificada:** la fuente confiable demuestra que el checkpoint y el head corresponden al último estado no revertido.
- **Endpoint reconciliado:** el endpoint real acredita su estado por recibo consultable/fencing verificable.

Solo la conjunción de las pruebas aplicables permite que la futura autoridad reabra rutas. Ningún constructor de dataclass ni reducer puede elevar un estado estructural a continuidad verificada.

## 7. Pruebas nuevas propuestas

Se amplía C45–C64 con escenarios ME-03C:

| ID | Escenario | Resultado |
|---|---|---|
| C65 | Campo de otro tipo de transición | Rechazo por allowlist. |
| C66 | READ_ACTIVATED sin READ_ADMITTED | Rechazo semántico. |
| C67 | READ_ADMITTED duplicada con ID distinto o repetido | Rechazo de duplicidad/operación contradictoria. |
| C68 | Egress para endpoint no inventariado | Rechazo. |
| C69 | Egress después de ENDPOINT_COMPLETED/FENCED | Rechazo. |
| C70 | Secuencia de emisión duplicada con recibo distinto | Rechazo. |
| C71 | ENDPOINT_COMPLETED con final_sequence menor que emisión comprometida | Rechazo. |
| C72 | ADMISSION_RECONCILED antes de resolver todos los endpoints | Rechazo. |
| C73 | FORGET_CLOSED omite admisión previa conocida | Rechazo. |
| C74 | READ_ADMITTED posterior a FORGET_CLOSED | Rechazo. |
| C75 | FORGET_SUPPRESSED con admisión no terminal | Rechazo. |
| C76 | INVALIDATION_CLOSED con inventario que no coincide con revisiones | Rechazo. |
| C77 | INVALIDATION_RECONCILED con endpoint pendiente | Rechazo. |
| C78 | receipt_id repetido en dos registros distintos | Rechazo; el replay idempotente se resuelve en append mediante idempotency_key, antes de duplicar el evento en el journal. |
| C79 | Mismo receipt_id correlacionado a otro hecho | Rechazo. |
| C80 | Checkpoint con dominio/época/posición inconsistente | Rechazo estructural. |
| C81 | continuity_reference presente pero sin verificador confiable | No elevar a continuidad verificada. |
| C82 | Registro desconocido o futuro | Cuarentena completa del dominio. |
| C83 | Transición terminal repetida con resultado distinto | Rechazo. |
| C84 | ENDPOINT_FENCED usa generación distinta a la del cierre exacto | Rechazo; no inferir ni corregir la generación del recibo. |
| C85 | Checkpoint con referencia pero sin proyección base reconstruida | Reducer falla cerrado; no asume que el estado previo está vacío. |
| C86 | Reutilización de idempotency_key en otra operación | Rechazo por conflicto. |
| C87 | Recuperación con clave de idempotencia vigente | La proyección conserva el tombstone opaco para impedir replay.

Los escenarios C65–C87 se implementarán inicialmente como pruebas puras del validador/reducer y fakes. No prueban persistencia durable, anti-rollback criptográfico ni endpoints reales.

## 8. Secuencia de implementación

1. Cerrar el esquema de campos por tipo en `ConsistencyTransition`.
2. Reforzar invariantes estructurales de `JournalEntry`, `ConsistencyCheckpoint` y `ConsistencyRecoveryState`.
3. Añadir proyección inmutable y reducer determinista.
4. Añadir C65–C87 sin borrar ni rebajar C45–C64.
5. Revisar compatibilidad de los fakes existentes y actualizar el contrato del journal.
6. Revisar diff/refs y estado CI. Sin DB, adaptadores, despliegue, PR ni merge.

## 9. Criterios de salida

ME-03C no se declara cerrado hasta que:
- todos los tipos tienen allowlist explícita;
- el reducer valida orden, correlación, generación, inventarios, idempotencia y terminalidad;
- un checkpoint no se utiliza hasta que su proyección base esté decodificada y verificada;
- los registros desconocidos o ambiguos fallan cerrados;
- se diferencia estructuralidad de continuidad confiable;
- C45–C87 están representados y ejecutados en entorno de pruebas;
- no se afirma persistencia, recuperación real o Forget completado sin adaptadores/evidencia reales.


## 10. Validación automatizada posterior

En el commit de código `0a6d120337e07e4b1365a7592f85e46ffe89718f`, GitHub Actions ejecutó la suite completa configurada por el repositorio:

- Python 3.10: éxito.
- Python 3.11: éxito.
- Python 3.12: éxito.
- Python 3.13: éxito.
- Resultado de Python 3.11: `Ran 323 tests`, `OK`.
- Workflow: [Atlas CI #43525199210](https://github.com/yon30c/atlas/actions/runs/43525199210).

Los 78 métodos de prueba de journal/reducer quedaron incluidos en esa suite. La ejecución valida los modelos, reducer, fakes y pruebas existentes en el repositorio. **No** demuestra persistencia durable, continuidad criptográfica, anti-rollback, atomicidad distribuida, fencing de endpoints reales ni Forget físico. La cobertura sigue siendo de contratos/modelos y fakes.
