# Diseño del probe de quiescencia del listener — A-IPC-05 / QP-01..QP-15

**Identificador:** ATLAS-PROBE-LISTENER-QUIESCENCE  
**Versión:** 1.0-draft  
**Estado:** diseño aprobado como siguiente trabajo de especificación; runner no implementado y escenarios no ejecutados.  
**Fecha:** 21 de noviembre de 2026.  
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
- No ejecutar `unlink`, `unlinkat`, `rm` ni limpieza de endpoint. El pathname fixture se conserva hasta cerrar todos los descriptores y el cleanup se limita al sandbox cuya identidad creó el runner.
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
- No hace fork después de bind/listen; el flujo normal del fixture no inicia subprocesses.
- No llama a `dup`/`dup2`/`fcntl(F_DUPFD*)` para replicar el listener ni envía/recibe ancillary data `SCM_RIGHTS`.
- No registra el listener en un supervisor externo ni lo publica en el canal de control.
- Mantiene un registro local de PID, FD, `fstat`, `getsockname`, `SO_TYPE`, `SO_ACCEPTCONN` y `FD_CLOEXEC` solo para la evidencia del fixture. Estos datos no sustituyen la evidencia del system manager/cgroup.
- Cierra el listener durante shutdown normal. El runner no mata ni cierra FDs del proceso mediante procfs como mecanismo de prueba.

### 3.2 Puerta de mantenimiento

El diseño de la puerta debe ser root-managed, exclusiva y mantenerse adquirida desde antes de solicitar stop hasta que se complete la última observación y decisión del escenario. La interfaz concreta (lock de archivo privado, coordinador o mecanismo equivalente) queda como punto de diseño de implementación; debe demostrar:

- exclusión entre dos orquestadores;
- bloqueo de start/restart a través del único punto autorizado de lifecycle;
- rechazo de solicitudes concurrentes y expiración/timeout fail-closed;
- liberación inequívoca al finalizar;
- no depender de que el proceso del servicio coopere para impedir que un actor externo reinicie la unidad.

Si el system manager, timers, dependencias, políticas automáticas o un actor con autoridad equivalente pueden iniciar la unidad sin pasar por la puerta, QP-11 no puede pasar y el contrato no queda demostrado. La puerta no debe presentarse como barrera frente a root malicioso; root pertenece al dominio de autoridad confiable.

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
14. Liberar la puerta y limpiar únicamente recursos del harness, tras verificar su identidad. Nunca retirar el pathname del listener mediante una operación de recuperación.

La secuencia no se sustituye por `sleep`, ausencia del PID principal, `pgrep`, tabla procfs AF_UNIX o una conexión de prueba.

## 5. Matriz de escenarios QP-01..QP-15

| ID | Preparación / estímulo | Evidencia que debe observarse | Resultado obligatorio |
|---|---|---|---|
| **QP-01** | Servicio fixture normal con listener propio en unidad dedicada; solicitar stop completo. | InvocationID/cgroup coherentes; unidad `inactive`; sin jobs start/restart; `populated 0` en dos lecturas correlacionadas; listener cerrado por el proceso. | `QUIESCENT` únicamente tras completar toda la secuencia común. |
| **QP-02** | Crear antes del listener un proceso auxiliar fixture dentro del mismo cgroup; mantenerlo vivo durante la primera observación y luego permitir su terminación por stop. | Antes de terminar el auxiliar, cgroup `populated 1` y no QUIESCENT; tras stop, todos los procesos del cgroup terminan y se observa `populated 0`. | Rechazar quiescencia prematura; después del stop completo puede ser `QUIESCENT`. El auxiliar no recibe el listener FD. |
| **QP-03** | Proceso residual fixture deliberadamente mantenido dentro del cgroup pese al stop/deadline (solo mecanismo controlado de laboratorio). | Unidad aparentemente inactiva o PID principal ausente, pero cgroup sigue `populated 1`; registrar proceso residual sin intentar matarlo por fuera del supervisor. | `ABORT_NOT_QUIESCENT`; preservar pathname y sandbox hasta cleanup controlado del fixture. |
| **QP-04** | Unidad en estado de transición o con job start/restart pendiente durante la ventana de observación. | Propiedades del manager muestran transición/job no terminal; la puerta debe impedir que el propio harness emita start concurrente. | `ABORT_NOT_QUIESCENT`; no inferir quiescencia aunque `populated 0` en una lectura aislada. |
| **QP-05** | Configurar el fixture para compartir cgroup con una unidad/proceso no perteneciente al servicio, o hacer que ControlGroup no sea el cgroup exclusivo esperado. | ControlGroup inesperado/compartido o identidad de cgroup no coincide con la unidad fixture dedicada. | `ABORT_NOT_QUIESCENT` antes de cualquier decisión sobre pathname; no detener el proceso ajeno. |
| **QP-06** | Presentar configuración fixture con delegación habilitada o evidencia de que el servicio puede migrar procesos fuera del cgroup. | Propiedad `Delegate`/configuración del manager y comprobaciones de jerarquía muestran delegación o capacidad de escape. | `ABORT_NOT_QUIESCENT`; no usar `populated 0` como prueba de ausencia de procesos/FDS externos. |
| **QP-07** | Simular lectura parcial, error de permisos, contenido malformado, clave duplicada/ausente o filesystem cgroup no esperado para `cgroup.events`. | Recolector identifica exactamente el error y conserva bytes/estado disponible sin normalizarlo como cero. | `ABORT_NOT_QUIESCENT`; nunca interpretar fallo de lectura como `populated 0`. |
| **QP-08** | El fixture intenta crear un proceso hijo después de bind/listen. | La política del fixture rechaza el intento antes de crear el hijo; evidencia de que no ocurrió fork y el listener no se heredó. | PASS del escenario solo si el fork está efectivamente prohibido por diseño/guardia. Si el hijo llega a crearse, FAIL del escenario aunque permanezca dentro del cgroup. |
| **QP-09** | Intentar enviar o recibir el listener FD por `SCM_RIGHTS` en el canal fixture. | Operación prohibida por la interfaz/política del fixture; no se entrega descriptor y el receptor no obtiene un FD que refiera al listener. | PASS solo si no se produce transferencia. Cualquier transferencia observada es FAIL y bloquea QUIESCENT. |
| **QP-10** | Intentar `exec` desde el proceso fixture con listener abierto, usando un helper de prueba que no transporta datos. | La política de no-fork impide el camino normal; en el subtest de descriptor, `FD_CLOEXEC` está activo y el nuevo programa no conserva el listener FD. | PASS solo si no hay herencia a través de exec. Este escenario no convierte CLOEXEC en defensa frente a fork. |
| **QP-11** | Mientras una instancia está en mantenimiento/stop, un segundo actor fixture solicita start/restart a través de la interfaz autorizada. | Puerta exclusiva rechaza/bloquea la solicitud; unidad no vuelve a activarse; lock permanece poseído hasta finalizar la decisión. | PASS si la solicitud no produce job ni nueva InvocationID. Si existe un canal de arranque que elude la puerta, INCOMPLETE/FAIL. |
| **QP-12** | Sustituir/reiniciar la unidad fixture entre snapshots mediante el controlador de laboratorio, sin tocar unidades ajenas. | InvocationID, ControlGroup o identidad de instancia difieren entre snapshots. | `ABORT_NOT_QUIESCENT`; no combinar evidencia de dos invocaciones. |
| **QP-13** | Caso de control negativo que modela retención externa del listener FD fuera del cgroup de servicio. No usar una unidad .socket real ni activar socket activation. | El cgroup del servicio puede estar vacío mientras un proceso externo fixture retiene una referencia; el registro de política/FD ownership detecta que la invariante Q-05/Q-06 no se cumple. | Nunca declarar `QUIESCENT`. Documentar expresamente que systemd socket activation permanece fuera de alcance y no se ha validado. |
| **QP-14** | Forzar fallo del supervisor, desconexión del manager o timeout durante stop/consulta. | Error/timeout identificable; falta una o más observaciones obligatorias; no se emite estado terminal positivo. | `ABORT_NOT_QUIESCENT` o `INCOMPLETE`; pathname preservado y sin operación de retirada. |
| **QP-15** | Cambiar la identidad/ruta del cgroup fixture o sustituir la instancia entre la lectura inicial y la verificación final. | Desacuerdo entre InvocationID/ControlGroup/identidad cgroup; relectura final no corresponde al snapshot inicial. | `ABORT_NOT_QUIESCENT`; no avanzar a inspección/retirada del pathname. |

### 5.1 Criterios de conteo

- Los quince escenarios son obligatorios; un escenario no ejecutado no se considera PASS.
- QP-01 y QP-02 deben demostrar el camino positivo y la terminación del cgroup.
- QP-03..QP-07 y QP-12..QP-15 deben demostrar abortos fail-closed.
- QP-08..QP-10 deben demostrar las invariantes de descriptor, no solo inspeccionar flags.
- QP-11 debe probar la exclusión de lifecycle durante toda la ventana de mantenimiento.
- QP-13 es una prueba negativa del supuesto de FD externo; no es una prueba de socket activation.
- No se permite que un escenario mutile ni retire el pathname del listener. Cualquier intento de unlink hace que el probe completo falle.

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
- bandera constante `pathname_mutation_performed=false`;
- bandera constante `systemd_socket_activation_tested=false`.

No registrar `QUIESCENT` si falta una lectura, si hay discrepancia entre manager/cgroup, si la puerta no está demostrada o si la política de FD no puede verificarse.

## 7. Reglas de fallo y cleanup

- Todo error, timeout, excepción, respuesta ambigua o evidencia incompleta produce FAIL/INCOMPLETE; nunca se convierte en cero procesos, `populated 0` ni PASS por defecto.
- No matar procesos ajenos ni corregir manualmente un cgroup inesperado.
- Si un fixture queda vivo, la limpieza solo puede dirigirse a la unidad transitoria identificada por nombre aleatorio e InvocationID capturados por el propio runner. Si la identidad no coincide, detener la limpieza y reportar INCOMPLETE.
- No borrar el pathname del listener mediante unlink. El fixture debe cerrar su FD y el cleanup del sandbox solo se permite después de verificar que todos los procesos fixture terminaron y que el directorio/sandbox conserva la identidad creada.
- Si cleanup no puede completarse de forma inequívoca, conservar evidencia y declarar INCOMPLETE; no ejecutar limpieza recursiva genérica.
- La puerta se libera al final de una ruta de salida controlada; si el proceso orquestador cae, el diseño de la puerta debe tener una política de recuperación auditada que no permita start/restart durante una decisión inconclusa.

## 8. Interpretación de resultados

Un `overall=PASS` significará únicamente que QP-01..QP-15 del harness se comportaron como se especifica en el commit, VM, versión de systemd/kernel y configuración registrados.

No demuestra:
- resistencia frente a root malicioso, capacidades equivalentes ni procesos comprometidos dentro de TCB-1;
- cobertura global de FDs de todo el host por inspección procfs;
- atomicidad entre snapshots ni ausencia de carreras fuera de la puerta;
- seguridad de socket activation;
- que una unidad/servicio Atlas real exista o esté correctamente configurado;
- que el pathname sea stale o que sea seguro retirarlo;
- que el residual TOCTOU de `unlinkat` haya desaparecido.

A-THREAT-05 seguirá abierta después de un PASS hasta satisfacer todos los criterios del contrato base, incluida una autorización humana real para cualquier retirada futura y una decisión explícita sobre TOCTOU.

## 9. Dependencias y puntos que deben resolverse antes de implementar

1. Seleccionar la interfaz exacta para consultar systemd (D-Bus/systemctl) y documentar cómo se obtienen InvocationID, ControlGroup, jobs y propiedades sin parseo ambiguo.
2. Definir el mecanismo root-managed de la puerta y demostrar que todos los caminos autorizados de start/restart pasan por ella.
3. Fijar el formato y límites del reporte JSON, incluyendo timestamps monotónicos y captura íntegra acotada de `cgroup.events`.
4. Determinar la preparación no mutante de la VM: versión systemd/cgroup v2, herramientas disponibles y fixtures de identidad. Si falta una precondición, el runner debe detenerse; no instalar/crear automáticamente recursos persistentes.
5. Definir cómo probar de forma determinista QP-05/QP-06/QP-08/QP-09/QP-10/QP-12/QP-13/QP-15 sin modificar unidades ajenas, escapar descriptores ni dejar procesos residuales.
6. Revisar que el uso de unidades transitorias y cleanup no contradiga el aislamiento de la VM ni permita que el runner alcance servicios no-fixture.

No implementar hasta que estos puntos se resuelvan en una revisión del diseño del runner. No ejecutar hasta que el propietario solicite expresamente la fase de validación local.

## 10. Relación con A-IPC-04 y listener-quiescence/1

A-IPC-04/SR-01..SR-12 valida la enumeración limitada de procesos/network namespaces y la inspección/retirada simulada de un residual fixture. No valida lifecycle systemd, cgroup exclusivo, parada de grupo, puerta de mantenimiento ni ausencia de FD externo.

QP-01..QP-15 cubre la capa previa de quiescencia del proceso/servicio. No reemplaza SR-01..SR-12 ni amplía su alcance procfs. Una futura decisión sobre pathname debe combinar evidencia separada y mantener la secuencia: quiescencia demostrada, inspección exacta del objeto, revisión de actividad dentro del alcance declarado y aprobación humana real. Ningún PASS aislado autoriza unlink.

## 11. Límites del trabajo actual

- R1–R7 fueron aprobadas por el propietario como baseline de diseño.
- Este documento define escenarios y evidencia, no un runner ejecutable.
- No se creó ninguna unidad, cgroup, usuario, grupo, ruta, servicio ni archivo en el host.
- No se implementó código, fixture ni mecanismo de mantenimiento.
- No se ejecutaron pruebas, builds, workflows ni probes desde GitHub.
- No se modificó `main`, `atlas-admin/1`, el handler IPC, SQLite ni el host.
- La próxima fase, si se autoriza, es cerrar los puntos de diseño de la sección 9; no saltar directamente a implementación.

## 12. Referencias

- `docs/contracts/local-authority-admin-listener-quiescence-1.md`
- `docs/design/local-authority-admin-listener-lifecycle.md`
- `docs/design/local-authority-admin-private-listener-stale-recovery.md`
- `docs/design/local-authority-admin-private-listener-stale-recovery-probe.md`
- `docs/status-current.md`
- `docs/PROJECT_CONTEXT.md`
