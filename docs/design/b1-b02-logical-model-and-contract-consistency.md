# B1-B-02 — Modelo lógico integrado y matriz de consistencia contractual

**Estado:** diseño lógico consolidado preliminar; no constituye contrato físico ni autorización de implementación.  
**Rama documental:** `docs/b1-b02-logical-model-and-next-phase`  
**Base normativa:** Contrato Atlas v1 revisión 4 y enmienda B1-A-06.  
**Alcance:** integrar Memory, Identity, Project, Environment, CAM, Consistency e Infrastructure; identificar invariantes, fronteras transaccionales, discrepancias y siguiente fase.

---

## 1. Propósito y autoridad

Este documento consolida el diseño lógico trabajado en B1-B-02 y ejecuta la revisión cruzada recomendada antes de definir tablas SQLite.

Orden de autoridad:

1. Contrato principal Atlas v1, revisión 4.
2. Enmienda normativa B1-A-06.
3. Contratos específicos vigentes (DM-01, ME-03F y contratos D4O relacionados).
4. Este documento, como consolidación de diseño y registro de propuestas técnicas.

Si este documento propone una solución que modifica o precisa un contrato superior, la propuesta no prevalece hasta que se apruebe la correspondiente enmienda. Una propuesta aquí descrita no se convierte por sí sola en decisión normativa.

La rama y el archivo son documentales. No se han creado tablas, migraciones, repositorios ni cambios de runtime.

## 2. Decisiones B1-B-02 ya aprobadas

Las siguientes decisiones son baseline aprobado y no deben reabrirse como si faltara decisión del propietario:

1. **Persistencia local compartida:** una única base SQLite local para Atlas, con dominios lógicos separados y propiedad de tablas por dominio.
2. **Unidad de trabajo:** usar `SQLiteUnitOfWork` para operaciones que realmente requieran atomicidad local compartida; no permitir escrituras cruzadas arbitrarias entre dominios.
3. **Memory payload:** mantener el contenido fuera de SQLite. SQLite conserva metadatos y referencias opacas; no payloads, chunks, embeddings, snippets, hashes de contenido ni derivados reconstruibles.
4. **PRIVATE authorization:** entidad CAM propia, independiente de Grants PROJECT, reconocida por Consistency como autoridad `PRIVATE_MEMORY_AUTHORIZATION`.
5. **Identity legacy:** conservar tipos `AGENT/WATCHER/SYSTEM` y estados `ACTIVE/SUSPENDED/REVOKED`; no convertir automáticamente al modelo nuevo.
6. **Consumer identity:** `consumer_id` es distinto de `identity_id`. Su fuente canónica verificable aún no está seleccionada. No crear una tabla `consumers` sin autoridad aprobada.
7. **Runtime:** separar lifecycle de Project/Environment de `desired runtime state` y `observed runtime state`. Broker es frontera de ejecución, no autoridad canónica de Project/Environment.
8. **Auditoría:** Consistency Journal registra transiciones coordinadas. Una auditoría administrativa/de seguridad separada solo se añade si existe propósito, acceso y retención propios; no duplicar el journal en una tabla genérica de eventos.
9. **Compatibilidad:** preservar migraciones existentes y schema v4. No reconstruir la base ni reinterpretar tablas históricas.

Estas decisiones fijan arquitectura lógica, no seleccionan todavía todos los campos, índices, restricciones, formatos, proveedores externos o políticas de retención.

## 3. Modelo lógico integrado de siete dominios

### 3.1 Memory

Responsabilidad: identidad lógica de la memoria, owner, scope, revisión, puntero vigente, versiones, propuestas y procedencia.

Agregados conceptuales:

- `Memory`: `memory_id`, owner, scope PRIVATE/PROJECT, `current_approved_version_id`, revision y timestamps.
- `MemoryVersion`: `version_id`, `memory_id`, número, clasificación, estado, parent version, revisión y referencia opaca al payload externo.
- `MemoryProposal`: intención CREATE_MEMORY/NEW_VERSION, memoria/versión exactas, submitter, fecha e idempotencia.
- `MemoryProvenance`: procedencia inmutable de cada versión, con referencias opacas.

Invariantes:
- Memory y su scope/owner son inmutables en operaciones ordinarias; no se habilita transferencia de owner ni reclasificación de scope.
- Una versión pertenece a exactamente una Memory; los números de versión no se reutilizan.
- El puntero vigente solo puede señalar una versión APPROVED de esa misma Memory.
- La propuesta no concede permisos ni demuestra que su submitter sea owner.
- Los metadatos canónicos se resuelven por `MemoryMetadataPort`; los consumidores no pueden sustituirlos con valores de contexto.
- El contenido no atraviesa SQLite ni se devuelve crudo fuera de Memory Gateway.

### 3.2 Identity

Responsabilidad: identidades canónicas y bindings autenticados.

Agregados conceptuales:
- `Identity`: `identity_id`, tipo, estado, revision y timestamps.
- `IdentityBinding`: binding_id, identity_id, issuer, subject, estado, revision y timestamps.

Invariantes:
- `identity_id` es la identidad canónica; (issuer, subject) identifica un binding externo.
- Un binding no concede permisos.
- VerifiedIdentityContext es evidencia de operación, no identidad persistente ni Grant.
- No almacenar contraseñas, tokens ni secretos en estas entidades.
- Tipos/estados legacy se preservan; no hay conversión automática sin contrato de migración.

### 3.3 Project

Responsabilidad: identidad y lifecycle del ámbito lógico del proyecto.

Campos lógicos propuestos: `project_id`, estado ACTIVE/INACTIVE/DELETING/DELETED, revision, timestamps y tombstone.

Invariantes:
- ID canónico, inmutable y no reutilizable.
- Desactivar Project bloquea nuevas admisiones protegidas en sus Environments, sin cambiar automáticamente el estado individual de cada Environment.
- Reactivar Project no reactiva Environments ni Grants.
- El propietario canónico necesita alineación explícita con Identity; no equiparar silenciosamente owner_id, user_id e identity_id.

### 3.4 Environment

Responsabilidad: identidad, pertenencia inmutable a Project y lifecycle del entorno.

Campos lógicos propuestos: `environment_id`, `project_id`, estado ACTIVE/INACTIVE/DELETING/DELETED, revision, timestamps y tombstone.

Invariantes:
- Cada Environment pertenece a exactamente un Project; un Project puede tener cero o muchos Environments.
- No se permite transferencia ordinaria entre Projects.
- Reactivar Environment requiere Project ACTIVE y validaciones vigentes.
- Eliminar Project no puede dejar Environments huérfanos ni usar cascadas destructivas.
- Un Project no escribe directamente las tablas de Environment.

Runtime se separa del lifecycle:
- `EnvironmentRuntimeDesiredState`: intención de ejecución, generation, operation_id, actor y timestamp.
- `EnvironmentRuntimeObservation`: observación de fuente, generación observada, source_id, evidencia, observed_at y received_at.
- La observación no modifica por sí sola el estado deseado ni el lifecycle.
- El catálogo concreto de estados y la retención de observaciones siguen pendientes de contratos del adaptador real.

### 3.5 CAM

Responsabilidad: decisiones de autorización exactas, Grants PROJECT y autorizaciones PRIVATE.

Agregados independientes:
- PROJECT: Grant, permisos, scopes de recursos, renovaciones e idempotencia.
- PRIVATE: `PrivateMemoryConsumerAuthorization`, permisos, owner_identity_id, consumer_id, memory_id, estado y revisión.
- Consumo de pruebas one-shot vinculado a operación e idempotency key exactas, sin reutilización.

Invariantes:
- PRIVATE authorization no es Grant PROJECT y no depende de él.
- `consumer_id` no es `identity_id`.
- CAM no modifica Memory, Identity, Project o Environment.
- Los permisos PRIVATE aprobados son explícitos: `memory.read`, `memory.propose_update`, `memory.export`; no crear alias implícitos para otros permisos.
- `memory.propose_update` no aprueba/rechaza ni ejecuta Forget.

### 3.6 Consistency

Responsabilidad: orden durable de operaciones coordinadas, journal, invalidaciones, fencing, admisiones, recuperación y reconciliación.

Conserva:
- consistency domains, journal entries/operations, checkpoints y projections de ME-03K;
- schema v4 de authority-change: operations, idempotency, invalidations, affected admissions/routes, source results y recovery evidence.

Invariantes:
- Consistency coordina cambios; no copia Grants ni se convierte en autoridad de sus datos.
- Una admisión vincula snapshot CAM, actor, recurso, versión, scope, revisiones, generación y rutas exactas.
- La ruta de entrega se resuelve desde inventario confiable; no se aceptan listas arbitrarias del solicitante.
- Timeout, ausencia de heartbeat o resultado externo ambiguo no prueban cancelación.
- Recovery debe reconciliar antes de liberar fencing o admitir nuevas operaciones.
- PRIVATE_MEMORY_AUTHORIZATION es autoridad propia; no alias de GRANT.

### 3.7 Infrastructure

Responsabilidad: SQLite, migraciones, metadatos de schema y frontera UoW.

Invariantes:
- Una DB local compartida; ownership de tablas por dominio.
- UoW compartida únicamente cuando la atomicidad sea real y necesaria.
- Migraciones históricas inmutables; conservar schema v4.
- No reconstruir ni resetear DB para introducir el modelo.
- Proveedores externos de autenticación y almacenamiento de payload no participan en transacciones SQLite.
- Broker Registry no se utiliza como autoridad de Memory, Identity, Project, Environment o CAM.

## 4. Matriz de consistencia contractual

| Eje | Memory | Identity | Project | Environment | CAM | Consistency | Infrastructure |
|---|---|---|---|---|---|---|---|
| Identidad primaria | memory_id | identity_id | project_id | environment_id | grant_id / authorization_id | operation/admission IDs | schema/migration IDs |
| Owner / actor | owner de Memory; no autoriza por sí solo | identidad canónica y bindings | owner pendiente de alinear | no redefine owner de Project | actor/owner/consumer comprobados | conserva referencias exactas | no decide ownership |
| Scope / pertenencia | PRIVATE o PROJECT | no aplica | ámbito lógico | exactamente un Project | evalúa alcance exacto | vincula objetivo y revisiones | restricciones físicas |
| Lifecycle | version status y estado de Memory según contrato | tipos/estados nuevos y legacy separados | ACTIVE/INACTIVE/DELETING/DELETED | mismos estados, subordinado a Project | ACTIVE/REVOKING/REVOKED/EXPIRED para PRIVATE auth; estados de Grant según contrato | operación/admisión/recuperación | sin lifecycle de negocio |
| Revision | Memory y MemoryVersion | Identity y Binding | Project | Environment | Grant y autorización PRIVATE | generation/epoch y journal position | CAS/UoW |
| Idempotencia | propuestas/operaciones declaradas | cambios de identidad/binding si se especifican | cambios coordinados | cambios coordinados | Grants, renewals, PRIVATE auth y proof consumption | operation reservation y semantic idempotency | constraints transaccionales |
| Invalidación | cambios que afectan visibilidad/versiones | binding/identity changes | project lifecycle/revision | environment lifecycle/revision | Grant/PRIVATE authorization changes | serializa invalidation/fencing | atomicidad local |
| Runtime | no posee | no posee | no posee | lifecycle separado del runtime | autorización previa a operación | coordina operación/evidencia | almacenamiento local de referencias |
| Recuperación | no sirve contenido bajo estado ambiguo | no inventa bindings | no reabre proyectos automáticamente | no activa runtime automáticamente | no restaura permisos automáticamente | autoridad de reconciliación | WAL, migrations, UoW; no anti-rollback externo |
| Contenido / secretos | payload externo; sin secretos | sin credenciales | sin secretos | sin secretos | no guarda credenciales de autenticación | evidencia y refs opacas | secretos fuera de DB/documentación |

La tabla es una matriz de responsabilidades, no un mapeo definitivo a tablas o columnas.

## 5. Relaciones y fronteras de autoridad

Relaciones:
- Identity proporciona contexto de actor verificado a CAM.
- Memory conserva owner y scope canónicos; CAM consulta esos metadatos.
- Project/Environment proporcionan estado y revisión canónicos para autorizaciones PROJECT.
- CAM decide la operación exacta.
- Consistency coordina admisión, invalidación, fencing y recuperación.
- Memory Gateway es la única frontera de lectura/propuesta de Memory.
- Infrastructure provee persistencia compartida sin absorber reglas de dominio.

No permitido:
- Identity concede Grants o permisos PRIVATE.
- Project escribe Environment o CAM.
- Environment cambia Project o Broker state.
- CAM cambia owner/scope/version de Memory.
- Consistency replica datos completos de Grants o políticas CAM.
- Broker Registry sustituye autoridades de dominio.
- Consumers acceden directamente a SQLite, contenido, índices o stores de Memory.

## 6. Fronteras transaccionales propuestas

Las transacciones SQLite deben limitarse a cambios locales que puedan confirmarse de manera atómica.

| Operación | Frontera lógica requerida | Coordinación externa |
|---|---|---|
| Crear Memory | Memory + primera Version + Proposal + idempotencia en una UoW | Payload se prepara externamente antes; objeto huérfano no visible si UoW falla |
| Proponer nueva Version | CAS Memory + Version + Proposal + idempotencia | Payload externo preparado previamente |
| Aprobar Version | CAS Memory + transiciones de versiones + puntero vigente + consumo durable de prueba cuando corresponda | Verificación de identidad/prueba fuera de la transacción; Consistency coordina invalidación/fencing |
| Crear/revocar binding | Identity/Binding y revisión; invalidación coordinada si afecta admisiones | Authentication Authority fuera de UoW |
| Crear/renovar Grant | CAM + historial/idempotencia correspondiente | Decisión/validación contextual previa |
| Revocar Grant/PRIVATE auth | Reserva durable, invalidación/fencing, CAS de autoridad, source result y reconciliación | Endpoints/rutas externos deben confirmar fencing |
| Cambiar lifecycle Project/Environment | CAS de entidad y revisión; coordinación de admisiones afectadas | Runtime/Broker por operación explícita, nunca dentro de una falsa atomicidad SQLite |
| Admitir lectura | Snapshot exacto + revisiones + rutas + admission durable, serializados con invalidaciones | Egress valida fencing en cada unidad |
| Recuperar operación | Journal/evidencia/proyecciones y fuente canónica reconciliadas antes de liberar gate | No inferir éxito por timeout |

No se afirma que todos estos coordinadores o repositorios existan hoy. La tabla expresa las garantías objetivo.

## 7. Discrepancias y propuestas que requieren resolución contractual

### D-01 — Semántica del propietario de Memory

**Hecho inspeccionado:** DM-01 tipa `Memory.owner_id` como `UserId`; B1-A-06 define PRIVATE authorization mediante `owner_identity_id`; Identity usa `identity_id` canónico y binding externo (issuer, subject).

**Riesgo:** dos identificadores distintos podrían representar al propietario y divergir; no se puede asumir que user_id sea identity_id.

**Propuesta técnica refinada tras revisar DM-01 §6.4 y B1-A-06 §§2.1, 4.2 y 5:**

- Conservar `Memory.owner_id: UserId` como el subject/user ID canónico al que está ligada la memoria, sin reinterpretarlo como `identity_id`.
- `owner_identity_id` en PRIVATE authorization representa la identidad interna canónica del propietario.
- La relación entre ambos valores se demuestra mediante un binding verificado de Identity Authority: el binding del propietario resuelve el subject exacto almacenado en `Memory.owner_id` hacia el `identity_id` exacto usado por CAM.
- No se exige igualdad textual entre `owner_id` y `owner_identity_id`; se exige una relación autenticada y vigente. Correo, nombre, ID declarado por el caller o igualdad casual de strings no sirven como prueba.
- Para una lectura PRIVATE del propietario, el sujeto autenticado debe coincidir con `Memory.owner_id`, y la identidad USER del actor debe estar vinculada a ese sujeto. Para autorización PRIVATE delegada, CAM debe comprobar que `owner_identity_id` corresponde al propietario de la memoria mediante esa misma fuente de identidad confiable.

Esta interpretación preserva los tipos y semántica explícitos de DM-01, y da significado verificable al `owner_identity_id` de B1-A-06 sin duplicar ni confundir identidades. Debe registrarse como aclaración contractual conjunta antes del esquema físico.

**Estado:** recomendación técnica, pendiente de aceptación/registro contractual; no cambiar el tipo del campo ni realizar migraciones por inferencia.

### D-02 — Payload externo y atomicidad

**Hecho aprobado:** payload fuera de SQLite; metadatos y referencia opaca dentro.

**Riesgo:** no existe atomicidad ACID entre SQLite y un proveedor externo no seleccionado.

**Propuesta técnica:** staging inmutable del payload, validación y obtención de referencia opaca antes de la UoW. La UoW confirma Memory/Version/Proposal y referencia. Si falla, el objeto staged queda inaccesible para Gateway y se registra para limpieza controlada; no se expone contenido huérfano.

**Pendiente:** contrato del Content Store: put immutable, read by opaque ref, integrity/evidence, lifecycle, quarantine, orphan inventory/cleanup, backup/restore, retention y failure semantics. No seleccionar proveedor en B1-B-02.

### D-03 — Admisiones activas al aprobar una nueva versión

**Hecho contractual:** snapshots y admisiones se vinculan a revisiones exactas; los cambios de autoridad requieren invalidación/fencing y el egress valida generación vigente.

**Riesgo:** una admisión antigua podría continuar usando una revisión de Memory anterior al cambio de puntero.

**Propuesta técnica conservadora:** al aprobar una versión y cambiar la revisión/puntero vigente, cerrar nuevas admisiones bajo la revisión anterior e invalidar/fencear admisiones previas afectadas antes de considerar efectivo el cambio. La política de finalización/cancelación debe respetar ME-03 y no usar timeout como prueba de fencing.

**Estado:** requiere precisión contractual del alcance de invalidación y de si una entrega previa puede completar bajo reglas explícitas. No implementado.

### D-04 — Fuente canónica de consumer_id

**Hecho aprobado:** consumer_id distinto de identity_id; no crear tabla consumers sin autoridad aprobada.

**Propuesta:** mantenerlo como identificador opaco suministrado por un registro/autoridad de consumidores autenticado y verificable. Seleccionar esa autoridad como subfase independiente; CAM rechaza ausencia, desconocimiento o binding no verificable.

**Estado:** proveedor/registro canónico pendiente. No crear tabla ni inferir consumer_id desde identidad.

### D-05 — Consistency domains y epochs

**Hecho:** el modelo usa revisiones monotónicas por autoridad y el journal conserva dominios/épocas.

**Riesgo:** una única época global podría acoplar autoridades sin necesidad; dominios separados sin orden común podrían permitir carreras entre admisión y revocación.

**Propuesta:** definir dominios de consistencia por conjunto mínimo de autoridades que deban serializarse juntas. Cada operación declara el conjunto exacto de dominios y sus posiciones/generaciones; una operación cross-domain debe adquirirlos en orden determinista o usar un coordinador que garantice orden común. No comparar revisiones de autoridades distintas.

**Estado:** requiere contraste completo con ME-03K, ME-03F y D4O-F/G/H antes de fijar tabla o algoritmo.

### D-06 — Inventario de admissions y routes

**Hecho:** ME-03 define ReadAdmission y DeliveryRouteSet; el código tiene modelos/puertos, pero no se ha acreditado implementación SQLite canónica de admit_read ni un inventario productivo completo de rutas.

**Propuesta:** reutilizar proyecciones/inventarios ME-03K y contratos de route registry existentes. No crear segunda tabla de admissions o routes hasta demostrar que el modelo existente no cubre la necesidad.

**Estado:** inspección de compatibilidad física pendiente.

### D-07 — PRIVATE_MEMORY_AUTHORIZATION en D4O-F

**Hecho aprobado:** PRIVATE authorization es autoridad de dominio propia, no alias de GRANT.

**Propuesta:** ampliar AuthorityKind, revision set, invalidation mapping, source CAS, recovery evidence y pruebas para identificar exactamente PRIVATE_MEMORY_AUTHORIZATION. La operación debe conservar consumer_id, owner_identity_id y memory_id exactos.

**Estado:** requiere enmienda/compatibilidad D4O-F y validación de D4O-G/H; no implementar por alias de GRANT.

### 7.1 Contraste adicional con ME-03F, ME-03H y ME-03K

La inspección de los contratos y modelos disponibles precisa las discrepancias anteriores:

**Admisión y recuperación exacta**
- ME-03F define `READ_ADMITTED` schema_version 2 con `scope_kind` y `scope_project_id`, exige `owner_id`, actor, request, IDs exactos, revisiones, generación y rutas; la proyección conserva `admitted_at`, clasificación de recuperabilidad y recibo terminal.
- ME-03F conserva v1 para replay histórico, pero una admisión v1 no es recuperable como objetivo vivo porque no conserva scope exacto. No se infiere PRIVATE/PROJECT.
- ME-03H exige recuperar todas las admisiones no terminales, tanto v1 como v2, como trabajo unresolved/fenced; todas las rutas persistidas se vuelven a cercar con una generación superior. Recibos históricos no omiten el nuevo fencing.
- ME-03H es un contrato de orquestación pura/fakes. No acredita autoridad durable que cierre el gate, contacte endpoints, persista todos los recibos y reconcilie atómicamente.

**No duplicar schema**
- ME-03K define `journal_entries`, `journal_operations`, `checkpoints`, `checkpoint_projections` e inventarios operativos como base del perfil local.
- Las admisiones se representan en transiciones/proyecciones de journal y sus inventarios; no se debe crear una segunda tabla canónica de admissions sin demostrar una necesidad no cubierta por esas estructuras.
- Las rutas deben seguir derivándose de un registro confiable y conservarse exactamente en la transición/proyección; la lista del caller no puede ampliar el inventario.
- ME-03K SQLite migration v2 refuerza la FK compuesta de `journal_operations` a `journal_entries`. Es distinta de `READ_ADMITTED` schema_version 2 de ME-03F. No comparten contador ni semántica de versión.

**Brecha PRIVATE en AuthorityRevisionSet**
- El código inspeccionado declara AuthorityKind MEMORY, MEMORY_VERSION, IDENTITY, PROJECT, ENVIRONMENT, GRANT y CONSISTENCY.
- `AuthorizationRevisionSet` solo tiene slots de revisión para Memory, Version, Identity y, opcionalmente, Project, Environment y Grant.
- El modelo de transición `INVALIDATION_CLOSED` depende de AuthorityKind. Por tanto, PRIVATE_MEMORY_AUTHORIZATION no puede expresarse actualmente como autoridad de revisión/invalidation independiente sin ampliar el contrato y sus validadores/reducer.
- La ampliación debe ser aditiva y explícita: nuevo AuthorityKind, revisión exacta de autorización PRIVATE donde aplique, validación de scope PRIVATE/PROJECT, invalidation mapping, source CAS y recuperación. No se debe mapear a GRANT ni hacer que PRIVATE dependa de Grant.

**Alcance real de D4O-B**
- ME-D4O-B define secuencia de admisión durable dentro de una UoW, revalidación de revisiones, idempotencia exacta y uso de READ_ADMITTED v2.
- El mismo documento declara que el coordinador/adaptadores de admisión siguen pendientes, que el bootstrap LOCAL es prerrequisito para operación y que D4O-B no habilita lecturas operativas.
- Por ello, contratos neutrales, schema de transición v2 y reducer no deben presentarse como `admit_read` durable completo.

**Perfil de recuperación**
- El baseline SQLite aprobado es LOCAL, un único servidor Debian, sin Trust Anchor externo ni garantía anti-rollback externa.
- El perfil ANCHORED se posterga a la etapa final; si se selecciona, no puede degradar automáticamente a LOCAL.
- Esta limitación no elimina la obligación de autenticidad local, fencing, idempotencia, atomicidad y recuperación fail-closed.

### 7.2 Bloqueos concretos para B1-B-03A

Antes del diseño físico se deben cerrar, con evidencia y contratos:

1. **Owner:** alinear `Memory.owner_id: UserId`, `AuthorizationSnapshot.owner_id`, el sujeto PRIVATE y `PrivateMemoryConsumerAuthorization.owner_identity_id`. Definir el binding canónico sin reinterpretar IDs existentes.
2. **Consumer:** identificar la autoridad que emite/verifica `consumer_id` y cómo se vincula con actor/identidad sin hacerlos equivalentes.
3. **PRIVATE revision:** definir revisión, snapshot, idempotencia e invalidación de `PRIVATE_MEMORY_AUTHORIZATION` a través de CAM, Consistency y recuperación.
4. **Read admission:** comprobar que el inventario ME-03K y las proyecciones ME-03F/H cubren admisión, rutas, recibos y recuperación; documentar únicamente las tablas auxiliares estrictamente necesarias.
5. **Consistency domains:** fijar el conjunto mínimo de autoridades que comparte orden serializable para cada operación, evitando tanto época global innecesaria como dominios aislados con carreras.
6. **Content Store:** aprobar el contrato de staging, referencia opaca, lectura condicional, cuarentena, inventario de huérfanos, backup/restore y retención antes de seleccionar proveedor.
7. **Invalidation on approval:** definir qué admisiones/versiones se cercan al mover el puntero vigente y qué evidencia permite completar o cancelar una entrega anterior.

Estos puntos son bloqueos de diseño físico, no una solicitud de modificar la DB actual.

## 8. Estado de implementación y límites conocidos

Evidencia de código/documentación inspeccionada en la rama documental base:

- `src/atlas/memory/models.py` contiene modelos inmutables Memory, MemoryScope, MemoryVersion, MemoryProposal y MemoryProvenance.
- `src/atlas/memory/ports/metadata.py` define puertos MemoryMetadataPort, ProjectMetadataPort y EnvironmentMetadataPort sin contenido.
- `MemoryMetadataResolver` valida tipo e identidad exacta del recurso y falla cerrado ante errores, excepciones o discrepancias.
- `src/atlas/memory/consistency.py` define AuthorityKind, snapshots, revision sets, admissions y recibos tipados; la presencia de tipos no acredita el flujo completo.
- `SQLiteDatabase` y `SQLiteUnitOfWork` proporcionan SQLite file-backed, WAL, foreign keys, synchronous FULL, BEGIN IMMEDIATE y migraciones ordenadas/inmutables.
- Schema v4 contiene el almacenamiento durable de authority-change descrito en D4O-I C.4.1.

No acreditado como completo:
- Repositorios SQLite canónicos para los siete dominios.
- Content Store externo y su ciclo de vida.
- Coordinador completo de revocación y cambios de autoridad.
- `admit_read` durable operativo.
- Inventario productivo completo de routes/endpoints y fencing extremo a extremo.
- PRIVATE authorization persistida y coordinada.
- Identity/Project/Environment persistidos y migrados.
- Anti-rollback externo del perfil LOCAL.
- Runtime protegido habilitado.

El inventario es una fotografía de fuentes inspeccionadas; antes de implementar debe repetirse sobre el commit exacto de trabajo.

## 9. Próxima fase recomendada: B1-B-03 — Diseño físico y plan de migraciones

B1-B-02 debe cerrarse primero con resolución/aceptación de D-01 a D-07. Después:

### B1-B-03A — Cierre de contratos y dependencias
1. Resolver semántica canónica de owner_id / owner_identity_id.
2. Definir la autoridad de consumer_id.
3. Precisar la política de invalidación de admisiones por aprobación de versión.
4. Completar compatibilidad PRIVATE_MEMORY_AUTHORIZATION con D4O-F/G/H.
5. Verificar el inventario real de admissions/routes/projections de ME-03K.
6. Definir conjuntos de consistency domains/epochs.
7. Aprobar el contrato lógico del Content Store sin seleccionar aún proveedor si no hace falta.

### B1-B-03B — Diseño físico SQLite
1. Inventariar el esquema/migraciones existentes y sus checksums; preservar v4.
2. Mapear cada agregado a tablas de propiedad de dominio, claves, FKs, índices, unique constraints y checks.
3. Definir CAS, revisiones, idempotency keys y relaciones de operation_id.
4. Diseñar UoW por caso de uso y documentar dónde la atomicidad no es posible.
5. Definir estrategia de migración incremental y rollback seguro sin reescribir migraciones históricas.
6. Preparar matriz de compatibilidad y escenarios de fallo/recuperación.

### B1-B-03C — Validación antes de implementación
1. Revisar el diseño contra contratos raíz, B1-A-06, DM-01, ME-03F/K y D4O-F/G/H.
2. Crear pruebas de conformidad de esquema y migración en DB temporal, sin tocar datos reales.
3. Revisar aislamiento por consumer/project y ausencia de cross-write.
4. Revisar Forget, fencing y recovery para impedir reaperturas inseguras.
5. Presentar el esquema físico y el plan de migración para aprobación explícita antes de escribir migraciones.

**Fuera de alcance de B1-B-03:** implementar repositorios, migrar datos reales, cambiar runtime, habilitar Memory Gateway protegido, abrir Recovery Gate, modificar Broker o desplegar.

## 10. Criterios de salida de B1-B-02

B1-B-02 se considerará documentalmente listo para diseño físico cuando:
- los siete dominios tengan ownership y autoridad inequívocos;
- las relaciones y cardinalidades estén documentadas;
- cada cambio protegido tenga revisión, idempotencia e invalidación definidos;
- las fronteras UoW y los límites externos estén explícitos;
- D-01 a D-07 estén resueltos o aislados como bloqueos explícitos aprobados;
- las proyecciones existentes de admissions/routes hayan sido contrastadas;
- no se duplique el schema v4 ni se cree una autoridad paralela.

La aprobación de este documento no implica implementación. Toda migración y código requiere fase y alcance aprobados por separado.
