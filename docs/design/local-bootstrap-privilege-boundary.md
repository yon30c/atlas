# Frontera de privilegios del bootstrap LOCAL

**Estado:** diseño de seguridad y evaluación de alternativas; no implementado ni instalado.
**Relacionado:** local-bootstrap-coordination-architecture.md, local-pam-bootstrap-authenticator.md, local-pam-bootstrap-proof-protocol.md.
**Objetivo:** definir cómo se ejecuta el helper C/libpam con privilegios mínimos y cómo entrega una prueba verificable al coordinador CAM.

## 1. Requisitos invariantes

El mecanismo elegido debe cumplir todo lo siguiente:

1. No utilizar un binario setuid ni conceder privilegios generales al proceso Atlas.
2. El helper debe ser root-owned, no modificable por greed como usuario sin privilegios, atlas, atlas-sandbox ni procesos Assistant.
3. El helper solo ejecuta una acción fija: autenticación PAM y emisión de una prueba para el bootstrap LOCAL inicial.
4. No acepta argumentos operativos, rutas, nombres de usuario, módulos PAM, descriptor, claves ni políticas elegidos por el caller.
5. El sujeto autorizado es el sujeto local configurado (`greed` actualmente), comprobado mediante evidencia confiable de la invocación y configuración protegida.
6. La contraseña se solicita mediante PAM en el TTY confiable; no entra por stdin, argv, entorno, archivo ni IPC.
7. La confirmación del descriptor se captura directamente dentro del helper en el mismo TTY.
8. La clave privada solo es accesible al helper; el proceso Python recibe una prueba firmada y usa material público para verificarla.
9. El helper no lee ni escribe SQLite/CAM y no puede abrir el Recovery Gate.
10. Cualquier ambigüedad sobre sujeto, TTY, invocación, configuración o clave produce rechazo.

## 2. Alternativas evaluadas

### A. Ejecutable root-owned invocado mediante sudo

El operador invoca una ruta fija, sin argumentos, a través de sudo. El ejecutable no tiene bit setuid y no se añade una regla NOPASSWD. El helper realiza siempre su propia reautenticación PAM; una caché de sudo no satisface ese requisito.

Ventajas:
- componente pequeño y de ejecución breve;
- no requiere un daemon privilegiado permanente;
- la interacción TTY permanece en el proceso que solicita PAM;
- salida de prueba firmada sencilla de transportar al coordinador.

Riesgos/condiciones:
- el helper debe obtener de forma confiable la identidad original del invocador; no debe aceptar SUDO_UID/SUDO_USER si la configuración sudo permite preservar o sobrescribir esas variables;
- debe exigir el entorno sudo esperado (`env_reset`, sin `SETENV` ni preservación arbitraria) y comprobar los metadatos de invocación;
- debe abrir `/dev/tty` directamente, validar que es terminal controladora de la sesión, comprobar sesión/grupo foreground y verificar propietario del dispositivo frente al sujeto esperado;
- no debe aceptar argumentos ni stdin como canal de interacción;
- sudo puede tener timestamp cacheado, pero esto no sustituye PAM del helper;
- la cuenta `greed` ya es administradora del host; este diseño no pretende proteger el sistema frente a un operador `greed` malicioso que ya puede obtener root mediante sudo.

**Estado:** candidato preferido por simplicidad, sujeto a inspección de `sudo -l`, configuración efectiva de sudo y pruebas de cómo se identifica el invocador en el host. No se asume que esas condiciones estén satisfechas.

### B. Servicio privilegiado root con socket Unix

Un servicio root de vida corta o socket-activated acepta una conexión local. Obtiene UID/GID/PID del peer mediante `SO_PEERCRED` y recibe el descriptor de TTY por `SCM_RIGHTS`. Valida que el TTY pertenece a la sesión del peer y realiza PAM en el servicio dedicado.

Ventajas:
- identidad del peer derivada del kernel, no de variables de entorno;
- no depende de la semántica de UID/variables de sudo;
- el socket puede restringir quién inicia una solicitud.

Costes y riesgos:
- añade servicio privilegiado, protocolo IPC, gestión de descriptores y superficie de parser;
- debe validar rigurosamente TTY transferido, sesión, foreground process group, propietario y cierre de descriptores;
- debe evitar aceptar conexiones sin TTY o reutilizar descriptores;
- el servicio root no puede convertirse en API general ni ejecutar comandos;
- exige definir ciclo de vida, límites, logging, rate limiting y comportamiento ante caída.

**Estado:** alternativa de reserva si el host no permite probar de forma fiable el invocador mediante sudo. No se implementa ahora.

### C. setuid, capabilities o privilegios generales del runtime

**Rechazado.** Aumenta el riesgo de escalada y mezcla autenticación con ejecución general. No se utilizará.

## 3. Candidato A: contrato de invocación

Si la inspección del host confirma las condiciones, el contrato será:

- ruta fija root-owned bajo `/usr/libexec/atlas/`;
- ejecución explícita mediante sudo, sin argumentos y sin `-E`, `-u`, shell o modo login;
- sin regla NOPASSWD adicional;
- entorno saneado por sudo; el helper valida los metadatos de invocación antes de limpiar el entorno;
- la identidad original se compara con la cuenta configurada y el UID obtenido de la base de cuentas local; nunca se toma un UID esperado del caller;
- el helper rechaza ejecución directa por root sin evidencia válida de invocación administrativa y rechaza cualquier sujeto distinto de greed;
- el helper abre `/dev/tty` y no usa stdin/stdout para prompts;
- la confirmación y el prompt PAM se realizan en ese TTY;
- la prueba firmada se escribe como bytes acotados a stdout solo después de completar la autenticación y confirmación; diagnósticos genéricos van a stderr;
- stdout no se considera canal confiable: el coordinador siempre verifica firma, host, sujeto, descriptor, acción y vigencia;
- la prueba no es secreta. Si se copia o repite, la verificación y consumo CAM de un solo uso siguen siendo obligatorios.

Los metadatos de sudo solo son confiables si la configuración efectiva de sudo garantiza que los establece el propio sudo y no permite al caller preservarlos o sustituirlos. Si no puede demostrarse, se elige la alternativa B en lugar de inventar heurísticas con PPID, nombre de proceso o UID efectivo.

## 4. Validación del TTY

El helper debe abrir el terminal controlador por sí mismo (`/dev/tty`) y fallar si no existe. Como mínimo, comprobará:

- el descriptor abierto es un TTY;
- el terminal tiene una sesión controladora válida;
- el proceso pertenece a esa sesión;
- el proceso es el grupo de procesos foreground del terminal durante la interacción;
- el dispositivo y su propietario corresponden al sujeto local configurado, considerando correctamente los permisos y comportamiento de devpts del host;
- el descriptor no se sustituye durante el flujo;
- el prompt no se envía a stdout/stderr redirigidos;
- no se acepta terminal remoto o no local si la política del bootstrap exige consola local.

Los checks exactos deben implementarse y probarse contra el comportamiento real de Debian/devpts. No basta con `isatty(0)` ni con comprobar que `/dev/tty` existe.



## 4.1 Resultado de la primera prueba de invocación (16-11-2026)

El propietario ejecutó una prueba inocua con `sudo python3` desde una shell interactiva:

- UID real y efectivo del proceso: 0.
- GID real y efectivo: 0.
- `SUDO_UID=1000` y `SUDO_USER=greed`.
- `/dev/tty` se pudo abrir y `isatty` devolvió verdadero.
- La inspección de sesión no terminó: el módulo Python `os` disponible no expone `tcgetsid`; no se obtuvo todavía el SID del terminal ni se comparó con la sesión/grupo foreground.
- La cuenta `greed` tiene sudo irrestricto `(ALL : ALL) ALL`.

**Conclusión:** bajo sudo, `getuid()` y `geteuid()` no identifican al invocador original: ambos son 0. `SUDO_UID`/`SUDO_USER` son metadatos útiles para diagnóstico, pero no se aceptarán aisladamente como prueba criptográfica de identidad ni como defensa frente al administrador root. La prueba tampoco demuestra todavía la vinculación del TTY a la sesión.

El modelo de amenaza ya excluye al propietario administrador actuando maliciosamente: `greed` puede obtener root por sudo. La frontera debe impedir que procesos Atlas sin privilegios (Assistant, Skills, `atlas`, `atlas-sandbox`) fabriquen o invoquen la prueba como si fueran el propietario. La reautenticación PAM del sujeto configurado sigue siendo obligatoria.

**Siguiente comprobación:** repetir solo la inspección de TTY usando la función libc `tcgetsid(2)` mediante `ctypes`, además de `tcgetpgrp`, `getsid(0)`, `getpgrp` y `fstat` del descriptor. No cambiar sudoers ni instalar/configurar nada. Después se decidirá si el mecanismo A puede sostenerse con los metadatos efectivos de sudo y el modelo de amenaza, o si conviene B (socket Unix + `SO_PEERCRED` + TTY transferido).

## 4.2 Segunda prueba y cadena de procesos (16-11-2026)

La inspección de sesión/TTY mediante libc devolvió:

- UID real/efectivo del proceso Python: 0/0.
- `SUDO_UID=1000`, `SUDO_USER=greed` (solo diagnóstico; no se aceptan como prueba).
- Terminal SID y proceso SID: `10931`.
- Grupo foreground reportado en esa ejecución: `10931`; grupo del proceso consultado: `10932`.
- `/dev/tty` abrió correctamente; propietario UID 0, GID 5.

En una comprobación separada de la cadena de procesos, el propietario obtuvo:

```text
PID    PPID   SID    PGID   TPGID  TT     RUID  EUID  COMMAND
10938  10936  10938  10938  10939  pts/2  1000  0     sudo
10939  10938  10938  10939  10939  pts/2     0  0     python3
```

Esta segunda salida aporta evidencia adicional:

- El proceso `sudo` es el padre directo del proceso privilegiado.
- `sudo` conserva RUID 1000 y EUID 0; el hijo ejecutado queda con RUID/EUID 0.
- El hijo comparte SID con `sudo` y su PGID coincide con TPGID: el hijo es el grupo foreground del terminal en esta comprobación.
- El grupo de `sudo` es distinto del grupo foreground, comportamiento compatible con que sudo coloque el comando en su propio grupo de procesos.

Las dos comprobaciones de TTY no deben fusionarse como si fueran una única instantánea: la primera mostró un grupo no coincidente; la cadena posterior muestra un comando hijo en foreground. La cadena de procesos hace viable investigar A mediante validación del padre directo, pero todavía no basta para aprobarlo definitivamente.

**Conclusión provisional:** A vuelve a ser el candidato preferido, condicionado a que un helper C real, ejecutado directamente por sudo, pueda validar de forma robusta y sin carreras:
1. que su padre directo es el binario sudo esperado, root-owned y no modificable por usuarios no confiables;
2. que el proceso padre tiene RUID igual al UID del sujeto configurado (1000 para greed) y EUID 0;
3. que helper, padre y TTY pertenecen a la misma sesión;
4. que el helper está en el grupo foreground del TTY durante toda la interacción;
5. que la configuración efectiva de sudo no permite que un caller no privilegiado falsifique la cadena de invocación o sustituya el ejecutable.

No usar `SUDO_UID`, `SUDO_USER`, PPID aislado, nombre de proceso aislado ni propietario del dispositivo TTY como prueba suficiente. El helper debe validar la relación completa con datos del kernel y archivos ejecutables/configuración protegidos. Esto no constituye una defensa contra greed actuando como administrador root.

**Siguiente paso de diseño:** especificar el contrato de validación del padre sudo y las comprobaciones anti-TOCTOU para el helper C. Antes de implementar, revisar el comportamiento exacto con el helper mínimo en un entorno de prueba y definir pruebas negativas (invocación directa, caller atlas, caller atlas-sandbox, sin TTY, TTY no foreground, padre inesperado y entorno manipulado). No modificar sudoers ni instalar/configurar nada todavía.


## 4.2.1 Política de terminal local y SSH interactivo

**Decisión aprobada: se admite bootstrap desde terminal local y desde SSH interactivo con PTY.** SSH sin PTY y cualquier ejecución no interactiva quedan fuera del flujo.

La autorización no depende de que el operador esté físicamente frente al servidor. Un PTY SSH acredita una sesión de terminal interactiva, no presencia física, ubicación ni dispositivo confiable.

Condiciones para ambas modalidades:

- El TTY controlador debe existir y superar las validaciones de SID y grupo foreground de §4.3.
- La confirmación del descriptor se lee directamente del TTY controlador, nunca de stdin, argumentos, variables de entorno, pipe, archivo o socket no autenticado.
- PAM realiza una autenticación reciente del sujeto configurado (`greed`) dentro del helper; el éxito de sudo, una sesión SSH ya abierta o una caché de credenciales no sustituyen esta autenticación.
- `pam_acct_mgmt` también debe aprobar; cuenta expirada, bloqueada o no autorizada implica rechazo.
- Pérdida de TTY, foreground, sesión, conexión o señal de cierre antes de emitir la prueba cancela el bootstrap.
- La prueba firmada vincula el descriptor exacto, sujeto autenticado, dominio/host, nonce, request/proof IDs y ventana temporal. No incluye ni confía en una afirmación del cliente sobre que el acceso fue local o remoto.
- Las políticas SSH del host (por ejemplo, permitir o denegar login root, autenticación y asignación de PTY) permanecen bajo administración del propietario. Este diseño no las modifica ni presupone su configuración.
- No se habilitará forwarding de terminal, X11 ni mecanismos alternativos como sustituto de un TTY controlador válido.

Pruebas específicas:
1. SSH con PTY y sujeto greed: puede continuar solo si todas las comprobaciones de sudo, TTY y PAM pasan.
2. SSH sin PTY (`ssh -T`) y comandos remotos no interactivos: rechazo antes de PAM y sin emitir prueba.
3. Desconexión SSH, HUP, EOF o pérdida del foreground durante confirmación/PAM: cancelación sin prueba.
4. TTY local válido: mismo contrato de seguridad que SSH con PTY.
5. Usuario SSH distinto de greed: rechazo, incluso si consigue invocar el ejecutable.
6. Reenvío de stdin/stdout/stderr, pipes o variables que simulen una sesión: no pueden sustituir el TTY controlador ni alterar el sujeto.

## 4.3 Contrato de validación del proceso padre sudo (diseño propuesto)

La evidencia observada permite mantener A como candidato preferido, pero no autoriza a tratar cualquier proceso root cuyo padre aparente ser sudo como confiable. El helper C deberá validar una relación de invocación concreta, usando datos del kernel y objetos abiertos, y fallar ante cualquier discrepancia.

### A. Precondiciones del helper

- Ejecutable en ruta fija, root-owned, no escribible por grupo/otros; todos los directorios padre también protegidos.
- No setuid ni file capabilities.
- Invocación esperada: `sudo -- /usr/libexec/atlas/local-bootstrap-authenticator`, sin argumentos.
- `argc` debe ser exactamente 1. No se interpreta stdin como entrada de protocolo ni de credenciales.
- El helper no acepta `-u`, `-E`, shell, modo login, rutas alternativas ni opciones.
- La política efectiva de sudo debe permitir únicamente el comportamiento esperado para el sujeto operativo. No se añadirá NOPASSWD ni una excepción amplia.
- La contraseña de sudo no sustituye la autenticación PAM que realiza el helper.

### B. Validación del padre directo

Al inicio, el helper captura `getpid()`, `getppid()`, `getsid(0)`, `getpgrp()` y la identidad del TTY. Luego:

1. Abre un pidfd para el PID padre con `pidfd_open(2)`; si no está disponible o falla, rechaza A en vez de degradar a una comprobación débil.
2. Abre `/proc/<ppid>/exe` y obtiene metadatos del ejecutable mediante `fstat` sobre el objeto abierto. Comprueba que corresponde al binario sudo aprobado en el host, es regular, propiedad de root y no modificable por grupo/otros. La ruta textual de `readlink` no basta como prueba.
3. Lee `/proc/<ppid>/status` de forma acotada y parsea estrictamente los cuatro UID/GID. El UID real debe coincidir con el UID del sujeto local obtenido de la configuración protegida y la base local de cuentas; el UID efectivo debe ser 0. No acepta valores de entorno como sustituto.
4. Comprueba que el padre directo sigue siendo el PID capturado, que su SID coincide con el SID del helper y que el helper no ha sido reparentado durante la validación.
5. Verifica que el padre no es el propio helper ni un wrapper/shell. No se sigue una cadena arbitraria de ancestros para “encontrar” un sudo más arriba.
6. Revalida el estado del pidfd y la relación de proceso antes de comenzar la interacción. Si el padre desaparece, cambia la relación o una lectura es inconsistente, aborta.

El pidfd fija la referencia al proceso y evita confundir un PID reutilizado con otro proceso; no congela por sí solo sus credenciales, ejecutable ni estado. Por eso se requieren lecturas coherentes, comprobaciones repetidas y una política de fallo cerrado. No se afirmará que /proc ofrece una instantánea atómica de todos los atributos.

### C. Validación de sesión y TTY

- Abre `/dev/tty` con flags que impidan seguir un enlace inesperado y comprueba con `fstat` y `isatty` que es un terminal.
- Obtiene SID del terminal mediante `tcgetsid(fd)`, SID del helper mediante `getsid(0)` y grupo foreground mediante `tcgetpgrp(fd)`.
- Exige que SID del terminal = SID del helper = SID del padre sudo.
- Exige que `tcgetpgrp(fd) == getpgrp()` antes de cada prompt y durante las fases interactivas. Si el helper deja de estar en foreground, interrumpe la operación y no emite prueba.
- No exige que el propietario UID del nodo devpts sea greed: con `sudo -i`/PTY allocation el dispositivo puede pertenecer a root. El propietario del nodo no autentica al operador.
- La política LOCAL debe decidir expresamente si admite PTY remoto (por ejemplo, SSH). Un TTY controlador válido demuestra interacción con una sesión, no presencia física ante el servidor. Hasta que esa política se cierre, no se describirá el control como “consola física”.
- No acepta stdin como sustituto del TTY ni usa stdout/stderr redirigidos para solicitar confirmación o contraseña.

Las llamadas a `tcgetpgrp` se repetirán justo antes de leer confirmación y antes/durante PAM. El helper no puede impedir que el usuario cambie de terminal o que la sesión se cierre; ante pérdida de foreground, HUP, EOF o error de terminal cancela y limpia el estado sensible.

### D. Configuración sudo y ejecutable

Antes de aprobar A debe existir una inspección de solo lectura y una prueba del helper mínimo que establezcan:

- versión/ruta efectiva de sudo y su ejecutable root-owned;
- `env_reset` efectivo y ausencia de preservación arbitraria de variables para esta invocación;
- ausencia de `SETENV` o reglas que permitan cambiar entorno/ejecutable de forma no prevista;
- uso de PTY coherente con la política aprobada;
- que el helper recibe exactamente el padre y las credenciales observadas en la prueba;
- que el usuario técnico `atlas`, `atlas-sandbox` y un proceso sin TTY no pueden obtener el mismo flujo mediante sus permisos reales.

No se considerará suficiente una coincidencia de nombre de proceso, PPID, `SUDO_UID`, `SUDO_USER`, UID efectivo, propietario del TTY ni una sola lectura de `/proc`. La cuenta greed ya tiene sudo irrestricto; el modelo no intenta limitar a un administrador que decide ejecutar código arbitrario como root.

### E. Pruebas negativas obligatorias antes de aprobar A

1. Ejecutar el helper directamente como greed sin sudo: rechazo.
2. Ejecutarlo desde root sin padre sudo válido: rechazo.
3. Intentar invocarlo desde `atlas` y `atlas-sandbox`: rechazo por política de sudo y por validación del sujeto.
4. Invocarlo sin TTY controlador: rechazo.
5. Invocarlo desde un grupo que no sea foreground: rechazo.
6. Cambiar de foreground o cerrar el TTY durante el prompt: cancelación sin prueba.
7. Añadir argumentos o intentar alterar entorno, locale, PATH, HOME, USER, SUDO_UID/SUDO_USER: no cambia descriptor, sujeto, ruta ni política; discrepancias producen rechazo.
8. Simular padre inesperado, proceso reparentado, fallo de pidfd o inconsistencia de /proc: rechazo.
9. Alterar permisos del helper, sus directorios, configuración o clave: rechazo antes de PAM.
10. Contraseña incorrecta, cuenta bloqueada/inactiva o fallo PAM: no se emite prueba.

Estas pruebas se diseñarán primero como pruebas unitarias/integración sin privilegios reales cuando sea posible. Las pruebas que requieran sudo/PAM se harán en un entorno de prueba controlado y solo después de aprobación explícita. No se ejecutarán ahora.

### F. Criterio de selección

A se aprobará únicamente si la implementación puede cumplir y demostrar todos los controles anteriores en el Debian real. Si pidfd, procfs, política sudo, sesión/TTY o pruebas negativas no permiten una validación coherente, se seleccionará B. No se relajarán las condiciones para conservar A.



## 4.4 Prototipo C de observación (diagnóstico, no validador)

Se añadió `tools/bootstrap-probe/bootstrap_probe.c` con instrucciones en `tools/bootstrap-probe/README.md`.

El programa únicamente observa e imprime:
- PID/PPID, UID/GID real y efectivo, SID y PGID del proceso actual;
- PID padre directo, UID/GID y PPID desde `/proc/PID/status`;
- disponibilidad de `pidfd_open` y estado inmediato observado mediante `poll`;
- metadatos del objeto ejecutable abierto mediante `/proc/PID/exe` y su destino textual informativo;
- SID del TTY, SID del proceso, grupo foreground, PGID y metadatos del dispositivo.

**No es un helper de seguridad.** No compara contra una allowlist, no decide si el padre es confiable, no autentica, no invoca PAM, no lee configuración ni claves, no firma, no emite prueba y no toca CAM. No debe instalarse en rutas privilegiadas ni recibir setuid/capabilities. Los resultados son observaciones no atómicas y no constituyen autorización.

Compilación propuesta por el usuario en su checkout Debian (binario temporal en `/tmp`):

```sh
cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror \
  -o /tmp/atlas-bootstrap-probe \
  tools/bootstrap-probe/bootstrap_probe.c
```

Ejecuciones para comparar:
- `/tmp/atlas-bootstrap-probe` desde shell interactiva normal;
- `sudo -- /tmp/atlas-bootstrap-probe` desde esa misma shell;
- `ssh -t HOST 'sudo -- /tmp/atlas-bootstrap-probe'` desde cliente SSH con PTY;
- `ssh -T HOST 'sudo -- /tmp/atlas-bootstrap-probe'` sin PTY. Interpretar el resultado según la autenticación disponible: si sudo no puede solicitar contraseña, el comando no se ejecuta y la prueba no informa sobre un eventual PTY creado por `use_pty`. No asumir que la ausencia de PTY del cliente implica ausencia de TTY en el proceso hijo si sudo llega a ejecutar el comando.

Reemplazar `HOST` por el alias/destino SSH real. No cambiar sudoers ni instalar el binario. Revisar la salida antes de compartirla. Todavía no se han compilado ni ejecutado estas fuentes en el Debian del propietario; no declarar el prototipo validado hasta recibir resultados.



## 4.5 Inspección de integridad de sudo y prueba SSH sin PTY (16-11-2026)

Se completó la inspección de solo lectura del ejecutable y configuración efectiva disponible en el host Debian:

- `/usr/bin/sudo`: UID 0, GID 0, modo `4755`, tamaño 306456 bytes, inode 3270762, dispositivo 2082.
- La cadena `/`, `/usr`, `/usr/bin` y el ejecutable pertenece a `root:root`; los directorios tienen modo `755`.
- `findmnt -T /usr/bin/sudo`: raíz sobre `/dev/sdc2`, ext4, opciones `rw,relatime,errors=remount-ro`; no aparece `nosuid`.
- Paquete propietario: `sudo`; versión `1.9.16p2-3+deb13u2`, estado `install ok installed`.
- `sudo dpkg --verify sudo` no produjo salida: no reportó discrepancias verificables en los archivos del paquete.
- El atributo extendido `security.capability` consultado mediante Python devolvió ENODATA (61), interpretado como atributo ausente; no se detectaron file capabilities adicionales.
- `getcap` y `getfattr` no están instalados. No se instalaron paquetes.
- `visudo -c` validó `/etc/sudoers` y `/etc/sudoers.d/README`.
- Hash observado de `/usr/bin/sudo`: `a59f393bad5037644b89de64fe558ae6d5d1473c25c63022241e7c7019ad2f0c`. Es una referencia de esta inspección, no una verificación criptográfica independiente contra un repositorio de confianza.
- La inspección previa de sudo mostró los defaults `env_reset`, `mail_badpass`, `secure_path` y `use_pty`; `greed` puede ejecutar `(ALL : ALL) ALL`.

### Resultado de SSH sin PTY

Se ejecutó desde Windows:

```text
ssh -T greed@10.0.0.81 'sudo -- /tmp/atlas-bootstrap-probe'
sudo: a terminal is required to read the password; either use the -S option to read from standard input or configure an askpass helper
sudo: a password is required
```

Sudo rechazó la solicitud porque no tenía un terminal desde el que solicitar la contraseña. El prototipo no se ejecutó. Por tanto, esta prueba **no demuestra** cómo se comportaría el helper si sudo ya tuviera una autorización válida para ejecutar el comando. Tampoco demuestra que el helper pueda distinguir un PTY asignado por SSH de un PTY creado por la opción sudo `use_pty`.

La política aprobada sigue excluyendo SSH sin PTY. Sin embargo, el mecanismo concreto para demostrar esa condición en presencia de `use_pty` queda pendiente de diseño y prueba; no se aceptará una inferencia basada únicamente en que `/dev/tty` exista o en el foreground del PTY que reciba el helper.

### Matriz consolidada de observaciones

| Escenario | Resultado observado | Alcance |
|---|---|---|
| Ejecución local sin sudo | Prototipo diagnóstico se ejecuta como greed | Observación de proceso/TTY |
| Ejecución local con sudo | Prototipo diagnóstico se ejecuta como root; padre sudo directo observado | Compatible con A |
| SSH con PTY y sudo | Prototipo diagnóstico se ejecuta como root; cadena sudo/TTY observada | Compatible con A y política SSH interactiva |
| SSH sin PTY, ejecución directa | No existe TTY controlador | Rechazo por ausencia de TTY |
| SSH sin PTY, sudo sin credenciales disponibles | Sudo no puede solicitar contraseña y no ejecuta el prototipo | No concluyente sobre sudo `use_pty` tras autenticación válida |

**Conclusión:** la integridad básica del ejecutable sudo y la configuración observada son compatibles con continuar evaluando A. No aprueban el diseño ni sustituyen el prototipo de validación C. La cuenta greed conserva autoridad administrativa irrestricta; el modelo no protege contra ese administrador actuando maliciosamente.


## 4.6 Diagnóstico del TTY controlador del padre sudo (16-11-2026)

Para investigar el efecto de `use_pty`, el probe diagnóstico se amplió para observar, sin tomar decisiones:

- `/proc/<sudo-pid>/stat`: estado, PPID, PGID, SID, `tty_nr` y `tpgid` del padre directo.
- destinos informativos de los descriptores 0, 1 y 2 del padre directo (`/proc/<sudo-pid>/fd/{0,1,2}`).
- se mantienen las observaciones del ejecutable padre, UID/GID, pidfd y TTY controlador del helper.

Hipótesis a contrastar, no asumida como hecho: si sudo crea un PTY separado para el comando, el helper podría tener un TTY controlador válido mientras el proceso sudo que lo lanzó conserva `tty_nr=0` cuando el cliente SSH no solicitó PTY. En SSH con PTY, se espera observar un TTY controlador en el padre sudo. Los resultados reales deben decidir si esta distinción existe y es estable en la versión/configuración instalada.

Límites:
- `tty_nr` y los enlaces de FD son observaciones de `/proc`, no una prueba criptográfica ni una instantánea atómica.
- Un padre puede cerrar/reabrir descriptores; los enlaces pueden cambiar durante la lectura.
- El diagnóstico no sigue procesos ancestros ni intenta atribuir origen físico/remoto.
- La salida no autoriza bootstrap y no se utilizará como condición de seguridad hasta que se diseñe una validación robusta y se cubran carreras y casos negativos.

**Prueba siguiente:** compilar el probe actualizado en `/tmp` y comparar la ejecución local interactiva, local con sudo y SSH con PTY. La prueba SSH sin PTY con sudo solo es informativa si sudo llega a ejecutar el probe; un rechazo por falta de terminal/credenciales no observa el proceso hijo ni permite concluir sobre `use_pty`. No alterar sudoers, timestamp policy ni PAM para forzar esa ejecución.


## 4.7 Resultados de la segunda ronda de diagnóstico C (16-11-2026)

El propietario compiló y ejecutó el probe ampliado. Se recibieron tres ejecuciones:

### Shell interactiva local, sin sudo

- Proceso probe UID/EUID 1000/1000; padre directo bash UID real/efectivo 1000/1000.
- Padre bash: `tty_nr=34816`, `tpgid=11353`; FD 0/1/2 apuntan a `/dev/pts/0`.
- El probe: SID 2320, PGID 11353; TTY SID 2320, foreground PGID 11353.
- Resultado: terminal interactivo normal observado.

### Shell interactiva local, con sudo

- Proceso probe UID/EUID 0/0; padre directo `/usr/bin/sudo`.
- Padre sudo: UID real/efectivo/saved/fs 1000/0/0/0; GID 0/0/0/0.
- Padre sudo: `tty_nr=34818`, `tpgid=11357`; FD 0/1/2 apuntan a `/dev/pts/0`.
- Padre y probe comparten SID 11356; el PGID del probe 11357 coincide con el foreground TPGID.
- TTY controlador del probe válido; terminal SID 11356 y foreground 11357.
- Ejecutable padre observado: dispositivo 2082, inode 3270762, UID/GID 0/0, modo 4755, destino `/usr/bin/sudo`.

### SSH con PTY y sudo

- Proceso probe UID/EUID 0/0; padre directo `/usr/bin/sudo`.
- Padre sudo: UID real/efectivo/saved/fs 1000/0/0/0; GID 0/0/0/0.
- Padre sudo: `tty_nr=34819`, `tpgid=11371`; FD 0/1/2 apuntan a `/dev/pts/2`.
- Padre y probe comparten SID 11370; el PGID del probe 11371 coincide con el foreground TPGID.
- TTY controlador del probe válido; terminal SID 11370 y foreground 11371.
- Ejecutable padre observado: dispositivo 2082, inode 3270762, UID/GID 0/0, modo 4755, destino `/usr/bin/sudo`.

### Interpretación

Las tres observaciones son compatibles con el contrato esperado para terminales interactivos. En las dos ejecuciones privilegiadas, el padre sudo tiene un `tty_nr` distinto de cero y sus descriptores 0/1/2 apuntan a un PTY. El hijo comparte SID con el padre y queda en el grupo foreground.

Esto no demuestra que el TTY del padre sudo sea necesariamente el PTY originalmente solicitado por el cliente SSH: `tty_nr`, SID, PGID y enlaces FD solo describen el estado actual observado del proceso. No prueban procedencia del terminal ni presencia física. La prueba SSH con PTY no responde al caso SSH sin PTY.

### Caso SSH sin PTY pendiente

La prueba previa `ssh -T ... sudo -- /tmp/atlas-bootstrap-probe` fue rechazada por sudo antes de ejecutar el probe porque no había terminal para solicitar contraseña. Por ello no observó el proceso sudo ni un posible PTY para el hijo.

No se debe cambiar la política de timestamp, habilitar NOPASSWD, usar `sudo -S` ni alterar sudoers para forzar la ejecución. Primero se debe inspeccionar el `timestamp_type` efectivo y determinar si existe un método de prueba aprobado que no modifique el host ni eluda la autenticación. Si no existe, se documentará el caso como no reproducible bajo la configuración actual y A no podrá afirmar que detecta de forma independiente la ausencia de PTY en el transporte SSH basándose en las observaciones actuales.

**Conclusión provisional:** el probe aporta evidencia favorable de que el patrón sudo + TTY interactivo se comporta como se esperaba. No se aprueba A todavía. La distinción entre SSH con PTY y SSH sin PTY sigue sin demostrarse en presencia de `use_pty`.

## 5. Entorno, argumentos y descriptores

- Rechazar argc distinto del valor fijo esperado.
- Rechazar variables que cambien módulos PAM, rutas, claves, configuración, sujeto, descriptor, locale de seguridad o política.
- No utilizar `PATH` ni ejecutar subprocesses; el helper no hace shell-outs.
- No confiar en `HOME`, `USER`, `LOGNAME`, `SUDO_USER` o `SUDO_UID` aislados.
- Validar cuidadosamente los metadatos de sudo y el UID real del dispositivo TTY.
- Cerrar todos los file descriptors heredados salvo los estrictamente necesarios; abrir configuración y clave mediante rutas fijas, `O_NOFOLLOW` y validación de `fstat`.
- La configuración y clave deben ser archivos regulares, con propietario/permisos esperados, directorios padre no modificables por usuarios no confiables y tamaño máximo.
- No seguir symlinks ni aceptar rutas suministradas por caller.
- No volcar configuración sensible ni material de clave a logs.

## 6. Clave y prueba

El helper carga la clave privada desde una ubicación fija root-only. No acepta key path, key id ni algoritmo del caller. El `key_id`, algoritmo y clave pública correspondiente se fijan en configuración de confianza del verificador.

La prueba se codifica en el formato versionado definido por el protocolo. La salida stdout contiene exclusivamente un envelope completo y acotado. El helper no crea archivos temporales de prueba ni deja evidencia privada en disco.

El coordinador Python recibe bytes, parsea estrictamente y verifica la firma. Nunca confía en que el proceso hijo haya devuelto éxito como sustituto de la verificación. El proof se consume junto con DOMAIN_BOOTSTRAPPED, identity, binding, head y gate en la misma SQLiteUnitOfWork.

El transporte stdout es aceptable únicamente porque la prueba está firmada y ligada al host/configuración; no se considera autenticado ni secreto. La copia/replay no debe permitir una segunda génesis.

## 7. Límites de seguridad

El diseño no protege frente a root comprometido, kernel comprometido, binario/configuración reemplazados por root, malware que capture teclado en la sesión del operador, ni frente al propio operador greed si conserva sudo irrestricto y actúa maliciosamente. No ofrece anti-rollback externo.

El objetivo es impedir que Assistant, Skills, atlas, atlas-sandbox o un caller sin privilegios puedan fabricar autenticación, cambiar descriptor/configuración, obtener la clave o ampliar la capacidad del helper. No se intenta convertir sudo en un sandbox contra el administrador del host.

## 8. Inspección de solo lectura requerida antes de seleccionar A

Ejecutar localmente y compartir las salidas, revisando/ocultando cualquier dato sensible que aparezca:

```bash
printf '%s\n' '===== IDENTIDAD Y SESION ====='
id
printf 'tty: '; tty || true
printf 'session: '; ps -o pid,ppid,sid,pgid,tpgid,tty,ruid,euid,comm -p $$
printf '%s\n' '===== SUDO DISPONIBLE ====='
command -v sudo
sudo -V | sed -n '1,35p'
printf '%s\n' '===== PERMISOS EFECTIVOS ====='
sudo -l
printf '%s\n' '===== DEFAULTS RELEVANTES (SI ESTAN EXPUESTOS) ====='
sudo -ll 2>/dev/null | sed -n '1,180p'
printf '%s\n' '===== CONFIGURACION SUDO RELEVANTE ====='
sudo grep -RInE '^[[:space:]]*(Defaults|#includedir|@includedir)|env_reset|env_keep|env_delete|setenv|secure_path|timestamp_type|requiretty|!authenticate|NOPASSWD|SETENV' /etc/sudoers /etc/sudoers.d 2>/dev/null
```

Estas órdenes son de inspección. No modifican sudoers, PAM, systemd ni permisos. La salida de `sudo -l` puede mostrar comandos administrativos permitidos; revisarla antes de compartirla.

## 9. Decisión pendiente

**A (helper root-owned invocado por sudo) es el candidato preferido, pero todavía no está aprobado ni implementado.** Las pruebas aportadas muestran un patrón compatible: sudo conserva RUID 1000/EUID 0 y el hijo root comparte sesión y puede quedar en el grupo foreground. No demuestran por sí solas que el helper pueda validar toda la relación sin carreras.

B (servicio privilegiado con socket Unix, `SO_PEERCRED` y TTY transferido mediante `SCM_RIGHTS`) permanece como alternativa de reserva si el contrato de A no puede implementarse y probarse rigurosamente.

Antes de aprobar A se requiere:
1. cerrar la política sobre PTY remoto/SSH frente a consola local;
2. verificar configuración efectiva de sudo, ejecutable y entorno para la invocación exacta;
3. implementar un prototipo mínimo de validación C en un entorno de prueba controlado, sin PAM, claves ni escritura CAM;
4. demostrar validación del padre directo, pidfd/procfs, SID, foreground TTY y fallo cerrado ante inconsistencias;
5. completar las pruebas negativas de §4.3;
6. revisar el código y aprobar explícitamente la implementación privilegiada.

No se modificará sudoers, PAM, systemd, Broker, usuarios/grupos ni permisos del host; no se instalará helper ni se generarán claves hasta cerrar el diseño y recibir aprobación explícita. Si cualquiera de los controles no puede demostrarse, se elige B sin debilitar los requisitos.
