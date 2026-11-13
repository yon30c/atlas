# ME-03 — Diseño del registro durable de consistencia y recuperación

**Estado:** propuesta técnica de diseño para revisión; no es un contrato normativo nuevo ni una implementación.  
**Rama de trabajo:** `implementation/me-01-to-me-04-memory-engine`  
**Dependencias:** CT-01, CT-03, CT-04, CT-05, CT-08; DM-01; `me-03-read-consistency-and-suppression-design.md`; `me-03-read-consistency-port-contracts.md`.  
**Alcance:** definir las garantías lógicas del registro durable que respalda admisiones, compromisos de emisión, cierres, invalidaciones, acknowledgements, idempotencia y recuperación.  
**Fuera de alcance:** selección de base de datos, formato físico, broker, transporte, ORM, proveedor criptográfico, topología, replicación, backups, despliegue y eliminación física de memoria.

Este documento no declara que exista persistencia durable. Define qué deberá preservar cualquier implementación futura para poder sostener las garantías ME-03.

---

## 1. Objetivo y separación de responsabilidades

El registro durable es la fuente recuperable del estado de consistencia y fencing. Debe permitir reconstruir, sin inferencias optimistas, qué admisiones fueron aceptadas, qué emisiones cruzaron el punto de compromiso, qué cierres o invalidaciones comenzaron y qué endpoints confirmaron finalización o fencing.

El registro:

- No decide autorización CAM ni crea Grants.
- No sustituye Memory Gateway ni permite acceso directo a contenido.
- No almacena contenido de memoria, fragmentos, respuestas derivadas ni hashes de contenido.
- No sustituye EventStore ni SecurityAudit.
- No decide que Forget terminó físicamente; solo respalda la supresión lógica y la reconciliación de entregas.
- No convierte un timeout, caída de proceso o ausencia de heartbeat en evidencia de cancelación.

### 1.1 No reutilizar EventStore como autoridad de consistencia

El contrato `docs/contracts/events.md` define eventos funcionales inmutables y append-only, pero declara que EventStore no tiene garantía implícita de idempotencia de `append()`, deduplicación, orden causal ni procesamiento exactamente una vez. También establece que EventStore no sustituye SecurityAudit.

Por tanto, el registro de consistencia es una frontera lógica separada. Puede producir referencias de correlación para eventos funcionales o SecurityAudit cuando esos sistemas estén disponibles, pero su corrección no depende de ellos ni les delega el estado de fencing.

## 2. Invariantes del registro

| ID | Invariante | Regla |
|---|---|---|
| DJ-01 | Durabilidad previa | Ninguna admisión puede habilitar lectura de contenido hasta que su registro durable haya sido confirmado. |
| DJ-02 | Orden monotónico | Cada transición confirmada tiene una posición de orden única y monotónica dentro de su dominio de consistencia. |
| DJ-03 | Serialización | Operaciones cuyos alcances se solapan deben tener un orden linealizable común. |
| DJ-04 | Append-only | Un registro confirmado no se modifica ni se elimina para reescribir el historial. Correcciones son nuevas transiciones correlacionadas. |
| DJ-05 | Idempotencia | Repetir una operación con la misma clave y la misma solicitud canónica devuelve la operación existente; reutilizarla con otra solicitud produce conflicto. |
| DJ-06 | Estado derivable | El estado recuperado se deriva de registros confirmados y checkpoints verificables; no de cachés o memoria volátil. |
| DJ-07 | Fail-closed | Registro ausente, corrupto, incompleto, ambiguo, atrasado o no verificable bloquea las rutas afectadas. |
| DJ-08 | Egress correlacionado | Cada compromiso de emisión debe poder reconciliarse con un recibo durable del último punto controlado de entrega. |
| DJ-09 | Evidencia mínima | Solo se conservan metadatos opacos necesarios para correlación, autorización, orden y reconciliación. |
| DJ-10 | No rollback | La recuperación nunca reduce generación, secuencia, revisión ni estado terminal ya confirmado. |
| DJ-11 | Cobertura explícita | La admisión y cada cierre conservan el inventario exacto de rutas afectadas. |
| DJ-12 | Separación de inventarios | Las rutas de entrega y los destinos de persistencia/derivados se inventarían por separado. |

## 3. Unidad lógica de orden y concurrencia

### 3.1 Dominio de consistencia

Cada registro pertenece a un `consistency_domain_id` opaco que identifica el ámbito donde las operaciones deben compartir orden.

El identificador es una abstracción de contrato, no una decisión de particionamiento físico. No se fija si la implementación usa un dominio global, particiones, locks distribuidos, compare-and-swap u otro mecanismo.

Regla obligatoria: dos operaciones que puedan afectar la misma admisión, memoria, generación, ruta o punto de emisión deben quedar ordenadas por una misma relación linealizable. Si una invalidación de Identity, Grant, Project o Environment afecta varias memorias, el orden debe cubrir el conjunto afectado como una sola transición lógica; no se permite que una parte del alcance siga emitiendo mientras otra parte ya considera efectiva la invalidación.

### 3.2 Secuencia

Cada transición confirmada recibe:

- `consistency_domain_id`;
- `authority_epoch`, que identifica la época confiable del registro;
- `sequence`, estrictamente creciente dentro del dominio;
- `record_id` único;
- `operation_id` que agrupa la operación.

La secuencia se asigna dentro de la misma frontera atómica que confirma la transición. Una operación abortada no deja un registro confirmado ni avanza el estado observable. La secuencia no se reutiliza dentro de una época.

Una nueva época no autoriza a reiniciar contadores ni a ignorar registros anteriores. Su activación requiere evidencia confiable de continuidad y no rollback. El mecanismo físico para establecer esa evidencia queda pendiente.

### 3.3 Orden entre admisión, cierre y egress

La admisión, el cierre Forget, la invalidación y el compromiso de emisión deben compartir la misma semántica de orden.

- Si el compromiso de emisión queda ordenado antes del cierre, esa unidad cuenta como emitida antes del cierre.
- Si el cierre queda ordenado primero, el compromiso posterior se rechaza.
- No se admite una comprobación de generación seguida de una liberación separada que pueda intercalarse con un cierre.
- Un resultado ambiguo de compromiso no se interpreta como rechazo ni como éxito: la admisión queda `UNRESOLVED` hasta reconciliar el recibo del endpoint.

La implementación deberá proporcionar esta propiedad incluso si el registro y el endpoint son componentes físicos diferentes. Si no puede demostrar el orden común, esa ruta no puede servir contenido protegido.

## 4. Sobre lógico de cada registro

Cada registro confirmado debe poder representarse mediante un sobre tipado que contenga, según el tipo:

| Campo | Uso |
|---|---|
| `record_id` | ID único del registro. |
| `schema_version` | Versión cerrada del esquema del registro. |
| `consistency_domain_id` | Dominio lógico de orden. |
| `authority_epoch` | Época confiable del registro. |
| `sequence` | Posición monotónica dentro del dominio. |
| `record_type` | Tipo cerrado de transición. |
| `operation_id` | Operación a la que pertenece. |
| `idempotency_key` | Clave opaca cuando la operación sea repetible. |
| `request_id`, `correlation_id` | Correlación, no prueba de autorización. |
| `actor_identity_id` | Actor atribuido cuando corresponda. |
| `subject_user_id` | Sujeto autenticado cuando corresponda. |
| `target` | IDs exactos de memoria, versión, autoridad o recurso afectado. |
| `generation` | Generación de fencing aplicable. |
| `revision_set` | Revisiones exactas evaluadas o invalidadas cuando correspondan. |
| `route_ids`, `endpoint_id` | Cobertura de entrega afectada. |
| `receipt_id` | Referencia opaca a recibo de egress/fencing/finalización. |
| `proof_reference` | Referencia opaca a evidencia de autorización directa, nunca la prueba secreta. |
| `occurred_at`, `recorded_at` | Instantes UTC diferenciados cuando corresponda. |
| `transition` | Estado anterior y posterior, limitado al tipo de registro. |

Los campos son tipados y aplicables por evento; no se admiten mapas arbitrarios que puedan introducir payloads sin revisión.

### 4.1 Datos prohibidos

El registro no conserva:

- contenido de Memory o MemoryVersion;
- fragmentos, tokens de contenido, buffers o respuestas derivadas;
- hashes de contenido olvidado;
- prompts, razonamiento interno o texto de conversación como prueba;
- secretos, credenciales, tokens de sesión o OwnerDecisionProof en bruto;
- copias de documentos fuente o datos completos de conectores.

Las referencias de evidencia son opacas y deben volver a pasar por su propio control de acceso. La referencia no concede permiso para recuperar la evidencia.

## 5. Tipos de transición

El catálogo inicial de tipos de registro es cerrado para esta etapa:

| Tipo | Hecho durable representado |
|---|---|
| `READ_ADMITTED` | Admisión exacta creada y registrada antes de permitir lectura de contenido. |
| `READ_ACTIVATED` | Admisión pasa a ACTIVE, si esa transición se registra separadamente. |
| `EGRESS_COMMITTED` | Unidad de emisión aceptada irrevocablemente por el último punto controlado. |
| `ENDPOINT_COMPLETED` | Endpoint confirma que terminó toda la entrega de esa admisión. |
| `ENDPOINT_FENCED` | Endpoint confirma que no puede emitir más unidades de una admisión/generación anterior. |
| `FORGET_CLOSED` | Se cerró admisión nueva, avanzó generación y se capturó el conjunto previo afectado. |
| `INVALIDATION_CLOSED` | Se ordenó una invalidación y su fencing para el alcance exacto. |
| `ADMISSION_RECONCILED` | Una admisión alcanzó COMPLETED o CANCELLED con evidencia correlacionada. |
| `FORGET_SUPPRESSED` | Todas las admisiones previas quedaron terminales y verificadas; solo declara supresión lógica. |
| `INVALIDATION_RECONCILED` | Todos los endpoints/admisiones del alcance fueron reconciliados. |
| `CHECKPOINT_COMMITTED` | Se confirmó un checkpoint íntegro y vinculado a un rango exacto del registro. |

Un registro no se reinterpreta retroactivamente. Un error se representa mediante un nuevo registro correlacionado, no reescribiendo el anterior.

## 6. Fronteras atómicas obligatorias

### 6.1 Admisión

La operación lógica de admisión debe confirmar conjuntamente:

1. que no hay Forget/supresión ni invalidación aplicable;
2. que las revisiones CAM siguen vigentes;
3. que las rutas están registradas y habilitadas;
4. la generación asignada;
5. el registro `READ_ADMITTED`;
6. la asociación de la admisión con su operación y endpoints.

Solo después de confirmar esta transición puede el Gateway invocar lectura condicional de contenido. Si el registro durable no confirma, no se lee contenido.

### 6.2 Inicio de Forget

El inicio de Forget debe confirmar como una sola transición lógica:

1. la autorización directa del propietario, ya verificada y consumida;
2. la clave de idempotencia y su solicitud canónica;
3. el cierre de nuevas admisiones para la memoria completa;
4. el avance de generación de fencing;
5. la captura exacta de admisiones no terminales anteriores;
6. la captura exacta de sus rutas de entrega;
7. el registro `FORGET_CLOSED`.

No puede existir una ventana en la que nuevas admisiones entren después del cierre o queden fuera del inventario previo.

### 6.3 Invalidación

La revisión canónica nueva, el cierre de admisiones/emisiones antiguas y el registro de la invalidación deben quedar ordenados antes de que el cambio se considere efectivo para contenido protegido. Una notificación eventual posterior no satisface esta garantía.

### 6.4 Compromiso de egress

El último punto controlado debe producir un recibo durable, único e idempotente que identifique admisión, endpoint, generación, secuencia y emisión.

El recibo debe permitir resolver los resultados inciertos tras un fallo entre la aceptación de la unidad y el registro de su confirmación en la autoridad. Si el endpoint no puede consultar o demostrar ese recibo después de reiniciar, la admisión permanece `UNRESOLVED`.

No se acepta:
- emitir primero y confiar en que el registro se actualice después sin recibo recuperable;
- registrar una emisión como completada antes de que el endpoint la haya aceptado irrevocablemente;
- tratar la pérdida de respuesta como prueba de que la unidad no salió.

La relación física entre el journal y el endpoint queda abierta; la garantía lógica de orden y recibo recuperable no.

### 6.5 Finalización y fencing

Cada recibo de endpoint se registra de forma correlacionada con operación, admisión, endpoint, generación y secuencia final aplicable. Los recibos duplicados idénticos son idempotentes; los recibos contradictorios, de otra operación o de generación antigua se rechazan y generan estado no resuelto/alarma según corresponda.

La admisión solo se reconcilia como:
- `COMPLETED` si todos los endpoints terminaron y no quedan unidades pendientes;
- `CANCELLED` si todos los endpoints relevantes confirmaron fencing y no existe compromiso posterior;
- `UNRESOLVED` en cualquier otro caso.

## 7. Idempotencia y consumo de autorización

### 7.1 Clave de idempotencia

La solicitud canónica debe vincular al menos:

- actor y sujeto autenticado;
- acción;
- recurso/alcance exacto;
- clave de idempotencia;
- referencia de autorización aplicable;
- parámetros que cambian el efecto de la operación.

La misma clave y misma solicitud canónica devuelve la misma operación y resultado durable. La misma clave con solicitud distinta devuelve conflicto. No se deriva idempotencia de `request_id`.

La evidencia mínima para impedir replay debe conservarse mientras la operación pueda repetirse o recuperarse. La política de retención/purga de tombstones de idempotencia es una decisión operativa pendiente; no puede purgarse un dato si eso permite reejecutar una operación protegida.

### 7.2 OwnerDecisionProof

DM-P06 exige prueba directa, no delegable, de un emisor confiable, ligada a acción y recursos exactos y consumida una sola vez.

El protocolo actual `VerifiedForgetAuthorization` solo expone decision_id, request_id, actor_identity_id, subject_user_id, memory_id y owner_id. Antes de habilitar Forget deberá poder comprobarse además, mediante evidencia confiable y no mediante campos declarados por el llamador:

- emisor confiable;
- proof_id/nonce no reutilizable;
- acción exacta `memory.forget`;
- vinculación a sujeto, actor, memoria y request;
- expiración y momento de consumo;
- resultado verificable de consumo de un solo uso.

El consumo de la prueba y el registro `FORGET_CLOSED` deben ser recuperables e idempotentes como una sola intención lógica. Si el verificador y la autoridad no pueden coordinar ese resultado de forma verificable, un fallo intermedio deja la solicitud sin reintento automático y Forget permanece deshabilitado hasta reconciliar o presentar una nueva prueba válida. No se añade bypass provisional.

## 8. Checkpoints y recuperación

### 8.1 Checkpoint

Un checkpoint es una representación compacta del estado reconstruible hasta un límite exacto de secuencia. Debe conservar:

- dominio y época de autoridad;
- secuencia máxima incluida;
- generación actual por alcance;
- cierres Forget e invalidaciones activos y terminales;
- admisiones no terminales y su inventario de endpoints;
- últimos estados y recibos de endpoints necesarios para reconciliar;
- claves/tombstones de idempotencia aún sujetas a replay;
- referencia de integridad y procedencia verificable del checkpoint.

El checkpoint no sustituye el registro histórico ni puede descartar evidencia necesaria para resolver una operación activa. La estrategia de retención y compactación queda pendiente; cualquier compactación debe demostrar equivalencia del estado reconstruido y preservar los requisitos de idempotencia y auditoría.

### 8.2 Secuencia de recuperación obligatoria

1. Iniciar en modo cerrado: no aceptar nuevas admisiones ni liberar contenido protegido.
2. Cargar checkpoint y registros posteriores desde una fuente autenticada y verificable.
3. Validar dominio, época, secuencias, unicidad de IDs, referencias, transiciones permitidas, generaciones y correlación.
4. Detectar truncamiento, huecos no explicados, duplicados contradictorios, rollback o registros desconocidos.
5. Reconstruir cierres, invalidaciones, admisiones, compromisos de egress y claves de idempotencia.
6. Reinstalar el fencing/generación más reciente antes de contactar endpoints.
7. Recuperar como `UNRESOLVED` cualquier admisión cuya terminalidad no esté probada por recibos recuperables.
8. Consultar/fencear cada endpoint y registrar recibos nuevos cuando sean necesarios.
9. Reconciliar operaciones solo cuando la evidencia cubra todos los endpoints.
10. Habilitar únicamente dominios/rutas cuya continuidad y estado hayan sido verificados.

Si falla cualquier paso, el dominio afectado permanece en cuarentena fail-closed. No se reconstruye una admisión ausente por inferencia, ni se marca CANCELLED por timeout.

### 8.3 Protección contra rollback y truncamiento

La recuperación debe poder detectar que está leyendo una copia antigua o truncada del registro. Para ello requiere una referencia de continuidad/alto-watermark confiable, independiente de los datos recuperados que se están validando.

El algoritmo criptográfico, almacenamiento de anclas, protección contra manipulación y ubicación del watermark no se eligen en este documento. Sin una prueba verificable de continuidad, no se reabren rutas protegidas.

## 9. Fallos intermedios y resultado exigido

| Punto de fallo | Estado tras recuperación |
|---|---|
| Antes de confirmar READ_ADMITTED | No existe admisión utilizable; no se leyó contenido. |
| Después de confirmar READ_ADMITTED, antes de leer contenido | Admisión recuperada; se reconcilia o se cerca antes de terminar. |
| Durante lectura condicional | UNRESOLVED hasta confirmar que ningún handle/buffer puede emitir. |
| Después de FORGET_CLOSED, antes de recibir acknowledgements | Gate sigue cerrado; cierre permanece CLOSING. |
| Después de compromiso egress, antes de persistir confirmación en autoridad | Consultar recibo durable del endpoint; si no es verificable, UNRESOLVED. |
| Después de recibir un acknowledgement, antes de checkpoint | Reconstruir desde journal/recibo; no asumir pérdida ni duplicar efecto. |
| Durante escritura de checkpoint | Usar únicamente checkpoint confirmado y completo anterior; mantener cierres posteriores. |
| Registro corrupto, truncado o de época antigua | Cuarentena del dominio; no admitir ni emitir. |
| Endpoint no disponible o sin consulta durable | Admisión UNRESOLVED; no confirmar supresión. |
| Verificador de OwnerDecisionProof no disponible | No iniciar Forget; no sustituirlo por una prueba local. |

## 10. Contrato lógico de puerto propuesto

El puerto de consistencia actual agrupa las operaciones de dominio, pero no expresa todavía la frontera del registro durable. Se propone separar la capacidad de registrar/recuperar transiciones, sin exponerla a Assistant, Skills ni consumidores:

```python
class ConsistencyJournalPort(Protocol):
    def append_transition(
        self,
        expected_position: ConsistencyPosition,
        transition: ConsistencyTransition,
    ) -> JournalCommit | None: ...

    def load_recovery_state(
        self,
        domain_id: str,
    ) -> ConsistencyRecoveryState | None: ...

    def load_endpoint_receipts(
        self,
        admission_id: str,
    ) -> tuple[EndpointReceiptReference, ...] | None: ...

    def commit_checkpoint(
        self,
        checkpoint: ConsistencyCheckpoint,
        expected_position: ConsistencyPosition,
    ) -> JournalCommit | None: ...
```

Este pseudocódigo describe responsabilidades, no nombres o firmas finales. La autoridad de consistencia es el único consumidor autorizado del journal. Los adaptadores no se exponen a Gateway callers ni a agentes.

### 10.1 Semántica de append_transition

- Verifica posición esperada/versión de concurrencia.
- Rechaza escrituras fuera de orden, transiciones ilegales y claves idempotentes contradictorias.
- Asigna secuencia y confirma registro en una única operación lógica.
- Devuelve un recibo de commit que identifica posición y registro.
- Resultado incierto no se interpreta como abortado; la autoridad consulta por clave de idempotencia/ID de operación.
- Nunca sobrescribe un registro confirmado.

### 10.2 Semántica de load_recovery_state

- Devuelve un estado reconstruible hasta una posición identificable.
- Incluye indicador de continuidad y procedencia verificables.
- Distingue estado completo, ausente, parcial, corrupto y no verificable.
- No devuelve contenido de memoria.
- No autoriza reabrir rutas; la autoridad realiza validación y reconciliación.

Las clases `ConsistencyPosition`, `ConsistencyTransition`, `JournalCommit`, `ConsistencyRecoveryState`, `EndpointReceiptReference` y `ConsistencyCheckpoint` son conceptos de diseño, no clases ya implementadas.

## 11. Pruebas de aceptación propuestas

Los escenarios siguientes amplían la cobertura C01–C44. Son requisitos para futuras pruebas deterministas; no afirman que estén implementados ni ejecutados.

| ID | Escenario | Resultado exigido |
|---|---|---|
| C45 | Falla el commit durable de READ_ADMITTED | Gateway no lee contenido ni crea handle. |
| C46 | Admisión compite con FORGET_CLOSED | Ambas quedan ordenadas; la lectura se incluye en el inventario previo o se rechaza. |
| C47 | FORGET_CLOSED compite con egress commit | La unidad queda inequívocamente antes o después del cierre. |
| C48 | Misma clave y solicitud canónica | Se devuelve la misma operación/resultado sin duplicar efecto. |
| C49 | Misma clave con solicitud/objetivo distinto | Conflicto; no se modifica el estado. |
| C50 | Crash después de FORGET_CLOSED | Tras recuperación la puerta sigue cerrada y el cierre sigue pendiente. |
| C51 | Crash después de egress commit y antes del journal acknowledgement | Se reconcilia por recibo durable; sin recibo verificable queda UNRESOLVED. |
| C52 | Recibo de endpoint repetido idéntico | Idempotente; no duplica transición ni secuencia terminal. |
| C53 | Recibo contradictorio, de otro endpoint o generación | Rechazado; operación no se declara resuelta. |
| C54 | Secuencia duplicada con contenido de registro distinto | Dominio en cuarentena; no se elige una versión arbitrariamente. |
| C55 | Journal truncado o con hueco no explicado | Dominio en cuarentena y rutas cerradas. |
| C56 | Checkpoint de época/secuencia anterior al watermark confiable | Rechazado por rollback. |
| C57 | Checkpoint omite admisión, cierre o endpoint activo | Rechazado; no se reabre tráfico. |
| C58 | Fallo entre consumo de OwnerDecisionProof y FORGET_CLOSED | No se reejecuta con prueba consumida; reconciliación o nueva prueba válida. |
| C59 | Verificador no disponible o prueba no verificable | Forget no inicia. |
| C60 | Compactación intenta eliminar tombstone aún necesario para idempotencia | Compactación rechazada o conserva el tombstone. |
| C61 | Recuperación parcial de un dominio multi-recurso | Ninguna ruta del alcance solapado se habilita hasta verificar el conjunto completo. |
| C62 | Registro desconocido/schema_version no soportado | Fail-closed; no ignorar silenciosamente la transición. |
| C63 | Endpoint confirma fencing pero falta registro correlacionado | No confirmar supresión hasta reconciliar evidencia y persistirla. |
| C64 | Reintento después de resultado incierto de append_transition | Consulta idempotente; no se crea una segunda operación. |

Las pruebas de concurrencia usarán barreras/eventos deterministas, nunca sleeps. Las pruebas de recuperación deberán inyectar fallos en cada frontera atómica descrita en §6 y verificar el estado después de reconstruir desde el journal.

## 12. Decisiones técnicas que permanecen abiertas

Este diseño no decide:

1. Tecnología de almacenamiento, motor, esquema físico u ORM.
2. Mecanismo de transacción, consenso, lock distribuido o compare-and-swap.
3. Si el journal será global, particionado o replicado, siempre que preserve la relación de orden exigida.
4. Formato criptográfico, firmas, MAC, hash chain o anclas antirrollback.
5. Tecnología de almacenamiento y consulta de recibos durables en endpoints.
6. Política de retención/compactación de registros y tombstones, compatible con idempotencia y CT-05.
7. Estrategia de backups, replicación, restauración y pruebas operativas.
8. Inventario real de rutas y destinos físicos.
9. Emisor y verificador confiables de OwnerDecisionProof.
10. Evidencia de purga física de Memory, versiones, propuestas, referencias, índices, derivados y backups.

No se selecciona una tecnología por conveniencia ni se infiere de la infraestructura actual de Atlas.

## 13. Criterios de salida del diseño

El contrato estará listo para traducirse a modelos/puertos implementables cuando:

- se acepte el alcance de orden y atomicidad de §3 y §6;
- las clases de registro y sus campos mínimos estén revisadas;
- el contrato de recuperación y anti-rollback de §8 tenga una fuente verificable definida a nivel de interfaz;
- el tratamiento del resultado incierto de egress y OwnerDecisionProof esté resuelto;
- los escenarios C45–C64 se conviertan en casos de prueba;
- se mantenga separada la autoridad de consistencia de EventStore y SecurityAudit.

La aprobación de este documento no autoriza adaptadores, migraciones, despliegue ni ejecución de Forget.

## 14. Relación con la implementación actual

En el commit de referencia de esta propuesta:

- existen modelos inmutables de snapshots, revisiones, admisiones, invalidaciones, recibos, cierres y `ForgetRecoverySnapshot`;
- existe un Gateway protegido que devuelve un handle opaco y delega emisión/finalización a puertos;
- existen fakes de proceso único para autoridad, egress y recuperación simulada;
- se definieron modelos puros iniciales en `src/atlas/memory/journal.py` y el protocolo `ConsistencyJournalPort` en `src/atlas/ports/consistency_journal.py`;
- no existe journal durable, watermark confiable, checkpoint durable ni protección antitruncamiento;
- el fake de recuperación no prueba reinicios reales, concurrencia entre procesos ni almacenamiento durable;
- no existe emisor/verificador confiable de OwnerDecisionProof;
- no se han completado inventarios reales de entrega y persistencia;
- se escribieron 29 pruebas unitarias de modelos y fake de journal en `tests/unit/test_memory_journal.py`; no se han ejecutado;
- no se ha ejecutado la suite completa ni las pruebas C01–C64 en esta etapa.

**Conclusión:** los modelos puros, el puerto tipado y un fake de proceso único con CAS/idempotencia/recovery/checkpoint y consulta de recibos ya están definidos. El siguiente trabajo será endurecer las invariantes restantes, completar los escenarios C45–C64, ejecutar las pruebas en un entorno disponible y revisar la relación con egress antes de considerar cualquier adaptador durable.
