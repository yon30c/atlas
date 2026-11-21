# Plan de probe aislado — autenticación mutua y capacidad IPC

**Fecha:** 2026-11-21  
**Estado (2026-11-21):** el propietario ejecutó el runner completo sobre checkout `66b348e1be9a7e614d51c4b3ade9e643c9152106` en `Atlas-VM-test` (Debian 13, kernel 6.12.117, Python 3.13.5, EUID 0; SERVICE 2005/2005, OTHER 2006/2006): MA-01..MA-10 y CP-01..CP-12 PASS; `overall=PASS`; duración 24.991 s; cleanup correcto. CP-12 confirmó rechazo con RLIMIT heredado 32/32, exit 3, evento `startup_error`, sin elevar límites ni crear socket. Evidencia detallada al final de este documento. Es validación experimental, no aprobación de transporte productivo.  
**Rama:** experiment/a-ipc-01-private-unix-listener-probe  
**Decisiones:** TCB-1; frontend EUID 0; client_uids={0}; perfil de capacidad inicial aprobado por el propietario.  
**Dependencias:** contrato atlas-admin/1, handler IPC, configuración confiable, resolución de rutas, stale recovery y lifecycle.

## 1. Objetivo y alcance

Preparar una validación adversarial aislada de los controles necesarios antes de considerar un listener propio AF_UNIX/SOCK_SEQPACKET:

1. Autenticación mutua por SO_PEERCRED, con el cliente administrativo bajo EUID 0 y el servicio bajo una identidad de fixture que representa atlas-runtime.
2. Orden de autenticación estricto: el cliente no envía bytes antes de autenticar al servidor; el servidor no lee bytes antes de autenticar al cliente.
3. Resolución segura de configuración y endpoint, sin seguir symlinks ni aceptar sustituciones de ancestros por identidades externas.
4. Capacidad limitada, backpressure, deadlines y recuperación después de saturación.
5. Fallo cerrado ante pathname preexistente y ausencia de stale cleanup automático.

Este plan no implementa el cliente, listener, pool de workers, lifecycle ni configuración de producción. No abre SQLite, no ejecuta operaciones administrativas y no modifica el host.

## 2. Decisiones fijadas por el propietario

### 2.1 Identidad y confianza

- Todos los procesos bajo la cuenta dedicada atlas-runtime pertenecen a TCB-1; no se exige aislamiento intra-UID.
- El frontend administrativo debe conectar con EUID 0.
- La allowlist del servicio es exactamente client_uids={0}.
- El cliente obtiene SO_PEERCRED después de connect y antes de send; exige el UID numérico de servicio configurado.
- El servidor obtiene SO_PEERCRED después de accept y antes de recv; exige UID 0.
- PID/GID se conservan como evidencia diagnóstica, no amplían autorización.
- No se añade handshake secreto ni se confía en UID/PID declarados por JSON.

### 2.2 Perfil de capacidad aprobado para el probe

| Control | Valor |
|---|---:|
| Conexiones/slots activos | 4 |
| Workers fijos | 4 |
| Backlog del kernel | 8 |
| Cola de aplicación | 0 |
| Timeout de lectura | 5 s |
| Timeout de escritura | 5 s |
| Deadline global desde accept | 15 s |
| Request / response | 16 KiB / 64 KiB |
| Profundidad JSON | 16 |
| RLIMIT_NOFILE | 64 |

El perfil se aprueba para la siguiente etapa de experimentación aislada. No es un límite de producción ni una configuración systemd aprobada. El valor de FDs debe contrastarse con el inventario real de descriptores cuando exista un entrypoint revisado. No se fijan todavía memoria, CPU, TasksMax ni plazo de drenaje.

## 3. Entorno de prueba y precondiciones

- Usar una VM desechable Debian/Linux o un sandbox equivalente, sin rutas ni recursos Atlas reales.
- Todos los sockets, archivos de configuración y directorios se crean bajo un directorio temporal nuevo, privado y verificado por el harness.
- La prueba del requisito EUID 0 requiere ejecutar el harness como UID 0 real dentro de la VM desechable, no como root simulado dentro de un user namespace. El harness debe iniciar un proceso de servicio hijo bajo un UID/GID numérico de fixture distinto, mediante descenso de credenciales dentro de ese proceso; no necesita crear una cuenta o grupo NSS. El cliente debe conservar EUID 0 real en la VM. Si el entorno no permite demostrar estas credenciales de kernel, marcar INCOMPLETE; no sustituirlas por mocks ni por root de user namespace y declarar PASS.
- No reutilizar la identidad temporal atlas-a09-test, sus claves, HOME o configuración SSH.
- No modificar /etc/atlas, usuarios, grupos, sudoers, PAM, SSH, systemd, permisos del host ni servicios.
- No usar el socket administrativo real, SQLite, DBs existentes ni rutas persistentes.
- El harness no ejecutará sudo, su ni runuser. Se ejecutará directamente desde una sesión root de la VM desechable; el cambio de UID/GID se limitará al proceso hijo de servicio y a los directorios temporales de fixture. No se modificará NSS ni se cambiarán credenciales de la sesión/host.
- El harness no eliminará rutas fuera de su raíz temporal; no hará stale cleanup sobre objetos no creados por esa ejecución.

Si no es posible probar un cliente EUID 0 real y un servidor bajo UID distinto sin alterar el host, detenerse y presentar el requisito de entorno antes de implementar el probe.

## 4. Matriz de autenticación mutua

| ID | Escenario | Resultado requerido |
|---|---|---|
| MA-01 | Cliente EUID 0 conecta al servicio de UID esperado | Cliente autentica server y solo entonces envía un paquete |
| MA-02 | Cliente conecta a endpoint servido por UID distinto | Cierra sin enviar ningún byte |
| MA-03 | Cliente no tiene EUID 0 | No intenta connect |
| MA-04 | Servidor acepta peer UID 0 | Continúa a recv después de verificar credenciales |
| MA-05 | Servidor acepta peer UID distinto de 0 | Cierra antes de recv; no responde envelope |
| MA-06 | Request contiene UID/PID/GID falsos | La identidad efectiva sigue siendo la entregada por el kernel |
| MA-07 | Configuración ausente, duplicada, desconocida o alterada | Fallo cerrado antes de conectar/aceptar |
| MA-08 | Configuración cambia después de cargar | La instancia conserva snapshot inmutable |
| MA-09 | Peer autorizado cierra su dirección de escritura después de conectar y antes de la primera petición | El handler devuelve PEER_DISCONNECTED; cero bytes de respuesta y ninguna petición aceptada |
| MA-10 | Transporte no es AF_UNIX/SOCK_SEQPACKET (AF_UNIX/SOCK_STREAM y AF_INET/SOCK_STREAM) | Rechazo antes de consumir el paquete; cero bytes de respuesta |

La evidencia debe demostrar el orden, no solo el resultado final. El harness debe observar bytes recibidos en el endpoint de fixture y probar que el contador permanece en cero cuando el cliente rechaza el UID del servidor; para MA-05 debe probar que el servidor no invocó recv ni produjo respuesta.

## 5. Matriz de rutas y pathname

| ID | Escenario | Resultado requerido |
|---|---|---|
| PA-01 | Symlink en cualquier ancestro | Rechazo sin abrir fuera del árbol |
| PA-02 | Componente .., ruta relativa o ambigua | Rechazo |
| PA-03 | Directorio escribible por UID externo | Rechazo antes de continuar |
| PA-04 | Configuración final FIFO/socket/symlink | Rechazo sin bloquear ni leer |
| PA-05 | Archivo de configuración reemplazado después de open | Lectura solo desde descriptor validado |
| PA-06 | Pathname de socket ya existente (regular, symlink, socket) | Bind falla y objeto/contenido permanecen idénticos |
| PA-07 | Entrada cambia antes de cleanup | No eliminar el sustituto |
| PA-08 | Connect por pathname canónico después del descriptor walk | Peer correcto; sin escape de ruta |
| PA-09 | Descriptor del directorio padre cerrado/perdido | Operación falla cerrada |

El baseline es el descriptor walk desde / y bind al pathname absoluto canónico tras validar la cadena y excluir escrituras de UIDs externos. El bind no es dirfd-atómico. La alternativa procfs permanece experimental y fuera del criterio de aceptación base.

## 6. Matriz de capacidad y backpressure

| ID | Escenario | Resultado requerido |
|---|---|---|
| CP-01 | Cuatro conexiones ocupan todos los slots | No existe quinto worker ni cola de aplicación |
| CP-02 | Más clientes llegan mientras slots están ocupados | Medir la cola AF_UNIX real y su límite efectivo para el valor pasado a listen() |
| CP-03 | Cola AF_UNIX en su límite efectivo | La siguiente conexión no bloqueante recibe EAGAIN; no aparecen accepts/workers adicionales |
| CP-04 | Se libera un slot | El accept loop recupera capacidad sin reiniciar |
| CP-05 | Cliente autorizado no envía paquete | El read timeout independiente cierra la conexión alrededor de 5 s; el deadline global de 15 s no se alcanza |
| CP-06 | Se consumen 11 s del presupuesto después de accept y antes de iniciar read | El read timeout efectivo se reduce al tiempo restante; la conexión termina alrededor del deadline global de 15 s desde accept |
| CP-07 | Excepción en worker | Socket se cierra y slot se libera en finally |
| CP-08 | Request >16 KiB / response >64 KiB | Rechazo conforme al contrato; sin truncamiento silencioso |
| CP-09 | Profundidad JSON >16 | Rechazo |
| CP-10 | FDs/threads bajo carga | No exceden los límites del perfil |
| CP-11 | Reinicio de carga tras saturación | Servicio vuelve al estado disponible sin fugas de slots/FDs |
| CP-12 | RLIMIT_NOFILE=64 | Startup detecta recursos insuficientes; no eleva el límite |

La prueba de backlog debe distinguir conexiones pendientes en kernel de conexiones aceptadas por la aplicación. El harness registrará workers vivos, slots usados, sockets aceptados, FDs abiertos y tiempo monotónico por conexión.

## 7. Recuperación stale y cleanup

- Startup nunca elimina un pathname existente.
- Una colisión debe dejar intactos tipo, bytes, st_dev, st_ino, UID/GID y modo del objeto preexistente.
- Cleanup normal solo considera la entrada creada por esa instancia, relativa al descriptor del directorio, y exige coincidencia de tipo, st_dev, st_ino y UID.
- La revalidación seguida de unlink conserva TOCTOU; el plan se apoya en directorio privado y TCB-1, no afirma atomicidad.
- El procedimiento de recuperación manual de socket residual se valida por separado en sandbox. Si cualquier namespace no puede inspeccionarse, se aborta; no se usa connect como detector de liveness.
- Ningún escenario puede borrar un objeto no creado por el harness o fuera de la raíz temporal.

## 8. Criterios globales de PASS / FAIL / INCOMPLETE

PASS solo si todos los escenarios obligatorios se ejecutan con credenciales de kernel reales, límites observables y cleanup verificado; cero fallos y cero escenarios omitidos.

FAIL si una identidad incorrecta puede enviar/recibir protocolo, se excede el límite, hay fuga de recursos, se altera un pathname preexistente o se elimina un objeto sustituto.

INCOMPLETE si el entorno no permite verificar credenciales reales, no se puede medir backlog/FDs/workers, una namespace no es visible o algún escenario obligatorio queda omitido. INCOMPLETE no se presenta como PASS.

## 9. Entregables y secuencia

1. **Implementado, pendiente de ejecución:** harness separado A-IPC-02 con procesos reales: cliente EUID 0, servicio bajo UID/GID numéricos de fixture, autenticación mutua `SO_PEERCRED`, prueba de orden antes de send/recv, cuatro workers fijos, backlog configurado 8, deadline global de 15 s, timeouts 5 s y `RLIMIT_NOFILE=64` en el proceso de servicio.
2. **Validación del propietario pendiente:** ejecutar exclusivamente en VM desechable con cuatro IDs numéricos reservados para fixtures; el harness no crea cuentas/grupos. El runner declara INCOMPLETE para escenarios todavía no implementados.
3. **MA-03 implementado, pendiente de validación del propietario:** el cliente fixture con EUID distinto de 0 invoca el mismo guard del cliente privilegiado; se exige rechazo antes de crear/conectar un socket y ausencia de accept en el servidor. Después completar config parser/snapshot, límites de payload/depth, read/write/deadline adversaries, excepción/recovery, saturación exacta del backlog y contabilidad de FDs.
4. Añadir resolución de rutas, symlinks, colisiones y cleanup por descriptor; mantenerlo separado del listener persistente.
5. Validar manualmente stale recovery en sandbox separado.
6. Revisar resultados y cerrar hallazgos antes de proponer cualquier listener persistente.

No combinar esta etapa con implementación del entrypoint administrativo real ni con las operaciones authority.diagnose, migraciones, initialize o provisioning.

## 9.1 Evidencia de ejecución del propietario — 2026-11-21

El propietario ejecutó el runner en `Atlas-VM-test`, Debian 13,
kernel `6.12.117+deb13-amd64`, Python 3.13.5, como EUID 0 real y con
fixtures SERVICE 2005/2005 y OTHER 2006/2006, sobre commit
`fbc8c68e75c7d5d32768442666cf861f7880eb28`.

- MA-01, MA-02, MA-04 y MA-05: PASS.
- CP-01 y CP-04: PASS; máximo observado de workers activos 4, recuperación
  a 0 workers activos.
- Backlog configurado 8; saturación real no probada.
- Global INCOMPLETE; duración 1.177 s.
- Cleanup: sandboxes privados y de traversal bajo `/run` eliminados tras
  terminar los procesos hijos.

La evidencia pertenece exclusivamente al commit y escenarios indicados.
MA-03 se implementó después, en commit `7a0d4f1`; aún requiere ejecución.
No inferir PASS de MA-03 ni completar cobertura por extrapolación.

## 10. Límites

- Este documento es un plan de probe, no una implementación.
- No modifica el contrato atlas-admin/1 ni el handler actual.
- No se ejecutaron pruebas, compilaciones ni workflows desde GitHub. El propietario ejecutó parcialmente el runner en la VM indicada en §9.1; el commit posterior con MA-03 está pendiente de validación local.
- No se crearon cuentas, grupos, archivos de configuración del host, sockets persistentes ni servicios.
- No se autorizó despliegue, acceso SQLite, cambios de privilegios ni producción.


## 9.2 Actualización de validación y MA-06 — 2026-11-21

El propietario ejecutó el runner en `Atlas-VM-test`, Debian 13,
kernel `6.12.117+deb13-amd64`, Python 3.13.5, EUID 0, fixtures
SERVICE 2005/2005 y OTHER 2006/2006, sobre commit
`069dbb9520f9e640955d9122f3a8012b2f55ba1a`.

- MA-01 a MA-05: PASS.
- MA-03 observó EUID cliente 2006, `connect_attempted=false` y
  `server_observed_connection=false`.
- CP-01 y CP-04: PASS; máximo de workers activos 4 y recuperación a 0.
- Backlog 8 configurado, no saturado.
- Global INCOMPLETE; 1.339 s; cleanup de ambos sandboxes `/run` completado.
- Sin filas FAIL.

Esta evidencia pertenece únicamente a `069dbb9`. Después se implementó
MA-06 en `9a8380e`, todavía pendiente de ejecución por el propietario.

**MA-06:** el fixture construye un envelope ping válido con campos top-level
adicionales `uid`, `gid` y `pid` que pretenden declarar identidad. El
servidor obtiene primero SO_PEERCRED del kernel y el decoder estricto debe
rechazar el envelope con `INVALID_REQUEST`; la observación de peer UID debe
seguir procediendo del kernel, no de esos campos. Esto valida el rechazo de
claims añadidos al protocolo, no resistencia frente a root comprometido ni
frente al kernel.

El runner permanece INCOMPLETE. MA-06 está implementado pero no validado;
no atribuirle PASS hasta recibir el JSON de una ejecución local del commit
`9a8380e` o posterior que contenga el cambio.



## A-IPC-02 — validación del propietario de MA-06 (2026-11-21)

El propietario ejecutó el runner directamente como root en la VM desechable
`Atlas-VM-test`, Debian 13, kernel `6.12.117+deb13-amd64`, Python
`3.13.5`, sobre el commit `b4eda57d36338f065adb2cb4e00d19a8ade58069`,
con fixtures SERVICE UID/GID `2005/2005` y OTHER UID/GID `2006/2006`.

- **MA-01..MA-06: PASS.** Cliente root autenticó el servidor UID 2005 y
  completó ping. El cliente rechazó el servidor UID 2006 antes de enviar
  bytes (`bytes_sent_by_client=0`). El servidor rechazó al peer UID 2006
  antes de leer (`response_bytes=0`). El cliente no-root EUID 2006 fue
  rechazado antes de connect (`connect_attempted=false`; el servidor no
  observó conexión).
- **MA-06:** el envelope ping incluía claims top-level falsos
  `uid=0`, `gid=0`, `pid=1`. El decoder respondió
  `INVALID_REQUEST`; la evidencia de identidad conservó
  `kernel_peer_uid=0`. Los campos aportados por el cliente no se aceptaron
  como credenciales.
- **CP-01/CP-04: PASS.** Máximo observado de workers/conexiones activas: 4;
  después de liberar carga, `active_after_recovery=0`.
- Backlog del kernel configurado en 8, **sin saturación exacta**.
- Duración: 1.431 s. Cleanup confirmado: sandboxes privado y de traversal
  bajo `/run` eliminados después de finalizar los procesos hijos.
- Resultado global: **INCOMPLETE**, sin escenarios FAIL.

La evidencia aplica al commit y entorno indicados; no se extiende a commits
posteriores sin repetir la ejecución. Permanecen sin implementar o validar
MA-07..MA-10 y CP-02..CP-03/CP-05..CP-12: configuración ausente/duplicada/
desconocida/alterada y snapshot inmutable; desconexión y variantes de
transporte; saturación exacta del backlog; adversarios de read/write/deadline;
recuperación ante excepciones; límites de payload/profundidad JSON y
contabilidad completa de FDs.

**Siguiente incremento propuesto:** revisar y diseñar MA-07/MA-08 antes de
codificar. El diseño de configuración confiable exige parser cerrado,
resolución segura desde descriptor, validación de tipo/owner/mode/tamaño,
fallo cerrado e inmutabilidad en memoria. La propuesta de
`/etc/atlas/admin-ipc.conf` sigue siendo solo diseño: no existe archivo
operativo, parser productivo ni entrypoint IPC revisado. Cualquier fixture
MA-07/08 debe vivir exclusivamente en sandbox temporal y no leer ni crear
configuración del host.

No se ejecutaron pruebas, compilaciones ni workflows desde GitHub. El
propietario ejecutó el probe localmente en la VM indicada. `main` no se
modificó, no se creó PR y no se aprobó listener persistente, transporte de
producción ni despliegue.


## 9.3 Evidencia del propietario — MA-07/MA-08 (2026-11-21)

El propietario ejecutó el runner en `Atlas-VM-test`, Debian 13, kernel `6.12.117+deb13-amd64`, Python 3.13.5, EUID 0 real, fixtures SERVICE UID/GID `2005/2005` y OTHER UID/GID `2006/2006`, sobre el commit `585dd3d979bc1b800550e4b9c79c382b22cf1f6c`.

- MA-01..MA-08: PASS. MA-01..MA-06 se reportaron agrupados; MA-07 y MA-08 como escenarios independientes.
- MA-07: aceptación de la configuración válida con UID/GID de servicio 2005/2005 y `client_uids=[0]`; rechazo de los 11 casos inválidos listados en §4/README.
- MA-08: pathname reemplazado de `/run/atlas/admin.sock` a `/run/atlas/changed.sock`; el snapshot retuvo el pathname original, con campos frozen y colección inmutable.
- CP-01/CP-04: PASS; máximo 4 workers activos y recuperación a 0. Backlog configurado 8, no saturado.
- Duración 1.497 s; cleanup de ambos sandboxes `/run` completado; cero filas FAIL.
- Global **INCOMPLETE**: MA-09..MA-10 y CP-02..CP-03/CP-05..CP-12 permanecen sin implementar/validar.

Esta evidencia aplica únicamente al commit indicado. MA-07/08 prueban un parser y loader fixture, no configuración productiva; el loader valida el archivo final relativo a un descriptor de sandbox ya confiable y no sustituye el path-walk PA desde `/`. No se modificó el handler ni el host.

**Siguiente incremento:** inspeccionar el estado actual del runner y del protocolo antes de implementar MA-09 (desconexión durante autenticación) y MA-10 (rechazo de transportes distintos de AF_UNIX/SOCK_SEQPACKET). Mantenerlos como pruebas aisladas y conservar INCOMPLETE hasta completar todos los escenarios obligatorios.

## 9.4 MA-09/MA-10 implementados — validación del propietario pendiente (2026-11-21)

Commit `f41df94d0f87d288bfc7e3df45c66295fa19d570` amplía el runner:

- **MA-09:** crea un par AF_UNIX/SOCK_SEQPACKET, confirma peer UID 0 mediante SO_PEERCRED, cierra la dirección de escritura del peer sin enviar request y llama al handler real. Exige `AdminPeerDisconnected/PEER_DISCONNECTED`, cero bytes de respuesta y que no se acepte petición. La prueba cubre EOF/half-close antes de la primera petición; no afirma observar una interrupción dentro de la syscall SO_PEERCRED.
- **MA-10:** entrega al handler real sockets AF_UNIX/SOCK_STREAM y AF_INET/SOCK_STREAM con un ping válido ya encolado. Exige `AdminProtocolRejected/INVALID_REQUEST`; `MSG_PEEK` comprueba que el handler no consumió el paquete y el peer no recibió bytes de respuesta.
- Ambos escenarios se registran como PASS únicamente si las aserciones del runner se cumplen. El bloque INCOMPLETE restante enumera CP-02..CP-03 y CP-05..CP-12.
- **Estado actual:** implementación y revisión estática completadas; ejecución del propietario pendiente. No se ejecutaron pruebas, builds ni workflows desde GitHub.
- Evidencia previa MA-01..MA-08 y CP-01/04 pertenece solo al commit `585dd3d979bc1b800550e4b9c79c382b22cf1f6c`; no atribuirla al commit nuevo sin repetir ejecución.

Siguiente paso: actualizar la VM desechable al commit nuevo y ejecutar el runner completo. Después, revisar el JSON antes de abordar la saturación exacta del backlog (CP-02/03).


## 9.5 Evidencia del propietario — MA-01..MA-10 y CP-01/CP-04 (2026-11-21)

El propietario ejecutó el runner directamente como EUID 0 en la VM desechable
`Atlas-VM-test`, Debian 13, kernel `6.12.117+deb13-amd64`, Python
`3.13.5`, con SERVICE fixture UID/GID `2005/2005` y OTHER fixture
UID/GID `2006/2006`. La ejecución duró `1.687 s`.

El checkout se actualizó mediante fast-forward de `991f91e` a
`901c792cb723d920da4970ecce98ea7f871c4f85` inmediatamente antes de la
ejecución. El JSON devolvió `commit: null`; por tanto, el SHA se registra
como el checkout actualizado según la salida de `git pull`, no como un
valor confirmado por el propio runner.

- **MA-01..MA-06: PASS.** Se observó autenticación del cliente EUID 0 frente
  al servicio UID 2005; rechazo del servidor UID 2006 antes de enviar bytes;
  rechazo del cliente UID 2006 antes de que el servidor lea o responda;
  rechazo de cliente EUID 2006 antes de connect; y rechazo
  `INVALID_REQUEST` de claims falsos UID/GID/PID, conservando UID 0 obtenido
  del kernel.
- **MA-07: PASS.** Configuración fixture válida aceptada y 11 casos inválidos
  rechazados.
- **MA-08: PASS.** El snapshot congelado conservó
  `/run/atlas/admin.sock` después del reemplazo atómico del archivo por una
  configuración con `/run/atlas/changed.sock`.
- **MA-09: PASS.** El peer AF_UNIX/SOCK_SEQPACKET autorizado cerró su
  dirección de escritura antes de enviar solicitud; el handler produjo
  `PEER_DISCONNECTED`, no aceptó una solicitud y no emitió respuesta.
- **MA-10: PASS.** AF_UNIX/SOCK_STREAM y AF_INET/SOCK_STREAM fueron
  rechazados con `INVALID_REQUEST` antes de leer. En ambos casos el primer
  byte permaneció encolado según `MSG_PEEK`, con cero bytes de respuesta.
- **CP-01/CP-04: PASS.** Máximo observado de workers activos: 4;
  `active_after_recovery=0`.
- Backlog kernel 8 configurado, pero no se probó saturación exacta.
- Cleanup: sandboxes privado y de traversal bajo `/run` eliminados después
  de finalizar los procesos hijos.
- Resultado global: **INCOMPLETE**, sin filas FAIL. Permanecen pendientes
  saturación exacta del backlog, adversarios de deadlines read/write/global,
  recuperación de excepciones, límites de payload/profundidad JSON y
  contabilidad completa de FDs (CP-02/CP-03 y CP-05..CP-12).

Esta evidencia es del harness experimental y no valida un listener
persistente, configuración productiva, resolución de rutas, stale recovery,
systemd, SQLite, lifecycle ni despliegue. No aprueba un transporte de
producción. No se ejecutaron pruebas, compilaciones ni workflows desde GitHub.


## 9.4 CP-02/CP-03 — implementación de saturación exacta del backlog (2026-11-21)

El runner ahora usa iproute2 `ss -x -l -n -H` para leer las columnas
`Recv-Q` y `Send-Q` de la fila LISTEN del socket fixture. El preflight
requiere que el ejecutable `ss` sea un archivo regular root-owned, ejecutable
y no escribible por grupo/otros. Si falta o la observación falla por una
precondición, el resultado es INCOMPLETE; no se sustituye la medición por
suposiciones basadas únicamente en llamadas `connect()`.

La secuencia de CP-02/CP-03 es:
1. Ocupar los cuatro workers con conexiones sin request.
2. Abrir ocho conexiones adicionales y comprobar mediante `ss` que
   `Recv-Q=8` y `Send-Q=8`.
3. Comprobar que la aplicación no aceptó ninguna conexión adicional mientras
   los cuatro slots permanecían ocupados.
4. Intentar una novena conexión no bloqueante y exigir `EAGAIN`/`EWOULDBLOCK`.
5. Volver a observar que el backlog permanece en 8/8 y que no hubo un accept
   adicional.

**Estado:** implementación inicial en commit `1e213b2f7a254cd2718e644e415670dca08435f5`, con endurecimiento posterior del preflight de `ss` y su ruta en commit `67526c21a1edc2938b5caefb699aa6c6576c5b73`; revisión estática solamente.
El propietario debe ejecutar el runner actualizado en `Atlas-VM-test`.
No se ejecutaron pruebas, builds ni workflows desde GitHub. CP-02/CP-03 no
se consideran PASS hasta recibir evidencia local. CP-05..CP-12 siguen
INCOMPLETE. El perfil sigue siendo experimental y no es configuración de
producción.


La revisión estática posterior detectó y corrigió un detalle de alcance de
variable al conservar la ruta resuelta de `ss`: `_preflight` declara
explícitamente `global SS_BIN`. Corrección publicada en
`4ab6a1b7762f4d45a745ea2c36f7289411a9c848`. Sigue sin validación de ejecución.


## 9.5 Ejecución CP-02/CP-03 — fallo de expectativa y corrección (2026-11-21)

El propietario ejecutó el commit `1ebf930a6559c3d6a81965f0f94c28ed8e6eef56`
en `Atlas-VM-test` (Debian 13, kernel `6.12.117+deb13-amd64`,
Python 3.13.5, EUID 0). MA-01..MA-10 y CP-01/CP-04 pasaron. El runner
observó primero `Recv-Q=8`/`Send-Q=8`, pero la conexión no bloqueante
siguiente devolvió `connect_ex=0`; por tanto la ejecución terminó FAIL antes
de confirmar CP-02/CP-03. Cleanup de los sandboxes correcto.

La inspección del código del kernel AF_UNIX muestra que la comprobación de
cola usa `skb_queue_len(...) > sk_max_ack_backlog`, no `>=`. Por ello,
con `listen(8)`, el kernel permite una conexión pendiente adicional:
con ocho ya en cola, la novena conecta; cuando la cola alcanza nueve, la
siguiente debe obtener `EAGAIN` en modo no bloqueante. Esto es comportamiento
de implementación Linux AF_UNIX, no una garantía portable para otros sistemas
o familias de sockets.

Corrección del runner en commit
`634e19decce2322e94ca0d1fe410b259f23dcb67`:
1. Conserva la comprobación inicial `Recv-Q=8`/`Send-Q=8`.
2. Exige que la conexión de frontera adicional tenga resultado 0 y mide
   `Recv-Q=9`/`Send-Q=8`.
3. Intenta otra conexión no bloqueante y exige `EAGAIN`/`EWOULDBLOCK`.
4. Comprueba que la cola permanezca 9/8 y que el accept loop no haya creado
   accepts ni workers adicionales.

**Estado:** corrección revisada estáticamente en GitHub; CP-02/CP-03 siguen
pendientes de validación local. No se ejecutaron pruebas, builds ni workflows
desde GitHub. No se debe cambiar el backlog aprobado de 8 basándose en esta
diferencia de una conexión: se registra el parámetro listen(8) y el límite
efectivo observado del kernel por separado.


## 9.6 Validación CP-02/CP-03 y gate CP-05 (2026-11-21)

El propietario ejecutó `b5b0128e2646e41e3a2f927251c6fa6dafa897d7` en `Atlas-VM-test` (Debian 13, kernel `6.12.117+deb13-amd64`, Python 3.13.5, EUID 0; fixtures 2005/2005 y 2006/2006). MA-01..MA-10, CP-01/04 y CP-02/03 PASS. Duración 1.454 s; cleanup de ambos sandboxes `/run` completado.

CP-02/03: `listen(8)`; Recv-Q/Send-Q 8/8; conexión novena admitida (9/8); décima rechazada con EAGAIN errno 11; cola final 9/8; `accepted_after_overflow=9`, igual a `accepted_while_full`; workers dentro del límite y recuperación a cero. Overall INCOMPLETE por CP-05..CP-12.

**Gate antes de CP-05:** el escenario documenta que un cliente silencioso termina por deadline global de 15 s, pero el fixture aplica `min(READ_TIMEOUT=5 s, remaining_global)` al primer `recv`. El cliente silencioso vence por read timeout a los 5 s, no a los 15 s. Aclarar si CP-05 debe probar read/idle timeout de 5 s o si se desea otro contrato global antes de implementar. No alterar los límites aprobados por inferencia.


## 9.7 CP-05 / CP-06 implementados — validación del propietario pendiente

Commit del runner: `59fafb801a31d7adf51a6598db78440255744321`.

La recomendación aprobada conserva los límites del perfil sin cambios:

- **CP-05 — read timeout:** un peer autorizado conecta y no envía paquete. El fixture observa el inicio de lectura y exige timeout alrededor de 5 s desde accept, cierre del peer y cero bytes de respuesta. Debe quedar demostrado que el deadline global aún no se alcanzó.
- **CP-06 — deadline global:** un servidor fixture dedicado introduce una espera controlada de 11 s después de accept/autenticación y antes de iniciar la lectura. La lectura recibe únicamente el presupuesto restante (aprox. 4 s); el peer debe cerrarse alrededor de 15 s desde accept. El runner registra el tiempo monotónico, timeout efectivo, presupuesto restante y EOF.

La espera de 11 s es **inyección de tiempo exclusivamente del harness**, no una pausa del handler productivo ni un cambio al contrato. Permite probar que el timeout de una fase posterior se recorta por el deadline contado desde accept. No simula una escritura bloqueada ni demuestra una suma de read/write real: el fixture actual realiza un único `recvmsg` y un único `send`, y cada timeout individual de 5 s no consume por sí solo los 15 s globales. La cobertura de escritura bloqueada/cómputo entre fases queda limitada y deberá revisarse si el handler incorpora más fases I/O.

El runner conserva `overall=INCOMPLETE` porque CP-07..CP-12 siguen pendientes. **CP-05/06 están implementados, no validados** hasta recibir el JSON del propietario en `Atlas-VM-test`. No se ejecutaron pruebas, builds ni workflows desde GitHub; no se modificaron handler productivo, contrato, `main`, host, cuentas, servicios o SQLite.


## 9.8 Validación del propietario — CP-05 / CP-06 (2026-11-21)

El propietario ejecutó el runner en Atlas-VM-test, Debian 13, kernel 6.12.117+deb13-amd64, Python 3.13.5, EUID 0 real, fixtures SERVICE UID/GID 2005/2005 y OTHER 2006/2006, commit 0db262802ce30ec38a4ce52a4f5bfaa3081fc2b1.

- MA-01..MA-06: PASS. Autenticación mutua, rechazo pre-connect de cliente no-root, rechazo antes de recv/send para identidades incorrectas y rechazo de claims UID/GID/PID falsos.
- MA-07: PASS. Once variantes inválidas de configuración rechazadas; configuración fixture válida aceptada.
- MA-08: PASS. Snapshot congelado/inmutable conservó el pathname original tras reemplazar la configuración.
- MA-09: PASS. Desconexión antes de request detectada como PEER_DISCONNECTED, cero bytes enviados/recibidos.
- MA-10: PASS. AF_UNIX/SOCK_STREAM y AF_INET/SOCK_STREAM rechazados antes de leer; primer byte permaneció encolado y cero respuesta.
- CP-01/04: PASS. Máximo 4 workers/activos y recuperación a 0.
- CP-02/03: PASS. Backlog listen(8): Recv-Q 8 y después 9; novena conexión admitida, décima rechazada con EAGAIN errno 11; accepts permanecieron en 9 y workers dentro del límite.
- CP-05: PASS. Peer autorizado silencioso; timeout configurado 5.0 s, observado 5.002 s desde accept, EOF del peer y cero bytes de respuesta. Deadline global no alcanzado.
- CP-06: PASS. Espera test-only 11.0 s después de accept; lectura inició a 11.004 s con timeout efectivo/restante 3.996 s; cierre a 15.006 s desde accept, EOF y cero bytes de respuesta. Deadline global alcanzado.
- Duración total 22.095 s; cleanup confirmó eliminación de sandboxes privados y de traversal después de finalizar los procesos hijos.
- Resultado global INCOMPLETE, sin filas FAIL. CP-07..CP-12 permanecen pendientes.

La espera de CP-06 sigue siendo instrumentación del harness; no representa trabajo del handler productivo ni una escritura bloqueada. La evidencia demuestra que la fase de lectura recibe el presupuesto restante del deadline accept-based. No amplía el alcance a listener productivo, lifecycle persistente, resolución de rutas, systemd, SQLite o despliegue.


## 9.9 CP-07 implementado — validación del propietario pendiente

Runner commit: fbd4512d163b31e53b355280e636fb47cf8d66a9.

CP-07 usa un servidor fixture dedicado con una inyección de excepción de un solo uso, activada después de aceptar la conexión y entrar al contexto de ownership del socket. El worker registra el fault y lanza RuntimeError; el bloque except registra worker_error; el contexto with cierra la conexión; y finally reduce active y libera el semáforo del slot.

El escenario exige: (1) el peer de la conexión fallida observa EOF y cero bytes de respuesta; (2) se observa el RuntimeError esperado; (3) el contador active vuelve a cero; (4) el proceso servidor permanece vivo; y (5) una segunda conexión válida completa authority.ping y vuelve a active=0. La segunda petición verifica que el accept loop y el worker pool continúan operativos tras la excepción.

La inyección es exclusivamente test-only y no modifica handler productivo. CP-07 está implementado y revisado estáticamente en GitHub, pero no está validado hasta la ejecución del propietario en Atlas-VM-test. CP-08..CP-12 siguen pendientes; overall debe permanecer INCOMPLETE. No se ejecutaron pruebas, builds ni workflows desde GitHub.


## 9.10 Primera ejecución CP-07 y corrección del harness (2026-11-21)

El propietario ejecutó el runner en d054f95f4cce9e33fe55bf61080dcd3f493ed3ce en Atlas-VM-test. MA-01..MA-10 y CP-01..CP-06 volvieron a PASS. CP-07 no llegó a completar sus aserciones: Server._record clasificó el evento worker_error esperado de la inyección como error fatal genérico y abortó el escenario antes de comprobar EOF, recuperación del contador/slot y segunda petición. El resultado fue overall=FAIL; por tanto CP-07 no se considera validado.

Corrección en runner commit c1fdcc12eb3d7a0fcb6cccccb8eb07b0028dcb40: cada instancia Server recibe un contador explícito de errores de worker esperados (1 solo para el fixture CP-07, 0 en todos los demás escenarios). _record consume únicamente el RuntimeError: CP-07 one-shot worker exception previsto; cualquier otro worker_error continúa siendo fatal. La validación de CP-07 sigue pendiente de una nueva ejecución del propietario en la VM desechable. No se ejecutaron pruebas, builds ni workflows desde GitHub; no se modificó handler productivo, contrato, main, host, cuentas, servicios o SQLite.


## 9.11 Segunda ejecución CP-07: reset por paquete pendiente y corrección (2026-11-21)

El propietario ejecutó el runner en commit ccfc495e4bcbe0adc9283f75bee1823d5338451b. MA-01..MA-10 y CP-01..CP-06 PASS; CP-07 falló con ConnectionResetError: [Errno 104] Connection reset by peer. La inspección del flujo muestra que el fixture inyectaba la excepción inmediatamente después de accept, sin consumir el paquete SOCK_SEQPACKET que el cliente ya había enviado. En Linux, cerrar un socket orientado a registros con datos entrantes sin leer puede producir ECONNRESET en el peer, en lugar del EOF ordenado requerido por el escenario. Por tanto no se demostró todavía la recuperación CP-07.

Runner corregido en commit 1df8385f3783308636ccd9538d4c1033fd05be33: el worker CP-07 consume el paquete desencadenante antes de lanzar la excepción deliberada. El evento worker_fault_injected registra el tamaño consumido; la conexión se cierra después de drenar el registro, permitiendo comprobar EOF y cero bytes de respuesta sin confundirlo con el reset causado por datos pendientes. El consumo es específico del fixture de inyección; no altera el handler productivo. Repetir la ejecución completa en Atlas-VM-test. No se ejecutaron pruebas, builds ni workflows desde GitHub.

## A-IPC-02 — CP-07 validado; CP-08/CP-09 implementados (2026-11-21)

El propietario ejecutó el commit `077e01b00e8f3c628d5f1cee44b8a58670434789`
en `Atlas-VM-test`, Debian 13, kernel `6.12.117+deb13-amd64`,
Python 3.13.5, como EUID 0 real y fixtures SERVICE `2005/2005` y
OTHER `2006/2006`. MA-01..MA-10 y CP-01..CP-07 reportaron PASS.
CP-07 confirmó EOF sin respuesta para el peer de la excepción, active=0,
slot liberado, servidor vivo y una segunda petición ping respondida OK.
Cleanup de ambos sandboxes `/run` completado. El resultado global fue
INCOMPLETE únicamente por CP-08..CP-12 aún no implementados en ese commit.

En el siguiente incremento del runner se implementaron CP-08 y CP-09:

- **CP-08 — tamaño de request/response:** request exactamente 16 KiB alcanza
  el decoder (y se rechaza por el campo extra, no por tamaño); 16 KiB + 1
  devuelve `REQUEST_TOO_LARGE`; un paquete mayor que el buffer de recepción
  produce `MESSAGE_TRUNCATED` sin envelope. Para response, se envía un
  paquete de exactamente 64 KiB y se comprueba su longitud íntegra; un
  response de 64 KiB + 1 falla con `INTERNAL_ERROR` antes de enviar bytes.
  Los casos usan sockets AF_UNIX/SOCK_SEQPACKET temporales y el encoder/
  sender real del módulo IPC.
- **CP-09 — profundidad JSON:** la estructura con 16 niveles de contenedores
  anidados pasa el gate de profundidad y llega al rechazo posterior de schema
  (`INVALID_REQUEST` por el campo extra); 17 niveles se rechazan como
  `INVALID_JSON`. El root object cuenta como profundidad 1, por lo que se
  usan 15/16 listas anidadas respectivamente para construir profundidad total
  16/17.

**Estado de CP-08/CP-09:** implementados y revisados estáticamente en GitHub;
pendientes de ejecución del propietario en `Atlas-VM-test`. No se ejecutaron
pruebas, compilaciones ni workflows desde GitHub. CP-10..CP-12 permanecen
sin implementar: contabilidad de FDs/threads bajo carga, ciclos de carga y
recuperación después de saturación, y rechazo de startup con RLIMIT_NOFILE
insuficiente sin elevarlo.

Siguiente paso: ejecutar el runner actualizado solo en la VM desechable y
compartir el JSON completo. No usar `greed` de producción. Esta etapa no
modifica handler/contrato, no crea servicios y no autoriza listener
persistente, systemd, SQLite, cambios del host ni despliegue.

## A-IPC-02 — CP-08/CP-09 validados; CP-10 implementado (2026-11-21)

El propietario ejecutó el commit `caf7bbb8c83388a3723b66a7f4060a01c97c171d`
en `Atlas-VM-test`, Debian 13, kernel `6.12.117+deb13-amd64`,
Python 3.13.5, EUID 0, fixtures SERVICE `2005/2005` y OTHER
`2006/2006`.

- MA-01..MA-10 y CP-01..CP-09: PASS.
- CP-08: request exacto 16 KiB alcanzó schema validation; 16 KiB+1 produjo
  `REQUEST_TOO_LARGE`; paquete mayor que el buffer produjo
  `MESSAGE_TRUNCATED` y cero bytes de respuesta. Response exacto 64 KiB
  llegó íntegro; 64 KiB+1 fue rechazado y el peer recibió cero bytes.
- CP-09: profundidad total 16 llegó a schema validation
  (`INVALID_REQUEST` por campo extra); profundidad 17 fue rechazada como
  `INVALID_JSON`.
- CP-05/06/07 y backlog conservaron PASS en la misma ejecución.
- Cleanup de sandboxes privado y traversal confirmado; duración 22.678 s.
- Overall INCOMPLETE solo porque CP-10..CP-12 no estaban incluidos en ese
  commit.

El runner implementó CP-10 en commits `e02bbbb7e3eacb45fbeab620d00cf0463e1c827e`
y `bf3c62375fd8a3017b332efe406be9d1fd903568`:

- Lee `/proc/<pid>/fd`, `/proc/<pid>/task` y `/proc/<pid>/status`
  del proceso fixture de servicio.
- Toma snapshot base y snapshot con cuatro workers ocupados y nueve
  conexiones pendientes (cola efectiva AF_UNIX para `listen(8)`).
- Verifica máximo 64 FDs por `RLIMIT_NOFILE=64`, exactamente cuatro
  threads worker más el thread principal (máximo 5), y que el servidor
  vuelve a active=0 después de cerrar los peers y drenar la cola.
- Comprueba también que el proceso sigue vivo y que el límite soft/hard
  reportado por procfs es 64/64.

**CP-10 está implementado y revisado estáticamente, pendiente de ejecución
del propietario.** Esta medida observa el proceso fixture/harness, no
establece límites productivos de memoria, CPU, TasksMax ni inventario de un
entrypoint futuro. CP-11/12 siguen pendientes: ciclos repetidos de
saturación/recuperación y rechazo de startup con RLIMIT_NOFILE insuficiente
sin elevarlo.

Siguiente paso: actualizar y ejecutar el runner solo en la VM desechable
`Atlas-VM-test`; nunca en `greed` producción. No se ejecutaron pruebas,
builds ni workflows desde GitHub. No se modificó handler, contrato,
`main`, host, cuentas, servicios, permisos ni SQLite.


## 9.12 CP-10 — fallo de diagnóstico procfs y corrección (2026-11-21)

El propietario ejecutó el commit `cbfe0e20a79ae3ee8fd901ba43ea6df360962398` en `Atlas-VM-test`. MA-01..MA-10 y CP-01..CP-09 reportaron PASS; CP-10 abortó antes de producir snapshots con `ProbeFailure: CP-10 procfs status omitted Max open files`. Los sandboxes `/run` se eliminaron correctamente. El resultado global fue FAIL por un defecto del lector de evidencia, no por una medición que demostrara exceso de FDs o threads.

La revisión estática confirmó que el runner buscaba `Max open files` en `/proc/<pid>/status`, pero Linux publica ese límite en `/proc/<pid>/limits`. Commit `47b9ed94c21d26b18c415bedd2f1d352894f2620` corrige únicamente la fuente procfs y el mensaje de diagnóstico; conserva la validación de soft/hard 64/64 y las mediciones de `fd/` y `task/`. No se ejecutaron pruebas, builds ni workflows desde GitHub.

CP-10 queda **corregido estáticamente, pendiente de nueva ejecución del propietario**. No atribuir PASS hasta recibir una ejecución satisfactoria. CP-11/CP-12 continúan pendientes; overall no puede ser PASS. Ejecutar solo en `Atlas-VM-test` desechable, nunca en `greed` producción.


## 9.13 CP-10 — sincronización del contador de accepts (2026-11-21)

El propietario ejecutó el commit `892d934267684fc8d5a179993f71c2b11c614c7e`: MA-01..MA-10 y CP-01..CP-09 PASS; CP-10 falló en la comprobación de accepts durante saturación. El error original no incluyó los valores baseline/observed, por lo que no permite concluir que el servidor haya aceptado realmente conexiones pendientes.

La revisión estática observó que `Server` consume stdout mediante un reader thread asíncrono, mientras CP-10 calculaba `accepted_before` directamente desde `server.events` sin reconciliar eventos todavía en la cola. Esto podía dejar el baseline atrasado y causar una comparación falsa. Commit `7c009dac7fd7c4270ea6edf8bc1a004a8fb8f898`: CP-10 drena eventos previos antes de capturar el baseline y, si la comprobación vuelve a fallar, informa baseline, expected, observed, pending y workers. La comprobación estricta se conserva; no se suprime ni relaja una aceptación real.

**CP-10 sigue pendiente de ejecución**. Esta modificación es una corrección de sincronización/diagnóstico revisada estáticamente, no evidencia de PASS ni de que la causa esté confirmada. No se ejecutaron pruebas, builds ni workflows desde GitHub. Repetir solo en `Atlas-VM-test` desechable.


Ajuste complementario en commit `664c398a5afdafda313eb81379cbb85a5b71007d`: `Server.drain(duration)` ahora mantiene la ventana completa aunque la cola esté temporalmente vacía, permitiendo que el reader thread transfiera eventos stdout que aún estaban en tránsito. Esto hace efectiva la sincronización previa del baseline; la aserción de accepts permanece estricta. Sigue pendiente de ejecución del propietario.

## 9.14 CP-10 — validación del propietario (2026-11-21)

El propietario ejecutó el commit `75929e1f9f3a17e2a19bb9a98d30e7cd86b26a0a`
como root en la VM desechable `Atlas-VM-test`: Debian 13,
kernel `6.12.117+deb13-amd64`, Python 3.13.5; fixtures SERVICE
2005/2005 y OTHER 2006/2006.

**MA-01..MA-10 y CP-01..CP-10: PASS.** Para CP-10 se observaron cuatro
workers activos y nueve conexiones pendientes; el contador de accepts
permaneció estable durante saturación (22). Snapshots del proceso:
baseline 4 FDs/5 threads; saturación 8 FDs/5 threads; recuperación
4 FDs/5 threads. `RLIMIT_NOFILE` soft/hard permaneció 64/64,
`active_after_recovery=0` y el servidor siguió vivo. Duración 22.725 s.
Los sandboxes privado y traversal bajo `/run` fueron eliminados después
de finalizar los procesos hijos.

La evidencia confirma CP-10 en ese commit y entorno. No establece una
política de recursos productiva ni autoriza listener persistente o
despliegue. CP-11 (ciclos repetidos de saturación/recuperación) y CP-12
(rechazo de startup con `RLIMIT_NOFILE` insuficiente, sin elevarlo)
continúan pendientes. No se ejecutaron pruebas, builds ni workflows desde
GitHub.

## 9.15 CP-11 — recuperación repetida implementada (2026-11-21)

Runner commit: `70ee6a7a77dc671fe4ec26a6ca98a25a2e47e104`.
CP-11 ejecuta tres ciclos consecutivos sobre el mismo servidor fixture.
Cada ciclo ocupa los cuatro workers, encola nueve conexiones AF_UNIX,
comprueba que el contador accepted no avance durante saturación, cierra
todos los peers y exige drenar las trece conexiones aceptadas. Toma
snapshots de FDs/threads antes, durante y después de cada ciclo; los
contadores deben volver exactamente a su baseline y el servidor debe
seguir vivo.

CP-11 es instrumentación exclusiva del harness; no modifica código
productivo. Está implementado y revisado estáticamente, pero **pendiente
de validación del propietario** en `Atlas-VM-test`. CP-12 sigue sin
implementarse: rechazo de startup al heredar un `RLIMIT_NOFILE`
insuficiente, sin elevarlo. Overall permanece INCOMPLETE.

## 9.16 CP-11 — validación del propietario (2026-11-21)

El propietario ejecutó `da8c6ea9ed0ce36d2c7b4c2c8c5417dd79975fb7`
en `Atlas-VM-test` desechable (Debian 13, kernel
`6.12.117+deb13-amd64`, Python 3.13.5). MA-01..MA-10 y CP-01..CP-11:
**PASS**. Los tres ciclos mantuvieron cuatro workers y nueve conexiones
pendientes; accepted: 31→35→44, 44→48→57 y 57→61→70. Cada ciclo
volvió a 4 FDs/5 threads, con 8 FDs/5 threads durante saturación,
active=0 tras recuperación y servidor vivo. Cleanup correcto; duración
24.72 s.

## 9.17 CP-12 — rechazo de startup con RLIMIT heredado bajo (2026-11-21)

Runner commit: `0fb5c3989f5ac9e11b14344557b18ad7bd75027b`. El proceso
fixture rechaza startup si el soft o hard `RLIMIT_NOFILE` heredado es
menor que 64; informa ambos valores y termina antes de crear/bindear el
listener. CP-12 inicia el child mediante un wrapper que baja ambos límites
heredados a 32 antes de `exec`, y verifica exit code 3, evento exacto de
rechazo, límites observados y ausencia de pathname de socket. No eleva el
límite. Es validación del harness, no política productiva. Revisión estática
solamente; falta ejecución del propietario en `Atlas-VM-test` desechable.



## 9.18 — validación completa de A-IPC-02 por el propietario (2026-11-21)

El propietario ejecutó el runner completo en la VM desechable `Atlas-VM-test`
sobre el checkout `66b348e1be9a7e614d51c4b3ade9e643c9152106`:
Debian 13, kernel `6.12.117+deb13-amd64`, Python 3.13.5, EUID efectivo 0,
fixtures SERVICE UID/GID `2005/2005` y OTHER `2006/2006`.
Duración: 24.991 s. El JSON reportó **`overall=PASS`**, sin escenarios
omitidos ni fallidos, y confirmó la eliminación de ambos sandboxes temporales
bajo `/run` después de salir los procesos hijos.

**Resultado:** MA-01..MA-10 y CP-01..CP-12: PASS.

Observaciones relevantes:

- **Autenticación mutua (MA-01..MA-06):** cliente root autenticó servidor
  UID 2005 antes de enviar; servidor rechazó peer UID 2006 antes de leer
  (cero bytes de respuesta); cliente rechazó servidor UID 2006 antes de
  enviar (cero bytes); cliente EUID 2006 fue rechazado antes de connect.
  Claims JSON falsos UID 0/GID 0/PID 1 fueron rechazados como
  `INVALID_REQUEST`; la identidad observada provino de SO_PEERCRED.
- **Configuración/snapshot (MA-07/08):** 11 variantes inválidas rechazadas;
  configuración válida aceptada con `client_uids=[0]`; reemplazo del archivo
  no alteró el snapshot inmutable cargado.
- **Desconexión y transporte (MA-09/10):** desconexión previa a request produjo
  `PEER_DISCONNECTED`, cero respuesta; AF_UNIX/SOCK_STREAM y
  AF_INET/SOCK_STREAM fueron rechazados antes de leer.
- **Capacidad y backpressure (CP-01..04):** máximo cuatro workers; con
  `listen(8)`, Linux permitió nueve conexiones pendientes; la décima recibió
  EAGAIN (errno 11). La cola observada fue 8 y luego 9, sin exceder cuatro
  workers activos.
- **Timeouts (CP-05/06):** timeout de lectura observado en 5.009 s; el
  escenario de deadline global cerró a 15.005 s, con 3.998 s disponibles al
  comenzar la lectura después de la demora test-only.
- **Recuperación (CP-07):** excepción `RuntimeError` aislada, peer EOF y
  cero respuesta; slot liberado, servidor vivo y ping posterior `OK`.
- **Tamaños y JSON (CP-08/09):** request 16 KiB aceptado hasta schema
  validation; 16 KiB+1 rechazado; paquete truncado detectado. Response
  64 KiB enviado íntegro y tamaño superior rechazado antes de enviar.
  Profundidad JSON 16 llegó a schema validation; profundidad 17 produjo
  `INVALID_JSON`.
- **Recursos (CP-10/11):** baseline 4 FDs/5 threads; saturación 8 FDs/5
  threads; recuperación exacta a 4 FDs/5 threads, active=0 y servidor vivo.
  Tres ciclos consecutivos repitieron la recuperación sin crecimiento de
  recursos.
- **Límite heredado (CP-12):** el child heredó soft/hard
  `RLIMIT_NOFILE=32/32` frente al requisito 64; rechazó startup con exit
  code 3 y evento `startup_error`, no elevó el límite y no creó el socket.

Esta evidencia valida los escenarios del harness A-IPC-02 en el commit y VM
indicados. **No aprueba** un listener persistente, el transporte AF_UNIX
para producción, el entrypoint administrativo real, integración systemd,
acceso a SQLite, operaciones mutantes ni despliegue. El perfil de capacidad
continúa siendo experimental. No se ejecutaron pruebas, builds ni workflows
desde GitHub; el resultado fue ejecutado por el propietario. 
