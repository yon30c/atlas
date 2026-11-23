# Diseño de puerta de sesión SSH para bootstrap LOCAL

**Fecha:** 23 de noviembre de 2026  
**Rama:** `work/atlas-mvp-runtime`  
**Estado:** análisis estático; alternativa de diseño no aprobada ni implementada. Candidate A continúa bloqueado.  
**Relacionado:** `local-bootstrap-sudo-tty-static-audit.md`, `local-bootstrap-privilege-validation-contract.md`, `local-bootstrap-chain-observer-v3-design.md`, `local-bootstrap-privilege-boundary.md`.

## 1. Decisión de política que debe cumplir

La política aprobada por el propietario es:

- Terminal local interactiva: permitir sudo/helper directo, sujeto a los demás controles.
- SSH: permitir solo después de abrir una shell interactiva con PTY y ejecutar sudo/helper directamente desde ella.
- Rechazar `ssh -t host 'sudo ...'`, aunque exista PTY.
- Rechazar SSH sin PTY, comandos remotos no interactivos y subsistemas no autorizados.
- Rechazar wrappers o shells intermedias entre la shell interactiva y sudo/helper.

La política no se relaja para acomodar las limitaciones de V3.

## 2. Hallazgo: la petición SSH y el PTY son dimensiones distintas

OpenSSH no decide el tipo de sesión mirando únicamente si existe un PTY:

- En una petición de shell sin comando, el proceso de sesión ejecuta la shell de la cuenta como login shell: `argv[0]` lleva el prefijo `-` y no se pasa `-c`.
- En una petición SSH de ejecución (`exec`), OpenSSH ejecuta la shell de la cuenta con `-c` y el comando solicitado.
- La asignación de PTY ocurre por una ruta separada. Una petición `exec` puede tener PTY y seguir siendo una petición de comando.

El código de OpenSSH muestra ambas formas de invocación en `do_child()` y la asignación del TTY en `do_exec_pty()`: [session.c — OpenSSH](https://github.com/openssh/openssh-portable/blob/master/session.c). La documentación de `ForceCommand` indica que se aplica a shell, command y subsystem, y que el comando original queda disponible en `SSH_ORIGINAL_COMMAND`: [sshd_config(5)](https://man.openbsd.org/sshd_config.5).

**Consecuencia:** `tty_nr`, `tpgid`, `SSH_TTY` o la existencia de un PTY no bastan para distinguir `ssh -t host` de `ssh -t host 'sudo ...'`. V3 observa la topología posterior, no la clase de petición SSH recibida por el servidor.

## 3. Alternativa que merece un prototipo aislado: puerta controlada por sshd

La alternativa más prometedora no es inferir la petición desde procfs después de iniciar sudo. Es hacer que OpenSSH aplique una puerta de sesión antes de entregar una shell al usuario.

### 3.1 Composición propuesta

1. Un ejecutable pequeño en C, root-owned, no escribible por el usuario, se configura como login shell de la cuenta SSH dedicada al bootstrap.
2. Una regla administrativa `Match User` establece un `ForceCommand` fijo que apunta a esa misma puerta.
3. OpenSSH invoca la puerta mediante la login shell y `-c`. La puerta valida que recibió exactamente el comando forzado esperado; cualquier otra forma falla cerrada.
4. Para una petición SSH de shell, OpenSSH no tiene comando original. La puerta exige que `SSH_ORIGINAL_COMMAND` esté **ausente**, verifica que `/dev/tty` sea un TTY controlador y comprueba SID/foreground. Si todo coincide, hace `execve()` de la shell real configurada en una referencia protegida.
5. Para una petición SSH de comando, OpenSSH establece `SSH_ORIGINAL_COMMAND`; la puerta rechaza aunque el cliente haya pedido PTY.
6. La puerta ejecuta la shell real con `execve()`, sin fork. Así no queda un wrapper adicional en la cadena de procesos: la shell ocupa el mismo PID que la puerta.
7. La invocación local interactiva puede seguir usando la misma puerta como login shell: si no existe contexto SSH y no hay comando forzado, valida el TTY local y hace `execve()` de la shell real.

La ausencia de `SSH_ORIGINAL_COMMAND` debe comprobarse por presencia de variable (`getenv() == NULL`), no por longitud: una cadena vacía sigue siendo un comando original presente.

### 3.2 Matriz esperada

| Solicitud | Señal en la puerta | Resultado requerido |
|---|---|---|
| SSH shell request con PTY | Sin comando original; TTY controlador válido | Ejecutar shell interactiva |
| SSH shell request sin PTY | Sin comando original; `/dev/tty` no disponible | Rechazar |
| `ssh -t host 'sudo ...'` | Comando original presente | Rechazar |
| SSH exec sin PTY | Comando original presente | Rechazar |
| SSH subsystem/SFTP | Debe quedar interceptado por ForceCommand y rechazado | Rechazar; validar en la versión exacta |
| Terminal local interactiva | Sin contexto SSH; TTY controlador válido | Ejecutar shell local |
| Shell interactiva seguida de sudo directo | Shell real como origen de la cadena | Candidato a aceptar, sujeto a la validación del helper |

### 3.3 Por qué se requiere tanto ForceCommand como una login shell controlada

`ForceCommand` cubre las peticiones shell, exec y subsystem, pero por sí solo no es suficiente si la login shell es una shell del usuario: esta podría ejecutar archivos de inicio antes de llegar al comando forzado y alterar el entorno. La documentación de OpenSSH confirma que ForceCommand se ejecuta usando la login shell con `-c` y que ignora `~/.ssh/rc`; no afirma que suprima todos los archivos de inicio de la shell.

Por eso la primera imagen ejecutada debe ser la puerta C root-owned, no Bash ni otro intérprete controlado por el usuario. La puerta solo ejecuta la shell real después de validar la petición. La configuración también debe impedir que el usuario sustituya su login shell por otra ruta que evite la puerta; una cuenta SSH dedicada y administrada por root es preferible a alterar sin más la cuenta cotidiana.

### 3.4 Condiciones de configuración que serían obligatorias

Antes de considerar esta alternativa:

- Configuración efectiva de sshd revisada para cada listener/puerto y para el usuario objetivo.
- `ForceCommand` definido en configuración administrativa, no en un `authorized_keys` modificable por el usuario.
- Login shell de la cuenta fijada a la puerta root-owned; cambio de shell por el usuario impedido o controlado.
- `PermitUserEnvironment no`; `AcceptEnv` limitado explícitamente y sin aceptar `SSH_ORIGINAL_COMMAND` ni `SSH_CONNECTION`; ningún `SetEnv` que defina esas variables.
- La puerta verifica presencia/ausencia de `SSH_ORIGINAL_COMMAND`, pero no confía en `SSH_TTY` como prueba.
- `PermitTTY yes`; la puerta exige TTY controlador, SID y foreground válidos.
- `UseLogin no`, o un análisis específico si se habilita otro flujo.
- `PermitUserRC no` y revisión de todas las rutas de inicio. ForceCommand ignora `~/.ssh/rc`, pero la shell real solo se inicia después de pasar la puerta.
- Forwarding deshabilitado o restringido por separado. ForceCommand no bloquea por sí solo TCP, agent, socket ni X11 forwarding.
- SFTP, SCP, subsistemas, múltiples sesiones y cualquier otro listener deben quedar denegados o pasar por la misma puerta.
- Binario, directorios padres, configuración y referencia de la shell real deben estar protegidos por root y tener un procedimiento de actualización verificable.

Estas condiciones son requisitos de diseño, no instrucciones para cambiar el host ahora.

## 4. Validación posterior que aún haría falta en el helper

La puerta SSH no convierte V3 en autorización. El helper tendría que ampliar la inspección de ancestros y validar, como mínimo:

- cadena sudo contigua y credenciales esperadas;
- primer proceso no sudo compatible con la shell real configurada;
- relación directa entre esa shell y el proceso de sesión OpenSSH esperado;
- TTY controlador de la shell, SID y foreground coherentes;
- ausencia de un proceso wrapper entre la shell y sudo;
- identidad y versión aprobadas de OpenSSH, sudo, puerta y configuración efectiva;
- revalidación en cada fase sensible y tratamiento fail-closed de carreras.

No se debe exigir que `sshd-session` tenga `tty_nr != 0`: el proceso servidor puede conservar el PTY master mientras la shell controla el PTY slave. La prueba de TTY se realiza en la shell admitida por la puerta, no deduciendo la ausencia de PTY del `tty_nr` de sshd.

### Límite residual: reemplazo de proceso

`execve()` conserva PID y PPID. Después de iniciar la shell, el usuario puede ejecutar `exec` para reemplazar la imagen de ese proceso. La inspección de procfs puede rechazar wrappers ordinarios que aparezcan como procesos intermedios y puede exigir la ruta de la shell real, pero los argumentos de un proceso no constituyen una prueba criptográfica de su modo interactivo y pueden ser alterados por el propio proceso.

Por tanto, todavía debe demostrarse si el contrato de “sudo directamente desde la shell interactiva” puede verificarse con suficiente fuerza bajo el modelo de amenaza de Atlas. Si exige distinguir también un reemplazo deliberado de la shell mediante `exec` que imite sus atributos observables, esta alternativa no lo demuestra por sí sola. No se debe ocultar esa limitación ni tratar la cadena procfs como una atestación del kernel.

## 5. Pruebas requeridas antes de cualquier integración

En una VM aislada y después de aprobar expresamente el prototipo:

1. Confirmar versión exacta y fuente Debian de OpenSSH instalada.
2. Revisar `sshd -T -C` para el usuario, origen y puerto relevantes; verificar todos los listeners.
3. Probar shell SSH con PTY y sin comando.
4. Probar `ssh -t host 'sudo ...'` y `ssh -T host 'sudo ...'`.
5. Probar comando vacío, comandos con espacios, SFTP/SCP y subsistemas.
6. Probar variables de entorno enviadas por cliente, `AcceptEnv`, `SetEnv`, `PermitUserEnvironment` y archivos de inicio.
7. Probar shell intermedia, wrapper, subshell, `exec`, cambio de foreground, cierre de sesión y pérdida de TTY.
8. Verificar que la puerta hace exec sin dejar proceso intermedio y que todos los casos ambiguos se rechazan.
9. Repetir las pruebas después de una actualización de OpenSSH y documentar la versión aprobada.

No ejecutar todavía estas pruebas ni cambiar la VM: primero debe aprobarse el diseño del prototipo y su alcance.

## 6. Puerta de decisión

- **V3 actual:** diagnóstico únicamente; no satisface la política SSH aprobada.
- **Inferencia basada solo en procfs/TTY:** insuficiente para distinguir de forma confiable shell request y exec request.
- **Puerta administrada por sshd:** alternativa técnicamente prometedora porque se coloca en la frontera donde OpenSSH conoce el tipo de petición; todavía no implementada ni validada.
- **Bloqueadores:** cuenta/login shell administrada, configuración efectiva completa, semántica de subsistemas, integridad de variables y configuración, identidad del proceso sshd, wrappers/exec y carreras.
- **Si cualquiera de los requisitos no puede demostrarse:** descartar Candidate A sin relajar la política y evaluar Candidate B de forma independiente.

La cuenta `greed` conserva sudo irrestricto `(ALL : ALL) ALL`; el diseño no protege frente a esa cuenta actuando como root. No se modifica PAM, sudoers, sshd, cuentas, shell, systemd, claves, permisos ni host. No se implementa helper ni se ejecutan pruebas desde GitHub.
