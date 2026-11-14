# ME-03K — Decisión de persistencia SQLite para el perfil local

**Estado:** decisión aprobada por el propietario; diseño previo a implementación.  
**Fecha:** 14 de noviembre de 2026.  
**Rama objetivo:** `feature/me-03k-local-profile`.  
**Base:** ME-03K, ME-03K-B y matriz de conformidad K01–K07.

## 1. Decisión

Se aprueba SQLite como motor de persistencia durable para el baseline del perfil local de Atlas en la topología inicial de un único servidor Debian.

Se utilizará la biblioteca estándar `sqlite3` de Python. No se introduce un servidor de base de datos separado ni una dependencia Python externa.

Esta decisión selecciona el motor de almacenamiento, pero no declara conformidad K01–K07 ni autoriza activar lecturas protegidas, Forget físico o el Recovery Gate operativo.

## 2. Límites de la decisión

- SQLite será la persistencia transaccional de la autoridad local de consistencia; no se creará una segunda autoridad en memoria.
- La implementación debe compartir una única base de orden durable para journal, admisiones, cierres, invalidaciones, recibos operativos, fencing y estado del Recovery Gate.
- Los procesos del servidor podrán abrir conexiones SQLite independientes al mismo archivo local.
- El baseline no contempla NFS, almacenamiento compartido entre nodos, failover multinodo, elección distribuida de líder ni leases distribuidos.
- El Trust Anchor externo sigue aplazado hasta la etapa final. El perfil seleccionado debe declararse explícitamente como `local`.
- La política de confianza, las claves HMAC y la configuración de emisores autorizados no se almacenarán en tablas restaurables junto al journal.
- No se almacenará contenido de memoria, fragmentos, payloads, embeddings, snippets, hashes de contenido ni datos derivados que permitan reconstruirlo.
- La restauración de un conjunto SQLite coherente y antiguo no puede detectarse mediante este perfil local. No se afirma anti-rollback externo.

## 3. Configuración SQLite del adaptador

La implementación deberá aplicar y verificar en cada conexión:

- `PRAGMA foreign_keys = ON`.
- `PRAGMA journal_mode = WAL`, comprobando que SQLite devuelve efectivamente `wal`.
- `PRAGMA synchronous = FULL`.
- `PRAGMA busy_timeout` con un valor explícito y acotado, configurable por el adaptador.
- Transacciones de escritura iniciadas con `BEGIN IMMEDIATE` para adquirir el turno de escritor antes de leer y validar la posición CAS.

La ruta de base de datos será configuración de despliegue, nunca una ruta fija dentro del repositorio. La base debe residir en un filesystem local que soporte correctamente los bloqueos y sincronización de SQLite; no se aceptará NFS ni un filesystem compartido no validado.

WAL mejora la convivencia entre lectores y escritor, pero SQLite mantiene un único escritor efectivo. La aplicación debe tratar `SQLITE_BUSY`, `SQLITE_LOCKED`, I/O errors, corrupción y fallos de commit como indisponibilidad o resultado potencialmente ambiguo, nunca como prueba automática de que la operación no se confirmó.

La política de backup debe considerar el archivo WAL y utilizar la API de backup de SQLite o un procedimiento consistente. Copiar únicamente el archivo principal mientras la base está activa no constituye un backup válido.

## 4. Modelo lógico inicial

El esquema se versionará mediante migraciones SQL numeradas e inmutables. Cada migración tendrá checksum; una versión aplicada con checksum diferente bloqueará el arranque.

### 4.1 `schema_migrations`

Registra versión, checksum y fecha de aplicación. Las migraciones se ejecutan de forma transaccional cuando SQLite lo permita y nunca se reescribe una migración ya publicada.

### 4.2 `consistency_domains`

Una fila por dominio de consistencia. Contiene como mínimo:

- `domain_id` como clave primaria;
- `authority_epoch` y `head_sequence`;
- `head_commitment` autenticado;
- perfil explícito (`local`);
- versión de política de confianza esperada;
- estado del Recovery Gate (`closed` o `open`);
- operación y generación de recuperación activas, si existen;
- recibo global que autorizó la última apertura, si existe;
- timestamps de auditoría.

La posición actual no se deriva de una caché ni de un contador en memoria. Se actualiza en la misma transacción que inserta el journal.

### 4.3 `journal_entries`

Almacena una transición por posición durable:

- dominio, época y secuencia;
- `record_id`, `operation_id`, `record_kind` y versión de esquema;
- solicitud/transición canónica versionada, en bytes UTF-8;
- envelope autenticado y compromiso anterior;
- compromiso del objeto y evidencia MAC;
- fecha UTC semántica.

Restricciones únicas: posición dentro de dominio/época, `record_id` dentro del dominio y operación dentro del ámbito contractual. Las claves foráneas deben impedir registros huérfanos.

Los bytes canónicos se generan con el canonicalizador versionado existente; no se serializan DTOs arbitrarios ni se confía en el orden JSON incidental.

### 4.4 `journal_operations`

Índice durable de resolución de operaciones e idempotencia:

- dominio, época y `operation_id`;
- `idempotency_key`, cuando aplique;
- versión y bytes de solicitud canónica;
- digest de la solicitud;
- posición y `record_id` del commit original.

Las restricciones únicas deben impedir que una operación o clave idempotente se vincule a dos solicitudes. Misma clave y misma solicitud devuelve el commit original con `replayed=True`; misma clave con solicitud diferente produce conflicto sin mutación.

Las entradas de este índice son tombstones de idempotencia y no se eliminan por compactación mientras un replay pueda afectar seguridad o semántica.

### 4.5 `checkpoints` y `checkpoint_projections`

El checkpoint persiste ID, dominio, época, secuencia exacta, referencias opacas de estado/integridad, versión de schema/reducer, envelope y compromisos.

La proyección base persistida contiene exclusivamente metadatos de control requeridos por el reducer (admisiones, cierres, invalidaciones, recibos, emisiones, idempotencia y generaciones). No puede contener contenido de memoria ni hashes del contenido.

El adaptador no tratará una proyección como verificada por el mero hecho de leerla desde SQLite: debe validar envelope, compromiso, política independiente y binding exacto al checkpoint antes de entregarla al reducer.

### 4.6 Inventarios operativos

Se mantendrán registros consultables y transaccionales para recibos, tombstones, referencias y operaciones pendientes/no terminales. Como mínimo, cada elemento debe conservar su identidad, dominio/época, operación, admisión/endpoint cuando aplique, generación, secuencia, referencia al registro que lo introdujo y evidencia de autenticidad correspondiente.

El verificador de inventarios debe comparar el conjunto completo de registros persistidos con la proyección reconstruida; no puede limitarse a comprobar que los IDs declarados por el journal existen.

Estos inventarios son evidencia de consistencia local, no una segunda fuente anti-rollback. Un backup antiguo que incluya un conjunto coherente de journal e inventarios sigue estando dentro de la limitación del perfil local.

## 5. Límites transaccionales obligatorios

### 5.1 Append del journal (K01)

Una única transacción `BEGIN IMMEDIATE`:

1. Lee dominio, época, head y estado de continuidad.
2. Comprueba que la posición esperada coincide exactamente.
3. Canonicaliza la solicitud y resuelve operación/clave idempotente.
4. Rechaza conflicto o transición inválida sin mutar.
5. Construye y autentica el envelope ligado al head anterior.
6. Inserta journal y resolución de operación.
7. Actualiza head/commitment del dominio.
8. Confirma la transacción.

La posición confirmada es `head_sequence + 1`. Ningún hueco se acepta. Dos procesos que compitan por la misma posición deben producir exactamente un commit y un rechazo/CAS obsoleto para el otro.

### 5.2 Cierre del Recovery Gate (K02/K05)

El evento `RECOVERY_CLOSED`, la generación activa, el cierre durable del gate y la actualización del head se escriben en una sola transacción SQLite. No se permite persistir primero el evento y cerrar después el gate en otra operación.

### 5.3 Reconciliación y apertura (K05)

La transición `RECOVERY_RECONCILED`, la vinculación al recibo global verificado y el cambio del gate a `open` ocurren en una única transacción. La transacción valida operación, generación, inventario exacto y posición esperada. Si falta cualquier evidencia, la transacción no abre el gate.

### 5.4 Resultado ambiguo

Ante timeout, pérdida de conexión o excepción durante/tras commit, el caller no presupone éxito ni fracaso. Consulta `journal_operations` y la posición durable mediante la misma autoridad.

- Coincidencia canónica única: `COMMITTED_EXACT`, con commit original.
- Ausencia demostrable y posición/época coherentes: `NOT_COMMITTED`.
- Clave/operación asociada a otra solicitud: `CONFLICT`.
- Corrupción, indisponibilidad o imposibilidad de demostrar ausencia: `UNKNOWN`.

`UNKNOWN` y `CONFLICT` bloquean el flujo. No se crea una operación nueva para intentar resolverlos.

## 6. Autoridad y egress: límite que SQLite no resuelve por sí solo

SQLite puede serializar las decisiones y el estado durable local. No puede hacer una transacción ACID conjunta con un endpoint o transporte remoto.

Por tanto, el adaptador SQLite no puede afirmar que una transacción local seguida de una llamada de red hace atómica la entrega. El contrato K03 requiere que el último punto irrevocable de aceptación del endpoint aplique generación/fencing e idempotencia en el mismo punto de aceptación, y que emita recibos autenticados verificables.

El diseño de implementación debe conservar una frontera de endpoint explícita, con fencing durable y reconciliación de resultados ambiguos. Si un endpoint no ofrece esa garantía, la ruta queda bloqueada; no se simula atomicidad con un lock local ni con check-token-then-send.

La composición `ProtectedMemoryRecoveryAuthorityPort` debe recibir una única instancia de autoridad SQLite para todas las facetas locales. No se permite construir journal y Recovery Gate con conexiones/adaptadores independientes que puedan divergir en la semántica transaccional.

## 7. Custodia de claves

La tabla SQLite no almacena claves HMAC. El puerto actual `LocalConsistencyKeyPort` solo resuelve claves históricas por referencia; no define cómo se crea, rota o selecciona la clave de firma actual.

Antes de implementar escrituras autenticadas se debe aprobar y diseñar una capacidad separada para obtener la clave activa de firma y custodiar claves históricas fuera de backups ordinarios. La indisponibilidad de clave produce `UNAVAILABLE/UNKNOWN` y mantiene el dominio cerrado. No se genera una clave nueva automáticamente al reiniciar ni se acepta una clave recuperada desde el mismo backup como raíz de confianza.

## 8. Orden de implementación

1. Migraciones y esquema SQLite, configuración segura y lifecycle de conexiones.
2. Adaptador de journal K01 con canonicalización, HMAC, CAS, idempotencia y resolución de operaciones.
3. Carga estructural y verificación local usando política y claves externas a la base restaurable.
4. Checkpoints y proyecciones verificadas, incluyendo compactación conservadora.
5. Inventarios completos de recibos, tombstones y operaciones pendientes.
6. Recovery Gate con cierre/apertura atómicos.
7. Integración de autoridad única con admisión, Forget, invalidaciones y egress, sin habilitar rutas que no demuestren K03.
8. Harness de conformidad K01–K07 contra SQLite real: procesos concurrentes, kill/restart, fallos inyectados, corrupción, backups y restauración.

Cada etapa tiene sus pruebas de integración propias. Los tests los ejecuta el usuario en Debian; no se usarán CI workflows que disparen tests ni se ejecutarán pruebas desde este entorno.

## 9. Criterios de salida

La implementación SQLite solo podrá declararse conforme cuando pase K01–K07 en el baseline de un servidor, con pruebas contra archivos SQLite reales y procesos independientes. En particular:

- CAS/idempotencia/resolución ambigua multiproceso;
- persistencia tras kill/restart y fallos en cada frontera durable;
- autenticidad de journal/checkpoint y rechazo de corrupción;
- inventarios completos y tombstones preservados;
- cierre y reapertura atómicos del gate;
- fencing de endpoints y rechazo de emisores antiguos;
- aislamiento entre dominios;
- recuperación fail-closed ante cualquier estado desconocido.

La aprobación de SQLite no implica que estos criterios estén ya satisfechos ni autoriza despliegue en producción.
