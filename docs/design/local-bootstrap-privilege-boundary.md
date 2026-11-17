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

No se aprueba todavía el mecanismo A ni B. Tras inspeccionar el host se elegirá:

- **A** solo si sudo establece metadatos de invocador confiables, el entorno está saneado y el TTY se puede vincular inequívocamente al sujeto.
- **B** si cualquiera de esas condiciones no puede demostrarse.

Después se fijarán la ruta del binario, los permisos exactos, el contrato de stdout, el cierre de descriptores y las pruebas negativas. No se instalará helper, no se cambiará sudoers ni systemd y no se tocará PAM hasta que el diseño se cierre y el propietario apruebe la implementación.