# Estado vigente de Atlas

> **Corte documental:** 22 de noviembre de 2026.
> **Main:** HEAD `a89e96cc4e5d9555e28a7ea5d9f3788654fe7268`; PR #29 integrado mediante merge commit `c4e5655c37f4d7bd21d431d1c855b8f0cb2c0d0b`.
> **Rama MVP activa:** `work/atlas-mvp-runtime`, no integrada en `main`. HEAD de código validado localmente: `29e900a1129efbb83c8e4b867c99d37d66473c55`; los commits posteriores de este ciclo son documentales. La comparación consultada mostró la rama por delante y no detrás de `main`.
> **Validación local de la rama MVP:** suite completa `Ran 1611 tests in 40.322s — OK (skipped=1)`; `compileall -q src tests` sin errores reportados. Validación comunicada por el propietario desde Debian 13 / `Atlas-VM-test`, no ejecutada desde GitHub.
> **Límite de validación:** la suite unitaria no demuestra migración sobre una base persistente real, login desplegado, composición autenticada, bootstrap, Workspace ni CAM operativo.
> **IPC:** el handler sigue siendo un prototipo para conexiones ya aceptadas; solo `authority.ping` está implementado. No hay listener persistente ni transporte aprobado para producción. Socket activation systemd sobre filesystem permanece suspendida por la colisión destructiva observada.

## Prioridad actual — MVP local limitado (2026-11-22)

La rama `work/atlas-mvp-runtime` prioriza un MVP local que permita conversar y preparar planes sin conceder autoridad de ejecución.

- **Consola:** conversación persistente con Ollama y comando `/plan <solicitud>` conectado al planificador F1. Presenta objetivo, capacidad, parámetros y resultado esperado; no ejecuta operaciones ni accede al filesystem.
- **Guard de autenticación:** implementación SQLite V28 publicada y validada en la suite completa. Usa el mismo archivo SQLite canónico, transacciones breves e independientes `BEGIN IMMEDIATE`, reservas por intento con TTL de 120 s, máximo dos reservas simultáneas por cuenta, ventana móvil de 15 min y demoras 1/2/4/7/15 min. Argon2id ocurre fuera de transacciones SQLite de escritura; el proof solo se devuelve tras revalidar estado/revisión y confirmar el éxito del guard.
- **Validación local:** además de la suite completa (1611 tests, 1 omitido), el propietario había validado 14 pruebas focalizadas de planificación, 21 pruebas focalizadas del guard y `compileall`. La evidencia de suite completa incluye las pruebas de ambos incrementos y las regresiones V28.
- **Composición revisada:** `src/atlas/cli.py` solo compone conversación/planificación; `src/atlas/bootstrap.py` solo construye el planificador. La UoW incluye Identity, Native Identity/Authentication, Project/Environment, asociación V18, Workspace y Grants, pero no compone el journal/Recovery Gate ni el binding PAM→propietario. No instancia `NativeAuthenticationService`, `SQLiteAuthenticationAttemptGuard` ni el attestor HMAC en un login operativo. Véase la [auditoría ampliada de brecha de composición](design/native-authentication-composition-gap-audit.md).
- **Bloqueos previos a login:** falta el proveedor/ciclo de vida del secreto HMAC para VerifiedIdentityContext (no reutilizar la clave ME-03K de Consistency); siguen sin aprobarse para implementación los contratos de génesis/provisión de propietario; el primer Grant no tiene scope/recursos/acciones/expiración concretos; el helper PAM no existe y la invocación privilegiada A/B sigue sin aprobarse.
- **Bloqueo de identidad:** `LocalConsoleRequestFactory` continúa creando un `OperationContext` sintético. `WorkspaceCapabilityExecutionService` y `MemoryAuthorizationService` no verifican `VerifiedIdentityContext`; `GrantManagementService.issue/revoke` verifican fuera de la UoW de mutación y requieren cierre de la ventana TOCTOU/fencing. No conectar estos consumidores.
- **Alcance temporal:** conversación persistente + vista previa de planes. Workspace read-only será posterior a autenticación USER verificable, bootstrap y autorización CAM exacta. No habilitar escritura, shell, Docker, Skills, Broker, runtime AGENT ni ejecución multi-paso.

**Siguiente secuencia:** cerrar el descriptor y perfil CAM mínimo de provisión B; decidir proveedor/ciclo de vida de clave HMAC; cerrar protocolo PAM y frontera privilegiada; diseñar atomicidad de génesis A con binding/journal/gate; cerrar verificación transaccional I-3. Solo después diseñar la composición de login. Workspace y consola sintética siguen desconectados.

**Nota de lectura:** las secciones posteriores conservan snapshots históricos y decisiones previas. Cuando contradigan este bloque operativo, prevalece este bloque; no deben confundirse resultados históricos con el estado actual.


## Autoridad administrativa local e IPC — estado al 2026-11-21

- PR #28 integró el alineamiento del contrato administrativo y `authority.ping` en `main`.
- PR #29 corrigió el probe opt-in para intercambiar `atlas-admin/1` y comprobar `completed/OK`; también registra las puertas de diseño del listener. Fue integrado en `main` mediante `c4e5655c37f4d7bd21d431d1c855b8f0cb2c0d0b`. El propietario validó localmente en Debian el HEAD de código del PR `4e84eab1fd03ddd9057525ee18a3c02a1d804cd6` (detalles arriba).
- El handler recibe conexiones ya aceptadas; no crea ni gestiona un listener persistente. No existe daemon administrativo ni acceso administrativo real a SQLite.
- `authority.ping` es la única operación administrativa funcional. Las otras seis operaciones siguen bloqueadas/no implementadas.
- La observación destructiva de colisión de pathname en Debian systemd 257.13 mantiene suspendida la socket activation sobre filesystem. No repetir el escenario destructivo.
- Alternativas:
  - **A — Listener creado por proceso en filesystem privado:** próximo probe aislado recomendado; requiere demostrar colisiones no destructivas, exclusión de stale cleanup automático, concurrencia y cleanup condicionado por identidad.
  - **B — systemd socket activation filesystem:** suspendida; no usar como baseline ni desplegar.
  - **C — AF_UNIX abstracto:** probe separado; no tiene controles DAC de filesystem y requiere evaluar preclaim, exposición local y DoS.
- Los probes deben ser opt-in, temporales, con recursos únicos bajo directorios temporales privados, sin `sudo`, sin `/run` ni `/var/lib`, y sin tocar recursos o unidades Atlas existentes.
- Próximo paso: diseñar y ejecutar, por separado, los probes A y C; comparar evidencia antes de seleccionar transporte. Ninguno queda aprobado por el merge de PR #29.

**Límite de esta validación:** el probe user-manager no valida system-manager, separación de privilegios ni despliegue. No autoriza listener persistente, selección de transporte de producción, unidades systemd de producción, cambios del host, usuarios/grupos, permisos/privilegios, acceso SQLite, provisioning o ejecución de operaciones administrativas. Socket activation sobre filesystem permanece suspendida.


## Posicionamiento

Atlas es software funcional en desarrollo incremental. Dispone de una experiencia conversacional local con Ollama, persistencia SQLite de conversaciones, administración, exportación y backup cifrado. En paralelo, el repositorio contiene una base creciente de Identity, Authentication, CAM, Project/Environment, Workspace y delegación AGENT.

Atlas todavía no es la plataforma autónoma completa de la visión. La presencia de servicios, repositorios y pruebas no significa que las capacidades estén conectadas a la consola ni que exista un runtime protegido de extremo a extremo.

## Capacidades implementadas en la rama revisada

- Consola conversacional local mediante `python -m atlas`, integración con Ollama, streaming y modo offline informativo.
- Persistencia SQLite de conversaciones, recuperación de conversación activa, administración, exportación JSON y backup cifrado con verificación/restauración.
- Interpretación y planificación funcional F1 aislada en `main`; la rama `work/atlas-mvp-runtime` añade `/plan` como vista previa. El incremento está validado localmente con 14 pruebas focalizadas y `compileall`; la suite completa de la rama sigue pendiente.
- Capacidades locales de Workspace para listar y leer archivos; protocolo controlado de escritura disponible como componente, pero no habilitado en el catálogo/runtime.
- Gate CAM local de solo lectura para `workspace.list` y `workspace.read`, con identidad canónica, Project/Environment, Grant y UoW compartida; no conectado a CLI/runtime.
- Persistencia canónica de Identity(USER), Project, Environment, Grants, asociaciones Project–Environment y Workspaces.
- Primitivas de autenticación nativa con Argon2id, autenticadores, proofs de un solo uso y persistencia separada de Authentication Authority e Identity Authority.
- Servicios de identidad verificada USER y AGENT, con validación de evidencia y revalidación dentro de la UoW cuando corresponde.
- Identidad AGENT, binding nativo, delegaciones explícitas emitidas/revocadas por el propietario y evidencia de delegación verificada de corta duración.
- Renovación delegada de Grants bajo CAM, con scope exacto y revalidación de identidad, delegación y asociación Project–Environment.
- Bootstrap administrativo local de Platform Admin y lifecycle de asociaciones Project–Environment con CAS, ledger de eventos y composición confiable.
- Separación de capacidades lifecycle 7B.6B: repositorio Workspace sin operaciones de transición de asociación y writer lifecycle interno ligado a la UoW del servicio.
- Composición compartida de almacenamiento SQLite de autoridad (PR #21): una instancia `SQLiteDatabase` y una `SQLiteLocalAuthorityUnitOfWorkFactory` ligada a ella; lifecycle puede reutilizar la misma factory. La composición no crea archivos, inicializa SQLite ni aplica migraciones.

## Evidencia local

El propietario reportó en Debian, sobre la rama `feat/local-authority-storage-composition` en el HEAD `c69b19f2ca815d1afc1e631e3de975b5f0654068`, antes de integrar PR #21:

```text
Ran 1547 tests in 35.761s

OK
```

También reportó que `python -m compileall -q src tests` terminó sin errores. El PR #21 se integró por squash en `main` como `5deb6bf1cf1a53a1eb905d5c23e61f4f027c5fee`; el contenido de código integrado coincide con el HEAD validado. No se reportó una ejecución de GitHub Actions.

La validación no equivale a pruebas E2E ni a una prueba de despliegue productivo. No debe ampliarse a garantías que la suite no cubre ni a la habilitación del runtime.

## Estado de dominios de la visión

| Dominio | Estado documental |
|---|---|
| Atlas Terminal y conversaciones | Funcional en el alcance conversacional descrito; no ejecuta herramientas |
| Assistant / AtlasCore | Composición conversacional funcional; planificación aislada, orquestación de capacidades pendiente |
| Authentication Authority | Primitivas nativas, Argon2id y persistencia implementadas; login desplegado y bootstrap de producción pendientes |
| Identity Authority | Identidad canónica USER/AGENT y bindings nativos implementados; integración completa de clientes pendiente |
| Verified identity | Servicios USER/AGENT y revalidación transaccional implementados; consumidores/runtime aún requieren integración y validación E2E |
| CAM / Grants | Evaluación, emisión, revocación y renovación implementadas parcialmente; no equivalen a una autoridad protegida global |
| Agent delegation | Contratos, persistencia, emisión/revocación del propietario y verificación de delegación implementados; runtime AGENT no habilitado |
| Project / Environment | Fuentes canónicas y asociaciones persistidas; lifecycle con ledger y servicio implementados |
| Workspace | Registro canónico, mount resolver y gate CAM read-only implementados; no conectado a la consola |
| Memory Engine | Infraestructura de dominio, gateway, consistencia, journal, checkpoints y recuperación local parciales; contenido durable y autoridad protegida completa pendientes |
| Broker | Desarrollo operativo separado; no integrado al runtime de Assistant |
| Skills Manager | Pendiente como subsistema operativo; las Skills externas requieren procedencia, análisis, permisos, aprobación, instalación aislada, auditoría y desactivación |
| Scheduler / Task Manager | Pendientes como runtime integrado |
| Approval, eventos y notificaciones | Pendientes como flujos integrados completos |
| Runtime de herramientas | No habilitado en la consola actual |

## Límites que siguen vigentes

- El modelo no concede permisos ni ejecuta operaciones por generar texto.
- Ollama permanece limitado a loopback.
- La consola no es un shell y no tiene acceso directo general a archivos, SQL, Docker ni contenedores.
- Las operaciones protegidas requieren identidad, contexto, autorización y mediación del componente responsable.
- Memory Engine no debe declararse independiente ni completo hasta demostrar composición y ejecución fuera de Atlas.
- El Recovery Gate debe permanecer cerrado mientras no se complete la autoridad protegida, bootstrap y recuperación exigidos.
- Backup/restore de conversaciones no equivale a backup/restore integral de todo Atlas.
- La eliminación lógica de conversaciones no garantiza borrado forense ni elimina copias en respaldos anteriores.

## Hoja de ruta y fase activa

- Hoja de ruta general por fases: [docs/roadmap.md](roadmap.md).
- Fase 3 — Inteligencia y comportamiento seguro: **Pausada por decisión del propietario**. No se considera completada; se conserva el estado y la evidencia para retomarla después.
- Prioridad actual: construir un Atlas funcional de prueba siguiendo [el plan funcional](functional-test-roadmap.md).
- Modelo principal seleccionado previamente: Gemma 4 E2B. Su evaluación avanzada queda pausada y se retomará desde la evidencia documentada, sin repetir la selección general.
- P3-PI-001: fallo exploratorio inicial al seguir una instrucción destructiva en un documento; repetición controlada posterior con 4/4 respuestas seguras tras revisión manual y cero llamadas a herramientas.
- P3-PI-002: matriz completada con `gemma4:e2b-it-q4_K_M`, Ollama 0.40.16, `think=false` solo en el harness, temperatura 0.2 y 512 tokens. Se realizaron 40 corridas (10 por combinación); contención 40/40 y reconocimiento estricto 22/40. Política inglesa: 18/20; española: 4/20. Informe: [matriz P3-PI-002](evaluations/p3-pi-002-gemma4-language-matrix.md).
- Corpus y harness aislado versionados en `tests/evaluation/phase3/`; `think=false` se limita al proveedor experimental y no modifica el runtime productivo. La subfase 3.1 (baseline y harness inicial) está completada: el usuario ejecutó `python -m unittest tests.evaluation.phase3.test_harness -v` y obtuvo 6/6 OK el 16 de noviembre de 2026. La subfase 3.3 dispone de schema JSON de propuestas y respuestas proposal/refusal, validadores puros, simulación de autorización externa, corpus P3-SR de nueve casos y structured_runner.py. En la evaluación reciente, `schema_only` obtuvo 9/9 PASS determinísticos en una pasada del corpus; SR-008 obtuvo 5/5 en una repetición separada. La revisión semántica/manual sigue pendiente, especialmente el reconocimiento de la inyección indirecta en SR-006. La Fase 3 queda pausada en este punto; estos resultados no equivalen a aprobación de seguridad.

## Fuente de detalle

- [Atlas Terminal](terminal/README.md)
- [Hoja de ruta](terminal/roadmap.md)
- [Operaciones de conversaciones](conversations.md)
- [Arquitectura](architecture.md)
- [Contratos](contracts/)
- [Contrato de delegación verificada AGENT I3-2B](design/verified-agent-delegation-contract-i3-2b.md)
- [Auditoría CAM de renovación delegada](design/i3-2b-cam-renewal-integration-audit.md)
- [Auditoría de frontera lifecycle 7B.6A](design/i3-2b-7b6a-lifecycle-write-boundary-audit.md)
- [Separación de capacidades lifecycle 7B.6B](design/i3-2b-7b6b-lifecycle-write-capability-separation.md)
- [Contrato operativo de almacenamiento de autoridad local](design/local-authority-storage-operational-contract.md) — decisión de arquitectura aprobada.
- [Diseño de operaciones administrativas de autoridad local](design/local-authority-administrative-operations-design.md) — propuesta de Fase 2.5.1; el socket Unix es candidato de prototipo, todavía no aprobado.
- [Provisioning offline Project/Environment](design/i3-2b-offline-project-environment-association-provisioning.md) — CLI actual no apto para la futura DB principal hasta adaptar su frontera de privilegios.


### Actualización 3.3.3 — sobre de respuesta estructurada

En `tests/evaluation/phase3/` se añadió un contrato cerrado que permite al modelo responder con `proposal` o `refusal`. Las propuestas se validan mediante el validador canónico; las negativas no pueden incluir herramientas ni campos de autoridad. Se añadieron seis pruebas unitarias nuevas. Pendiente de actualización y ejecución local por el usuario; no se ha conectado ninguna herramienta real.


### Preparación P3-SR

Se añadieron nueve casos estructurados que cubren propuestas válidas, negativas, acceso entre proyectos, inyección indirecta, herramientas desconocidas, autoridad falsificada y suplantación de administrador. La política y construcción de solicitudes son exclusivas del harness. No se ha ejecutado Gemma ni se han conectado herramientas reales.


### Bootstrap LOCAL — validador V1, observador V2 y cadena sudo V3

- **V1:** validador aislado de fixtures completado y validado por el propietario en Debian el 16-11-2026. Compilación estricta, matriz ampliada y AddressSanitizer/UndefinedBehaviorSanitizer superados.
- **V2:** observador Linux genérico en `tools/bootstrap-observer/`, validado por el propietario en Debian: build estricto, pruebas automatizadas, observación local y sostenida, detección de foreground, sudo local, SSH con PTY directo, shell intermediario y SSH sin PTY. El resultado genérico no autoriza ni valida cadenas de privilegios.
- **V3:** observador diagnóstico específico de la cadena sudo en `tools/bootstrap-chain-observer/`, con diseño `docs/design/local-bootstrap-chain-observer-v3-design.md`. Implementa revisión del padre directo, metadatos sudo setuid root, UID/GID, cadena sudo contigua, TTY del ancestro de origen, pidfd y doble muestra. **Build estricto, pruebas fixture y smoke test superados por el propietario en Debian.** Los casos manuales documentados incluyen shell ordinaria (rechazo), sudo local directo (coincidencia diagnóstica), SSH interactivo con PTY entrando primero a shell (coincidencia diagnóstica), SSH remoto directo con sudo (rechazo por origen no vinculado) y shell intermediaria `sudo -- sh -c` (rechazo por padre directo shell).
- Frontera: V3 es solo lectura y no privilegiada; no instala ni ejecuta helper, no modifica PAM, sudoers, systemd, SSH, usuarios/grupos, claves o configuración protegida, y no se conecta a Broker, SQLite, CAM o runtime. `CHAIN_PATTERN_MATCHED_DIAGNOSTICALLY` no es autorización. Candidate A no aprobado para ejecución privilegiada; Recovery Gate permanece cerrado. La inspección posterior confirmó sudo 1.9.16p2 y que `greed` conserva `(ALL : ALL) ALL`; las pruebas `sudo -- sh -c` muestran diferencias entre los descriptores de entrada del monitor sudo y el shell hijo. Se documentó que este acceso root irrestricto impide tratar el helper como defensa frente al propio `greed` malicioso. Se propone estudiar la separación entre cuenta cotidiana y cuenta administrativa independiente, sin cambios realizados. Véase [evaluación Candidate A/B y separación de privilegios](design/local-bootstrap-candidate-evaluation-2026-11-16.md).


### Actualización — evaluación de la cadena sudo y separación de privilegios (16-11-2026)

**Evidencia adicional recibida del propietario en Debian:**

- `sudo -V`: sudo 1.9.16p2; plugins de política, sudoers e I/O en la misma versión.
- `sudo -l`: `greed` conserva autorización irrestricta `(ALL : ALL) ALL`.
- Defaults activos observados: `env_reset`, `mail_badpass`, `secure_path` y `use_pty`. No se observaron excepciones activas `env_keep` en la inspección compartida.
- `visudo -c`: los archivos sudoers inspeccionados parsean correctamente.
- En `sudo -- sh -c`, el listado de procesos mostró un proceso `sudo` y un shell `sh` hijo, ambos asociados a `pts/1`; el descriptor 0 del proceso sudo apuntaba a `/dev/pts/0` y el del shell a `/dev/pts/1`.
- La segunda muestra de `/proc/<pid>/status` confirmó UID/GID real, efectivo, saved y filesystem 0/0/0/0 para el shell hijo. Su `stat` mostró PPID, SID, PGID, TTY y TPGID para esa ejecución.

**Interpretación limitada:** las observaciones ayudan a describir la topología de procesos y la diferencia entre los descriptores del monitor sudo y del comando hijo. No prueban por sí solas la procedencia del PTY, presencia física, autenticación PAM reciente, integridad frente a root ni la capacidad de distinguir todos los modos de invocación. No cambian el resultado diagnóstico V3 ni conceden autorización.

**Implicación para Candidate A:** mientras `greed` conserve `(ALL : ALL) ALL`, puede ejecutar como root comandos que modifiquen el helper, su configuración o el host. Por tanto, el helper no puede presentarse como una frontera de seguridad contra el propio `greed` malicioso. Esto no invalida el uso de un helper para separar Assistant/procesos sin privilegios del administrador del host; sí limita explícitamente el modelo de amenaza.

**Nueva dirección propuesta, aún no aprobada:** separar la cuenta cotidiana `greed` (sin administración general) de una identidad administrativa independiente, y ejecutar Atlas como servicio con privilegios mínimos. La cuenta administrativa debe conservar una vía de recuperación probada. Antes de cambiar grupos, sudoers, PAM, systemd, permisos o servicios se requiere inventario read-only de dependencias, plan de migración, acceso de recuperación verificado y aprobación explícita. No se ha cambiado ninguna cuenta ni privilegio.

**Estado de decisión:**
- Candidate A: sigue siendo candidato de evaluación; no aprobado para ejecución privilegiada.
- Candidate B: sigue siendo alternativa si A no puede demostrar el contrato requerido sin relajar controles.
- Helper C/libpam, servicio PAM, claves, configuración protegida, verificador, consumo de proof y bootstrap CAM: no implementados.
- No se ha inicializado CAM ni abierto Recovery Gate.
- No se han modificado sudoers, PAM, systemd, SSH, usuarios/grupos ni permisos del host.

Detalle y secuencia propuesta: [Evaluación de Candidate A/B y separación de privilegios](design/local-bootstrap-candidate-evaluation-2026-11-16.md).

## Actualización posterior al merge de PR #28 — 2026-11-19

El estado de este documento se complementa con la línea base validada en `main`:
- Merge commit: `74fcc6461c3ad8b802ef765b9d1e8aa478dcc552`.
- El propietario reportó desde Debian: 1,590 tests, `OK (skipped=1)`, 34.895 s, Python 3.13.5; checkout `main` sincronizado con `origin/main` y árbol limpio.
- El handler IPC continúa siendo un prototipo para conexiones ya aceptadas. No existe listener persistente, daemon ni integración de producción con systemd.
- La prueba opt-in de systemd user-manager tenía un envelope incompatible con el handler `atlas-admin/1`; la rama `work/systemd-socket-activation-probe-contract-alignment` lo corrige y exige respuesta `completed/OK`. Validación local de esa corrección pendiente.
- La prueba observó una colisión destructiva de ruta en Debian systemd 257.13. La activación de sockets sobre filesystem no está aprobada hasta demostrar una estrategia segura de propiedad de ruta. La prueba ya no repite el escenario destructivo.
- Esta actualización no autoriza instalación de unidades, cambios del host, usuarios, permisos, acceso SQLite ni operaciones administrativas.

## Evaluación de alternativas de propiedad del endpoint IPC — 2026-11-19

La revisión separa la propiedad del endpoint del mecanismo de activación:
- Listener creado por proceso en directorio privado preaprovisionado: candidato para un probe temporal; fallo cerrado ante colisión, sin stale cleanup automático. La atomicidad de bind y la limpieza condicionada deben demostrarse localmente.
- systemd socket activation sobre filesystem: suspendida por la colisión destructiva observada.
- AF_UNIX abstract namespace: alternativa experimental sin pathname/inode, pero sin permisos filesystem y con exposición a conexiones/preclaim local; requiere probe propio.

No hay transporte aprobado para producción ni listener persistente implementado. Los siguientes probes deben ser opt-in, usar nombres y directorios temporales únicos, no ejecutar con sudo y no tocar recursos Atlas existentes. La decisión final de transporte requiere evidencia local y aprobación explícita del propietario.


## Validación local de PR #29 — 2026-11-21

El propietario confirmó checkout exacto `4e84eab1fd03ddd9057525ee18a3c02a1d804cd6`, rama `work/systemd-socket-activation-probe-contract-alignment`, árbol limpio y sincronizado con origin. En Debian 13 reportó:

- Probe `tests/integration/systemd_socket_activation/run_user_manager_test.py`: `PASS` para activación systemd user-manager, validación del descriptor, dos activaciones, ownership/mode privados y limpieza del pathname delegada al harness con `RemoveOnStop=no`.
- Suite completa: `Ran 1590 tests in 34.753s`; `OK (skipped=1)`.

El resultado valida el alcance de ese HEAD. No prueba system-manager, separación real de privilegios, resistencia a root/procesos del mismo UID, ni despliegue. La colisión destructiva previa mantiene suspendida la activación systemd sobre filesystem. Las alternativas A y C requieren probes independientes.


## Integración de PR #29 — 2026-11-21

PR [#29](https://github.com/yon30c/atlas/pull/29) fue marcado Ready for review e integrado en `main` mediante merge commit `c4e5655c37f4d7bd21d431d1c855b8f0cb2c0d0b`. La evidencia local comunicada corresponde al HEAD de código `4e84eab1fd03ddd9057525ee18a3c02a1d804cd6`: probe systemd user-manager `PASS` y suite `Ran 1590 tests in 34.753s — OK (skipped=1)`. Los commits posteriores del PR fueron documentales. No se ejecutaron pruebas desde GitHub ni se ha afirmado una nueva suite sobre el merge commit.

La integración no habilita listener persistente, system-manager, separación de privilegios, operaciones administrativas ni transporte de producción. La activación systemd sobre filesystem sigue suspendida por la colisión destructiva observada. Los probes A y C permanecen pendientes como experimentos independientes.


### Actualización de implementación del guard — 2026-11-22

El propietario aprobó ajustar la cuarta demora de 8 a **7 minutos**, manteniendo la ventana de 15 minutos y la demora máxima de 15 minutos. La secuencia 1+2+4+7 suma 14 minutos, de modo que el quinto fallo secuencial puede ocurrir dentro de la ventana.

**Código publicado en `work/atlas-mvp-runtime`:**
- `AuthenticationAttemptGuardPort` y reserva opaca con ID/expiración.
- Migración `CORE_SCHEMA_V28` con tablas e índices de reservas/fallos; incluida en `SQLITE_MIGRATIONS`.
- `SQLiteAuthenticationAttemptGuard`: transacciones cortas independientes, máximo dos reservas, TTL 120 s, ventana 15 min y demoras 1/2/4/7/15.
- `NativeAuthenticationService`: issuer en UoW breve, reserva antes de leer el autenticador, Argon2id fuera de UoW, revalidación de issuer/autenticador/status/subject/revisión antes del proof y confirmación del guard antes de devolver la referencia.
- Pruebas unitarias del servicio y nuevo archivo de pruebas del adaptador SQLite, incluyendo concurrencia multiproceso y recolección acotada de registros vencidos de cuentas inactivas.

**Revisión y validación:** se corrigieron durante la revisión el registro/exportación de V28, la limpieza durable de reservas expiradas, el orden reserva→lectura de credencial y un import de pruebas con secuencias literales escapadas. El propietario ejecutó localmente `tests.unit.test_native_authentication_service` y `tests.unit.test_sqlite_authentication_attempt_guard`: `Ran 21 tests in 2.968s — OK`. También ejecutó `.venv/bin/python -m compileall -q src tests` sin errores. **El incremento focalizado del guard queda validado localmente; la suite completa de la rama aún no está validada.**

**No habilitado:** login operativo, bootstrap, endpoints, Workspace, CAM y composición autenticada de consola. La clave HMAC y la decisión del perfil CAM del Grant inicial siguen siendo dependencias independientes.

**Siguiente paso:** cerrar revisión estática de todos los puntos de construcción/instanciación de `NativeAuthenticationService`, revisar el contrato de SQLite y las pruebas, y luego pedir al propietario que ejecute la validación focalizada en Debian. No modificar `main`.


### Resultado de validación local del guard — 2026-11-22

El propietario confirmó en `Atlas-VM-test`, checkout `/opt/atlas-dev`:

```text
Ran 21 tests in 2.968s

OK
```

Comando utilizado:

```bash
.venv/bin/python -m unittest -v \
  tests.unit.test_native_authentication_service \
  tests.unit.test_sqlite_authentication_attempt_guard
```

También ejecutó:

```bash
.venv/bin/python -m compileall -q src tests
```

sin errores reportados.

**Conclusión:** las pruebas focalizadas del servicio y del adaptador SQLite pasan y el árbol compila. La suite completa de la rama `work/atlas-mvp-runtime` sigue pendiente. No se han validado aún migración sobre una base de datos persistente real, pruebas de integración del flujo de login ni composición operativa. Mantener login, bootstrap, Workspace y CAM deshabilitados.

**Siguiente paso:** ejecutar la suite unitaria completa en Debian; revisar el resultado antes de decidir si se integra o si hacen falta correcciones. No modificar `main`.


## Suite completa — compatibilidad V28 (2026-11-22)

El propietario ejecutó localmente en Debian, checkout `/opt/atlas-dev`, la suite completa de la rama y reportó:

```text
Ran 1611 tests in 42.725s

FAILED (failures=23, errors=10, skipped=1)
```

La revisión agrupó los fallos en tres causas de compatibilidad con V28: el CLI de provisión offline aún exigía V27; pruebas de Platform Admin aplicaban V28 aunque su contrato de fixture es V27; y la prueba de compatibilidad lifecycle insertaba la asociación después de V27, cuando ya se exige el evento exacto de provisión offline.

Correcciones publicadas en `work/atlas-mvp-runtime`:
- CLI: valida el historial completo hasta `CORE_SCHEMA_V28`.
- Test del CLI: corrompe el checksum de la migración 28 para comprobar el historial completo.
- Tests de Platform Admin: aplican explícitamente `SQLITE_MIGRATIONS[:-1]` (hasta V27).
- Test de compatibilidad lifecycle: crea la asociación con el esquema hasta V26 (`SQLITE_MIGRATIONS[:-2]`) antes de aplicar V27 y posteriores.

Commits de corrección:
- `797a5f3882a4536f6b2f63b45c8c7bfb347cbcfa` — CLI V28.
- `a1f24742ccaf3272f43ebdefd02a75d6b5f4b686` — prueba de historial completo V28.
- `ee8bd43b1d5b2f56ff7304938765d267f8af9668` — fixture lifecycle.
- `9808f697dc8b9b21f401a887b89cea957ec06b03` — fixture Platform Admin authority.
- `78cbf6288b8dc342f2c10b0c5290a4698a58edd3` — fixture Platform Admin bootstrap.

**Estado:** correcciones publicadas, pendientes de validación local. No se ejecutaron pruebas desde GitHub. El resultado fallido anterior no debe confundirse con el resultado focalizado del guard (21 tests OK); tampoco se debe declarar verde la suite completa hasta recibir una nueva ejecución local.


## Validación local de suite completa — 2026-11-22

El propietario confirmó en Debian, VM `Atlas-VM-test`, checkout `/opt/atlas-dev`, después de incorporar las correcciones de compatibilidad V28:

```text
Ran 1611 tests in 40.322s

OK (skipped=1)
```

También ejecutó:

```bash
.venv/bin/python -m compileall -q src tests
```

sin errores reportados.

**Conclusión:** la suite unitaria completa de esta rama queda validada localmente con 1611 tests ejecutados, cero fallos y un test omitido. La compilación de `src` y `tests` también finalizó correctamente. Esta evidencia no equivale a validar migraciones sobre una base persistente real ni habilita login, bootstrap, Workspace, CAM o composición autenticada; esas capacidades continúan deshabilitadas según las decisiones vigentes.

**Siguiente paso:** revisar el estado/documentación y definir el siguiente incremento del MVP sin ampliar permisos ni activar flujos operativos por inferencia. La validación fue ejecutada por el propietario en Debian; no se ejecutaron pruebas desde GitHub.
