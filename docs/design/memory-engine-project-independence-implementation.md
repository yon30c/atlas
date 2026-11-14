# Memory Engine — implementación de independencia por proyecto

Fecha: 2026-11-14  
Rama de trabajo: `feature/atlas-functional-f1`

## Objetivo

Convertir Memory Engine en un componente reutilizable por Atlas y por aplicaciones externas, sin permitir que un consumidor sustituya la autorización del motor ni obtenga acceso cruzado por conocer identificadores.

## Implementado en ME-D1 — frontera de contexto y autorización

- `atlas.memory.context.MemoryRequestContext`: contexto neutral para transportar atributos de una solicitud desde un consumidor.
- `atlas.memory.authorization.MemoryAuthorizationDecision` y `MemoryAuthorizationResult`: resultado de autorización propio del dominio Memory Engine.
- `atlas.ports.memory_authorization.MemoryAuthorizationPort`: contrato que desacopla el Gateway de la implementación concreta de CAM Atlas.
- `atlas.adapters.atlas_memory_authorization.AtlasMemoryAuthorizationAdapter`: adaptador de compatibilidad con CAM Atlas.
- `MemoryGatewayService` depende del puerto y contexto neutrales, no directamente de `MemoryAuthorizationService` ni de `OperationContext`.

## Implementado en ME-D2 — contrato neutral de vinculación de identidad

- `atlas.memory.identity.MemoryIdentityBinding`: relación verificada actor-sujeto, activa y versionada.
- `MemoryIdentityBindingPort` y `resolve_authenticated_memory_binding`: contrato de resolución y validación fail-closed.
- `AtlasIdentityBindingAdapter`: adapta el contrato histórico de identidad de Atlas.
- `MemoryAuthorizationService` consume el binding neutral. La política CAM, Grants y evaluación PROJECT permanecen en Atlas.

## Implementado en ME-D3 — metadatos independientes del consumidor

- `atlas.memory.ports.metadata` contiene `MemoryMetadataPort`, `ProjectMetadataPort` y `EnvironmentMetadataPort`. Son contratos que cada consumidor debe implementar contra sus fuentes canónicas.
- `atlas.memory.metadata_resolver.MemoryMetadataResolver` se trasladó al núcleo de Memory Engine. Valida IDs exactos, tipo de respuesta y correspondencia del recurso; errores, excepciones, respuestas ausentes o IDs discordantes devuelven ausencia y no habilitan fallback.
- Los DTO `MemoryVersionMetadata`, `ProjectMetadata` y `EnvironmentMetadata` usan `MemoryContractError`; la validación UUIDv7 de sus identificadores de memoria se realiza sin importar `atlas.core.errors.ContractError` ni el validador de Atlas.
- `MemoryAuthorizationService` importa el resolver desde `atlas.memory`, mientras la política CAM continúa siendo específica de Atlas.
- Se conservaron los módulos anteriores `atlas.ports.memory_metadata` y `atlas.authorization.memory_metadata_resolver` como reexportaciones de compatibilidad para consumidores existentes.

## Implementado en ME-D4A — puertos neutrales de custodia y firma de consistencia

- Se añadieron `atlas.memory.ports.consistency_keys.MemoryConsistencyKeyPort` y `atlas.memory.ports.consistency_signing.MemoryConsistencySignerPort` al paquete de puertos del dominio.
- El verificador de recuperación local consume el puerto neutral de custodia de claves; el adaptador HMAC consume el puerto neutral de firma.
- Los módulos históricos `atlas.ports.local_consistency_keys` y `atlas.ports.local_consistency_signer` se conservaron como reexportaciones de compatibilidad. Los nombres anteriores siguen disponibles.
- La separación mantiene la custodia fuera del journal: el núcleo recibe referencias opacas y no material de clave. La verificación continúa separada de la firma.
- No se modificaron canonicalización JSON, HMAC-SHA-256, envelopes, allowlists, checkpoints, reducer, estados de recuperación ni garantías anti-rollback.

## Implementado en ME-D4B — contratos neutrales de proyección y recuperación

- Se añadió `atlas.memory.ports.recovery`, que define contratos neutrales para posiciones, checkpoints, estados y proyecciones mediante protocolos estructurales; no importa modelos del journal Atlas, SQLite ni el reducer.
- Los DTO neutrales `CheckpointProjectionRequest/Result`, `VerifiedCheckpointProjection`, `RecoveryInventoryRequest/Result` y `VerifiedRecoveryInventories` enlazan cada atestación con el dominio, época, secuencia, referencias exactas y versión de política solicitada.
- Se añadieron `CheckpointProjectionPort` y `RecoveryInventoryVerifierPort` al paquete neutral de puertos.
- `LocalCheckpointProjectionAdapter` y `LocalRecoveryInventoryAdapter` traducen entre los contratos neutrales y los DTO históricos del perfil local. La validación histórica de evidencia sigue ejecutándose antes de convertirla; evidencia malformada o discordante se rechaza.
- `LocalConsistencyRecoveryVerifier` y `LocalCheckpointCoordinator` consumen ahora los contratos neutrales. El reducer sigue recibiendo la proyección concreta del adaptador local, sin aceptar proyecciones arbitrarias.
- Los contratos antiguos de `atlas.ports.local_consistency_recovery` permanecen disponibles para los adaptadores y consumidores existentes.

**Composición local:** construir una instancia de cada adaptador local y compartir la misma instancia de `LocalCheckpointProjectionAdapter` entre `LocalConsistencyRecoveryVerifier`, el journal y `LocalCheckpointCoordinator`. La instancia compartida mantiene la comprobación de identidad del resolver. El adaptador de inventarios se inyecta en el verificador de recuperación.

**Límite de confianza:** que un objeto satisfaga el protocolo neutral no demuestra por sí solo que la evidencia sea auténtica. La confianza depende de los puertos concretos configurados en la raíz de composición. En el perfil local, los adaptadores delegan en los verificadores locales existentes y validan el enlace exacto antes de devolver `VERIFIED`.

## Implementado en ME-D4C — contrato neutral del journal

- Se añadió `atlas.memory.ports.journal` con protocolos estructurales para posición, transición, commit, resolución de operaciones, entrada, checkpoint y estado de recuperación.
- `ConsistencyJournalPort` es genérico y parametrizado por los modelos inmutables del consumidor. Así, Memory Engine no obliga a una aplicación externa a importar `ConsistencyPosition`, `ConsistencyTransition`, envelopes o DTO del perfil Atlas.
- El contrato distingue carga estructural de recuperación operativa: `load_recovery_state` es solo diagnóstico. La autenticidad, continuidad, inventarios y anti-rollback deben verificarse mediante puertos de confianza separados.
- Los contratos se exportan desde `atlas.memory.ports`. La implementación SQLite y los modelos históricos no se sustituyeron en esta entrega; su adaptación al nuevo puerto queda pendiente de un adaptador de perfil local.
- No se cambiaron la forma canónica de idempotencia, el esquema persistido, las migraciones, la firma, el reducer ni la política de recuperación.



## Implementado en ME-D4D — adaptador del journal SQLite local

- Se refinó `atlas.memory.ports.journal.ConsistencyJournalPort`: el commit de checkpoint ahora conserva explícitamente el `expected_continuity_reference` y devuelve un resultado de checkpoint que incluye el checkpoint autenticado y el commit del marcador.
- Se añadió `LocalSQLiteConsistencyJournalAdapter` en `atlas.adapters.sqlite.local_consistency_journal`. Traduce la firma neutral del checkpoint a la firma interna SQLite (`expected_position`, compromiso esperado de cabecera, checkpoint), y delega append, resolución y lectura estructural sin reconstruir ni modificar DTO persistidos.
- El adaptador no expone `load_verified_recovery_state`. La recuperación operativa continúa exclusivamente en el journal local concreto, que pasa por `LocalConsistencyRecoveryVerifier`.
- `load_recovery_state` sigue siendo diagnóstico y no una fuente autorizada para reducer, admisión ni egress.
- El journal SQLite no ofrece actualmente una operación completa de inventario de recibos por admisión. Por ello, el adaptador devuelve `None` para `load_endpoint_receipts`, incluso cuando se proporciona una admisión válida. No devuelve una tupla vacía ni afirma que no existan recibos.
- La escritura de checkpoint mantiene el compare-and-swap contra la posición y el compromiso previo exactos; el marcador y el checkpoint continúan en una transacción atómica. No se cambiaron tablas, migraciones, canonicalización, envelopes ni HMAC.

**Composición:** construir el `SQLiteConsistencyJournal` como hasta ahora para los flujos operativos de recuperación local. Cuando un consumidor necesite la interfaz neutral de persistencia, envolver esa misma instancia con `LocalSQLiteConsistencyJournalAdapter`. No sustituir el journal concreto inyectado en el coordinador/verificador de recuperación por el adaptador neutral.



## Implementado en ME-D4E — composición separada de persistencia y recuperación verificada

- Se añadió `LocalSQLiteVerifiedRecoveryAdapter` en `atlas.adapters.sqlite.local_journal_composition`. Expone únicamente `load_verified_recovery_state` y delega en el verificador local configurado dentro de la instancia SQLite.
- El adaptador solo acepta evidencia del perfil local: si un resultado declara `VERIFIED` sin `verified_local_state`, lo convierte en `REJECTED`. Un resultado inesperado se convierte en `UNAVAILABLE`.
- Se añadió `LocalSQLiteConsistencyJournalPorts`, que agrupa el puerto neutral de persistencia y el puerto local de recuperación verificada. Su construcción exige que ambos adaptadores envuelvan exactamente la misma instancia de `SQLiteConsistencyJournal`.
- `compose_local_sqlite_journal_ports(journal)` falla si el journal no tiene configurada la pareja `recovery_verifier` + `recovery_trust_policy`. No crea políticas, claves, resolvers ni evidencia de confianza por su cuenta.
- La interfaz neutral de persistencia sigue sin ofrecer `load_verified_recovery_state`; la interfaz local de confianza no ofrece lectura estructural ni acceso directo al reducer.
- No se sustituyeron todavía los journals concretos inyectados en `LocalCheckpointCoordinator`, `RecoveryCoordinator` u otros flujos operativos. Esos consumidores continúan usando el objeto SQLite concreto porque también dependen de metadatos de issuer/key, compare-and-swap de checkpoint y otras operaciones locales. La migración de cada consumidor requiere un contrato compuesto explícito y pruebas de conformidad; no se hace por sustitución automática.
- No se modificaron persistencia, migraciones, serialización, canonicalización, HMAC, allowlists, reducer, estados de recuperación ni semántica anti-rollback.

**Composición local recomendada para nuevos consumidores:** crear una sola instancia de `SQLiteConsistencyJournal` con signer y verificador/política locales; pasarla a `compose_local_sqlite_journal_ports`; inyectar `ports.persistence` solo donde se necesite persistencia neutral y `ports.verified_recovery` solo donde se requiera un resultado autenticado local. Los consumidores que todavía necesiten operaciones específicas de Atlas/local deben continuar recibiendo el journal concreto hasta que exista un puerto explícito para esas operaciones.



## Implementado en ME-D4F — LocalCheckpointCoordinator usa puerto de recuperación explícito

- Se añadió el protocolo local de consumidor `LocalVerifiedRecoveryPort` en `memory/checkpoint_coordinator.py`. Su única capacidad es `load_verified_recovery_state(domain_id)`.
- `LocalCheckpointCoordinator` ahora exige `verified_recovery` como dependencia keyword-only. Ya no consulta `journal.load_verified_recovery_state`.
- El journal conserva las capacidades locales necesarias para este flujo: metadatos de issuer/role/key, validación de política y `commit_checkpoint` con compare-and-swap sobre la posición y continuidad exactas.
- La evidencia de recuperación se obtiene exclusivamente del puerto inyectado y sigue exigiendo `ConsistencyRecoveryVerificationResult.VERIFIED`, `VerifiedLocalConsistencyRecoveryState` y coincidencia de la versión de política.
- Las pruebas de `test_checkpoint_coordinator.py` fueron actualizadas para inyectar `LocalSQLiteVerifiedRecoveryAdapter` construido sobre la misma instancia de journal.
- No se migró todavía el commit del checkpoint al puerto neutral: el contrato neutral actual no representa issuer/key metadata ni toda la semántica local de CAS. Tampoco se cambió el reducer ni el formato de persistencia.
- No se ejecutaron pruebas ni build.

**Composición de checkpoint local:** crear el journal local y sus verificadores; crear `LocalSQLiteVerifiedRecoveryAdapter(journal)` o usar `compose_local_sqlite_journal_ports(journal).verified_recovery`; inyectar ese puerto en `LocalCheckpointCoordinator`. Mantener el mismo journal local para la escritura atómica del checkpoint.

## Alcance pendiente de ME-D4

- El nuevo contrato del journal es neutral, pero `SQLiteConsistencyJournal` todavía utiliza los DTO Atlas/local y no se ha adaptado al puerto genérico.
- Los modelos neutrales de proyección son estructurales y transportan la proyección concreta del consumidor; aún no existe un reducer neutral reutilizable. El reducer y las políticas de replay siguen ligados al perfil Atlas/local.
- `LocalConsistencyTrustPolicy`, `LocalConsistencyRecoveryVerifier`, `LocalCheckpointCoordinator` y `SQLiteConsistencyJournal` siguen siendo componentes del perfil local/Atlas.
- La extracción de validadores y modelos concretos de transición/replay como modelos de dominio neutrales sigue pendiente. No se debe sustituirlos por `object`, ni aceptar evidencia creada por el consumidor sin verificar su correspondencia exacta.
- El perfil local sigue sin ofrecer protección anti-rollback externa. Ninguna extracción de puertos cambia esa limitación.

## Límite de confianza obligatorio

Los contextos transportan atributos, no credenciales. Los bindings de identidad solo acreditan una relación actor-sujeto; no conceden permisos. Los metadatos de memoria, proyecto y entorno deben proceder de las fuentes canónicas implementadas por el consumidor, nunca de valores declarados por el solicitante.

Los adaptadores deben verificar identidad, estado, revisión, propietario, proyecto y entorno. Si no pueden verificar un atributo necesario, deben denegar. La política de autorización debe comprobar propietario, scope, clasificación, estado de versión y Grants aplicables después de resolver los metadatos.

La reutilización del resolver no convierte al consumidor en autoridad de autorización ni cambia las reglas PRIVATE/PROJECT. Los snapshots, admisiones, rutas, fencing y egress protegido permanecen obligatorios.

## Compatibilidad y alcance

Esta entrega es incremental, no la finalización de la independencia.

- CAM, Grants, evaluación de permisos y construcción de snapshots siguen siendo Atlas.
- Los modelos de dominio y validadores generales aún conservan dependencias de tipos/errores de `atlas.core`.
- La política local de confianza, los modelos del journal, el reducer y el orquestador de recuperación siguen ligados al perfil Atlas/local. Los puertos de custodia de claves, firma, proyección/inventario y journal ya tienen contratos neutrales, pero los adaptadores de persistencia siguen usando modelos del perfil local.
- La persistencia del contenido de memorias, versiones y propuestas no está implementada; SQLite continúa persistiendo el diario/control de consistencia.
- Los servicios operativos de propuestas, revisión y Forget no están completos.

## Próximas fases

1. Adaptar el perfil local/SQLite al contrato neutral del journal mediante una frontera explícita, preservando sus DTO y compatibilidad históricos.
2. Separar modelos neutrales de transición/replay y diseñar un reducer reutilizable sin debilitar la verificación de evidencia.
3. Implementar repositorios persistentes para Memory, MemoryVersion y MemoryProposal.
4. Completar propuesta, aprobación/rechazo explícitos, Forget operativo e integración con AtlasCore.
5. Añadir pruebas de conformidad con al menos dos consumidores distintos y pruebas negativas de aislamiento.

## Validación pendiente

Por instrucción del propietario, no se ejecutaron pruebas ni builds durante ME-D1, ME-D2, ME-D3, ME-D4A, ME-D4B ni ME-D4C. La compatibilidad con fakes y consumidores actuales, imports, construcción de paquetes y casos negativos quedan pendientes de la fase de pruebas.

## No incluido

- No se modifica el contrato normativo `docs/contracts/memory.md`.
- No se cambian los scopes PRIVATE/PROJECT, sus reglas de visibilidad ni las decisiones de aprobación.
- No se crea una base de datos de contenido ni se cambia infraestructura de producción.
- No se declara completada la independencia hasta validar al menos un segundo consumidor sin dependencias de AtlasCore.


## Implementado en ME-D4G — RecoveryJournalCoordinator separa lectura verificada y escritura

- Se añadió el puerto consumidor `VerifiedRecoveryStatePort`, cuya única capacidad es cargar un resultado de recuperación autenticado.
- `RecoveryJournalCoordinator` recibe ahora `verified_recovery` como dependencia explícita. Su método `_load` consulta ese puerto y nunca solicita recuperación verificada al journal de escritura.
- Se redujo el contrato del journal requerido por este coordinador a `RecoveryJournalWritePort`, que expone únicamente `append_transition`. La coordinación conserva la escritura durable del cierre del gate y de cada fencing.
- El coordinador continúa exigiendo un resultado `VERIFIED`, un estado presente y el dominio exacto antes de alimentar el reducer. Las excepciones, los estados no verificados y los dominios discordantes siguen bloqueando la recuperación.
- Las pruebas existentes de recuperación inyectan un fake de lectura verificada separado del fake de escritura. La prueba de indisponibilidad sigue simulando el fallo en la fuente de evidencia.
- No se cambiaron el reducer, los modelos persistidos, las transiciones, la secuencia de cierre/fencing, los recibos, ni la política de recuperación. El reducer y la orquestación siguen siendo específicos del perfil Atlas/local.
- No se ejecutaron pruebas ni build.

**Composición:** crear una única fuente local de journal; pasar una capacidad de escritura (`append_transition`) al coordinador y el puerto `verified_recovery` procedente de `compose_local_sqlite_journal_ports(journal)`. Ambos deben corresponder al mismo journal subyacente. El coordinador no puede inferir ni fabricar esa relación; la raíz de composición es responsable de garantizarla.


## Implementado en ME-D4H — raíz de composición de recuperación SQLite

- Se añadió LocalSQLiteRecoveryAuthorityPort, que combina la autoridad protegida de runtime con RecoveryGatePort y declara la identidad exacta de su SQLiteConsistencyJournal.
- Se añadió compose_local_sqlite_recovery_coordinator(...). La función crea los puertos de persistencia y recuperación verificada desde una sola instancia SQLite e inyecta esas dos capacidades separadas en RecoveryJournalCoordinator.
- La composición exige que consistency_authority.consistency_journal sea exactamente journal y valida las capacidades de admisión, Forget, invalidación, egress y cierre/restauración del Recovery Gate. Una autoridad incompleta o vinculada a otro journal se rechaza.
- El objeto de composición devuelve la misma instancia consistency_authority. El consumidor debe inyectar esa instancia exacta también en MemoryGatewayService; no debe construir una segunda autoridad para el Gateway ni para recuperación.
- El contrato de la autoridad exige que cierre del gate y persistencia de RECOVERY_CLOSED sean atómicos con admisiones/egress. La propiedad de identidad enlaza la composición local al journal, pero no sustituye la implementación ni las pruebas de atomicidad de la autoridad.
- Se actualizó test_memory_recovery_completion.py para inyectar explícitamente el puerto verified_recovery y el contexto de confianza requeridos desde ME-D4G.
- Limitación real: el repositorio todavía no contiene una implementación concreta de ProtectedMemoryRecoveryAuthorityPort enlazada a SQLite. Por tanto, ME-D4H proporciona la raíz contractual y falla cerrado ante una autoridad no vinculada; no declara que exista ya una autoridad SQLite operativa ni activa el runtime.
- No se ejecutaron pruebas ni build.


## ME-D4I — inspección de frontera transaccional SQLite

**Estado: inspección completada; diseño de implementación pendiente. No se implementó la autoridad concreta.**

### Evidencia confirmada en la rama

- `SQLiteDatabase.write_transaction()` abre una conexión nueva por operación, aplica `BEGIN IMMEDIATE`, confirma al salir y revierte ante excepción. La conexión configura `foreign_keys=ON`, `synchronous=FULL`, `busy_timeout` y el archivo utiliza WAL.
- `CORE_SCHEMA_V1` ya incluye en `consistency_domains` los campos `recovery_gate_state` (por defecto `closed`), `active_recovery_operation_id`, `active_recovery_generation` y `recovery_receipt_id`. El esquema tiene por tanto espacio para persistir el estado del gate; no demuestra que exista una autoridad que lo gobierne.
- `SQLiteConsistencyJournal.append_transition()` realiza su propia llamada a `self._database.write_transaction()`. `commit_checkpoint()` también abre su propia transacción. Las operaciones de journal no reciben una conexión/transacción externa.
- En el código de `SQLiteConsistencyJournal` inspeccionado no hay referencias operativas a `recovery_gate_state`, `active_recovery_operation_id`, `active_recovery_generation` ni `recovery_receipt_id`. El journal persiste transiciones y compromisos, pero no sincroniza el estado durable del gate.
- `ProtectedMemoryRecoveryAuthorityPort` sigue siendo un Protocol compuesto por `ProtectedMemoryConsistencyPort` y `RecoveryGatePort`. No se encontró una implementación concreta SQLite de ese protocolo.
- ME-D4H ya exige identidad de la misma instancia de journal en la raíz de composición, pero esa comprobación de identidad no comparte conexiones ni demuestra atomicidad.

### Conclusión

SQLite proporciona una primitiva local razonable para serializar escritores en el servidor único aprobado. Sin embargo, la arquitectura actual no permite que una implementación externa al journal actualice el gate y llame después a `append_transition()` como si fueran una sola operación: serían dos transacciones independientes, con una ventana de inconsistencia y posibilidad de resultado ambiguo.

Por tanto, **no es seguro implementar la autoridad mediante composición de llamadas actuales**. No se debe utilizar un lock de proceso como sustituto de la transacción SQLite: no cubriría reinicios ni otros procesos.

### Diseño requerido antes de implementar

1. Introducir una frontera transaccional explícita compartida, por ejemplo una unidad de trabajo SQLite que entregue una conexión activa bajo `BEGIN IMMEDIATE`. La autoridad y el journal deben operar sobre esa misma conexión y transacción.
2. Separar métodos internos que acepten una conexión ya abierta (por ejemplo, append dentro de transacción) de métodos públicos que abren su propia unidad de trabajo. Evitar transacciones anidadas o commits internos.
3. En una sola transacción, validar dominio/época/posición e idempotencia, comprobar el gate, aplicar la mutación de autoridad y persistir la transición autenticada, la operación/idempotency record y el nuevo head. Si una parte falla, revertir todo.
4. Persistir y reconstruir el estado del gate desde la misma fuente autoritativa. Los campos de gate no pueden convertirse en una segunda verdad separada del journal: las invariantes entre estado materializado y transición deben verificarse en cada apertura/reinicio.
5. Definir resolución exacta de resultado ambiguo por `operation_id`, `idempotency_key` y solicitud canónica, bajo la misma autoridad transaccional. `UNKNOWN` o conflicto mantiene el gate cerrado.
6. Diseñar por separado el límite de egress. Una transacción SQLite no puede incluir de forma atómica la aceptación irrevocable de un transporte remoto. La solución deberá demostrar fencing e idempotencia en el receptor o una estrategia durable equivalente; no basta con hacer commit y luego enviar.
7. Añadir pruebas de concurrencia multiproceso y fallos inyectados para admisión vs cierre, egress vs invalidación/Forget, cierre vs reinicio, y reconciliación/apertura vs reintento. Estas pruebas quedan pendientes y no se ejecutaron en esta fase.

### Próximo paso técnico

Diseñar la API concreta de unidad de trabajo y el refactor mínimo de `SQLiteConsistencyJournal` para que sus operaciones internas puedan reutilizar una conexión transaccional sin perder firma, canonicalización, CAS, idempotencia ni semántica de errores. Solo después de revisar ese diseño se implementará la autoridad SQLite. No se modifica todavía el esquema, no se añaden migraciones y no se activa ningún runtime.

**Validación:** no se ejecutaron pruebas ni build, de acuerdo con la instrucción vigente del propietario.



## ME-D4J — diseño de unidad de trabajo SQLite compartida

**Estado: diseño documentado; implementación pendiente.**

- Se documentó la API conceptual `SQLiteUnitOfWork`, propiedad de una única instancia `SQLiteDatabase`, con conexión configurada, `BEGIN IMMEDIATE`, validación de propietario y ciclo de vida limitado al contexto.
- El journal conservará sus métodos públicos compatibles, pero las mutaciones compuestas deberán delegar en operaciones internas que reciban la misma unidad de trabajo y no abran ni confirmen transacciones propias.
- La mutación del Recovery Gate, la transición autenticada, la idempotencia y el head del journal deberán confirmarse o revertirse en un solo commit.
- El diseño conserva canonicalización, envelopes, firma, CAS, idempotencia, reducer y DTO persistidos. No requiere alterar las migraciones V1–V3 salvo que el análisis posterior identifique datos realmente ausentes.
- Se mantiene explícito el límite distribuido: SQLite no hace atómica la aceptación remota de egress. El fencing requiere un protocolo verificable e idempotente en el receptor.
- Se documentaron pruebas pendientes de rollback, ownership, compatibilidad, fallos inyectados, concurrencia multiproceso, reinicio y reconciliación exacta.
- No se implementó código, no se modificó el esquema, no se ejecutaron pruebas ni build y no se activó ningún runtime.

Documento de diseño: [ME-D4J — unidad de trabajo SQLite compartida](ME-D4J-sqlite-unit-of-work.md).
Guía de configuración local: [Memory Engine README](../memory-engine/README.md).


## ME-D4K — SQLiteUnitOfWork base

**Estado: implementación añadida; pruebas pendientes.**

- `SQLiteUnitOfWork` se vincula a la instancia propietaria de `SQLiteDatabase`; la conexión solo se obtiene mediante el chequeo interno de propietario y actividad.
- `SQLiteDatabase.unit_of_work()` abre conexión configurada, ejecuta `BEGIN IMMEDIATE`, confirma al salir y revierte ante excepción.
- Se rechaza anidamiento en el mismo hilo y uso del handle tras terminar su contexto.
- `write_transaction()` conserva la interfaz anterior y delega el ciclo de vida transaccional en `unit_of_work()`.
- Se exportó `SQLiteUnitOfWork` desde `atlas.adapters.sqlite`.
- Tests nuevos cubren commit, rollback, propietario diferente, anidamiento y compatibilidad. No ejecutados.

**Fuera de alcance:** journal todavía no acepta una unidad de trabajo externa; Recovery Gate authority SQLite sigue sin implementación. No se ha demostrado atomicidad compuesta gate+journal. No hubo cambios de esquema, migraciones ni runtime. No se ejecutaron pruebas ni build.


## ME-D4L — append del journal con unidad de trabajo externa

- Implementado `SQLiteConsistencyJournal.append_transition_in(...)` para reutilizar una `SQLiteUnitOfWork` activa y de la misma base de datos.
- `append_transition(...)` mantiene su API pública y crea una UoW propia; la operación interna propaga fallos para permitir rollback de la composición.
- Se conservan canonicalización, firma/envelope, idempotencia, CAS y DTO persistidos.
- Se añadieron pruebas de reutilización y rollback ante fallo del signer; **pendientes de ejecución**.
- Alcance limitado a append de transiciones. Checkpoint, bootstrap del dominio y autoridad Recovery Gate no están integrados en esta frontera.


## ME-D4M — checkpoint con unidad de trabajo externa

- Implementado SQLiteConsistencyJournal.commit_checkpoint_in(...) para usar la UoW activa de la misma SQLiteDatabase.
- El wrapper commit_checkpoint(...) conserva su interfaz y estados públicos, delegando en una UoW propia.
- Checkpoint, marcador autenticado, registro idempotente y head CAS usan una sola conexión transaccional. Los errores de persistencia se propagan desde la ruta interna.
- Añadidas pruebas de éxito en UoW externa y rollback compuesto ante fallo de inserción del marcador; **pendientes de ejecución**.
- Recovery Gate, autoridad SQLite concreta y egress protegido siguen pendientes.

## ME-D4N — adaptador SQLite del Recovery Gate

- Implementado LocalSQLiteRecoveryGateAdapter, vinculado al SQLiteConsistencyJournal exacto y a su SQLiteDatabase.
- close_recovery_gate confirma RECOVERY_CLOSED y proyección cerrada en una única SQLiteUnitOfWork.
- reconcile_and_open_recovery_gate valida VerifiedRecoveryCompletionReceipt y confirma RECOVERY_RECONCILED más proyección abierta en el mismo commit.
- ensure_recovery_gate_closed/open restauran únicamente el cierre más reciente que demuestra la proyección local verificada.
- Añadida composición gate-only con RecoveryJournalCoordinator; no es la autoridad completa ProtectedMemoryRecoveryAuthorityPort.
- Añadidas pruebas de éxito, rollback, recibo/inventario exacto, restauración y concurrencia. Pendientes de ejecución.
- Sin cambios de esquema: los campos de gate ya existen desde V1.
- No se implementaron todavía admisión, Forget/invalidation ni egress protegido sobre la misma UoW. No se afirma linealizabilidad global.
- El perfil local no tiene anti-rollback externo. No se activó runtime ni producción.

Diseño: [ME-D4N — Recovery Gate SQLite](ME-D4N-sqlite-recovery-gate.md).


## ME-D4O — bloqueo de bootstrap e integración

La inspección de la implementación SQLite encontró que un dominio nuevo inicia con `recovery_gate_state='closed'` por default y no existe una operación autenticada de bootstrap que pueda abrirlo. `ensure_recovery_gate_open` exige un `RECOVERY_RECONCILED` verificado; ese evento no es una prueba de bootstrap y el coordinador no genera una recuperación terminal para un dominio vacío.

Se documentó el diseño ME-D4O y la secuencia A–E: bootstrap autenticado; admisión durable; egress durable; lifecycle/Forget/invalidation; composición de autoridad completa. Se detuvo la implementación de admisión/egress hasta resolver el contrato de bootstrap. No se modificó esquema ni runtime. No se ejecutaron pruebas/build/CI.

Diseño: [ME-D4O — bootstrap seguro e integración](ME-D4O-sqlite-authority-bootstrap-and-integration.md).


## ME-D4O — corrección de perfiles por Trust Anchor opcional

**Decisión aplicada — 14 de noviembre de 2026.**

La revisión de ME-03K-B, ME-03K-C y Contrato de diseño Atlas v1 §20.6 confirmó que Trust Anchor externo es opcional y su implementación queda postergada hasta la etapa final. El baseline de las etapas actuales es LOCAL, en un único servidor.

Se corrigió la interpretación anterior que había convertido el proveedor externo en requisito previo para ME-D4O-B–E:

- ME-D4O-A ahora define bootstrap por perfil. El baseline LOCAL no requiere Trust Anchor externo, pero sí exige autorización explícita y verificable del propietario, evento de génesis autenticado localmente y atomicidad de evento/head/idempotencia/gate en una misma SQLiteUnitOfWork.
- El perfil ANCHORED queda opt-in y futuro. Si se selecciona, la ausencia o discrepancia del proveedor mantiene el gate cerrado; nunca hay fallback automático a LOCAL.
- ME-D4O-B (admisión), D4O-C (egress), D4O-D (lifecycle/Forget/invalidation) y D4O-E (composición) pueden desarrollarse para LOCAL sin implementar ahora el proveedor externo.
- Esto no habilita runtime protegido: el bootstrap LOCAL requiere resolver la evidencia de acción directa del propietario, aún pendiente en docs/contracts/memory.md §8, y completar atomicidad, composición y pruebas.
- El perfil LOCAL no demuestra anti-rollback externo. Las restauraciones que puedan preceder a Forget, fencing o cierres requeridos permanecen bloqueadas hasta reconciliación contra una fuente independiente aprobada. La integridad del backup no basta.
- La aceptación remota de egress continúa requiriendo idempotencia/fencing verificable en el receptor; SQLite no atomiza el transporte.

Documentos corregidos:
- [ME-D4O-A — bootstrap por perfil](ME-D4O-A-authenticated-domain-bootstrap.md).
- [ME-D4O — integración de autoridad SQLite por perfiles](ME-D4O-sqlite-authority-bootstrap-and-integration.md).

No se modificó código, esquema, migraciones ni runtime. No se ejecutaron pruebas, build ni CI.
