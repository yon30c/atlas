# Contrato de validación de privilegios para bootstrap LOCAL (candidato A)

**Estado:** contrato general de validación pendiente de cierre; alcance V1 del validador aislado aprobado para implementación sin privilegios. Candidato A no aprobado para ejecución privilegiada.  
**Rama:** `feature/terminal-commands`.  
**Fecha:** 16 de noviembre de 2026.  
**Relacionado:** `local-bootstrap-privilege-boundary.md`, `local-pam-bootstrap-authenticator.md`, `local-pam-bootstrap-proof-protocol.md`, `local-bootstrap-coordination-architecture.md`.

## 1. Propósito y decisión actual

Este documento convierte las observaciones del prototipo C en requisitos verificables para evaluar el candidato A: helper C root-owned, ejecutado directamente mediante sudo, con autenticación PAM propia.

El contrato no aprueba A ni autoriza implementar o instalar el helper privilegiado. Define las condiciones que deberán demostrarse antes de considerar ese candidato. Por decisión del propietario del 16-11-2026, queda aprobado únicamente el alcance V1 descrito en `local-bootstrap-validator-v1-design.md`: parser/evaluador aislado basado en fixtures, sin recolector de procesos real, privilegios, PAM, claves, configuración protegida, SQLite ni CAM.

**Decisión provisional:** A continúa como candidato preferido por su menor superficie operativa. B (servicio privilegiado con socket Unix, `SO_PEERCRED` y TTY transferido) permanece como alternativa. Si una condición obligatoria de A no puede demostrarse en el Debian real, no se debilita el requisito: A se descarta y se reevalúa B.

La política de sesión ya acordada admite terminal local y SSH interactivo con PTY; rechaza SSH sin PTY y toda ejecución no interactiva. Un PTY no demuestra presencia física.

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

La política funcional permite terminal local y SSH interactivo con PTY. No se intenta inferir presencia física ni ubicación.

La opción sudo `use_pty` introduce una distinción esencial: el proceso ejecutor puede tener un PTY creado por sudo incluso cuando el cliente SSH no solicitó uno. Por eso, que el helper tenga `/dev/tty`, esté en foreground o comparta SID con el ejecutor no demuestra por sí solo que la sesión de origen tenía PTY.

El diseño debe identificar de forma inequívoca el proceso monitor de sudo (o el contexto de invocación equivalente, específico de la versión/configuración aprobada) y comprobar que conserva la terminal de la sesión iniciadora. La observación anterior de dos PTY distintos en la ejecución indirecta muestra que monitor y ejecutor pueden tener descriptores/terminales diferentes; no basta comparar destinos textuales de FD ni buscar un ancestro con nombre `sudo`.

**Condición obligatoria aún no demostrada:** el monitor de sudo asociado a la invocación debe permitir distinguir una sesión iniciada con PTY de una ejecución SSH sin PTY a la que `use_pty` asigna un PTY interno. Si no puede identificarse y verificarse de forma estable, A no puede cumplir la política de rechazo de SSH sin PTY y debe descartarse o rediseñarse sin relajar la política.

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

### Etapa V1 — parser/evaluador aislado (APROBADA PARA IMPLEMENTACIÓN)

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

La aprobación de V1 autoriza únicamente este trabajo aislado. No autoriza V2, integración con procesos reales, cambios del host ni ejecución privilegiada.

### Etapa V2 — integración de solo observación en Debian

Solo después de revisión del contrato y sin PAM, claves, instalación ni cambios de configuración:
1. ejecución ordinaria sin sudo;
2. sudo directo desde terminal local;
3. sudo directo desde SSH con PTY;
4. shell intermediario;
5. SSH sin PTY, únicamente si el probe puede ejecutarse bajo la autenticación ya disponible sin alterar políticas;
6. pérdida de TTY/foreground durante una interacción simulada.

El caso SSH sin PTY no se declara superado si sudo rechaza antes de ejecutar el probe. No se cambia timestamp, no se habilita NOPASSWD y no se usa stdin para introducir contraseña.

### Etapa V3 — pruebas negativas de autoridad

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

### Etapa V4 — decisión A/B

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

## 12. Prohibiciones fuera del alcance V1 aprobado

No:
- escribir o instalar helper privilegiado;
- modificar PAM, sudoers, systemd, SSH, usuarios, grupos o permisos;
- instalar paquetes;
- generar o provisionar claves;
- crear migraciones o filas CAM;
- abrir Recovery Gate;
- conectar el helper con el runtime;
- aceptar observaciones diagnósticas como autorización.

**Estado de aprobación:** el propietario aprobó el alcance V1 aislado el 16-11-2026. El contrato general permanece abierto y el candidato A no está aprobado. Cualquier ampliación a V2, recolector real, PAM, helper privilegiado o cambios del host requiere diseño, revisión y aprobación separados.
