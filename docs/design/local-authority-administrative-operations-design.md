# Diseño de operaciones administrativas de autoridad local

**Estado:** propuesta de diseño para revisión; no autoriza implementación privilegiada ni operaciones sobre una base real.  
**Fecha:** 18 de noviembre de 2026.  
**Fase:** 2.5 — operaciones administrativas de autoridad.  
**Base de código:** `main` después de `5deb6bf1cf1a53a1eb905d5c23e61f4f027c5fee`.

Este diseño desarrolla la frontera establecida en [el contrato operativo de almacenamiento de autoridad local](local-authority-storage-operational-contract.md). La base primaria aún no está desplegada. El CLI de provisioning existente no es apto para ella y no debe ejecutarse contra esa futura base.

## 1. Objetivos y no objetivos

### Objetivos

1. Hacer explícitas y auditables las operaciones de diagnóstico, inicialización, migración y provisioning.
2. Ejecutar toda apertura de escritura SQLite bajo UID/GID `atlas-runtime`.
3. Mantener la autorización/procedencia del operador separada de la identidad Linux que ejecuta la transacción.
4. Evitar que el frontend privilegiado reciba una ruta SQLite, abra SQLite o pueda solicitar SQL/comandos arbitrarios.
5. Hacer que cada mutación valide nuevamente el estado y las invariantes dentro del proceso de autoridad y de su transacción.
6. Resolver reintentos y resultados ambiguos sin duplicar operaciones.

### No objetivos

- No habilitar HTTP, consola conversacional, plugins, skills o AGENT para ejecutar estas operaciones.
- No proporcionar una API SQL ni un ejecutor genérico de comandos.
- No crear ni modificar usuarios, grupos, sudoers, PAM, systemd o permisos del host en esta fase.
- No inicializar ni provisionar una base real, ni ejecutar migraciones en Debian.
- No resolver todavía backup/restore, custodia de claves ni anti-rollback; corresponden a la siguiente fase.

## 2. Actores y fronteras de confianza

| Actor | Responsabilidad | Acceso SQLite |
|---|---|---|
| Operador humano | Solicita y confirma una operación administrativa | Ninguno |
| Frontend privilegiado | Verifica invocación, TTY, alcance, motivo y confirmación | Ninguno, ni siquiera lectura |
| Servicio administrativo de autoridad | Valida la petición y ejecuta el caso de uso | Como `atlas-runtime` |
| Runtime conversacional / skills / plugins | Solicita capacidades ordinarias mediante APIs autorizadas | Ninguno |
| Administrador root del host | Administración y recuperación del sistema | Es parte de la raíz de confianza del host |

La separación no pretende defender la base contra un root malicioso. Un root irrestricto puede cambiar ejecutables, unidades, permisos y datos. El objetivo es que el flujo normal no ejecute SQLite como root y que procesos conversacionales o extensiones no confiables no obtengan el UID propietario de la base.

El frontend debe ser un artefacto instalado desde una ubicación no modificable por usuarios ordinarios, con configuración protegida. No se debe ejecutar como root código importado desde un checkout de desarrollo escribible por el operador.

## 3. Arquitectura candidata de delegación

### 3.1 Candidato preferido para evaluación: socket Unix local estrecho

Se propone evaluar un canal local dedicado entre el frontend privilegiado y un servicio administrativo ejecutado como `atlas-runtime`:

- Socket AF_UNIX local, sin listener TCP ni exposición de red.
- Preferencia inicial por `SOCK_SEQPACKET` para conservar los límites de cada mensaje; si la plataforma o la integración con systemd no lo soporta de forma fiable, documentar framing de longitud fija/máxima sobre `SOCK_STREAM`.
- El servicio obtiene las credenciales del peer desde el kernel mediante `SO_PEERCRED`; no acepta un UID de cliente declarado en JSON como prueba de identidad.
- El socket queda accesible solo a la frontera privilegiada del host. El servicio rechaza peers que no cumplan el UID permitido.
- El servicio se ejecuta con UID/GID `atlas-runtime`, `NoNewPrivileges=yes`, sin capabilities, `UMask=0077`, filesystem endurecido y escritura limitada al directorio de autoridad.
- El servicio recibe una lista cerrada de operaciones y payloads tipados. No acepta ruta de base, ruta de ejecutable, SQL, nombres de módulos, variables de entorno, opciones de shell ni comandos.
- El proceso de autoridad deriva su UID/GID de ejecución localmente. Nunca confía en campos de ejecución proporcionados por el frontend.
- El frontend transmite procedencia del operador como evidencia del proceso privilegiado. El servicio registra por separado peer UID, UID/GID real de ejecución y datos de operador recibidos.

La activación por socket de systemd puede reducir el código que administra el listener, pero la modalidad exacta (`Accept=yes/no`), el transporte del descriptor y el ciclo de vida del servicio deben validarse con un prototipo mínimo. No se fijan todavía directivas de unidad ni una implementación de protocolo.

**Estado:** candidato recomendado para prototipo, no mecanismo aprobado. Requiere pruebas adversariales antes de producción.

### 3.2 Alternativas no seleccionadas

| Alternativa | Riesgo/limitación | Decisión |
|---|---|---|
| `setuid` / cambio manual de UID en Python | Errores de UID/GID, grupos suplementarios, capabilities, saved IDs y posibilidad de recuperar privilegios | No usar como atajo |
| `setpriv` o wrapper shell | Riesgo de quoting, entorno heredado, rutas sustituibles y expansión de superficie | No aprobar sin un diseño distinto y pruebas |
| `systemd-run --uid=atlas-runtime` por operación | Puede convertirse en ejecutor genérico si el caller controla argv, entorno, propiedades o ejecutable; el transporte de la solicitud requiere diseño | No seleccionar todavía |
| Pipe/STDIN a un proceso hijo | El contrato aún no demuestra integridad del canal, framing, identidad del peer ni ausencia de sustitución | No aprobar por conveniencia |
| Socket Unix con credenciales del peer | API local estrecha, identidad de peer verificable por kernel; requiere controlar socket, protocolo, lifecycle y servicio | Candidato preferido para prototipo |

El hecho de que el peer sea root identifica un proceso privilegiado del host; no prueba por sí solo la identidad civil del operador. La procedencia del operador conserva las limitaciones del mecanismo sudo/TTY. La auditoría debe describirlo como UID/sesión observados, no como identidad humana verificada.

### 3.3 Protocolo mínimo

El protocolo debe ser versionado, acotado y estricto:

- Un mensaje de solicitud por conexión.
- Tamaño máximo asimétrico definido en §10: solicitud 16 KiB y respuesta 64 KiB; la propuesta inicial de 64 KiB para solicitudes queda sustituida.
- JSON UTF-8 con versión explícita, request ID UUIDv4, nombre de operación y payload específico.
- Rechazo de claves duplicadas, campos desconocidos, tipos inesperados, valores excesivos y mensajes adicionales.
- No aceptar rutas, SQL, expresiones, código ni argumentos arbitrarios.
- La respuesta contiene request ID, estado terminal/no terminal, código estable, resumen y referencia de auditoría; nunca secretos ni trazas internas completas.
- Timeout, desconexión, mensaje truncado o versión desconocida producen rechazo/resultado desconocido y nunca una segunda ejecución automática.
- El servidor valida el peer con credenciales del kernel y valida de nuevo todos los datos de dominio.

La canonicalización y el digest del request se calculan en el lado de autoridad, usando una representación versionada. No se confía en un digest enviado por el frontend.

## 4. Catálogo cerrado de operaciones

### 4.1 Diagnóstico de solo lectura

Operación: `authority.diagnose`.

Puede devolver:
- existencia y tipo del archivo esperado;
- propietario, grupo y modos observados;
- estado de permisos de los directorios de la ruta;
- versión SQLite;
- resultado de `PRAGMA integrity_check` (o `quick_check` para un diagnóstico rápido explícitamente diferenciado);
- versión actual, última versión disponible, secuencia y checksums del ledger;
- discrepancias de esquema, WAL y sidecars;
- disponibilidad del directorio de backups, sin abrir ni leer su contenido.

Restricciones:
- No crea directorios, DB, ledger ni sidecars intencionalmente.
- Abre SQLite en modo de solo lectura y activa `query_only`.
- No repara, migra, hace checkpoint ni borra archivos.
- Un error o una comprobación incompleta se presenta como `UNKNOWN/UNAVAILABLE`, nunca como saludable.
- El frontend no recibe datos de tablas de identidad, autenticadores, secretos ni contenido sensible que no necesite para decidir.

La implementación actual de `SQLiteDatabase.connection()` abre una conexión normal de lectura/escritura. La operación requiere una vía explícita read-only, por ejemplo una conexión URI `mode=ro` validada o una abstracción equivalente; no debe simularse la condición read-only solo por omitir sentencias de escritura.

### 4.2 Plan de migración

Operación: `authority.migrations.plan`.

- Solo lectura; calcula migraciones pendientes, versión actual, versión objetivo y checksums.
- Rechaza ledger discontinuo, checksum/nombre divergente, versión futura o historial de código incompleto.
- No inicializa SQLite ni crea `schema_migrations`.
- Devuelve un plan determinista que el frontend presenta antes de pedir confirmación.
- Un plan es informativo: el servicio debe volver a validar todas las condiciones al ejecutar.

### 4.3 Inicialización explícita

Operación: `authority.initialize`.

Debe estar separada de una actualización ordinaria. Solo se admite cuando:
- el path configurado es el path canónico de despliegue, no un argumento del operador;
- el archivo aún no existe;
- el directorio padre existe, es privado y pertenece a `atlas-runtime`;
- no existe un archivo, symlink, socket o directorio en el destino;
- el operador confirma el nombre de la base y el hecho de que se creará una base nueva.

La creación debe ser exclusiva y no seguir symlinks (`O_CREAT|O_EXCL|O_NOFOLLOW` cuando aplique), con modo inicial privado. Luego el proceso `atlas-runtime` abre la base y ejecuta el bootstrap de esquema de forma transaccional. Cualquier fallo deja el resultado en estado diagnosticable; no se borra automáticamente un archivo cuya escritura pueda haber sido parcial o ambigua.

No debe utilizarse `SQLiteDatabase.apply_migrations()` sin una guarda de inicialización: actualmente llama a `initialize()`, que puede crear el archivo y el ledger de migraciones. La futura herramienta debe distinguir de forma explícita bootstrap de una base nueva frente a migración de una base existente.

### 4.4 Aplicación de migraciones

Operación: `authority.migrations.apply`.

- Solo actúa sobre la ruta canónica configurada.
- Requiere base existente, archivo regular, no symlink, propiedad/modos esperados y directorios privados.
- El frontend presenta versión actual y destino; exige motivo y confirmación tipada que incluya ambos valores.
- El servicio vuelve a validar ledger, secuencia, checksums, versión objetivo y precondiciones dentro de la transacción.
- No permite downgrade, saltar versiones, migración parcial elegida por el usuario ni SQL manual.
- No aplica migraciones al iniciar el runtime.
- Cualquier discrepancia bloquea la operación antes de escribir.
- El commit y el registro durable de la operación administrativa deben pertenecer a la misma transacción.

La API actual `SQLiteDatabase.apply_migrations()` verifica historial/checksums, pero llama primero a `initialize()`. La futura operación administrativa necesita una capa explícita que impida crear accidentalmente una DB en el modo de actualización y que incorpore el evento de auditoría al mismo commit.

### 4.5 Provisioning de asociación

Operación: `authority.project_environment.provision`.

Payload limitado a:
- operation ID UUIDv4;
- Project ID;
- Environment ID;
- motivo normalizado obligatorio (1–500 caracteres).

El frontend solicita confirmación exacta de ambos IDs y motivo. No abre SQLite para preconsultar Project, Environment o asociaciones. El servicio valida en una única transacción:
- historial de migraciones completo y checksum exacto hasta la versión que contiene el ledger de provisioning;
- Project y Environment canónicos existentes;
- ausencia de asociación previa;
- idempotencia exacta del operation ID;
- inserción de asociación ACTIVE/revision 1 y evento inmutable correspondiente.

El writer existente `SQLiteProjectEnvironmentAssociationProvisioningWriter` contiene la mutación de dominio y el evento V27, pero el CLI actual ejecuta la lectura y escritura desde el proceso EUID 0. La adaptación debe reutilizar la semántica de dominio, no la frontera de privilegios antigua.

### 4.6 Operaciones expresamente excluidas

No se incluyen en el primer catálogo:
- SQL arbitrario, shell o ejecución de Python;
- cambio de propietario/permisos/ruta de DB;
- migración downgrade o reparación automática;
- borrado, compactación o sustitución de DB;
- backup/restore;
- rotación/recuperación de claves;
- creación de USER, AGENT, Platform Admin, Grant o credenciales;
- suspensión/reactivación de asociaciones (lifecycle distinto de provisioning);
- comandos genéricos de filesystem.

## 5. Auditoría, idempotencia y resultados ambiguos

### 5.1 Separación de identidades

Cada mutación debe distinguir al menos:
- operador observado: UID real, UID efectivo del frontend, TTY/sesión y timestamp de autorización;
- ejecutor: UID/GID efectivos observados dentro del servicio (deben corresponder a `atlas-runtime`);
- peer del IPC: UID/GID/PID obtenidos mediante credenciales del kernel;
- operación: UUID, tipo, alcance, motivo y digest canónico;
- resultado: committed, rejected, not committed o unknown;
- evidencia: referencia al evento de dominio y/o ledger administrativo.

No se acepta un campo `executor_uid` suministrado por el frontend. El servicio lo deriva de su propio proceso. El servicio no eleva la procedencia de sudo a identidad Atlas USER ni a prueba de identidad civil.

### 5.2 Ledger administrativo

Se propone añadir una migración versionada (siguiente versión disponible al implementar) que cree un ledger append-only de operaciones administrativas con:
- event ID y operation ID;
- tipo de operación y versión del protocolo;
- digest de solicitud canónica;
- operador observado y metadatos de sesión;
- peer UID/GID;
- executor UID/GID;
- alcance y motivo;
- timestamps UTC de recepción y decisión;
- resultado y referencia al evento de dominio/migración.

Triggers deben impedir UPDATE/DELETE ordinarios. El evento de provisioning V27 continúa siendo el evento de dominio específico; el ledger general lo correlaciona sin reemplazarlo.

Para migraciones, el evento de éxito se inserta en la misma transacción que aplica el lote y actualiza el ledger de esquema. En el bootstrap inicial, la migración que crea el ledger administrativo y el evento de bootstrap deben quedar en el mismo commit. Si la transacción falla antes de que exista el ledger, el fallo se registra en journald y el servicio devuelve resultado no confirmado; no se afirma que el ledger interno cubra fallos anteriores a su propia creación.

Las consultas de diagnóstico de solo lectura no escriben el ledger SQLite; pueden emitir un registro operacional a journald, sin presentarlo como evidencia transaccional.

### 5.3 Idempotencia y commit ambiguo

- Toda mutación recibe operation ID UUIDv4 y digest de intención.
- Repetición del mismo ID y digest devuelve el resultado original.
- Mismo ID con digest diferente es conflicto y no muta.
- Un error durante/después de commit no se traduce automáticamente en fracaso.
- El servicio reabre la DB y consulta el ledger por operation ID.
- Coincidencia exacta y estado durable coherente: `COMMITTED_EXACT`.
- Ausencia demostrable y estado previo intacto: `NOT_COMMITTED`.
- Discrepancia, corrupción, DB inaccesible o imposibilidad de demostrar ausencia: `UNKNOWN`; bloquear reintentos con un ID nuevo y requerir diagnóstico.

## 6. Requisitos de seguridad del servicio y del frontend

### Frontend privilegiado

- Artefacto y configuración instalados en rutas root-owned no modificables por usuarios ordinarios.
- Lista cerrada de comandos y payloads; nunca proxy de argv, shell, SQL o rutas.
- UID real debe corresponder con la invocación sudo esperada; EUID 0; TTY/foreground para initialize, migrations.apply y provisioning.
- Confirmación tipada con base, alcance y transición exactos.
- Motivo obligatorio para mutaciones.
- No abrir SQLite, no hacer stat/read de la DB para tomar decisiones de dominio y no recibir descriptores SQLite.
- No dejar temporales con solicitudes sensibles ni heredar descriptores no necesarios.
- No afirmar éxito hasta recibir resultado terminal verificable.

### Servicio `atlas-runtime`

- UID/GID de servicio esperado comprobado al iniciar; no root.
- `NoNewPrivileges=yes`, sin capabilities, `UMask=0077`, `ProtectSystem=strict`, `ProtectHome=yes`, `PrivateTmp=yes`.
- Escritura solo en el directorio de autoridad; red no permitida; familia de sockets limitada a AF_UNIX.
- Rechazar peer UID no autorizado, protocolo/versiones desconocidos, campos extra, solicitudes excesivas y operaciones fuera de allowlist.
- Una sola instancia SQLiteDatabase y UoW compartida para cada transacción.
- No ejecutar plugins, skills, modelos, subprocesses arbitrarios ni código cargado dinámicamente.
- No exponer SQL, writer genérico ni filesystem.
- No confiar en el frontend para validar invariantes, esquema, scope o idempotencia.

## 7. Modelo de amenazas y pruebas adversariales obligatorias

El prototipo del canal debe demostrar:

1. Un usuario ordinario no puede conectar al socket ni suplantar peer credentials.
2. Un proceso con UID incorrecto es rechazado incluso si envía JSON válido.
3. Un campo JSON `executor_uid=0` no cambia la identidad registrada por el servicio.
4. No se puede enviar ruta alternativa, SQL, comando, nombre de módulo, entorno o argumentos adicionales.
5. Mensajes duplicados, truncados, demasiado grandes, malformados o con claves JSON duplicadas se rechazan sin mutación.
6. El frontend no puede abrir la DB ni heredar una conexión/descriptor SQLite.
7. El servicio no tiene EUID/EGID/saved IDs 0 ni capabilities; no puede recuperar privilegios.
8. Un path sustituido por symlink, archivo especial o directorio se rechaza; se prueban carreras dentro del modelo de permisos.
9. Cambio del archivo de configuración o ejecutable por usuario ordinario es imposible según ownership/modos.
10. Desconexión antes/durante/después del commit produce resultado recuperable por operation ID, sin duplicación.
11. Dos solicitudes concurrentes con mismo ID producen una sola operación; mismo ID con payload distinto produce conflicto.
12. La migración con checksum alterado, ledger discontinuo o versión futura falla cerrada.
13. El modo plan y diagnóstico no crean archivo, ledger, WAL/SHM ni modifican timestamps/esquema.
14. Migraciones y provisioning se ejecutan con `atlas-runtime` y el evento de auditoría queda atómico con el cambio.
15. Ninguna prueba apunta a las DBs experimentales existentes ni ejecuta provisioning real.

La suite debe usar directorios temporales, usuarios/UIDs de fixture cuando sea posible, sockets locales reales y procesos separados. Las pruebas de credenciales y permisos que requieren Linux deben ejecutarse en Debian por el propietario. No se afirmará cobertura adversarial por tests unitarios puros.

## 8. Secuencia de implementación propuesta

| Subfase | Entregable | Criterio de salida |
|---|---|---|
| 2.5.1 | Contrato y catálogo administrativo | Diseño revisado, operaciones y límites cerrados |
| 2.5.2 | Prototipo aislado del canal Unix | Peer credentials, framing, allowlist y pruebas adversariales; sin DB real |
| 2.5.3 | Servicio administrativo y frontend de diagnóstico/plan | Diagnóstico read-only y plan de migración sin mutaciones |
| 2.5.4 | Migrator/bootstrap explícito | Inicialización y migraciones en DB temporal, ledger atómico, checksums y reintentos |
| 2.5.5 | Provisioning adaptado | Reutiliza writer de dominio bajo atlas-runtime; frontend no abre DB |
| 2.5.6 | Validación Debian y revisión de seguridad | Suite focalizada/completa y pruebas de procesos/permisos reportadas por el propietario |

No se debe avanzar directamente de 2.5.1 a una operación privilegiada real. Cada subfase necesita revisión y evidencia propia. No se integra una mutación de host ni se despliega servicio durante esta fase.

## 9. Decisiones que siguen abiertas

- Confirmar el socket Unix como transporte después de prototipo adversarial.
- Definir la integración exacta con systemd (socket activation, ciclo de vida, hardening y límites de recursos).
- Definir el artefacto instalado del frontend y su relación con la cuenta administrativa humana.
- Definir el esquema final del ledger administrativo y su versión de migración.
- Definir si diagnóstico completo ejecuta `integrity_check` en cada llamada o separa diagnóstico rápido y profundo.
- Definir límites de concurrencia, timeouts y política de disponibilidad del servicio.
- Resolver auditoría externa, backup/restore, claves y anti-rollback en sus fases correspondientes.

**Conclusión:** el socket Unix estrecho es el candidato más prometedor para separar el frontend root del writer `atlas-runtime`, pero no se considera aprobado ni seguro hasta demostrarlo con un prototipo real y pruebas adversariales. El CLI actual permanece bloqueado para la futura DB principal.


## 10. Contrato de transporte y mensajes — v0.1

Este apartado concreta §3.3 a partir de las pruebas aisladas realizadas en Debian 13.7 / kernel 6.12.117 / systemd 257.13 / Python 3.13.5 el 18-11-2026. Es un contrato de diseño para el siguiente prototipo; no convierte el fixture en implementación aprobada ni autoriza despliegue.

### 10.1 Transporte y ciclo de conexión

- Familia: `AF_UNIX`.
- Tipo: `SOCK_SEQPACKET`; cada paquete conserva sus límites. No se añade un encabezado de longitud.
- Listener: administrado por systemd mediante socket activation, con `Accept=no` como candidato del prototipo.
- Una solicitud y una respuesta como máximo por conexión.
- El servidor acepta una conexión, procesa como máximo un paquete y cierra esa conexión. No se admite una sesión persistente ni se procesa un segundo paquete como otra operación.
- El cliente debe abrir una conexión nueva para cada solicitud.
- No se admite tráfico TCP, sockets de red ni fallback silencioso a `SOCK_STREAM`.
- El listener debe aplicar backpressure y un límite explícito de concurrencia/cola. Para el primer prototipo se prefiere ejecución serial de una solicitud activa; el valor de backlog y la semántica de reactivación de systemd deben probarse y fijarse antes de implementar.
- El descriptor heredado se valida antes de atender clientes: `LISTEN_PID`, `LISTEN_FDS`, FD esperado, familia, tipo y nombre del socket.
- El servicio no hace `bind`, `unlink`, `chmod` ni `shutdown` sobre el listener heredado.

### 10.2 Identidad del peer

- El servidor obtiene PID, UID y GID mediante `SO_PEERCRED`; nunca acepta credenciales declaradas en el JSON.
- En el prototipo inicial, el peer permitido es UID 0. El rechazo del peer se realiza antes de leer o interpretar su solicitud.
- Los permisos del directorio/socket y `SO_PEERCRED` son controles diferentes: se prueban por separado. El directorio privado root-owned y el socket restringido no se relajan para hacer pasar pruebas de credenciales.
- UID 0 identifica un proceso privilegiado del host; no prueba identidad civil ni identidad Atlas USER.
- El ejecutor de operaciones sigue siendo `atlas-runtime`; su UID/GID se observa dentro del servicio y nunca se acepta desde un campo del cliente.

### 10.3 Límites de mensajes

| Límite | Valor v0.1 | Regla |
|---|---:|---|
| Solicitud | 16 KiB | Rechazar si el paquete excede el límite |
| Respuesta | 64 KiB | Respuestas mayores requieren resumen/paginación, no truncamiento |
| Profundidad JSON | 16 niveles | Rechazar estructuras más profundas |
| Solicitudes por conexión | 1 | Cerrar después de la respuesta o rechazo |
| Tiempo de lectura de solicitud | 5 s por defecto | Límite superior configurable de 60 s |
| Tiempo de escritura | 5 s por defecto | Límite superior configurable de 60 s |

Los límites son límites de protocolo, no sustituyen los límites de CPU, memoria, descriptores, concurrencia ni tiempo de cada caso de uso. Cada operación de larga duración necesita además un deadline de ejecución explícito.

El servidor recibe con `recvmsg()` y debe comprobar:

- `MSG_TRUNC`: el paquete excedió el buffer/límite; rechazar sin ejecutar.
- `MSG_CTRUNC`: los datos ancillary quedaron truncados; rechazar.
- Cualquier dato ancillary/control message: rechazado. No se pasan descriptores de archivo ni credenciales adicionales mediante ancillary data.
- Un paquete vacío no se interpreta como una solicitud JSON válida.

No basta con `recv(1024)`: puede devolver un prefijo truncado sin que la aplicación compruebe el tamaño original. El servidor no debe intentar interpretar ni ejecutar ese prefijo.

La distinción entre un paquete de longitud cero y EOF del peer debe verificarse con `recvmsg()` y las banderas observadas en los kernels soportados. Si la plataforma no permite distinguirlos de forma fiable, ambos se tratan como cierre de transporte sin operación y sin respuesta; nunca se intenta escribir a un peer ya desconectado.

### 10.4 Solicitud JSON

Codificación UTF-8 estricta, un objeto JSON por paquete:

```json
{
  "protocol": "atlas-admin/1",
  "request_id": "UUIDv4",
  "operation": "authority.diagnose",
  "payload": {}
}
```

Reglas normativas:

- `protocol`, `request_id`, `operation` y `payload` son obligatorios.
- `request_id` identifica el intercambio de transporte; cada intento nuevo obtiene un UUIDv4 nuevo.
- `operation` pertenece al catálogo cerrado de §11.
- `payload` es un objeto con esquema específico de la operación.
- Rechazar UTF-8 inválido, JSON inválido, claves duplicadas, campos desconocidos, tipos incorrectos, valores fuera de rango, profundidad excesiva, `NaN`, `Infinity` y cualquier representación no admitida por JSON estricto.
- No se permiten rutas de base, SQL, shell, ejecutables, nombres de módulos, expresiones, código, variables de entorno ni argumentos genéricos.
- El digest de intención se calcula en el servicio sobre una representación normalizada y versionada del payload. El cliente no puede imponer el digest ni sustituir la canonicalización.
- Las mutaciones incluyen además un `operation_id` UUIDv4 distinto de `request_id`; este identificador es la clave durable de idempotencia.

Para operaciones mutables, `payload` incluye la evidencia de procedencia del operador, motivo y confirmación tipada exigidos por §4 y §6. Esa evidencia se registra como procedencia transmitida por el frontend privilegiado; no se presenta como una identidad civil verificada por el servicio. El servicio registra por separado las credenciales del peer y su propia identidad de ejecución. Se rechaza cualquier campo `executor_uid` o equivalente enviado por el cliente.

### 10.5 Respuesta

Respuesta satisfactoria:

```json
{
  "protocol": "atlas-admin/1",
  "request_id": "UUIDv4",
  "status": "completed",
  "code": "OK",
  "summary": "Operation completed",
  "result": {},
  "audit_ref": "reference-or-null"
}
```

Respuesta de rechazo/error:

```json
{
  "protocol": "atlas-admin/1",
  "request_id": "UUIDv4-or-null",
  "status": "rejected",
  "code": "INVALID_REQUEST",
  "summary": "Request rejected",
  "result": {},
  "audit_ref": null
}
```

Estados de respuesta permitidos:

- `completed`: resultado terminal confirmado.
- `rejected`: solicitud rechazada sin ejecutar la mutación.
- `pending`: operación aceptada pero todavía no terminal; solo se permite para operaciones que definan explícitamente este estado.
- `unknown`: el servicio no puede demostrar si una mutación llegó a commit; requiere resolución por `operation_id`.

Las respuestas no incluyen stack traces, rutas internas, SQL, secretos ni datos de tablas que el frontend no necesite. Si no puede recuperarse de forma segura el `request_id` de una solicitud malformada, se devuelve `null`. Para peer no autorizado, paquete truncado o ancillary data prohibido, el servicio puede cerrar sin respuesta; nunca debe ejecutar la operación.

### 10.6 Errores estables

Los códigos forman parte del contrato y no deben depender de mensajes de excepción del lenguaje:

| Código | Significado |
|---|---|
| `UNAUTHORIZED_PEER` | UID del peer no permitido |
| `EMPTY_REQUEST` | Paquete vacío cuando puede distinguirse de EOF |
| `REQUEST_TOO_LARGE` | Solicitud supera 16 KiB |
| `MESSAGE_TRUNCATED` | `MSG_TRUNC` detectado |
| `ANCILLARY_DATA_FORBIDDEN` | Datos ancillary o `MSG_CTRUNC` |
| `INVALID_UTF8` | Codificación no válida |
| `INVALID_JSON` | JSON malformado o no estricto |
| `INVALID_REQUEST` | Sobre de solicitud incompleto o campos no admitidos |
| `UNSUPPORTED_PROTOCOL_VERSION` | Versión no admitida |
| `UNKNOWN_OPERATION` | Operación fuera del catálogo |
| `INVALID_ARGUMENTS` | Payload no cumple el esquema |
| `OPERATION_DENIED` | Operación no autorizada por sus precondiciones |
| `IDEMPOTENCY_CONFLICT` | Mismo operation ID con intención diferente |
| `TIMEOUT` | Deadline de transporte/operación agotado |
| `OPERATION_FAILED` | Fallo controlado del caso de uso |
| `RESULT_UNKNOWN` | No se puede demostrar el resultado durable |
| `INTERNAL_ERROR` | Fallo interno no recuperable, sin detalles sensibles |

Una entrada inválida no debe provocar una excepción no controlada ni terminar el proceso de autoridad por un error de validación. `BrokenPipeError`/peer desaparecido es un resultado de transporte: no debe causar una caída inesperada ni convertir una mutación potencialmente confirmada en un falso `failed`.

## 11. Catálogo de operaciones v0.1 y matriz de autorización

Todas las operaciones requieren un peer local autorizado por `SO_PEERCRED` (UID 0 en el prototipo) y pasan por una allowlist exacta. Esta condición solo autentica el proceso del host; no reemplaza las precondiciones específicas de cada operación.

| Operación | Acceso a DB | Mutación | TTY/confirmación | Motivo | Idempotencia |
|---|---|---:|---|---|---|
| `authority.ping` | Ninguno | No | No | No | `request_id` |
| `authority.diagnose` | Solo lectura | No | No | No | `request_id` |
| `authority.migrations.plan` | Solo lectura | No | No | No | `request_id` |
| `authority.operation.status` | Lectura del ledger | No | No | No | `operation_id` consultado |
| `authority.initialize` | Crea/bootstrap | Sí | TTY foreground y confirmación tipada | Obligatorio | `operation_id` |
| `authority.migrations.apply` | Escritura transaccional | Sí | TTY foreground y confirmación exacta origen→destino | Obligatorio | `operation_id` |
| `authority.project_environment.provision` | Escritura transaccional | Sí | TTY foreground y confirmación exacta Project/Environment | Obligatorio | `operation_id` |

### 11.1 `authority.ping`

- Comprueba que el servicio atiende el protocolo y devuelve su versión.
- No abre SQLite, no inspecciona rutas de DB y no cambia estado.
- No debe exponer configuración, secretos ni inventario sensible.
- Es una operación de salud del canal, no una prueba de que la autoridad de dominio esté saludable.

### 11.2 `authority.diagnose`

Conserva las restricciones de §4.1. Solo el servicio puede inspeccionar el almacenamiento configurado. El frontend no abre SQLite ni toma decisiones a partir de lecturas propias. Diagnóstico rápido y profundo deben distinguirse en el resultado; una comprobación no ejecutada o incompleta es `UNKNOWN/UNAVAILABLE`, nunca saludable.

### 11.3 `authority.migrations.plan`

Conserva §4.2. Devuelve un plan determinista y de solo lectura. No crea DB, ledger, directorios, WAL ni sidecars. Aplicar el plan siempre vuelve a validar estado y checksums.

### 11.4 `authority.operation.status`

Nueva operación de solo lectura necesaria para resolver commits ambiguos:

- Payload: `operation_id` UUIDv4.
- Consulta únicamente el ledger administrativo; no permite búsquedas SQL ni lecturas arbitrarias.
- Devuelve `COMMITTED_EXACT`, `NOT_COMMITTED` o `UNKNOWN`, junto con tipo de operación, digest registrado y referencia de auditoría cuando exista.
- `NOT_COMMITTED` solo se devuelve cuando el ledger autoritativo está disponible, íntegro y permite demostrar la ausencia de commit.
- Si la DB/ledger no está disponible, es inconsistente o todavía no existe (por ejemplo, bootstrap inicial incompleto), devuelve `UNKNOWN`.
- No inicia, reintenta ni repara la operación consultada.

### 11.5 `authority.initialize`

Conserva §4.3. Solo crea una base nueva en la ruta canónica configurada. Exige ausencia demostrada de cualquier objeto en destino, confirmación tipada y operation ID. El evento de bootstrap y el ledger inicial deben quedar en el mismo commit cuando técnicamente sea posible. Un resultado ambiguo nunca provoca borrado automático ni repetición con otro ID.

### 11.6 `authority.migrations.apply`

Conserva §4.4. Solo aplica migraciones publicadas e inmutables sobre una DB existente. No admite downgrade, salto de versiones, SQL manual ni selección arbitraria de archivos. El cambio de esquema y el evento administrativo correspondiente se confirman en la misma transacción.

### 11.7 `authority.project_environment.provision`

Conserva §4.5. Payload cerrado: operation ID, Project ID, Environment ID y motivo normalizado. El servicio valida y muta en una sola UoW/SQLite transaction. No crea identidades, Grants, credenciales ni recursos adyacentes.

### 11.8 Operaciones fuera de catálogo

Continúan excluidas todas las operaciones enumeradas en §4.6. Tampoco se admiten aliases, nombres alternativos, comodines, comandos compuestos, operaciones batch ni extensiones dinámicas del catálogo. Agregar una operación requiere cambio de contrato, revisión de permisos, pruebas y aprobación explícita.

## 12. Idempotencia, desconexión y auditoría de protocolo

### 12.1 Dos identificadores distintos

- `request_id`: correlaciona un intercambio IPC. Es nuevo en cada intento de transporte.
- `operation_id`: identifica una intención administrativa mutable y permanece estable durante todos sus reintentos/resoluciones.

El mismo `operation_id` y el mismo digest canónico devuelven el resultado original. El mismo ID con digest diferente produce `IDEMPOTENCY_CONFLICT` sin mutación.

### 12.2 Desconexión y resultado ambiguo

- Desconexión antes de recibir una solicitud válida: cerrar limpiamente; cero operaciones.
- Solicitud inválida, truncada o no autorizada: cero mutaciones.
- Desconexión durante el procesamiento: el servicio no asume que la transacción fue cancelada.
- Error al enviar respuesta después de una mutación: no declarar automáticamente `NOT_COMMITTED`; resolver mediante `authority.operation.status`.
- Mientras el resultado sea `UNKNOWN`, no iniciar el mismo propósito con un operation ID nuevo.
- La desconexión del cliente no debe provocar rollback ficticio, doble ejecución ni una excepción no controlada del servidor.

### 12.3 Auditoría mínima

Cada intercambio registra, con redacción de datos sensibles:

- timestamp UTC y duración;
- request ID y operation ID cuando exista;
- peer PID/UID/GID obtenidos del kernel;
- identidad real/efectiva del ejecutor observada dentro del servicio;
- operación y versión del protocolo;
- digest canónico de intención;
- decisión, código estable y resultado;
- referencia al evento transaccional/ledger cuando exista;
- desconexión o fallo de entrega de respuesta.

La procedencia del operador transmitida por el frontend se etiqueta como evidencia declarada por ese frontend. No se fusiona con peer credentials, identidad de ejecución ni identidad Atlas USER.

## 13. Evidencia de laboratorio que motiva v0.1

Las pruebas del 18-11-2026 se realizaron en una VM Debian desechable, sobre el fixture `atlas-authority-admin-lab.py`, sin modificar el repositorio ni el socket principal de Atlas:

| Prueba | Evidencia | Consecuencia de diseño |
|---|---|---|
| Paquete vacío | Recibió `invalid`; el handler lanzó RuntimeError y systemd marcó fallo | Tratar entrada vacía/EOF de forma controlada y no lanzar excepción |
| Operación desconocida | Recibió `invalid`; RuntimeError no controlado | Allowlist y error estable sin caída |
| Paquete de 2048 bytes con `recv(1024)` | El handler recibió un prefijo y respondió `invalid`; no comprobó truncamiento | `recvmsg()` + `MSG_TRUNC` obligatorio |
| Prueba aislada de `recvmsg(1024)` | 2048 bytes enviados, 1024 recibidos y `MSG_TRUNC=True` | El kernel expone la señal de truncamiento; falta integrarla y probarla en el handler |
| Dos `ping` en una conexión | Primera respuesta `pong`; segunda escritura del cliente recibió `BrokenPipeError` | Una solicitud por conexión debe ser explícita |
| Cliente cierra sin enviar paquete | El servidor intentó responder `invalid` y obtuvo `BrokenPipeError` | Desconexión no debe tratarse como solicitud inválida ni derribar el servicio |
| Recuperación posterior | Nuevo `ping` respondió `pong`; socket activo y servicio terminó `inactive` correctamente | El fallo de las pruebas negativas era del handler de fixture, no del listener |

La prueba aislada de `MSG_TRUNC` usó un par de sockets local y no demuestra todavía el comportamiento final del handler systemd. Tampoco se ha demostrado aún la distinción fiable entre paquete de longitud cero y EOF; queda como prueba obligatoria del prototipo.

El repositorio permaneció limpio (`lab/pr-27...origin/pr-27`) y el socket principal conservó su inode/permisos durante estas pruebas. La evidencia no valida el protocolo de producción ni autoriza integrar el fixture en Atlas.

## 14. Decisiones pendientes antes de implementar

1. Ejecutar pruebas específicas de `recvmsg()` para distinguir paquete vacío y EOF en Debian soportado.
2. Integrar y probar `MSG_TRUNC`, `MSG_CTRUNC` y rechazo de ancillary data en un fixture aislado.
3. Medir y fijar backlog, concurrencia máxima y backpressure del listener systemd.
4. Fijar deadlines por operación, especialmente migración/bootstrap, y comportamiento de cancelación.
5. Definir canonicalización versionada exacta para el digest de idempotencia.
6. Revisar el esquema y atomicidad del ledger administrativo, incluido bootstrap inicial.
7. Probar `authority.operation.status` ante commit, rollback, caída del proceso, pérdida de respuesta y DB inaccesible.
8. Revisar los payloads definitivos y la procedencia del operador para cada mutación.

**Criterio de salida:** no implementar operaciones mutables ni conectar este protocolo al runtime hasta cerrar estos puntos con pruebas reproducibles y revisión de seguridad. Este documento es una especificación de diseño v0.1; no aprueba despliegue, provisioning real ni cambios privilegiados en el host.


## 15. Contratos individuales de las siete operaciones

El catálogo de §11 queda **cerrado para la primera versión**. Los siete nombres siguientes son la allowlist completa de `atlas-admin/1`; no existen alias, extensiones dinámicas, operaciones batch ni una operación genérica de ejecución. Agregar o retirar una operación requiere una nueva revisión explícita del contrato.

Todos los sobres usan el formato de §10. El campo `operation` contiene exactamente uno de los siete nombres. `payload` contiene solo los campos aquí enumerados. Los ejemplos son ilustrativos y no sustituyen la validación de esquema. Campos desconocidos, duplicados o ausentes se rechazan.

### 15.1 Reglas compartidas

**Lecturas**
- No reciben `operation_id`, motivo ni confirmación de mutación.
- No cambian el estado de dominio ni crean DB, ledger, sidecars, directorios o archivos.
- Pueden emitir telemetría operacional a journald, pero no insertan eventos de mutación en el ledger SQLite.
- La lectura de SQLite, cuando corresponda, debe abrir la ruta canónica en modo read-only y activar `query_only`.

**Mutaciones**
- Las tres mutaciones requieren `operation_id` UUIDv4, `reason` de 1–500 caracteres normalizados y evidencia de procedencia del frontend privilegiado.
- La evidencia de procedencia incluye como mínimo UID real observado, UID efectivo del frontend, TTY/sesión observada, timestamp de autorización y alcance exacto confirmado. Se registra como evidencia declarada por el frontend; el servicio no la confunde con `SO_PEERCRED`, identidad de ejecución ni identidad Atlas USER.
- La confirmación tipada se verifica en el frontend privilegiado antes de enviar la solicitud. El servicio vuelve a validar alcance, estado, invariantes y digest; no confía en la confirmación visual como sustituto de las precondiciones de dominio.
- El peer IPC debe superar `SO_PEERCRED` y la allowlist. La política de UID 0 del prototipo no convierte cualquier payload root en una operación válida.
- El mismo `operation_id` y digest canónico devuelve el resultado ya registrado. El mismo ID con intención distinta devuelve `IDEMPOTENCY_CONFLICT`.
- Ninguna mutación se declara `completed` antes de demostrar el commit durable. Si no puede determinarse el resultado, devuelve `unknown/RESULT_UNKNOWN` y exige resolverlo con `authority.operation.status`.

### 15.2 `authority.ping` — disponibilidad del canal

**Payload:** objeto vacío `{}`.

**Acceso:** no abre SQLite ni inspecciona el filesystem de la base.

**Resultado `completed/OK`:**
- versión de protocolo;
- versión del servicio;
- estado de disponibilidad del handler.

No devuelve rutas, variables de entorno, configuración secreta, identidad del operador ni inventario interno. Un ping correcto solo demuestra que el canal y el handler responden; no demuestra integridad, disponibilidad o salud de SQLite.

**Efectos:** ninguno. No crea sesión ni conserva estado entre conexiones.

### 15.3 `authority.diagnose` — diagnóstico read-only

**Payload permitido:**
- `profile`: `quick` o `deep`.

No admite ruta, nombre de archivo, SQL, tabla, pragma libre ni selector de directorio. La ubicación se toma exclusivamente de configuración protegida del servicio.

**Perfil quick:** inspecciona existencia/tipo del destino, symlink, propietario/modo de directorios y archivo, accesibilidad read-only, versión SQLite y coherencia básica de versión/ledger/checksums cuando el ledger está disponible. No ejecuta una comprobación íntegra costosa.

**Perfil deep:** incluye quick y además ejecuta la comprobación de integridad SQLite definida por la implementación (`integrity_check`, o una alternativa documentada y etiquetada). El resultado debe indicar explícitamente qué comprobaciones se ejecutaron, cuáles no, su duración y estado.

**Resultado:** un objeto de comprobaciones individuales con estado `PASS`, `FAIL`, `UNKNOWN` o `NOT_APPLICABLE`, código estable y resumen seguro. Debe diferenciar DB ausente, DB inaccesible, ledger ausente, historial inconsistente, checksum divergente, archivo inesperado, permisos incorrectos y comprobación no ejecutada.

**Reglas:**
- La ausencia de DB durante el estado pre-bootstrap no equivale por sí sola a corrupción; se informa como `NOT_INITIALIZED`.
- Un diagnóstico parcial nunca se resume como saludable.
- Si la DB no existe, no se crea para diagnosticar.
- No se hace checkpoint, vacuum, repair, migrate, chmod, chown, unlink ni limpieza de WAL/SHM.
- Ningún contenido de tablas de identidad, credenciales, autenticadores o secretos se devuelve al frontend.

### 15.4 `authority.migrations.plan` — plan determinista de migración

**Payload permitido:** objeto vacío `{}`; no se acepta ruta ni selección de archivo/migración.

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

### 15.5 `authority.operation.status` — resolución de resultado durable

**Payload requerido:** `operation_id` UUIDv4. No admite filtros, SQL, paginación arbitraria ni consulta de otros registros.

**Acceso:** solo lectura del ledger administrativo canónico.

**Resultado:**
- `COMMITTED_EXACT`: existe registro durable con el mismo operation ID y digest/tipo esperado; devuelve tipo de operación, digest, timestamp y referencia de auditoría.
- `NOT_COMMITTED`: el ledger está disponible, íntegro y permite demostrar que no existe commit para ese ID; devuelve evidencia mínima de la comprobación.
- `UNKNOWN`: ledger ausente, corrupto, inaccesible, inconsistente o incapaz de demostrar presencia/ausencia.

Si existe un registro para el ID pero el caller no puede demostrar que corresponde a la misma intención, no se devuelve `COMMITTED_EXACT`; se devuelve conflicto/resultado desconocido según la evidencia disponible. Esta operación nunca inicia, reintenta, repara ni revierte la operación consultada.

### 15.6 `authority.initialize` — bootstrap único

**Payload requerido:**
- `operation_id`: UUIDv4;
- `reason`: 1–500 caracteres;
- `confirmation_phrase`: nombre canónico exacto esperado por el frontend, en formato `INITIALIZE <canonical-database-name>`;
- `operator_evidence`: evidencia descrita en §15.1.

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

**Fallos:** nunca borrar automáticamente un archivo o DB parcialmente creada. Si el proceso cae después de crear el archivo y antes de confirmar el ledger, la siguiente acción es diagnóstico y resolución; no repetir bootstrap a ciegas ni asignar un ID nuevo. La atomicidad del primer evento/ledger y la creación del archivo se debe demostrar en pruebas específicas.

### 15.7 `authority.migrations.apply` — aplicar migraciones forward-only

**Payload requerido:**
- `operation_id`: UUIDv4;
- `reason`: 1–500 caracteres;
- `expected_current_version`: versión observada por el operador;
- `target_version`: versión objetivo exacta del plan;
- `plan_digest`: digest del plan mostrado;
- `confirmation_phrase`: `MIGRATE <expected_current_version> -> <target_version>`;
- `operator_evidence`: evidencia descrita en §15.1.

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

**Efecto:** aplica únicamente todas las migraciones forward-only comprendidas entre current y target, en orden publicado. No permite selección parcial, downgrade, salto ni SQL externo. La actualización del schema ledger y el evento administrativo de éxito deben quedar en el mismo commit transaccional.

**Resultado:** versión final y lista exacta aplicada, checksums y referencia de auditoría. Si ocurre un error, la transacción debe revertirse cuando aún no hubo commit. Si el resultado del commit no puede demostrarse, devolver `unknown/RESULT_UNKNOWN`; no volver a aplicar automáticamente.

### 15.8 `authority.project_environment.provision` — asociación inicial

**Payload requerido:**
- `operation_id`: UUIDv4;
- `project_id`: ID canónico;
- `environment_id`: ID canónico;
- `reason`: 1–500 caracteres;
- `confirmation_phrase`: `PROVISION <project_id> -> <environment_id>`;
- `operator_evidence`: evidencia descrita en §15.1.

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

### 15.9 Tabla final de capacidades

| Operación | Lee filesystem | Lee SQLite | Escribe SQLite | Requiere TTY foreground | Requiere motivo |
|---|---:|---:|---:|---:|---:|
| `authority.ping` | No | No | No | No | No |
| `authority.diagnose` | Sí, ruta canónica | Sí, read-only | No | No | No |
| `authority.migrations.plan` | Sí, manifiesto/ruta canónica | Sí, read-only | No | No | No |
| `authority.operation.status` | Sí, ruta canónica | Sí, ledger read-only | No | No | No |
| `authority.initialize` | Sí, ruta canónica | Bootstrap | Sí | Sí | Sí |
| `authority.migrations.apply` | Sí, ruta/manifiesto | Sí | Sí | Sí | Sí |
| `authority.project_environment.provision` | Sí, ruta canónica | Sí | Sí | Sí | Sí |

La tabla describe el comportamiento lógico esperado; no concede al frontend acceso directo al filesystem/SQLite. Todas las lecturas y escrituras de autoridad se ejecutan dentro del servicio bajo la identidad de servicio.

## 16. Secuencia de cierre del catálogo

El catálogo está aceptado como conjunto cerrado, pero sus contratos solo se consideran implementables cuando pasen revisiones y pruebas específicas. La secuencia de trabajo es:

1. **Canal y errores:** probar framing, peer credentials, límites, ancillary data, EOF y desconexiones en fixture aislado.
2. **Lecturas sin mutación:** cerrar `ping`, `diagnose`, `migrations.plan` y `operation.status`; demostrar ausencia de efectos laterales.
3. **Ledger e idempotencia:** validar esquema, atomicidad, digest canónico y resolución de commit ambiguo.
4. **Mutaciones:** diseñar y probar bootstrap, migraciones y provisioning en fixtures desechables, nunca en la futura DB real.
5. **Revisión de seguridad:** comprobar allowlist, permisos, identidad del writer, auditoría y recuperación antes de conectar cualquier frontend.

El catálogo de siete operaciones no se amplía durante estas etapas. Las decisiones pendientes de §14 y los criterios de aceptación de este documento siguen vigentes.
