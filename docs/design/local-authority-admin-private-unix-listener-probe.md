# Diseño del probe A-IPC-01 — listener Unix propio en directorio privado

**Estado:** diseño aprobado e implementación experimental preparada en rama separada; pendiente de revisión local y ejecución por el propietario. No validado; no aprobado como transporte de producción.  
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
| A09 | Peer con UID distinto y no permitido | Conectar y enviar | Sin respuesta y conexión cerrada |
| A10 | Peer permitido | Conectar y enviar | Se procesa conforme al handler actual |
| A11 | Peer desconecta antes/durante envío | Procesar | No crash; no se informa éxito ficticio |
| A12 | Paquete truncado o ancillary prohibido | Procesar | Cierre sin respuesta según contrato |
| A13 | Cliente no envía paquete | Esperar timeout | Recurso liberado al vencer timeout |
| A14 | Conexiones simultáneas por encima del límite | Saturar listener | Backpressure/rechazo controlado; memoria y tareas acotadas |
| A15 | Cierre ordenado del listener | Reintentar conexión | Conexión nueva falla; no queda descriptor abierto |
| A16 | Dos procesos/hilos de prueba intentan `bind()` simultáneamente sobre el mismo pathname libre del sandbox | Ejecutar ambos binds concurrentemente y observar resultados | Exactamente un bind gana; el otro falla por colisión; el listener ganador permanece operativo y ningún objeto se modifica |

A09 es condicional: solo se ejecuta si el entorno ya ofrece una identidad de prueba no privilegiada distinta y puede invocarse sin sudo, cambios de UID/GID ni cambios del host. Si no, se marca `SKIP` con causa y la autorización por UID queda sin evidencia de integración multi-UID. No se sustituye por mocks como prueba de credenciales reales.

A06 utiliza únicamente un fixture del sandbox para simular sustitución. No intenta reproducir ni volver a ejecutar la colisión destructiva histórica de systemd.

## 7. Credenciales y autorización

- El listener obtiene las credenciales del peer aceptado mediante `SO_PEERCRED` antes de leer el paquete.
- La estructura de credenciales debe respetar los tipos Linux: PID con signo; UID/GID sin signo.
- La política de autorización se mantiene separada de la identificación del peer.
- El probe usa una allowlist de prueba explícita, inmutable durante la ejecución y no derivada de datos enviados por el cliente.
- Un UID identificado pero no permitido no recibe respuesta.
- No se interpreta `SO_PEERCRED` como identidad Atlas, identidad humana ni autorización de dominio.
- La evidencia de un único UID no demuestra aislamiento entre cuentas Linux.
- El probe no cambia UID/GID, no usa `setuid()`, no ejecuta `sudo` y no crea cuentas.

## 8. Concurrencia y límites de recursos

El probe debe declarar límites pequeños y fijos para:

- backlog de `listen()`;
- número máximo de conexiones aceptadas simultáneamente;
- tamaño máximo del paquete recibido, alineado con el contrato actual (16 KiB);
- tamaño máximo de respuesta (64 KiB);
- timeout de lectura y escritura independiente (default actual 5 s; máximo contractual 60 s);
- número de solicitudes por conexión (exactamente una);
- tiempo máximo total del escenario;
- número máximo de descriptores abiertos por el ejecutor.

El test de saturación debe verificar que el servidor no crea tareas/hilos ilimitados, no acumula paquetes ilimitados y recupera capacidad al cerrar clientes. Los valores concretos del límite de concurrencia deben ser parámetros fijos del fixture de prueba y quedar registrados en el resultado. Este diseño no decide todavía los valores de producción.

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

La implementación cubre A01–A08, A10–A16. A09 queda SKIP deliberado: el runner no cambia UID/GID, no usa sudo y no crea identidades. Por tanto, un recorrido sin otros fallos termina como INCOMPLETE, no PASS. A14 utiliza un harness de prueba con un máximo fijo de dos workers y backlog ocho; no representa ni fija capacidad de producción.

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
4. Revisar el diff y las condiciones de cleanup, colisiones, timeout, concurrencia y clasificación.
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

No ejecutar el comando hasta revisar el código y el commit de la rama por el propietario.

## 15. Decisión pendiente

Este documento define el experimento, no selecciona el transporte IPC definitivo. La alternativa A continúa siendo candidata. La alternativa B permanece suspendida por la colisión destructiva observada. La alternativa C (AF_UNIX abstract namespace) conserva riesgos distintos y requiere un probe separado.

**No se autoriza con este documento:** listener persistente, daemon, activación systemd, cambios de host, usuarios/grupos, permisos, privilegios, acceso SQLite, provisioning, mutaciones administrativas ni despliegue.
