# Plan de probe aislado A-IPC-04 — socket residual y recuperación fail-closed

**Fecha:** 2026-11-21  
**Estado:** plan de diseño; runner no implementado ni ejecutado. Requiere revisión estática antes de codificar. No autoriza herramienta de mantenimiento, listener persistente, limpieza automática ni cambios del host.  
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
| SR-03 | Namespace adicional con listener activo para el mismo pathname | Detectarlo y abortar; integración real puede ser SKIP solo si el kernel/VM no permite crear namespace, nunca reportar PASS de cobertura multi-namespace |
| SR-04 | Una tabla de namespace requerida no se puede leer | Abort fail-closed; objeto intacto |
| SR-05 | Enumeración PID/namespace incompleta o carrera no resuelta | Abort fail-closed |
| SR-06 | Tabla procfs malformada, truncada o con registro ambiguo | Abort fail-closed |
| SR-07 | Pathname exacto activo frente a prefijos/sufijos similares | Solo coincidencia exacta bloquea; no aceptar parsing ambiguo |
| SR-08 | Entrada final symlink, regular, FIFO, directorio o socket con tipo/owner/mode incorrectos | Abort; bytes/inode del objeto intactos |
| SR-09 | Sustitución del objeto entre inspección y revalidación | Detectar device/inode/type/owner/mode distinto; no unlink |
| SR-10 | Residual fixture con identidad exacta y token de aprobación ligado a metadata | Retirar solo ese objeto mediante parent dirfd y verificar ausencia |
| SR-11 | Socket activo en namespace del inspector | No se llama connect/accept/send/recv; descriptor listener se cierra en cleanup |
| SR-12 | Cualquier fallo/timeout/cleanup inesperado | Resultado global INCOMPLETE/FAIL, nunca PASS por omisión; sandbox cleanup acotado y auditado |

SR-03 debe reportarse por separado de la cobertura determinista del parser. Si no se puede crear un segundo network namespace en la VM, el escenario real multi-namespace queda SKIP y la evidencia global no puede afirmar que esa parte fue validada.

## 6. Modelo de resultado y evidencia

JSON debe registrar como mínimo:

- commit exacto del checkout, kernel, Python, EUID, IDs fixture, duración y cleanup;
- lista/identidad de namespaces descubiertos e inspeccionados, y representative PID por namespace (sin exponer datos ajenos innecesarios);
- conteos de procesos vistos, namespaces deduplicados, tablas leídas y errores de enumeración;
- pathname fixture, tipo de socket, resultado de matching y decisión (ACTIVE/ABORT/ELIGIBLE/REMOVED);
- metadata filesystem observada y metadata revalidada (device, inode, type, UID/GID, mode);
- si se invocó connect/send/recv (debe ser false en todos los escenarios);
- token de aprobación de fixture aplicado o ausente, sin aceptar ni registrar secretos;
- por escenario PASS/FAIL/SKIP y razón explícita.

Reglas globales:
- cualquier escenario obligatorio omitido, namespace coverage incierta o cleanup no confirmado impide `overall=PASS`;
- SR-03 real multi-namespace en SKIP limita la conclusión: puede haber PASS de las pruebas deterministas restantes, pero overall debe ser `INCOMPLETE`;
- el runner nunca realiza operaciones fuera de su sandbox.

## 7. Preguntas que deben cerrarse antes de implementar

1. ¿Qué errores de `/proc` son carreras reintentables por desaparición de PID y cuáles obligan a abort inmediato?
2. ¿Cómo se demuestra la cobertura del conjunto de procesos/namespaces visible bajo el montaje procfs de la VM, y qué limitación se documenta si hay hidepid/PID namespace?
3. ¿Qué parser exacto del formato `/proc/<pid>/net/unix` se valida en Debian 13/kernel 6.12.117?
4. ¿La creación de un segundo network namespace está permitida en la VM? Si no, SR-03 debe permanecer SKIP e impedir una conclusión global completa.
5. ¿Cómo se vincula el token de aprobación de fixture a una sola identidad observada sin crear una herramienta de mantenimiento reutilizable?

No comenzar el runner hasta revisar estas preguntas y el alcance de los resultados.

## 8. No objetivos

- No implementar recuperación automática al iniciar el servicio.
- No decidir ni aprobar una ruta real de endpoint.
- No crear listener persistente, cliente IPC, daemon o unidad systemd.
- No ejecutar cleanup en el host ni en sockets Atlas reales.
- No resolver lifecycle A-THREAT-08 ni la política de deployment A-THREAT-09.
- No convertir ausencia de registro en procfs en prueba absoluta de que ningún proceso externo conserva una referencia.
