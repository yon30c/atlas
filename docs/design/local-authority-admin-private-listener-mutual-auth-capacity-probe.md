# Plan de probe aislado — autenticación mutua y capacidad IPC

**Fecha:** 2026-11-21  
**Estado (2026-11-21):** el propietario reportó en `Atlas-VM-test` MA-01..MA-10 y CP-01/CP-04 PASS; global INCOMPLETE en la ejecución de `901c792cb723d920da4970ecce98ea7f871c4f85` (JSON `commit: null`). CP-02/CP-03 se implementaron después para observar y llenar exactamente el backlog AF_UNIX con iproute2 `ss`, y comprobar rechazo EAGAIN del intento excedente; esta nueva implementación está pendiente de ejecución local. CP-05..CP-12 siguen pendientes.  
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
| CP-02 | Más clientes llegan mientras slots están ocupados | El kernel retiene como máximo el backlog configurado |
| CP-03 | Backlog lleno | El proceso no crea workers, sockets aceptados ni memoria de cola ilimitados |
| CP-04 | Se libera un slot | El accept loop recupera capacidad sin reiniciar |
| CP-05 | Cliente no envía paquete | Conexión termina al alcanzar deadline global de 15 s |
| CP-06 | Read y write separados | La suma no reinicia ni excede el deadline global |
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
