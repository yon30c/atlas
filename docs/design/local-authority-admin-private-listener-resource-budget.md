# Presupuesto de recursos y backpressure — listener IPC administrativo

**Fecha:** 2026-11-21  
**Estado:** propuesta de capacidad inicial para revisión; no implementada ni aprobada para producción.  
**Dependencias:** `atlas-admin/1`, handler actual, lifecycle, probe A-IPC-01/A14 y TCB-1.  
**Relacionado:** `local-authority-admin-private-listener-threat-model-review.md`.

## 1. Objetivo y límites

Definir límites explícitos para accept, conexiones activas, workers, backlog, descriptores, tamaños y deadlines antes de implementar un servicio persistente. El handler actual valida un paquete y una respuesta, pero no implementa accept loop, pool, backpressure, límites globales ni shutdown.

Los límites de A14 son exclusivamente del harness: dos workers activos y backlog ocho. El resultado A14 no constituye evidencia de capacidad de producción ni justifica copiar sus valores.

## 2. Límites ya existentes en el handler

Revisión estática de `src/atlas/platform_admin_ipc.py`:

| Control | Valor actual | Significado |
|---|---:|---|
| Request máximo | 16 KiB | El handler recibe como máximo límite + 1 para detectar exceso |
| Response máximo | 64 KiB | La respuesta se codifica y limita antes de enviar |
| Profundidad JSON | 16 | Límite de anidamiento |
| Timeout lectura por defecto | 5 s | Timeout de una operación recv |
| Timeout escritura por defecto | 5 s | Timeout de una operación send |
| Timeout configurable máximo | 60 s | Tope de cada timeout individual, no deadline global |

El handler no impone deadline total desde accept hasta cierre. Los 5 s de lectura y 5 s de escritura tampoco equivalen a un presupuesto global. El caller puede pasar otros valores dentro del máximo.

## 3. Perfil inicial recomendado para revisión

Los valores siguientes son una propuesta conservadora para el primer servicio administrativo local de baja frecuencia. No son valores ya implementados ni una aprobación de systemd.

| Recurso | Propuesta inicial | Razón |
|---|---:|---|
| Conexiones procesadas simultáneamente | 4 | Permite una operación interactiva y varias consultas/status breves sin concurrencia ilimitada |
| Workers | 4 fijos | Un worker por conexión admitida; nunca crear threads ilimitados |
| Backlog kernel | 8 | Absorbe ráfagas cortas; no crea una cola de aplicación ilimitada |
| Cola de aplicación | 0 | Backpressure directo: cuando los 4 slots están ocupados, el accept loop deja de aceptar y el kernel mantiene la cola limitada |
| Request/response/depth | 16 KiB / 64 KiB / 16 | Conservar los límites ya presentes en el handler |
| Read/write timeout | 5 s / 5 s | Conservar los defaults del handler para IPC de control |
| Deadline total de conexión | 15 s | Límite absoluto desde accept hasta respuesta/cierre; requiere implementación con reloj monotónico |
| Descriptores abiertos (`RLIMIT_NOFILE`) | 64, candidato | Presupuesto inicial con margen; validar contra logging, config, listener, workers y conexiones SQLite reales |
| Conexiones por socket | Una solicitud por conexión | El handler ya procesa un único paquete; cerrar después de una respuesta |

**Por qué 4 y no los 2 de A14:** A14 usa 2 para demostrar saturación y recuperación del harness. El perfil propuesto 4 es una decisión de capacidad para permitir varias solicitudes de control/status breves, no una extrapolación de la prueba. Debe confirmarse con el flujo real del frontend y medirse en el entorno aislado.

## 4. Backpressure y admisión

- El accept loop mantiene un pool fijo de cuatro workers y cuatro slots.
- El loop solo acepta cuando existe un slot libre. Cuando todos están ocupados, deja de llamar a accept; el kernel mantiene como máximo el backlog configurado.
- No se acumulan sockets aceptados en una cola Python sin límite.
- Cuando el backlog se llena, el cliente puede recibir error/timeout de connect. El cliente debe usar timeout finito y mostrar un fallo de capacidad; no reintentar indefinidamente.
- Cada conexión procesa una sola solicitud y se cierra.
- El servidor nunca lee datos de un peer no autorizado. La autenticación SO_PEERCRED debe ocurrir antes del recv de protocolo.
- Los errores de capacidad se registran con rate limit; no crear una entrada de log por cada intento abusivo.
- No existe respuesta IPC de “busy” si la conexión no ha sido admitida y el request_id no se ha leído; el cliente debe tratar la desconexión/timeout como resultado de transporte, no como resultado de operación.

El frontend no debe repetir automáticamente una operación mutante ante timeout ambiguo. La capa de operaciones debe tener request/operation IDs e idempotencia según el contrato; ese comportamiento es independiente del pool de conexiones.

## 5. Separación entre conexión y trabajo administrativo

Una conexión de control no debe quedar retenida durante una migración, inicialización o provisioning de larga duración. El diseño de dominio debe:

- validar y registrar la operación;
- devolver un estado no terminal y un identificador de operación cuando corresponda;
- ejecutar trabajo mutante mediante un executor acotado y serializado;
- permitir consultas breves de `authority.operation.status` mientras la operación sigue activa;
- rechazar o diferir una segunda mutación concurrente de forma determinista.

Propuesta de dominio inicial: máximo una operación mutante activa; las consultas de estado/diagnóstico y ping usan el presupuesto de conexiones sin abrir un segundo writer SQLite. La concurrencia de lecturas debe fijarse al revisar las operaciones y el contrato de resultados. No crear una cola ilimitada de trabajos.

Esto no está implementado por el handler actual y requiere alineación con el diseño de operaciones administrativas antes de implementar.

## 6. Presupuesto de descriptores

El valor candidato `RLIMIT_NOFILE=64` debe validarse con un inventario real. Presupuesto conceptual:

- listener + descriptor del directorio endpoint + configuración;
- stdin/stdout/stderr y logging;
- hasta cuatro sockets aceptados;
- hasta cuatro conexiones/handles de base de datos si el diseño futuro los permite;
- descriptors auxiliares (signal/event, auditoría, temporales) y margen operativo.

El servicio debe fallar al iniciar si no puede reservar/validar los recursos mínimos. No abrir conexiones SQLite por adelantado solo para consumir el límite; usar el pool real aprobado. La cuenta final debe considerar todos los FDs simultáneos y no asumir que cuatro conexiones equivalen a cuatro FDs.

El límite de procesos/threads, memoria y CPU no se fija todavía: depende del entrypoint, librerías, stack de threads, logging y acceso SQLite. Se debe medir en un sandbox antes de fijar límites del supervisor. No imponer `MemoryMax`, `TasksMax`, seccomp ni directivas systemd sin revisar el runtime real.

## 7. Shutdown y deadlines

- Deadline de conexión propuesto: 15 s total, distinto del timeout de cada syscall.
- El deadline se calcula con reloj monotónico y se propaga al handler; cada recv/send recibe el tiempo restante, nunca un timeout nuevo que reinicie el presupuesto total.
- Al iniciar shutdown, dejar de admitir conexiones nuevas y cerrar el listener.
- Drenar conexiones activas dentro de un plazo explícito; el plazo final y comportamiento de operaciones mutantes pertenecen a A-THREAT-08 y al contrato de operaciones.
- No cancelar una transacción SQLite a mitad sin un mecanismo de rollback/estado ambiguo definido.
- Cerrar cada socket y liberar slot en `finally`, incluidos errores de autenticación, protocolo, timeout y desconexión.

El plazo de drenaje/shutdown no se fija en este documento porque requiere resolver la máquina de estados del lifecycle.

## 8. Escenarios de validación

En un probe desechable, no en Debian productivo:

1. Cuatro workers se ocupan; el quinto cliente permanece en backlog y no crea un quinto worker.
2. El backlog se llena; el proceso no crea threads, sockets aceptados ni memoria de cola sin límite.
3. Al liberarse un slot, el accept loop recupera capacidad.
4. Peer no autorizado se cierra antes de leer bytes.
5. Cliente que no envía solicitud se libera al vencer el deadline global.
6. Cliente que envía paquete máximo y respuesta máxima respeta límites.
7. Timeout de lectura más timeout de escritura no exceden el deadline total.
8. Excepciones de worker siempre cierran conexión y liberan slot.
9. Shutdown detiene accept y drena/cierra todas las conexiones según deadline.
10. El número de FDs y threads nunca supera el presupuesto configurado.
11. Una operación mutante activa no bloquea indefinidamente consultas de estado y no permite un segundo writer concurrente.

Los escenarios son requisitos futuros. No se han implementado ni ejecutado.

## 9. Decisiones pendientes

1. Confirmar si el flujo real del frontend necesita cuatro conexiones simultáneas o si basta un límite menor.
2. Confirmar backlog ocho y deadline total de conexión de 15 s.
3. Validar `RLIMIT_NOFILE=64` con inventario de FDs del servicio real.
4. Definir política de concurrencia de lecturas y mutaciones contra el contrato de operaciones/SQLite.
5. Medir memoria, CPU y threads antes de fijar límites del supervisor.
6. Definir deadline de shutdown en A-THREAT-08.

## 10. Límites

- Revisión estática y diseño desde GitHub.
- No se modificó handler, contrato normativo, runtime, SQLite ni host.
- No se ejecutaron pruebas, compilaciones ni workflows.
- No se implementó listener, worker pool, scheduler ni configuración de recursos.
- No se aprobaron systemd, límites del host ni despliegue.
