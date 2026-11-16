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
