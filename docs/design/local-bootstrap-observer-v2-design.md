# Diseño V2 del observador LOCAL de procesos

**Estado:** alcance V2 aprobado por el propietario el 16-11-2026 para implementación de solo observación, sin instalación ni cambios del host. No es un autenticador ni un componente de autorización.  
**Rama:** `feature/terminal-commands`.  
**Relacionado:** `local-bootstrap-validator-v1-design.md`, `local-bootstrap-privilege-validation-contract.md`, `local-bootstrap-privilege-boundary.md`.

## 1. Objetivo

V2 añade un recolector Linux real, no privilegiado por diseño, que toma observaciones acotadas del proceso actual, su padre directo, procfs, pidfd y el TTY controlador cuando existe. Reutiliza los parsers puros y el evaluador V1 sin modificar su semántica.

V2 sirve para comprobar si las observaciones del entorno real son legibles, repetibles y coherentes. No autentica al operador, no demuestra la procedencia de un PTY, no valida una invocación de sudo como confiable y no aprueba el candidato A.

## 2. Límites obligatorios

- Solo lecturas de procfs, apertura de pidfd, consultas TTY y metadatos de ejecutables.
- Sin escritura en archivos, procfs, terminal, configuración o servicios.
- Sin shell-outs, PATH, variables de entorno como fuente de identidad, PAM, sudo API, claves o emisión de proof.
- Sin setuid, file capabilities, instalación, paquetes ni cambios de host.
- Sin SQLite, CAM, Broker, runtime, red ni configuración protegida.
- El programa no solicita privilegios. El operador puede ejecutar manualmente escenarios de diagnóstico ya previstos; la ejecución bajo sudo no transforma el resultado en autorización.
- La ruta textual de `/proc/PID/exe`, nombre, inode y metadatos se muestran solo como observaciones. Ninguno decide por sí solo que el padre sea sudo.
- Un PTY disponible no demuestra si procede de SSH, terminal local o `sudo use_pty`.

## 3. Componentes

- `bootstrap_validator.c/.h`: parsers puros y evaluador V1; permanecen independientes del sistema operativo.
- `bootstrap_observer_linux.c/.h`: adaptador Linux separado. Lee procfs, abre pidfd, inspecciona ejecutables y consulta TTY. Convierte las observaciones en el modelo V1.
- `test_bootstrap_observer_linux.c`: pruebas locales de la interfaz/validación del observador que no requieren privilegios ni cambian el host.

El observador se enlaza con el validador V1; no enlaza ni reutiliza `tools/bootstrap-probe/`.

## 4. Captura de proceso y mitigación de carreras

Para el padre directo:

1. Capturar PID propio y PPID mediante llamadas del proceso.
2. Rechazar PID inválidos o padre igual al proceso actual.
3. Abrir pidfd del padre lo antes posible; si la syscall no está disponible o falla, registrar observación incompleta.
4. Leer `/proc/PID/stat` y `/proc/PID/status` con límites explícitos, acumulando lecturas hasta EOF y detectando exceso.
5. Abrir `/proc/PID/exe` como descriptor de ruta (`O_PATH`) y obtener metadatos con `fstat`; el destino de `readlink` es solo informativo.
6. Repetir las lecturas de status/stat y volver a abrir exe. Comparar PID, starttime, PPID, credenciales, estado, SID, PGID, TTY y metadatos del ejecutable.
7. Comprobar pidfd antes y después. Revalidar que `getppid()` no cambió.
8. Cualquier fallo de lectura, truncamiento, terminación, cambio o imposibilidad de comparar se clasifica como incompleto o inconsistente, nunca consistente.

Estas medidas reducen ventanas de confusión, pero no hacen atómicas las lecturas de procfs ni congelan el proceso. El documento y la salida deben conservar esa limitación explícita.

## 5. TTY

Abrir `/dev/tty` sin adquirir un terminal de control (`O_NOCTTY`) y consultar:

- SID del terminal mediante `tcgetsid`;
- foreground PGID mediante `tcgetpgrp`;
- SID y PGID del proceso mediante `getsid` y `getpgrp`.

Si no existe TTY controlador o la consulta no está disponible, mostrar un estado explícito `TTY_UNAVAILABLE`/incompleto. No inferir TTY a partir de stdin/stdout, propietario del dispositivo, `tty_nr` aislado o variables de entorno.

La coherencia limitada se comprueba con igualdad de SID y correspondencia del PGID con el foreground PGID. Esta observación no prueba origen del PTY ni presencia física.

## 6. Ejecutable padre

Abrir `/proc/PID/exe` y consultar `fstat` para observar device, inode, mode, UID y GID. Reabrirlo después de las demás lecturas y comparar metadatos. `readlink` puede mostrar el destino textual como diagnóstico.

No se compara con una ruta/inode codificada ni se clasifica el proceso como sudo. Un cambio entre observaciones produce inconsistencia; ausencia de datos produce incompleto. Incluso metadatos idénticos no impiden un `execve` posterior.

## 7. Salida y estados

Salida legible por humanos, con campos etiquetados para:
- PID/PPID/SID/PGID del observador;
- estado pidfd;
- resultado V1;
- PPID, UID/GID y starttime observados del padre;
- doble muestra y estabilidad observada;
- metadatos de exe (device/inode/mode/UID/GID) y destino textual opcional;
- TTY disponible/no disponible, SID y foreground PGID;
- errores de observación sin incluir secretos.

Estados V1 permitidos: `OBSERVATION_CONSISTENT`, `OBSERVATION_INCONSISTENT`, `OBSERVATION_INCOMPLETE`. Ningún estado se llama ALLOW, AUTHORIZED, TRUSTED o PROOF_READY.

Códigos de salida:
- 0: observaciones completas y consistentes según V1;
- 2: observación incompleta;
- 3: observación inconsistente;
- 1: error interno/uso de sistema;
- 64: argumentos no válidos.

Una observación consistente no significa que el proceso padre sea sudo ni que el flujo de bootstrap sea confiable.

## 8. Muestreo de foreground

Un modo diagnóstico opcional de duración acotada permite muestrear el TTY y foreground PGID durante una ventana corta fija/configurable con límites estrictos. No lee entrada ni escribe en el terminal. Informa cambios observados, pérdida de TTY o ausencia de TTY. No intenta recuperar foreground ni interactuar con el shell.

## 9. Pruebas V2

Las pruebas automatizadas cubren validación de argumentos, límites de lectura, clasificación de errores, pidfd y comparaciones de snapshots mediante funciones auxiliares testeables. Las pruebas de integración manuales en Debian se ejecutarán después de completar la implementación:

1. invocación ordinaria desde terminal local;
2. sudo directo desde terminal local, solo si el operador decide ejecutarlo;
3. SSH interactivo con PTY y sudo directo;
4. SSH con PTY y shell intermediario (el padre directo debe reflejar el wrapper, no aceptar un sudo ancestro);
5. SSH sin PTY: registrar ausencia de TTY; si sudo no permite ejecutar por falta de terminal/autenticación, caso no concluyente, sin cambiar políticas;
6. muestreo de foreground/TTY y cambios durante la ventana diagnóstica.

No habilitar NOPASSWD, no cambiar timestamp, no usar sudo -S ni alterar sudoers/SSH. No instalar el observador. Binarios solo en `/tmp`.

## 10. Criterios de cierre

1. Adaptador Linux aislado del parser V1 y del probe diagnóstico.
2. Lectura acotada, acumulación hasta EOF y manejo correcto de EINTR/errores.
3. pidfd real abierto y consultado antes/después.
4. doble muestra de procfs y revalidación de PPID/starttime/credenciales.
5. metadatos exe observados desde descriptor y comparación entre muestras.
6. consulta TTY por llamadas específicas, con ausencia explícita cuando no existe.
7. estados y códigos de salida no autoritativos y fail-closed.
8. build estricto y suite automatizada en Debian por el propietario.
9. documentación con comandos exactos y límites.

El cierre de implementación no se declarará validado en el host hasta que el propietario ejecute y comparta las pruebas Debian. Completar V2 no aprueba A, no autoriza PAM, helper privilegiado ni V3/V4.
