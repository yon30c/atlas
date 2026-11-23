# Diseño V3 — observador diagnóstico de la cadena sudo para bootstrap LOCAL

**Estado:** prototipo diagnóstico V3 implementado y validado localmente en Debian; validación original y escenarios SSH documentados en §4, con reejecución de build/tests y escenarios locales directos/sudo el 23-11-2026 (§4.1).  
**Aprobación:** el propietario autorizó trabajar conjuntamente los puntos 1–7 el 16-11-2026. La aprobación cubre únicamente el observador C no privilegiado, sus pruebas y documentación. No autoriza helper privilegiado, PAM, instalación, configuración del host ni ejecución de bootstrap.  
**Rama de trabajo actual:** `work/atlas-mvp-runtime`.  
**Relacionado:** local-bootstrap-privilege-validation-contract.md, local-bootstrap-observer-v2-design.md, local-bootstrap-privilege-boundary.md.

## 1. Objetivo y resultado

V3 implementa un observador Linux de solo lectura que contrasta una forma acotada de la cadena de procesos del candidato A. Separa expresamente la observación genérica V2 de la pregunta específica: si el proceso actual fue lanzado directamente por un proceso compatible con sudo y si la cadena observada conserva una relación verificable entre el TTY controlador del primer ancestro no sudo y el monitor sudo externo; esto no autentica la procedencia del TTY ni del canal SSH.

Resultados permitidos:
- CHAIN_PATTERN_MATCHED_DIAGNOSTICALLY
- CHAIN_MISMATCH
- CHAIN_INCOMPLETE

Ningún resultado es ALLOW, AUTHORIZED, TRUSTED o PROOF_READY. El resultado positivo solo indica que una muestra limitada coincide con el patrón esperado; no autentica al operador ni aprueba el candidato A.

## 2. Alcance de los siete objetivos

### 2.1 Padre directo sudo

El primer proceso observado debe ser el padre directo del observador. Se observa el objeto ejecutable mediante O_PATH/fstat y el destino textual de /proc/PID/exe mediante readlink. Son observaciones separadas y no atómicas; se comparan en dos muestras. Para la clasificación diagnóstica se exige:
- nombre base del destino sudo;
- archivo regular;
- UID/GID del objeto 0/0;
- bit setuid presente;
- ausencia de escritura por grupo y otros.

No se fija inode/hash como ancla permanente y no se afirma identidad de paquete. La verificación del binario sudo aprobado exige una referencia de confianza protegida y revisión administrativa independiente.

Un shell o wrapper como padre directo produce CHAIN_MISMATCH, aunque haya un proceso sudo más arriba.

### 2.2 Credenciales del proceso sudo

Se comparan los cuatro UID y GID de /proc/PID/status. El patrón diagnóstico requiere UID real no root y UID efectivo/saved/filesystem root; GID efectivo/saved/filesystem root. Se exige que los procesos sudo contiguos observados mantengan el mismo UID real.

No se codifica UID 1000 ni se declara que el UID real sea el sujeto canónico aprobado. La vinculación con greed y la configuración protegida siguen pendientes.

### 2.3 Sesión, grupo de procesos y TTY

Se comprueba:
- PPID del observador igual al PID del padre capturado;
- SID del sudo ejecutor igual al SID del observador;
- TPGID del sudo ejecutor igual al PGID del observador;
- stat propio del observador coherente con PID/PPID/SID/PGID obtenidos por syscalls;
- TTY controlador del observador disponible;
- tty_nr del observador igual al tty_nr del padre sudo directo;
- TPGID propio igual al foreground PGID del terminal;
- SID del terminal igual al SID del observador;
- foreground PGID del terminal igual al PGID del observador.

Para el TTY de origen, se identifica el primer ancestro no sudo después de la cadena contigua de procesos sudo. Se exige que su tty_nr sea distinto de cero, coincida con el tty_nr del sudo monitor más externo y que su TPGID corresponda al PGRP de ese monitor.

Esta relación intenta distinguir el PTY de origen del PTY interno que sudo puede crear para el comando. Sigue siendo una inferencia diagnóstica ligada a la topología observada y a la versión/configuración de sudo; no demuestra criptográficamente que el PTY provenga de SSH ni presencia física.

### 2.4 Rechazo de wrappers

La regla se aplica al padre directo, no a la existencia de un sudo en cualquier posición de la ascendencia. Por tanto:
- sudo -- observer: candidato a coincidencia diagnóstica;
- sudo -- sh -c observer: padre directo shell; rechazo;
- ejecución ordinaria sin sudo: padre directo distinto de sudo; rechazo.

El prototipo no intenta convertir wrappers en una cadena aceptable buscando ancestros.

### 2.5 Carreras y sustitución de procesos

- Se abre pidfd para cada proceso observado.
- Se leen status, stat y metadatos del ejecutable dos veces. El fstat del descriptor O_PATH y readlink del enlace procfs son observaciones separadas, no una prueba atómica del mismo instante.
- Se comparan PID, PPID, UID/GID, estado, PGRP, SID, TTY, TPGID, starttime y metadatos del objeto ejecutable.
- Se comprueba liveness del pidfd antes/después.
- Se comprueban los enlaces PPID entre nodos.
- Se vuelve a comprobar stat propio, PPID, SID, PGID y TTY del observador.

Las lecturas procfs no son atómicas. pidfd no congela credenciales, PPID, execve, SID, PGID ni TTY. La doble muestra reduce ventanas de confusión, pero no resuelve todas las carreras. Una transición detectada rechaza o deja incompleta la observación.

### 2.6 SSH sin PTY

La comprobación no se limita a que el observador tenga /dev/tty: sudo puede crear un PTY interno. Se inspecciona también el primer ancestro no sudo que originó la invocación y su relación con el sudo monitor.

Si el ancestro de origen carece de TTY, o su TTY/foreground no coincide con el monitor, se produce CHAIN_MISMATCH. Si sudo no ejecuta el comando porque no puede autenticar sin terminal, el caso es no concluyente y no debe forzarse.

No se usarán sudo -S, NOPASSWD, cambios de timestamp ni modificaciones de sudoers para fabricar el escenario.

### 2.7 Salida no autoritativa y pruebas negativas

La salida enumera nodos observados, credenciales, SID/PGID/TTY, starttime, pidfd y razón diagnóstica. Se escapan bytes de control en destinos ejecutables. La salida termina siempre con AUTHORIZATION=NOT_PROVIDED.

Las pruebas fixture cubren:
- patrón directo con dos procesos sudo y shell de origen con TTY;
- padre directo shell aunque haya sudo más arriba;
- credenciales sudo inesperadas;
- ausencia, discrepancia o foreground incorrecto del TTY de origen;
- SID/foreground incorrectos;
- enlaces PPID inconsistentes;
- pidfd/evidencia ausentes;
- snapshots inestables;
- metadatos que no corresponden a sudo setuid root;
- ausencia de afirmaciones de autorización.

## 3. Implementación

Código separado en tools/bootstrap-chain-observer/; reutiliza únicamente los parsers puros V1. No reutiliza el probe diagnóstico ni cambia el observador V2.

El recolector:
1. captura PID/PPID/SID/PGID y stat propio del observador;
2. abre /dev/tty sin adquirir uno nuevo y conserva el descriptor;
3. camina una cadena de ascendencia acotada hasta el primer ancestro no sudo;
4. abre pidfd para cada nodo;
5. lee status/stat y el objeto exe;
6. repite lecturas y compara snapshots;
7. revalida pidfds, enlaces PPID y estado TTY;
8. evalúa fixtures/reglas y emite un resultado exclusivamente diagnóstico.

No ejecuta comandos externos, no lee variables de entorno para decidir identidad, no escribe archivos ni configuración, no solicita privilegios y no invoca sudo.

## 4. Build y pruebas Debian

Desde la raíz del repositorio:

    sh tools/bootstrap-chain-observer/test_chain.sh

Compilación estricta:
-std=c11 -Wall -Wextra -Wpedantic -Werror -O2

Los binarios se crean en /tmp. Primero deben pasar fixtures y smoke test. Solo después se ejecutan manualmente:
1. usuario ordinario (debe rechazar por padre directo no sudo);
2. sudo local directo (debe coincidir diagnósticamente si la topología instalada satisface el contrato);
3. SSH con PTY y sudo directo;
4. SSH con PTY y shell intermediario (debe rechazar);
5. SSH sin PTY ordinario (debe rechazar por padre no sudo/TTY ausente);
6. opcionalmente SSH sin PTY con sudo solo si la política y timestamp existentes permiten ejecutarlo sin alterar nada; si sudo no lo ejecuta, queda no concluyente.

Resultados manuales reportados por el propietario el 16-11-2026:
- Ejecución ordinaria: `CHAIN_MISMATCH`, padre directo `/usr/bin/bash`.
- Sudo local directo: `CHAIN_PATTERN_MATCHED_DIAGNOSTICALLY`, dos ancestros sudo, `AUTHORIZATION=NOT_PROVIDED`.
- SSH interactivo con PTY, entrando primero a una shell y ejecutando `sudo -- observer`: `CHAIN_PATTERN_MATCHED_DIAGNOSTICALLY`, dos ancestros sudo y primer ancestro no sudo `/usr/bin/bash` con TTY de origen vinculado al monitor sudo.
- SSH con PTY ejecutando directamente `sudo -- observer` como comando remoto: `CHAIN_MISMATCH`, razón `ORIGINATING_TTY_NOT_BOUND_TO_SUDO_MONITOR`; el primer ancestro no sudo fue `sshd-session` con `tty_nr=0` y `tpgid=-1`.
- SSH con PTY y `sudo -- sh -c observer`: `CHAIN_MISMATCH`, padre directo `/usr/bin/dash`.

En una inspección separada de solo lectura, `sshd-session` conservaba descriptores `/dev/ptmx` cuyo `fdinfo` incluía `tty-index` coincidente con el PTY esclavo de la shell SSH (`/dev/pts/2`). Esto demuestra que `tty_nr=0` en `sshd-session` no equivale a que la conexión SSH carezca de PTY. No demuestra por sí solo una asociación segura y estable apta para el observador: V3 no inspecciona ni valida esa relación de descriptores y no se amplía el contrato con base únicamente en esta observación.

Los resultados manuales son evidencia del host y de la versión/configuración actual de sudo, no una garantía para futuras actualizaciones.

## 5. Límites y decisiones todavía abiertas

V3 no valida:
- que el objeto sudo observado sea el paquete/build aprobado;
- la política efectiva completa de sudo ni sus defaults por comando;
- integridad de sudoers y sus includes en todos los escenarios;
- autenticidad de la sesión SSH ni la procedencia criptográfica del PTY;
- resistencia frente a un administrador root malicioso;
- PAM, confirmación del descriptor, configuración protegida, claves, proof/envelope, CAM o Recovery Gate;
- todas las carreras de kernel entre muestras.

Si el comportamiento real de sudo no coincide con el modelo de monitor/TTY, no se relajan las reglas: se documenta el caso como incompleto/inconsistente y se revisa A/B por separado.

## 6. Criterios de cierre

1. Build estricto y pruebas fixture negativas superadas por el propietario en Debian.
2. Observación local ordinaria rechazada.
3. Sudo local directo y SSH interactivo con PTY (shell de sesión seguida de sudo directo) evaluados con salida completa.
4. SSH remoto directo con sudo y shell intermediario evaluados; ambos rechazos documentados según la topología observada.
5. Ausencia de PTY de origen rechazada cuando el comando puede ejecutarse sin modificar políticas.
6. Sanitizers ejecutados si están disponibles.
7. Revisión de código independiente antes de cualquier propuesta de helper privilegiado.

Completar V3 no aprueba A ni autoriza PAM, helper privilegiado, cambios del host o Recovery Gate. La siguiente etapa requiere una revisión específica de política efectiva sudo, trust reference del ejecutable, PAM, TTY interactivo y transporte del proof.


### 4.1 Revalidación local del build y escenarios directos — 2026-11-23

El propietario repitió en Debian 13 / `Atlas-VM-test`:

```text
bootstrap-chain-observer: tests passed
Bootstrap chain observer build and tests completed.
Observer binary: /tmp/atlas-bootstrap-chain-observer
```

La ejecución directa desde `bash` volvió a producir `CHAIN_MISMATCH` con `DIRECT_PARENT_IS_NOT_ROOT_OWNED_SETUID_SUDO`. La invocación `sudo -- /tmp/atlas-bootstrap-chain-observer` produjo `CHAIN_PATTERN_MATCHED_DIAGNOSTICALLY`, con dos procesos sudo contiguos (ejecutor y monitor), shell de origen en el índice 2, `chain_stable=yes`, `pidfds_stable=yes` y `collection_complete=yes`. Ambas rutas mantuvieron `AUTHORIZATION=NOT_PROVIDED`.

Esta reejecución confirma build/tests y los dos escenarios locales en el estado Debian observado; no repitió los escenarios SSH históricos de §4 ni amplía sus conclusiones. En particular, los resultados anteriores distinguen: SSH interactivo con PTY entrando primero a una shell y ejecutando sudo (coincidencia diagnóstica); comando remoto `ssh -t ... 'sudo ...'` (mismatch porque `sshd-session` aparece como origen sin `tty_nr`); y shell intermediaria (mismatch por padre directo `dash`). La observación separada de descriptores `/dev/ptmx` no se ha convertido en una prueba de procedencia TTY segura.

No se ejecutaron pruebas desde GitHub. No hubo cambios en sudoers, PAM, SSH, timestamp, configuración o privilegios del host. Los límites de §5 y la prohibición de interpretar la salida como autorización permanecen sin cambio.


### 5.1 Aclaración de la auditoría estática — 2026-11-23

La revisión estática de `bootstrap_chain_observer.c` confirma que la regla V3 observa el TTY controlador del primer ancestro no sudo (`tty_nr`, `tpgid`) y lo compara con el monitor sudo externo. No inspecciona descriptores `/dev/ptmx`, no asocia el master con el slave de la sesión SSH y no autentica la procedencia del terminal. Por ello, `tty_nr=0` en `sshd-session` no demuestra ausencia de PTY; el resultado `CHAIN_MISMATCH` solo expresa que no se cumplió la relación de TTY controlador implementada. La auditoría completa y los comandos de host read-only están en `local-bootstrap-sudo-tty-static-audit.md`.

La misma revisión confirma que `aco_is_sudo_candidate()` verifica solo basename, tipo regular, UID/GID 0/0, setuid y ausencia de escritura por grupo/otros. No valida paquete, versión aprobada, hash de confianza, plugin ni política sudo efectiva. V3 permanece estrictamente diagnóstica.


### 5.2 Política SSH/PTY adoptada — 2026-11-23

El propietario adoptó la política conservadora: SSH solo se acepta si primero se establece una shell interactiva con PTY y desde ella se ejecuta sudo directamente. Se rechazan el comando remoto `ssh -t host 'sudo ...'`, SSH sin PTY, comandos no interactivos y wrappers/shells intermedias.

Esta decisión define los casos de aceptación futuros; no cambia el comportamiento ni la autoridad del observador V3. La coincidencia V3 en una shell SSH interactiva sigue siendo diagnóstica y no autentica SSH ni la procedencia del PTY. El mecanismo para distinguir de forma estable la shell interactiva de un comando remoto con PTY sigue sin resolverse. No aceptar `sshd-session` ni inspección `/dev/ptmx` como sustituto sin un contrato y pruebas específicos. Si no puede demostrarse fail-closed, Candidate A se descarta sin relajar la política.
