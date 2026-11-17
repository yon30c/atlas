# Diseño V3 — observador diagnóstico de la cadena sudo para bootstrap LOCAL

**Estado:** prototipo diagnóstico publicado; compilación y pruebas Debian pendientes.  
**Aprobación:** el propietario autorizó trabajar conjuntamente los puntos 1–7 el 16-11-2026. La aprobación cubre únicamente el observador C no privilegiado, sus pruebas y documentación. No autoriza helper privilegiado, PAM, instalación, configuración del host ni ejecución de bootstrap.  
**Rama:** feature/terminal-commands.  
**Relacionado:** local-bootstrap-privilege-validation-contract.md, local-bootstrap-observer-v2-design.md, local-bootstrap-privilege-boundary.md.

## 1. Objetivo y resultado

V3 implementa un observador Linux de solo lectura que contrasta una forma acotada de la cadena de procesos del candidato A. Separa expresamente la observación genérica V2 de la pregunta específica: si el proceso actual fue lanzado directamente por un proceso compatible con sudo y si la cadena observada conserva una relación verificable con el TTY de origen.

Resultados permitidos:
- CHAIN_PATTERN_MATCHED_DIAGNOSTICALLY
- CHAIN_MISMATCH
- CHAIN_INCOMPLETE

Ningún resultado es ALLOW, AUTHORIZED, TRUSTED o PROOF_READY. El resultado positivo solo indica que una muestra limitada coincide con el patrón esperado; no autentica al operador ni aprueba el candidato A.

## 2. Alcance de los siete objetivos

### 2.1 Padre directo sudo

El primer proceso observado debe ser el padre directo del observador. Se compara el objeto ejecutable abierto en /proc/PID/exe mediante O_PATH/fstat y readlinkat sobre el mismo descriptor. Para la clasificación diagnóstica se exige:
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
- TTY controlador del observador disponible;
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
- Se leen status, stat y metadatos del ejecutable dos veces.
- Se comparan PID, PPID, UID/GID, estado, PGRP, SID, TTY, TPGID, starttime y metadatos del objeto ejecutable.
- Se comprueba liveness del pidfd antes/después.
- Se comprueban los enlaces PPID entre nodos.
- Se vuelve a comprobar PPID, SID, PGID y TTY del observador.

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
1. captura PID/PPID/SID/PGID del observador;
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

Los resultados manuales son evidencia del host y de la versión actual de sudo, no una garantía para futuras actualizaciones.

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
3. Sudo local directo y SSH con PTY directo evaluados con salida completa.
4. Shell intermediario rechazado por padre directo.
5. Ausencia de PTY de origen rechazada cuando el comando puede ejecutarse sin modificar políticas.
6. Sanitizers ejecutados si están disponibles.
7. Revisión de código independiente antes de cualquier propuesta de helper privilegiado.

Completar V3 no aprueba A ni autoriza PAM, helper privilegiado, cambios del host o Recovery Gate. La siguiente etapa requiere una revisión específica de política efectiva sudo, trust reference del ejecutable, PAM, TTY interactivo y transporte del proof.
