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

**Propuesta técnica:** hacer que el propietario de Memory se refiera semánticamente al `identity_id` canónico. Mantener el nombre de campo `owner_id` solo si el contrato documenta explícitamente que su valor es identity_id, o migrar a `owner_identity_id` mediante enmienda y migración compatible. No almacenar el subject externo como owner.

**Estado:** propuesta pendiente de aprobación contractual; no cambiar DM-01 por inferencia.

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
