# Frontera de consistencia para operaciones del Assistant

> Estado: decisión de arquitectura F2.3.4.
> Rama: `feature/terminal-commands`.
> Alcance: definir las garantías necesarias antes de conectar capacidades del Assistant con CAM.
> Este documento no implementa autorización, admisión ni ejecución.

## 1. Problema

`OperationAuthorizationEvidence` enlaza una decisión CAM con actor, Grant, proyecto, entorno, acción, recurso y revisiones. La comparación local de esos claims y su ventana temporal no demuestra que las revisiones sigan vigentes ni impide que una revocación compita con la operación.

Un verificador que consulte cada repositorio por separado tiene una ventana TOCTOU: una fuente puede cambiar después de su lectura y antes del efecto. Una secuencia de lecturas exitosas no es una barrera de concurrencia.

## 2. Decisión

La autorización de una operación con efectos requiere una **admisión de operación** emitida por una autoridad de consistencia común. La admisión debe vincular, como mínimo:

- identidad inmutable de la operación y su idempotency key;
- decisión/evidencia CAM exacta y request ID;
- actor y revisión de identidad;
- Grant y revisión, cuando aplique;
- proyecto y revisión;
- entorno y revisión;
- acción, tipo e ID de recurso;
- dominio, época y secuencia de consistencia;
- instante UTC y estado de admisión.

Una admisión no es un permiso transferible ni una autorización general. Es válida solo para esa operación, parámetros, actor, proyecto, entorno y recurso exactos. No puede reutilizarse para otra operación ni para un retry semánticamente distinto.

## 3. Orden obligatorio

Toda mutación de una fuente de autoridad debe pasar por el mismo coordinador de consistencia que controla las admisiones:

1. Registrar/reservar el cambio de autoridad con identidad durable e idempotencia.
2. Marcar la autoridad afectada como invalidación pendiente y cerrar nuevas admisiones incompatibles.
3. Aplicar fencing a las operaciones/admisiones afectadas.
4. Mutar la fuente de autoridad con compare-and-swap de la revisión esperada.
5. Reconciliar las operaciones afectadas y cerrar la invalidación.
6. Permitir nuevas admisiones solo después de que el estado reconciliado sea demostrable.

Si cualquier fase queda incierta, la autoridad afectada permanece bloqueada/fenced. Un timeout, excepción o reinicio no equivale a abortar ni a completar.

La admisión sigue el orden inverso de forma coordinada: comprobar que no existe invalidación aplicable, validar las fuentes exactas, releer el head de consistencia y registrar la admisión dentro de la misma unidad de serialización. Si la posición cambió, abortar y volver a validar desde el principio.

## 4. Perfil local SQLite: garantía y condiciones

`SQLiteUnitOfWork` abre `BEGIN IMMEDIATE`. Esto puede proporcionar serialización local entre admisiones y mutaciones **solo si se cumplen todas** estas condiciones:

- existe una única instancia lógica de autoridad de consistencia y una única base SQLite para las fuentes que participan;
- identidad, Grant, proyecto, entorno, revisiones, invalidaciones, admisiones y journal se leen/escriben mediante la misma `SQLiteDatabase` y la misma `SQLiteUnitOfWork`;
- todos los caminos de mutación usan el coordinador; ningún servicio escribe directamente a los repositorios;
- la admisión lee las fuentes y registra su decisión dentro de la transacción `BEGIN IMMEDIATE`;
- una mutación de autoridad no puede confirmar su cambio sin registrar y reconciliar su invalidación en el protocolo;
- la autoridad no se compone de lecturas cacheadas ni de snapshots externos sin validación.

Si alguna fuente no participa en esa transacción, no se declara consistencia atómica. Un lock de proceso, una notificación eventual o una segunda lectura fuera de la transacción no sustituyen estas condiciones.

La serialización SQLite es local a la base/archivo compartido; no constituye un protocolo distribuido ni una garantía entre bases independientes.

## 5. Operaciones de workspace y límite de efectos

### Lecturas

Para `workspace.list` y `workspace.read`, la ruta de prueba podrá considerarse protegida únicamente cuando la admisión y la lectura estén dentro de una sección de consistencia que impida confirmar una revocación concurrente hasta que termine la lectura, y todas las autoridades participen en esa misma barrera.

La lectura debe limitarse al workspace registrado y a rutas canónicas permitidas. No se permite seguir symlinks ni escapar de la raíz. El resultado se publica solo después de completar la operación admitida.

### Escrituras

No se habilitan en esta fase. Una transacción SQLite no puede hacer commit atómico de una modificación del sistema de archivos. Antes de permitir `workspace.write` se requiere un protocolo durable específico: staging, identidad/idempotencia de operación, commit/rename controlado, reconciliación tras crash y tratamiento explícito de resultados inciertos. La aprobación humana tampoco resuelve esa atomicidad.

## 6. Reutilización de componentes existentes

- `OperationAuthorizationEvidence` conserva los claims exactos y las cuatro revisiones.
- `OperationAuthorizationEvidenceVerificationService` conserva la validación local y delega la verificación confiable; su estado VERIFIED no se convierte por sí solo en admisión ni permiso de ejecución.
- `RevisionValidationPort` es una referencia de diseño útil para el patrón invalidation-first + posición de consistencia, pero sigue siendo específico de Memory y de `AuthorizationSnapshot`. No se reutiliza como puerto genérico del Assistant.
- `ConsistencyPosition` expresa dominio/época/secuencia; no proporciona por sí mismo almacenamiento ni exclusión mutua.
- `AuthorityChangeCoordinatorPort` expresa fases de coordinación, pero no hay adaptador concreto en esta rama.
- `SQLiteAuthorityChangeStore` conserva reservas e idempotencia, pero no ejecuta fencing, mutación de fuentes ni reconciliación.
- `SQLiteIdentityAuthority` ofrece CAS para identidad, pero no prueba que las demás autoridades compartan la misma transacción.
- `GrantRepository` es un contrato CRUD y no impone por sí mismo el protocolo de invalidación.

No se debe combinar estas piezas en un falso coordinador mediante composición superficial.

## 7. Criterios de aceptación antes de implementar el adaptador

1. Identificar los repositorios canónicos de Identity, Grant, Project y Environment y sus bases de datos reales.
2. Demostrar que todos comparten una instancia de `SQLiteDatabase` y aceptan la misma `SQLiteUnitOfWork`, o diseñar un fencing equivalente que cubra explícitamente las fuentes externas.
3. Implementar el coordinador durable completo, no solo su store: reserva, invalidación, fencing, CAS de fuente, reconciliación y recuperación.
4. Probar concurrencia real entre admisión y revocación con conexiones independientes/procesos: nunca puede confirmarse una lectura admitida después de que una revocación incompatible haya cerrado su admisión.
5. Probar crash/restart en cada fase; la incertidumbre debe quedar bloqueada, nunca convertirse en ALLOW.
6. Probar cambio de cada una de las cuatro revisiones, cambio de proyecto/entorno, Grant expirado/revocado, actor suspendido/revocado, replay e idempotency key con parámetros alterados.
7. Solo entonces crear un adaptador de verificación/admisión para el perfil de solo lectura.
8. Mantener `workspace.write` y la integración CLI/runtime desconectadas hasta que tengan su propio protocolo probado.

## 8. Estado actual

- F2.3.1: contratos de evidencia y resultado, validados por el propietario.
- F2.3.2: servicio y puerto de verificación, validados por el propietario.
- F2.3.3a: revisiones de proyecto y entorno añadidas; el propietario reportó 925/925 pruebas aprobadas.
- F2.3.3b: inspección de autoridad y consistencia documentada.
- F2.3.4: esta decisión define la admisión común y las condiciones de consistencia; todavía no hay coordinador durable ni adaptador.
- No se ha conectado el verificador al runtime ni se ejecutan capacidades reales.

## 9. Próximo incremento

F2.3.5 debe ser una inspección de persistencia/composición: localizar exactamente dónde viven hoy Identity, Grant, Project y Environment, qué repositorios los modifican y qué instancias de base de datos usan. El resultado será una matriz fuente → repositorio → base de datos → UoW → caminos de mutación. No crear código de coordinador hasta que esa matriz confirme una estrategia implementable.


## 10. F2.3.5 — Inventario real de persistencia y composición

Inspección estática de la rama `feature/terminal-commands`:

| Fuente | Contrato/implementación encontrada | Persistencia/UoW | Caminos de cambio observados | Conclusión |
|---|---|---|---|---|
| Identity | `IdentityAuthorityPort` / `SQLiteIdentityAuthority` | SQLite propia recibida por `compose_sqlite_identity(path)`; `get_user` usa conexión independiente y `update_user_status` abre su propia UoW | `create_user`, CAS de estado | No comparte UoW con CAM/Grant por composición actual; CAS no registra invalidación común |
| Grant | `GrantRepository` Protocol; no se encontró adaptador SQLite concreto en `src/atlas/adapters/sqlite` | `AuthorizationUnitOfWork` agrupa Grants + renovaciones, pero no demuestra una UoW SQLite compartida con Identity/journal | `GrantManagementService.issue` escribe directamente al repositorio; renovación usa su UoW; revoke requiere coordinador inyectado y falla cerrado si falta | No existe persistencia canónica concreta común demostrada |
| Project | `ProjectMetadataPort` + `ProjectMetadata` tipados bajo Memory | Sin adaptador canónico de proyecto encontrado en el código de producción | No se encontró servicio/repositorio de ciclo de vida de proyectos | Fuente y UoW no definidas |
| Environment | `EnvironmentMetadataPort` + `EnvironmentMetadata` tipados bajo Memory | Sin adaptador canónico de entorno encontrado en el código de producción | No se encontró servicio/repositorio de ciclo de vida de entornos | Fuente y UoW no definidas |
| Consistency journal | `SQLiteConsistencyJournal`, composición local de journal | Recibe `SQLiteDatabase`; puede compartir archivo solo si composición lo hace explícitamente | Append/posición del journal; Recovery Gate separado | No prueba compartir DB con Identity/Grant/Project/Environment |
| Authority changes | `AuthorityChangeCoordinatorPort` + `SQLiteAuthorityChangeStore` | El store recibe SQLite, persiste reserva/idempotencia | No implementa invalidación, fencing, mutación de fuentes ni reconciliación | Coordinador completo no encontrado |

### Hallazgos concretos

- `compose_sqlite_identity(path)` crea una instancia nueva de `SQLiteDatabase` y su `SQLiteIdentityAuthority`; no acepta una instancia compartida desde una composición de aplicación.
- `SQLiteIdentityAuthority.update_user_status` hace CAS, pero no pasa por `AuthorityChangeCoordinatorPort` ni escribe un evento de invalidación en el journal.
- `GrantManagementService.issue` llama directamente a `GrantRepository.create`. La revocación está diseñada para delegar al coordinador, pero la configuración es opcional y falla cerrado cuando falta; no se encontró un coordinador concreto.
- `AuthorizationUnitOfWork` solo agrupa Grants y renovaciones. No declara una misma instancia `SQLiteDatabase`, ni incluye Identity, Project, Environment o consistency journal.
- Project/Environment solo aparecen como contratos de metadatos consumidos por Memory; no hay repositorios canónicos de producto identificados.
- `SQLiteConsistencyJournal` usa una instancia `SQLiteDatabase` inyectada. La composición de journal demuestra compartir esa instancia entre journal y algunos puertos de recuperación, no con las fuentes CAM.
- En `src/atlas/adapters/sqlite` no hay adaptador de Grant, Project o Environment en la rama inspeccionada.

### Resultado de F2.3.5

La estrategia de una única UoW SQLite para las cuatro autoridades **no es implementable con la composición actual sin introducir nuevas fuentes/adaptadores y cambiar caminos de mutación existentes**. No basta con añadir un verificador.

La ruta recomendada es una composición de autoridad local explícita que reciba una única instancia `SQLiteDatabase` y que sea dueña de los repositorios canónicos Identity, Grant, Project, Environment, el journal y las tablas de admisión/invalidation. Todos los servicios de mutación deben usar el coordinador de esa composición; los métodos directos actuales deberán convertirse en fachadas delegadas o quedar fuera de la composición protegida. No se debe mantener un segundo repositorio "de espejo" como fuente de verdad.

Antes de implementar, hay una decisión de alcance: ¿construir ahora esas cuatro fuentes canónicas mínimas para el perfil de prueba, o mantener el scope de F2 read-only sin autorización CAM integrada y avanzar primero con tareas/UX? No se ha cambiado código ni se ha habilitado ejecución.


## 11. F2.3.6 — Punto de composición compartida para Identity

Se añadió `compose_sqlite_identity_on_database(database)` en `atlas.adapters.sqlite.identity_composition`. Esta función acepta una instancia ya creada de `SQLiteDatabase`, aplica las migraciones de Identity y construye `SQLiteIdentityAuthority` usando exactamente esa misma instancia. No crea ni sustituye la base recibida. La composición standalone anterior `compose_sqlite_identity(path)` se conserva y delega en la nueva función, por compatibilidad.

Pruebas añadidas para verificar identidad de objeto de la base compartida, lectura/escritura canónica y rechazo de entradas que no sean `SQLiteDatabase`.

**Límite explícito:** este incremento solo abre el seam de composición para Identity. No crea todavía repositorios de Grant/Project/Environment, ni coordinador, invalidación, admisiones o fencing. El CAS de Identity sigue sin integrarse al protocolo común. No habilita operaciones del Assistant.


## 12. F2.3.7 — Persistencia canónica inicial de Grants

Se añadió la migración SQLite v7 `canonical_sqlite_grants` y `SQLiteGrantRepository`. El Grant completo (scope, IDs concretos, acciones, fechas y revisión) se conserva en una fila, con colecciones serializadas canónicamente. La escritura de actualización exige revisión siguiente y usa compare-and-swap (`WHERE revision = new_revision - 1`).

La base impone:
- unicidad de `grant_id`;
- revisión estrictamente incremental;
- identidad, propietario, sujeto, proyecto, entorno, tipo de recurso, scope y acciones inmutables;
- revocación terminal;
- retención del Grant como tombstone (sin DELETE).

Se añadió `SQLiteLocalAuthorityFoundation` como composición compartida inicial. Identity, GrantRepository y `SQLiteAuthorityChangeStore` verifican que usan exactamente la misma instancia `SQLiteDatabase`. La composición standalone de Identity se mantiene compatible.

Pruebas nuevas cubren round-trip, duplicados, aislamiento por propietario, orden estable, CAS obsoleto, tombstones, inmutabilidad de scope/acciones, revocación terminal, reapertura de DB y composición común. Las pruebas históricas de migración v6 se ajustaron para seguir partiendo de schema v5, sin alterar las migraciones anteriores.

**Límites:** Grant issue y renewal todavía no están compuestos por un UoW SQLite compartido; los cambios de Identity/Grant aún no pasan por un coordinador de invalidación común. Project y Environment no tienen fuentes canónicas. No hay admisión de operaciones ni ejecución del Assistant. Requiere suite local completa antes de considerarse validado.

## 13. F2.3.8 — UoW SQLite para Grant y renovaciones

La migración v8 añade `authorization_grant_renewals`, con vínculo FK al Grant, versión CAS, binding inmutable, decisión terminal, evidencia de decisión inmutable y retención como tombstone.

`SQLiteAuthorizationUnitOfWorkFactory` crea una unidad sobre el `SQLiteDatabase` canónico. Dentro de una unidad, `SQLiteGrantRepository` y `SQLiteGrantRenewalRepository` reciben el mismo `SQLiteUnitOfWork` y ejecutan sus consultas/escrituras sobre la misma conexión `BEGIN IMMEDIATE`. La unidad confirma únicamente al salir sin excepción y después de una llamada explícita a `commit()`; sin esa llamada, o ante cualquier excepción incluso posterior a la solicitud de commit, revierte la transacción.

`GrantRenewalService` ya consume el puerto `AuthorizationUnitOfWork`, por lo que puede operar con esta fábrica SQLite para crear solicitudes, aprobar/rechazar y actualizar Grant + decisión de renovación atómicamente. `GrantManagementService.issue` acepta ahora una fábrica opcional y, cuando se configura, hace la comprobación de unicidad y el INSERT dentro de la misma unidad.

**Límites:** el servicio de emisión conserva modo legacy si no se inyecta UoW; la composición aún no fuerza que toda instancia de GrantManagementService use la fábrica. Revocación sigue dependiendo del coordinador CAM y no se cambia aquí. Esto no implementa aún invalidación/fencing común ni admisión de operaciones.

## 14. F2.3.9 — Fuentes canónicas iniciales de Project y Environment

La migración v9 crea `atlas_projects` y `atlas_environments` como fuentes SQLite canónicas mínimas. Cada registro contiene identificador opaco, estado y revisión positiva. Los identificadores son inmutables, cada actualización debe incrementar exactamente una revisión y los registros no se pueden borrar: los cierres/desactivaciones se representan como cambios de estado.

`SQLiteProjectEnvironmentRepository` implementa los puertos `ProjectMetadataPort` y `EnvironmentMetadataPort` existentes, devolviendo los snapshots tipados `ProjectMetadata` y `EnvironmentMetadata`. Añade altas y actualizaciones CAS para administrar el ciclo de vida básico. `SQLiteLocalAuthorityFoundation` compone este repositorio sobre la misma instancia `SQLiteDatabase` de Identity, Grants, renovaciones y el ledger de cambios.

**Validación:** 967/967 pruebas locales reportadas por el propietario.

**Límites críticos:** el contrato de metadatos existente continúa ubicado en el paquete Memory; se reutiliza para evitar un segundo modelo de snapshot en esta fase. Los registros Project/Environment no tienen todavía relación de pertenencia entre sí porque el contrato actual no la define. Las escrituras del repositorio aún no pasan por un coordinador común de invalidación/fencing y no son una autorización para ejecutar operaciones. No se integra el runtime.


## 15. F2.3.10 — Auditoría de rutas de mutación y bloqueo de integración

La persistencia canónica compartida ya existe, pero no equivale a una frontera de mutación coordinada. La inspección de los servicios y repositorios encontró rutas que deben migrarse antes de habilitar el coordinador:

| Autoridad | Ruta actual | Estado de coordinación |
|---|---|---|
| Identity | `SQLiteIdentityAuthority.update_user_status` / CAS | Mutación directa; no demuestra invalidación común con Grant/Project/Environment |
| Grant | `GrantManagementService.issue` sin UoW opcional | Permite fallback de escritura directa; el wiring SQLite debe exigir la UoW compartida |
| Grant | `GrantManagementService.revoke` | Exige puertos CAM/coordinador, pero no existe coordinador concreto completo en la composición local |
| Grant | `GrantRenewalService.approve_renewal` | Actualiza Grant + renovación atómicamente, pero fuera del coordinador de autoridad |
| Grant renewal | `request_renewal` / `reject_renewal` | Mutan solicitudes; deben mantenerse dentro del mismo dominio transaccional y tener política explícita de coordinación |
| Project | `SQLiteProjectEnvironmentRepository.update_project` | CAS directo sin invalidación/fencing |
| Environment | `SQLiteProjectEnvironmentRepository.update_environment` | CAS directo sin invalidación/fencing |

El coordinador requerido no es una simple función que actualice el registro. Debe asegurar durablemente: reserva idempotente; bloqueo/fencing de admisiones incompatibles; invalidación de admisiones y rutas afectadas; consumo de autorización CAM vinculada a la operación exacta; CAS de la fuente; reconciliación verificable; y recuperación tras fallo/crash. Cualquier incertidumbre debe dejar el recurso bloqueado, nunca reabrir admisiones por timeout.

### Orden de trabajo obligatorio

1. Crear una API de mutación canónica que no exponga métodos directos a las capas de aplicación.
2. Migrar todos los servicios de mutación de Identity, Grant, renovaciones, Project y Environment a esa API o a comandos coordinados equivalentes.
3. Inventariar y cerrar accesos alternativos a los repositorios; los adaptadores de persistencia pueden conservar primitivas internas, pero el composition root no debe ofrecerlas como API de mutación libre.
4. Integrar el coordinador con journal, invalidation, delivery-route registry y fencing concretos; compartir UoW o demostrar una barrera de consistencia equivalente.
5. Probar concurrencia entre admisión y mutación, revocación concurrente, replay/idempotencia, y crashes después de cada transición durable.
6. Solo entonces implementar el verificador de evidencia/admisión de operaciones y habilitar workspace.list/read.

### Decisión

No se implementa todavía un `SQLiteAuthorityChangeCoordinator` de producción. `SQLiteAuthorityChangeStore` solo persiste reservas e idempotencia; no debe confundirse con el coordinador. El puerto `AuthorityChangeCoordinatorPort` es un contrato, no una implementación. Tampoco se conecta F2.3 al runtime. Esta pausa es deliberada para evitar una falsa garantía de consistencia.


## 16. F2.3.12 — Auditoría detallada de renovaciones y APIs de mutación

La revisión del servicio `GrantRenewalService` confirma:

- `request_renewal` crea la solicitud dentro de la UoW compartida; no cambia la revisión del Grant, pero cambia estado de autorización pendiente y debe quedar en el mismo dominio transaccional y auditable.
- `approve_renewal` actualiza Grant (revisión +1 y nuevo vencimiento) y solicitud (versión +1) en una misma UoW. La atomicidad SQLite evita estados parciales, pero no invalida/fencea admisiones que dependan de la revisión anterior.
- `reject_renewal` actualiza solo la solicitud dentro de UoW; requiere política explícita de auditoría y autorización de la decisión, aunque no cambia la revisión del Grant.
- Los métodos de repositorio `create/update/update_if_version` siguen siendo primitivas de persistencia accesibles desde la capa de aplicación y pruebas; no constituyen por sí mismos una API de autoridad coordinada.

La futura operación coordinada de aprobación debe vincular la reserva durable a `renewal_id`, `grant_id`, Grant expected/proposed revision, renewal expected/proposed version, actor, owner, proyecto, entorno, acción y contexto. La decisión humana del propietario debe persistirse como aprobación explícita, pero no sustituye la autorización CAM. El cambio de vencimiento del Grant debe pasar por el mismo fencing/invalidation/CAS/reconciliation que cualquier otro cambio de Grant. El rechazo y la creación de solicitudes requieren una política diferenciada porque no mutan el Grant.

**No cambiar aún el servicio para aceptar un coordinador ficticio ni reutilizar el autorizador CAM específico de revocación.** Primero definir contratos neutrales de autorización para cambios de autoridad y una composición que garantice atomicidad entre la decisión humana, renovación, Grant, journal e invalidación.


## 17. F2.3.13 — Contrato de cambios sobre múltiples autoridades

**Estado:** diseño normativo; no implementado.

### Problema

El `AuthorityChangeIntent` actual reserva una única autoridad `(authority_kind, authority_id)` y una pareja de revisiones. Sirve para una revocación individual, pero no representa completamente la aprobación de una renovación: esta modifica en una misma decisión el Grant (vencimiento/revisión) y la solicitud (estado APPROVED/versión). La UoW SQLite hace atómica la escritura local, pero no invalida admisiones antiguas ni bloquea rutas que consuman revisiones previas.

La segunda mutación no debe esconderse en `request_context_ref`, `change_kind` ni JSON opaco.

### Modelo propuesto

Introducir un conjunto inmutable de objetivos de cambio:

- `AuthorityChangeTarget`: `authority_kind`, `authority_id`, `expected_revision`, `proposed_revision`.
- `AuthorityChangeIntent`: `consumer_id`, `idempotency_key`, acción, actor, propietario, proyecto/entorno, conjunto de objetivos, referencia de contexto y timestamp.

Cada objetivo exige revisión esperada positiva y propuesta estrictamente superior. No se permiten objetivos duplicados; se fija un orden canónico antes de calcular la huella idempotente. La clave queda vinculada a la intención completa. Reutilizarla con cualquier diferencia semántica se rechaza. Una sola operación y reserva durable reclaman todos los objetivos atómicamente; nunca se reserva un subconjunto.

### Aprobación de renovación

| Objetivo | Recurso | Revisión esperada | Revisión propuesta |
|---|---|---:|---:|
| Grant | `grant_id` | `grant.revision` | `grant.revision + 1` |
| Solicitud | `renewal_id` | `renewal.version` | `renewal.version + 1` |

La solicitud CAM debe incluir actor USER activo, propietario, proyecto, entorno, acción `grant.renewal.approve`, IDs exactos, vencimiento actual/propuesto y solicitud pendiente. La aprobación humana es una decisión de negocio autenticada y auditable; no reemplaza CAM. La evidencia consumida debe vincularse a operation_id, clave idempotente, actor, propietario, todos los objetivos/revisiones, proyecto, entorno, acción, emisor y tiempos.

### Orden durable

1. Leer y validar fuentes canónicas.
2. Construir intención inmutable con todos los objetivos.
3. Reservar todos los objetivos bajo una operación idempotente y una transacción.
4. Obtener, verificar y consumir evidencia CAM exacta.
5. Aplicar fencing a admisiones/rutas incompatibles para todos los objetivos.
6. Aplicar todos los cambios fuente en una misma UoW SQLite y CAS por objetivo.
7. Persistir resultado fuente y posición de consistencia.
8. Reconciliar invalidaciones/rutas y verificar todas las revisiones propuestas.
9. Marcar COMPLETED y retirar fencing solo tras reconciliación completa.

Si falla un CAS, no puede confirmarse parcialmente el conjunto. Ante incertidumbre se mantiene BLOCKED/fenced; timeout nunca significa rollback ni ABORTED.

### Otras operaciones

- Solicitar renovación: crea una solicitud pendiente sin incrementar Grant; debe registrar actor/delegación y revisión/vencimiento observados, y rechazar solicitudes incompatibles con un Grant cambiado.
- Rechazar renovación: muta solo la solicitud; requiere decisión del propietario y autorización/auditoría explícita.
- Aprobar renovación: muta Grant + solicitud; requiere dos objetivos y atomicidad.

### Persistencia futura

La persistencia actual guarda una autoridad por operación. Se requiere tabla hija de objetivos (p. ej. `authority_change_targets`) con FK a operación, clave única por operación/autoridad, revisiones esperada/propuesta e inmutabilidad tras reserva. Operación, clave idempotente y todos los objetivos se insertan en una única transacción `BEGIN IMMEDIATE`. La migración será aditiva y compatible con operaciones históricas de un objetivo; nunca se fabrican objetivos secundarios para filas antiguas.

### Pruebas obligatorias

- Reservas concurrentes sobre el mismo Grant o la misma solicitud: solo una gana.
- No existe reserva parcial del conjunto.
- Revisión obsoleta de cualquiera de los objetivos impide aplicar todos.
- Fallo entre escrituras nunca deja Grant aprobado con solicitud pendiente, ni viceversa.
- Revocación concurrente con aprobación produce un orden válido; no resucita Grants revocados.
- Replay exacto recupera la misma operación; misma clave con objetivo/acción/revisión diferente se rechaza.
- Crashes tras reserva, consumo CAM, fencing, CAS, resultado y reconciliación conservan bloqueo hasta recuperar el estado autoritativo.
- COMPLETED demuestra la revisión final de cada objetivo y la invalidación reconciliada.

### Decisiones

No implementar renovación como dos cambios independientes; no tratar UoW como sustituto de fencing; no transportar objetivos ocultos en texto libre; no considerar aprobación humana como permiso CAM. No se implementa todavía coordinador SQLite ni se conecta este diseño al runtime.

**Criterio de salida:** contrato multiobjetivo, esquema aditivo, repositorio, coordinador durable, adaptadores CAM y pruebas de concurrencia/recuperación completados antes de habilitar aprobaciones de renovación.


### F2.3.14 — Modelos inmutables multiobjetivo

Se añadieron `AuthorityChangeTargetKind`, `AuthorityChangeTarget` y `MultiAuthorityChangeIntent` en `atlas.memory.authority_changes`.

- Los tipos distinguen `grant` y `grant_renewal` sin alterar todavía el enum ni el esquema histórico de operaciones de un solo objetivo.
- Cada target exige transición de revisión exactamente +1.
- La intención requiere al menos dos objetivos, acción, actor, propietario, clave idempotente, consumidor, contexto y timestamp UTC.
- Los objetivos se canonicalizan por tipo e ID antes de comparar/hash de intención; los duplicados se rechazan.
- Los modelos son inmutables y no asignan `operation_id`.

Se añadieron pruebas unitarias para binding de Grant + renovación, orden canónico, duplicados, mínimo de objetivos, salto de revisión, booleanos como revisión, campos requeridos, UTC e inmutabilidad.

**Límite:** estos modelos aún no son aceptados por `SQLiteAuthorityChangeStore`, no reservan ni mutan recursos y no autorizan operaciones. Pendiente de pruebas locales.


### F2.3.15 — Persistencia de reservas multiobjetivo (publicada; pendiente de validación)

Se añadió la migración SQLite v10 con tres tablas separadas del ledger histórico de una sola autoridad:

- `multi_authority_change_operations`: identidad de operación, actor, propietario, acción, contexto y estado.
- `multi_authority_change_idempotency`: namespace consumidor/clave y digest + canonicalización semántica.
- `multi_authority_change_targets`: conjunto completo de objetivos tipados con revisiones esperada/propuesta.

La separación evita insertar valores sintéticos en las columnas NOT NULL del ledger antiguo y preserva intactas las operaciones históricas. La reserva inserta operación, todos los objetivos y binding idempotente dentro de una única SQLiteUnitOfWork. El conjunto se canonicaliza; el replay exacto recupera la misma operación y la misma marca temporal original; una misma clave con intención distinta se rechaza. Triggers impiden actualizar/eliminar objetivos, ampliar el conjunto después del binding idempotente o alterar/eliminar dicho binding.

Se añadieron `MultiAuthorityChangeReservation`, `reserve_multi_change`, `get_multi_reservation` y `get_multi_by_idempotency_key`, además de pruebas para persistencia tras reinicio, replay, conflicto semántico, aislamiento por consumidor y sellado del conjunto.

**Límite de seguridad importante:** esto persiste una reserva lógica, pero todavía no adquiere claims exclusivos sobre recursos, no serializa dos operaciones diferentes que intenten cambiar el mismo objetivo, no ejecuta CAM, no aplica fencing/invalidation, no muta fuentes ni coordina recuperación. No se debe usar como coordinador ni habilitar cambios multiobjetivo en runtime hasta implementar esas garantías.

## 17. F2.3.16 — Claims exclusivos multiobjetivo

La migración v11 añade `multi_authority_change_claims`, con clave primaria global por `(authority_kind, authority_id)`. Por tanto, una misma autoridad no puede estar reclamada por dos operaciones multiobjetivo activas, incluso si compiten desde conexiones SQLite distintas. `acquire_multi_claims(operation_id)` usa `BEGIN IMMEDIATE`, valida que la operación exista y siga en `REQUESTED`, compara el conjunto completo de targets y adquiere todos los claims en una sola transacción. Los reintentos exactos del mismo operation_id son idempotentes; si cualquier target ya pertenece a otra operación, devuelve conflicto sin insertar ningún claim del segundo conjunto.

La base impone que cada claim coincida con un target inmutable de una operación `REQUESTED`. Los claims no se pueden actualizar ni borrar. Esta retención es intencionalmente conservadora: **todavía no existe liberación**, porque el estado terminal por sí solo no prueba que la reconciliación haya sido verificada. La futura liberación requiere recibo durable de terminalidad/reconciliación, transición autorizada y operación coordinada dentro de la misma UoW. Operaciones bloqueadas o inciertas conservan todos sus claims.

**Límite:** esto ofrece exclusión mutua local sobre los recursos reclamados en una única base SQLite; no implementa CAM, invalidación de admisiones, fencing de rutas, mutación de fuentes ni coordinador completo. Tampoco protege escrituras que eviten este store. No conectar al runtime.

## 18. F2.3.17 — Contrato de evidencia terminal multiobjetivo

Se añadieron los contratos inmutables `AuthorityChangeTerminalOutcome`,
`AuthorityChangeTerminalTarget` y `AuthorityChangeTerminalEvidence`.

- El recibo se vincula a un `operation_id`, identificador propio, referencia durable de evidencia, registrador y timestamp UTC.
- Debe incluir al menos dos objetivos tipados, sin duplicados, con las revisiones esperada/propuesta reservadas y la revisión final observada.
- `COMPLETED` exige que cada fuente observe su revisión propuesta.
- `ABORTED` exige que cada fuente permanezca en su revisión esperada.
- Los objetivos se canonicalizan y `matches(reservation)` exige coincidencia exacta de operación, recursos y transiciones de revisión.

**Límite esencial:** este contrato valida forma y consistencia interna, no autentica la referencia, no demuestra por sí solo que la reconciliación ocurrió y no autoriza liberar claims. Todavía no hay persistencia del recibo, transición atómica del estado ni protocolo de liberación. Los claims siguen retenidos. El siguiente incremento debe persistir el recibo junto con la transición terminal en una misma UoW y validar su binding contra el conjunto reservado antes de considerar cualquier liberación.

**Estado:** validado por el propietario con 1003/1003 pruebas. Runtime desconectado.



## 19. F2.3.18 — Persistencia atómica de evidencia terminal

Migración SQLite v12 añade multi_authority_change_terminal_evidence y multi_authority_change_terminal_targets. El store record_multi_terminal_evidence valida que la operación exista, esté en RECONCILING, conserve el conjunto completo de claims y que el recibo coincida exactamente con todos los objetivos/revisiones reservados.

El recibo, sus objetivos y el cambio de estado a COMPLETED o ABORTED se escriben en una única SQLiteUnitOfWork. Un replay byte-semántico exacto recupera el recibo original; cualquier recibo distinto para la misma operación se rechaza. La recuperación recalcula el digest y la canonicalización para detectar corrupción del contenido persistido. Las tablas y filas son inmutables, los objetivos están ligados por FK al conjunto reservado y triggers impiden marcar terminal sin recibo y objetivos completos o cambiar después el estado terminal. Las claims no se liberan.

**Límite:** el digest/canonicalización protege la identidad del replay, no autentica al registrador ni prueba independientemente la verdad de la referencia externa. No hay verificador de evidencia, CAM, invalidación/fencing, mutación coordinada de fuentes ni runtime. Las operaciones BLOCKED/inciertas retienen claims.

**Estado:** validado por el propietario con 1014/1014 pruebas (16 de noviembre de 2026).


## 20. F2.3.19 — Liberación auditable de claims terminales

Migración SQLite v13 añade `multi_authority_change_claim_releases`, un recibo inmutable de liberación vinculado al digest de la evidencia terminal. El trigger de inserción exige una operación COMPLETED/ABORTED, recibo terminal coincidente y conjuntos completos de targets, observaciones y claims. El trigger de borrado de claims solo permite eliminarlos cuando existe ese recibo.

`release_multi_claims(operation_id)` recupera y vuelve a verificar la evidencia terminal (incluyendo digest y canonicalización), compara exactamente los objetivos reservados con los observados y los claims activos, y registra el recibo + elimina todos los claims dentro de una única UoW. Replays exactos son idempotentes; los estados no terminales no liberan; inconsistencias o claims parciales fallan cerrados. El historial de liberación no se puede actualizar ni borrar y los recursos quedan disponibles para una nueva operación después de la liberación confirmada.

**Límite:** la integridad/digest no autentica al registrador ni prueba por sí sola la veracidad externa de la referencia. Este mecanismo es persistencia local y no sustituye un coordinador de autoridad completo, CAM, invalidación/fencing ni reconciliación real. Runtime permanece desconectado.

**Estado:** validado por el propietario con 1030/1030 pruebas (16 de noviembre de 2026).


## 21. F2.3.20 — Auditoría de recuperación de claims

Se añade el contrato inmutable de solo lectura `MultiAuthorityClaimAudit` y `SQLiteAuthorityChangeStore.audit_multi_claims(operation_id)`. La auditoría clasifica la operación como UNCLAIMED, CLAIMED, TERMINAL_CLAIMS_HELD, RELEASED o INCONSISTENT. Contrasta objetivos reservados, claims existentes, estado terminal, recibo reconstruido (incluida verificación de digest/canonicalización) y recibo durable de liberación.

Un recibo corrupto, un conjunto parcial, un estado terminal sin evidencia, una liberación con claims restantes o un recibo de liberación que no coincide producen INCONSISTENT. La lectura no repara datos, no libera claims y no autoriza mutaciones. Operaciones desconocidas devuelven None.

**Límite:** es una clasificación local de persistencia, no prueba de reconciliación externa ni autenticidad del registrador. No reemplaza CAM, fencing, invalidación ni coordinador de fuentes. Runtime permanece desconectado.

**Estado:** validado por el propietario con 1043/1043 pruebas (16 de noviembre de 2026).


## 22. F2.3.21 — Frontera UoW compartida de autoridades

Identity y Project/Environment ahora pueden participar en una `SQLiteUnitOfWork` externa, verificando que pertenece a la misma instancia de `SQLiteDatabase` y que sigue activa. `SQLiteLocalAuthorityUnitOfWork` extiende la composición transaccional existente para exponer Identity, Grants, renovaciones y Project/Environment sobre la misma conexión y transacción.

La composición puede confirmar o revertir en conjunto estas fuentes canónicas. La frontera continúa siendo solo de persistencia y no define el protocolo de coordinación. No implementa CAM, invalidación, fencing ni reconciliación real. Runtime desconectado.

**Estado:** validado por el propietario con 1040/1040 pruebas (16 de noviembre de 2026).


## 23. F2.3.22 — Ledger de operaciones dentro de la UoW compartida

`SQLiteAuthorityChangeStore` puede construirse con la UoW externa y utiliza esa conexión para sus reservas, claims, evidencias terminales, liberaciones y consultas. La composición local expone `authority_changes` junto a Identity, Grants, renovaciones y Project/Environment. Así, una transacción puede confirmar o revertir en conjunto los registros canónicos y el ledger de operación.

Esto elimina la separación transaccional SQLite entre el ledger y esas fuentes cuando todos participan explícitamente en la misma UoW. No crea por sí solo un coordinador: faltan política de admisión, autorización CAM, orden de mutación, invalidación, fencing, reconciliación externa y pruebas de concurrencia de extremo a extremo. Runtime desconectado.

**Estado:** validado por el propietario con 1043/1043 pruebas (16 de noviembre de 2026).


## 24. F2.3.23 — Máquina de estados durable multiobjetivo

La migración v14 agrega triggers para limitar el ledger multiobjetivo a transiciones forward-only: REQUESTED → INVALIDATION_PENDING → SOURCE_PENDING → SOURCE_CONFIRMED → RECONCILING → COMPLETED/ABORTED. Los pasos intermedios requieren el conjunto exacto y completo de claims. Los estados terminales siguen exigiendo el recibo durable y completo implementado en v12; la migración no abre una ruta alternativa de terminalización.

`transition_multi_status(operation_id, expected_status, new_status)` ofrece CAS atómico: rechaza estado esperado obsoleto, rechaza reintentos con estado esperado obsoleto y falla cerrado ante claims incompletos. Los triggers protegen incluso escrituras SQL directas. El método solo registra avance del ledger; no demuestra que invalidación, mutación o reconciliación externa hayan sucedido. No autoriza ni ejecuta acciones. La transición a BLOCKED y su recuperación se dejan fuera hasta definir evidencia y semántica de reanudación.

**Estado:** VALIDADA localmente por el propietario; suite completa: 1048 tests en 9.026 s, todos OK.


## 25. F2.3.24 — Diagnóstico de recuperación multiobjetivo

`MultiAuthorityRecoveryAssessment` es una proyección de solo lectura del ledger y la auditoría de claims. Sus disposiciones distinguen `NOT_STARTED`, `CLAIMED_BEFORE_INVALIDATION`, `INVALIDATION_OUTCOME_UNKNOWN`, `SOURCE_OUTCOME_UNKNOWN`, `SOURCE_CONFIRMATION_RECORDED`, `RECONCILIATION_IN_PROGRESS`, `TERMINAL_CLAIMS_HELD`, `TERMINAL_RELEASED` e `INCONSISTENT`.

`SOURCE_PENDING` siempre significa que el resultado de la mutación de fuente es desconocido. No se puede inferir que la operación no se ejecutó ni repetirla automáticamente. La evaluación no cambia datos, no libera claims y no constituye autorización ni evidencia externa.

**Estado: VALIDADA.** Suite completa: 1054 tests OK.


## 26. F2.3.25 — Decisión declarativa de recuperación

Se añaden los contratos MultiAuthorityRecoveryDecisionKind, MultiAuthorityRecoveryEvidenceRequirement y MultiAuthorityRecoveryDecision, además de recommend_multi_recovery_decision(assessment). La función es pura: vincula cada decisión al operation_id y disposición evaluada, asigna un código de motivo y enumera la evidencia independiente requerida antes de que una futura persona/coordinador pueda continuar.

Las recomendaciones distinguen: no requerir acción de recuperación para una operación no iniciada o terminal ya liberada; revalidar autoridad antes de cualquier avance desde claims previos a invalidación; verificar por separado los resultados de invalidación y de fuente cuando sean inciertos; verificar revisiones canónicas, invalidación y fencing antes de reconciliar; autenticar la evidencia terminal antes de liberar claims; y exigir revisión humana ante inconsistencias.

**Reglas obligatorias:** ninguna decisión permite acción automática; no existe recomendación de retry; la etapa registrada no autentica evidencia externa; la recomendación no cambia el ledger, no transiciona a BLOCKED, no libera claims, no sustituye CAM y no constituye permiso. La evidencia enumerada deberá ser obtenida y verificada independientemente por una futura capa coordinadora.

**Estado: VALIDADA.** Suite completa: 1061 tests en 7.206 s, todos OK.
