# Contrato de validación de privilegios para bootstrap LOCAL (candidato A)

**Estado:** V1, V2 y V3 validadas localmente en el alcance documentado; contrato general abierto y Candidate A no aprobado para ejecución privilegiada.  
**Rama de trabajo actual:** `work/atlas-mvp-runtime`.  
**Fecha de actualización:** 23 de noviembre de 2026. La sección 11 conserva el corte histórico del 16-11-2026.  
**Relacionado:** `local-bootstrap-privilege-boundary.md`, `local-pam-bootstrap-authenticator.md`, `local-pam-bootstrap-proof-protocol.md`, `local-bootstrap-coordination-architecture.md`, `local-bootstrap-chain-observer-v3-design.md`, `local-bootstrap-sudo-tty-static-audit.md`.

## 1. Propósito y decisión actual

Este documento convierte las observaciones del prototipo C en requisitos verificables para evaluar el candidato A: helper C root-owned, ejecutado directamente mediante sudo, con autenticación PAM propia.

El contrato no aprueba A ni autoriza implementar o instalar el helper privilegiado. Define las condiciones que deberán demostrarse antes de considerar ese candidato. V1 (parser/evaluador puro), V2 (observador Linux genérico) y V3 (observador diagnóstico de cadena sudo) son prototipos no privilegiados separados. La aprobación del propietario del 16-11-2026 para V3 cubre solo código diagnóstico, pruebas y documentación; no cubre PAM, claves, configuración protegida, SQLite, CAM, instalación ni ejecución privilegiada.

**Decisión provisional:** A continúa como candidato preferido por su menor superficie operativa. B (servicio privilegiado con socket Unix, `SO_PEERCRED` y TTY transferido) permanece como alternativa. Si una condición obligatoria de A no puede demostrarse en el Debian real, no se debilita el requisito: A se descarta y se reevalúa B.

La política de sesión ya acordada admite terminal local interactiva y solo SSH que abre primero una shell interactiva con PTY y después ejecuta sudo/helper directamente. Rechaza ssh -t host 'sudo ...', SSH sin PTY, comandos remotos no interactivos, subsistemas no autorizados y wrappers intermedios. Un PTY no demuestra presencia física.

## 2. Límites e invariantes

1. El helper solo puede realizar una operación fija: presentar el descriptor configurado, recoger confirmación directa, reautenticar mediante PAM al sujeto configurado y emitir una prueba limitada.
2. No es una shell, un runner, un agente, un servicio CAM ni una autoridad de identidad.
3. No acepta argumentos operativos, rutas, usuarios, módulos PAM, claves, descriptor, acción, perfil, epoch ni resultado PAM del caller.
4. No utiliza `PATH`, shell-outs, comandos externos ni variables de entorno para decidir identidad o autoridad.
5. No lee ni escribe SQLite/CAM y no puede abrir Recovery Gate.
6. El sujeto operativo se obtiene de configuración protegida y se resuelve contra la base local de cuentas. Actualmente es `greed` (UID observado 1000); no se codifica ese UID como identidad canónica.
7. `atlas`, `atlas-sandbox`, Assistant y Skills no son propietarios ni sujetos de bootstrap.
8. La reautenticación PAM y `pam_acct_mgmt` son obligatorias. La autenticación de SSH, la caché de sudo o la mera ejecución como root no las sustituyen.
9. Cualquier condición obligatoria ausente, ambigua, inconsistente, inestable o no verificable produce rechazo sin emitir prueba.
10. El diseño no pretende defenderse del operador `greed` actuando maliciosamente como administrador root; esa cuenta conserva sudo irrestricto. Sí debe impedir que procesos Atlas sin privilegios fabriquen o invoquen el flujo como si fueran el propietario.

## 3. Clasificación de las comprobaciones

Cada comprobación futura debe clasificarse como una de estas categorías:

- **Obligatoria:** su fallo o imposibilidad de verificar impide continuar.
- **Defensa adicional:** reduce errores o detecta anomalías, pero no sustituye una condición obligatoria.
- **Diagnóstica:** se registra para análisis; nunca concede ni deniega por sí sola una autoridad, salvo que una regla obligatoria explícita utilice el mismo dato validado.

El prototipo actual es únicamente diagnóstico. Ninguna de sus salidas constituye una decisión de seguridad.

## 4. Contrato de ejecución e identidad

### 4.1 Forma de invocación

La única forma prevista es:

```sh
sudo -- /usr/libexec/atlas/local-bootstrap-authenticator
```

Condiciones:

- `argc == 1`; no se aceptan argumentos.
- No se acepta shell, wrapper, `sudo -u`, `sudo -E`, modo login ni ruta alternativa.
- El helper no se instala setuid y no recibe file capabilities.
- El ejecutable y todos sus directorios padre deben estar protegidos contra escritura por usuarios no confiables.
- El helper debe validar su propia ubicación y metadatos desde objetos abiertos, no confiar en una ruta textual aislada.
- No se añade una regla NOPASSWD ni se modifica la política de sudo para facilitar las pruebas.

### 4.2 Sujeto autorizado

La identidad esperada se obtiene de la configuración protegida del host y se resuelve mediante la base local de cuentas. El helper debe verificar que el UID real del invocador sudo corresponde a ese sujeto y que el proceso sudo tiene los privilegios esperados.

No son pruebas suficientes, por separado ni combinadas sin validación de procedencia:

- `SUDO_UID`, `SUDO_USER`, `USER`, `LOGNAME` o `HOME`;
- UID efectivo 0;
- nombre o ruta textual del proceso;
- PPID aislado;
- propietario del TTY;
- existencia de un proceso sudo en cualquier posición de la cadena.

Las variables sudo pueden servir como señales de coherencia o diagnóstico únicamente después de que la política efectiva de sudo y la cadena del proceso hayan sido validadas por otros medios.

### 4.3 Política efectiva de sudo

Antes de aprobar A debe documentarse, sin modificar el host:

- ruta, versión, paquete e identidad del ejecutable sudo;
- defaults efectivos para la invocación concreta;
- política de entorno: `env_reset`, `env_keep`, `SETENV` y reglas aplicables;
- uso de `use_pty` y comportamiento del monitor/ejecutor;
- reglas que afecten autenticación, timestamp y selección del usuario;
- ausencia de una vía por la que un caller no privilegiado pueda sustituir el ejecutable o falsificar los metadatos usados por el helper.

La configuración se revisa para el comando y sujeto exactos, no solo mediante una búsqueda textual de archivos. Si no puede establecerse la política efectiva, A no se aprueba.

## 5. Contrato de proceso padre y anti-TOCTOU

### 5.1 Padre directo

El helper debe capturar al inicio PID propio, PPID, SID y PGID. El padre directo esperado es el proceso ejecutor de sudo que lanzó el helper.

Requisitos:

1. El PPID observado debe ser válido y distinto del PID del helper.
2. La identidad del padre debe ser compatible con el ejecutable sudo aprobado y con el UID real del sujeto configurado.
3. El padre debe tener las credenciales efectivas esperadas para la ejecución privilegiada.
4. El helper y el padre deben pertenecer a la relación de sesión permitida.
5. Un shell o wrapper como padre directo implica rechazo, aunque exista sudo más arriba en la cadena.
6. No se busca arbitrariamente un sudo entre los ancestros para aceptar una invocación indirecta.

### 5.2 Referencias de proceso

El prototipo futuro debe evaluar el siguiente patrón, sujeto a prueba en el kernel Debian instalado:

- Capturar el PID candidato.
- Abrir pidfd lo antes posible; si `pidfd_open` no está disponible o falla, rechazar A.
- Leer `/proc/<pid>/stat` y `status` con límites estrictos y parseo completo.
- Registrar `starttime` de `stat` para detectar que las lecturas no se refieren a generaciones distintas del PID.
- Abrir `/proc/<pid>/exe` y conservar el descriptor del objeto ejecutable mientras se inspecciona.
- Comprobar que el pidfd no señala terminación y que el PPID observado sigue siendo el esperado.
- Repetir las lecturas críticas inmediatamente antes de cada fase sensible y comprobar que PID, starttime, credenciales, SID y ejecutable conservan la identidad esperada.
- Si el padre termina, cambia de ejecutable, cambia la relación observada o alguna lectura no puede completarse, abortar.

### 5.3 Límites que no deben ocultarse

Un pidfd fija una referencia al proceso, pero no congela su ejecutable, credenciales, PPID, SID, PGID ni descriptores. Un descriptor abierto de `/proc/<pid>/exe` identifica el objeto abierto, pero no impide que el proceso haga `execve`. Las lecturas de procfs no forman una instantánea atómica.

La secuencia `getppid() → pidfd_open() → lecturas de /proc` tiene una ventana de carrera. Comparar PID y `starttime` antes/después reduce confusiones por reutilización, pero no convierte la relación de parentesco en una prueba atómica. El diseño debe describir exactamente qué carreras quedan acotadas y cuáles no.

**Criterio de salida:** si el prototipo no puede demostrar una asociación suficientemente consistente entre el padre directo observado y la ejecución actual, sin depender de una lectura aislada, A se rechaza. No se presentará pidfd como solución completa anti-TOCTOU.

### 5.4 Identidad del ejecutable sudo

No se fija para siempre el inode observado en noviembre de 2026. Las actualizaciones legítimas de sudo pueden cambiarlo.

La referencia de confianza debe proceder de configuración protegida y tener un procedimiento administrativo explícito de actualización. Como mínimo, la comprobación debe considerar:

- descriptor del ejecutable abierto mediante `/proc/<pid>/exe`;
- tipo de archivo regular;
- propietario root y ausencia de escritura por grupo/otros;
- dispositivo/inode y metadatos esperados para la versión aprobada;
- identidad del paquete/versión y mecanismo de actualización de la referencia;
- revalidación para detectar un `execve` del proceso padre.

La ruta devuelta por `readlink` es informativa, no suficiente. El hash/inode observado actualmente sirve como dato diagnóstico, no como ancla de confianza permanente.

## 6. Contrato de sesión y TTY

### 6.1 TTY del helper

El helper debe abrir `/dev/tty` directamente y conservar el descriptor durante toda la operación. Debe comprobar:

- apertura exitosa y `isatty(fd)`;
- `fstat` del descriptor y tipo de dispositivo esperado;
- `tcgetsid(fd)` coincide con `getsid(0)`;
- la sesión del padre sudo satisface la relación aprobada;
- `tcgetpgrp(fd)` coincide con `getpgrp()` antes de cada interacción;
- el descriptor sigue representando el mismo terminal durante la operación;
- pérdida de terminal, EOF, HUP, señal de cierre, cambio de foreground o error de lectura cancela el flujo.

No se usa stdin, stdout, stderr, pipes ni variables de entorno como sustituto del TTY confiable. Los prompts PAM y la confirmación del descriptor se presentan/leen mediante el TTY validado.

### 6.2 Terminal local y SSH

La política funcional cerrada permite terminal local interactiva y SSH únicamente después de una petición de shell interactiva con PTY; desde esa shell se debe invocar sudo/helper directamente. Se rechazan las peticiones SSH exec aunque tengan PTY, SSH sin PTY, comandos remotos no interactivos y wrappers intermedios. No se infiere presencia física ni ubicación.

La opción sudo `use_pty` sigue siendo relevante: el proceso ejecutor puede tener un PTY creado por sudo incluso cuando el cliente SSH no solicitó uno. Sin embargo, el problema es más amplio que detectar un PTY interno. OpenSSH distingue una petición shell de una petición exec antes de ejecutar la login shell: la petición shell se invoca sin `-c`; la petición exec se invoca con `-c <command>`. La asignación de PTY es independiente, por lo que `ssh -t host 'sudo ...'` continúa siendo una petición exec.

La auditoría identificó una alternativa en la frontera de OpenSSH: puerta C root-owned como login shell administrada y `ForceCommand` administrativo fijo, descrita en `local-bootstrap-sshd-session-gate-design.md`. La puerta podría rechazar el comando original antes de ejecutar la shell real y exigir TTY controlador para la petición shell. Es un diseño candidato, no una implementación ni una aprobación.

El helper todavía debe validar la cadena sudo→shell→sshd, el TTY de la shell, el foreground y la ausencia de wrappers. El monitor sudo y el ejecutor pueden conservar PTY distintos; no basta comparar destinos textuales de FD ni buscar un ancestro con nombre sudo. Las carreras procfs/pidfd permanecen.

**Condición obligatoria aún no demostrada:** la puerta y el helper deben distinguir de forma estable shell request interactiva de exec request con PTY, rechazar subsystems que no pasen por la puerta y verificar la invocación directa. Si no puede demostrarse sin relajar la política, Candidate A se descarta y B se evalúa por separado.

No se modificará timestamp, sudoers, NOPASSWD, PAM ni se usará `sudo -S` para forzar una prueba. Si la configuración actual no permite ejecutar la prueba negativa de forma segura, se documenta como no demostrada.

### 6.3 Revalidación durante la interacción

Antes de mostrar el descriptor, antes de aceptar la confirmación, antes de iniciar PAM y antes de emitir la prueba, el helper debe volver a comprobar:

- pidfd y vida del padre;
- identidad y starttime del padre;
- relación de parentesco observada;
- identidad del ejecutable;
- SID y foreground del TTY;
- descriptor de TTY conservado.

Una transición o fallo cancela. La revalidación reduce ventanas de carrera, pero no debe describirse como atomicidad perfecta del kernel.

## 7. Configuración y entorno

- La configuración se abre desde ruta fija, con `O_NOFOLLOW` y validación de cada directorio padre.
- Se valida archivo regular, propietario, permisos, tamaño, formato, versión y canonicalización.
- No se aceptan valores de configuración suministrados por caller.
- Se limpia el entorno después de obtener únicamente las señales de invocación que el diseño haya justificado y validado.
- No se ejecutan programas externos ni se consulta `PATH`.
- Se cierran descriptores heredados no permitidos; el TTY se abre y conserva explícitamente.
- Ningún error de configuración puede provocar fallback a valores por defecto permisivos.

## 8. PAM y confirmación directa

PAM queda fuera del prototipo de validación de proceso. Cuando el contrato de invocación y TTY esté aprobado:

- servicio PAM fijo, revisado y configurado por administración;
- usuario PAM obtenido de configuración protegida;
- conversación PAM exclusivamente por TTY validado;
- `pam_authenticate` y `pam_acct_mgmt` obligatorios;
- confirmación directa del descriptor exacto, presentada y recogida por el helper;
- timeout, cancelación, pérdida de foreground o fallo PAM implican no emitir prueba;
- no registrar contraseña, tokens ni contenido sensible.

El éxito de PAM acredita autenticación del sujeto configurado, no la identidad canónica CAM ni la autorización de génesis.

## 9. Salida y frontera CAM

El helper no toca SQLite/CAM. Solo después de completar validación, confirmación y PAM podrá emitir un envelope firmado, acotado y ligado al descriptor exacto, sujeto, dominio/host, request ID, nonce, proof ID y vigencia.

- stdout transporta únicamente el envelope; stderr solo diagnósticos genéricos.
- El coordinador no confía en exit code ni en el texto de stdout: verifica firma, emisor, host, sujeto, descriptor, acción, vigencia y unicidad.
- La prueba se consume junto con el evento de génesis, identity, owner binding, head y gate en una sola SQLiteUnitOfWork.
- Reintentos idempotentes no crean otra identidad ni otra génesis.
- Cualquier fallo deja Recovery Gate cerrado.

## 10. Plan de verificación por etapas

No ejecutar todavía pruebas que requieran instalar el helper, modificar host o usar PAM. Primero revisar el diseño y luego desarrollar un prototipo C no privilegiado/diagnóstico en `/tmp`.

### Etapa V0 — revisión estática

- Revisar parseo de `/proc/<pid>/stat` (incluido nombre de proceso con espacios/paréntesis) y `status`.
- Revisar límites de buffers, truncamiento, errores y manejo de descriptores.
- Revisar PID/starttime/pidfd y orden de apertura/revalidación.
- Revisar identidad del ejecutable y actualización de referencias.
- Revisar todos los caminos de error y asegurar que ninguno continúa.
- Mantener el probe separado del futuro helper.

### Etapa V1 — parser/evaluador aislado (COMPLETADA Y VALIDADA)

El alcance aprobado se limita estrictamente al documento [Diseño V1 del validador aislado](local-bootstrap-validator-v1-design.md).

Se autoriza implementar en `tools/bootstrap-validator/`:

- parsers puros que reciben bytes y longitud explícita para campos seleccionados de `/proc/<pid>/status` y `/proc/<pid>/stat`;
- validación estricta de gramática, límites, duplicados, truncamiento, PID y `starttime`;
- modelos normalizados que distinguen valores ausentes/no verificables de valores reales;
- evaluador puro sobre snapshots y fixtures;
- únicamente los resultados `OBSERVATION_CONSISTENT`, `OBSERVATION_INCONSISTENT` y `OBSERVATION_INCOMPLETE`;
- pruebas unitarias positivas y negativas de la matriz del diseño V1.

Condiciones obligatorias:

1. El parser no abre archivos ni consulta procfs; no realiza llamadas al sistema.
2. No se reutiliza ni enlaza código de `tools/bootstrap-probe/`.
3. V1 no incluye recolector real, pidfd, lectura de TTY, validación de ejecutables ni inspección del host.
4. No existe resultado de autorización, `ALLOW`, `AUTHORIZED` o `PROOF_READY`.
5. No se genera, serializa ni emite proof o envelope.
6. No se conecta PAM, configuración protegida, claves, sudo, systemd, Broker, SQLite, CAM ni runtime.
7. Los fixtures y binarios se mantienen en el checkout o en rutas temporales no privilegiadas.
8. Compilación estricta y pruebas negativas deben demostrar los estados exactos previstos; los datos incompletos fallan de forma cerrada.

V1 quedó validada mediante compilación estricta, suite ampliada y ejecución con AddressSanitizer/UndefinedBehaviorSanitizer en Debian, según los resultados comunicados por el propietario. La aprobación explícita del propietario del 16-11-2026 autorizó V2 bajo sus límites de solo observación; posteriormente, el propietario confirmó su validación en Debian. La aprobación adicional para V3 se limita al observador diagnóstico de cadena sudo descrito en `local-bootstrap-chain-observer-v3-design.md`, sin instalación ni cambios del host.

### Etapa V2 — observador Linux de solo lectura (COMPLETADA Y VALIDADA EN DEBIAN)

El propietario aprobó expresamente el 16-11-2026 la implementación de V2 según `local-bootstrap-observer-v2-design.md`. El propietario confirmó en Debian compilación estricta, suite automatizada y escenarios manuales local, sudo, SSH con PTY, shell intermediario, ausencia de PTY y cambios de foreground. V2 observa el proceso actual y su padre directo mediante lecturas acotadas de procfs, pidfd, metadatos de `/proc/PID/exe` y consultas TTY. Reutiliza los parsers/evaluador puros V1, sin modificar su semántica.

La aprobación permite escribir y documentar el observador no privilegiado, su suite automatizada y comandos de pruebas manuales. No autoriza instalación, paquetes, cambios del host, PAM, claves, configuración protegida, sudoers, systemd, SSH, Broker, SQLite, CAM, red ni runtime. El programa no invoca sudo ni solicita privilegios; los escenarios sudo/SSH son decisiones manuales del propietario después de recibir el código.

Escenarios de integración previstos:
1. ejecución ordinaria desde terminal local;
2. sudo directo desde terminal local, si el propietario decide probarlo;
3. sudo directo desde SSH con PTY;
4. shell intermediario, que debe aparecer como padre directo y no aceptar un sudo ancestro;
5. SSH sin PTY: registrar ausencia de TTY; si sudo rechaza la ejecución antes de iniciar el observador, el caso queda no concluyente;
6. muestreo de TTY/foreground y cambios observables durante una ventana acotada.

No se cambia timestamp, no se habilita NOPASSWD, no se usa sudo -S y no se altera ninguna política. Los binarios se ejecutan desde `/tmp`. La salida nunca autoriza bootstrap ni prueba la procedencia del PTY.

### Etapa V3 — observador diagnóstico de cadena sudo (IMPLEMENTADO Y VALIDADO LOCALMENTE; SOLO DIAGNÓSTICO)

El propietario autorizó el 16-11-2026 desarrollar conjuntamente los puntos 1–7 como prototipo C no privilegiado. El diseño está en `local-bootstrap-chain-observer-v3-design.md` y el código en `tools/bootstrap-chain-observer/`.

El prototipo observa el padre directo, clasifica metadatos compatibles con sudo setuid root, compara UID/GID, SID/PGID/TTY y el stat propio, recorre la cadena sudo contigua hasta el primer ancestro no sudo, verifica el TTY de origen contra el sudo monitor, abre pidfd para cada nodo y compara dos muestras. Un wrapper como padre directo se rechaza; la presencia de sudo más arriba no lo convierte en directo. Un TTY interno de sudo no debe ocultar que el ancestro de origen carece de TTY.

Resultados limitados a `CHAIN_PATTERN_MATCHED_DIAGNOSTICALLY`, `CHAIN_MISMATCH` y `CHAIN_INCOMPLETE`, siempre con `AUTHORIZATION=NOT_PROVIDED`. La coincidencia no prueba identidad de paquete, política sudo efectiva, autenticidad SSH, presencia física ni autorización. No integra PAM, helper privilegiado, configuración protegida, claves, Broker, SQLite, CAM o runtime.

El propietario ejecutó `sh tools/bootstrap-chain-observer/test_chain.sh` en Debian y comunicó `bootstrap-chain-observer: tests passed`. También completó los escenarios manuales de invocación directa y mediante sudo descritos en §11.1. V3 queda validada localmente solo para esos escenarios. No se alteraron sudoers, timestamp, PAM, SSH ni configuración del host.

### Etapa V4 — pruebas negativas de autoridad

En entorno controlado, después de aprobar explícitamente:
- ejecución directa por greed sin sudo;
- ejecución por root sin padre sudo esperado;
- caller atlas y atlas-sandbox;
- padre inesperado o wrapper;
- argumentos y entorno alterados;
- TTY inexistente, no controlador o no foreground;
- cambio de foreground, cierre de terminal y HUP;
- inconsistencia de configuración/ejecutable;
- fallos PAM y cuenta inactiva.

No ejecutar esta etapa todavía. Requiere diseño y aprobación separados; no implica instalar el helper de producción.

### Etapa V5 — decisión A/B

A solo puede aprobarse si:
- el padre directo y la política sudo son verificables;
- la relación proceso/pidfd no depende de heurísticas aisladas;
- la procedencia de TTY distingue PTY de origen de PTY interno de sudo;
- los casos negativos fallan cerrados;
- el código pasa revisión independiente;
- el propietario aprueba expresamente la implementación privilegiada.

Si cualquier punto no se puede demostrar, A se descarta. B se vuelve a diseñar y evaluar con los mismos requisitos de identidad, TTY, PAM, mínimo privilegio y auditoría; no se adopta automáticamente.

## 11. Estado de evidencia a 16-11-2026

Observaciones recibidas del propietario:

| Caso | Observación | Conclusión permitida |
|---|---|---|
| Shell local sin sudo | UID 1000, bash como padre, TTY foreground válido | Diagnóstico de terminal ordinaria |
| sudo local directo | Padre sudo directo, RUID 1000/EUID 0, TTY foreground | Compatible con patrón A |
| SSH con PTY y sudo directo | Padre sudo directo, RUID 1000/EUID 0, TTY foreground | Compatible con patrón A |
| SSH con PTY y shell intermediario | Padre directo dash; sudo aparece más arriba | Distingue wrapper; debe rechazarse |
| SSH sin PTY directo | No existe TTY controlador | Confirma ausencia de TTY en ejecución directa |
| SSH sin PTY con sudo | Sudo no pudo solicitar contraseña; probe no se ejecutó | No concluyente respecto a `use_pty` tras autenticación válida |

El recorrido de ancestros y el pidfd del probe son lecturas diagnósticas no atómicas. No se ha ejecutado un validador, no se ha probado PAM dentro de helper, no se han emitido pruebas y no se ha modificado el host.

## 11.1 Validación local de V3 — 2026-11-23

El propietario ejecutó en Debian 13, VM `Atlas-VM-test`, checkout `/opt/atlas-dev`:

```text
bootstrap-chain-observer: tests passed
Bootstrap chain observer build and tests completed.
Observer binary: /tmp/atlas-bootstrap-chain-observer
```

Escenarios manuales comunicados:

- Ejecución directa desde la shell interactiva: `CHAIN_MISMATCH`, con razón `DIRECT_PARENT_IS_NOT_ROOT_OWNED_SETUID_SUDO`. La shell `bash` era el padre directo. Resultado esperado: no aceptar una invocación que no venga directamente del patrón sudo.
- Ejecución `sudo -- /tmp/atlas-bootstrap-chain-observer`: `CHAIN_PATTERN_MATCHED_DIAGNOSTICALLY`. Se observaron dos procesos sudo contiguos (ejecutor y monitor), seguidos por la shell de origen. `chain_stable=yes`, `pidfds_stable=yes` y `collection_complete=yes`; el ancestro de origen se encontró en el índice 2. El primer intento de contraseña fue rechazado por sudo; el segundo permitió ejecutar el observador.
- Ambos resultados mantuvieron `AUTHORIZATION=NOT_PROVIDED`.

**Alcance validado:** compilación/build y pruebas automatizadas del observador; clasificación diagnóstica de la ejecución directa como mismatch; coincidencia diagnóstica de la cadena sudo interactiva observada en esta VM.

**No repetido en esta ejecución del 23-11:** los escenarios SSH con/sin PTY, wrapper/shell intermediaria y root sin sudo. El diseño V3 conserva resultados manuales históricos del propietario para SSH: shell SSH interactiva con PTY seguida de sudo directo coincidió; el comando remoto `ssh -t ... 'sudo ...'` y el wrapper fueron rechazados por la topología observada. Véase §4 y §5 de `local-bootstrap-chain-observer-v3-design.md`. Esos resultados no demuestran autenticidad SSH ni procedencia criptográfica del TTY. Siguen pendientes la política sudo efectiva, identidad del paquete y validación PAM. La salida no demuestra autorización ni presencia física. La observación de dos procesos sudo no elimina las limitaciones TOCTOU de procfs/pidfd descritas arriba. La auditoría estática posterior precisa que V3 comprueba la relación del TTY controlador del primer ancestro no sudo con el monitor, no la procedencia del canal SSH ni la mera asignación de un PTY; la política efectiva y el binario sudo aprobado tampoco quedan verificados por V3. Véase `local-bootstrap-sudo-tty-static-audit.md`.

**Decisión:** V3 pasa de pendiente a validada localmente para el alcance anterior. Esto no aprueba el candidato A, no habilita helper privilegiado y no autoriza cambios en PAM, sudoers, systemd, claves, SQLite, CAM o el host. A sigue provisional; antes de decidir A/B deben cerrarse las comprobaciones obligatorias restantes, en particular la procedencia del TTY y la política efectiva de sudo.

## 12. Prohibiciones fuera del alcance V1–V3 aprobado

No:
- escribir o instalar helper privilegiado;
- modificar PAM, sudoers, systemd, SSH, usuarios, grupos o permisos;
- instalar paquetes;
- generar o provisionar claves;
- crear migraciones o filas CAM;
- abrir Recovery Gate;
- conectar el helper con el runtime;
- aceptar observaciones diagnósticas como autorización.

**Estado:** V1, V2 y V3 completadas y validadas localmente en el alcance documentado. El contrato general permanece abierto y el candidato A no está aprobado para ejecución privilegiada. La validación V3 no constituye autorización; las pruebas negativas restantes, decisión A/B, PAM, helper privilegiado o cambios del host requieren diseño, revisión y aprobación separados. La política efectiva de sudo, la referencia de confianza del ejecutable y la semántica de SSH interactivo/PTy siguen abiertas; véase la auditoría estática. Las pruebas negativas restantes, decisión A/B, PAM, helper privilegiado o cambios del host requieren diseño, revisión y aprobación separados.


## 13. Auditoría estática de sudo, ejecutable y TTY — 2026-11-23

Se añadió `local-bootstrap-sudo-tty-static-audit.md`. La revisión de código confirma que V3 clasifica sudo por basename, archivo regular, UID/GID 0/0, setuid y ausencia de escritura por grupo/otros; no verifica identidad de paquete, hash contra una referencia protegida, política efectiva ni integridad de sudoers. Su comprobación TTY exige que el primer ancestro no sudo tenga TTY controlador y que coincida con el monitor sudo externo; no inspecciona el PTY master de `sshd-session` ni autentica procedencia SSH. Por ello, el rechazo histórico de `ssh -t host 'sudo ...'` no demuestra que no hubiera PTY: solo que el ancestro no cumplió la regla de TTY controlador.

La evidencia histórica reportada para Debian es sudo 1.9.16p2, defaults `env_reset`, `mail_badpass`, `secure_path`, `use_pty` y autorización irrestricta `(ALL : ALL) ALL` para `greed`; falta reconfirmar la política efectiva completa y la identidad/integridad del binario. El acceso root irrestricto define el límite de amenaza: Candidate A no protege frente a `greed` actuando como root. No se han realizado cambios de host ni pruebas desde GitHub. Candidate A continúa bloqueado por política efectiva, trust reference del ejecutable y semántica/procedencia TTY.


## 14. Política SSH/PTY aprobada — 2026-11-23

El propietario eligió la recomendación conservadora:

- Aceptar terminal local interactiva con sudo directo.
- Aceptar SSH únicamente cuando se inicia primero una shell interactiva con PTY y desde esa shell se ejecuta sudo/helper directamente.
- Rechazar `ssh -t host 'sudo ...'`, aunque el cliente solicite PTY.
- Rechazar SSH sin PTY y cualquier comando remoto no interactivo.
- Rechazar shell o wrapper intermedio entre la shell interactiva y sudo/helper.

Esta es una **decisión de política**, no una afirmación de que V3 pueda verificarla. V3 sigue siendo observador diagnóstico; su coincidencia no constituye autenticación de SSH, procedencia de PTY ni autorización.

El diseño técnico debe demostrar la distinción de forma estable y fail-closed. No se debe inferirla únicamente de `tty_nr`, `tpgid`, basename de procesos o la presencia de un descriptor `/dev/ptmx`. Si no se puede demostrar sin relajar la política, Candidate A se descarta y Candidate B se evalúa por separado con los mismos requisitos. La política general de sudo irrestricto de `greed` sigue fuera de la protección que Candidate A puede ofrecer frente a ese usuario actuando como root.

**Estado:** decisión funcional cerrada; mecanismo de verificación abierto; Candidate A no aprobado; sin cambios de host ni pruebas privilegiadas.


## 15. Puerta SSH en la frontera de OpenSSH — 2026-11-23

La auditoría estática identificó que OpenSSH diferencia la petición de shell de la petición de comando antes de ejecutar la login shell: la primera usa argv de login sin -c; la segunda usa -c <command>. La asignación de PTY es independiente. Por tanto, V3 no puede inferir esa diferencia a partir del TTY controlador del primer ancestro no sudo.

Se documentó como alternativa una puerta C root-owned configurada como login shell administrada, junto con ForceCommand administrativo fijo. La puerta sería el primer ejecutable del usuario, rechazaría comandos originales/subsystems y solicitudes sin TTY, y haría execve() de la shell real solo para la petición interactiva aprobada. El diseño está en local-bootstrap-sshd-session-gate-design.md.

**No es implementación ni aprobación de Candidate A.** Antes de cualquier prototipo deben cerrarse la versión exacta de OpenSSH, configuración efectiva de todos los listeners, variables de entorno no falsificables, cuenta/login shell administrada, subsystems, forwarding, relación shell→sshd, wrappers y reemplazos mediante exec. La puerta no resuelve por sí sola las carreras de procfs ni demuestra que el proceso shell no haya sido reemplazado. Si no se puede validar cada requisito, A se descarta sin relajar la política.

La verificación reportada por el propietario sudo dpkg -V sudo terminó sin salida; se registra solo como ausencia de discrepancias reportadas por dpkg, no como raíz de confianza ni política segura.
