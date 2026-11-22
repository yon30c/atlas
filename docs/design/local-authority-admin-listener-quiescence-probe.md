# Diseño del probe de quiescencia del listener — A-IPC-05 / QP-01..QP-15

**Identificador:** ATLAS-PROBE-LISTENER-QUIESCENCE  
**Versión:** 1.0-draft  
**Estado:** diseño aprobado; runner inicial implementado parcialmente en `tests/integration/private_unix_listener/run_listener_quiescence_probe.py`; no ejecutado. QP-03/QP-04/QP-06/QP-07/QP-12 tienen estímulos y oráculos iniciales; QP-01/QP-02 solo validan lifecycle y permanecen INCOMPLETE por falta de evidencia FD.  
**Fecha de actualización:** 22 de noviembre de 2026.  
**Contrato base:** `docs/contracts/local-authority-admin-listener-quiescence-1.md`, versión 1.0-draft, recomendaciones R1–R7 aprobadas expresamente por el propietario.  
**Rama:** `experiment/a-ipc-01-private-unix-listener-probe`  
**Entorno futuro:** únicamente VM desechable `Atlas-VM-test`; nunca `greed` producción.

## 1. Objetivo

Definir una prueba experimental aislada que compruebe si una instancia de servicio que crea y posee su propio listener AF_UNIX/SOCK_SEQPACKET puede declararse quiescente únicamente después de detenerse completamente y demostrar que su cgroup exclusivo está vacío, mientras una puerta de mantenimiento impide un arranque concurrente.

El probe valida las condiciones de lifecycle y la evidencia exigida por listener-quiescence/1. No implementa una utilidad de mantenimiento ni una recuperación de pathname. Su salida no autoriza `unlink`, cleanup real, listener persistente Atlas, integración productiva, acceso a SQLite ni despliegue.

## 2. Decisiones de alcance

### 2.1 Baseline aprobado

El propietario aprobó R1–R7 del contrato base. El probe se diseña, por tanto, exclusivamente para:

- listener creado por el proceso fixture del servicio mediante `socket()`, `bind()` y `listen()`;
- unidad service dedicada, cgroup propio y no delegado;
- parada de todo el grupo, con `KillMode=control-group` como candidato que debe observarse y validarse;
- declaración conjunta de unidad `inactive`, ausencia de transición/jobs start/restart y `cgroup.events` con `populated 0`;
- puerta root-managed que excluye start/restart concurrente durante la observación;
- política de no fork después de crear el listener y no herencia/duplicación/transferencia/retención externa del FD;
- exclusión de systemd socket activation.

La aprobación de estas recomendaciones es aprobación del baseline de diseño. No equivale a autorización para crear ahora unidades, cgroups, cuentas, rutas o servicios, implementar el runner, ejecutar pruebas, ni cambiar el host.

### 2.2 Entorno y aislamiento futuro

La futura ejecución debe realizarse como root únicamente dentro de una VM desechable dedicada. El runner podrá crear recursos **transitorios y de nombre aleatorio** bajo un sandbox privado de `/run` y unidades transitorias del system manager de esa VM, si el diseño final confirma que son necesarias. No instalará unidades persistentes ni escribirá en `/etc/systemd/system`, `/etc/atlas` o rutas persistentes.

El fixture debe usar un nombre de unidad exclusivo por ejecución y cgroup generado por systemd; nunca reutilizar una unidad preexistente. Antes de iniciar, comprobar que el nombre elegido no existe. Si hay colisión, abortar sin detener, modificar ni inspeccionar destructivamente la unidad encontrada.

No crear usuarios ni grupos del sistema. El probe usará identidades fixture ya preparadas en la VM o la identidad temporal explícitamente definida en una revisión futura; cualquier precondición no satisfecha produce INCOMPLETE, no una modificación automática del host.

### 2.3 Límites absolutos

- No operar sobre el listener, pathname, unidad, cgroup o proceso de Atlas real.
- No consultar ni detener servicios ajenos al fixture.
- No crear unidades persistentes, habilitar servicios, cambiar configuración global de systemd/cgroup, modificar usuarios, grupos, permisos o políticas del host.
- No usar `systemd-run`/D-Bus contra el host de producción; toda interacción futura se limita a la VM desechable.
- No conectar al listener para inferir liveness; no aceptar ni intercambiar payloads.
- Durante la observación de quiescencia y cualquier decisión sobre stale recovery está prohibido ejecutar `unlink`, `unlinkat` o `rm` sobre el endpoint. Al terminar el probe, se permite retirar exclusivamente el socket fixture creado por esa ejecución como cleanup separado: todos los FDs deben estar cerrados, y `fstatat(AT_SYMLINK_NOFOLLOW)` debe confirmar tipo socket y la misma pareja `st_dev/st_ino` capturada al crearlo; la retirada se hace con `unlinkat` relativo a un `dirfd` anclado al sandbox verificado. Nunca se retira un pathname preexistente, sustituido o ajeno. Si la identidad no coincide, se conserva y el cleanup queda INCOMPLETE.
- No considerar un PASS como autorización de recuperación, ni como prueba host-wide frente a root o procesos fuera del modelo TCB-1.

## 3. Arquitectura del harness propuesta

El diseño separa cuatro roles:

1. **Orquestador root del probe:** crea el sandbox, adquiere/libera la puerta exclusiva, solicita acciones al system manager y captura evidencia. No posee ni recibe el listener FD.
2. **Servicio fixture:** proceso mínimo lanzado por la unidad transitoria. Crea el listener dentro de su cgroup, verifica sus invariantes de FD y permanece vivo hasta recibir una señal/orden fixture de shutdown. No implementa protocolo administrativo Atlas.
3. **Controlador externo fixture:** coordina acciones de prueba (por ejemplo, mantener un hijo vivo en QP-02) sin recibir el listener FD. Cualquier proceso auxiliar de servicio debe permanecer en el cgroup de la unidad.
4. **Recolector de evidencia:** obtiene estado de unidad, jobs, invocation ID, ControlGroup, propiedades de delegación/kill mode y `cgroup.events`; registra snapshots correlacionados con reloj monotónico.

El canal de control fixture debe ser distinto del listener bajo prueba y no transportar descriptores. Se recomienda un pipe/socketpair privado creado antes del bind; el listener no se comparte por ese canal. El recolector no debe inferir la identidad de la unidad a partir de stdout del servicio: consulta el manager confiable y contrasta el resultado con la unidad aleatoria esperada.

### 3.1 Requisitos del servicio fixture

- Crea un único socket AF_UNIX/SOCK_SEQPACKET bajo el sandbox privado.
- Establece `FD_CLOEXEC` al crear el descriptor o inmediatamente después, antes de cualquier posible exec.
- No hace fork después de bind/listen; tras crear el listener instala un filtro seccomp que devuelve `EPERM` para `fork`, `vfork`, `clone` y `clone3`.
- El mismo filtro deniega `sendmsg`, `recvmsg`, `sendmmsg` y `recvmmsg` después de crear el listener; el canal de control usa únicamente `read`/`write` y mensajes de longitud fija, sin ancillary data.
- No llama a `dup`/`dup2`/`fcntl(F_DUPFD*)` para replicar el listener. El filtro seccomp no pretende proteger frente a root/capacidades equivalentes ni frente a mecanismos externos fuera de TCB-1.
- No registra el listener en un supervisor externo ni lo publica en el canal de control.
- Mantiene un registro local de PID, FD, `fstat`, `getsockname`, `SO_TYPE`, `SO_ACCEPTCONN` y `FD_CLOEXEC` solo para la evidencia del fixture. Estos datos no sustituyen la evidencia del system manager/cgroup.
- Cierra el listener durante shutdown normal. El runner no mata ni cierra FDs del proceso mediante procfs como mecanismo de prueba.

### 3.2 Puerta de mantenimiento

La puerta será un protocolo root-managed de dos piezas: un `flock(LOCK_EX|LOCK_NB)` sobre un archivo de lock permanente en un directorio privado root:root 0700 de `/run`, y un marcador sticky de mantenimiento creado con `O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC`, modo 0600, que contiene `run_id`, unidad y fase. El lock serializa actores vivos; el marcador permanece si el orquestador cae y hace que el supervisor rechace nuevos start/restart hasta recuperación manual auditada. El marcador solo se retira después de persistir el resultado final y completar cleanup seguro. La puerta debe demostrar:

- exclusión entre dos orquestadores;
- bloqueo de start/restart a través del único punto autorizado de lifecycle;
- rechazo de solicitudes concurrentes y expiración/timeout fail-closed;
- liberación inequívoca al finalizar y retención fail-closed del marcador ante caída del orquestador;
- el segundo actor autorizado usa el mismo supervisor/lock y no llama directamente a systemd;
- la unidad fixture tiene `Restart=no`, no está habilitada y no tiene timers, paths, sockets, dependencias activadoras ni triggers externos.

**Límite de autoridad:** ningún lock de archivo puede impedir que un administrador root llame directamente a PID 1 por D-Bus o `systemctl`. Root pertenece al dominio de confianza del contrato. La puerta serializa todos los actores autorizados y automatizaciones declaradas; no es una defensa contra root malicioso ni demuestra que un host de producción carezca de vías de arranque no declaradas.

Si timers, dependencias, triggers o políticas automáticas pueden iniciar la unidad sin pasar por la puerta, QP-11 no puede pasar. Una llamada directa de root a PID 1 se considera una acción del dominio de autoridad confiable y queda fuera de la protección de la puerta; QP-12 comprueba que la sustitución resultante se detecta.

## 4. Secuencia común de observación

Cada escenario que aspire a declarar quiescencia debe seguir una secuencia equivalente, con timestamps monotónicos:

1. Generar un identificador de ejecución y nombres aleatorios para sandbox/unidad; validar que no existen.
2. Crear el sandbox privado y registrar su identidad de filesystem.
3. Adquirir la puerta de mantenimiento; registrar propietario lógico, resultado y tiempo de adquisición.
4. Iniciar la unidad fixture; consultar al manager y registrar nombre exacto, `InvocationID`, `ControlGroup`, `KillMode`, `Delegate`, `ActiveState`, `SubState` y jobs relevantes.
5. Esperar señal explícita de readiness emitida después de bind/listen y de registrar la identidad del socket fixture. La señal no prueba quiescencia.
6. Solicitar stop mediante el supervisor designado.
7. Esperar hasta un deadline monotónico acotado. Timeout, error del manager o pérdida de comunicación produce ABORT.
8. Verificar que la unidad exacta está `inactive`, no está en transición y no tiene jobs start/restart pendientes.
9. Confirmar que InvocationID y cgroup corresponden a la instancia observada antes del stop; resolver la ruta de cgroup v2 desde información del manager, sin aceptar una ruta aportada por el fixture.
10. Leer y parsear `cgroup.events`; exigir exactamente una entrada válida `populated 0`. Lectura parcial, malformada, inaccesible, filesystem inesperado o cgroup desaparecido de forma no explicada produce ABORT.
11. Volver a consultar unidad, InvocationID, ControlGroup y jobs; verificar que no hubo sustitución ni reinicio.
12. Releer `cgroup.events` mientras la puerta sigue adquirida y exigir `populated 0`.
13. Emitir `QUIESCENT` solo si todas las condiciones requeridas y la evidencia de no escape/FD ownership del escenario son completas. En cualquier otro caso emitir `ABORT_NOT_QUIESCENT` o `INCOMPLETE` con razón explícita.
14. Persistir el reporte y la decisión; liberar el marcador solo tras completar la secuencia. Limpiar únicamente recursos del harness cuya identidad se verificó. La retirada del endpoint fixture, si procede, es el cleanup exacto descrito en §7 y no una operación de stale recovery.

La secuencia no se sustituye por `sleep`, ausencia del PID principal, `pgrep`, tabla procfs AF_UNIX o una conexión de prueba.

## 5. Matriz de escenarios QP-01..QP-15

| ID | Preparación / estímulo | Evidencia que debe observarse | Resultado obligatorio |
|---|---|---|---|
| **QP-01** | Servicio fixture normal con listener propio en unidad dedicada; solicitar stop completo. | InvocationID/cgroup coherentes; unidad `inactive`; sin jobs start/restart; `populated 0` en dos lecturas correlacionadas; listener cerrado por el proceso. | `QUIESCENT` únicamente tras completar toda la secuencia común. |
| **QP-02** | Crear antes del listener un proceso auxiliar fixture dentro del mismo cgroup; mantenerlo vivo durante la primera observación y luego permitir su terminación por stop. | Antes de terminar el auxiliar, cgroup `populated 1` y no QUIESCENT; tras stop, todos los procesos del cgroup terminan y se observa `populated 0`. | Rechazar quiescencia prematura; después del stop completo puede ser `QUIESCENT`. El auxiliar no recibe el listener FD. |
| **QP-03** | Servicio fixture ignora SIGTERM; `TimeoutStopSec` de la unidad es mayor que el deadline de observación del probe. | Durante el deadline, unidad `deactivating`, job stop pendiente y cgroup `populated 1`; el probe no mata el proceso por fuera del manager. Después del aborto, systemd aplica su política final de terminación y el harness espera la salida antes de cleanup. | `ABORT_NOT_QUIESCENT` en la ventana inicial; nunca `QUIESCENT` por ausencia del PID principal. |
| **QP-04** | Unidad en estado de transición o con job start/restart pendiente durante la ventana de observación. | Propiedades del manager muestran transición/job no terminal; la puerta debe impedir que el propio harness emita start concurrente. | `ABORT_NOT_QUIESCENT`; no inferir quiescencia aunque `populated 0` en una lectura aislada. |
| **QP-05** | Crear dos unidades transitorias fixture independientes (SERVICE y OTHER), verificar sus cgroups separados y ejecutar además una variante con el `ControlGroup` esperado deliberadamente discrepante en el adaptador de prueba. | Las identidades `ControlGroup` y `st_dev/st_ino` deben ser distintas y coincidir con la unidad exacta. La variante de discrepancia debe abortar antes de leer/actuar sobre el cgroup equivocado. No se fuerza una migración manual de procesos entre cgroups: hacerlo alteraría la jerarquía que el manager controla. | `ABORT_NOT_QUIESCENT` ante cualquier discrepancia o cgroup compartido observado; no detener ni modificar OTHER. |
| **QP-06** | Crear una unidad transitoria negativa con `Delegate=yes` y otra válida con `Delegate=no`; no mover procesos manualmente ni escribir en cgroupfs. | El adaptador consulta `Delegate`, `DelegateControllers`, capacidades efectivas del proceso y permisos de escritura relevantes. La variante delegada se rechaza antes de declarar quiescencia; la válida no dispone de autoridad para modificar la jerarquía. | `ABORT_NOT_QUIESCENT` para `Delegate=yes`; no usar `populated 0` como prueba de ausencia de procesos/FDS externos. |
| **QP-07** | Simular lectura parcial, error de permisos, contenido malformado, clave duplicada/ausente o filesystem cgroup no esperado para `cgroup.events`. | Recolector identifica exactamente el error y conserva bytes/estado disponible sin normalizarlo como cero. | `ABORT_NOT_QUIESCENT`; nunca interpretar fallo de lectura como `populated 0`. |
| **QP-08** | Después de bind/listen, el fixture instala seccomp y ejecuta intentos controlados de `fork`, `vfork`, `clone` y `clone3`. | Cada syscall debe fallar con `EPERM`; el contador de procesos del fixture y el inventario del cgroup no deben mostrar un descendiente nuevo. | PASS solo si todas las vías disponibles quedan denegadas. Si una syscall no puede filtrarse o crea un hijo, FAIL. |
| **QP-09** | Intentar duplicar el listener mediante `dup`, `dup2`, `dup3` y `fcntl(F_DUPFD/F_DUPFD_CLOEXEC)`, y transferirlo mediante `sendmsg`, `recvmsg`, `sendmmsg` y `recvmmsg` después de bind/listen. | Seccomp debe devolver `EPERM` para las syscalls de duplicación y paso de FD antes de que se cree otra referencia o se transfiera ancillary data; el canal de control basado en `read`/`write` continúa funcionando. Para `fcntl`, el filtro compara específicamente los comandos F_DUPFD y F_DUPFD_CLOEXEC, sin bloquear operaciones no relacionadas. | PASS solo si no se produce transferencia. Cualquier syscall no filtrada o FD recibido es FAIL y bloquea QUIESCENT. |
| **QP-10** | Ejecutar `execve` en el mismo proceso (sin fork) hacia un helper mínimo de inspección, con el listener abierto y `FD_CLOEXEC` activo. | El PID/cgroup permanecen correlacionados y el nuevo image confirma que el FD listener no existe; el helper informa por un FD de control preexistente que no transporta el listener. | PASS solo si el descriptor se cierra en exec. Este escenario no convierte CLOEXEC en defensa frente a fork. |
| **QP-11** | Mientras el orquestador mantiene lock y marcador sticky, un segundo actor solicita start/restart por el supervisor autorizado; un subcaso simula caída del orquestador dejando el marcador. | La solicitud concurrente se rechaza por lock/marker; tras caída, el lock se libera pero el marcador persiste y el supervisor sigue rechazando start/restart hasta recuperación manual explícita. | PASS si no aparece job ni nueva InvocationID y el marcador sobrevive a la caída. Una llamada directa de root a PID 1 queda fuera del modelo de protección, no se presenta como bloqueada. |
| **QP-12** | Un actor root de fault-injection, explícitamente fuera de la ruta autorizada, reinicia solo la unidad transitoria fixture entre snapshots mediante el manager. | Cambia `InvocationID` aunque el nombre de unidad y `ControlGroup` textual puedan repetirse; el orquestador no combina snapshots. La prueba demuestra detección, no bloqueo de root. | `ABORT_NOT_QUIESCENT`; no combinar evidencia de dos invocaciones. |
| **QP-13** | Caso de control negativo que modela retención externa del listener FD fuera del cgroup de servicio. No usar una unidad .socket real ni activar socket activation. | El cgroup del servicio puede estar vacío mientras un proceso externo fixture retiene una referencia. Para hacer determinista el control negativo, el harness crea deliberadamente esa referencia externa mediante una transferencia fixture controlada, marcada como violación intencional de Q-05/Q-06; el recolector debe identificarla por el inventario cerrado de actores fixture y rechazar la quiescencia. Esta excepción existe solo dentro del escenario negativo, no es un patrón permitido para el servicio. | Nunca declarar `QUIESCENT`. Documentar expresamente que systemd socket activation permanece fuera de alcance y no se ha validado. |
| **QP-14** | Forzar fallo del supervisor, desconexión del manager o timeout durante stop/consulta. | Error/timeout identificable; falta una o más observaciones obligatorias; no se emite estado terminal positivo. | `ABORT_NOT_QUIESCENT` o `INCOMPLETE`; pathname preservado y sin operación de retirada. |
| **QP-15** | Inyectar en la frontera de lectura una identidad final distinta (`st_dev/st_ino`) o un `ControlGroup` cambiado, sin escribir ni renombrar cgroups reales. | El adaptador de prueba entrega evidencia de identidad discordante; el comparador debe detectarla antes de usar `cgroup.events` como evidencia positiva. | `ABORT_NOT_QUIESCENT`; no avanzar a inspección/retirada del pathname. |

### 5.1 Criterios de conteo

- Los quince escenarios son obligatorios; un escenario no ejecutado no se considera PASS.
- QP-01 y QP-02 deben demostrar el camino positivo y la terminación del cgroup.
- QP-03..QP-07 y QP-12..QP-15 deben demostrar abortos fail-closed.
- QP-08..QP-10 deben demostrar las invariantes de descriptor mediante seccomp y exec en el mismo proceso, no solo inspeccionar flags.
- QP-11 debe probar la exclusión de lifecycle durante toda la ventana de mantenimiento y la persistencia del marcador ante caída del orquestador.
- QP-13 es una prueba negativa del supuesto de FD externo mediante una violación controlada y acotada de la política de FD; no es una prueba de socket activation ni valida la retención real del system manager.
- QP-05 no intenta reparentar procesos ni escribir manualmente en cgroupfs; el mismatch se prueba en el límite del adaptador y con dos unidades fixture separadas.
- QP-12 es fault injection root fuera del supervisor autorizado y solo comprueba detección de sustitución; QP-15 prueba la validación de identidad del descriptor de cgroup.
- Ningún escenario de quiescencia ni de fault injection puede retirar o sustituir el pathname. Solo la fase final de cleanup puede retirar el endpoint fixture de esta ejecución, bajo las verificaciones exactas de §7 y §9.6; cualquier otra mutación hace que el probe falle.

## 6. Evidencia estructurada

El resultado JSON debe incluir como mínimo:

### Identidad de ejecución y entorno
- commit exacto del checkout, nombre de VM/entorno declarado, kernel, systemd, cgroup mode y Python;
- EUID, duración monotónica, identificador aleatorio de ejecución y estado de cleanup;
- nombres aleatorios de sandbox/unidad fixture y su identidad filesystem;
- versión/schema del propio reporte.

### Evidencia de lifecycle por snapshot
- timestamp monotónico de cada consulta;
- nombre exacto de unidad, InvocationID, ActiveState, SubState, ControlGroup, KillMode y Delegate;
- lista/estado de jobs relevantes start/restart;
- filesystem y mount de cgroup observados;
- contenido íntegro acotado de `cgroup.events`, resultado de parseo y `populated`;
- identidad de cgroup y correlación con la invocación;
- estado de la puerta: adquirido, contención concurrente probada, liberado.

### Evidencia de descriptor
- PID/FD fixture, target de FD, tipo, `SO_ACCEPTCONN`, `FD_CLOEXEC`, pathname y metadata del socket;
- resultados de intentos controlados fork/exec/SCM_RIGHTS;
- confirmación de que ningún descriptor fue publicado al orquestador ni a proceso externo;
- nunca incluir payloads, secretos ni datos personales.

### Resultado
- QP-01..QP-15: PASS/FAIL/INCOMPLETE y razón;
- resultado global PASS solo con 15/15 PASS, cleanup confirmado y todas las evidencias requeridas;
- resultado final de quiescencia por escenario: `QUIESCENT` o `ABORT_NOT_QUIESCENT`;
- `recovery_pathname_mutation_performed=false`;
- `fixture_cleanup_endpoint_removed=true|false`, con `st_dev/st_ino` antes/después y resultado de validación;
- bandera constante `systemd_socket_activation_tested=false`.

No registrar `QUIESCENT` si falta una lectura, si hay discrepancia entre manager/cgroup, si la puerta no está demostrada o si la política de FD no puede verificarse.

## 7. Reglas de fallo y cleanup

- Todo error, timeout, excepción, respuesta ambigua o evidencia incompleta produce FAIL/INCOMPLETE; nunca se convierte en cero procesos, `populated 0` ni PASS por defecto.
- No matar procesos ajenos ni corregir manualmente un cgroup inesperado.
- Si un fixture queda vivo, la limpieza solo puede dirigirse a la unidad transitoria identificada por nombre aleatorio e InvocationID capturados por el propio runner. Si la identidad no coincide, detener la limpieza y reportar INCOMPLETE.
- No retirar un pathname residual, ajeno, preexistente o sustituido como operación de recuperación. El único endpoint que puede retirarse en cleanup es el creado por esta ejecución y solo tras verificar cierre de todos los FDs, `st_dev/st_ino`, tipo socket, owner/mode y el `dirfd` anclado al sandbox.
- El cleanup del endpoint fixture usa `unlinkat` de un único nombre conocido, nunca recorrido recursivo; después se retiran únicamente los directorios vacíos creados por la ejecución.
- Si cualquier identidad no coincide o cleanup no puede completarse inequívocamente, conservar el objeto y declarar INCOMPLETE; no ejecutar limpieza recursiva genérica.
- La puerta se libera al final de una ruta de salida controlada; si el proceso orquestador cae, el diseño de la puerta debe tener una política de recuperación auditada que no permita start/restart durante una decisión inconclusa.

## 8. Interpretación de resultados

Un `overall=PASS` significará únicamente que QP-01..QP-15 del harness se comportaron como se especifica en el commit, VM, versión de systemd/kernel y configuración registrados.

No demuestra:
- resistencia frente a root malicioso, capacidades equivalentes ni procesos comprometidos dentro de TCB-1;
- cobertura global de FDs de todo el host por inspección procfs;
- atomicidad entre snapshots ni ausencia de carreras frente a root que omita deliberadamente la puerta;
- seguridad de socket activation;
- que una unidad/servicio Atlas real exista o esté correctamente configurado;
- que el pathname sea stale o que sea seguro retirarlo;
- que el residual TOCTOU de `unlinkat` haya desaparecido.

A-THREAT-05 seguirá abierta después de un PASS hasta satisfacer todos los criterios del contrato base, incluida una autorización humana real para cualquier retirada futura y una decisión explícita sobre TOCTOU.

## 9. Resolución de los seis puntos previos a implementación

Los seis puntos de diseño se consideran **resueltos a nivel de especificación** mediante las decisiones siguientes. Esto cierra la fase de análisis documental, no la revisión del runner: cualquier detalle que contradiga estas decisiones deberá volver a revisión antes de escribir código.

### 9.1 Punto 1 — Interfaz de systemd y fuente de verdad

**Decisión:** consultar estado y propiedades mediante el D-Bus del system manager usando `busctl --system --json=short`. No parsear salida humana de `systemctl status`, `systemctl show`, `systemd-analyze` ni mensajes de journald para decidir quiescencia.

El adaptador consultará:

1. `org.freedesktop.systemd1.Manager.GetUnit(nombre)` para obtener el object path exacto de la unidad ya cargada; no usar `LoadUnit` para resolver una unidad desconocida.
2. `org.freedesktop.DBus.Properties.GetAll` sobre las interfaces Unit, Service y ResourceControl que la introspección del manager indique para esa unidad.
3. De Unit: `Id`, `Names`, `LoadState`, `ActiveState`, `SubState`, `Job`, `InvocationID`, `Transient`, `Triggers`, `TriggeredBy`, `Requires`, `Wants` y dependencias relevantes.
4. De Service: `ControlGroup`, `KillMode`, `Restart`, `User`, `Group` y propiedades disponibles para confirmar la configuración fixture.
5. De ResourceControl, cuando esté expuesta: `Delegate`, `DelegateControllers` y `DelegateSubgroup`.
6. `Manager.ListJobs()` para enumerar jobs y filtrar por nombre exacto de unidad y tipos start/restart/try-restart/reload-or-start; la propiedad Unit.Job debe concordar con el inventario.

El cliente debe validar el JSON tipado producido por busctl contra las firmas D-Bus esperadas, preservar los tipos, rechazar campos ausentes/tipos inesperados y comprobar el código de salida. No se aceptan conversiones heurísticas de texto. La introspección del object path identifica en qué interfaz está expuesta cada propiedad; si `InvocationID`, `ControlGroup`, `KillMode` o `Delegate` no están disponibles con su firma esperada, el preflight aborta. La consulta de estado usa snapshots antes y después de leer cgroup; no se considera una única respuesta D-Bus una transacción atómica.

La petición de stop se emite sobre la unidad exacta mediante el supervisor designado (D-Bus `Manager.StopUnit` con respuesta tipada o `systemctl --no-block stop` invocado sin shell). El estado terminal se determina exclusivamente por D-Bus y cgroup, no por el texto/exit status del comando que solicitó stop. Cada llamada tiene timeout acotado y salida stdout/stderr acotada. La conexión siempre es al bus **system** local; quedan prohibidos `--user`, `--host`, `--machine` y destinos remotos.

**Criterio de aceptación:** en preflight, `busctl --version` debe confirmar soporte JSON; el adaptador debe resolver una unidad fixture conocida, extraer propiedades y jobs con sus tipos exactos, y tratar una propiedad/interfaz no disponible como INCOMPLETE. No se implementa fallback a parseo de texto.

### 9.2 Punto 2 — Puerta root-managed de mantenimiento

**Decisión:** lock exclusivo más marcador sticky, ambos en un directorio privado root:root 0700 bajo `/run`.

- El lock se abre con `O_NOFOLLOW|O_CLOEXEC`, se verifica como archivo regular root:root con nlink 1 y modo 0600, y se adquiere con `flock(LOCK_EX|LOCK_NB)`.
- Tras adquirirlo, el orquestador crea el marcador de mantenimiento con `O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC`, modo 0600. Contiene schema, run_id aleatorio, nombre de unidad, InvocationID inicial y fase. Se escribe de forma completa y se sincroniza antes de solicitar stop.
- Todo start/restart autorizado pasa por un supervisor único. Ese supervisor adquiere el mismo lock y rechaza si existe marcador. El orquestador de mantenimiento conserva el lock desde antes de stop hasta que reporte, decisión y cleanup hayan concluido.
- El marcador no se elimina en un bloque finally genérico. Solo se elimina tras persistir el reporte final, confirmar estado terminal y completar cleanup exacto. Si el orquestador cae, el kernel libera flock pero el marcador permanece y el supervisor sigue rechazando start/restart; su retiro requiere recuperación manual auditada.
- La unidad de prueba es transitoria, no habilitada, con `Restart=no`, sin timers, path/socket activators, triggers ni dependencias que puedan iniciarla automáticamente.

**Límite explícito:** un administrador root puede eludir deliberadamente el supervisor y llamar a PID 1 directamente. El lock no puede impedirlo y no se afirma lo contrario. Root está dentro del dominio de confianza. La prueba verifica que los actores autorizados y automatizaciones declaradas usan la puerta, y que una omisión root durante QP-12 es detectada por la revalidación de InvocationID; no demuestra resistencia a root malicioso.

**Criterio de aceptación:** dos actores cooperantes no pueden mantener simultáneamente el lock; el segundo no crea job; la caída del orquestador deja marcador y bloquea el siguiente start autorizado; el marcador no se limpia automáticamente por timeout ni por proceso de recuperación no auditado.

### 9.3 Punto 3 — Reporte JSON y límites

**Decisión:** reporte JSON UTF-8, schema `atlas.listener-quiescence-probe/1`, una sola estructura raíz, claves deterministas, sin NaN/Infinity, sin claves duplicadas y sin datos no serializables. El reporte completo tendrá un máximo de **1 MiB**; cada escenario, máximo **32 KiB**; cada snapshot D-Bus, máximo **16 KiB**; cada lectura `cgroup.events`, máximo **4 KiB**. Al superar un límite se aborta el escenario; nunca se trunca evidencia y se conserva como si fuera completa.

Campos raíz obligatorios:

- `schema`, `run_id`, `probe_version`, `git_commit`;
- `environment`: distro/release, kernel, systemd, busctl, Python, cgroup mode/mount, VM declarada y EUID;
- `started_utc`/ `finished_utc` solo informativos y `started_monotonic_ns`/ `finished_monotonic_ns` obligatorios para ordenar eventos dentro del mismo boot;
- `preflight`, `gate`, `unit_identity`, `snapshots`, `scenarios`, `cleanup`, `overall`;
- por escenario: ID, estado PASS/FAIL/INCOMPLETE, razón estable, timestamps monotónicos, snapshots referenciados y resultado QUIESCENT/ABORT_NOT_QUIESCENT si aplica.

Los timestamps se obtienen con `time.clock_gettime_ns(CLOCK_MONOTONIC)`; UTC nunca se usa para calcular deadlines. El lector de `cgroup.events` acumula lecturas parciales hasta EOF con un máximo de 4096 bytes. El parser exige una única clave `populated` con valor entero 0 o 1; rechaza duplicados, ausencia, valores extraños y claves desconocidas hasta que se revise el schema del kernel. Se permiten las claves conocidas del cgroup v2 objetivo, registrando su contenido íntegro.

El reporte no contiene payloads IPC, variables de entorno completas, secretos, tokens, contenido de archivos ajenos ni datos personales. stdout y stderr de subprocesos se limitan y se redactan; la evidencia primaria son los campos estructurados consultados.

**Criterio de aceptación:** validación contra schema local versionado, límites aplicados antes de acumular memoria ilimitada, timestamps monotónicos presentes en cada evento y fallo fail-closed ante JSON inválido o evidencia sobredimensionada.

### 9.4 Punto 4 — Preflight no mutante de Atlas-VM-test

**Decisión:** el runner no prepara ni repara el sistema. Ejecuta una fase preflight de solo lectura y, si cualquier requisito falta, termina INCOMPLETE sin crear recursos.

Perfil de compatibilidad inicial que se va a validar: Debian 13, systemd 257.13, kernel `6.12.117+deb13-amd64`, Python 3.13.5, cgroup v2 unificado y `busctl` con JSON. Cualquier cambio de versión queda fuera de este primer perfil y requiere revisión explícita antes de ampliar compatibilidad.

Preflight obligatorio:

- EUID 0 y confirmación humana explícita de que el entorno es la VM desechable `Atlas-VM-test`; el runner no puede demostrar por sí solo que una VM es desechable.
- system bus y PID 1 accesibles; systemd y busctl dentro del perfil fijado; interfaces D-Bus y propiedades requeridas presentes.
- cgroup v2 unificado: mount de tipo cgroup2, raíz y mountpoint inequívocos, `cgroup.events` legible, sin fallback a cgroup v1.
- `/run` montado como tmpfs, espacio suficiente y permisos para un sandbox privado de ejecución.
- identidades fixture numéricas reservadas SERVICE 2005:2005 y OTHER 2006:2006, aprobadas para la VM desechable `Atlas-VM-test`; no requieren entradas NSS ni cuentas/grupos del sistema. Como systemd exige resolver `User=`/`Group=` mediante NSS, el runner inicia cada unidad transitoria como root con `CapabilityBoundingSet=CAP_SETUID CAP_SETGID CAP_SETPCAP` y `AmbientCapabilities=` vacío. `/usr/bin/setpriv` limpia grupos suplementarios, cambia a los UID/GID numéricos, vacía inheritable/permitted/effective/ambient/bounding capabilities y ejecuta Python mediante `exec`; `NoNewPrivileges` se aplica en los escenarios que lo requieren. El runner verifica por separado la identidad root y el perfil de capacidades de arranque de systemd, y las credenciales/grupos/capacidades reales observadas por el proceso fixture. El binario setpriv debe ser regular, root-owned y no modificable por grupo/otros. No crea, modifica ni consulta cuentas/grupos.
- intérprete Python 3.13.5, `busctl`, `systemd-run`, `systemctl` y biblioteca `libseccomp.so.2` disponibles. No instalar paquetes ni compilar componentes durante preflight.
- ausencia de colisión para los nombres aleatorios que se van a usar; una colisión implica generar otro nombre o abortar, nunca reutilizar el objeto existente.
- disponibilidad de syscalls/funciones requeridas para dirfd, no-follow, monotonic clock y seccomp.

Preflight no ejecuta stop/restart de unidades preexistentes, no consulta ni enumera servicios Atlas reales, no escribe en `/etc`, no cambia cgroups, no crea usuarios/grupos y no toca configuración global. Solo después de PASS de preflight el operador podrá iniciar una ejecución expresamente autorizada.

**Criterio de aceptación:** reporte preflight completo y sin mutaciones; toda precondición ausente produce INCOMPLETE con código de razón estable.

### 9.5 Punto 5 — Reproducción determinista de los escenarios difíciles

**Decisión:** usar fixtures transitorios aislados y fault injection en límites explícitos, sin modificar unidades ajenas ni escribir manualmente en la jerarquía cgroup.

- **QP-05:** dos unidades fixture independientes SERVICE/OTHER prueban cgroups separados. Una variante del adaptador presenta un ControlGroup esperado distinto para probar rechazo de identidad. No se fuerza una falsa compartición moviendo procesos manualmente entre cgroups.
- **QP-06:** unidad negativa transitoria con `Delegate=yes` se rechaza antes de aceptar quiescencia; unidad positiva `Delegate=no` se comprueba sin otorgar capacidades de administración cgroup al proceso. No se escribe en cgroupfs para simular escape.
- **QP-08:** filtro seccomp instalado después de bind/listen deniega `fork`, `vfork`, `clone` y `clone3` con EPERM. El test intenta cada syscall disponible y confirma que no nace un descendiente.
- **QP-09:** el mismo filtro deniega `sendmsg`, `recvmsg`, `sendmmsg`, `recvmmsg`, `pidfd_getfd`, `io_uring_setup`, `io_uring_enter` y `io_uring_register`; también bloquea duplicación por `dup*` y `fcntl(F_DUPFD*)`. El canal de control usa read/write. QP-13 es la única excepción fixture deliberada y separada para demostrar el resultado negativo de un FD externo.
- **QP-10:** el proceso ejecuta `execve` sobre sí mismo (sin fork); el helper comprueba que FD_CLOEXEC cerró el listener y reporta por un descriptor de control que no es el listener.
- **QP-12:** fault injector root llama directamente al manager para reiniciar únicamente la unidad transitoria entre snapshots. Es una violación deliberada de la puerta y sirve para comprobar que InvocationID distinto invalida toda la evidencia; no representa un actor autorizado.
- **QP-13:** una variante aislada sin filtro de FD transfiere deliberadamente el listener mediante SCM_RIGHTS a un holder OTHER fuera del cgroup. Tras detener el servicio, se demuestra `populated 0` en el cgroup y FD listener aún abierto en el holder; el resultado obligatorio es ABORT_NOT_QUIESCENT. El holder se termina de forma controlada al finalizar el caso.
- **QP-15:** el adaptador de cgroup inyecta una identidad final st_dev/st_ino distinta o un ControlGroup discordante. No se renombra ni manipula el cgroup real del kernel.

**Criterio de aceptación:** cada fault injection tiene un identificador explícito, solo puede referirse a la unidad/run_id fixture actual y debe dejar evidencia del estímulo y de la respuesta. Si el escenario requiere tocar un servicio ajeno o mover procesos en cgroupfs, se marca INCOMPLETE; no se improvisa.

### 9.6 Punto 6 — Unidades transitorias, sandbox y cleanup

**Decisión:** crear únicamente unidades `.service` transitorias con nombre aleatorio mediante `systemd-run --no-block --unit=...` y propiedades explícitas. No crear archivos de unidad, drop-ins, enlaces enablement, timers, sockets ni slices persistentes. El estado se consulta por D-Bus, no se parsea la salida de systemd-run/systemctl.

Propiedades mínimas de la unidad fixture: `Type=exec`, `User=root`, `Group=root`, `CapabilityBoundingSet=CAP_SETUID CAP_SETGID CAP_SETPCAP`, `AmbientCapabilities=` vacío, `KillMode=control-group`, `Delegate=no`, `Restart=no`, sin activadores, y límites de inicio/parada acotados. El launcher `/usr/bin/setpriv` reduce credenciales y capacidades antes de ejecutar el fixture; el proceso Python debe observar UID/GID fixture y todos los conjuntos de capacidades en cero. `NoNewPrivileges=yes` se aplica cuando el escenario lo exige. QP-03 ajusta solo su fixture negativo y su deadline para observar el aborto antes de la terminación final del manager.

El sandbox usa `/run/atlas-qp` root:root 0711 (sin permiso de listado para otros) y un subdirectorio aleatorio por ejecución root:2005 modo 0730, de forma que SERVICE 2005:2005 pueda crear el endpoint conocido sin conceder acceso a otros UIDs. QP-05 usa un subdirectorio hermano root:OTHER modo 0730 para probar separación de acceso. QP-13 crea una excepción controlada: un directorio compartido root:root modo 01733, sin listado, donde OTHER publica un socket de control modo 0666 y sus archivos ready/received permanecen 0600; SERVICE conecta al socket únicamente para transferir el listener FD mediante SCM_RIGHTS. Todos los nombres se generan por ejecución; cada directorio se abre y conserva mediante dirfd y se registra su st_dev/st_ino. El servicio no recibe rutas arbitrarias del usuario.

Orden de cleanup:

1. Persistir snapshots y resultado del escenario antes de modificar recursos fixture.
2. Solicitar stop solo a la unidad transitoria exacta y esperar por D-Bus `inactive`, sin jobs, cgroup vacío y cierre del fixture.
3. Confirmar que no queda holder externo del escenario; QP-13 debe cerrar su FD y terminar el proceso OTHER antes de seguir.
4. Verificar el endpoint fixture con `fstatat(AT_SYMLINK_NOFOLLOW)` y comparar tipo, owner, mode, st_dev y st_ino con la identidad registrada al crearlo.
5. Retirar únicamente ese nombre mediante `unlinkat(dirfd, nombre, 0)`; después retirar directorios fixture vacíos mediante dirfd. Nunca usar `rm -rf`, glob, path reconstruido o recorrido recursivo.
6. Cerrar el observer FD de cgroup después de confirmar `populated=0`; llamar `UnrefUnit` en la conexión persistente que adquirió `RefUnit`; esperar que `ListUnitsByNames` no devuelva la unidad y que `ListJobs` no contenga jobs para ella. Si la unidad persiste, no forzar cleanup global.
7. Persistir resultado final, retirar el marcador sticky y liberar flock. Si algo falla, conservar marcador/sandbox y reportar INCOMPLETE.

Esta retirada del socket fixture es exclusivamente cleanup de un objeto creado en esta ejecución y validado por identidad. No es stale recovery, no prueba `unlinkat` productivo y no autoriza retirar ningún endpoint Atlas. La bandera de recuperación debe permanecer siempre `recovery_pathname_mutation_performed=false`.

**Criterio de aceptación:** el inventario de recursos creados por run_id coincide exactamente con el inventario retirado; no hay cambios en unidades, cgroups, archivos o procesos ajenos; cualquier discrepancia detiene cleanup y deja evidencia.

### 9.7 Estado de los seis puntos

| Punto | Decisión de diseño | Estado |
|---|---|---|
| 1. Interfaz systemd | D-Bus tipado vía busctl JSON; sin parseo de salida humana | Resuelto documentalmente |
| 2. Puerta root-managed | flock + marcador sticky + supervisor único; root directo queda dentro del TCB | Resuelto con límite explícito |
| 3. Reporte JSON | schema versionado y límites estrictos | Resuelto documentalmente |
| 4. Preflight VM | perfil fijado y solo lectura; sin auto-provisioning | Resuelto documentalmente |
| 5. Fault injection | fixtures aislados, seccomp y adaptadores controlados | Resuelto documentalmente |
| 6. Lifecycle/cleanup | unidades transitorias y cleanup por identidad exacta | Resuelto documentalmente |

**Estado de implementación (2026-11-22, actualización):** el propietario autorizó implementar el runner y aprobó un supervisor temporal exclusivo del harness para QP-11. El archivo `tests/integration/private_unix_listener/run_listener_quiescence_probe.py` contiene estímulos y oráculos para QP-01..QP-15. La implementación sigue sin ejecutar ni validar; el código está en revisión estática y no constituye evidencia experimental.

Cobertura implementada:
- **QP-01/QP-02:** política seccomp aplicada después de bind/listen; QP-02 crea el auxiliar antes del listener e instala también en él la política anti-fork/FD-escape antes de que el padre enlace. El runner comprueba `fork`, `vfork`, `clone`, `clone3`, duplicación FD (`dup*`, `fcntl(F_DUPFD*)`, `pidfd_getfd`), `SCM_RIGHTS` e interfaces `io_uring`. El auxiliar QP-02 comunica evidencia propia de `NoNewPrivs=1`, `Seccomp=2`, filtro activo, `CapEff=0`, sin CAP_SYS_ADMIN y sin escritura en su cgroup. El listener principal confirma también `NoNewPrivs=1`, `Seccomp=2`, filtro activo, `CapEff=0`, sin CAP_SYS_ADMIN y sin escritura cgroup. Se usan dos lecturas `cgroup.events` separadas por 50 ms y observaciones D-Bus correlacionadas. Solo emite `QUIESCENT` si todos los predicados se cumplen.
- **QP-03/QP-04:** QP-03 detiene una unidad cuyo proceso ignora SIGTERM y observa `deactivating` + job stop pendiente + `populated=1` antes de que systemd termine el fixture. QP-04 solicita un `restart` real no bloqueante sobre un fixture sin pathname, exige el job `restart` exacto mientras el cgroup antiguo sigue poblado, detecta la nueva `InvocationID` y observa el cgroup de reemplazo antes de detenerlo. Ambos escenarios clasifican el intervalo no quiescente como ABORT; no autorizan pathname mutation.
- **QP-05/QP-06/QP-07:** separación de ControlGroup/identidades; rechazo de `Delegate=yes` y control positivo con `Delegate=no`, `NoNewPrivileges=yes`, `ProtectControlGroups=yes`, bounding/ambient capabilities vacías, `CapBnd=0`, `CapEff=0`, sin CAP_SYS_ADMIN y sin escritura cgroup; parser de `cgroup.events` con lecturas parciales, claves duplicadas, valores inválidos, límite y error de lectura.
- **QP-08/QP-09/QP-10:** denegación seccomp de creación de procesos; denegación de los mecanismos de duplicación/transferencia comprobados (`dup*`, `fcntl(F_DUPFD*)`, `pidfd_getfd`, `SCM_RIGHTS` e `io_uring_setup/enter/register`); comprobación adicional de que abrir `/proc/self/fd/N` para el listener socket falla con `ENXIO` en Linux (no es un `dup`); y `execve` en el mismo PID con descriptor CLOEXEC cerrado. El fallo `ENXIO` es una propiedad de apertura del socket, no una regla seccomp.
- **QP-11:** `_TestLifecycleSupervisor` es una clase interna del runner. Comprueba token de actor, exclusión flock, caída simulada, persistencia del marcador y rechazo de restart por un supervisor nuevo. La simulación libera flock y cierra la conexión persistente sd-bus (liberando RefUnit); tras reacquirir la puerta abre una conexión nueva y vuelve a referenciar el fixture activo. No es la terminación real de un proceso supervisor independiente.
- **QP-12:** restart directo de root fuera del supervisor como fault injection; detecta `InvocationID` nuevo y conserva separados los observadores cgroup de la invocación antigua y la sustituta.
- **QP-13:** fixture sin filtro que transfiere el listener FD mediante SCM_RIGHTS a un proceso OTHER externo al cgroup. Se comprueba que el servicio puede quedar `populated=0` mientras OTHER conserva el FD; el holder se termina antes de retirar el endpoint fixture.
- **QP-14/QP-15:** fallos inyectados del adaptador/supervisor y timeout acotado; discrepancias inyectadas de ControlGroup/st_dev/st_ino.

El runner fija el perfil Debian 13/systemd 257/kernel/Python previsto y verifica tanto `busctl --version` como la propiedad D-Bus `Manager.Version` del PID 1 (no asume que la versión del cliente equivale a la del manager); valida `libseccomp` y `libsystemd`, que SERVICE y OTHER puedan recorrer/leer el script y ejecutar Python sin poder escribir ni reemplazar el archivo o sus directorios padre; valida además tipo `SOCK_SEQPACKET`, `SO_ACCEPTCONN=1`, `CLOEXEC` y UID/GID del endpoint contra la identidad de cada fixture; crea solo unidades `.service` transitorias y mantiene un observer FD de `cgroup.events` para cada fixture. El cleanup es bifásico: primero detener y comprobar todos los fixtures; solo si todos están inactivos, sin jobs y con cgroup vacío, retirar endpoints y archivos ready por dirfd + identidad exacta. Los JSON de fixture se leen con O_NOFOLLOW y O_NONBLOCK, límites, owner/mode/inode y rechazo de claves duplicadas; las aperturas para verificar o retirar archivos regulares también son no bloqueantes para rechazar FIFO sin quedar colgado. El reporte aplica límites por escenario/total y timestamps monotónicos. El marcador y el reporte se reescriben solo si conservan el inode original; el supervisor verifica el marker con O_NOFOLLOW y owner/mode/dev/inode. La evidencia final y la autorización de liberar la puerta se persisten antes de retirar el marcador; no se reescribe el reporte después de retirar el marcador. La ausencia del marcador, junto al registro de autorización persistido, es el testigo de liberación.

Las observaciones tipadas se hacen con `busctl`: propiedades genéricas (`Id`, `InvocationID`, `Job`, etc.) se consultan en `org.freedesktop.systemd1.Unit`, mientras `ControlGroup`, `MainPID`, `Delegate`, `DelegateControllers` y `DelegateSubgroup` se consultan en `org.freedesktop.systemd1.Service` según la API systemd 257. Las referencias transitorias usan una única conexión persistente `libsystemd/sd-bus`: `RefUnit` y `UnrefUnit` se ejecutan sobre el mismo sender, evitando perder la referencia al terminar cada proceso `busctl`. Tras cerrar el observer cgroup y ejecutar `UnrefUnit`, el runner espera que `ListUnitsByNames` deje de devolver la unidad y que `ListJobs` no contenga jobs; si no ocurre, cleanup queda INCOMPLETE y el marcador sticky se conserva.

**Límites:** QP-11 es un test double en proceso, no un supervisor productivo ni protección contra root. QP-12 confirma explícitamente que root puede eludir la puerta. QP-13 prueba un holder OTHER controlado, no socket activation. El modelo TCB-1 sigue considerando confiables los procesos del mismo UID dedicado; root permanece en la TCB. A-THREAT-05 continúa abierta.

**Estado de validación:** no se han ejecutado el runner, pruebas, builds ni workflows. No se han creado unidades, cgroups, usuarios, grupos, rutas ni servicios en ningún host durante esta sesión. La siguiente puerta es terminar la revisión estática y luego ejecutar exclusivamente en `Atlas-VM-test`, nunca en `greed`.

Referencias técnicas externas usadas para fijar la interfaz y contrastadas durante la revisión estática del perfil systemd 257.13:

- Linux `proc_pid_fd(5)` describe los enlaces `/proc/PID/fd` para sockets; la apertura de un socket a través de ese enlace falla en Linux con `ENXIO` porque el tipo de archivo socket no implementa `open`: https://blog.gnoack.org/post/proc-fd-is-not-dup
- systemd D-Bus API: https://www.freedesktop.org/software/systemd/man/257/org.freedesktop.systemd1.html
- busctl JSON y llamadas D-Bus: https://www.freedesktop.org/software/systemd/man/257/busctl.html
- cgroup v2: https://docs.kernel.org/admin-guide/cgroup-v2.html
- pidfd_getfd syscall and ptrace access requirement (Debian trixie man-pages): https://manpages.debian.org/trixie/manpages-dev/pidfd_getfd.2.en.html

## 10. Relación con A-IPC-04 y listener-quiescence/1

A-IPC-04/SR-01..SR-12 valida la enumeración limitada de procesos/network namespaces y la inspección/retirada simulada de un residual fixture. No valida lifecycle systemd, cgroup exclusivo, parada de grupo, puerta de mantenimiento ni ausencia de FD externo.

QP-01..QP-15 cubre la capa previa de quiescencia del proceso/servicio. No reemplaza SR-01..SR-12 ni amplía su alcance procfs. Una futura decisión sobre pathname debe combinar evidencia separada y mantener la secuencia: quiescencia demostrada, inspección exacta del objeto, revisión de actividad dentro del alcance declarado y aprobación humana real. Ningún PASS aislado autoriza unlink.

## 11. Límites del trabajo actual

- R1–R7 fueron aprobadas por el propietario como baseline de diseño.
- El runner QP-01..QP-15 está implementado en `tests/integration/private_unix_listener/run_listener_quiescence_probe.py`; aún no se ha ejecutado ni validado.
- QP-01/QP-02 contienen el predicado para emitir QUIESCENT, condicionado a seccomp, invocación estable, no jobs, cgroup vacío y observaciones correlacionadas; ningún resultado se considera evidencia hasta la ejecución del propietario.
- QP-11 usa un supervisor temporal interno al harness y una caída simulada; no es un supervisor independiente/productivo. QP-12 demuestra el bypass root de forma intencional. QP-13 usa un holder OTHER mediante SCM_RIGHTS, no socket activation.
- Cleanup bifásico, observers cgroup fijados, verificación de ausencia en `ListUnitsByNames`/`ListJobs`, JSON acotado y validación de identidad de archivos/endpoints están implementados, pendientes de validación.
- No se ejecutaron pruebas, builds, workflows ni probes desde GitHub; no se modificó `main`, `atlas-admin/1`, handler IPC, SQLite ni host.
- Siguiente fase: cerrar la revisión estática, después ejecutar el runner solo en `Atlas-VM-test`. A-THREAT-05 sigue abierta.

## 12. Referencias

- `docs/contracts/local-authority-admin-listener-quiescence-1.md`
- `docs/design/local-authority-admin-listener-lifecycle.md`
- `docs/design/local-authority-admin-private-listener-stale-recovery.md`
- `docs/design/local-authority-admin-private-listener-stale-recovery-probe.md`
- `docs/status-current.md`
- `docs/PROJECT_CONTEXT.md`
