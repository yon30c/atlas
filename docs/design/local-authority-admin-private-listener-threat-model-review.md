# Revisión estática del modelo de amenazas — alternativa A (listener AF_UNIX privado)

**Fecha:** 2026-11-21  
**Rama revisada:** `experiment/a-ipc-01-private-unix-listener-probe`  
**Alcance:** revisión estática de la alternativa A, el lifecycle propuesto, el contrato `atlas-admin/1`, el handler actual y el probe A-IPC-01.  
**Estado:** revisión inicial; no aprobación de implementación persistente ni de producción.

## 1. Conclusión ejecutiva

La alternativa A es técnicamente viable como línea de investigación y el probe A-IPC-01 aporta evidencia experimental útil: el propietario reportó 16/16 escenarios PASS en Debian 13, incluido DAC entre UIDs distintos, rechazo mediante `SO_PEERCRED`, colisiones de bind y carrera de dos binds.

La evidencia no cierra el modelo de amenazas de un servicio persistente. Antes de implementar el listener deben resolverse, como mínimo, la autenticación del servidor frente al cliente, el límite de confianza del UID de servicio, la política inmutable del UID cliente, la recuperación tras caída y los límites del cleanup por pathname. El probe tampoco valida las identidades candidatas de despliegue (`atlas-runtime` y cliente UID 0), hardening del proceso, ni el lifecycle de un daemon.

**Resultado de la revisión:** continuar con diseño y especificación; no empezar aún la implementación persistente. No se identificó una razón que obligue a abandonar A, pero existen decisiones de seguridad bloqueantes que no deben ocultarse tras el PASS del probe.

## 2. Fuentes revisadas en GitHub

- `src/atlas/platform_admin_ipc.py`: handler de una conexión ya aceptada.
- `docs/contracts/local-authority-admin-ipc-atlas-admin-1.md`: contrato normativo 1.1.
- `docs/design/local-authority-admin-listener-lifecycle.md`: lifecycle candidato.
- `docs/design/local-authority-admin-private-unix-listener-probe.md`: diseño y límites de A-IPC-01.
- `tests/integration/private_unix_listener/run_probe.py` y `a09_ssh_client.py`: harness experimental.
- `docs/status-aipc01-validation-2026-11-21.md`: evidencia comunicada por el propietario.

La revisión fue estática y de solo lectura. No se ejecutaron pruebas, compilaciones, workflows ni comandos en el host.

## 3. Actores y límites de confianza

| Actor | Capacidad / relación con A | Tratamiento propuesto |
|---|---|---|
| Cliente administrativo esperado | Candidato actual: UID 0; debe conectarse al endpoint fijo | Aún no validado en el probe; UID final y origen del cliente requieren decisión explícita |
| Proceso local de UID distinto | Sin acceso DAC al directorio/socket privado | A09a aporta evidencia para UID 1001 frente a endpoint 0700/0600 |
| Proceso bajo UID `atlas-runtime` | Puede acceder al directorio que pertenece a ese UID y modificar sus entradas | Debe definirse como parte del mismo dominio de confianza o aislarse; 0700 no separa procesos del mismo UID |
| Root / capabilities suficientes | Puede superar DAC y alterar procesos/archivos del servicio | Fuera del modelo de protección; root pertenece a la TCB |
| Kernel comprometido | Puede falsificar las garantías de credenciales y filesystem | Fuera del modelo de protección |
| Servicio Atlas comprometido | Controla el proceso, el descriptor listener y el UID de servicio | Fuera del límite que este transporte puede resolver por sí solo |

### Decisión de confianza pendiente

El diseño dice que no debe existir ejecución arbitraria bajo `atlas-runtime`, pero todavía no define ni demuestra cómo se garantiza esa exclusividad. Debe decidirse explícitamente:

- **Modelo 1 — UID como dominio de confianza:** cualquier proceso ejecutado como `atlas-runtime` se considera equivalente al servicio y confiable. En ese caso, la amenaza de otro proceso con el mismo UID queda fuera del modelo y debe declararse así.
- **Modelo 2 — procesos del mismo UID no confiables:** el directorio 0700 y el socket 0600 no proporcionan aislamiento entre ellos. Se necesita una frontera adicional de proceso/identidad antes de afirmar que A los separa.

No se debe afirmar simultáneamente que el UID de servicio es compartido y que DAC 0700 protege frente a procesos maliciosos bajo ese mismo UID.

## 4. Hallazgos

### A-THREAT-01 — Autenticación del servidor frente al cliente no especificada

**Severidad: ALTA — bloqueante para integrar un cliente privilegiado.**

El contrato define autenticación del peer en el handler: el servidor obtiene `SO_PEERCRED` y compara el UID del cliente con una allowlist antes de leer el paquete. No define el mecanismo por el cual el cliente comprueba que el pathname al que se conecta termina en el proceso Atlas legítimo.

La propuesta A deja el directorio bajo propiedad de `atlas-runtime`. Un proceso con ese mismo UID puede modificar el directorio y sustituir la entrada del socket. Si el cliente privilegiado conecta solo por pathname y no autentica al servidor, podría hablar con un endpoint falso. Comprobar únicamente que el servidor reporta UID `atlas-runtime` tampoco distingue dos procesos que comparten ese UID.

**Requisito antes de implementar:** especificar autenticación mutua o declarar formalmente que todo proceso con el UID de servicio es parte de la TCB. La solución elegida debe ser comprobable por el cliente y no depender de datos declarados en JSON. No se prescribe todavía un mecanismo concreto.

### A-THREAT-02 — Alcance de confianza del UID de servicio sin cerrar

**Severidad: ALTA — bloqueante para fijar permisos y despliegue.**

El directorio 0700 y el socket 0600 impiden acceso DAC desde otros UIDs no privilegiados, como se observó en A09a. No aíslan procesos con el mismo UID propietario: estos comparten autoridad DAC sobre el directorio y pueden conectar, retirar o sustituir entradas.

El lifecycle menciona una cuenta dedicada sin login y prohíbe ejecución arbitraria bajo ella, pero no existe aún evidencia de su aprovisionamiento, restricciones de ejecución, procesos asociados o exclusividad.

**Requisito antes de implementar:** decidir si el UID completo es confiable y definir cómo se mantiene esa condición. Si no lo es, introducir una frontera adicional y probarla. No reutilizar `greed`, `atlas-sandbox` ni una identidad de despliegue antigua.

### A-THREAT-03 — Allowlist del cliente aún depende del futuro caller

**Severidad: ALTA — bloqueante para conectar el listener.**

`handle_admin_connection()` recibe `allowed_peer_uids` como argumento y valida que sea un conjunto no vacío de UIDs válidos. Esto es correcto para un handler reutilizable, pero no fija la política del servicio. El propietario ya fijó EUID 0 como requisito del frontend y `client_uids={0}` para esta configuración; no es una autorización universal para otros consumidores. El entrypoint real aún no existe/revisado.

**Requisito antes de implementar:** definir una única política de UID del cliente en configuración de confianza del servicio; no permitir que el cliente, variables de entorno no confiables o una solicitud alteren esa política. Verificarla al arrancar y mantenerla inmutable durante la vida del listener. La prueba A09b valida rechazo de UID 1001 en un fixture, no la política real UID 0 ↔ `atlas-runtime`.

### A-THREAT-04 — Cleanup por identidad tiene una ventana TOCTOU conocida

**Severidad: MEDIA — limitación técnica residual aceptada bajo TCB-1, condicionada a exclusividad del directorio y listener de instancia única.**

El lifecycle reconoce que `lstat/stat` seguido de `unlink` no es una operación atómica condicionada por inode. La comparación `st_dev + st_ino + tipo` evita borrar sustitutos en los casos observados, pero no elimina la carrera entre comprobación y unlink. Bajo TCB-1, UIDs externos no deben poder modificar el directorio privado; root y procesos del mismo UID `atlas-runtime` son parte de la TCB. La ventana TOCTOU permanece como limitación técnica y no se declara atómica.

**Condiciones para aceptar el residual:** toda la cadena de directorios debe impedir escritura de UIDs externos; el directorio endpoint debe ser privado, dedicado y propiedad de `atlas-runtime`; el servicio debe ser de instancia única y no compartir el UID con procesos no confiables; cleanup debe usar el descriptor del directorio, revalidar tipo/owner/mode/dev/inode inmediatamente antes de `unlinkat` y omitir la eliminación ante cualquier discrepancia. El diseño no protege frente a root ni procesos del mismo UID, y no afirma que el unlink sea atómico. Si no se puede garantizar cualquiera de estas condiciones, A-THREAT-04 vuelve a ser bloqueante.

### A-THREAT-05 — Recuperación después de caída no tiene procedimiento operativo completo

**Severidad: ALTA — bloqueante para servicio persistente.**

El diseño correctamente prohíbe stale cleanup automático y establece que un pathname preexistente debe hacer fallar el arranque. Esto evita borrar una ruta que podría pertenecer a otra instancia, pero deja pendiente el procedimiento seguro para recuperar un socket residual después de SIGKILL, crash, reinicio del host o fallo entre bind/listen.

**Diseño candidato publicado:** [Recuperación manual de socket IPC residual](local-authority-admin-private-listener-stale-recovery.md) propone detener el servicio, confirmar que no hay procesos que conserven el descriptor, inspeccionar todas las tablas AF_UNIX de los network namespaces visibles mediante `/proc/<pid>/net/unix`, validar el objeto filesystem por descriptor y exigir autorización humana específica antes de `unlinkat`.

**Estado:** A-THREAT-05 sigue abierto hasta probar la enumeración de namespaces y el flujo de recuperación en un sandbox. El arranque normal continúa fallando cerrado; nunca debe hacer stale cleanup ni usar `connect()` como detector de liveness.

### A-THREAT-06 — La resolución segura de la ruta necesita especificación completa

**Severidad: MEDIA/ALTA — requisito de implementación.**

El lifecycle recomienda descriptor de directorio, `dir_fd` y `O_NOFOLLOW`, además de validar propietario/modo. Debe aclararse cómo se resuelven **todos** los componentes de la ruta, no solo el componente final: abrir el directorio final con `O_NOFOLLOW` no demuestra por sí solo que ningún componente padre haya sido sustituido por symlink durante una resolución absoluta ordinaria.

**Diseño candidato publicado:** [Resolución segura de rutas y ownership](local-authority-admin-private-listener-path-resolution.md) define recorrido componente a componente desde `/` mediante `openat`/ `dir_fd`, `O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC`, validación `fstat` de cada directorio y apertura del archivo final relativa al descriptor padre. La investigación añadió un candidato Linux procfs (`/proc/self/fd/<dirfd>/...`) documentado por `sockat` para bind/connect.

**Estado:** el requisito está especificado a nivel de diseño, pero no cerrado para implementación. Bajo TCB-1, el baseline puede usar el pathname absoluto canónico después de recorrer y validar todos los componentes, siempre que ownership/modos impidan que UIDs externos alteren cualquier ancestro. El bind no es dirfd-atómico; la carrera frente a root o al mismo UID queda dentro de la TCB. El candidato procfs de §4.1 es opcional y añade complejidad de observabilidad/recuperación; no se requiere para el baseline. Falta un probe de symlinks, sustitución de ancestros por UID externo, bind collision y connect canónico. No usar `realpath()` como único control ni asumir que `O_NOFOLLOW` en el último componente protege los ancestros.

### A-THREAT-07 — Límites del probe no equivalen a límites del servicio

**Severidad: MEDIA/ALTA — bloqueante para definir capacidad.**

A14 demuestra límites del harness experimental (dos workers y backlog ocho) y recuperación de slots. El propio diseño advierte que no existe límite global de descriptores ni watchdog global para todos los escenarios. El handler controla tamaño de paquete y timeout por conexión, pero no implementa accept loop, cola, backpressure, política de rechazo, cierre global ni límite de recursos del proceso.

**Diseño candidato publicado:** [Presupuesto de recursos y backpressure](local-authority-admin-private-listener-resource-budget.md) propone un perfil inicial de cuatro conexiones/workers, backlog ocho, sin cola de aplicación, request/response 16/64 KiB, read/write 5 s, deadline total 15 s y `RLIMIT_NOFILE=64` provisional. Explica el motivo de no copiar el 2/8 de A14.

**Estado:** A-THREAT-07 sigue abierto hasta que el propietario confirme los valores de capacidad, se revise el scheduler de operaciones/SQLite y un probe aislado valide saturación, deadline, FDs, threads y shutdown. Memoria/CPU y límites del supervisor no están fijados.

### A-THREAT-08 — Lifecycle de shutdown/readiness y descriptor no implementado

**Severidad: MEDIA — bloqueante para servicio persistente.**

El diseño enumera una secuencia candidata de bind, verificación, listen, accept, cierre de conexiones activas y cleanup. No existe todavía una máquina de estados implementada ni evidencia de señales, readiness, instancia única durante todo el lifecycle, descriptor heredado no previsto o shutdown bajo carga.

**Requisito antes de implementar:** definir estados de arranque, listo, drenaje, parada y fallo; orden de cierre; deadline para conexiones activas; comportamiento ante error parcial después de bind; y garantía de no dejar workers/FDs vivos. Mantener el fallo cerrado si no se puede verificar la propiedad del endpoint.

### A-THREAT-09 — Evidencia de A09 no cubre la pareja de identidades de despliegue

**Severidad: MEDIA — brecha de evidencia.**

La ejecución A-IPC-01 reportada se realizó con runner UID 1000 y peer UID 1001. A09a valida DAC frente a un UID distinto y A09b valida rechazo del handler real desde un fixture permisivo. No prueba el cliente candidato UID 0, el proceso de servicio `atlas-runtime`, ni la combinación real de ownership/modos de despliegue.

**Requisito antes de aprobar el modelo de host:** cuando exista un plan de prueba autorizado y aislado, comprobar la matriz exacta de UID/GID y permisos propuesta sin cambiar cuentas ni servicios productivos como parte de este trabajo. El resultado del probe actual no debe presentarse como validación de esa matriz.

## 5. Garantías que sí están respaldadas por el código/evidencia revisados

- El handler valida que la conexión aceptada sea `AF_UNIX/SOCK_SEQPACKET`.
- Obtiene PID/UID/GID mediante `SO_PEERCRED` del kernel y valida el UID antes de recibir el paquete.
- El decoder impone límite de solicitud, UTF-8 estricto, JSON estricto, rechazo de claves duplicadas, profundidad máxima y catálogo cerrado.
- Solo `authority.ping` está implementada; las seis operaciones restantes se rechazan como `OPERATION_DENIED`.
- El handler no crea listener, no cambia credenciales, no abre SQLite y no realiza operaciones administrativas mutantes.
- El propietario reportó A01–A16 = 16 PASS, 0 SKIP, 0 FAIL para el commit experimental y entorno consignados en el registro de validación.
- A09a aportó evidencia DAC para UID distinto; A09b aportó evidencia de rechazo `UNAUTHORIZED_PEER` antes de procesar el paquete, sin respuesta de protocolo.

Estas garantías son acotadas al código y ejecución identificados. No prueban un daemon ni un despliegue.

## 6. Matriz de amenazas y cobertura actual

| Amenaza | Control previsto | Evidencia actual | Estado |
|---|---|---|---|
| UID local distinto conecta al endpoint privado | Directorio 0700/socket 0600 | A09a: EACCES, cero accepts | Validado en fixture/entorno experimental |
| UID distinto alcanza handler por fixture permisivo | SO_PEERCRED + allowlist | A09b: UNAUTHORIZED_PEER, 0 bytes respuesta | Validado para UID 1001 |
| Cliente suplanta UID en JSON | Ignorar identidad declarada; usar SO_PEERCRED | Handler usa credenciales del kernel | Implementado en handler |
| Cliente privilegiado conecta a servidor falso | Autenticación del servidor | No definida | **Bloqueante** |
| Proceso malicioso con UID de servicio | Separación de UID / TCB | No hay aislamiento entre procesos del mismo UID | **Decisión bloqueante** |
| Root/capabilities suficientes | Fuera de la TCB de este control | No se prueba | Fuera de alcance declarado |
| Path preexistente / colisión | Bind sin unlink previo | A02–A05 y A16 | Validado experimentalmente |
| Socket residual tras crash | Fallar cerrado, no stale cleanup | A05 simula stale; recuperación operacional no probada | Parcial |
| Sustitución de pathname durante cleanup | Directorio privado TCB-1 + revalidación y unlinkat relativo | A06/A07 y diseño reconoce TOCTOU | Residual aceptado bajo condiciones TCB-1; requiere probe |
| Saturación / DoS de conexiones | Límites y backpressure | A14 harness 2 workers/backlog 8 | Solo harness |
| Shutdown bajo carga / restart persistente | Máquina de estados y drenaje | No existe listener persistente | Pendiente |
| Hardening / privilegios heredados | UID/GID/capabilities/FD explícitos | No probado para proceso de servicio | Pendiente |

## 7. Decisiones que debe cerrar el diseño antes de codificar

1. ¿Todo proceso con UID `atlas-runtime` se considera confiable, o debemos resistir a otros procesos bajo ese UID?
2. ¿Cómo autentica el cliente privilegiado al servidor, además de comprobar el pathname?
3. ¿Cuál es la identidad exacta del cliente autorizado y dónde se fija la allowlist?
4. ¿Cuál es el procedimiento manual, auditado y separado para recuperar un socket residual?
5. La ventana TOCTOU de cleanup se acepta bajo TCB-1 solo si ownership/modos excluyen UIDs externos, el listener es de instancia única y cleanup revalida la identidad por descriptor; si no, detener el diseño.
6. ¿Qué primitive de resolución de ruta y descriptor se exige para todos los componentes?
7. ¿Qué límites reales de conexiones, FDs, workers, deadlines y shutdown tendrá el servicio?
8. ¿Qué propiedades del proceso `atlas-runtime` deben verificarse (UID/GID reales/efectivos/saved, capabilities, no_new_privs, descriptores, umask, entorno, cwd y restricciones de ejecución)?

## 8. Próxima fase propuesta

La siguiente tarea es redactar un **diseño de frontera de confianza y autenticación mutua** para A, sin código:

- fijar actores dentro/fuera de la TCB;
- resolver la confianza en el UID `atlas-runtime`;
- definir cómo el cliente verifica el servidor;
- fijar la allowlist de cliente y su origen confiable;
- definir el flujo de conexión desde resolución de ruta hasta `SO_PEERCRED`, intercambio de protocolo y cierre;
- documentar fallos, logs y recuperación.

Después se puede completar la especificación de lifecycle y convertir cada requisito en escenarios de prueba local. No ejecutar ni instalar nada en Debian hasta que exista un plan concreto y autorización explícita.

## 9. Límites de esta revisión

- Revisión estática de GitHub únicamente.
- No se modificó código ni contrato normativo.
- No se ejecutaron pruebas, compilaciones, workflows ni comandos locales.
- No se cambió `main`, no se creó PR ni se aprobó transporte de producción.
- No se autorizan cambios de host, usuarios/grupos, permisos, systemd, SSH/PAM/firewall, servicios, privilegios, SQLite ni despliegue.


## Actualización de seguimiento — diseño de frontera de confianza (2026-11-21)

El siguiente artefacto de diseño ya está publicado: [Frontera de confianza y autenticación mutua — alternativa A](local-authority-admin-private-listener-trust-boundary.md). Propone TCB-1, donde todos los procesos bajo atlas-runtime se consideran parte de la TCB, y autenticación mutua de UID mediante SO_PEERCRED: el servidor verifica el UID del cliente antes de recv; el cliente verifica el UID del servidor antes de send.

Esta propuesta no cierra los hallazgos por sí sola. Requiere decisión del propietario sobre confianza intra-UID, confirmación de identidad/UID del cliente, configuración confiable e inmutable y pruebas aisladas en ambos extremos. El mecanismo no autentica un ejecutable específico ni protege frente a root, kernel o procesos que ya formen parte de la TCB.

El siguiente paso ya no es redactar el diseño inicial: es obtener la decisión de confianza e identidad del propietario. No se implementó ni ejecutó código.


## Actualización — EUID 0 y especificación de rutas (2026-11-21)

El propietario confirmó EUID 0 como requisito del frontend administrativo; la allowlist de diseño queda exactamente `{0}`. Esto cierra la decisión de política del propietario, pero no demuestra el EUID del futuro entrypoint, que aún no existe/revisado. La política se valida en ambos extremos: cliente EUID 0 antes de conectar y servidor `SO_PEERCRED.uid == 0` antes de `recv`; el cliente valida el UID de `atlas-runtime` antes de `send`.

A-THREAT-06 cuenta ahora con una especificación de diseño dedicada, pero permanece abierta para implementación hasta probar recorrido completo y resolver la relación entre el descriptor del directorio validado y el pathname usado por `bind()`. A-THREAT-04 queda como residual aceptado bajo TCB-1, condicionado a directorio privado, instancia única y revalidación por descriptor; unlink no es atómico. A-THREAT-05 tiene procedimiento manual candidato publicado, pero sigue bloqueante hasta validar la enumeración de namespaces y el flujo en sandbox.
