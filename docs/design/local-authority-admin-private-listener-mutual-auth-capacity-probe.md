# Plan de probe aislado — autenticación mutua y capacidad IPC

**Fecha:** 2026-11-21  
**Estado:** plan de validación aprobado a nivel de diseño; no implementado ni ejecutado.  
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
- La prueba de credenciales reales requiere procesos separados con UIDs distintos. Preferir un mecanismo aislado (por ejemplo, user namespace con mapeo explícito) que no cree ni modifique cuentas del host. Si el kernel/entorno no permite demostrar las credenciales reales requeridas, marcar INCOMPLETE; no sustituirlas por mocks y declarar PASS.
- No reutilizar la identidad temporal atlas-a09-test, sus claves, HOME o configuración SSH.
- No modificar /etc/atlas, usuarios, grupos, sudoers, PAM, SSH, systemd, permisos del host ni servicios.
- No usar el socket administrativo real, SQLite, DBs existentes ni rutas persistentes.
- El harness no ejecutará sudo, su, runuser ni cambios globales de credenciales. Cualquier mecanismo de aislamiento debe quedar dentro de la VM desechable y documentado antes de implementarse.
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
| MA-09 | Socket peer se desconecta durante autenticación | Cierre limpio, sin bytes de protocolo ni operación |
| MA-10 | Transporte no es AF_UNIX/SOCK_SEQPACKET | Rechazo |

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

1. Revisar este plan contra las APIs disponibles del handler y las garantías del kernel.
2. Diseñar harness temporal con fixtures de procesos separados y métricas explícitas; no implementar todavía listener persistente.
3. Implementar primero autenticación mutua en cliente/servidor de fixture, sin DB ni operaciones administrativas.
4. Añadir resolución de rutas y pruebas de colisión/cleanup.
5. Añadir pool fijo/backpressure/deadline/FD accounting.
6. Validar manualmente stale recovery en sandbox separado.
7. Entregar comandos y commit exacto para ejecución por el propietario en Debian/VM.
8. Revisar resultados y cerrar hallazgos antes de proponer cualquier listener persistente.

No combinar esta etapa con implementación del entrypoint administrativo real ni con las operaciones authority.diagnose, migraciones, initialize o provisioning.

## 10. Límites

- Este documento es un plan de probe, no una implementación.
- No modifica el contrato atlas-admin/1 ni el handler actual.
- No se ejecutaron pruebas, compilaciones ni workflows.
- No se crearon cuentas, grupos, archivos de configuración del host, sockets persistentes ni servicios.
- No se autorizó despliegue, acceso SQLite, cambios de privilegios ni producción.
