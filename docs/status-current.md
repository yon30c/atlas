# Estado vigente de Atlas

> **Corte documental:** 21 de noviembre de 2026. A-IPC-01 reportado por el propietario como 16/16 PASS en Debian 13; registro: `status-aipc01-validation-2026-11-21.md`.
> **Main:** permanece en HEAD `1bd73d149dbd98e7ee2e5fdc36880883b6b03d16`; PR #29 está integrado. La suite reportada para el HEAD de código de PR #29 fue 1,590 tests, `OK (skipped=1)`; no se ha reportado una nueva ejecución sobre el merge HEAD.
> **Rama activa de diseño:** `experiment/a-ipc-01-private-unix-listener-probe`. Se mantiene separada de `main`; no tiene PR propio. PR #30 sigue abierto en Draft y corresponde a la rama de diseño original.
> **Estado IPC:** el handler procesa conexiones ya aceptadas; solo `authority.ping` está implementada. No hay listener persistente, daemon administrativo ni acceso administrativo real a SQLite.
> **Transporte:** alternativa A sigue siendo la línea de evaluación elegida, no un transporte aprobado para producción. B sigue suspendida por la colisión destructiva de systemd; C no está priorizada.
> **Validación A-IPC-01:** commit probado `1d5bdb122a8480c36b445be7dd961b93806de74b`, Debian 13, 16 PASS, 0 SKIP, 0 FAIL. Esta evidencia valida el probe experimental, no el despliegue.
> **Decisiones del propietario:** TCB-1 aceptada (todos los procesos `atlas-runtime` pertenecen a la TCB); frontend administrativo requerido con EUID 0; política de diseño del servicio `client_uids={0}`.
> **Diseños publicados en esta rama:** configuración confiable de identidad; autenticación mutua por `SO_PEERCRED`; resolución segura de rutas; recuperación manual de socket stale; presupuesto de recursos/backpressure aprobado para probes; plan de probe de autenticación mutua y capacidad. Ver hallazgos y estado debajo.
> **Límites:** no se implementó código nuevo de listener/cliente; no se ejecutaron pruebas, compilaciones ni workflows desde GitHub; no hubo cambios en Debian/host, `main`, cuentas, permisos, servicios o SQLite. No se autorizó listener persistente ni despliegue.

## Autoridad administrativa local e IPC — estado al 2026-11-21

- PR #28 integró el alineamiento del contrato administrativo y `authority.ping` en `main`.
- PR #29 fue integrado mediante `c4e5655c37f4d7bd21d431d1c855b8f0cb2c0d0b`; la suite comunicada para su HEAD de código `4e84eab1fd03ddd9057525ee18a3c02a1d804cd6` fue 1,590 tests, `OK (skipped=1)`. No atribuir esa ejecución al merge HEAD.
- El handler recibe conexiones ya aceptadas; no crea ni gestiona listener persistente. Solo `authority.ping` es funcional; las otras seis operaciones del catálogo no están habilitadas.
- **Dirección elegida:** alternativa A, listener AF_UNIX/SOCK_SEQPACKET propio en directorio filesystem privado. Es línea de evaluación, no aprobación productiva.
- **PR #30:** abierto en Draft sobre `design/isolated-private-unix-listener-probe`; no es la rama experimental actual. No hay PR propio para la rama `experiment/a-ipc-01-private-unix-listener-probe`.
- **A-IPC-01:** el propietario reportó A01–A16 = 16 PASS, 0 SKIP, 0 FAIL en el commit indicado en el registro. A09a validó DAC con UID distinto; A09b validó rechazo real del handler mediante SO_PEERCRED. No valida UID 0 ↔ `atlas-runtime` ni despliegue.
- **A-IPC-02 — validación parcial del propietario:** en `Atlas-VM-test`, Debian 13, commit probado `fbc8c68e75c7d5d32768442666cf861f7880eb28`, MA-01/02/04/05 y CP-01/04 = PASS; global INCOMPLETE, 1.177 s, cleanup de ambos sandboxes `/run` completado. Workers máximos observados: 4; activos tras recuperación: 0. Backlog 8 configurado, no saturado. Registro: README del probe y diseño A-IPC-02.
- **TCB-1:** aceptada. Procesos bajo el UID dedicado `atlas-runtime` son parte de la TCB; no se exige aislamiento intra-UID. Su exclusividad operativa aún debe definirse y verificarse.
- **Identidad cliente:** EUID 0 aceptado como requisito del frontend; `client_uids={0}`. El entrypoint IPC real aún no existe/revisado. El harness A-IPC-02 ha validado en el commit indicado la autenticación mutua del fixture root↔UID de servicio; MA-03 (rechazo pre-connect de EUID no root) está implementado en `7a0d4f1`, pendiente de ejecución.
- **Configuración:** `local-authority-admin-private-listener-identity-config.md` propone fuente root-managed `/etc/atlas/admin-ipc.conf`, root:root 0644 sin secretos, parser estricto y carga inmutable. No se creó el archivo ni se fijaron valores operativos.
- **Rutas:** `local-authority-admin-private-listener-path-resolution.md` especifica recorrido de todos los componentes desde `/`, validación por descriptor y baseline de bind pathname canónico bajo TCB-1, siempre que UIDs externos no puedan escribir en ningún ancestro. La ruta procfs es opcional, no baseline.
- **Cleanup TOCTOU (A-THREAT-04):** residual aceptado bajo TCB-1 si el directorio es privado, la instancia es única y cleanup revalida por descriptor; unlink no es atómico.
- **Socket stale (A-THREAT-05):** procedimiento manual candidato publicado; sigue pendiente validarlo en sandbox. Startup nunca hace stale cleanup ni conecta para probar liveness.
- **Resolución de rutas (A-THREAT-06):** especificación de diseño publicada; falta probe de symlinks, sustitución por UID externo, colisiones y connect canónico.
- **Recursos (A-THREAT-07):** el propietario aprobó para probes aislados 4 conexiones/workers, backlog 8, cola de aplicación 0, read/write 5 s, deadline global 15 s y `RLIMIT_NOFILE=64`. CP-01/CP-04 se ejecutaron y pasaron en `fbc8c68` (máximo 4 workers, recuperación a 0); backlog exacto, adversarios de timeout y contabilidad completa de FDs siguen pendientes. No es configuración de producción. Plan: `design/local-authority-admin-private-listener-mutual-auth-capacity-probe.md`.
- **Lifecycle (A-THREAT-08):** máquina de estados, readiness, shutdown/drenaje y cierre de FDs aún no diseñados/validados.
- **Evidencia de despliegue (A-THREAT-09):** A09 usó runner UID 1000 y peer UID 1001; no probó cliente root, servicio `atlas-runtime` ni permisos/ownership finales.
- **Siguiente paso:** validar MA-03 del commit `7a0d4f1` exclusivamente en `Atlas-VM-test`; después ampliar configuración/snapshot, transporte/desconexión, backlog, límites, deadlines, recuperación de workers y FD accounting. Path-walk, colisiones y stale recovery siguen siendo líneas separadas. Nunca ejecutar en `greed` de producción ni crear cuentas/grupos.
- No se ejecutaron pruebas, compilaciones ni workflows desde GitHub. La validación A-IPC-02 indicada fue ejecutada por el propietario; el commit posterior `7a0d4f1` solo recibió revisión estática. `main` y Debian/host no fueron modificados; no se creó PR.

**Límites de autorización:** el PASS experimental no selecciona por sí solo un transporte productivo ni autoriza listener persistente, daemon, unidades systemd de producción, cambios del host, usuarios/grupos, permisos/privilegios, acceso SQLite, provisioning o despliegue. No habilita operaciones administrativas distintas del ping no mutante usado como fixture.

## Posicionamiento

Atlas es software funcional en desarrollo incremental. Dispone de una experiencia conversacional local con Ollama, persistencia SQLite de conversaciones, administración, exportación y backup cifrado. En paralelo, el repositorio contiene una base creciente de Identity, Authentication, CAM, Project/Environment, Workspace y delegación AGENT.

Atlas todavía no es la plataforma autónoma completa de la visión. La presencia de servicios, repositorios y pruebas no significa que las capacidades estén conectadas a la consola ni que exista un runtime protegido de extremo a extremo.

## Capacidades implementadas en la rama revisada

- Consola conversacional local mediante `python -m atlas`, integración con Ollama, streaming y modo offline informativo.
- Persistencia SQLite de conversaciones, recuperación de conversación activa, administración, exportación JSON y backup cifrado con verificación/restauración.
- Interpretación y planificación funcional F1 mediante contratos y servicios aislados; no está conectada al flujo de consola.
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


## A-IPC-01 — implementación experimental del listener Unix privado (2026-11-20)

**Estado:** implementación opt-in preparada en una rama separada; pendiente de revisión/ejecución local por el propietario. No validada y no aprobada como transporte de producción.

- **Diseño aprobado:** [local-authority-admin-private-unix-listener-probe.md](design/local-authority-admin-private-unix-listener-probe.md).
- **Rama de implementación:** `experiment/a-ipc-01-private-unix-listener-probe`, creada desde el HEAD documental `d7a14302061e1cfc52df5097a42d65bd4ba482bb` de `design/isolated-private-unix-listener-probe`.
- **Archivos:** `tests/integration/private_unix_listener/run_probe.py` y `tests/integration/private_unix_listener/README.md`.
- **Cobertura:** A01–A08 y A10–A16; sandbox temporal privado; directorio `0700`; socket `0600`; colisiones con archivo, symlink, listener activo y socket stale; sustitución controlada durante cleanup; ping `atlas-admin/1`; SO_PEERCRED; desconexión; truncamiento; ancillary; timeout; harness de concurrencia acotada; carrera de dos binds.
- **A09 multi-UID:** SKIP deliberado. El ejecutor no cambia UID/GID, no usa sudo y no crea identidades. Por tanto, sin fallos en otros escenarios el resultado global es INCOMPLETE, nunca PASS. No se sustituye evidencia multi-UID por mocks.
- **A14:** el máximo de dos workers y backlog ocho pertenecen únicamente al harness experimental; no son parámetros de producción.
- **Seguridad:** no se modifica el handler ni el contrato; no listener persistente, daemon, systemd, SQLite, operaciones administrativas, cambios del host ni despliegue. Cleanup compara dispositivo/inode/tipo y conserva el límite TOCTOU documentado.
- **Comando para el propietario, desde la raíz del checkout y sin sudo:**

  ```bash
  PYTHONPATH=src python tests/integration/private_unix_listener/run_probe.py
  ```

**Validación:** no se ejecutaron pruebas, compilaciones ni workflows desde GitHub. No hay resultado local comunicado para esta implementación. El propietario debe revisar el commit exacto y ejecutar el comando en Debian; conservar el JSON completo, incluyendo INCOMPLETE/SKIP y cleanup.

**Estado de Git:** `main` no fue modificado y no se abrió PR. La rama de implementación contiene únicamente el probe y las actualizaciones documentales de este incremento; la comparación exacta y HEAD deben consultarse en GitHub antes de continuar.

**Siguiente paso:** el propietario revisa el HEAD exacto y ejecuta el comando opt-in en Debian; después comparte el JSON completo para analizar PASS/FAIL/SKIP/INCOMPLETE. A no queda seleccionado como transporte definitivo.

**Límites vigentes:** la implementación del probe no autoriza listener persistente, daemon, systemd, unidades de producción, cambios del host, usuarios, grupos, permisos, privilegios, acceso SQLite, provisioning, operaciones administrativas ni despliegue. La colisión destructiva de systemd no debe repetirse.



## Revisión estática A-IPC-01 — 2026-11-20

La rama `experiment/a-ipc-01-private-unix-listener-probe` fue revisada directamente en GitHub contra el diseño A-IPC-01, el README y el handler existente `atlas-admin/1`. Se detectó que A14 podía depender de que los workers no vencieran su timeout antes de completar la aceptación de clientes; además, el harness descartaba cualquier excepción de worker. Se corrigió el harness para mantener los workers admitidos detrás de una compuerta exclusiva del test hasta observar la saturación, exigir que ambos slots estén ocupados, y registrar como fallo las excepciones distintas de timeout/desconexión esperados.

- Commit que corrigió el runner: `909d658e5ba177941f46b87a50c891869e5ca6d7`; los commits posteriores de este ciclo actualizan documentación.
- La rama está basada en `design/isolated-private-unix-listener-probe` y permanece por delante, sin commits por detrás; consultar la comparación viva al reanudar.
- No se modificó el handler, el contrato, SQLite, runtime, servicios ni configuración del host.
- No se ejecutaron pruebas, compilaciones ni workflows desde GitHub. La corrección está pendiente de validación por el propietario en Debian.
- A09 continúa SKIP deliberado; sin otra identidad preexistente, el resultado global esperado sigue siendo INCOMPLETE aunque los demás escenarios pasen.

La revisión no aprueba listener persistente, selección de transporte de producción, systemd, cambios de host, acceso SQLite ni operaciones administrativas. Próximo paso: actualizar Debian a este HEAD, inspeccionar el diff local y solo entonces ejecutar el probe opt-in sin sudo.


## Resultado de ejecución local A-IPC-01 — 2026-11-20

El propietario ejecutó el probe experimental en Debian 13, sin sudo, desde el checkout sincronizado en `experiment/a-ipc-01-private-unix-listener-probe`, commit `314e7395fbc972f8b9ab4a10dd800e85c11c7b59`.

**Entorno y clasificación**
- Kernel: `6.12.117+deb13-amd64`; Python: `3.13.5`; UID efectivo: `1000`.
- Duración: `0.876 s`.
- Resultado global: **INCOMPLETE**.
- Escenarios: **15 PASS**, **A09 SKIP**, **0 FAIL**.
- Cleanup: `empty sandbox root removed`.

**Evidencia observada**
- A01: directorio modo `0700` y socket modo `0600`.
- A02–A05: las colisiones con archivo regular, symlink, listener activo y socket stale no reemplazaron ni alteraron los objetos preexistentes.
- A06–A07: cleanup preservó el pathname sustituto y eliminó el socket propio cuando su identidad permanecía sin cambios.
- A08/A10: ping permitido y credenciales kernel del peer observadas: PID 3751, UID 1000, GID 1000.
- A11–A13: desconexión, truncamiento/ancillary y timeout controlados.
- A14: `peak_active=2`, `rejected_connections=6`, `handled_connections=8`, `active_after_recovery=0`.
- A15: listener cerrado no aceptó nuevas conexiones.
- A16: dos binds concurrentes produjeron exactamente un ganador; el listener ganador permaneció operativo.

**A09 y significado del resultado**
A09 (rechazo de peer con UID distinto) quedó SKIP deliberadamente. El runner no cambia UID/GID, no usa sudo y no asume una segunda identidad preexistente. Por tanto, no se ha demostrado autorización multi-UID y el resultado correcto es INCOMPLETE, aunque los otros 15 escenarios hayan pasado. No hubo FAIL.

**Alcance de la evidencia**
El resultado respalda los invariantes del listener pathname privado dentro del sandbox temporal y la concurrencia del harness de prueba para el UID ejecutor. No demuestra resistencia frente a root o procesos maliciosos del mismo UID, autorización completa, separación real de privilegios, lifecycle persistente, integración con systemd/SQLite ni idoneidad para producción. Los límites TOCTOU de cleanup siguen vigentes.

**Estado y siguiente paso**
- La rama experimental permanece separada; `main` no se modificó y no hay aprobación de transporte de producción.
- El probe sigue siendo opt-in y no debe ejecutarse con sudo.
- Siguiente trabajo: evaluar de forma estática una forma segura de cubrir A09 mediante una identidad no privilegiada ya existente, sin cambiar credenciales ni configuración del host desde el runner. No crear usuarios ni alterar grupos/sudoers/PAM/systemd como parte de esta prueba.
- No se ejecutaron pruebas, compilaciones ni workflows desde GitHub; esta evidencia procede de la ejecución local comunicada por el propietario.


## Revisión A09 de A-IPC-01 — separación DAC / SO_PEERCRED (2026-11-21)

La revisión del diseño y del handler confirma que el A09 original no podía atribuir un fallo de conexión a la autorización de aplicación cuando el endpoint candidato conserva directorio 0700 y socket 0600. Un cliente de otro UID queda bloqueado por DAC antes de llegar a accept(); por ello no hay evidencia de que el handler haya leído SO_PEERCRED.

Se define una separación documental:

- **A09a — DAC:** probar la denegación de acceso al endpoint candidato con los modos originales 0700/0600. Registrar el bloqueo filesystem; no atribuirlo a SO_PEERCRED.
- **A09b — SO_PEERCRED:** probar el rechazo de aplicación con un fixture efímero distinto, deliberadamente accesible a un UID externo (p. ej. directorio 0711/socket 0666). El handler debe observar las credenciales reales y rechazar el UID no permitido antes de leer la solicitud, sin respuesta de protocolo. Este fixture no representa ni sustituye los permisos del endpoint candidato.
- Ambos requieren una identidad no privilegiada ya existente y cliente externo; no se crean usuarios, no se cambia UID/GID, no se usa sudo ni se modifica el host.
- El runner actual permanece sin cambios y continúa omitiendo A09. La ejecución comunicada (15 PASS, A09 SKIP, 0 FAIL) conserva clasificación **INCOMPLETE**. No existe aún validación multi-UID de DAC ni de autorización SO_PEERCRED.

**Cambio realizado:** diseño, README y documentación de contexto/estado. **No se modificaron** handler, runner, contrato, runtime, SQLite, systemd ni host. No se ejecutaron pruebas, compilaciones ni workflows desde GitHub. `main` permanece intacta; no hay PR ni aprobación de transporte de producción.


### A09 fixture topology correction

A09b's temporary fixture must not be nested under the private probe root (0700), since DAC on that parent would still block the external UID. It must be a separate sibling directory directly under a verified shared sticky temporary parent (e.g. /tmp), with fixture directory 0711 and test socket 0666. The candidate endpoint remains 0700/0600. A09a/A09b also require a second already-authenticated ordinary-user session with a different pre-existing UID; the runner must not switch credentials or invoke privilege tools. This is a design correction only; neither subscenario is implemented or validated.


## A09 — identidad temporal multi-UID provisionada (2026-11-20)

El propietario autorizó la creación de la identidad temporal dedicada atlas-a09-test y confirmó su ejecución y verificación en Debian. La fase de cuenta/grupo/HOME queda completada; esto no autoriza clave SSH, login, ejecución A09 ni cambios adicionales del host.

**Evidencia comunicada por el propietario**
- Cuenta: atlas-a09-test:x:1001:984::/var/lib/atlas-a09-test:/bin/bash; UID 1001, GID primario 984, shell /bin/bash.
- Grupo dedicado: atlas-a09-test:x:984:; id muestra solo el grupo primario dedicado, sin grupos suplementarios adicionales.
- passwd -S informa estado L (contraseña bloqueada).
- HOME /var/lib/atlas-a09-test: directory, owner/group atlas-a09-test, permisos 0700.
- El UID es automático y distinto del runner (UID 1000). Preflight posterior comunicado por el propietario: `ps -u atlas-a09-test` sin procesos; `loginctl show-user` indica que UID 1001 no está conectado ni tiene linger; `user@1001.service` `inactive`; no existe archivo `/var/lib/systemd/linger/atlas-a09-test`; `sudo -l -U atlas-a09-test` confirma que no puede usar sudo. Esta observación no excluye por sí sola unidades de sistema ajenas que pudieran referenciar la cuenta.

**Preflight SSH comunicado**
- sshd -T: pubkeyauthentication yes, passwordauthentication yes, kbdinteractiveauthentication no, usepam yes, strictmodes yes, permituserenvironment no, pero x11forwarding yes, allowtcpforwarding yes, allowagentforwarding yes, permitopen any y permitlisten any.
- SSH escucha en 0.0.0.0:22 y [::]:22. El ruleset nftables reportado tiene políticas INPUT ACCEPT para IPv4 e IPv6; no se ha demostrado aislamiento global de SSH a loopback. No modificar SSH/PAM/firewall en este experimento.
- ssh-keyscan presentó ED25519 SHA256:txiDPT+/ldcIwnN6BPotbeL7QsofAieAeqF3GKMa9xI, coincidente con el fingerprint local previamente obtenido de la host key ED25519. RSA/ECDSA también aparecieron, pero la futura conexión deberá fijar ED25519.
En ese preflight inicial aún no se había generado/instalado clave ni probado login. La fase se completó posteriormente: existe una clave Ed25519 restringida con `from="127.0.0.1",restrict`, y la conexión local devolvió UID 1001. El comando forzado actual es `/usr/bin/id -u`; no se ha cambiado. sshd/PAM/firewall globales siguen sin cambios.

**Estado A09 y siguiente paso**
- A09a/A09b siguen sin implementar ni validar; la ejecución anterior conserva 15 PASS, A09 SKIP, 0 FAIL, global INCOMPLETE.
- La creación de cuenta no cambia ni amplía la evidencia del runner. No ejecutar A09 hasta implementar y revisar coordinación cliente/runner y obtener aprobación separada.
- Siguiente paso posible: diseñar/revisar el procedimiento exacto para generar e instalar la clave Ed25519 restringida y probar un comando fijo por SSH. Requiere autorización explícita separada antes de modificar authorized_keys o iniciar sesión.
- La eliminación futura de la cuenta, grupo y HOME también requiere autorización explícita separada.
- No se ejecutaron pruebas, compilaciones ni workflows desde GitHub. main permanece intacta; no hay PR ni transporte de producción aprobado.


## A09 — autenticación SSH de identidad externa confirmada (2026-11-21)

El propietario confirmó la instalación de una clave Ed25519 efímera y una conexión SSH local estrictamente verificada a `atlas-a09-test@127.0.0.1`. La clave en `authorized_keys` conserva `from="127.0.0.1",restrict` y el comando forzado actual `/usr/bin/id -u`; la conexión devolvió UID `1001`. El archivo de clave privada permanece en runtime privado de `greed`; no está en GitHub. El known_hosts temporal es propiedad de `greed`, modo 0600, y fija la host key ED25519 previamente comparada por fingerprint.

**Qué demuestra:** autenticación por clave pública de la cuenta UID 1001 y ejecución del comando forzado. **Qué no demuestra:** acceso DAC al endpoint candidato, rechazo real por SO_PEERCRED, A09a, A09b ni seguridad de producción.

La coordinación A09 se diseñó en [local-authority-admin-private-unix-listener-probe.md](design/local-authority-admin-private-unix-listener-probe.md), sección 16. El modelo propuesto es un helper remoto fijo, sin órdenes genéricas, ejecutado mediante un subprocess SSH con opciones estrictas; el runner permanece UID 1000 y no cambia credenciales. A09a conserva endpoint 0700/0600 y espera EACCES antes de accept. A09b usa fixture hermano independiente bajo /tmp sticky (0711/0666), envía ping y exige que el handler real observe el UID externo y rechace UNAUTHORIZED_PEER antes de leer el request, sin respuesta.

**Estado de aquella actualización:** el helper/runner aún no estaban implementados. Esa nota histórica queda supersedida por la actualización posterior de esta misma página: el código A09a/A09b ya está implementado en la rama, pero no ejecutado ni validado. El cambio de comando forzado de authorized_keys continúa sin autorización específica. No modificar sshd_config, PAM, firewall, systemd, handler, contrato, runtime, SQLite ni servicios. La evidencia local sigue en 15 PASS + A09 SKIP + 0 FAIL, global INCOMPLETE.


## A09 — helper y runner implementados, host change pendiente (2026-11-21)

La rama experimental ahora contiene una primera implementación de A09a/A09b:

- `tests/integration/private_unix_listener/a09_ssh_client.py`: helper fijo y stdlib-only; entrada JSON limitada, escenarios cerrados A09a/A09b, sin shell arbitraria, sin cambio de credenciales ni acceso al checkout.
- `tests/integration/private_unix_listener/run_probe.py`: SSH local con clave explícita, agente desactivado, autenticación solo por clave, host key ED25519 estricta/fijada, sin PTY/forwarding/proxy, A09a/A09b independientes y cleanup por identidad.
- A09a exige EACCES, cero accepts y endpoint candidato 0700/0600 intacto.
- A09b usa fixture hermano /tmp 0711/0666, comprueba SO_PEERCRED PID/UID/GID, exige que el handler real lance UNAUTHORIZED_PEER y que el cliente reciba cero bytes.
- A09 queda deshabilitado por defecto. El opt-in requiere rutas explícitas de clave/known_hosts y confirmaciones del operador de que el comando forzado fue aprobado/actualizado y que los archivos de inicio del shell fueron revisados.

**No ejecutar todavía:** la clave instalada sigue forzando `/usr/bin/id -u`. Cambiarla a `/usr/bin/python3 -I /tmp/atlas-a09-client.py` modifica seguridad del host y requiere aprobación explícita específica. No se ha modificado `authorized_keys`, sshd_config, PAM, firewall ni shell startup files. El propietario debe inspeccionar estos últimos de forma read-only antes de considerar el cambio.

**Validación:** el código es implementación en rama experimental, no evidencia de ejecución. No se han ejecutado pruebas, compilaciones ni workflows desde GitHub. La última evidencia local comunicada sigue siendo 15 PASS, A09 SKIP, 0 FAIL, global INCOMPLETE; los nuevos escenarios A09a/A09b no están validados. `main` permanece intacta; no hay PR y ningún transporte está aprobado para producción.


### A09 — revisión estática del helper/runner completada (2026-11-21)

Se completó revisión estática directa en GitHub de `a09_ssh_client.py` y `run_probe.py`: helper de acciones cerradas y path-shape restringido; SSH sin configuración/agent/password/PTY/forwarding/proxy; host key ED25519 fijada; stdin/stdout/stderr con límites; A09a y A09b separados; credenciales de kernel comparadas; cleanup condicionado por identidad y preservación de recursos si el hijo no termina.

Esto es revisión de código, no ejecución. No se corrieron pruebas, compilaciones ni workflows. A09a/A09b siguen sin validar. La clave en Debian todavía fuerza `/usr/bin/id -u`; no se modificó `authorized_keys`. Falta inspección read-only del shell startup y aprobación explícita específica del cambio de comando forzado, seguida de autorización independiente para ejecutar A09.


## Actualización de estado A-IPC-01 — ejecución completa 2026-11-21

Esta sección supersede las notas previas de A-IPC-01 en este documento que indicaban A09 SKIP/INCOMPLETE o que el helper/runner no se habían ejecutado. Es una validación de probe experimental, no una selección de transporte productivo.

**Ejecución reportada por el propietario**
- Rama: `experiment/a-ipc-01-private-unix-listener-probe`.
- Commit exacto: `1d5bdb122a8480c36b445be7dd961b93806de74b`.
- Debian 13; kernel `6.12.117+deb13-amd64`; Python `3.13.5`; UID del runner 1000.
- Identidad externa: `atlas-a09-test`, UID 1001/GID 984.
- Duración: 1.72 s; cleanup: `empty sandbox root removed`.
- Resultado global: **PASS — 16 escenarios PASS, 0 SKIP, 0 FAIL**.

**A09a — DAC**
- Cliente externo PID 5405, UID 1001/GID 984.
- Conexión denegada con `EACCES` / errno 13.
- `accepted_connections=0`.
- Endpoint candidato sin relajación: directorio 0700, socket modo 0600, socket propiedad UID 1000.

**A09b — SO_PEERCRED**
- Cliente externo PID 5417, UID 1001/GID 984.
- Fixture separado: directorio 0711, socket 0666; no se aplicaron estos modos al endpoint candidato.
- Handler real rechazó con `UNAUTHORIZED_PEER`.
- Se enviaron 122 bytes de solicitud ping; el cliente observó reset y `response_bytes=0`.

Los escenarios restantes A01–A08 y A10–A16 también fueron PASS. A14 reportó `peak_active=2`, seis conexiones rechazadas, ocho manejadas y cero activas tras recuperación. A16 confirmó exactamente un ganador y listener operativo. El reporte completo está en [el registro de validación A-IPC-01](status-aipc01-validation-2026-11-21.md).

**Estado actualizado**
- A-IPC-01 queda validado como probe experimental en el commit y entorno citados.
- El helper/runner A09a/A09b ya fueron ejecutados y no están pendientes para esta evidencia.
- No se ejecutaron pruebas, compilaciones ni workflows desde GitHub; la evidencia fue comunicada por el propietario tras ejecutar Debian localmente.
- `main` permanece intacta; la rama experimental no se ha integrado y no se crea PR por esta actualización documental.
- Ningún transporte IPC está aprobado para producción. No se autoriza listener persistente, daemon, systemd, despliegue, acceso SQLite, separación de privilegios ni operaciones administrativas mutantes.
- La evidencia no demuestra protección frente a root/capabilities suficientes ni procesos maliciosos del mismo UID. La suspensión del socket activation filesystem por la colisión destructiva previa permanece vigente.
- No asumir que la cuenta temporal `atlas-a09-test`, la clave SSH, el respaldo de `authorized_keys` o los artefactos temporales han sido eliminados. Cualquier limpieza host-side es una operación separada.

El propietario informó que el cambio temporal de `authorized_keys` conservó `from="127.0.0.1",restrict`, clave y modo 0600, y forzó `/usr/bin/python3 -I /tmp/atlas-a09-client.py`. Los archivos de inicio fueron revisados read-only. No se reportaron cambios globales en sshd_config, PAM o firewall.


## Actualización de estado — EUID 0 y resolución segura de rutas (2026-11-21)

**Decisión aceptada:** el frontend administrativo debe conectar con EUID 0. La política de diseño del servicio es `client_uids={0}` y no admite consumidores adicionales sin nueva decisión. El cliente debe comprobar EUID 0 antes de conectar; el servidor comprueba `SO_PEERCRED` antes de `recv`; el cliente comprueba UID de `atlas-runtime` antes de enviar. No existe todavía un entrypoint IPC ejecutable revisado, así que la identidad está aceptada como requisito pero no validada en runtime.

**Diseño publicado:** `docs/design/local-authority-admin-private-listener-path-resolution.md` especifica recorrido de todos los componentes desde `/` con descriptores, `openat`/`dir_fd`, `O_DIRECTORY|O_NOFOLLOW`, validación de cada directorio y lectura de configuración desde descriptor. A-THREAT-06 tiene especificación completa a nivel de diseño: bajo TCB-1, el baseline es bind al pathname absoluto canónico después de validar toda la cadena y demostrar que UIDs externos no pueden escribir en ningún ancestro. El bind no es dirfd-atómico; root y `atlas-runtime` son TCB. El patrón procfs queda opcional, no baseline. Cleanup con `unlinkat` conserva ventana TOCTOU, aceptada bajo las mismas condiciones de exclusividad y listener de instancia única.

**Próximos bloqueos:** (1) probe aislado del recorrido de rutas y bind canónico con colisiones/symlinks; (2) validar el procedimiento de recuperación manual stale (A-THREAT-05); (3) definir límites reales de conexiones/FDs/deadlines (A-THREAT-07); (4) implementar/revisar el entrypoint cliente con EUID 0 y el probe de autenticación mutua. No se modifica código ni contrato. No se ejecutaron pruebas, compilaciones ni workflows; no hubo cambios en Debian/host, `main` ni PR.


### Candidato técnico para resolver bind/pathname

La investigación encontró un patrón Linux procfs usado por `sockat` para bind/connect mediante descriptores. Se conserva como alternativa experimental, no como baseline: `getsockname()` puede devolver la ruta procfs temporal y pueden quedar artefactos D/R ante crash. El baseline TCB-1 es bind al pathname absoluto canónico después de validar toda la cadena y demostrar que UIDs externos no pueden modificarla. No se añadió dependencia ni código.


## A-THREAT-05 — recuperación manual de socket residual (2026-11-21)

Se publicó `docs/design/local-authority-admin-private-listener-stale-recovery.md` con un procedimiento de mantenimiento separado: detener servicio, confirmar que no quedan procesos/FDs del listener, inspeccionar las tablas AF_UNIX de los network namespaces visibles (`/proc/<pid>/net/unix`), validar tipo/owner/mode/inode mediante descriptor de directorio, pedir autorización específica y retirar solo el objeto exacto con `unlinkat`. Ante cualquier duda, se conserva el socket. No se conecta para probar si está vivo.

A-THREAT-05 sigue abierto hasta validar la enumeración de namespaces y la retirada exacta en sandbox. Se presupone pathname canónico absoluto como baseline y cliente/servicio en el mismo network namespace; no heredar ni pasar el FD listener. La alternativa procfs queda experimental porque cambia la ruta reportada y complica diagnóstico stale.


## A-THREAT-07 — presupuesto de recursos aprobado para probes (2026-11-21)

Se publicó `docs/design/local-authority-admin-private-listener-resource-budget.md`. El handler actual limita request 16 KiB, response 64 KiB y JSON depth 16; read/write defaults 5 s, con máximo individual configurable 60 s, pero no deadline global ni accept loop. A14 (2 workers/backlog 8) es solo harness.

Perfil aprobado por el propietario para probes aislados: 4 conexiones/workers fijos, backlog 8, cola de aplicación 0, read/write 5 s, deadline total 15 s y `RLIMIT_NOFILE=64`. No equivale a configuración de producción. Mutaciones serializadas; operaciones largas con ID/status sin retener conexión. Memoria, CPU, TasksMax, shutdown e inventario real de FDs no están fijados.

A-THREAT-07 sigue abierto hasta validar el perfil en un probe aislado. No se modificó código ni host.


## A-IPC-02 — primera iteración de autenticación mutua/capacidad (2026-11-21)

Se implementó \`tests/integration/private_unix_listener/run_mutual_auth_capacity_probe.py\` como runner separado de A-IPC-01. Es un harness experimental de procesos reales, no un listener de Atlas:

- Exige ejecución directa como root dentro de una VM desechable y confirmaciones explícitas; requiere cuatro IDs numéricos de fixture dedicados. No crea cuentas/grupos ni usa sudo/su.
- El cliente root valida \`SO_PEERCRED.uid\` del servidor antes de enviar el ping; un servidor con UID alternativo debe recibir EOF con cero bytes.
- El servidor fixture valida \`SO_PEERCRED.uid == 0\` antes de \`recv\`; el cliente con UID alternativo no recibe respuesta protocolaria.
- El proceso servidor usa UID/GID reales, efectivos y saved del fixture, sin grupos suplementarios; aplica \`RLIMIT_NOFILE=64\`.
- Pool fijo de cuatro workers y semáforo antes de \`accept()\`; el probe mantiene cuatro conexiones ocupadas, verifica que la quinta no sea aceptada como quinto worker y que se acepte después de liberar un slot.
- Backlog configurado 8, read/write 5 s y deadline global 15 s. La saturación exacta, adversarios de timeout, full FD accounting, límites de payload/depth y escenarios restantes todavía no están implementados.

El runner crea fixtures temporales bajo \`/run\`, incluyendo una raíz de traversal root-owned 0711 (no escribible por grupo/otros) para que el peer alternativo pueda alcanzar el socket expuesto. Copia el script y el módulo IPC a una ubicación temporal de solo lectura accesible por los procesos con UID reducido. La limpieza valida identidad de cada socket; ante sustitución o fallo de un proceso, preserva el sandbox y reporta FAIL.

**Estado:** revisión estática en GitHub solamente. No se ejecutó el runner, pruebas, compilaciones ni workflows. El resultado completo esperado en esta iteración es \`INCOMPLETE\` porque quedan escenarios deliberadamente pendientes. El propietario debe revisar y ejecutar únicamente en VM desechable; no usar el servidor Debian de producción.

**Siguiente paso:** inspeccionar el diff local tras actualizar a este commit y decidir cuatro IDs numéricos reservados para la VM; después ejecutar A-IPC-02 y compartir el JSON completo. A continuación se completarán backlog/deadlines/FD accounting y el probe de resolución de rutas/colisiones. No se modifica handler/contrato ni se autoriza listener persistente, systemd, SQLite o despliegue.
