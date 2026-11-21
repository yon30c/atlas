# Recuperación manual de socket IPC residual — alternativa A

**Fecha:** 2026-11-21  
**Estado:** procedimiento de diseño candidato, no autorizado para uso operativo. A-IPC-04 validado por el propietario con 12/12 escenarios PASS en `375fb00a3fee230a57f89ffa7897a29309ff1dd2`; la prueba unitaria del lector procfs también fue reportada PASS antes del probe, sin commit exacto confirmado. A-THREAT-05 sigue abierta: la validación es limitada a la vista procfs/PID namespace del harness y no resuelve carreras de enumeración ni TOCTOU. No ejecutar en el host.
**Dependencia:** listener pathname canónico, TCB-1, resolución segura de rutas y lifecycle.  
**Relacionado:** `local-authority-admin-private-listener-path-resolution.md`, `local-authority-admin-listener-lifecycle.md`, `local-authority-admin-private-listener-threat-model-review.md`.

## 1. Objetivo y principio de seguridad

Una caída abrupta puede cerrar el descriptor listener y dejar en filesystem la entrada socket pathname. El siguiente arranque debe fallar cerrado si el nombre ya existe. El servicio **nunca** debe decidir por sí mismo que un socket es stale ni ejecutar `unlink` automático.

La retirada de un socket residual es una operación de mantenimiento separada, privilegiada, explícita y auditable. Si no se puede demostrar con suficiente confianza que ningún proceso conserva el socket activo, se conserva el objeto y se escala la investigación. No se conecta al endpoint para decidir si está activo.

Este procedimiento está diseñado para el baseline de bind con pathname absoluto canónico descrito en `local-authority-admin-private-listener-path-resolution.md`. Si se adopta la alternativa procfs que deja en el kernel una dirección no canónica, este procedimiento debe revisarse antes: el path de `/proc/net/unix` podría no coincidir con el pathname canónico.

## 2. Condiciones previas de arquitectura

Antes de implementar un servicio persistente, deben cumplirse y documentarse:

- El frontend y el servicio comparten el mismo network namespace Linux para que AF_UNIX pueda conectarlos. No introducir `PrivateNetwork=yes` o aislamiento equivalente sin rediseñar el transporte.
- El servicio no pasa el descriptor listener mediante `SCM_RIGHTS`, no lo hereda a procesos auxiliares y no hace fork después de crear el listener. El descriptor debe ser close-on-exec y mantenerse dentro del proceso servidor.
- La cuenta `atlas-runtime` es dedicada y TCB-1 aceptada. Procesos bajo ese UID son confiables; root es autoridad superior confiable.
- La ruta del socket es absoluta, canónica, fija y protegida por una cadena de directorios que impide escrituras de UIDs externos.
- La configuración de identidad/endpoint es root-managed y se carga desde descriptor validado.

Estas condiciones hacen que, en el modelo normal, el descriptor activo pertenezca al proceso del servicio. Si se permite herencia, paso de FD, namespaces de red distintos o procesos adicionales que puedan poseer el socket, el procedimiento de recuperación debe ampliar sus verificaciones.

## 3. Evidencia de actividad del kernel

Linux expone sockets AF_UNIX en `/proc/net/unix`, que representa la tabla del network namespace del proceso que lee el archivo. El registro incluye tipo, estado, inode y pathname. Para `SOCK_SEQPACKET`, el campo Type se representa como `0005`.

La comprobación propuesta es conservadora:

1. Confirmar que el servicio está detenido y que no existe un reinicio pendiente/automático que pueda competir con la recuperación.
2. Enumerar los network namespaces visibles en el host mediante `/proc/<pid>/ns/net`, deduplicando por identidad de namespace. Leer `/proc/<pid>/net/unix` una vez por cada namespace visible; incluir también el namespace del proceso de mantenimiento.
3. Buscar el pathname canónico exacto configurado. Si aparece en cualquier tabla, tratar el socket como activo o posiblemente activo y **abortar sin borrar**, aunque el estado no parezca LISTEN.
4. Si no se puede leer alguna tabla, enumerar todos los namespaces visibles o interpretar el formato sin ambigüedad, abortar. La ausencia de evidencia incompleta no equivale a evidencia de ausencia.
5. Usar `ss -xlp`, `lsof` o `lsfd` solo como corroboración diagnóstica, nunca como única prueba.

La tabla `/proc/net/unix` informa los sockets del namespace, no es un registro histórico del archivo residual. Una entrada filesystem que ya no tiene socket kernel asociado puede permanecer en el directorio después de que el proceso haya muerto. La comparación se hace por pathname canónico exacto y tipo; no se debe asumir que el inode mostrado por `/proc/net/unix` sea el mismo `st_ino` de la entrada filesystem.

Referencias: [procfs(5), sección /proc/net/unix](https://manpages.debian.org/bookworm/manpages/procfs.5.en.html); [proc_pid_net(5)](https://www.man7.org/linux/man-pages/man5/proc_pid_net.5.html).

## 4. Procedimiento de mantenimiento propuesto

No ejecutar este procedimiento en Debian todavía. Los pasos describen una futura operación con aprobación independiente:

1. **Autorizar ventana de mantenimiento.** Registrar operador, host, fecha, motivo y unidad/instancia afectada.
2. **Detener el servicio por separado.** Confirmar que la unidad está inactiva, que no hay proceso servidor/worker residual y que el supervisor no tiene un restart pendiente. No ejecutar limpieza desde el proceso de servicio.
3. **Confirmar exclusividad de identidad.** Verificar que no quedan procesos `atlas-runtime` ni procesos auxiliares que puedan conservar el listener. Si existe alguno, abortar y determinar por qué sigue vivo.
4. **Resolver la ruta de forma segura.** Abrir desde `/` cada componente mediante descriptores, `O_DIRECTORY|O_NOFOLLOW`, validar propietario/modo/tipo con `fstat` y conservar el descriptor del directorio padre.
5. **Inspeccionar la entrada final.** Con operación relativa al descriptor y no-follow, exigir que el objeto sea un socket real, propiedad del UID/GID esperados y con el modo aprobado. Si es symlink, archivo regular, directorio, dispositivo, owner inesperado o modo inesperado, abortar sin cambiarlo.
6. **Verificar todos los network namespaces visibles.** Aplicar §3. Si aparece un registro con el pathname o la comprobación no puede completarse, abortar. No llamar a `connect()` ni enviar datos al endpoint.
7. **Solicitar confirmación humana específica.** La aprobación debe nombrar el pathname y la identidad filesystem observada (`st_dev`, `st_ino`, tipo, UID/GID, modo). No reutilizar una aprobación genérica de mantenimiento.
8. **Revalidar y retirar.** Inmediatamente antes de la operación, volver a consultar la entrada con el mismo descriptor padre; comparar tipo, `st_dev`, `st_ino`, owner y modo con los datos aprobados. Si cambió, abortar. Solo entonces ejecutar `unlinkat` relativo al descriptor.
9. **Verificar resultado.** Confirmar que el nombre está ausente mediante el mismo descriptor. No borrar directorios padres ni artefactos desconocidos. Registrar resultado y cualquier residuo.
10. **Reinicio separado.** Iniciar el servicio solo mediante una acción de mantenimiento aprobada por separado y comprobar que crea un socket nuevo con ownership/modo correctos y que la autenticación mutua funciona.

El paso 8 conserva una ventana TOCTOU porque Linux no ofrece unlink pathname condicionado atómicamente por inode. Bajo TCB-1, la seguridad depende de que UIDs externos no puedan escribir en el directorio y de que no haya procesos `atlas-runtime` activos; root y ese UID son parte de la TCB. Si estas hipótesis no se pueden demostrar, no retirar el objeto.

## 5. Condiciones de aborto obligatorio

Dejar el socket residual intacto si ocurre cualquiera de estos casos:

- el servicio o algún proceso que pueda poseer el descriptor sigue activo;
- existe una entrada coincidente en cualquier tabla `/proc/<pid>/net/unix`;
- no se puede enumerar un network namespace visible o leer su tabla;
- hay procesos `atlas-runtime` inesperados;
- la ruta, directorio padre, propietario, grupo, modo, tipo, dispositivo o inode difieren de lo esperado;
- la entrada no es un socket filesystem;
- el objeto cambia entre inspección y retirada;
- procfs no está montado/accesible o la ruta usada por bind no coincide con el pathname canónico;
- no existe autorización humana específica para retirar exactamente ese objeto.

No usar `rm -f`, globbing, limpieza recursiva, `find -delete`, scripts genéricos de stale cleanup ni `connect()` como detector de liveness.

## 6. Escenarios para un probe futuro

En un sandbox temporal desechable y sin usar rutas Atlas:

- Listener activo aparece en la tabla AF_UNIX y la recuperación aborta.
- Socket cerrado deja pathname filesystem residual y ya no aparece en la tabla; la recuperación simulada solo permite retirar el objeto exacto después de aprobación.
- Listener activo en otro network namespace visible impide la retirada.
- Una tabla de namespace inaccesible produce abort, no falsa clasificación stale.
- Entrada sustituida por symlink/archivo/socket distinto entre inspección y cleanup queda intacta.
- Owner, modo, tipo o pathname inesperado produce abort.
- Revalidación por descriptor padre detecta cambio de `st_dev/st_ino`.
- Descriptor heredado/pasado a otro proceso se detecta o el diseño de servicio prohíbe ese mecanismo.
- La herramienta no conecta ni envía datos durante diagnóstico.
- El registro de auditoría contiene evidencia mínima suficiente y no expone secretos/configuración completa.

El runner A-IPC-04 existe como harness separado y el propietario lo validó en `Atlas-VM-test` con 12/12 PASS. No es herramienta de mantenimiento: solo opera sobre fixtures en su sandbox, y no debe ejecutarse contra sockets reales ni fuera de la VM desechable.

## 7. Estado de A-THREAT-05

El procedimiento de diseño queda especificado como candidato, pero A-THREAT-05 **no está cerrado**. El propietario validó SR-01..SR-12 (12/12 PASS) en `Atlas-VM-test`, commit `375fb00a3fee230a57f89ffa7897a29309ff1dd2`. La prueba unitaria del lector procfs también fue reportada PASS inmediatamente antes del probe, sin commit exacto confirmado. Esta evidencia valida el harness y no un procedimiento de mantenimiento real.

## 8. Límites

- Diseño estático/documentación desde GitHub.
- No se modificó código, contrato normativo, runtime, SQLite ni configuración del host.
- No se ejecutaron pruebas, compilaciones ni workflows.
- No se creó ni eliminó socket, usuario, grupo, directorio, permiso, servicio o unidad.
- El runner A-IPC-04 fue revisado estáticamente en GitHub y ejecutado/validado por el propietario en `Atlas-VM-test`; el asistente no ejecutó pruebas, compilaciones ni workflows.
- No se aprobó listener persistente, systemd, acceso SQLite ni despliegue.


## 9. Revisión posterior a A-IPC-04: límites y requisitos pendientes (2026-11-21)

### Evidencia que sí queda establecida

- El lector acotado de procfs resuelve el defecto reproducido de lectura parcial en los escenarios SR-01/SR-11.
- El harness detectó listeners activos en el namespace local y en un namespace adicional; abortó ante cobertura incompleta y preservó objetos no admisibles o sustituidos.
- El escenario SR-10 demuestra una retirada de fixture ligada a la identidad observada y a un token generado dentro del propio runner.
- La prueba unitaria del lector fue reportada PASS por el propietario antes del probe; su SHA exacto no se confirmó. El probe fue ejecutado sobre `375fb00a3fee230a57f89ffa7897a29309ff1dd2`.

### Lo que A-IPC-04 no demuestra

1. **Cobertura host-wide:** el runner enumera PIDs visibles en el montaje procfs y PID namespace del inspector. Rechaza `hidepid`, resuelve y deduplica los namespaces asociados a esos PIDs y registra el alcance. Esto no prueba que el montaje exponga todos los procesos/network namespaces del host ni descubre necesariamente namespaces retenidos fuera de esa vista.
2. **Snapshot atómico:** compara dos snapshots PID/netns y vuelve a enumerar después de leer las tablas. Esto detecta cambios observados durante el recorrido y permite reintentos acotados, pero no congela la creación de procesos/namespaces. Un proceso puede aparecer después de la comprobación final; por tanto, la ausencia de coincidencia solo describe la instantánea observada.
3. **Ausencia de descriptores delegados:** el probe no demuestra por sí mismo que un descriptor listener nunca fue heredado, duplicado o transferido a un proceso fuera de la vista. El diseño de servicio debe prohibir y verificar fork/herencia/paso de FD (`SCM_RIGHTS`) o incorporar una prueba de propiedad/contención equivalente.
4. **Aprobación humana real:** el token SR-10 es fixture-only, determinista y creado por el runner. No prueba autenticación de operador, consentimiento interactivo ni auditoría de una operación de mantenimiento.
5. **Atomicidad de retirada:** `fstatat`/consulta por `dir_fd` seguida de `unlinkat` conserva una ventana TOCTOU. El descriptor del directorio evita escapes de pathname, pero no convierte la comparación de inode y la eliminación en una operación atómica.

### Requisito de diseño antes de cualquier procedimiento real

Bajo TCB-1, root y todos los procesos `atlas-runtime` pertenecen al dominio confiable; el aislamiento DAC no separa procesos del mismo UID. La ruta de recuperación debe demostrar que el servicio está detenido, que su dominio de ejecución está vacío y que ningún proceso confiable puede conservar un listener FD. Una posible línea a evaluar —no adoptada ni validada— es un servicio dedicado en un cgroup exclusivo, detenido mediante supervisor con política de terminación del grupo (`KillMode=control-group`) y con `cgroup.events` indicando `populated 0`, junto con invariantes explícitas: UID dedicado, sin procesos externos bajo ese UID, sin fork posterior a bind, `CLOEXEC` y sin transferencia de FD. Debe revisarse si esta prueba de lifecycle/propiedad puede ser una base más fuerte y acotada que prometer una enumeración global de todos los namespaces.

La propuesta de cgroup no es todavía una decisión de arquitectura ni una autorización para crear unidades systemd. Requiere un contrato y un probe aislado propios. Solo podría demostrar la ausencia del listener si el FD se crea y permanece exclusivamente dentro del proceso/cgroup del servicio; si se adoptara systemd socket activation, el manager podría conservar el FD fuera del cgroup del servicio y sería necesaria una prueba distinta sobre la unidad `.socket` y su descriptor. Hasta entonces, cualquier incertidumbre sobre procesos, namespace, descriptor o identidad obliga a conservar el pathname y escalar a revisión manual. No usar `connect()` para liveness, no automatizar `unlinkat` y no ejecutar en `greed`.
