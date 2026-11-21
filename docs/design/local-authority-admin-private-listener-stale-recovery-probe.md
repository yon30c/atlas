# Plan de probe aislado A-IPC-04 — socket residual y recuperación fail-closed

**Fecha:** 2026-11-21  
**Estado:** primera ejecución del propietario en Atlas-VM-test: 8 PASS / 4 FAIL. Se corrigieron dos fixtures de parser y se añadieron diagnósticos acotados para SR-01/SR-11; requiere nueva ejecución. No es herramienta de mantenimiento ni autoriza listener persistente, limpieza automática o cambios del host.  
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
3. **Parser:** exige el encabezado exacto Num RefCount Protocol Flags Type St Inode Path; acepta filas con siete campos (sin pathname) u ocho (pathname preservado como último campo), valida el primer campo hexadecimal `Num` con su sufijo obligatorio `:`, los otros cinco campos hexadecimales y el inode decimal. SR-06 incluye una fila realista con ese delimitador y casos que lo omiten o duplican. Solo Type=0005 (SOCK_SEQPACKET) y pathname exacto bloquean. No compara el inode de procfs con el inode filesystem. El runner limita cada tabla a 4 MiB.
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
