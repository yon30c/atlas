# Diseño del probe A-IPC-01 — listener Unix propio en directorio privado

**Estado:** diseño aprobado e implementación experimental preparada en rama separada; revisión estática de GitHub completada con una corrección de determinismo en A14; pendiente de inspección local y ejecución por el propietario. No validado; no aprobado como transporte de producción.
**Fase:** 2.5 — evaluación experimental de propiedad del endpoint IPC.  
**Alternativa evaluada:** A — listener creado por el propio proceso sobre un pathname AF_UNIX dentro de un directorio privado.  
**Contrato de aplicación:** `atlas-admin/1`; este probe no modifica el contrato ni amplía el catálogo de operaciones.

## 1. Objetivo

Obtener evidencia local, reproducible y no destructiva de que un proceso puede crear y administrar un endpoint AF_UNIX de filesystem sin apropiarse de una ruta ocupada, sin modificar objetos preexistentes y sin eliminar objetos que no sean el socket creado por esa misma instancia.

El probe debe evaluar por separado:

1. propiedad y creación atómica del pathname mediante `bind()`;
2. permisos del directorio y del socket;
3. aceptación y cierre de conexiones;
4. identificación del peer mediante `SO_PEERCRED` y decisión de autorización separada;
5. límites de concurrencia, lectura, escritura y desconexión;
6. limpieza condicionada del endpoint propio;
7. comportamiento ante fallos y reinicios simulados.

El resultado es evidencia para una decisión arquitectónica posterior. Un PASS no autoriza listener persistente, daemon, systemd, acceso SQLite ni operaciones administrativas.

## 2. Contexto y motivación

El handler actual de `atlas-admin/1` atiende una conexión ya aceptada. No crea un listener persistente. La alternativa B (systemd socket activation sobre filesystem) permanece suspendida por la colisión destructiva observada en Debian 13 / systemd 257.13: al intentar iniciar un socket sobre una ruta que contenía un archivo regular, el contenido sentinel fue alterado.

La alternativa A evita delegar la creación del pathname a systemd: el proceso experimental crea el socket con `bind()`. En Linux, una ruta ya ocupada debe producir un error de colisión; el probe debe comprobar empíricamente que el objeto preexistente y su destino permanecen intactos en cada caso.

Esta expectativa no se presenta como garantía suficiente por sí sola: deben medirse los errores reales, el estado posterior y los límites de carrera.

## 3. Alcance

### Incluido

- Programa de prueba independiente y opt-in, ejecutado sin privilegios.
- Directorio temporal exclusivo por ejecución y pathname único por caso.
- Socket `AF_UNIX/SOCK_SEQPACKET` para conservar compatibilidad con el handler existente.
- `bind()`, `listen()`, `accept()` y cierre controlado.
- Pruebas de colisión con archivo regular, symlink, socket activo y socket stale.
- Verificación de inode/tipo/permisos y contenido sentinel antes/después.
- Pruebas de conexión, credenciales kernel, rechazo de peer no autorizado cuando pueda prepararse un UID distinto sin elevar privilegios, desconexión, truncamiento, ancillary y timeouts.
- Evidencia explícita de escenarios omitidos por limitaciones del entorno.
- Cleanup de los recursos creados por el probe, limitado a su directorio temporal.

### Excluido

- Implementar el listener de producción o convertirlo en servicio.
- Cambiar el handler de protocolo o el contrato `atlas-admin/1`.
- Ejecutar cualquiera de las siete operaciones administrativas; el probe solo puede usar `authority.ping` o un fixture equivalente inocuo.
- Abrir, crear, migrar, inspeccionar o modificar SQLite.
- Instalar o activar unidades systemd, sockets, timers o servicios.
- Crear usuarios/grupos, cambiar permisos del host, usar sudo, setuid, capabilities o modificar PAM/sudoers.
- Cambiar UID/GID del proceso para fabricar un caso de prueba.
- Limpiar automáticamente sockets stale o cualquier pathname que no haya sido creado por la instancia actual.
- Conectarse a sockets, directorios o servicios reales de Atlas.
- Declarar separación de privilegios, aislamiento frente a root o seguridad de producción.

## 4. Modelo de ejecución aislada

El ejecutor crea un directorio temporal privado mediante una API segura de creación de directorios temporales (por ejemplo, `mkdtemp`) bajo el directorio temporal del usuario.

Precondiciones verificadas en runtime:

- proceso no ejecutado como UID 0;
- directorio recién creado, propiedad del UID efectivo del proceso;
- directorio de tipo directorio, no symlink, con modo efectivo `0700`;
- pathname del socket derivado exclusivamente del directorio temporal de esa ejecución;
- pathname suficientemente corto para los límites de `sockaddr_un`;
- no hay rutas configurables que permitan apuntar a recursos persistentes;
- no se siguen enlaces simbólicos para preparar o limpiar el endpoint.

Si alguna precondición no se cumple, el probe aborta antes de crear sockets y reporta `SKIP/ENVIRONMENT_NOT_SAFE` o fallo de precondición, sin intentar reparar permisos.

Cada caso utiliza un subdirectorio o pathname único. Los tests de colisión preparan el objeto dentro del espacio temporal del propio test; nunca reutilizan una ruta conocida del host.

## 5. Contrato de creación y propiedad

### 5.1 Secuencia de creación

1. Crear/verificar el directorio privado.
2. Crear un socket `AF_UNIX/SOCK_SEQPACKET`.
3. Aplicar una umask restrictiva antes de `bind()`, preservando/restaurando la umask del proceso en un bloque garantizado.
4. Invocar `bind()` directamente sobre el pathname.
5. No realizar un patrón `lstat() -> unlink() -> bind()` ni ninguna limpieza preventiva.
6. Tras éxito, obtener `lstat()` del pathname y registrar identidad observada: dispositivo, inode, tipo y modo.
7. Verificar que el objeto es un socket y reside dentro del directorio privado.
8. Aplicar/verificar el modo de socket esperado, si la plataforma lo permite, sin relajar el modo del directorio.
9. Solo después, invocar `listen()` y comenzar a aceptar conexiones.

El modo esperado del socket en este experimento es exactamente `0600`; el modo del directorio temporal es exactamente `0700`. Estos valores son requisitos del probe, no una política de producción. La prueba debe registrar los modos observados y fallar si son más permisivos o no coinciden con el valor fijado.

### 5.2 Colisión

Si `bind()` falla porque el pathname está ocupado:

- no ejecutar `unlink()`, `rename()`, `chmod()` ni escritura sobre el objeto;
- no intentar recuperar automáticamente sockets stale;
- comprobar que el objeto conserva tipo, dispositivo/inode y contenido o destino según corresponda;
- clasificar el errno observado sin depender de un único errno como única evidencia;
- cerrar el descriptor del socket no enlazado y finalizar el caso.

El comportamiento esperado para cualquier objeto preexistente es **fallo cerrado sin modificación**.

### 5.3 Propiedad durante cleanup

Al crear correctamente el socket, la instancia captura `st_dev`, `st_ino` y tipo de archivo mediante `lstat()`. En cleanup:

1. detener aceptación y cerrar el listener;
2. hacer `lstat()` del pathname sin seguir symlinks;
3. comprobar que sigue siendo un socket y que dispositivo/inode coinciden con la identidad capturada;
4. si coincide, intentar eliminar exclusivamente ese pathname;
5. si no coincide, desapareció o la inspección falla, no eliminar nada y reportar `CLEANUP_SKIPPED_OWNERSHIP_MISMATCH`;
6. eliminar únicamente el directorio temporal propio cuando esté vacío; no usar borrado recursivo indiscriminado.

**Límite TOCTOU:** la secuencia de inspección y unlink no es una operación atómica. El directorio privado reduce la exposición a otros UIDs, pero no protege frente a root ni frente a procesos maliciosos con el mismo UID. El probe debe documentar este límite y no presentar la comparación inode como garantía absoluta frente a esos actores.

## 6. Matriz de escenarios obligatorios

| ID | Preparación temporal | Acción | Resultado esperado |
|---|---|---|---|
| A01 | Directorio privado y pathname libre | Crear, bind, listen, aceptar y cerrar | PASS; socket creado y verificable |
| A02 | Archivo regular con contenido sentinel | Intentar bind | Falla; contenido, inode y tipo intactos |
| A03 | Symlink a sentinel dentro del sandbox | Intentar bind | Falla; symlink y destino intactos |
| A04 | Segundo listener activo en pathname | Intentar segundo bind | Falla; primer listener sigue operativo |
| A05 | Socket stale creado por fixture y cerrado sin unlink | Intentar bind | Falla; pathname stale permanece intacto |
| A06 | Listener propio con pathname sustituido por fixture controlado | Ejecutar cleanup | No elimina el objeto sustituto; reporta mismatch |
| A07 | Listener propio sin sustitución | Ejecutar cleanup | Elimina solo el socket propio y deja directorio vacío |
| A08 | Conexión válida | Enviar un único paquete válido de ping | Una respuesta conforme a `atlas-admin/1`; cierre de conexión |
| A09a | Listener candidato: directorio 0700, socket 0600; cliente con UID distinto | Intentar acceder y conectar | DAC bloquea antes de accept(); no afirmar que SO_PEERCRED fue consultado |
| A09b | Fixture temporal separado y accesible a otro UID | Cliente externo conecta y envía | SO_PEERCRED observa UID real; handler rechaza con UNAUTHORIZED_PEER sin respuesta |
| A10 | Peer permitido | Conectar y enviar | Se procesa conforme al handler actual |
| A11 | Peer desconecta antes/durante envío | Procesar | No crash; no se informa éxito ficticio |
| A12 | Paquete truncado o ancillary prohibido | Procesar | Cierre sin respuesta según contrato |
| A13 | Cliente no envía paquete | Esperar timeout | Recurso liberado al vencer timeout |
| A14 | Conexiones simultáneas por encima del límite | Saturar listener | Backpressure/rechazo controlado; memoria y tareas acotadas |
| A15 | Cierre ordenado del listener | Reintentar conexión | Conexión nueva falla; no queda descriptor abierto |
| A16 | Dos procesos/hilos de prueba intentan `bind()` simultáneamente sobre el mismo pathname libre del sandbox | Ejecutar ambos binds concurrentemente y observar resultados | Exactamente un bind gana; el otro falla por colisión; el listener ganador permanece operativo y ningún objeto se modifica |

A09 se divide en dos evidencias independientes porque DAC del pathname y autorización de aplicación son capas distintas:

- **A09a — aislamiento DAC:** utiliza el endpoint candidato sin alterar directorio 0700 ni socket 0600. Un proceso externo con UID distinto intenta acceder; el kernel debe denegar el acceso antes de accept(). Esto demuestra aislamiento filesystem, no que SO_PEERCRED haya sido leído ni que la allowlist haya rechazado al peer.
- **A09b — autorización SO_PEERCRED:** utiliza un fixture temporal separado, no el endpoint candidato. Para permitir que un UID distinto llegue al listener, el fixture puede usar un directorio atravesable pero no escribible por otros UIDs (por ejemplo 0711) y un socket de prueba conectable (por ejemplo 0666). Estos permisos son exclusivos del fixture efímero; nunca se aplican al listener candidato ni se presentan como configuración de producción. El handler debe leer las credenciales del kernel y rechazar al UID externo antes de procesar la solicitud, sin respuesta de protocolo.
- **Ubicación obligatoria del fixture A09b:** debe ser un directorio temporal hermano del sandbox privado, directamente bajo un directorio temporal compartido y seguro (por ejemplo `/tmp` con sticky bit), nunca un hijo del root `0700` del probe. El fixture propio será `0711` y el socket `0666`; el directorio padre compartido debe impedir que otro UID sustituya/elimine el fixture (preferiblemente sticky bit). Si no puede verificarse esa topología y sus permisos, A09b se marca `SKIP`.
- Ambos escenarios requieren una identidad no privilegiada distinta ya disponible y un cliente lanzado externamente bajo esa identidad. El runner no crea cuentas, no cambia UID/GID, no usa sudo y no modifica el host. Si falta esa identidad o no puede orquestarse el cliente externo de forma segura, cada subescenario no demostrado se marca `SKIP` con causa y el resultado global permanece `INCOMPLETE`.
- A09b no debe simular credenciales ni sustituir el intercambio real de SO_PEERCRED por mocks. El fixture permisivo no reduce ni altera los modos exigidos para el endpoint candidato.

A06 utiliza únicamente un fixture del sandbox para simular sustitución. No intenta reproducir ni volver a ejecutar la colisión destructiva histórica de systemd.

## 7. Credenciales y autorización

- El listener obtiene las credenciales del peer aceptado mediante `SO_PEERCRED` antes de leer el paquete.
- La estructura de credenciales debe respetar los tipos Linux: PID con signo; UID/GID sin signo.
- La política de autorización se mantiene separada de la identificación del peer.
- El probe usa una allowlist de prueba explícita, inmutable durante la ejecución y no derivada de datos enviados por el cliente.
- Un UID identificado pero no permitido no recibe respuesta.
- **DAC y autorización no son la misma prueba:** A09a verifica que el filesystem impide alcanzar el endpoint privado; A09b verifica que el handler rechaza un peer distinto después de que la conexión llegó al listener.
- A09b utiliza un fixture temporal con permisos distintos a los del endpoint candidato. No se deben relajar los modos `0700/0600` de A01 para forzar una conexión multi-UID.
- No se interpreta `SO_PEERCRED` como identidad Atlas, identidad humana ni autorización de dominio.
- La evidencia de un único UID no demuestra aislamiento entre cuentas Linux.
- El probe no cambia UID/GID, no usa `setuid()`, no ejecuta `sudo` y no crea cuentas.

## 8. Concurrencia y límites de recursos

La implementación experimental declara estos límites fijos:

- backlog de `listen()`: 8;
- máximo de conexiones activas en el harness de aceptación: 2 workers;
- tamaño máximo de request del handler: 16 KiB;
- tamaño máximo de respuesta del handler: 64 KiB;
- timeout de lectura y escritura del handler en el harness: 0.35 s cada uno (menor que el default del handler, 5 s; nunca supera el máximo contractual de 60 s);
- exactamente una solicitud por llamada al handler y por conexión aceptada en el harness;
- espera máxima de aceptación en los escenarios de ping: 8 s;
- saturación: hasta 8 intentos de cliente; workers adicionales se rechazan sin crear threads adicionales.

A14 verifica que el harness no supera dos workers activos, que ocupa ambos slots y rechaza al menos una conexión excedente, y que recupera capacidad después de cerrar los clientes. Los workers admitidos esperan en una compuerta exclusiva del test hasta observar la saturación; así, la comprobación no depende de que el timeout de lectura o la planificación de hilos mantengan ocupados los slots. Las excepciones inesperadas de workers se conservan como fallo en vez de descartarse. El harness es código de prueba; no es el listener de producción ni una recomendación de capacidad.

**Límites de evidencia:** no se impone un límite global de descriptores al proceso ni un watchdog global que interrumpa cualquier escenario a los 8 s. Las operaciones bloqueantes del runner tienen timeouts acotados y se registran duraciones, pero el campo de 8 s solo representa la espera máxima de aceptación indicada, no un timeout global por escenario. Estos puntos quedan como límites explícitos del experimento y no deben describirse como verificados.

## 9. Estructura de implementación

La implementación opt-in está consolidada en:

```text
tests/integration/private_unix_listener/
    README.md
    run_probe.py
```

- `README.md`: alcance, límites, escenarios, clasificación y comando local.
- `run_probe.py`: preflight, sandbox privado, escenarios A01–A16 aplicables, salida JSON y cleanup limitado por identidad.

Se reutiliza el handler existente desde `src/atlas/platform_admin_ipc.py`; no se modifica ese módulo ni el contrato. Se eligió un único ejecutor para que el probe sea explícito y no se incorpore accidentalmente a la suite unitaria predeterminada. Los escenarios siguen separados por identificador y se detienen al primer FAIL.

La implementación cubre A01–A08, A10–A16. A09a/A09b quedan SKIP deliberado: el runner no cambia UID/GID, no usa sudo y no crea identidades. Por tanto, un recorrido sin otros fallos termina como INCOMPLETE, no PASS. A14 utiliza un harness de prueba con un máximo fijo de dos workers y backlog ocho; no representa ni fija capacidad de producción.

## 10. Salida y clasificación

El ejecutor debe emitir por escenario:

- identificador;
- resultado `PASS`, `FAIL` o `SKIP`;
- errno/causa cuando aplique;
- tipo, modo, dispositivo e inode antes/después cuando aplique;
- confirmación de integridad del sentinel/destino;
- UID/GID/PID observados (sin datos sensibles adicionales);
- duración y motivo de skip;
- confirmación de cleanup o razón por la que se omitió.

Resultado global:

- **PASS:** todos los escenarios obligatorios aplicables pasan; los SKIP condicionales están enumerados. No significa aprobación de producción.
- **FAIL:** cualquier objeto preexistente cambia, se elimina o se sigue de forma no prevista; cleanup elimina un objeto sustituto; el listener se bloquea/crashea; el peer no autorizado obtiene respuesta; se exceden límites; o se produce una operación no prevista.
- **INCOMPLETE:** un requisito esencial no puede probarse en el entorno (por ejemplo, UID distinto) o el escenario se omite por limitación ambiental. No convertir INCOMPLETE en PASS global.

El resultado debe incluir versión kernel, versión Python, plataforma, UID efectivo del ejecutor, ruta temporal raíz (sin secretos), configuración de límites y versión/commit del checkout.

## 11. Criterios de aceptación

El probe solo se considera técnicamente satisfactorio si:

1. no modifica ningún objeto preexistente en ninguna colisión;
2. nunca elimina un pathname que no pueda demostrar que corresponde al socket creado por esa instancia;
3. el directorio y socket respetan los límites de permisos fijados para el experimento;
4. un segundo bind no interfiere con el primer listener;
5. la identificación del peer ocurre antes de procesar datos;
6. un peer no autorizado no recibe respuesta;
7. cada conexión procesa como máximo una solicitud;
8. desconexión, truncamiento, ancillary y timeout se resuelven sin crash ni resultado ficticio;
9. concurrencia y recursos permanecen acotados;
10. los SKIP y límites del modelo de amenaza se informan sin ocultarlos;
11. todos los recursos temporales del probe se limpian o queda una explicación verificable de por qué se omitió cleanup.

Un único cambio de contenido, destino, tipo o inode inesperado en un objeto preexistente constituye FAIL inmediato y detiene la ejecución restante.

## 12. Modelo de amenaza y limitaciones

El probe busca proteger frente a colisiones accidentales y procesos de otros UIDs que no puedan modificar el directorio privado. No demuestra protección frente a:

- root o procesos con capabilities suficientes;
- procesos maliciosos bajo el mismo UID;
- compromiso del proceso Atlas o de su intérprete;
- reemplazo de pathname mediante carrera por un actor con acceso al directorio;
- ataques de agotamiento de recursos fuera de los límites medidos;
- vulnerabilidades del kernel o de la biblioteca;
- identidad humana o autorización Atlas.

La privacidad del directorio es una condición de aislamiento del experimento, no una frontera de seguridad contra el mismo propietario del UID.

## 13. Secuencia de trabajo posterior a la aprobación

1. Revisar el diseño contra el árbol de tests y el contrato IPC.
2. Mantener directorio `0700`, socket `0600`, sin cambios de UID/GID ni privilegios.
3. Preparar el probe en una rama separada sin cambiar handler, runtime ni listener productivo. **Completado en código; pendiente de revisión local.**
4. Revisar el diff y las condiciones de cleanup, colisiones, timeout, concurrencia y clasificación. **Revisión manual en GitHub completada; queda pendiente la validación local.**
5. El propietario ejecuta el comando opt-in en Debian y conserva el JSON y commit exacto.
6. Registrar PASS/FAIL/SKIP/INCOMPLETE sin convertir un SKIP esencial en PASS.
7. Revisar resultados y código. Solo entonces comparar A con C y decidir si merece un prototipo posterior.
8. Cualquier listener persistente o transporte de producción requiere diseño y aprobación independientes.

## 14. Comando de ejecución

El entrypoint opt-in está preparado, pero no se ha ejecutado ni validado. Desde la raíz del checkout y como usuario ordinario:

```bash
PYTHONPATH=src python tests/integration/private_unix_listener/run_probe.py
```

No usar sudo. El runner rechaza UID 0, usa exclusivamente un sandbox temporal propio y no toca servicios ni rutas Atlas existentes. Código de salida: 0 = PASS; 1 = FAIL; 2 = INCOMPLETE. A09 está deliberadamente omitido, por lo que el resultado global esperado sin fallos será INCOMPLETE hasta que exista una forma segura de probar otro UID sin que el runner cambie credenciales o el host.

La revisión manual del diff en GitHub está completada; el propietario debe confirmar el HEAD local y ejecutar el comando en Debian. No se han ejecutado pruebas ni compilaciones desde GitHub.

## 15. Decisión pendiente

Este documento define el experimento, no selecciona el transporte IPC definitivo. La alternativa A continúa siendo candidata. La alternativa B permanece suspendida por la colisión destructiva observada. La alternativa C (AF_UNIX abstract namespace) conserva riesgos distintos y requiere un probe separado.

**No se autoriza con este documento:** listener persistente, daemon, activación systemd, cambios de host, usuarios/grupos, permisos, privilegios, acceso SQLite, provisioning, mutaciones administrativas ni despliegue.


### Requisito adicional de topología para A09b

El sandbox principal del runner permanece `0700` y no puede ser atravesado por otro UID. Por tanto, no basta con crear un subdirectorio `0711` dentro de ese sandbox: el control DAC del directorio padre seguiría bloqueando el acceso antes de llegar al socket. El fixture A09b debe crearse como directorio temporal independiente, hermano del sandbox principal, directamente bajo un directorio temporal compartido que haya superado preflight de seguridad (p. ej. `/tmp` con sticky bit). El fixture independiente tendrá modo `0711`, pertenecerá al UID ejecutor y contendrá el socket de prueba `0666`. Nunca se cambiarán los modos del sandbox principal ni del endpoint candidato.

La ejecución requiere dos sesiones de usuario ordinario ya autenticadas: una mantiene el runner/servidor y la otra ejecuta el cliente bajo un UID distinto preexistente. El runner no invoca `sudo`, `su`, `runuser`, `setuid`, systemd ni mecanismos para cambiar credenciales. Si el propietario no dispone de una segunda sesión real y controlable, A09a/A09b permanecen SKIP; no se sustituye esa condición por una identidad simulada.


## 16. Diseño de coordinación externa para A09a/A09b — 2026-11-21

### 16.1 Evidencia nueva y estado real de SSH

El propietario confirmó en Debian que la clave Ed25519 temporal está instalada y restringida en `authorized_keys` con `from="127.0.0.1",restrict` y el comando forzado `/usr/bin/id -u`. Ejecutó una conexión SSH a `127.0.0.1:22` con autenticación exclusivamente por clave, host key ED25519 verificada estrictamente y sin PTY; la salida fue `1001`.

Esto confirma autenticación SSH de la cuenta `atlas-a09-test` (UID 1001) y ejecución del comando forzado actual. **No** demuestra A09a, A09b ni que el helper de cliente exista. El comando forzado actual `/usr/bin/id -u` no puede realizar las operaciones de socket requeridas.

La documentación anterior que indicaba que no había clave ni login probado queda supersedida por esta evidencia, sin cambiar el hecho de que SSH/PAM/firewall globales no fueron modificados.

### 16.2 Modelo de coordinación seleccionado para el diseño

Se propone que el runner sea el orquestador de dos procesos independientes:

1. El proceso servidor/runner permanece bajo el UID ordinario del propietario del checkout (actualmente 1000).
2. El runner inicia un cliente SSH local mediante `subprocess`. El proceso cliente SSH también se ejecuta localmente bajo el UID 1000; el proceso remoto que sshd inicia por la clave restringida se ejecuta como `atlas-a09-test` (UID 1001).

El runner no cambia sus credenciales y no invoca `sudo`, `su`, `runuser`, `setuid`, capabilities ni systemd. La identidad distinta proviene de una autenticación SSH real y de la sesión remota administrada por sshd. No se necesitan dos terminales interactivos ni se pasa el control del runner a una shell remota.

### 16.3 Cliente remoto fijo, sin canal de órdenes genéricas

Se propone añadir al repositorio un helper autónomo, por ejemplo `tests/integration/private_unix_listener/a09_ssh_client.py`, que use solo la biblioteca estándar y no importe el paquete Atlas ni acceda al checkout.

Antes de abrir SSH, el runner copiará el helper a una ruta fija y temporal, `/tmp/atlas-a09-client.py`, mediante creación exclusiva (`O_CREAT|O_EXCL`), sin sobrescribir ningún objeto existente. El archivo será propiedad del UID del runner y modo `0644`; el sticky bit de `/tmp` impide que otro UID lo reemplace o elimine. El contenido no incluye claves ni secretos. Si el pathname ya existe, el runner no lo modifica y marca los escenarios como SKIP/INCOMPLETE o aborta el preflight. Si el proceso termina abruptamente y deja el helper, la siguiente ejecución no lo sobrescribe: requiere inspección y limpieza explícitas.

La clave de prueba tendría un comando forzado fijo:

```text
/usr/bin/python3 -I /tmp/atlas-a09-client.py
```

El helper acepta exclusivamente un mensaje JSON de tamaño limitado por stdin, con esquema estricto y campos permitidos para `scenario`, `socket_path` y nonce aleatorio de ejecución. Rechaza campos adicionales, datos excesivos, escenarios desconocidos y cualquier `SSH_ORIGINAL_COMMAND` no vacío. No ejecuta shell, no acepta comandos ni argumentos remotos, no cambia UID/GID y no lee el repositorio.

**Preflight del shell remoto:** antes de sustituir el comando forzado, inspeccionar de forma read-only los archivos de inicio que puedan ejecutarse para `atlas-a09-test` (en particular `.bashrc`, `.bash_profile`, `.profile` y cualquier configuración indicada por el entorno). El login de identidad ya probado no demuestra por sí solo que esos archivos carezcan de efectos secundarios. No añadir ni modificar archivos de inicio como parte de este experimento. Si no se puede demostrar que el comando forzado se ejecutará sin salida lateral ni procesos adicionales, mantener A09 en SKIP y diseñar una alternativa; no cambiar el shell de la cuenta ni la configuración global.

El runner envía una instrucción por conexión SSH y valida una única respuesta JSON por stdout, incluyendo nonce, escenario, UID/GID/PID del proceso cliente y resultado de socket. stderr se captura por separado; no se mezcla con el JSON. No se registran rutas de clave privada ni contenido de claves.

### 16.4 Opciones obligatorias de SSH

El runner solo podrá invocar SSH con parámetros fijos y explícitos:

- configuración de cliente aislada mediante `-F /dev/null`;
- destino `atlas-a09-test@127.0.0.1`, puerto 22;
- clave exacta suministrada por argumento y `IdentitiesOnly=yes`;
- `BatchMode=yes`, `PreferredAuthentications=publickey`, `PubkeyAuthentication=yes`, password, keyboard-interactive, GSSAPI y host-based authentication desactivados;
- `IdentityAgent=none`, `IdentitiesOnly=yes`, clave explícita y configuración cliente aislada con `-F /dev/null`;
- `StrictHostKeyChecking=yes`, archivo `UserKnownHostsFile` explícito y previamente verificado;
- `HostKeyAlgorithms=ssh-ed25519` y `PubkeyAcceptedAlgorithms=ssh-ed25519`;
- `GlobalKnownHostsFile=/dev/null`, `ClearAllForwardings=yes`, `ForwardAgent=no`, `ForwardX11=no`, `RequestTTY=no`, sin proxy ni multiplexación;
- timeout de conexión y timeout total de proceso acotados;
- ningún comando remoto adicional: el comando forzado de `authorized_keys` es el único ejecutable remoto.

Antes de lanzar SSH, el runner verificará que la clave privada y el archivo known_hosts sean archivos regulares, no symlinks, propiedad del UID ejecutor y con permisos privados exactos (clave y known_hosts modo `0600`). El UID esperado del peer se obtendrá de la cuenta local configurada (por defecto `atlas-a09-test`) mediante consulta de la base de cuentas; no se fija UID 1001 en el código. Se exigirá que sea distinto del UID ejecutor.

La opción `from="127.0.0.1"` restringe esta clave a conexiones originadas en loopback; `restrict` deshabilita PTY y forwarding para esta clave. Esto **no** restringe la escucha global de sshd, que ya fue observada en todas las interfaces. No se cambiarán sshd_config, PAM, firewall ni el servicio SSH.

### 16.5 Secuencia A09a — DAC del endpoint candidato

1. El runner crea el listener candidato habitual dentro de su sandbox privado, conservando directorio `0700` y socket `0600`.
2. El runner genera un nonce y envía por stdin SSH el escenario A09a y el pathname del socket.
3. El helper remoto intenta una única conexión AF_UNIX/SOCK_SEQPACKET, sin inspeccionar ni modificar el pathname.
4. Resultado esperado del cliente: `EACCES` por DAC. No se interpreta como rechazo SO_PEERCRED.
5. El runner verifica que no se haya aceptado ninguna conexión durante una ventana acotada y que el listener y su identidad inode sigan intactos.
6. El helper devuelve JSON con UID real y errno observado; el runner valida nonce, escenario y UID.

Cualquier conexión exitosa, errno distinto del esperado, respuesta incoherente, aceptación inesperada o alteración de identidad es FAIL. Si el entorno no permite demostrar el errno o no hay identidad externa disponible, SKIP.

### 16.6 Secuencia A09b — autorización real mediante SO_PEERCRED

1. El runner verifica que `/tmp` sea un directorio real, propiedad de root y modo `01777` (sticky bit y escritura compartida).
2. Crea un fixture temporal hermano del sandbox privado, directamente bajo `/tmp`; el directorio del fixture será `0711`, propiedad del UID ejecutor. No se anida bajo el sandbox `0700`.
3. Crea el listener AF_UNIX/SOCK_SEQPACKET y cambia únicamente el socket del fixture a `0666`; verifica tipo, propietario, inode y modo antes de lanzar el cliente. Estos permisos nunca se aplican al endpoint candidato.
4. El runner inicia el helper remoto por SSH. El helper conecta y envía un único paquete válido e inocuo `authority.ping`.
5. El servidor acepta una conexión, obtiene una observación independiente de `SO_PEERCRED` para registrar PID/UID/GID y llama al handler real `handle_admin_connection` con allowlist que contiene solo el UID del runner.
6. El handler vuelve a leer `SO_PEERCRED` y, por el orden actual del código, debe lanzar `AdminPeerRejected` / `UNAUTHORIZED_PEER` antes de ejecutar `recvmsg()`. No se modifica ni simula el handler.
7. El servidor cierra la conexión. El cliente debe observar EOF o reset sin recibir ningún byte de respuesta; timeout o cualquier byte recibido es FAIL.
8. El runner comprueba que el UID observado por el kernel coincide con el UID de `atlas-a09-test`, distinto del UID autorizado.

La observación previa de credenciales por el runner es únicamente evidencia; el handler realiza su propia consulta SO_PEERCRED para la decisión de autorización. Una conexión de un UID distinto del esperado no cuenta como PASS y debe tratarse como conexión inesperada/fallo, no como sustituto del peer configurado.

### 16.7 Timeouts, clasificación y cleanup

- Tiempo de conexión SSH: máximo 5 s; tiempo total por invocación: máximo 10 s.
- Timeout de conexión/lectura del cliente AF_UNIX: máximo 2 s.
- Espera de aceptación del servidor: limitada por el límite ya definido para el probe.
- El helper temporal se crea con identidad de archivo capturada. Solo se elimina si sigue siendo el mismo archivo regular, propietario del runner e inode original.
- El listener se cierra y su pathname se elimina únicamente si conserva la identidad registrada.
- El fixture se elimina solo después de cerrar el listener, comprobar identidad del directorio y verificar que está vacío. No usar borrado recursivo.
- Si el proceso SSH excede el límite, el runner termina únicamente el proceso hijo local iniciado por él. Si no puede confirmar que el hijo terminó, preserva helper, socket pathname, fixture y sandbox pertinentes; no elimina recursos que podrían seguir en uso y registra FAIL para inspección manual. No se detienen servicios del host.
- El informe expone A09a y A09b como escenarios independientes, con UID esperado/observado, errno, resultado de handler, bytes recibidos y cleanup. Si alguno se omite, el global permanece INCOMPLETE; solo ambos PASS pueden cerrar el requisito multi-UID, y aun así no autorizan producción.

### 16.8 Puertas pendientes

El helper y la coordinación A09a/A09b están implementados en la rama experimental, pero aún no se han ejecutado ni validado.

1. **Implementación en GitHub:** completada en `tests/integration/private_unix_listener/a09_ssh_client.py` y `run_probe.py`. A09a/A09b son filas independientes; el runner mantiene A09 deshabilitado por defecto y exige confirmaciones explícitas de preflight.
2. **Revisión estática:** revisar helper, serialización stdin/stdout, subprocess SSH, validación de archivos, límites, credenciales, cleanup e invariantes de cada escenario antes de considerar el código listo para Debian.
3. **Preflight del shell remoto:** el propietario debe inspeccionar de forma read-only `.bashrc`, `.bash_profile`, `.profile` y comportamiento de inicio del shell de `atlas-a09-test`. No modificar esos archivos.
4. **Cambio host pendiente:** sustituir la opción de comando forzado actual `/usr/bin/id -u` por `/usr/bin/python3 -I /tmp/atlas-a09-client.py`. Este cambio en `authorized_keys` es una modificación de seguridad del host y requiere autorización explícita específica. No se ha hecho.
5. **Ejecución:** requiere aprobación explícita independiente después de la revisión estática y del cambio host aprobado. El runner no usa sudo ni cambia credenciales.
6. **Validación:** el propietario ejecuta A09 en Debian, conserva JSON y commit exacto, y comparte el resultado para revisión.

El runner exige `--a09-forced-command-confirmed` y `--a09-shell-startup-reviewed` además de `--enable-a09` y rutas explícitas de clave/known_hosts. Estos flags son confirmaciones operativas, no sustituyen la autorización explícita ni prueban por sí mismos que el host esté configurado correctamente.

No se ejecutaron pruebas, compilaciones ni workflows desde GitHub. `main` permanece intacta, no hay PR y A-IPC-01 no está aprobado como transporte de producción.


### 16.9 Implementación del helper y runner — 2026-11-21

La implementación de código se publicó en la rama experimental:

- `tests/integration/private_unix_listener/a09_ssh_client.py`: helper fijo, biblioteca estándar, entrada JSON limitada a 4096 bytes, esquema cerrado `scenario/socket_path/nonce`, nonce de 128 bits en hexadecimal, rechazo de `SSH_ORIGINAL_COMMAND` no vacío, una sola conexión AF_UNIX/SOCK_SEQPACKET y salida JSON acotada. A09b envía un único `authority.ping` y lee como máximo un byte para detectar cualquier respuesta.
- `tests/integration/private_unix_listener/run_probe.py`: A09a/A09b independientes; SSH invocado como proceso local con argumentos fijos, entorno mínimo, agente desactivado, clave/host key explícitas, algoritmo ED25519, sin comando remoto ni forwarding. No se invocan herramientas de cambio de credenciales.
- El runner exige cuenta externa distinta y no privilegiada, clave privada/known_hosts regulares propiedad del ejecutor y modo 0600, directorio de clave 0700, sin hardlinks, known_hosts con una entrada loopback exacta para el puerto 22 (`127.0.0.1` o `[127.0.0.1]:22`, según la forma canónica del archivo) y fingerprint ED25519 previamente verificado.
- El helper se instala temporalmente en `/tmp/atlas-a09-client.py` mediante creación exclusiva, modo 0644 y cleanup condicionado por identidad. Un archivo preexistente nunca se sobrescribe.
- A09a valida EACCES desde el cliente remoto, cero accepts y preservación del endpoint candidato. A09b valida PID/UID/GID del kernel contra la identidad del helper, rechazo real `UNAUTHORIZED_PEER`, solicitud enviada y cero bytes de respuesta.
- El runner requiere `--enable-a09`, rutas explícitas y confirmaciones `--a09-forced-command-confirmed` y `--a09-shell-startup-reviewed`. Sin el opt-in, A09a/A09b permanecen SKIP.
- Si el proceso SSH local no termina tras kill, los recursos relacionados se preservan y el escenario falla; no se hace cleanup potencialmente concurrente.

**Estado de validación:** revisión estática de implementación en GitHub en curso; no se ejecutaron pruebas, compilaciones ni workflows. La clave instalada todavía fuerza `/usr/bin/id -u`; no se ha cambiado `authorized_keys`. El owner debe inspeccionar shell startup files y solicitar autorización específica antes del cambio host. No ejecutar A09 todavía.
