# Contrato propuesto de parada y exclusividad del listener administrativo — listener-quiescence/1

**Identificador:** ATLAS-CONTRACT-LOCAL-AUTHORITY-LISTENER-QUIESCENCE  
**Versión:** 1.0-draft  
**Estado:** PROPUESTA PARA REVISIÓN DEL PROPIETARIO; no aprobada como arquitectura, operación ni despliegue.  
**Fecha:** 21 de noviembre de 2026.  
**Ámbito:** alternativa A — listener AF_UNIX/SOCK_SEQPACKET creado y poseído por el proceso del servicio bajo `atlas-runtime`.  
**Dependencias:** TCB-1; `atlas-admin/1`; `local-authority-admin-listener-lifecycle.md`; `local-authority-admin-private-listener-stale-recovery.md`; A-IPC-04.

---

## 1. Propósito

Definir qué evidencia debe reunir una futura operación de mantenimiento antes de declarar que el listener administrativo está quiescente y que un pathname residual podría pasar a una evaluación separada de recuperación.

Este contrato no implementa ni autoriza la recuperación. Su función es cerrar el vacío entre «el servicio recibió stop» y «ningún proceso puede conservar el descriptor listener».

La regla principal es:

> **No se puede declarar quiescencia por el mero estado `inactive` de una unidad, por ausencia de un PID principal, por una lectura de `/proc/net/unix`, ni por la ausencia del pathname en una tabla AF_UNIX.** La declaración requiere demostrar conjuntamente el cierre de la unidad correcta, el vaciado del cgroup exclusivo y las invariantes de propiedad/no delegación del descriptor.

## 2. Estado y precedencia

Este documento es un contrato propuesto de lifecycle y mantenimiento, subordinado al contrato normativo `atlas-admin/1`. No modifica el envelope, el catálogo, las credenciales ni la autorización de operaciones IPC.

Hasta que el propietario lo apruebe expresamente:

- sus requisitos son criterios de diseño para revisión, no instrucciones operativas;
- no se deben crear unidades, cgroups, cuentas, rutas o servicios en Debian;
- no se debe ejecutar una recuperación real ni eliminar sockets;
- el arranque normal debe seguir fallando cerrado ante cualquier pathname preexistente;
- el token de SR-10 continúa siendo fixture-only y no representa aprobación humana.

Si una implementación existente contradice esta propuesta, no se debe asumir que el código está autorizado: se documenta la diferencia y se solicita decisión.

## 3. Modelo de confianza y supuestos

### 3.1 TCB-1

Se conserva la decisión TCB-1 aceptada: todos los procesos bajo el UID dedicado `atlas-runtime` forman un único dominio confiable. Root es autoridad superior confiable. El contrato no pretende defenderse de root, de un proceso comprometido dentro de TCB-1 ni de capacidades equivalentes.

La cuenta `atlas-runtime` debe ser dedicada y de uso exclusivo para el servicio y los componentes explícitamente autorizados. No debe utilizarse para login interactivo, tareas generales, sesiones de usuario, cron ajeno ni procesos no relacionados.

### 3.2 Supuesto de propiedad del listener

Este contrato cubre únicamente la alternativa A:

- el propio proceso del servicio crea el socket con `socket()`, `bind()` y `listen()`;
- el descriptor listener nace dentro del cgroup de servicio;
- el descriptor permanece bajo control del proceso del servicio;
- no se usa systemd socket activation ni se recibe el descriptor desde otro supervisor.

La propiedad anterior es un requisito que deberá verificarse en el futuro entrypoint; no es una capacidad existente demostrada hoy.

### 3.3 Límite de la afirmación

La evidencia de cgroup solo sirve si el listener nunca pudo escapar de ese dominio mediante herencia, duplicación, transferencia o recepción desde un proceso externo. Por eso la contención de procesos y la política de descriptores son requisitos conjuntos e inseparables.

## 4. Invariantes normativos propuestos

### Q-01 — Unidad de servicio exclusiva

El listener se ejecutará en una unidad de servicio dedicada y estable, con cgroup propio. No compartirá el cgroup con servicios no relacionados ni con procesos administrativos interactivos.

La unidad no delegará el control de su cgroup a procesos del servicio. La identidad de la unidad y su cgroup deben obtenerse del system manager confiable, no de valores suministrados por el proceso que se está inspeccionando.

### Q-02 — Un único propietario de lifecycle

Un solo supervisor autorizado controlará start, stop, restart y recuperación. Durante una operación de mantenimiento debe existir una puerta de exclusión que impida un start/restart concurrente hasta finalizar la inspección y la decisión humana.

La puerta debe cubrir también automatizaciones, timers, dependencias y políticas de restart. Si no puede demostrarse que no hay un job de inicio/reinicio pendiente ni un actor autorizado que pueda iniciarlo durante la ventana, se aborta.

No se prescribe todavía el mecanismo concreto de exclusión (lock, modo de mantenimiento o coordinador); requiere un diseño verificable y root-managed.

### Q-03 — Terminación de todo el cgroup

La unidad debe usar una política de parada que termine todos los procesos del cgroup, no solo el PID principal. `KillMode=control-group` es el candidato inicial para systemd, sujeto a validación en la versión/manager objetivo.

Una parada se considera completada solo cuando concurren:

1. el system manager informa que la unidad objetivo está `inactive` y no está en transición;
2. no existe un job start/restart pendiente para esa unidad;
3. el cgroup de esa invocación está identificado sin ambigüedad;
4. el archivo `cgroup.events` de ese cgroup informa `populated 0`;
5. la observación se obtiene después de que el supervisor haya completado stop y antes de liberar la puerta de exclusión;
6. cualquier error, desaparición inesperada o inconsistencia de lectura produce ABORT.

El estado `inactive` sin `populated 0` no es suficiente. `populated 0` sin identidad inequívoca del cgroup tampoco lo es.

### Q-04 — No escape ni delegación de procesos

La unidad no debe habilitar delegación del cgroup ni permitir que procesos del servicio muevan procesos fuera de él. Las capacidades y permisos que permitan alterar la jerarquía cgroup deben quedar fuera del servicio.

Los procesos auxiliares que el servicio llegue a crear deben permanecer dentro del mismo cgroup y ser terminados por la política de parada. No se acepta un helper persistente fuera del cgroup que pueda conservar el listener o reiniciar el servicio.

### Q-05 — Propiedad exclusiva del descriptor listener

El descriptor listener:

- se crea dentro del proceso/cgroup del servicio;
- se marca close-on-exec desde su creación o inmediatamente después, antes de cualquier posibilidad de exec;
- no se duplica para procesos externos;
- no se hereda a procesos hijos;
- no se envía ni recibe mediante `SCM_RIGHTS`;
- no se publica por IPC, archivos, variables de entorno, sockets auxiliares ni mecanismos equivalentes;
- no se registra en un supervisor externo que lo retenga después de parar el servicio.

`CLOEXEC` es una defensa contra fuga a través de exec, no una defensa contra fork. Por ello el diseño debe prohibir fork después de crear el listener, o demostrar que cualquier descendiente permanece dentro del cgroup y que la parada lo termina. La opción preferida para la primera implementación es no crear procesos hijos después de bind/listen.

La aplicación no debe aceptar ancillary data con descriptores. La regla se aplica en ambos sentidos: ni envío ni recepción de FD para el listener.

### Q-06 — Sin descriptores retenidos fuera del cgroup

El contrato solo permite usar `cgroup.events: populated 0` como evidencia de ausencia de procesos capaces de poseer el listener porque Q-04/Q-05 excluyen que el FD sea transferido a procesos externos.

Si no puede probarse la política de no delegación/transferencia, el cgroup vacío no demuestra ausencia global del descriptor. En ese caso se requiere una técnica independiente y fiable de inventario de referencias FD o el diseño debe permanecer bloqueado; la enumeración procfs limitada de A-IPC-04 no basta para suplir esa prueba.

### Q-07 — Identidad de invocación y cgroup estable

La operación debe registrar y correlacionar, como mínimo:

- nombre de unidad exacto;
- identificador de invocación de systemd (cuando esté disponible);
- cgroup path resuelto por el manager;
- identidad del cgroup (descriptor/metadata relevante y filesystem cgroup v2 esperado);
- instante monotónico de inicio y final de la observación;
- estado de unidad y resultado de lectura de `cgroup.events`.

No se debe confiar en un PID reciclable como identidad de la instancia. Si el manager no permite distinguir la invocación que se detuvo de una instancia posterior, abortar.

### Q-08 — Puerta fail-closed

Cualquier condición no demostrada se interpreta como NO QUIESCENTE. No existe estado «probablemente detenido» que permita continuar.

Son abortos obligatorios, entre otros:

- unidad ausente, duplicada, desconocida o en transición;
- cgroup inesperado, compartido, delegado o no identificable;
- `populated 1` o cualquier valor distinto de `0`;
- lectura parcial, error de permisos, parseo ambiguo o filesystem cgroup no esperado;
- proceso residual dentro del cgroup;
- job de restart/start pendiente o puerta de exclusión no adquirida;
- evidencia de fork/FD passing/descriptor externo;
- pérdida de identidad de invocación durante la comprobación;
- discrepancia entre estado del manager y estado del cgroup.

ABORT conserva el pathname residual sin modificarlo y requiere investigación manual.

## 5. Procedimiento de quiescencia propuesto

Esta secuencia es una especificación de diseño, no un runbook autorizado para ejecutar hoy.

1. Adquirir una puerta de mantenimiento root-managed que excluya start/restart y otras recuperaciones concurrentes.
2. Resolver el nombre exacto de la unidad desde configuración confiable; no aceptar nombre de unidad desde argumentos de usuario no validados.
3. Consultar al system manager y capturar identidad de unidad/invocación y cgroup antes de detener.
4. Solicitar stop a la unidad de servicio mediante el único supervisor autorizado.
5. Esperar un resultado terminal dentro de un deadline monotónico acotado. Un timeout produce ABORT; no se continúa con inspección destructiva.
6. Verificar estado `inactive`, ausencia de transición y ausencia de jobs start/restart.
7. Abrir/leer la evidencia del cgroup identificado; verificar filesystem cgroup v2 y `cgroup.events` con `populated 0`.
8. Volver a consultar la identidad de unidad/invocación para descartar sustitución o reinicio entre las observaciones.
9. Releer `cgroup.events` y exigir que permanezca `populated 0` mientras la puerta de mantenimiento sigue adquirida.
10. Registrar evidencia completa, versión del supervisor/kernel, resultado y cualquier incertidumbre.
11. Mantener la puerta de mantenimiento hasta terminar la decisión separada sobre el pathname. La quiescencia no autoriza por sí misma `unlinkat`.
12. Liberar la puerta únicamente cuando la operación concluya en un estado explícito y auditable. Ante error, mantener el objeto y escalar; no intentar cleanup compensatorio.

No se propone una espera basada únicamente en `sleep`, ausencia de PID principal, `pgrep`, `/proc/net/unix` o conexión al socket.

## 6. Separación entre quiescencia y recuperación

El resultado de esta especificación tiene dos estados:

- `QUIESCENT`: todas las condiciones Q-01..Q-08 relevantes han sido demostradas para la invocación exacta.
- `ABORT_NOT_QUIESCENT`: una o más condiciones no se han demostrado, existe discrepancia o la evidencia no es completa.

Incluso `QUIESCENT` solo permite pasar a una segunda puerta independiente: inspección del pathname mediante descriptor de directorio, validación de tipo/owner/mode/`st_dev`/`st_ino`, revisión de tablas AF_UNIX dentro del alcance definido y aprobación humana explícita ligada a la identidad exacta del objeto.

La autorización humana debe ser real, autenticada, específica para la acción y objeto, de un solo uso y auditable. El token fixture-only de SR-10 no satisface este requisito.

El residual TOCTOU entre revalidación e `unlinkat` permanece. Este contrato no lo vuelve atómico ni autoriza aceptar ese riesgo sin la decisión separada que corresponda bajo TCB-1.

## 7. Caso excluido: systemd socket activation

Este contrato **no cubre** socket activation.

Con `Accept=no`, el system manager crea/posee el listener y pasa un descriptor al servicio. El FD del manager vive fuera del cgroup del servicio; por tanto, detener el servicio y observar `populated 0` no demuestra que el listener haya desaparecido ni que no haya un FD activo.

Para reconsiderar socket activation se necesitaría otro contrato que incluya, como mínimo:

- unidad `.socket` exacta e identidad de invocación;
- estado y jobs de la unidad socket, además de la unidad service;
- prueba de cierre/ausencia del FD retenido por el manager;
- coordinación de stop de ambas unidades y política de reinicio;
- propiedad y colisión de pathname.

Además, el candidato filesystem de socket activation sigue suspendido por el incidente observado en systemd 257.13, donde un archivo regular preexistente en la ruta perdió contenido. Este contrato no levanta esa suspensión ni propone usar `RemoveOnStop=` como workaround.

## 8. Evidencia y auditoría requeridas

Una futura implementación/probe debe producir un registro estructurado con:

- identificador de la operación de mantenimiento;
- unidad e invocación objetivo;
- cgroup path e identidad verificada;
- versión de systemd, kernel y cgroup mode;
- resultado de cada condición Q-01..Q-08;
- lecturas de estado del manager y `cgroup.events` con timestamps monotónicos;
- resultado final `QUIESCENT` o `ABORT_NOT_QUIESCENT`;
- identidad del pathname/objeto solo si se pasa a la fase de inspección;
- identidad del operador y aprobación explícita solo en la fase separada que autorice la retirada.

Los logs no deben incluir payloads IPC, secretos ni datos personales innecesarios. No se debe registrar `QUIESCENT` si falta un campo requerido o si una lectura falló.

## 9. Matriz mínima de validación futura

La validación debe ejecutarse únicamente en una VM desechable y con fixtures; no en `greed`.

| ID | Escenario | Resultado obligatorio |
|---|---|---|
| QP-01 | Servicio con listener en cgroup propio; stop completo | QUIESCENT solo después de `inactive` + `populated 0` |
| QP-02 | Proceso auxiliar hijo dentro del cgroup | No QUIESCENT mientras siga vivo; stop termina todo el grupo |
| QP-03 | Proceso residual deliberadamente persistente | ABORT; no pathname mutation |
| QP-04 | Unidad en transición/restart pendiente | ABORT |
| QP-05 | Cgroup compartido o inesperado | ABORT |
| QP-06 | Cgroup delegado o posibilidad de migración | ABORT |
| QP-07 | Lectura `cgroup.events` parcial, inaccesible o malformada | ABORT |
| QP-08 | Intento de fork después de bind | Rechazado por diseño/política o contenido dentro del cgroup y terminado; nunca escapar |
| QP-09 | Intento de enviar/recibir listener FD mediante `SCM_RIGHTS` | Rechazado; no aparece descriptor externo |
| QP-10 | Intento de exec con FD | El descriptor no sobrevive exec por CLOEXEC |
| QP-11 | Start/restart concurrente durante mantenimiento | Bloqueado por puerta exclusiva |
| QP-12 | Unidad reiniciada/sustituida entre snapshots | ABORT por discrepancia de invocación |
| QP-13 | FD retenido por systemd socket unit | Caso fuera de alcance; no declarar QUIESCENT con este contrato |
| QP-14 | Fallo del supervisor o pérdida de conexión al manager | ABORT; pathname preservado |
| QP-15 | Evidencia completa seguida de cambio de cgroup antes de cierre | Detectar discrepancia o ABORT; no avanzar a pathname mutation |

El probe debe demostrar tanto los caminos positivos como los abortos; no debe ejecutar `unlinkat` real sobre un endpoint no-fixture.

## 10. Criterios de aceptación del contrato

A-THREAT-05 no puede declararse cerrada hasta que:

1. el propietario apruebe este contrato o una revisión corregida;
2. el lifecycle del servicio garantice y demuestre Q-01..Q-08;
3. se implemente un probe aislado que valide QP-01..QP-15 en el entorno objetivo;
4. se demuestre la ausencia de listener FD fuera del cgroup bajo el modelo TCB-1;
5. la puerta de mantenimiento impida reinicio concurrente durante la decisión;
6. se defina la autorización humana real y auditable para la retirada;
7. el procedimiento de pathname mantenga las comprobaciones de A-IPC-04 y documente el alcance procfs, sin reclamar cobertura host-wide;
8. se acepte explícitamente el residual TOCTOU o se establezca otra estrategia que lo elimine.

Un PASS del probe de quiescencia no autoriza listener persistente, despliegue, socket activation, cleanup automático ni cambios del host.

## 11. Decisiones que requieren confirmación del propietario

Este borrador recomienda:

- **R1:** mantener alternativa A (listener creado por el proceso) como único alcance de este contrato;
- **R2:** usar una unidad service dedicada y cgroup exclusivo, sin delegación;
- **R3:** exigir `KillMode=control-group` como candidato de terminación;
- **R4:** exigir `cgroup.events: populated 0` junto con estado terminal del manager;
- **R5:** prohibir fork después de bind, FD inheritance, `SCM_RIGHTS` y cualquier retención externa del listener;
- **R6:** mantener una puerta de mantenimiento que impida start/restart concurrente;
- **R7:** excluir explícitamente socket activation y tratarla mediante contrato separado si se reconsidera.

Estas recomendaciones no se convierten en decisiones aprobadas hasta la aceptación expresa del propietario. Si se rechaza una de ellas, deberá definirse una alternativa con evidencia equivalente; no se rebaja el criterio de quiescencia por conveniencia.

## 12. Límites del trabajo actual

- No existe todavía listener persistente ni unidad de servicio Atlas.
- No se creó ni modificó ninguna unidad systemd, cgroup, usuario, grupo, ruta, permiso o servicio.
- No se modificó el handler IPC ni el contrato `atlas-admin/1`.
- No se implementó herramienta de mantenimiento ni recuperación.
- A-IPC-04 valida el harness SR-01..SR-12, no este contrato ni la propiedad del descriptor de un servicio real.
- El asistente solo preparó documentación en GitHub; no ejecutó pruebas, builds, workflows ni probes.
- No se debe ejecutar ninguna parte de este borrador en el host `greed`.

## 13. Referencias relacionadas

- `docs/contracts/local-authority-admin-ipc-atlas-admin-1.md`
- `docs/design/local-authority-admin-listener-lifecycle.md`
- `docs/design/local-authority-admin-private-listener-stale-recovery.md`
- `docs/design/local-authority-admin-private-listener-threat-model-review.md`
- `docs/design/local-authority-admin-private-listener-path-resolution.md`
- `docs/design/local-authority-admin-private-listener-stale-recovery-probe.md`
