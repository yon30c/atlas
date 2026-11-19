# Diseño de operaciones administrativas de autoridad local

**Estado:** propuesta de diseño para revisión; no autoriza implementación privilegiada ni operaciones sobre una base real.  
**Fecha:** 18 de noviembre de 2026.  
**Fase:** 2.5 — operaciones administrativas de autoridad.  
**Base de código:** `main` después de `5deb6bf1cf1a53a1eb905d5c23e61f4f027c5fee`.

Este diseño desarrolla la frontera establecida en [el contrato operativo de almacenamiento de autoridad local](local-authority-storage-operational-contract.md). Para el transporte IPC, envelope, límites, estados y catálogo, prevalece el [Contrato normativo IPC administrativo atlas-admin/1](../contracts/local-authority-admin-ipc-atlas-admin-1.md). Este documento desarrolla el diseño de dominio y las propuestas de operación; no es la fuente normativa del protocolo ni una especificación IPC individual completa. La base primaria aún no está desplegada. El CLI de provisioning existente no es apto para ella y no debe ejecutarse contra esa futura base.

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
- Tamaño máximo según el contrato normativo `atlas-admin/1`: request 16 KiB y response 64 KiB. La propuesta inicial de request de 64 KiB queda sustituida.
- JSON UTF-8 con versión explícita, request ID UUIDv4, nombre de operación y payload específico.
- Rechazo de claves duplicadas, campos desconocidos, tipos inesperados, valores excesivos y mensajes adicionales.
- No aceptar rutas, SQL, expresiones, código ni argumentos arbitrarios.
- La respuesta contiene request ID, estado terminal/no terminal, código estable, resumen y referencia de auditoría; nunca secretos ni trazas internas completas.
- Timeout, desconexión, mensaje truncado o versión desconocida producen rechazo/resultado desconocido y nunca una segunda ejecución automática.
- El servidor valida el peer con credenciales del kernel y valida de nuevo todos los datos de dominio.

La canonicalización y el digest del request se calculan en el lado de autoridad, usando una representación versionada. No se confía en un digest enviado por el frontend.

## 4. Catálogo de operaciones de dominio

Esta sección describe cinco operaciones de dominio y sus intenciones de diseño. No constituye el catálogo IPC completo. El catálogo normativo de `atlas-admin/1` contiene exactamente siete operaciones, incluidas `authority.ping` y `authority.operation.status`; véase el contrato normativo IPC §9. Las descripciones de esta sección no habilitan una operación ni sustituyen su payload y resultado IPC individual aprobados.

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

**Cierre documental posterior:** los esquemas exactos de resultado por operación y la tabla estable de códigos/estados se encuentran en el contrato normativo IPC §§9.12 y 10.4. Este diseño permanece subordinado y no debe redefinirlos ni ampliar el catálogo. El cierre de contrato no habilita las operaciones.


- Toda mutación recibe operation ID UUIDv4 y digest de intención. Para `atlas-admin/1`, la proyección exacta y su canonicalización JSON v1/SHA-256 están fijadas normativamente en el contrato IPC §9.11.6; el digest del plan de migraciones es otro digest y se define por separado en §9.11.5.
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
