# Contrato normativo IPC administrativo de autoridad local — atlas-admin/1

**Identificador:** ATLAS-CONTRACT-LOCAL-AUTHORITY-ADMIN-IPC  
**Versión del contrato:** 1.0  
**Estado:** baseline normativo de protocolo para desarrollo y prototipo; no autoriza despliegue ni operaciones administrativas reales.  
**Protocolo:** `atlas-admin/1`  
**Fecha:** 19 de noviembre de 2026.

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

- Requieren `operation_id` UUIDv4, `reason` canónico de 1–500 puntos de código Unicode y `operator_evidence`. La normalización normativa de `reason` está definida en §9.11.3; el servicio rechaza valores no canónicos y nunca los corrige silenciosamente.
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

Las decisiones de dominio y las aprobaciones expresas del propietario fijan ya la estructura de `operator_evidence`, la normalización de `reason` y las gramáticas de los identificadores/valores administrativos definidos en §9.11.4. Antes de implementar las seis operaciones pendientes todavía deben cerrarse:

- Los esquemas completos de cada objeto de resultado, incluidos nombres de campos, tipos y códigos estables por fallo/precondición.
- El mapeo exhaustivo de resultados de dominio a `status/code` del envelope, incluidos los casos de `BLOCKED`, `NOT_INITIALIZED`, `COMMITTED_EXACT` y `NOT_COMMITTED`.
- La serialización canónica exacta del contenido del plan que alimenta el SHA-256 de `plan_digest`; la gramática textual del digest sí queda fijada en §9.11.4.

Estas precisiones son cierre de esquema, no permiso para agregar campos, rutas, selectores ni capacidades. Las seis operaciones no implementadas siguen deshabilitadas.

### 9.11.1 Semántica y frontera de confianza de la evidencia

La revisión de confianza establece las siguientes restricciones semánticas para los cinco elementos requeridos:

| Elemento | Qué representa | Qué no demuestra ni autoriza |
|---|---|---|
| UID real observado | El UID real que el frontend afirma haber observado para el contexto del operador que inició la confirmación. | No identifica por sí solo a una persona, no demuestra autenticación Atlas y no sustituye las credenciales kernel del peer IPC. |
| UID efectivo del frontend | El UID efectivo que el propio frontend afirma observar en su proceso al preparar la solicitud. | No es el UID del operador, no es necesariamente el UID del peer visto por el servicio y no concede privilegios. |
| TTY/sesión observada | La observación del frontend sobre el terminal y la sesión desde los que se realizó la confirmación interactiva exigida por la operación. | Un nombre de TTY, un identificador de sesión o la mera existencia de un terminal no prueban presencia física, identidad humana ni autorización. |
| Timestamp de autorización | El instante que el frontend afirma corresponder a la aceptación de la confirmación explícita para esa operación y alcance. | No es la hora de recepción del servicio, no acredita por sí mismo que la confirmación ocurrió y no debe usarse como reloj de commit o de auditoría del servidor. |
| Alcance exacto confirmado | La operación concreta y los identificadores/valores de destino que el frontend presentó y cuya confirmación solicitó. | No puede ampliar el payload ni convertirse en una ruta, selector, conjunto de capacidades o instrucción ejecutable aportada por el cliente. |

Reglas de interpretación:

1. Todo el objeto `operator_evidence` es una **declaración no confiable del frontend**. Su registro conserva procedencia declarada; no eleva la confianza de los valores ni transforma la evidencia en una credencial.
2. El servicio conserva por separado las credenciales observadas mediante `SO_PEERCRED` y su propia hora de recepción. No copia ni sustituye esos valores con los declarados por el frontend.
3. El frontend privilegiado es responsable de exigir TTY foreground y confirmación tipada antes de enviar. El servicio no puede afirmar que verificó de forma independiente el TTY del frontend solo porque recibió esos datos.
4. El servicio vuelve a derivar el alcance permitido desde `operation` y los campos de payload definidos para esa operación. Si el alcance declarado no coincide exactamente con ese alcance derivado, debe rechazar la solicitud antes de cualquier efecto.
5. Ningún elemento de `operator_evidence` reemplaza autenticación/autorización de dominio, allowlist de peer, precondiciones, digest de idempotencia ni auditoría durable.
6. La evidencia conserva separadas tres procedencias: (a) datos observados/declarados por el frontend, (b) credenciales kernel observadas por el servicio y (c) timestamp/resultado de commit generados por la autoridad.

### 9.11.2 Representación JSON aprobada de operator_evidence

**Estado:** estructura y tipos JSON aprobados por el propietario para las tres mutaciones. La normalización de `reason` está aprobada y definida en §9.11.3; las gramáticas de IDs, nombre de DB, versiones y digest están aprobadas y definidas en §9.11.4.

El objeto `operator_evidence` tiene exactamente estas cinco propiedades, todas obligatorias y no anulables:

```json
{
  "operator_real_uid": 1000,
  "frontend_effective_uid": 0,
  "tty_session": {
    "terminal_device": "/dev/pts/2",
    "session_id": 1234,
    "process_group_id": 1234,
    "foreground_process_group_id": 1234
  },
  "authorized_at": "2026-11-19T02:15:30.123456Z",
  "confirmed_scope": {}
}
```

No se permiten propiedades adicionales, propiedades ausentes, valores `null`, booleanos donde se exige un entero ni conversiones implícitas desde cadenas.

**Tipos y restricciones estructurales:**

- `operator_real_uid`: entero JSON no negativo y representable por el tipo UID del sistema operativo de destino. Se admite cualquier UID válido; no se exige UID distinto de cero.
- `frontend_effective_uid`: entero JSON no negativo y representable por el tipo UID del sistema operativo de destino. Se admite cualquier UID válido; no se exige UID cero. La autorización efectiva sigue siendo una política separada.
- `tty_session`: objeto obligatorio con exactamente cuatro propiedades:
  - `terminal_device`: cadena UTF-8 no vacía, ruta absoluta, sin byte NUL y con longitud máxima de 256 bytes. Es una declaración del frontend; el servicio no abre, resuelve ni inspecciona esa ruta como parte de la validación de evidencia.
  - `session_id`: entero JSON positivo y representable por el tipo PID del sistema operativo de destino.
  - `process_group_id`: entero JSON positivo y representable por el tipo PID del sistema operativo de destino.
  - `foreground_process_group_id`: entero JSON positivo y representable por el tipo PID del sistema operativo de destino. En el instante de autorización, el frontend debe haber observado que este valor coincide con `process_group_id`; el frontend también debe comprobar el TTY foreground y la relación de terminal/sesión exigida por el contrato. El servicio valida la coherencia declarada entre ambos números, pero no afirma haber observado el terminal del frontend.
- `authorized_at`: cadena UTC en formato exacto `YYYY-MM-DDTHH:MM:SS.ffffffZ` (seis dígitos de fracción, sufijo literal `Z`, sin offset alternativo). El frontend la genera después de aceptar la confirmación tipada y antes de transmitir la solicitud. No sustituye el reloj de recepción del servicio.
- `confirmed_scope`: objeto no anulable, con esquema exacto dependiente de `operation`, definido abajo.

Los enteros son enteros JSON, no booleanos, cadenas ni números de punto flotante. Los límites de representación del decoder y del protocolo siguen aplicando. UID, session ID y process-group ID son declaraciones del frontend, no credenciales verificadas por el kernel del servicio.

**Esquemas exactos de `confirmed_scope`:**

Para `authority.initialize`:

```json
{
  "operation": "authority.initialize",
  "canonical_database_name": "authority.sqlite3",
  "reason": "Inicializar la autoridad local"
}
```

Para `authority.migrations.apply`:

```json
{
  "operation": "authority.migrations.apply",
  "expected_current_version": 27,
  "target_version": 29,
  "plan_digest": "<digest-del-plan>",
  "reason": "Aplicar las migraciones revisadas"
}
```

Para `authority.project_environment.provision`:

```json
{
  "operation": "authority.project_environment.provision",
  "project_id": "<project-id-canonico>",
  "environment_id": "<environment-id-canonico>",
  "reason": "Vincular el entorno inicial del proyecto"
}
```

En cada variante:

1. El conjunto de propiedades es exacto; no se admiten claves extra, ausentes ni valores nulos.
2. `operation` debe coincidir exactamente con el nombre de operación del envelope.
3. Los valores de alcance deben coincidir exactamente, tipo incluido, con la fuente autoritativa correspondiente: para `authority.migrations.apply` y `authority.project_environment.provision`, con los campos respectivos del payload; para `authority.initialize`, `canonical_database_name` debe coincidir con el nombre canónico derivado por el servicio desde su configuración protegida y la `confirmation_phrase` del payload debe corresponder exactamente a ese mismo nombre.
4. `reason` se repite deliberadamente y debe ser idéntico, carácter por carácter, al `reason` del payload. No se normaliza silenciosamente uno para hacerlo coincidir con el otro; la regla de normalización previa a la construcción del request sigue pendiente y se especifica por separado.
5. Para `authority.migrations.apply`, las versiones y `plan_digest` deben cumplir §9.11.4, además de coincidir exactamente con sus valores correspondientes en el payload.
6. Los nombres canónicos e IDs deben cumplir §9.11.4. No se relaja por ello la igualdad exacta entre los valores que el servicio compara.

El servicio deriva de forma independiente el objeto esperado de alcance a partir de la operación, del payload y, para el nombre canónico de la base durante `authority.initialize`, de su configuración protegida. La comparación es estructural y exacta, sin coerción de tipos, normalización oportunista ni aceptación de subconjuntos. Cualquier diferencia produce rechazo antes de iniciar efectos de dominio.

La frase de confirmación tipada (`confirmation_phrase`) permanece en el payload de cada mutación y se valida por separado contra la gramática de esa operación. No se duplica dentro de `confirmed_scope`: el alcance estructurado contiene los datos que el frontend presentó, y la frase es una prueba de confirmación interactiva distinta.

**Reglas del frontend:** debe obtener los cuatro datos TTY/sesión desde sus observaciones locales en el momento de la confirmación; verificar que la terminal usada para la interacción es la esperada, que la sesión y los grupos de procesos corresponden y que el proceso está en foreground; luego construir la evidencia y enviar. No debe rellenar campos desconocidos con cero, valores ficticios o datos de otra sesión.

**Límites de confianza:** aprobar esta representación no convierte la evidencia en autenticación fuerte, prueba de presencia humana ni autorización de dominio. Tampoco aprueba UID de producción, uso obligatorio de root, listener persistente, systemd, acceso directo a SQLite ni ejecución de las mutaciones.

### 9.11.3 Normalización canónica de reason

**Estado:** aprobada expresamente por el propietario el 19 de noviembre de 2026. Esta regla se aplica al campo `reason` de las tres mutaciones y al valor duplicado en `operator_evidence.confirmed_scope.reason`.

La normalización produce una representación canónica antes de solicitar la confirmación tipada:

1. La entrada debe ser una cadena Unicode válida. No se aplica normalización Unicode NFC, NFD, NFKC ni NFKD; las secuencias de puntos de código se conservan exactamente, salvo la transformación de whitespace definida abajo.
2. Se rechazan todos los caracteres Unicode de categoría general `Cc` (controles), incluidos C0, DEL y C1. No se convierten controles en espacios. En particular, tabuladores, CR y LF se rechazan.
3. Cada secuencia máxima de caracteres con la propiedad Unicode `White_Space` se sustituye por un único espacio ASCII `U+0020`.
4. Se eliminan los espacios ASCII `U+0020` resultantes al principio y al final. Una entrada vacía o compuesta únicamente por whitespace se rechaza.
5. La longitud del resultado canónico debe estar entre 1 y 500 puntos de código Unicode, inclusive. El límite se aplica al resultado normalizado, no a los bytes UTF-8 ni a grafemas visuales.

**Frontera de validación:**

- El frontend prepara el valor canónico antes de presentarlo para confirmación; la confirmación tipada debe mostrar exactamente el valor que se enviará.
- El servicio valida que el `reason` recibido ya esté en forma canónica. Si aplicar el algoritmo anterior cambiara el valor recibido, lo rechaza; no lo recorta, colapsa ni reescribe silenciosamente.
- Después de validar la forma canónica, `operator_evidence.confirmed_scope.reason` debe ser idéntico, carácter por carácter y por tipo, al `reason` del payload.
- La canonicalización del digest de idempotencia utiliza ese valor canónico exacto. No se realizan transformaciones adicionales dependientes de locale.
- Esta regla define la representación de nuevos requests `atlas-admin/1`; no reescribe, migra ni altera motivos históricos ya almacenados.

**Controles Unicode:** el rechazo cubre la categoría general Unicode `Cc`, no solo C0 y DEL. No se extiende a otras categorías Unicode de formato o carácter invisible (por ejemplo, `Cf`) como parte de esta decisión; cualquier política adicional requeriría aprobación separada.

### 9.11.4 Gramáticas canónicas de IDs, nombre de base, versiones y digest

**Estado:** aprobadas expresamente por el propietario el 19 de noviembre de 2026. Estas reglas fijan la representación de los valores usados por las mutaciones de `atlas-admin/1`; no cambian los modelos generales de dominio ni migran identificadores históricos.

#### Identificadores `project_id` y `environment_id`

Ambos campos usan la misma gramática ASCII:

- Longitud: de 1 a 128 bytes ASCII inclusive (equivalente a 1–128 caracteres, porque solo se admite ASCII).
- Caracteres permitidos: letras minúsculas ASCII `a-z`, dígitos `0-9` y guion ASCII `-`.
- El primer y último carácter deben ser una letra minúscula o un dígito.
- No se admiten mayúsculas, guion bajo, puntos, espacios, barras, Unicode no ASCII ni separadores repetidos con semántica especial.
- Expresión regular normativa: `^[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?# Contrato normativo IPC administrativo de autoridad local — atlas-admin/1

**Identificador:** ATLAS-CONTRACT-LOCAL-AUTHORITY-ADMIN-IPC  
**Versión del contrato:** 1.0  
**Estado:** baseline normativo de protocolo para desarrollo y prototipo; no autoriza despliegue ni operaciones administrativas reales.  
**Protocolo:** `atlas-admin/1`  
**Fecha:** 19 de noviembre de 2026.

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

- Requieren `operation_id` UUIDv4, `reason` canónico de 1–500 puntos de código Unicode y `operator_evidence`. La normalización normativa de `reason` está definida en §9.11.3; el servicio rechaza valores no canónicos y nunca los corrige silenciosamente.
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

Las decisiones de dominio y las aprobaciones expresas del propietario fijan ya la estructura de `operator_evidence`, la normalización de `reason` y las gramáticas de los identificadores/valores administrativos definidos en §9.11.4. Antes de implementar las seis operaciones pendientes todavía deben cerrarse:

- Los esquemas completos de cada objeto de resultado, incluidos nombres de campos, tipos y códigos estables por fallo/precondición.
- El mapeo exhaustivo de resultados de dominio a `status/code` del envelope, incluidos los casos de `BLOCKED`, `NOT_INITIALIZED`, `COMMITTED_EXACT` y `NOT_COMMITTED`.
- La serialización canónica exacta del contenido del plan que alimenta el SHA-256 de `plan_digest`; la gramática textual del digest sí queda fijada en §9.11.4.

Estas precisiones son cierre de esquema, no permiso para agregar campos, rutas, selectores ni capacidades. Las seis operaciones no implementadas siguen deshabilitadas.

### 9.11.1 Semántica y frontera de confianza de la evidencia

La revisión de confianza establece las siguientes restricciones semánticas para los cinco elementos requeridos:

| Elemento | Qué representa | Qué no demuestra ni autoriza |
|---|---|---|
| UID real observado | El UID real que el frontend afirma haber observado para el contexto del operador que inició la confirmación. | No identifica por sí solo a una persona, no demuestra autenticación Atlas y no sustituye las credenciales kernel del peer IPC. |
| UID efectivo del frontend | El UID efectivo que el propio frontend afirma observar en su proceso al preparar la solicitud. | No es el UID del operador, no es necesariamente el UID del peer visto por el servicio y no concede privilegios. |
| TTY/sesión observada | La observación del frontend sobre el terminal y la sesión desde los que se realizó la confirmación interactiva exigida por la operación. | Un nombre de TTY, un identificador de sesión o la mera existencia de un terminal no prueban presencia física, identidad humana ni autorización. |
| Timestamp de autorización | El instante que el frontend afirma corresponder a la aceptación de la confirmación explícita para esa operación y alcance. | No es la hora de recepción del servicio, no acredita por sí mismo que la confirmación ocurrió y no debe usarse como reloj de commit o de auditoría del servidor. |
| Alcance exacto confirmado | La operación concreta y los identificadores/valores de destino que el frontend presentó y cuya confirmación solicitó. | No puede ampliar el payload ni convertirse en una ruta, selector, conjunto de capacidades o instrucción ejecutable aportada por el cliente. |

Reglas de interpretación:

1. Todo el objeto `operator_evidence` es una **declaración no confiable del frontend**. Su registro conserva procedencia declarada; no eleva la confianza de los valores ni transforma la evidencia en una credencial.
2. El servicio conserva por separado las credenciales observadas mediante `SO_PEERCRED` y su propia hora de recepción. No copia ni sustituye esos valores con los declarados por el frontend.
3. El frontend privilegiado es responsable de exigir TTY foreground y confirmación tipada antes de enviar. El servicio no puede afirmar que verificó de forma independiente el TTY del frontend solo porque recibió esos datos.
4. El servicio vuelve a derivar el alcance permitido desde `operation` y los campos de payload definidos para esa operación. Si el alcance declarado no coincide exactamente con ese alcance derivado, debe rechazar la solicitud antes de cualquier efecto.
5. Ningún elemento de `operator_evidence` reemplaza autenticación/autorización de dominio, allowlist de peer, precondiciones, digest de idempotencia ni auditoría durable.
6. La evidencia conserva separadas tres procedencias: (a) datos observados/declarados por el frontend, (b) credenciales kernel observadas por el servicio y (c) timestamp/resultado de commit generados por la autoridad.

### 9.11.2 Representación JSON aprobada de operator_evidence

**Estado:** estructura y tipos JSON aprobados por el propietario para las tres mutaciones. La normalización de `reason` está aprobada y definida en §9.11.3; las gramáticas de IDs, nombre de DB, versiones y digest están aprobadas y definidas en §9.11.4.

El objeto `operator_evidence` tiene exactamente estas cinco propiedades, todas obligatorias y no anulables:

```json
{
  "operator_real_uid": 1000,
  "frontend_effective_uid": 0,
  "tty_session": {
    "terminal_device": "/dev/pts/2",
    "session_id": 1234,
    "process_group_id": 1234,
    "foreground_process_group_id": 1234
  },
  "authorized_at": "2026-11-19T02:15:30.123456Z",
  "confirmed_scope": {}
}
```

No se permiten propiedades adicionales, propiedades ausentes, valores `null`, booleanos donde se exige un entero ni conversiones implícitas desde cadenas.

**Tipos y restricciones estructurales:**

- `operator_real_uid`: entero JSON no negativo y representable por el tipo UID del sistema operativo de destino. Se admite cualquier UID válido; no se exige UID distinto de cero.
- `frontend_effective_uid`: entero JSON no negativo y representable por el tipo UID del sistema operativo de destino. Se admite cualquier UID válido; no se exige UID cero. La autorización efectiva sigue siendo una política separada.
- `tty_session`: objeto obligatorio con exactamente cuatro propiedades:
  - `terminal_device`: cadena UTF-8 no vacía, ruta absoluta, sin byte NUL y con longitud máxima de 256 bytes. Es una declaración del frontend; el servicio no abre, resuelve ni inspecciona esa ruta como parte de la validación de evidencia.
  - `session_id`: entero JSON positivo y representable por el tipo PID del sistema operativo de destino.
  - `process_group_id`: entero JSON positivo y representable por el tipo PID del sistema operativo de destino.
  - `foreground_process_group_id`: entero JSON positivo y representable por el tipo PID del sistema operativo de destino. En el instante de autorización, el frontend debe haber observado que este valor coincide con `process_group_id`; el frontend también debe comprobar el TTY foreground y la relación de terminal/sesión exigida por el contrato. El servicio valida la coherencia declarada entre ambos números, pero no afirma haber observado el terminal del frontend.
- `authorized_at`: cadena UTC en formato exacto `YYYY-MM-DDTHH:MM:SS.ffffffZ` (seis dígitos de fracción, sufijo literal `Z`, sin offset alternativo). El frontend la genera después de aceptar la confirmación tipada y antes de transmitir la solicitud. No sustituye el reloj de recepción del servicio.
- `confirmed_scope`: objeto no anulable, con esquema exacto dependiente de `operation`, definido abajo.

Los enteros son enteros JSON, no booleanos, cadenas ni números de punto flotante. Los límites de representación del decoder y del protocolo siguen aplicando. UID, session ID y process-group ID son declaraciones del frontend, no credenciales verificadas por el kernel del servicio.

**Esquemas exactos de `confirmed_scope`:**

Para `authority.initialize`:

```json
{
  "operation": "authority.initialize",
  "canonical_database_name": "authority.sqlite3",
  "reason": "Inicializar la autoridad local"
}
```

Para `authority.migrations.apply`:

```json
{
  "operation": "authority.migrations.apply",
  "expected_current_version": 27,
  "target_version": 29,
  "plan_digest": "<digest-del-plan>",
  "reason": "Aplicar las migraciones revisadas"
}
```

Para `authority.project_environment.provision`:

```json
{
  "operation": "authority.project_environment.provision",
  "project_id": "<project-id-canonico>",
  "environment_id": "<environment-id-canonico>",
  "reason": "Vincular el entorno inicial del proyecto"
}
```

En cada variante:

1. El conjunto de propiedades es exacto; no se admiten claves extra, ausentes ni valores nulos.
2. `operation` debe coincidir exactamente con el nombre de operación del envelope.
3. Los valores de alcance deben coincidir exactamente, tipo incluido, con la fuente autoritativa correspondiente: para `authority.migrations.apply` y `authority.project_environment.provision`, con los campos respectivos del payload; para `authority.initialize`, `canonical_database_name` debe coincidir con el nombre canónico derivado por el servicio desde su configuración protegida y la `confirmation_phrase` del payload debe corresponder exactamente a ese mismo nombre.
4. `reason` se repite deliberadamente y debe ser idéntico, carácter por carácter, al `reason` del payload. No se normaliza silenciosamente uno para hacerlo coincidir con el otro; la regla de normalización previa a la construcción del request sigue pendiente y se especifica por separado.
5. Para `authority.migrations.apply`, las versiones y `plan_digest` deben cumplir §9.11.4, además de coincidir exactamente con sus valores correspondientes en el payload.
6. Los nombres canónicos e IDs deben cumplir §9.11.4. No se relaja por ello la igualdad exacta entre los valores que el servicio compara.

El servicio deriva de forma independiente el objeto esperado de alcance a partir de la operación, del payload y, para el nombre canónico de la base durante `authority.initialize`, de su configuración protegida. La comparación es estructural y exacta, sin coerción de tipos, normalización oportunista ni aceptación de subconjuntos. Cualquier diferencia produce rechazo antes de iniciar efectos de dominio.

La frase de confirmación tipada (`confirmation_phrase`) permanece en el payload de cada mutación y se valida por separado contra la gramática de esa operación. No se duplica dentro de `confirmed_scope`: el alcance estructurado contiene los datos que el frontend presentó, y la frase es una prueba de confirmación interactiva distinta.

**Reglas del frontend:** debe obtener los cuatro datos TTY/sesión desde sus observaciones locales en el momento de la confirmación; verificar que la terminal usada para la interacción es la esperada, que la sesión y los grupos de procesos corresponden y que el proceso está en foreground; luego construir la evidencia y enviar. No debe rellenar campos desconocidos con cero, valores ficticios o datos de otra sesión.

**Límites de confianza:** aprobar esta representación no convierte la evidencia en autenticación fuerte, prueba de presencia humana ni autorización de dominio. Tampoco aprueba UID de producción, uso obligatorio de root, listener persistente, systemd, acceso directo a SQLite ni ejecución de las mutaciones.

### 9.11.3 Normalización canónica de reason

**Estado:** aprobada expresamente por el propietario el 19 de noviembre de 2026. Esta regla se aplica al campo `reason` de las tres mutaciones y al valor duplicado en `operator_evidence.confirmed_scope.reason`.

La normalización produce una representación canónica antes de solicitar la confirmación tipada:

1. La entrada debe ser una cadena Unicode válida. No se aplica normalización Unicode NFC, NFD, NFKC ni NFKD; las secuencias de puntos de código se conservan exactamente, salvo la transformación de whitespace definida abajo.
2. Se rechazan todos los caracteres Unicode de categoría general `Cc` (controles), incluidos C0, DEL y C1. No se convierten controles en espacios. En particular, tabuladores, CR y LF se rechazan.
3. Cada secuencia máxima de caracteres con la propiedad Unicode `White_Space` se sustituye por un único espacio ASCII `U+0020`.
4. Se eliminan los espacios ASCII `U+0020` resultantes al principio y al final. Una entrada vacía o compuesta únicamente por whitespace se rechaza.
5. La longitud del resultado canónico debe estar entre 1 y 500 puntos de código Unicode, inclusive. El límite se aplica al resultado normalizado, no a los bytes UTF-8 ni a grafemas visuales.

**Frontera de validación:**

- El frontend prepara el valor canónico antes de presentarlo para confirmación; la confirmación tipada debe mostrar exactamente el valor que se enviará.
- El servicio valida que el `reason` recibido ya esté en forma canónica. Si aplicar el algoritmo anterior cambiara el valor recibido, lo rechaza; no lo recorta, colapsa ni reescribe silenciosamente.
- Después de validar la forma canónica, `operator_evidence.confirmed_scope.reason` debe ser idéntico, carácter por carácter y por tipo, al `reason` del payload.
- La canonicalización del digest de idempotencia utiliza ese valor canónico exacto. No se realizan transformaciones adicionales dependientes de locale.
- Esta regla define la representación de nuevos requests `atlas-admin/1`; no reescribe, migra ni altera motivos históricos ya almacenados.

.
- La cadena recibida debe cumplir la gramática directamente. No se aplica trim, lowercase, transliteración, normalización Unicode ni corrección silenciosa.
- Los valores siguen siendo identificadores opacos: el protocolo no deriva rutas, nombres de archivo, nombres SQL ni permisos a partir de ellos.

La gramática solo valida la forma. La autoridad debe resolver ambos IDs contra los registros canónicos dentro de la UoW y verificar existencia, elegibilidad, estado y ausencia de asociación/conflicto conforme a §9.8. Conocer o presentar un ID válido no concede acceso ni crea el recurso.

Esta restricción es específica del límite IPC administrativo. No cambia retroactivamente los tipos `ProjectId`/`EnvironmentId`, las filas existentes ni los contratos de otros subsistemas. La compatibilidad de registros históricos que no satisfagan esta gramática debe evaluarse antes de habilitar provisioning por IPC; no se deben renombrar ni migrar automáticamente.

#### `canonical_database_name`

- El único valor admitido es la cadena ASCII exacta `authority.sqlite3`.
- Se compara byte por byte; no se acepta ruta, separador, prefijo, sufijo, mayúsculas alternativas ni otro nombre.
- En `authority.initialize`, el servicio no toma este valor como selector del cliente: lo deriva de la configuración protegida y exige que `operator_evidence.confirmed_scope.canonical_database_name` y la frase de confirmación coincidan exactamente con ese valor.
- El nombre no autoriza al frontend a abrir, crear ni seleccionar la base. La ruta física continúa siendo exclusivamente configuración protegida del servicio.

#### Versiones de migración

`expected_current_version`, `target_version` y las versiones equivalentes en `confirmed_scope` son enteros JSON con estas restricciones:

- Deben ser enteros JSON matemáticos, no booleanos, cadenas ni números de punto flotante; no se permite coerción.
- Rango: de 1 a `2^63 - 1` inclusive, compatible con el entero firmado de 64 bits usado por SQLite.
- La representación JSON canónica es el entero decimal sin signo positivo explícito, sin ceros iniciales (salvo el valor cero, que no pertenece al rango) y sin notación exponencial ni fraccionaria.
- Para `authority.migrations.apply`, `target_version` debe ser estrictamente mayor que `expected_current_version`.
- La autoridad compara la versión actual leída del ledger y el destino del plan recalculado; la gramática no permite downgrade, saltos ni selección de migraciones.

#### `plan_digest`

- Algoritmo: SHA-256.
- Representación: exactamente 64 caracteres ASCII hexadecimales en minúsculas (`[0-9a-f]{64}`), sin prefijo (`sha256:`), espacios, padding ni terminador.
- El valor debe coincidir exactamente entre payload, `confirmed_scope` y digest recalculado por la autoridad.
- El digest identifica la integridad del plan, no es un token, credencial, autorización ni sustituto de revalidar manifiesto, ledger, secuencia y checksums.
- La serialización canónica exacta de los campos del plan antes de calcular SHA-256 permanece pendiente de especificación; hasta cerrarla, no se debe implementar ni habilitar `authority.migrations.apply` basándose solo en esta gramática.

Cualquier valor fuera de estas reglas se rechaza antes de iniciar efectos de dominio.



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
3. **Catálogo:** siete operaciones exactas; solo ping está implementada en el prototipo. Las otras seis ya tienen especificaciones individuales en §§9.3–9.8, pero siguen deshabilitadas hasta cerrar los detalles de §9.11, implementar y validar.
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
