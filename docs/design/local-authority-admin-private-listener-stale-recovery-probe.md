# Plan de probe aislado A-IPC-04 — socket residual y recuperación fail-closed

**Fecha:** 2026-11-21  
**Estado:** A-IPC-04 sigue sin validación (última ejecución completa comunicada: 10 PASS / 2 FAIL). Una comparación controlada confirmó lecturas parciales causadas por buffering=0 y una sola llamada read(); el runner se corrigió para acumular lecturas acotadas. La corrección y sus pruebas unitarias quedan pendientes de ejecución por el propietario en Atlas-VM-test. No es herramienta de mantenimiento ni autoriza listener persistente, limpieza automática o cambios del host.  
**Rama:** `experiment/a-ipc-01-private-unix-listener-probe`  
**Dependencias:** A-IPC-03 validado; `local-authority-admin-private-listener-stale-recovery.md`; `local-authority-admin-private-listener-path-resolution.md`; TCB-1.

## 1. Objetivo

Convertir A-THREAT-05 en evidencia experimental de que una decisión de recuperación de pathname AF_UNIX falla cerrada: si hay evidencia de socket activo en cualquier network namespace visible, si no se puede completar la inspección, si la entrada no coincide con la política o si cambia su identidad, no se retira el objeto.

El probe separa tres conceptos que no deben confundirse:

1. **Inspección:** inventariar tablas AF_UNIX de los network namespaces visibles y clasificar un pathname exacto como ocupado/posiblemente activo o sin registro observado.
2. **Elegibilidad:** validar el objeto filesystem mediante el descriptor del directorio padre y comparar tipo, UID/GID, modo, dispositivo e inode con una identidad esperada.
3. **Retirada simulada y explícitamente aprobada:** demostrar en un sandbox temporal que solo el socket residual exacto puede retirarse tras una confirmación vinculada a su identidad observada. No implementar una utilidad general de mantenimiento.

La ausencia de una entrada en las tablas inspeccionadas no prueba por sí sola que el socket sea stale si la enumeración de namespaces/procesos está incompleta. Cualquier duda produce ABORT.

## 2. Límites de seguridad y aislamiento

- Runner independiente: `tests/integration/private_unix_listener/run_stale_recovery_probe.py`.
- Ejecución directa como EUID 0 únicamente en la VM desechable `Atlas-VM-test`; no usar `greed` producción.
- Un único sandbox aleatorio root:root 0700 bajo `/run`; todos los sockets y archivos de prueba viven dentro.
- No leer ni modificar rutas Atlas reales, no acceder a `/etc/atlas`, no inspeccionar servicios reales ni consultar unidades systemd.
- No conectar a ningún socket para inferir liveness. La única operación de red local es `bind()` de sockets fixture dentro del sandbox; no se acepta ni intercambia tráfico.
- No crear usuarios/grupos, cambiar cuentas, permisos del host, servicios, unidades, SQLite ni configuración del sistema.
- Enumeración de namespaces limitada a la vista procfs disponible para el proceso. El runner debe registrar el alcance y fallar cerrado si no puede demostrar que enumeró completamente los procesos/namespaces visibles según el contrato del probe.
- Nunca ejecutar `unlink` sobre una ruta recibida externamente ni usar `rm`, globbing, recursión o limpieza genérica.
- Cleanup del propio sandbox solo después de cerrar todos los sockets y terminar los hijos; validar su identidad inode antes de retirarlo.

## 3. Contrato de inspección de namespaces

El inspector debe:

1. Enumerar entradas PID numéricas bajo `/proc`, sin seguir rutas arbitrarias.
2. Para cada PID visible, obtener identidad de `/proc/<pid>/ns/net` y deduplicar namespaces por identidad de namespace (device/inode del enlace/descriptor según la API usada).
3. Leer una vez la tabla `/proc/<representative-pid>/net/unix` por cada namespace deduplicado; incluir el namespace del propio inspector.
4. Tratar un registro con pathname canónico exacto como evidencia de ocupado/posiblemente activo, sin intentar inferir stale a partir del campo state.
5. Abort si no puede enumerar /proc, resolver un namespace visible o leer/parsear una tabla requerida. Una carrera por proceso que desaparece puede reintentarse con límite y una nueva enumeración; si la cobertura sigue incierta, abort.
6. Comparar el pathname exacto y el tipo esperado SOCK_SEQPACKET (valor Linux mostrado por procfs según el formato observado). El parser debe rechazar líneas ambiguas/truncadas o campos inesperados; no usar coincidencias parciales.
7. No tratar el inode de `/proc/net/unix` como el inode de la entrada filesystem: son identificadores distintos y no deben compararse entre sí.

El parser de procfs debe separarse del enumerador real para permitir pruebas deterministas de tabla inaccesible, formato inválido, namespaces duplicados y registros con pathname exacto. El resultado debe incluir qué namespaces fueron inspeccionados, no solo un booleano.

## 4. Contrato de elegibilidad y retirada de fixture

- Resolver el directorio padre mediante el path-walk validado por A-IPC-03, usando descriptor y operaciones relativas.
- Inspeccionar la entrada final sin seguir symlinks. Exigir socket filesystem real, pathname exacto del fixture, UID/GID y modo esperados, y capturar `st_dev`/`st_ino`.
- Si la tabla de cualquier namespace contiene el pathname, clasificar como `ABORT_ACTIVE_OR_POSSIBLY_ACTIVE`.
- Si la enumeración/lectura/parsing de namespaces no es completa, clasificar como `ABORT_INCOMPLETE_NAMESPACE_COVERAGE`.
- Si el objeto no es socket o owner/mode/path no coincide, abortar sin cambiarlo.
- Simular la confirmación humana con un token de fixture que incluya pathname y metadata observada; no crear una interfaz de aprobación ni aceptar un booleano genérico desligado de esa identidad.
- Inmediatamente antes de retirar, repetir `fstatat`/equivalente relativo al mismo parent dirfd y comparar tipo, device, inode, UID/GID y modo. Cualquier diferencia produce abort y conserva el objeto.
- Solo el escenario de socket residual del sandbox puede ejecutar `unlinkat` relativo al descriptor. Confirmar ausencia por el mismo descriptor.
- La ventana entre revalidación y unlink no es atómica. El probe no elimina el residual aceptado A-THREAT-04 ni protege frente a root/procesos dentro de TCB-1.

## 5. Escenarios obligatorios propuestos

| ID | Escenario | Resultado requerido |
|---|---|---|
| SR-01 | Listener SOCK_SEQPACKET fixture activo en el namespace actual | Path exacto detectado; abort sin unlink ni connect |
| SR-02 | Socket fixture cerrado que deja pathname residual y no aparece en tabla completa | Elegibilidad únicamente; no retirar sin token de aprobación específico |
| SR-03 | Namespace adicional con listener activo para el mismo pathname | Detectarlo y abortar; si no se puede crear el namespace, reportar INCOMPLETE y nunca PASS de cobertura multi-namespace |
| SR-04 | Una tabla de namespace requerida no se puede leer | Abort fail-closed; objeto intacto |
| SR-05 | Enumeración PID/namespace incompleta o carrera no resuelta | Abort fail-closed |
| SR-06 | Tabla procfs malformada, truncada o con registro ambiguo | Abort fail-closed |
| SR-07 | Pathname exacto activo frente a prefijos/sufijos similares | Solo coincidencia exacta bloquea; no aceptar parsing ambiguo |
| SR-08 | Entrada final symlink, regular, FIFO, directorio o socket con tipo/owner/mode incorrectos | Abort; bytes/inode del objeto intactos |
| SR-09 | Sustitución del objeto entre inspección y revalidación | Detectar device/inode/type/owner/mode distinto; no unlink |
| SR-10 | Residual fixture con identidad exacta y token de aprobación ligado a metadata | Retirar solo ese objeto mediante parent dirfd y verificar ausencia |
| SR-11 | Socket activo en namespace del inspector | No se llama connect/accept/send/recv; descriptor listener se cierra en cleanup |
| SR-12 | Cualquier fallo/timeout/cleanup inesperado | Resultado global INCOMPLETE/FAIL, nunca PASS por omisión; sandbox cleanup acotado y auditado |

SR-03 se ejecuta realmente con unshare --net y un listener fixture en un namespace distinto; el proceso padre inspecciona el pathname exacto sin conectarse. Si la creación del namespace no está permitida, SR-03 queda INCOMPLETE y el resultado global no puede ser PASS.

## 6. Modelo de resultado y evidencia

JSON debe registrar como mínimo:

- commit exacto del checkout, kernel, Python, EUID, IDs fixture, duración y cleanup;
- inventario inicial de namespaces descubiertos, identidad device/inode, PID representativo y conteo de registros; SR-03 registra además el namespace adicional real;
- conteo de procesos vistos, namespaces deduplicados y tablas leídas; los errores de enumeración/lectura/parsing se reflejan como INCOMPLETE o FAIL por escenario;
- pathname fixture, tipo de socket, resultado de matching y decisión (ACTIVE/ABORT/ELIGIBLE/REMOVED);
- metadata filesystem observada y metadata revalidada (device, inode, type, UID/GID, mode);
- si se invocó connect/send/recv (debe ser false en todos los escenarios);
- token de aprobación de fixture aplicado o ausente, sin aceptar ni registrar secretos;
- por escenario PASS/FAIL/SKIP y razón explícita.

Reglas globales:
- cualquier escenario obligatorio omitido, namespace coverage incierta o cleanup no confirmado impide `overall=PASS`;
- SR-03 real multi-namespace en INCOMPLETE limita la conclusión: puede haber PASS de las pruebas deterministas restantes, pero overall debe ser `INCOMPLETE`;
- el runner nunca realiza operaciones fuera de su sandbox.

## 7. Resolución de las preguntas previas a la implementación

Las decisiones siguientes están incorporadas en el runner. Son decisiones del harness experimental, no una política productiva aprobada.

1. **Carreras de PID:** ENOENT, ESRCH y ENOTDIR al inspeccionar un PID se tratan como desaparición/carrera y provocan un reintento completo, limitado a tres intentos. Si la vista PID/namespace cambia entre snapshots, también se reintenta. Si persiste, se aborta. EACCES, EPERM, errores de lectura, procfs no disponible y errores de parsing abortan inmediatamente como cobertura incompleta.
2. **Alcance de procfs:** el runner identifica el montaje /proc, rechaza hidepid, compara el PID namespace del inspector con el de PID 1 y enumera todos los PID numéricos visibles. El alcance declarado es exclusivamente la vista accesible desde ese montaje/PID namespace; no se afirma cobertura host-wide ni visibilidad de namespaces sin procesos visibles. La enumeración se compara en tres snapshots estables, pero no es una operación atómica frente a creación concurrente de procesos. El procedimiento de mantenimiento requiere una ventana controlada y autoridad confiable para evitar esa carrera.
3. **Parser:** exige el encabezado exacto Num RefCount Protocol Flags Type St Inode Path; acepta filas con siete campos (sin pathname) u ocho (pathname preservado como último campo), valida el primer campo hexadecimal `Num` con su sufijo obligatorio `:`, los otros cinco campos hexadecimales y el inode decimal. SR-06 incluye una fila realista con ese delimitador y casos que lo omiten o duplican. Solo Type=0005 (SOCK_SEQPACKET) y pathname exacto bloquean. No compara el inode de procfs con el inode filesystem. El runner limita cada tabla a 4 MiB y debe acumular lecturas cortas hasta EOF o hasta el byte adicional que permite detectar exceso; una única lectura no buffered no garantiza entregar el contenido completo.
4. **Segundo network namespace:** la VM permitió unshare --net true y el propietario confirmó una tabla AF_UNIX visible solo en el namespace del listener. SR-03 ahora crea un listener fixture real en un namespace adicional y exige detectarlo desde el inventario procfs del proceso padre. La ejecución del runner sigue pendiente.
5. **Token de aprobación:** SR-10 usa un dataclass inmutable de fixture ligado al pathname y a st_dev, st_ino, tipo, UID, GID y modo observados. El challenge es una constante exclusiva del escenario. No es aprobación humana real, no es una API reutilizable y no autoriza mantenimiento fuera del sandbox.

El runner está implementado y revisado estáticamente; no se ejecutó desde GitHub. El parser refleja el formato Linux de `/proc/net/unix`: el primer campo `Num` termina en `:`. SR-06 acepta una fila realista y rechaza delimitadores ausentes o duplicados. Si falla el inventario inicial, los contadores quedan `null` en vez de aparentar cero procesos o namespaces. La identidad de cada namespace se obtiene manteniendo abierto brevemente un descriptor O_PATH y leyendo su enlace /proc/self/fd; el PID representativo se comprueba antes y después de leer su tabla para detectar cambios de namespace durante la lectura. SR-10 también demuestra que un token con inode distinto se rechaza sin mutar el residual. Las decisiones anteriores deberán revisarse si la ejecución del propietario descubre diferencias del formato procfs o del comportamiento del kernel.

## 8. No objetivos

- No implementar recuperación automática al iniciar el servicio.
- No decidir ni aprobar una ruta real de endpoint.
- No crear listener persistente, cliente IPC, daemon o unidad systemd.
- No ejecutar cleanup en el host ni en sockets Atlas reales.
- No resolver lifecycle A-THREAT-08 ni la política de deployment A-THREAT-09.
- No convertir ausencia de registro en procfs en prueba absoluta de que ningún proceso externo conserva una referencia.


## 9. Primera ejecución del propietario y correcciones (2026-11-21)

El propietario ejecutó el commit `27dd83a34e149901f908356668dc119b4491487f`
en `Atlas-VM-test` (Debian 13, kernel `6.12.117+deb13-amd64`,
Python 3.13.5, EUID 0; SERVICE 2005:2005, OTHER 2006:2006).
Resultado: `overall=FAIL`, 8 PASS, 4 FAIL, 0 INCOMPLETE; el inventario
vio 204 procesos y seis namespaces visibles, y el sandbox se eliminó.

Hallazgos por escenario:

- **SR-01 y SR-11:** no se encontró el pathname de los listeners locales
  activos en las tablas inspeccionadas. No se debe interpretar como ausencia
  de listener ni como socket stale. SR-03 sí encontró el listener real en
  el namespace adicional `net:[4026532290]`.
- **SR-06:** el fixture positivo contenía separadores `\\n` literales en
  vez de saltos de línea reales; por eso el parser recibió una sola línea y
  rechazó la cabecera.
- **SR-07:** sus tres filas de prueba omitían el delimitador obligatorio
  `:` del campo `Num`, por lo que el propio fixture no representaba filas
  válidas del formato Linux.

Correcciones estáticas publicadas en commits `b2767ff6a64886fb361bbf7f8f36a016f90c3e7f`
y `48008ff559b8c4f2528e3668d140797266f38844`:

1. SR-06 usa saltos de línea reales y conserva casos negativos de delimitador
   ausente y duplicado.
2. SR-07 usa el delimitador correcto en sus tres filas positivas; mantiene
   comparación exacta de pathname.
3. SR-01/SR-11 ahora incluyen, solo cuando falla la detección, un conjunto
   acotado de filas candidatas de procfs (namespace, pathname, type e inode)
   para diagnosticar qué nombres expone el kernel. Este diagnóstico no altera
   la decisión ni relaja el requisito de detección.

**Pendiente:** los fallos SR-01/SR-11 no están resueltos; la causa no se puede
determinar con el JSON actual porque no incluía filas candidatas. Se requiere
una nueva ejecución del runner corregido para validar SR-06/SR-07 y obtener
diagnósticos de SR-01/SR-11. A-THREAT-05 permanece abierta; no usar ni
adaptar este mecanismo para recuperación real. No se ejecutaron pruebas,
builds, workflows ni probes desde GitHub.


## 10. Segunda ejecución del propietario y siguiente diagnóstico (2026-11-21)

El propietario ejecutó `bd3b0e0a1379c7b034e10a33b9b45b329e6e807a`
en `Atlas-VM-test`: `overall=FAIL`, 10 PASS, 2 FAIL, 0 INCOMPLETE.
El inventario vio 201 procesos y seis namespaces; el sandbox se eliminó.
SR-06 y SR-07 pasan después de las correcciones de fixtures. SR-03
detectó el listener del namespace adicional. SR-01 y SR-11 siguen
fallando con `candidate_rows=[]`.

La salida no permite determinar por qué los listeners creados localmente
no aparecen en las tablas del snapshot. No es evidencia de inactividad,
no prueba que el pathname sea residual y no permite retirar el objeto.

Commit `a7bf92d07d12012d20822b64a57ee0ab17c953e1` añade, en los errores
SR-01/SR-11, evidencia diagnóstica acotada y no decisoria:

- PID y network namespace del inspector;
- inode del descriptor del socket fixture;
- identidades de namespaces incluidos en el snapshot;
- filas candidatas del snapshot por pathname o inode del socket;
- lectura directa de `/proc/self/net/unix` y filas por pathname/inode;
- error explícito si esa lectura directa no puede completarse.

La comprobación directa sirve para distinguir entre una omisión del
inventario de namespaces y una diferencia entre la tabla leída vía
representante y la tabla del proceso que creó el listener. No altera
la regla de detección ni realiza connect/accept/send/recv.

**Pendiente:** ejecutar el HEAD actual solo en `Atlas-VM-test` y revisar
el JSON completo. A-THREAT-05 sigue abierta. No usar el procedimiento
en hosts reales ni permitir limpieza automática.

## Registro de tercera ejecución — 2026-11-21

El propietario ejecutó el runner en commit `f10cda09aec5cb0b9d42ab50f3bb9f6617dc8fda`: 10 PASS / 2 FAIL / 0 INCOMPLETE; 203 procesos visibles; seis namespaces en el inventario inicial; siete durante SR-03; sandbox eliminado.

### SR-01 — observación adicional

El listener fixture seguía abierto y su descriptor tenía inode `39340`. El inspector estaba en `net:[4026531840]`, identidad incluida en el snapshot. No se encontró ninguna fila candidata en el conjunto de tablas ni en la lectura directa de `/proc/self/net/unix`; esta lectura no produjo error. Por tanto, la discrepancia ya no puede atribuirse solamente a la elección del PID representante. El resultado no demuestra que el listener esté inactivo ni permite clasificar el pathname como stale. Mantener SR-01 FAIL y no relajar el criterio de detección.

### SR-11 — defecto del harness

El escenario llamó a `_listener_diagnostics(snapshot, path)` aunque la función requiere también el socket `listener`; terminó con `TypeError` antes de producir diagnóstico. Commit `8a89bc9f66829886164ed4fe93fd7af232a18f01` corrige la llamada. La corrección requiere reejecución del propietario.

SR-02..SR-10 y SR-12 pasaron, incluido SR-03 para namespace adicional, abortos ante cobertura incompleta y token ligado a identidad. No se llamó connect/accept/send/recv como prueba de liveness. A-IPC-04 continúa no validado; A-THREAT-05 abierta. El probe no es herramienta de mantenimiento ni autoriza cleanup automático o despliegue.

## A-IPC-04 — cuarta ejecución del propietario y diagnóstico ampliado (2026-11-21)

El propietario ejecutó `e46070e6e1824b06af04a3627feb0f658de9c1f8` en `Atlas-VM-test`: **10 PASS / 2 FAIL / 0 INCOMPLETE**; 204 procesos visibles; seis namespaces en el inventario inicial y siete durante SR-03; cleanup confirmado.

- SR-01 y SR-11 fallaron ambos porque los listeners locales activos no aparecieron en las tablas visibles. La lectura directa de `/proc/self/net/unix` tampoco encontró filas candidatas ni coincidencias por inode, sin error de lectura. Los inodes de FD fueron `39726` y `40202` respectivamente.
- SR-11 ya no falla por el `TypeError`; produce el mismo fallo sustantivo de detección que SR-01.
- SR-02..SR-10 y SR-12: PASS. SR-03 detectó de nuevo el listener en namespace adicional; los abortos por cobertura incompleta y la protección de identidad/token siguen pasando.
- No se llamó connect para probar liveness. El sandbox privado fue eliminado.

La fuente del kernel revisada muestra que la interfaz procfs de AF_UNIX enumera sockets y expone inode/path; la discrepancia requiere diagnóstico adicional, no una relajación del matching. Commit `a3e2d3dcb24842c4ae842f1d8082b4a2dbade374` amplía los diagnósticos de SR-01/SR-11 con FD target, `getsockname()`, `SO_TYPE`, `SO_ACCEPTCONN`, recuento y filas completas (acotadas a 64) de la tabla local. Es un cambio de diagnóstico, no ejecutado aún por el propietario.

**Estado:** A-IPC-04 no validado; A-THREAT-05 abierta. La ausencia de filas no clasifica un socket como stale y no autoriza unlink. Repetir solo en `Atlas-VM-test`, nunca en `greed`. Sin limpieza automática, listener persistente ni despliegue.


## Quinta ejecución del propietario — diagnóstico de listener local (2026-11-21)

Checkout: `6f77960c25fba873be67bd29fb40814619e44ee8`, VM desechable
`Atlas-VM-test`, Debian 13, kernel `6.12.117+deb13-amd64`,
Python 3.13.5, EUID 0. Resultado: **10 PASS / 2 FAIL / 0 INCOMPLETE**;
203 procesos visibles; seis namespaces en inventario inicial; duración
0.161 s; cleanup confirmado.

La nueva evidencia de SR-01 y SR-11 descarta que el fixture simplemente
haya fallado al enlazar o entrar en listen:
- `getsockname()` devolvió la ruta esperada en cada escenario.
- `SO_TYPE=5` y `SO_ACCEPTCONN=true`.
- `/proc/self/fd/3` apuntó a `socket:[41168]` (SR-01) y
  `socket:[41184]` (SR-11).
- La lectura directa de `/proc/self/net/unix` se completó sin error y
  devolvió 58 registros, pero no incluyó el pathname, los inodes ni filas
  candidatas de ninguno de los listeners. El namespace del inspector
  `net:[4026531840]` estaba incluido en el snapshot.
- SR-03 volvió a detectar desde el proceso padre el listener del namespace
  adicional `net:[4026532290]`, PID 6051.

Por tanto SR-01/SR-11 siguen siendo fallos sustantivos de observabilidad
procfs, no fallos de creación/listen ni una demostración de inactividad.
SR-02..SR-10 y SR-12 pasaron. No se usó connect/accept/send/recv para
comprobar liveness y el sandbox se eliminó.

**Próxima investigación:** aislar por qué el kernel expone otros sockets
AF_UNIX en la tabla local, pero no estos sockets SOCK_SEQPACKET que el mismo
proceso confirma como enlazados y escuchando. Revisar el camino de creación/
registro y la semántica de enumeración procfs para la versión exacta del
kernel Debian 6.12.117; añadir, si procede, una prueba diagnóstica mínima
que registre el comportamiento sin debilitar el matching ni la clasificación.
No cambiar a comparación solo por inode, no tratar una tabla sin coincidencia
como prueba de stale y no ejecutar unlink.

**Estado:** A-IPC-04 no validado; A-THREAT-05 abierta. No usar en sockets
reales ni en `greed`; no habilitar cleanup automático, listener persistente
o despliegue. Resultado aportado y ejecutado por el propietario; el asistente
no ejecutó pruebas, builds, workflows ni probes.


### Comparación manual STREAM/SEQPACKET posterior a la quinta ejecución (2026-11-21)

El propietario creó en un mismo proceso dos listeners temporales AF_UNIX:
STREAM (tipo 1, FD inode 40634) y SEQPACKET (tipo 5, FD inode 40638).
Ambos devolvieron pathname esperado y SO_ACCEPTCONN=1. Los filtros
por pathname en /proc/self/net/unix y ss -xl no devolvieron filas para
ninguno. La observación no parece exclusiva de SOCK_SEQPACKET.

La salida filtrada no demuestra que las tablas completas estén vacías
ni identifica la causa. Próximo diagnóstico: obtener ambas salidas
completas mientras los sockets sigan abiertos y registrar
/proc/self/ns/net del proceso creador. No relajar matching, no inferir
stale y no ejecutar unlink. A-IPC-04 sigue no validado y A-THREAT-05 abierta.


## 11. Quinta investigación — lectura parcial de procfs y corrección (2026-11-21)

El propietario aisló las funciones del runner en Atlas-VM-test y confirmó que _fixture_listener() crea correctamente un listener AF_UNIX/SOCK_SEQPACKET. La discrepancia estaba en el lector de tablas:

- _read_table() abría /proc/<pid>/net/unix con buffering=0 y realizaba una sola llamada read(4 MiB + 1).
- La lectura diagnóstica directa de /proc/self/net/unix repetía el mismo patrón.
- En una comparación con el listener todavía abierto, el lector de una sola llamada devolvió **4.048 bytes / 58 registros** y no encontró el socket.
- La lectura buffered completa devolvió **51.172 bytes / 711 registros** e incluyó el pathname esperado, Type 0005, estado 01 e inode de socket 41747.

Esto confirma un defecto de lectura parcial: el código trataba una lectura corta como EOF y analizaba una tabla incompleta. No era un problema de selección del PID representante, matching exacto ni creación/listen del fixture.

### Corrección aplicada en la rama

- Se añadió _read_bounded(stream, limit), que acumula bloques de hasta 64 KiB, continúa tras lecturas cortas y termina en EOF o al alcanzar el límite.
- _read_table() ahora abre el archivo con buffering normal y utiliza el lector acotado con límite de 4 MiB + 1 byte. El byte adicional permite al llamador detectar y rechazar tablas mayores de 4 MiB.
- La lectura diagnóstica de /proc/self/net/unix usa el mismo helper; ya no existe una segunda lectura única sin buffering.
- Se añadió tests/unit/test_private_listener_procfs_read.py para lecturas cortas sucesivas, límite de bytes, EOF y límite negativo.

**Validación pendiente:** el asistente no ejecutó tests, builds, workflows ni probes. El propietario debe ejecutar primero la nueva prueba unitaria y después el runner completo en Atlas-VM-test. Hasta recibir esos resultados, SR-01/SR-11 no se marcan PASS; A-IPC-04 no está validado y A-THREAT-05 permanece abierta.

La corrección no cambia el parser, el matching por pathname exacto y Type=SOCK_SEQPACKET, la cobertura de namespaces, las reglas fail-closed ni la política de no hacer cleanup automático. La ausencia de coincidencia nunca autoriza unlink. No ejecutar en greed, no usar el runner como herramienta de mantenimiento y no habilitar listener persistente ni despliegue.

## A-IPC-04 — sexta ejecución del propietario: validación completa (2026-11-21)

El propietario ejecutó el runner en Atlas-VM-test sobre el commit
375fb00a3fee230a57f89ffa7897a29309ff1dd2: Debian 13, kernel
6.12.117+deb13-amd64, Python 3.13.5, EUID 0, fixtures SERVICE
2005:2005 / OTHER 2006:2006. Resultado: **overall=PASS, 12/12
escenarios PASS, 0 FAIL y 0 INCOMPLETE**; 204 procesos visibles, seis
namespaces inventariados inicialmente, cero reintentos de snapshot y
cleanup confirmado del sandbox privado bajo /run.

- **SR-01:** listener local activo detectado en net:[4026531840];
  decisión ABORT_ACTIVE_OR_POSSIBLY_ACTIVE, sin connect.
- **SR-02:** residual elegible, pero no retirado sin token de aprobación;
  pathname preservado.
- **SR-03:** listener activo detectado en namespace adicional
  net:[4026532290], sin connect.
- **SR-04/SR-05:** cobertura incompleta produce abort y no muta el objeto.
- **SR-06/SR-07:** parser y matching exacto PASS; una coincidencia exacta.
- **SR-08/SR-09:** objetos no admisibles y sustitución de identidad
  rechazados; reemplazo preservado.
- **SR-10:** solo se retiró el fixture exacto con token ligado a identidad;
  token incompatible rechazado sin mutación.
- **SR-11:** listener local activo detectado; no se llamaron accept, connect,
  recv ni send.
- **SR-12:** fallos de escenario/cleanup no pueden convertirse en PASS.

El inventario inicial informó 710 registros para el namespace principal
y entre 2 y 3 para los namespaces restantes. liveness_connect_called=false;
cleanup reportó que los procesos y sockets se cerraron antes de eliminar
el sandbox.

**Conclusión:** la corrección de lectura acotada de procfs resolvió la causa
confirmada de SR-01/SR-11. A-IPC-04 queda validado para los 12 escenarios
del harness, en el commit, kernel, VM y vista procfs indicados. La validación
no demuestra cobertura fuera de los procesos/namespaces visibles desde ese
montaje procfs/PID namespace, ni elimina carreras ante creación concurrente
de procesos o el límite TOCTOU entre revalidación y unlink.

**Límites que permanecen:** A-THREAT-05 no queda cerrada por esta prueba;
no se aprueba recuperación de sockets reales, cleanup automático, listener
persistente, activación systemd ni despliegue. El mecanismo sigue siendo
un probe experimental aislado. El asistente no ejecutó pruebas, builds,
workflows ni probes.