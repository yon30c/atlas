# Contrato normativo IPC administrativo de autoridad local — atlas-admin/1

**Identificador:** ATLAS-CONTRACT-LOCAL-AUTHORITY-ADMIN-IPC  
**Versión del contrato:** 1.0  
**Estado:** baseline normativo de protocolo para desarrollo y prototipo; no autoriza despliegue ni operaciones administrativas reales.  
**Protocolo:** `atlas-admin/1`  
**Fecha:** 18 de noviembre de 2026.

## 1. Autoridad, alcance y precedencia

Este documento es la fuente normativa única para el envelope, transporte de mensajes, validación, límites, semántica de respuesta y catálogo de operaciones del protocolo IPC administrativo `atlas-admin/1`.

Se deriva de las decisiones de protocolo aprobadas por el propietario y fija su interpretación implementable. No sustituye el contrato general de Atlas ni el contrato operativo de almacenamiento. Tampoco convierte en aprobadas las propuestas de despliegue del listener o del servicio.

Precedencia dentro de este ámbito:

1. Las decisiones expresamente aprobadas por el propietario y registradas aquí.
2. Este contrato normativo, para todos los aspectos comunes de `atlas-admin/1`.
3. Las especificaciones individuales de operación, una vez aprobadas e incorporadas como secciones normativas de este documento o documentos subordinados expresamente enlazados.
4. Los diseños, auditorías, prototipos, notas de implementación y documentación de estado, que son descriptivos y no pueden ampliar ni modificar el contrato.

Si un documento subordinado o histórico contradice este contrato, prevalece este contrato y el documento contradictorio debe corregirse. El contrato raíz `Contrato-de-diseno-Atlas-v1.md` continúa siendo la autoridad arquitectónica general, pero sus §§10, 11 y 15 **no** son definiciones del protocolo IPC y no deben citarse como fuente del envelope, catálogo o respuestas.

Una modificación de decisiones aprobadas requiere aceptación expresa del propietario y actualización de la versión/revisión de este contrato. Una implementación parcial no reduce el alcance normativo aprobado.

## 2. Estados documentales y límites de aprobación

- **APROBADO / BASELINE DE DESARROLLO:** decisión de protocolo aceptada y obligatoria para el desarrollo de `atlas-admin/1`.
- **PENDIENTE DE ESPECIFICACIÓN:** detalle de una operación o política que no puede inferirse de las reglas comunes.
- **PROPUESTA / CANDIDATO:** alternativa técnica que requiere validación y aprobación antes de convertirse en requisito de despliegue.
- **IMPLEMENTADO:** comportamiento observado en el código de una revisión concreta; no equivale a verificado.
- **VALIDADO:** comportamiento respaldado por evidencia de pruebas o comprobación identificada.
- **NO IMPLEMENTADO:** capacidad normativa aún ausente del código.

Este contrato no aprueba por sí mismo: listener persistente, socket activation, unidades systemd, ownership/permisos de filesystem en producción, UID/GID definitivos del cliente, hardening del servicio, apertura de SQLite, migraciones reales, provisioning real ni cambios en el host.

## 3. Transporte y modelo de conexión

### 3.1 Baseline de protocolo

Para el prototipo `atlas-admin/1`:

- Familia: `AF_UNIX`.
- Tipo: `SOCK_SEQPACKET`.
- Una solicitud por conexión.
- Una respuesta como máximo por conexión.
- El peer se identifica mediante credenciales del kernel obtenidas con `SO_PEERCRED`; nunca se confía en un UID/PID/GID declarado en JSON.
- Las credenciales del peer se obtienen y validan antes de leer el paquete de solicitud.
- Se rechaza cualquier dato ancillary; no se admiten descriptores transferidos mediante `SCM_RIGHTS`.
- Se rechaza el paquete si se detecta truncamiento (`MSG_TRUNC`) o truncamiento de ancillary (`MSG_CTRUNC`).

La identidad del peer del sistema operativo no equivale a identidad humana Atlas, identidad civil ni autorización de dominio. La autorización de cada operación protegida es una capa distinta y no queda concedida por superar `SO_PEERCRED`.

### 3.2 Política de UID autorizado

La allowlist de UID es una política local del caller/listener y debe ser explícita. El handler recibe la allowlist como configuración y compara contra el UID informado por `SO_PEERCRED`.

El contrato no codifica un UID universal ni convierte UID 0 en una autorización implícita para cualquier despliegue. La propuesta de utilizar UID 0 para un futuro frontend privilegiado pertenece al diseño de despliegue y requiere aprobación/validación específica. Los tests ejecutados con el UID actual no demuestran el modelo de despliegue con root ni aislamiento entre cuentas.

Un peer no autorizado se rechaza antes de leer el paquete y no recibe envelope de respuesta.

### 3.3 Lifecycle fuera de alcance

Este contrato no define creación, bind, listen, ownership, modo, ACL, directorio, limpieza, stale socket, concurrencia del listener, socket activation ni unidades systemd. Esos aspectos pertenecen al documento de lifecycle y permanecen sujetos a sus puertas de decisión. El socket de filesystem y su instalación en el host no quedan aprobados por la especificación del protocolo.

## 4. Envelope de solicitud

La solicitud es un único objeto JSON UTF-8 con exactamente estas cuatro claves de nivel superior:

```json
{
  "protocol": "atlas-admin/1",
  "request_id": "UUIDv4-canónico",
  "operation": "nombre.de.operacion",
  "payload": {}
}
```

Reglas:

1. `protocol` MUST ser exactamente `atlas-admin/1`.
2. `request_id` MUST ser un UUID versión 4, variante RFC 4122, en representación canónica minúscula con guiones; no se aceptan formas equivalentes no canónicas.
3. `operation` MUST ser una cadena que coincida exactamente con una de las siete operaciones del catálogo cerrado de §9.
4. `payload` MUST ser un objeto JSON. Su esquema lo determina exclusivamente la especificación individual de la operación.
5. No se permiten claves ausentes, claves adicionales ni claves duplicadas en ningún objeto JSON.
6. No se aceptan valores JSON no estándar como `NaN`, `Infinity` o `-Infinity`.
7. Los números deben ser representables por el decoder y los valores numéricos deben ser finitos.
8. Se rechazan tipos incorrectos, JSON malformado y UTF-8 inválido.
9. No se permiten mensajes adicionales ni una segunda solicitud en la misma conexión.

No existen campos comunes implícitos para actor, motivo, procedencia, rutas, executor UID, SQL, comandos, variables de entorno o argumentos de proceso. Si una operación necesita alguno de esos datos, debe declararlo en su payload individual aprobado. Nunca se debe aceptar un campo extra por conveniencia.

## 5. Límites y timeouts

| Parámetro | Valor normativo |
|---|---:|
| Tamaño máximo de solicitud | 16 KiB (16 × 1024 bytes) |
| Tamaño máximo de respuesta | 64 KiB (64 × 1024 bytes) |
| Profundidad máxima de JSON | 16 niveles |
| Timeout de lectura por conexión | 5 segundos por defecto |
| Timeout de escritura por conexión | 5 segundos por defecto |
| Timeout máximo configurable por dirección | 60 segundos |

Los timeouts de lectura y escritura son independientes. Cada valor configurado MUST ser positivo, finito y no superar 60 segundos. El tamaño se mide sobre el paquete recibido/enviado, no sobre caracteres Unicode ni sobre el objeto ya decodificado.

Los límites de 16 KiB para request y 64 KiB para response sustituyen la propuesta anterior de 64 KiB para solicitud que aparece en el diseño de operaciones administrativas. Para `atlas-admin/1`, los valores de esta tabla son los vigentes.

## 6. Validación y rechazo

La implementación debe validar en este orden lógico:

1. Tipo de socket y transporte admitidos.
2. Credenciales kernel del peer y allowlist configurada.
3. Recepción de un único paquete dentro de los límites.
4. Ausencia de truncamiento y ancillary data.
5. UTF-8 estricto y JSON estricto.
6. Profundidad, números y claves duplicadas.
7. Envelope exacto y versión de protocolo.
8. UUIDv4 canónico.
9. Operación dentro del catálogo cerrado.
10. Payload conforme a la especificación individual de la operación.
11. Autorización y precondiciones de dominio, dentro del proceso responsable, antes de cualquier efecto.

La validación del protocolo no reemplaza la validación de dominio. Un request sintácticamente válido no implica que el actor esté autorizado ni que la operación pueda ejecutarse.

### 6.1 Cuándo responder y cuándo cerrar

Se envía un envelope `rejected` únicamente cuando el peer ha sido autenticado como permitido, el paquete fue recibido de forma íntegra y es seguro enviar una respuesta.

Se cierra sin intentar respuesta cuando ocurra cualquiera de estos casos:

- peer no autorizado;
- paquete truncado;
- ancillary data presente o truncado;
- EOF/desconexión o error de transporte que impida una respuesta fiable.

Los errores de timeout, desconexión o envío fallido son también resultados de transporte; no deben convertirse en una afirmación de éxito o fracaso de dominio. El cliente debe tratar la ausencia de respuesta como resultado no confirmado según la operación, no como permiso para repetir ciegamente una mutación.

## 7. Envelope de respuesta

Toda respuesta de protocolo que pueda enviarse de forma segura usa exactamente este conjunto de claves:

```json
{
  "protocol": "atlas-admin/1",
  "request_id": "UUIDv4-canónico-o-null",
  "status": "completed",
  "code": "OK",
  "summary": "Descripción breve y no sensible",
  "result": {},
  "audit_ref": null
}
```

Reglas:

- `protocol` identifica el protocolo.
- `request_id` repite el UUID validado de la solicitud; puede ser `null` cuando el envelope no permitió recuperar un request ID canónico.
- `status` es uno de los estados definidos en §8.
- `code` es un código estable de máquina; no debe depender del texto de excepción.
- `summary` es una descripción breve, segura y no sensible.
- `result` es un objeto cuyo esquema depende de la operación; en rechazos de protocolo sin resultado de dominio se utiliza `{}`.
- `audit_ref` es una referencia opaca o `null`. Su formato, persistencia y obligatoriedad para operaciones concretas deben definirse en la especificación individual. No se debe inventar una referencia ni presentar `null` como evidencia de auditoría durable.

La respuesta no contiene secretos, trazas internas, rutas sensibles ni detalles que permitan convertir errores en una filtración de información.

## 8. Estados de respuesta

El conjunto normativo es cerrado:

| Estado | Significado |
|---|---|
| `completed` | La operación alcanzó el resultado completado definido por su contrato individual. |
| `rejected` | La solicitud fue rechazada antes de aceptar la operación o por una precondición que su contrato define como rechazo. |
| `pending` | La operación fue admitida, pero todavía no existe un resultado terminal. Solo se usa si la especificación individual define seguimiento y transición. |
| `unknown` | No puede demostrarse de forma fiable si la operación produjo su efecto o alcanzó un resultado terminal. |

No se permite reinterpretar timeout, desconexión o falta de respuesta como `rejected` o `completed`. La semántica de `pending` y `unknown` debe especificarse para cada operación que pueda tener ejecución prolongada o commit ambiguo.

El prototipo actual implementa únicamente respuestas `completed` para ping y `rejected` para rechazos de protocolo. Esto es un subconjunto de implementación y no elimina los estados `pending` y `unknown` del contrato.

## 9. Catálogo cerrado de operaciones

La allowlist completa de `atlas-admin/1` contiene exactamente:

1. `authority.ping`
2. `authority.diagnose`
3. `authority.migrations.plan`
4. `authority.operation.status`
5. `authority.initialize`
6. `authority.migrations.apply`
7. `authority.project_environment.provision`

No existen alias, extensiones dinámicas, operaciones batch, comodines ni operación genérica de ejecución. Añadir, retirar o renombrar una operación requiere una revisión explícita del contrato y aceptación del propietario.

Un nombre fuera de esta lista se rechaza como `UNKNOWN_OPERATION`. Un nombre catalogado que no esté habilitado en una versión concreta del servicio se rechaza como `OPERATION_DENIED`; reconocer el nombre no significa implementarlo ni autorizarlo.

### 9.1 authority.ping

**Estado:** especificación individual aprobada para el prototipo.

- Naturaleza: lectura pura de disponibilidad del handler.
- Payload exacto: objeto vacío `{}`.
- No requiere `operation_id`, motivo ni procedencia de operador.
- No abre SQLite, no inspecciona la ruta ni el filesystem de la base, no crea sesión, no conserva estado entre conexiones y no produce efectos.
- Resultado exacto:
  - `protocol_version`: `atlas-admin/1`.
  - `service_version`: versión de la distribución instalada; si no hay metadatos de distribución en ejecución desde checkout, fallback sincronizado con `[project].version` de `pyproject.toml`.
  - `handler_status`: `available`.
- Respuesta exitosa: `status: "completed"`, `code: "OK"`, `audit_ref: null`.

Ping acredita únicamente que el handler del protocolo pudo procesar la solicitud. No acredita disponibilidad de SQLite, salud de la base, listener persistente, autorización de dominio ni capacidad de ejecutar otras operaciones.

### 9.2 Reglas individuales compartidas

Las siguientes reglas aplican a las operaciones del catálogo y no amplían sus payloads.

**Lecturas**

- No reciben `operation_id`, motivo ni confirmación de mutación, salvo `authority.operation.status`, cuyo `operation_id` identifica la operación consultada y no una nueva mutación.
- No cambian el estado de dominio ni crean DB, ledger, sidecars, directorios o archivos.
- Pueden emitir telemetría operacional a journald, pero no insertan eventos de mutación en el ledger SQLite.
- La lectura de SQLite, cuando corresponda, abre la ruta canónica en modo read-only y activa `query_only`.

**Mutaciones**

Las únicas tres mutaciones del catálogo son `authority.initialize`, `authority.migrations.apply` y `authority.project_environment.provision`.

- Requieren `operation_id` UUIDv4, `reason` de 1–500 caracteres normalizados y `operator_evidence`.
- `operator_evidence` incluye como mínimo UID real observado, UID efectivo del frontend, TTY/sesión observada, timestamp de autorización y alcance exacto confirmado. Se registra como evidencia declarada por el frontend; el servicio no la confunde con `SO_PEERCRED`, identidad de ejecución ni identidad Atlas USER.
- La confirmación tipada se verifica en el frontend privilegiado antes de enviar la solicitud. El servicio vuelve a validar alcance, estado, invariantes y digest; no confía en la confirmación visual como sustituto de las precondiciones de dominio.
- El peer IPC debe superar `SO_PEERCRED` y la allowlist. La política local de UID no convierte cualquier payload de ese peer en una operación válida.
- El mismo `operation_id` y digest canónico devuelve el resultado ya registrado. El mismo ID con intención distinta devuelve `IDEMPOTENCY_CONFLICT`.
- Ninguna mutación se declara `completed` antes de demostrar el commit durable. Si no puede determinarse el resultado, devuelve `unknown/RESULT_UNKNOWN` y exige resolverlo con `authority.operation.status`.

### 9.3 authority.diagnose — diagnóstico read-only

**Payload exacto:**

```json
{"profile":"quick"}
```

`profile` acepta exactamente `quick` o `deep`. No admite ruta, nombre de archivo, SQL, tabla, pragma libre ni selector de directorio. La ubicación se toma exclusivamente de configuración protegida del servicio. No admite campos adicionales.

**Perfil quick:** inspecciona existencia/tipo del destino, symlink, propietario/modo de directorios y archivo, accesibilidad read-only, versión SQLite y coherencia básica de versión/ledger/checksums cuando el ledger está disponible. No ejecuta una comprobación íntegra costosa.

**Perfil deep:** incluye quick y además ejecuta la comprobación de integridad SQLite definida por la implementación (`integrity_check`, o una alternativa documentada y etiquetada). El resultado indica explícitamente qué comprobaciones se ejecutaron, cuáles no, su duración y estado.

**Resultado:** objeto de comprobaciones individuales con estado `PASS`, `FAIL`, `UNKNOWN` o `NOT_APPLICABLE`, código estable y resumen seguro. Diferencia DB ausente, DB inaccesible, ledger ausente, historial inconsistente, checksum divergente, archivo inesperado, permisos incorrectos y comprobación no ejecutada.

**Reglas:**

- La ausencia de DB durante el estado pre-bootstrap no equivale por sí sola a corrupción; se informa como `NOT_INITIALIZED`.
- Un diagnóstico parcial nunca se resume como saludable.
- Si la DB no existe, no se crea para diagnosticar.
- No hace checkpoint, vacuum, repair, migrate, chmod, chown, unlink ni limpieza de WAL/SHM.
- Ningún contenido de tablas de identidad, credenciales, autenticadores o secretos se devuelve al frontend.

### 9.4 authority.migrations.plan — plan determinista de migración

**Payload exacto:** objeto vacío `{}`. No acepta ruta ni selección de archivo/migración.

**Lecturas:** configuración protegida, manifiesto de migraciones publicadas y DB/ledger existente en modo read-only.

**Precondiciones para producir un plan aplicable:**

- DB existente y regular, no symlink;
- ruta canónica y permisos esperados;
- ledger inicializado y legible;
- historial continuo desde la versión inicial;
- nombres y checksums coincidentes con el manifiesto publicado;
- versión actual no superior a la versión de código;
- ninguna migración publicada faltante o alterada.

**Resultado:** `current_version`, `target_version` (última versión publicada compatible), lista ordenada de migraciones pendientes con nombre y checksum, digest del plan calculado por la autoridad y estado `APPLICABLE` o `BLOCKED` con razón estable.

**Reglas:**

- No crea DB, ledger, tablas, WAL/SHM, directorios ni archivos.
- No permite elegir migraciones, omitir versiones, downgrade ni ejecutar SQL enviado por el cliente.
- Un historial divergente produce `BLOCKED`, no un plan parcial ejecutable.
- El digest del plan es informativo y se vuelve a calcular al aplicar; no es un token de autorización ni evita la revalidación.

### 9.5 authority.operation.status — resolución de resultado durable

**Payload exacto:**

```json
{"operation_id":"<UUIDv4>"}
```

No admite filtros, SQL, paginación arbitraria ni consulta de otros registros.

**Acceso:** solo lectura del ledger administrativo canónico.

**Resultado:** uno de estos resultados de dominio:

- `COMMITTED_EXACT`: existe registro durable con el mismo operation ID y digest/tipo esperado; devuelve tipo de operación, digest, timestamp y referencia de auditoría.
- `NOT_COMMITTED`: el ledger está disponible, íntegro y permite demostrar que no existe commit para ese ID; devuelve evidencia mínima de la comprobación.
- `UNKNOWN`: ledger ausente, corrupto, inaccesible, inconsistente o incapaz de demostrar presencia/ausencia.

Si existe un registro para el ID pero el caller no puede demostrar que corresponde a la misma intención, no se devuelve `COMMITTED_EXACT`; se devuelve conflicto/resultado desconocido según la evidencia disponible. Esta operación nunca inicia, reintenta, repara ni revierte la operación consultada.

### 9.6 authority.initialize — bootstrap único

**Payload requerido:** exactamente los siguientes campos:

- `operation_id`: UUIDv4;
- `reason`: 1–500 caracteres normalizados;
- `confirmation_phrase`: nombre canónico exacto esperado por el frontend, en formato `INITIALIZE <canonical-database-name>`;
- `operator_evidence`: evidencia definida en §9.2.

No acepta ruta, nombre de archivo alternativo, directorio, parámetros SQLite ni lista de migraciones. El path se obtiene exclusivamente de configuración protegida.

**Confirmación frontend:** TTY foreground obligatorio; mostrar que se creará una autoridad nueva y el nombre canónico; exigir la frase exacta. Sin TTY, foreground, motivo o confirmación exacta, no se envía la mutación.

**Precondiciones del servicio:**

- path configurado coincide con el canónico;
- directorio padre preexistente, privado y con owner/mode esperado;
- destino inexistente como cualquier tipo de filesystem object, incluyendo symlink;
- no existe una DB válida, parcial o ledger previo en destino;
- migraciones de bootstrap publicadas y checksums íntegros;
- operation ID no usado con otra intención.

**Resultado:** versiones iniciales instaladas, referencia al evento de bootstrap y estado durable. El archivo se crea exclusivamente y sin seguir symlinks; SQLite y el bootstrap se ejecutan como `atlas-runtime`.

**Fallos:** nunca borrar automáticamente un archivo o DB parcialmente creada. Si el proceso cae después de crear el archivo y antes de confirmar el ledger, la siguiente acción es diagnóstico y resolución; no repetir bootstrap a ciegas ni asignar un ID nuevo. La atomicidad del primer evento/ledger y la creación del archivo debe demostrarse en pruebas específicas.

### 9.7 authority.migrations.apply — aplicar migraciones forward-only

**Payload requerido:** exactamente los siguientes campos:

- `operation_id`: UUIDv4;
- `reason`: 1–500 caracteres normalizados;
- `expected_current_version`: versión observada por el operador;
- `target_version`: versión objetivo exacta del plan;
- `plan_digest`: digest del plan mostrado;
- `confirmation_phrase`: `MIGRATE <expected_current_version> -> <target_version>`;
- `operator_evidence`: evidencia definida en §9.2.

No acepta ruta, SQL, archivo, nombre de migración libre ni downgrade.

**Confirmación frontend:** TTY foreground obligatorio; presentar versión actual, destino y migraciones exactas; exigir frase exacta y motivo.

**Precondiciones del servicio, revalidadas inmediatamente antes de escribir:**

- DB existente, regular, no symlink, ruta canónica;
- owner/mode y directorios correctos;
- versión real igual a `expected_current_version`;
- plan/digest recalculado coincide con el plan confirmado;
- secuencia, nombres y checksums completos;
- destino es la versión publicada compatible actual;
- no hay operación incompatible en curso ni estado de ledger ambiguo.

**Efecto:** aplica únicamente todas las migraciones forward-only comprendidas entre current y target, en orden publicado. No permite selección parcial, downgrade, salto ni SQL externo. La actualización del schema ledger y el evento administrativo de éxito quedan en el mismo commit transaccional.

**Resultado:** versión final y lista exacta aplicada, checksums y referencia de auditoría. Si ocurre un error, la transacción se revierte cuando aún no hubo commit. Si el resultado del commit no puede demostrarse, devuelve `unknown/RESULT_UNKNOWN`; no vuelve a aplicar automáticamente.

### 9.8 authority.project_environment.provision — asociación inicial

**Payload requerido:** exactamente los siguientes campos:

- `operation_id`: UUIDv4;
- `project_id`: ID canónico;
- `environment_id`: ID canónico;
- `reason`: 1–500 caracteres normalizados;
- `confirmation_phrase`: `PROVISION <project_id> -> <environment_id>`;
- `operator_evidence`: evidencia definida en §9.2.

No acepta datos de Project/Environment para crearlos, cambios de lifecycle, estado deseado arbitrario, actor/UID de ejecución ni campos adicionales.

**Confirmación frontend:** TTY foreground obligatorio; mostrar ambos IDs y el motivo; exigir frase exacta.

**Precondiciones del servicio dentro de una única UoW/transacción:**

- esquema y ledger compatibles, historial/checksums completos;
- Project y Environment canónicos existentes y elegibles;
- no existe ya la asociación;
- no hay asociación previa en estado conflictivo;
- operation ID/digest cumplen idempotencia;
- el writer de dominio y el evento administrativo comparten la misma transacción.

**Efecto:** crea solo la asociación inicial `ACTIVE`, revisión 1, y su evento inmutable correspondiente. No crea ni modifica Project, Environment, USER, AGENT, Grant, credenciales ni recursos adyacentes. No suspende, reactiva ni elimina asociaciones.

**Resultado:** IDs canónicos, estado inicial, revisión y referencia a evento de dominio/auditoría. Un conflicto de asociación preexistente no se convierte en actualización automática.

### 9.9 Matriz de capacidades

| Operación | Lee filesystem | Lee SQLite | Escribe SQLite | TTY foreground | Motivo |
|---|---:|---:|---:|---:|---:|
| `authority.ping` | No | No | No | No | No |
| `authority.diagnose` | Sí, ruta canónica | Sí, read-only | No | No | No |
| `authority.migrations.plan` | Sí, manifiesto/ruta canónica | Sí, read-only | No | No | No |
| `authority.operation.status` | Sí, ruta canónica | Sí, ledger read-only | No | No | No |
| `authority.initialize` | Sí, ruta canónica | Bootstrap | Sí | Sí | Sí |
| `authority.migrations.apply` | Sí, ruta/manifiesto | Sí | Sí | Sí | Sí |
| `authority.project_environment.provision` | Sí, ruta canónica | Sí | Sí | Sí | Sí |

La tabla describe el comportamiento lógico esperado; no concede al frontend acceso directo al filesystem/SQLite. Todas las lecturas y escrituras de autoridad se ejecutan dentro del servicio bajo la identidad de servicio.

### 9.10 Estado de especificación e implementación

El catálogo de siete operaciones es normativamente cerrado. Las especificaciones individuales anteriores recuperan las decisiones ya aprobadas en el diseño administrativo. Su incorporación aquí no significa que estén implementadas, probadas ni habilitadas.

- `authority.ping`: implementada en el handler de prototipo.
- Las otras seis operaciones: especificadas, pero no implementadas y no habilitadas.
- Las tres mutaciones requieren además cerrar y probar ledger, atomicidad, idempotencia, procedencia y reconciliación de commit ambiguo.
- Ninguna de estas especificaciones aprueba el despliegue del listener, systemd, permisos definitivos del host ni operaciones sobre la DB real.



### 9.11 Detalles de representación aún por cerrar

Las decisiones de dominio recuperadas fijan los campos y semánticas de los payloads anteriores, pero no todas las gramáticas de sus valores. Antes de implementar las seis operaciones pendientes deben cerrarse, sin ampliar los campos:

- La estructura exacta y la validación campo por campo de `operator_evidence`; ya están fijados como mínimo UID real observado, UID efectivo del frontend, TTY/sesión, timestamp de autorización y alcance exacto confirmado. No se debe tratar ninguno como sustituto de `SO_PEERCRED` ni inventar valores probatorios.
- La normalización exacta de `reason` dentro del límite de 1–500 caracteres.
- Las gramáticas canónicas de `project_id`, `environment_id`, `canonical-database-name` y las representaciones de versión/digest.
- Los esquemas completos de cada objeto de resultado, incluidos nombres de campos, tipos y códigos estables por fallo/precondición.
- El mapeo exhaustivo de resultados de dominio a `status/code` del envelope, incluidos los casos de `BLOCKED`, `NOT_INITIALIZED`, `COMMITTED_EXACT` y `NOT_COMMITTED`.

Estas precisiones son cierre de esquema, no permiso para agregar campos, rutas, selectores ni capacidades. Hasta que estén aprobadas, las operaciones siguen no implementadas y deshabilitadas.

## 10. Códigos de rechazo y errores

Los códigos son identificadores estables y no deben derivarse de mensajes de excepción. El texto de resumen puede evolucionar sin cambiar el código.

### 10.1 Códigos de protocolo observados en la implementación actual

La implementación de referencia actual utiliza:

- `EMPTY_REQUEST`
- `INVALID_UTF8`
- `INVALID_JSON`
- `INVALID_REQUEST`
- `UNSUPPORTED_PROTOCOL_VERSION`
- `REQUEST_TOO_LARGE`
- `UNKNOWN_OPERATION`
- `OPERATION_DENIED`
- `INVALID_ARGUMENTS`
- `MESSAGE_TRUNCATED`
- `ANCILLARY_DATA_FORBIDDEN`
- `UNAUTHORIZED_PEER`
- `PEER_DISCONNECTED`
- `TIMEOUT`
- `IDEMPOTENCY_CONFLICT` (requerido por las reglas compartidas de mutación).
- `RESULT_UNKNOWN` (requerido cuando no puede demostrarse el resultado durable de una mutación).
- `INTERNAL_ERROR`

La implementación actual del prototipo emite los códigos de transporte/protocolo anteriores; `IDEMPOTENCY_CONFLICT` y `RESULT_UNKNOWN` son además códigos normativos requeridos por las reglas compartidas de mutación, aunque no estén implementados en el prototipo. Los códigos concretos para conflictos de precondición y fallos de cada operación (por ejemplo, diagnósticos bloqueados o asociación existente) todavía requieren una tabla estable por operación antes de implementar esas operaciones. No se deben inventar códigos ad hoc a partir de excepciones.

### 10.2 Política de respuesta por clase

| Clase/código | Comportamiento de transporte |
|---|---|
| `UNAUTHORIZED_PEER` | Rechazar antes de leer; cerrar sin respuesta. |
| `MESSAGE_TRUNCATED` | Cerrar sin respuesta. |
| `ANCILLARY_DATA_FORBIDDEN` | Cerrar sin respuesta. |
| `PEER_DISCONNECTED` | Cerrar; no hay respuesta fiable. |
| `TIMEOUT` | Error de transporte; no inferir resultado de dominio. |
| `EMPTY_REQUEST`, `INVALID_UTF8`, `INVALID_JSON`, `INVALID_REQUEST`, `UNSUPPORTED_PROTOCOL_VERSION`, `REQUEST_TOO_LARGE`, `UNKNOWN_OPERATION`, `OPERATION_DENIED`, `INVALID_ARGUMENTS` | Enviar `rejected` solo si el peer está autorizado y el paquete no está truncado ni contiene ancillary prohibido. |
| `INTERNAL_ERROR` | Error interno/transport; no revelar detalle. La posibilidad de respuesta depende de que el canal siga siendo fiable. |

La asignación anterior refleja el comportamiento del prototipo y la regla de cierre seguro. Cualquier nuevo código debe documentar clase, estado, si se responde, y si el cliente puede conocer el resultado de dominio.

### 10.3 Resultado desconocido e idempotencia

Una desconexión o timeout después de que una mutación pueda haber comenzado no prueba que la mutación no se haya producido. El cliente no debe repetir automáticamente una mutación con un identificador nuevo.

Cada operación mutadora debe especificar antes de habilitarse su identificador de operación, digest/identidad de intención, política de repetición, consulta de estado y reconciliación de commit ambiguo. No se presupone idempotencia por pertenecer al protocolo. Las reglas generales de idempotencia de Atlas no sustituyen la declaración individual de cada operación.

## 11. Requisitos de seguridad comunes

- No aceptar SQL, shell, Python, comandos, rutas arbitrarias, nombres de módulos, variables de entorno ni ejecución genérica.
- No aceptar campos de identidad del proceso como prueba de peer; el peer procede del kernel.
- No confundir peer UID con operador humano ni con autorización Atlas.
- La validación de dominio y autorización se realiza en el proceso responsable, no se delega al frontend.
- Ninguna operación catalogada queda habilitada solo por existir en la allowlist.
- El protocolo no concede acceso directo a SQLite al frontend.
- No devolver secretos, credenciales, datos de autenticación ni trazas internas.
- Los errores de resultado incierto no deben provocar repetición automática de mutaciones.
- Las operaciones mutadoras requieren especificación individual de procedencia, motivo, autorización, idempotencia, auditoría y atomicidad antes de habilitarse.

## 12. Relación con documentos subordinados

- [Diseño de operaciones administrativas](local-authority-administrative-operations-design.md): diseño de dominio y propuestas; debe alinearse con este contrato y no definir el envelope común.
- [Auditoría de alineación IPC](local-authority-admin-ipc-contract-audit.md): evidencia de revisión y estado de implementación; no es fuente normativa.
- [Prototipo IPC Unix](local-authority-admin-ipc-prototype.md): descripción del comportamiento implementado; no amplía el catálogo ni autoriza despliegue.
- [Lifecycle del listener](local-authority-admin-listener-lifecycle.md): diseño separado de filesystem, listener y systemd; permanece sujeto a aprobación.
- [Contrato operativo de almacenamiento](local-authority-storage-operational-contract.md): gobierna almacenamiento y autoridad SQLite; no sustituye el contrato IPC.

## 13. Registro de discrepancias corregidas y pendientes

1. **Referencias de sección:** las antiguas referencias IPC a §§10.5, 11 y 15.1–15.2 del contrato raíz son incorrectas para este protocolo. La fuente normativa es este documento.
2. **Tamaño de solicitud:** 16 KiB es el límite vigente; sustituye la propuesta previa de 64 KiB del diseño de operaciones.
3. **Catálogo:** siete operaciones exactas; solo ping está implementada en el prototipo. Las otras seis requieren contratos individuales antes de habilitarse.
4. **Estados:** el conjunto normativo incluye `completed`, `rejected`, `pending` y `unknown`; el prototipo solo materializa el subconjunto necesario para ping/rechazos.
5. **Códigos:** la implementación tiene códigos de transporte/protocolo adicionales; este documento registra los observados y exige especificación individual de códigos de dominio.
6. **Listener:** la especificación del protocolo no aprueba la topología ni el lifecycle del listener persistente.
7. **Validación:** este contrato no declara pruebas ejecutadas ni validadas. La evidencia de validación debe registrarse en la auditoría con revisión de código exacta y resultado comunicado por el propietario.

## 14. Criterios de conformidad del protocolo

Una implementación solo puede declararse conforme a `atlas-admin/1` para una operación cuando se haya demostrado que:

- cumple transporte, autenticación del peer, envelope y límites comunes;
- rechaza estrictamente los mensajes inválidos;
- produce el envelope y estado definidos;
- implementa únicamente operaciones incluidas en el catálogo y habilitadas;
- cumple la especificación individual aprobada de la operación;
- maneja desconexión, timeout y resultado ambiguo según el contrato individual;
- no amplía privilegios ni expone acceso genérico;
- dispone de pruebas y evidencia adecuadas para el alcance que afirma.

La conformidad del handler de ping no equivale a conformidad de las seis operaciones restantes ni a aprobación de despliegue.
