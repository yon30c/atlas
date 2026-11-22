# Estado vigente de Atlas

> **Corte documental:** 22 de noviembre de 2026. A-IPC-01: 16/16 PASS; A-IPC-02: MA-01..MA-10 y CP-01..CP-12 PASS; A-IPC-03/A-THREAT-06: PR-01..PR-12 PASS; A-IPC-04: SR-01..SR-12, **12/12 PASS** en `375fb00a3fee230a57f89ffa7897a29309ff1dd2`. La prueba unitaria `test_private_listener_procfs_read.py` fue reportada PASS inmediatamente antes del probe, sin SHA exacto confirmado. `docs/contracts/local-authority-admin-listener-quiescence-1.md` v1.0-draft: R1–R7 aprobadas como baseline; validación pendiente. Runner QP-01..QP-15 implementado en `tests/integration/private_unix_listener/run_listener_quiescence_probe.py`; revisión estática final en curso, no ejecutado. QP-01/02 contienen predicado QUIESCENT condicionado; QP-11 usa supervisor temporal interno con caída simulada; QP-12 prueba bypass root; QP-13 holder OTHER por SCM_RIGHTS. No hay evidencia experimental todavía. A-THREAT-05 permanece abierta.
> **Main:** permanece en HEAD `1bd73d149dbd98e7ee2e5fdc36880883b6b03d16`; PR #29 está integrado. La suite reportada para el HEAD de código de PR #29 fue 1,590 tests, `OK (skipped=1)`; no se ha reportado una nueva ejecución sobre el merge HEAD.
> **Rama activa de diseño:** `experiment/a-ipc-01-private-unix-listener-probe`. Se mantiene separada de `main`; no tiene PR propio. PR #30 sigue abierto en Draft y corresponde a la rama de diseño original.
> **Estado IPC:** el handler procesa conexiones ya aceptadas; solo `authority.ping` está implementada. No hay listener persistente, daemon administrativo ni acceso administrativo real a SQLite.
> **Transporte:** alternativa A sigue siendo la línea de evaluación elegida, no un transporte aprobado para producción. B sigue suspendida por la colisión destructiva de systemd; C no está priorizada.
> **Validación A-IPC-01:** commit probado `1d5bdb122a8480c36b445be7dd961b93806de74b`, Debian 13, 16 PASS, 0 SKIP, 0 FAIL. Esta evidencia valida el probe experimental, no el despliegue.
> **Decisiones del propietario:** TCB-1 aceptada (todos los procesos `atlas-runtime` pertenecen a la TCB); frontend administrativo requerido con EUID 0; política de diseño del servicio `client_uids={0}`.
> **Diseños publicados en esta rama:** configuración confiable de identidad; autenticación mutua por `SO_PEERCRED`; resolución segura de rutas y A-IPC-03; recuperación manual de socket stale y A-IPC-04/SR-01..SR-12. A-IPC-04 validado 12/12 PASS sobre `375fb00a3fee230a57f89ffa7897a29309ff1dd2`; prueba unitaria del lector procfs reportada PASS por el propietario antes del probe, commit exacto desconocido. El resultado cubre solo procesos/namespaces visibles desde el procfs/PID namespace usado; no es host-wide ni atómico ante creación concurrente. La revalidación seguida de `unlinkat` conserva TOCTOU. A-THREAT-05 sigue abierta.
> **Límites:** no se implementó listener ni cliente IPC productivo; A-IPC-02 y A-IPC-03 son harnesses experimentales separados. No se ejecutaron pruebas, compilaciones ni workflows desde GitHub; la validación citada fue ejecutada por el propietario. No hubo cambios en Debian/host, `main`, cuentas, permisos, servicios o SQLite. No se autorizó listener persistente ni despliegue.

## Autoridad administrativa local e IPC — estado al 2026-11-21

- PR #28 integró el alineamiento del contrato administrativo y `authority.ping` en `main`.
- PR #29 fue integrado mediante `c4e5655c37f4d7bd21d431d1c855b8f0cb2c0d0b`; la suite comunicada para su HEAD de código `4e84eab1fd03ddd9057525ee18a3c02a1d804cd6` fue 1,590 tests, `OK (skipped=1)`. No atribuir esa ejecución al merge HEAD.
- El handler recibe conexiones ya aceptadas; no crea ni gestiona listener persistente. Solo `authority.ping` es funcional; las otras seis operaciones del catálogo no están habilitadas.
- **Dirección elegida:** alternativa A, listener AF_UNIX/SOCK_SEQPACKET propio en directorio filesystem privado. Es línea de evaluación, no aprobación productiva.
- **PR #30:** abierto en Draft sobre `design/isolated-private-unix-listener-probe`; no es la rama experimental actual. No hay PR propio para la rama `experiment/a-ipc-01-private-unix-listener-probe`.
- **A-IPC-01:** el propietario reportó A01–A16 = 16 PASS, 0 SKIP, 0 FAIL en el commit indicado en el registro. A09a validó DAC con UID distinto; A09b validó rechazo real del handler mediante SO_PEERCRED. No valida UID 0 ↔ `atlas-runtime` ni despliegue.
- **A-IPC-02 — evidencia vigente del propietario:** checkout `66b348e1be9a7e614d51c4b3ade9e643c9152106`, Debian 13 / kernel 6.12.117 / Python 3.13.5, EUID 0, fixtures 2005/2005 y 2006/2006. MA-01..MA-10 y CP-01..CP-12: PASS; overall PASS; duración 24.991 s; cleanup confirmado. CP-12: RLIMIT heredado 32/32, exit 3, `startup_error`, límite no elevado y socket no creado. Ver registro detallado al final.
- **TCB-1:** aceptada. Procesos bajo el UID dedicado `atlas-runtime` son parte de la TCB; no se exige aislamiento intra-UID. Su exclusividad operativa aún debe definirse y verificarse.
- **Identidad cliente:** EUID 0 aceptado como requisito del frontend; `client_uids={0}`. El entrypoint IPC real aún no existe/revisado. El harness A-IPC-02 validó MA-01..MA-10 en la última ejecución reportada, incluida la autenticación mutua root↔UID de servicio, rechazo pre-connect de EUID no root, claims UID/GID/PID falsificados, parser fixture estricto, snapshot inmutable, desconexión previa a request y rechazo de transportes no soportados antes de leer.
- **Configuración:** `local-authority-admin-private-listener-identity-config.md` propone fuente root-managed `/etc/atlas/admin-ipc.conf`, root:root 0644 sin secretos, parser estricto y carga inmutable. No se creó el archivo ni se fijaron valores operativos.
- **Rutas:** `local-authority-admin-private-listener-path-resolution.md` especifica recorrido de todos los componentes desde `/`, validación por descriptor y baseline de bind pathname canónico bajo TCB-1, siempre que UIDs externos no puedan escribir en ningún ancestro. La ruta procfs es opcional, no baseline.
- **Cleanup TOCTOU (A-THREAT-04):** residual aceptado bajo TCB-1 si el directorio es privado, la instancia es única y cleanup revalida por descriptor; unlink no es atómico.
- **Socket stale (A-THREAT-05):** A-IPC-04 validado por el propietario: SR-01..SR-12, 12/12 PASS, commit `375fb00a3fee230a57f89ffa7897a29309ff1dd2`. La prueba unitaria procfs fue reportada PASS antes del probe, sin SHA confirmado. El alcance procfs/PID namespace no es host-wide ni atómico; SR-10 es fixture-only y `unlinkat` conserva TOCTOU. `docs/contracts/local-authority-admin-listener-quiescence-1.md` v1.0-draft: R1–R7 aprobadas por el propietario como baseline de diseño. `docs/design/local-authority-admin-listener-quiescence-probe.md` define QP-01..QP-15 y resuelve documentalmente los seis puntos previos a implementación. El runner tiene implementación parcial y no está ejecutado; el contrato no está validado. La puerta no bloquea a root que invoque PID 1 directamente; root sigue dentro del TCB. El cleanup futuro solo podrá retirar el endpoint fixture creado por esa ejecución y validado por inode; no habilita stale recovery. No cubre socket activation systemd; no hay recuperación real ni cleanup automático.
- **Resolución de rutas (A-THREAT-06):** A-IPC-03 validado por el propietario en `b200c292ac0602593c8dbefafb1bd71b79001b06`: PR-01..PR-12 PASS, 0 fallos, 0.062 s y cleanup confirmado en Debian 13/kernel 6.12.117/Python 3.13.5. Cubre path-walk, symlinks, ownership/modos, config vía parent dirfd, descriptor anchoring y DAC en fixtures. No hace bind/connect ni valida colisiones/stale recovery; ruta productiva no fijada.
- **Recursos (A-THREAT-07):** perfil experimental del harness validado en A-IPC-02 completo: 4 workers, `listen(8)`, cola de aplicación 0, read/write 5 s, deadline global 15 s, requests 16 KiB, responses 64 KiB y `RLIMIT_NOFILE=64`. En Linux AF_UNIX probado se observaron 9 conexiones pendientes efectivas: la novena conecta y la décima recibe EAGAIN. CP-01..CP-12 PASS en checkout `66b348e`; no es configuración ni aprobación de producción. Plan: `design/local-authority-admin-private-listener-mutual-auth-capacity-probe.md`.
- **Lifecycle (A-THREAT-08):** máquina de estados, readiness, shutdown/drenaje y cierre de FDs aún no diseñados/validados.
- **Evidencia de despliegue (A-THREAT-09):** A09 usó runner UID 1000 y peer UID 1001; no probó cliente root, servicio `atlas-runtime` ni permisos/ownership finales.
- **Diseño/runner QP:** los seis puntos previos a implementación de la sección 9 están resueltos documentalmente y el runner QP-01..QP-15 ya está implementado en `tests/integration/private_unix_listener/run_listener_quiescence_probe.py`. Su cobertura incluye seccomp FD/fork/io_uring, cgroup observers fijados, D-Bus tipado, unidades transitorias, supervisor test-double QP-11, bypass root QP-12 y holder OTHER QP-13. No se ha ejecutado ni validado. **Siguiente gate:** terminar revisión estática y pasar a las pruebas del propietario solo en `Atlas-VM-test`. El baseline R1–R7 cubre listener creado por el servicio y excluye socket activation. No ejecutar recuperación real ni modificar el host.
- No se ejecutaron pruebas, compilaciones ni workflows desde GitHub. La evidencia A-IPC-04 y la prueba unitaria fue ejecutada/reportada por el propietario; no se atribuye el PASS unitario a un commit específico.

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

**Bloqueos vigentes tras A-IPC-04:** (1) completar A-THREAT-05: demostrar parada/exclusividad del servicio y ausencia de listener FDs heredados o transferidos; (2) definir límites de lifecycle/readiness/shutdown (A-THREAT-08); (3) implementar/revisar el entrypoint cliente EUID 0 y su integración de autenticación mutua. A-IPC-04 ya validó el harness, pero no un procedimiento operativo de recuperación. No se modifica código ni contrato normativo.


### Candidato técnico para resolver bind/pathname

La investigación encontró un patrón Linux procfs usado por `sockat` para bind/connect mediante descriptores. Se conserva como alternativa experimental, no como baseline: `getsockname()` puede devolver la ruta procfs temporal y pueden quedar artefactos D/R ante crash. El baseline TCB-1 es bind al pathname absoluto canónico después de validar toda la cadena y demostrar que UIDs externos no pueden modificarla. No se añadió dependencia ni código.


## A-THREAT-05 — recuperación manual de socket residual (2026-11-21)

Se publicó `docs/design/local-authority-admin-private-listener-stale-recovery.md` con un procedimiento de mantenimiento separado: detener servicio, confirmar que no quedan procesos/FDs del listener, inspeccionar las tablas AF_UNIX de los network namespaces visibles (`/proc/<pid>/net/unix`), validar tipo/owner/mode/inode mediante descriptor de directorio, pedir autorización específica y retirar solo el objeto exacto con `unlinkat`. Ante cualquier duda, se conserva el socket. No se conecta para probar si está vivo.

A-IPC-04 validado por el propietario: SR-01..SR-12, 12/12 PASS, commit `375fb00a3fee230a57f89ffa7897a29309ff1dd2`. La prueba unitaria del lector procfs fue reportada PASS inmediatamente antes del probe; el SHA de esa ejecución no está confirmado. La evidencia valida el harness, no una operación real. A-THREAT-05 sigue abierta por alcance limitado al procfs/PID namespace visible, falta de snapshot atómico, necesidad de probar ausencia de FD heredado/transferido y ventana TOCTOU. El baseline sigue siendo pathname canónico; no heredar ni pasar el FD listener. La alternativa procfs queda experimental.


## A-THREAT-07 — presupuesto de recursos aprobado para probes (2026-11-21)

Se publicó `docs/design/local-authority-admin-private-listener-resource-budget.md`. El handler actual limita request 16 KiB, response 64 KiB y JSON depth 16; read/write defaults 5 s, con máximo individual configurable 60 s, pero no deadline global ni accept loop. A14 (2 workers/backlog 8) es solo harness.

Perfil aprobado por el propietario para probes aislados: 4 conexiones/workers fijos, backlog 8, cola de aplicación 0, read/write 5 s, deadline total 15 s y `RLIMIT_NOFILE=64`. No equivale a configuración de producción. Mutaciones serializadas; operaciones largas con ID/status sin retener conexión. Memoria, CPU, TasksMax, shutdown e inventario real de FDs no están fijados.

A-THREAT-07 sigue abierto hasta validar el perfil en un probe aislado. No se modificó código ni host.


## A-IPC-02 — primera iteración de autenticación mutua/capacidad (2026-11-21)

Se implementó `tests/integration/private_unix_listener/run_mutual_auth_capacity_probe.py` como runner separado de A-IPC-01. Es un harness experimental de procesos reales, no un listener de Atlas:

- Exige ejecución directa como root dentro de una VM desechable y confirmaciones explícitas; requiere cuatro IDs numéricos de fixture dedicados. No crea cuentas/grupos ni usa sudo/su.
- El cliente root valida `SO_PEERCRED.uid` del servidor antes de enviar el ping; un servidor con UID alternativo debe recibir EOF con cero bytes.
- El servidor fixture valida `SO_PEERCRED.uid == 0` antes de `recv`; el cliente con UID alternativo no recibe respuesta protocolaria.
- El proceso servidor usa UID/GID reales, efectivos y saved del fixture, sin grupos suplementarios; aplica `RLIMIT_NOFILE=64`.
- Pool fijo de cuatro workers y semáforo antes de `accept()`; el probe mantiene cuatro conexiones ocupadas, verifica que la quinta no sea aceptada como quinto worker y que se acepte después de liberar un slot.
- Backlog configurado 8, read/write 5 s y deadline global 15 s. La saturación exacta, adversarios de timeout, full FD accounting, límites de payload/depth y escenarios restantes todavía no están implementados.

El runner crea fixtures temporales bajo `/run`, incluyendo una raíz de traversal root-owned 0711 (no escribible por grupo/otros) para que el peer alternativo pueda alcanzar el socket expuesto. Copia el script y el módulo IPC a una ubicación temporal de solo lectura accesible por los procesos con UID reducido. La limpieza valida identidad de cada socket; ante sustitución o fallo de un proceso, preserva el sandbox y reporta FAIL.

**Estado:** revisión estática en GitHub solamente. No se ejecutó el runner, pruebas, compilaciones ni workflows. El resultado completo esperado en esta iteración es `INCOMPLETE` porque quedan escenarios deliberadamente pendientes. El propietario debe revisar y ejecutar únicamente en VM desechable; no usar el servidor Debian de producción.

**Siguiente paso:** inspeccionar el diff local tras actualizar a este commit y decidir cuatro IDs numéricos reservados para la VM; después ejecutar A-IPC-02 y compartir el JSON completo. A continuación se completarán backlog/deadlines/FD accounting y el probe de resolución de rutas/colisiones. No se modifica handler/contrato ni se autoriza listener persistente, systemd, SQLite o despliegue.


## Actualización A-IPC-02 — 2026-11-21 (MA-03 validado; MA-06 implementado)

El propietario ejecutó en `Atlas-VM-test` el commit
`069dbb9520f9e640955d9122f3a8012b2f55ba1a`: MA-01..MA-05 PASS y
CP-01/CP-04 PASS; global INCOMPLETE. MA-03 comprobó EUID 2006 rechazado
antes de connect (`connect_attempted=false`) y ninguna conexión observada
por el servidor. Capacidad: máximo 4 workers activos, 0 tras recuperación;
backlog 8 configurado pero no saturado. Duración 1.339 s; cleanup de ambos
sandboxes `/run` completado. Debian 13, kernel 6.12.117+deb13-amd64,
Python 3.13.5; fixtures 2005/2005 y 2006/2006.

Posteriormente se implementó MA-06 en commit `9a8380eb4a4051763699b7c07c3ad9dfcf1eeccd`:
el runner envía un envelope ping con claims top-level `uid`, `gid`, `pid`;
el decoder debe rechazar campos extra como `INVALID_REQUEST`, mientras la
identidad del peer se obtiene de SO_PEERCRED. **MA-06 está pendiente de
ejecución por el propietario.** No extender el PASS de `069dbb9` al commit
posterior.

Siguiente paso: revisión estática final del diff MA-06 y ejecución en
`Atlas-VM-test`. No ejecutar en `greed` de producción. El probe sigue
INCOMPLETE; configuración confiable, transporte/desconexión, backlog exacto,
deadlines, recuperación de workers y FD accounting siguen pendientes.



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


## Incremento A-IPC-02 — MA-07/MA-08 implementados (2026-11-21)

Se añadió `tests/integration/private_unix_listener/probe_config.py`, un parser/loader **exclusivo del probe**, y se integró al runner:

- Gramática cerrada ASCII `clave=valor`, sin defaults, duplicados, claves desconocidas, secciones, comentarios ni extensiones.
- Carga relativa a un descriptor de directorio del sandbox privado; `O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC`; verificación de archivo regular, root:root, modo exacto 0644 del fixture, un hardlink y tamaño máximo 4096 bytes.
- Validación de IDs numéricos de servicio frente a los IDs de fixture, allowlist exactamente `(0,)`, `SOCK_SEQPACKET`, ruta absoluta canónica y modos de fixture 0600/0700.
- MA-07 incluye ausencia, clave duplicada/desconocida/ausente, identidad alterada, symlink, FIFO, modo inseguro, owner incorrecto, archivo excesivo y hardlink.
- MA-08 reemplaza atómicamente el archivo después de cargarlo y comprueba que el snapshot congelado y su colección tuple conservan los valores originales.
- Los archivos temporales se crean y eliminan dentro del sandbox privado `/run/atlas-mutual-auth-*`; no se consulta ni crea `/etc/atlas/admin-ipc.conf`.

**Límite deliberado:** el formato `clave=valor` y los valores del fixture no son el formato ni la configuración de producción. El loader valida el archivo final relativo a un descriptor de directorio temporal ya confiable; no implementa el recorrido completo de ancestros desde `/`, que permanece en el probe PA separado. El módulo no está en `src/atlas` ni integrado al handler.

**Estado:** MA-07/08 implementados y pendientes de ejecución del propietario. No se ejecutaron pruebas, compilaciones ni workflows desde GitHub. El resultado global seguirá INCOMPLETE por MA-09/10 y cobertura CP pendiente.

## A-IPC-02 — validación del propietario de MA-07/MA-08 (2026-11-21)

El propietario ejecutó el runner en `Atlas-VM-test`, Debian 13, kernel `6.12.117+deb13-amd64`, Python 3.13.5, como EUID 0 real, con fixtures SERVICE UID/GID `2005/2005` y OTHER UID/GID `2006/2006`, sobre el commit `585dd3d979bc1b800550e4b9c79c382b22cf1f6c`.

- **MA-01..MA-08: PASS.** La ejecución agrupó MA-01..MA-06 en una fila PASS y MA-07 y MA-08 en filas independientes PASS.
- **MA-07:** configuración válida aceptada con `service_uid=2005`, `service_gid=2005` y `client_uids=[0]`; rechazó los 11 casos previstos: ausente, clave duplicada, desconocida o requerida ausente, identidad de servicio alterada, symlink, FIFO, modo group/other-writable, owner incorrecto, archivo excesivo y hardlink.
- **MA-08:** después de reemplazar atómicamente el pathname de configuración, el snapshot conservó `/run/atlas/admin.sock`; la ruta sustituta era `/run/atlas/changed.sock`. Campos frozen y colecciones inmutables: PASS.
- **MA-01..MA-06:** autenticación mutua y orden antes de send/recv; cliente no-root rechazado antes de connect; claims UID/GID/PID falsificados rechazados como `INVALID_REQUEST`.
- **CP-01/CP-04: PASS.** Máximo observado de workers activos: 4; recuperación a `active_after_recovery=0`. Backlog configurado 8, **sin saturación exacta**.
- Duración: 1.497 s. Cleanup de sandboxes privado y traversal bajo `/run` completado después de salir los procesos hijos. No hubo filas FAIL.
- **Resultado global: INCOMPLETE.** Siguen sin implementar/validar MA-09..MA-10 y CP-02..CP-03/CP-05..CP-12.

La evidencia corresponde únicamente al commit y entorno indicados. No demuestra validación de todos los ancestros de la ruta, listener persistente, configuración productiva, lifecycle, límites adversariales completos ni despliegue. El parser sigue siendo fixture exclusivo del probe.

**Siguiente incremento:** revisar el runner y el contrato antes de implementar MA-09/MA-10; mantener separadas las pruebas de desconexión durante autenticación y rechazo de transportes distintos de AF_UNIX/SOCK_SEQPACKET. Después continuar con backlog, deadlines, recuperación, límites de payload/profundidad y contabilidad de FDs.

## A-IPC-02 — MA-09/MA-10 implementados, pendientes de validación (2026-11-21)

En el commit `f41df94d0f87d288bfc7e3df45c66295fa19d570` se añadieron dos escenarios al runner, ejercitando el handler real `handle_admin_connection` de `src/atlas/platform_admin_ipc.py`:

- **MA-09 — EOF antes de la primera petición:** un peer AF_UNIX/SOCK_SEQPACKET autorizado cierra su dirección de escritura sin enviar bytes. El handler debe lanzar `AdminPeerDisconnected` con `PEER_DISCONNECTED`; se verifica que no envía respuesta y no acepta una petición.
- **MA-10 — transporte no soportado:** se entregan al handler una conexión AF_UNIX/SOCK_STREAM y una AF_INET/SOCK_STREAM, ambas con un paquete ping válido ya encolado. Se exige `AdminProtocolRejected/INVALID_REQUEST`, que el paquete siga sin consumirse (MSG_PEEK) y cero bytes de respuesta. Esto comprueba rechazo de familia/tipo antes de leer el protocolo.
- El runner ahora reporta MA-09 y MA-10 individualmente; el bloque INCOMPLETE se limita a CP-02..CP-03 y CP-05..CP-12.
- **Estado:** implementación revisada estáticamente; MA-09/MA-10 pendientes de ejecución del propietario. No se ejecutaron pruebas, builds ni workflows desde GitHub. MA-01..MA-08 y CP-01/04 conservan únicamente la evidencia previa del commit `585dd3d`; no se extrapola al nuevo commit.
- **Límite:** MA-09 prueba EOF/half-close antes de enviar la primera petición, no una interrupción en mitad de la llamada kernel SO_PEERCRED. MA-10 valida los dos casos representativos indicados, no todas las combinaciones de socket.


### A-IPC-02 — actualización del runner CP-02/CP-03 (2026-11-21)

Commit de implementación: `1e213b2f7a254cd2718e644e415670dca08435f5`.
La ejecución anterior del propietario en `901c792` validó MA-01..MA-10
y CP-01/CP-04; no valida este cambio posterior. CP-02/CP-03 ahora miden
`Recv-Q/Send-Q` con iproute2 `ss`, saturan backlog 8 y requieren EAGAIN
para la novena conexión sin accept adicional. Estado: pendiente de ejecución
en `Atlas-VM-test`. CP-05..CP-12 continúan pendientes. No hay cambios en
`main`, host, cuentas, servicios, SQLite o transporte productivo.


El preflight del observador `ss` se endureció en commit
`67526c21a1edc2938b5caefb699aa6c6576c5b73`: el runner resuelve el
ejecutable y valida también todos sus directorios ancestros como root-owned
y no escribibles por grupo/otros. La medición usa la ruta resuelta. Esta
corrección también está pendiente de validación local.


Corrección estática adicional en commit
`4ab6a1b7762f4d45a745ea2c36f7289411a9c848`: declaración explícita de
`global SS_BIN` para que el preflight pueda conservar la ruta resuelta del
observador sin sombrear el nombre global. Pendiente de validación junto con
CP-02/CP-03.


### Resultado CP-02/CP-03 y corrección de semántica AF_UNIX (2026-11-21)

Ejecución del propietario sobre commit `1ebf930`: overall FAIL en CP-02/CP-03
porque la conexión no bloqueante posterior a Recv-Q=8 devolvió 0. El resto
de escenarios MA-01..MA-10 y CP-01/CP-04 pasó; cleanup de sandboxes correcto.

El kernel Linux AF_UNIX compara longitud de cola con backlog usando `>`,
por lo que `listen(8)` admite nueve conexiones pendientes antes de rechazar
la siguiente. El runner ahora comprueba la novena conexión exitosa, mide
Recv-Q=9/Send-Q=8, y exige EAGAIN en la décima. Corrección commit
`634e19decce2322e94ca0d1fe410b259f23dcb67`. Pendiente de ejecución local;
no se ejecutaron pruebas desde GitHub.


### A-IPC-02 — CP-02/CP-03 validados (2026-11-21)

El propietario reportó ejecución sobre `b5b0128e2646e41e3a2f927251c6fa6dafa897d7`: MA-01..MA-10, CP-01/04 y CP-02/03 PASS; overall INCOMPLETE por CP-05..CP-12. Recv-Q/Send-Q 8/8, novena conexión admitida 9/8, décima rechazada EAGAIN errno 11; accepts permanecieron en 9, workers dentro del límite y cleanup correcto.

**Gate CP-05:** un cliente silencioso vence al read timeout de 5 s, ya que el fixture aplica `min(READ_TIMEOUT, remaining_global)`, antes del deadline global de 15 s. Aclarar el comportamiento deseado antes de implementar el escenario.


## A-IPC-02 — CP-05 / CP-06 implementados (2026-11-21)

Runner commit: 59fafb801a31d7adf51a6598db78440255744321. Diseño y README actualizados en 60a4549fd9c6dbb3030c187203ae8c3cdec43aa1 y 4265ac9a53428468778c73ad7f271f15b883686c.

La decisión del propietario conserva read/write timeout de 5 s y deadline global de 15 s:

- **CP-05:** peer autorizado silencioso; el fixture debe observar timeout de lectura cerca de 5 s, antes del deadline global, y cierre sin respuesta.
- **CP-06:** servidor fixture separado inyecta 11 s de espera test-only después de accept/autenticación y antes de read. El timeout de lectura se limita al presupuesto restante (aprox. 4 s), con cierre cerca de 15 s desde accept. Se registran timestamps monotónicos, timeout efectivo, presupuesto restante y EOF del peer.

La espera controlada no es comportamiento productivo ni simula una escritura bloqueada. Con el fixture actual de un recv y un send, los timeouts I/O individuales de 5 s no consumen por sí solos el deadline de 15 s. CP-06 demuestra el recorte del timeout de una fase posterior por el deadline accept-based, no una carga read+write acumulada real.

**Estado:** CP-05/06 implementados y pendientes de validación del propietario en Atlas-VM-test. CP-07..CP-12 siguen pendientes; overall INCOMPLETE. No se ejecutaron pruebas, builds ni workflows desde GitHub. No se modificaron handler productivo, contrato, main, host, cuentas, servicios ni SQLite.


## A-IPC-02 — validación CP-05/CP-06 (2026-11-21)

El propietario ejecutó commit 0db262802ce30ec38a4ce52a4f5bfaa3081fc2b1 en Atlas-VM-test, Debian 13, kernel 6.12.117+deb13-amd64, Python 3.13.5, EUID 0, fixtures SERVICE 2005/2005 y OTHER 2006/2006. Duración 22.095 s; cleanup de sandboxes /run correcto.

- MA-01..MA-10: PASS.
- CP-01/04: PASS; máximo 4 workers, activos tras recuperación 0.
- CP-02/03: PASS; cola observada 8 y 9; novena conexión admitida, décima EAGAIN errno 11; sin accepts extra.
- CP-05: PASS; read timeout 5.002 s desde accept, deadline global no alcanzado, EOF y 0 bytes de respuesta.
- CP-06: PASS; fase read comienza a 11.004 s con 3.996 s de presupuesto restante; cierre a 15.006 s desde accept, deadline global alcanzado, EOF y 0 bytes de respuesta.
- CP-07..CP-12: INCOMPLETE; sin FAIL en escenarios reportados. Overall permanece INCOMPLETE.

CP-06 usa una espera artificial test-only; no representa trabajo productivo ni una escritura bloqueada. No se ejecutaron pruebas/builds/workflows desde GitHub; no se modificó handler productivo, contrato, main ni host. No hay aprobación de transporte productivo ni despliegue.


## A-IPC-02 — CP-07 implementado (2026-11-21)

Runner commit: fbd4512d163b31e53b355280e636fb47cf8d66a9. CP-07 inyecta una RuntimeError de un solo uso en un worker fixture. Requiere EOF y cero respuesta en el peer fallido, evento worker_error, active=0 tras la excepción, servidor todavía vivo y una segunda petición authority.ping exitosa seguida de active=0. La inyección es test-only; el handler productivo no cambia.

**Estado:** CP-07 implementado y revisado estáticamente, pendiente de ejecución del propietario en Atlas-VM-test. CP-08..CP-12 pendientes; overall INCOMPLETE. No se ejecutaron pruebas, builds ni workflows desde GitHub; no se modificó main, host ni servicios.


## A-IPC-02 — CP-07 primera ejecución y corrección

El propietario ejecutó el runner d054f95 en Atlas-VM-test: MA-01..MA-10 y CP-01..CP-06 PASS; CP-07 abortó porque el colector Server._record clasificó el evento worker_error deliberadamente inyectado como fatal. No se alcanzaron las comprobaciones de EOF, liberación de slot ni segunda petición; resultado overall=FAIL, CP-07 sigue sin validar.

Corrección del runner en 1df8385f3783308636ccd9538d4c1033fd05be33: se permite consumir exactamente el RuntimeError previsto solo en el servidor CP-07; cualquier otro worker_error continúa siendo fatal. Siguiente paso: actualizar Atlas-VM-test a este commit y repetir el runner completo. Solo VM desechable; no usar greed. No se ejecutaron pruebas, builds ni workflows desde GitHub.


## A-IPC-02 — CP-07 segunda ejecución y corrección del reset

En commit ccfc495e4bcbe0adc9283f75bee1823d5338451b, MA-01..MA-10 y CP-01..CP-06 volvieron a PASS; CP-07 falló con ECONNRESET. El worker fixture lanzaba la excepción sin consumir el registro SOCK_SEQPACKET enviado por el cliente. El cierre con datos pendientes puede producir reset en vez de EOF; CP-07 no está validado.

Runner corregido en 1df8385f3783308636ccd9538d4c1033fd05be33: CP-07 consume el paquete desencadenante antes de inyectar RuntimeError, para que el cierre pueda probar EOF ordenado y cero bytes de respuesta. La aserción de recuperación permanece intacta. Siguiente paso: actualizar y repetir el runner completo solo en Atlas-VM-test desechable. No ejecutar en greed. No se ejecutaron pruebas, builds ni workflows.

## A-IPC-02 — CP-07 validado; CP-08/CP-09 implementados (2026-11-21)

El propietario ejecutó `077e01b00e8f3c628d5f1cee44b8a58670434789`
en `Atlas-VM-test`, Debian 13, kernel `6.12.117+deb13-amd64`,
Python 3.13.5, EUID 0, fixtures SERVICE `2005/2005` y OTHER
`2006/2006`.

- **MA-01..MA-10: PASS.**
- **CP-01..CP-07: PASS.** Cuatro workers máximos; backlog efectivo Linux
  9 para listen(8), décima conexión EAGAIN; CP-05 timeout 5.008 s; CP-06
  deadline 15.012 s con 3.995 s restantes al iniciar read; CP-07 cerró el
  peer de la excepción con EOF/0 bytes, recuperó active=0 y procesó una
  segunda petición ping con código OK. El servidor permaneció vivo.
- **Cleanup:** sandboxes privado y de traversal bajo `/run` eliminados
  después de finalizar los procesos hijos.
- **Resultado global:** INCOMPLETE, sin escenarios FAIL; CP-08..CP-12 no
  estaban incluidos en el commit ejecutado.

El runner incorporó después CP-08 y CP-09 en commit
`fe7343fa5b0dc9a63368ad067d5f5ca08c764e01`:

- CP-08 verifica request exactamente 16 KiB, 16 KiB + 1 y un paquete que
  excede el buffer de recepción; además prueba response exactamente 64 KiB
  y rechazo de 64 KiB + 1 antes de enviar bytes.
- CP-09 verifica profundidad total 16 y rechazo de profundidad 17 como
  `INVALID_JSON`.

**CP-08/CP-09 están implementados y revisados estáticamente, no validados.**
No se ejecutaron pruebas, compilaciones ni workflows desde GitHub. CP-10..12
siguen pendientes: contabilidad completa de FDs/threads bajo carga,
recuperación tras ciclos de saturación y rechazo de startup con
`RLIMIT_NOFILE` insuficiente sin elevarlo.

**Siguiente paso único:** actualizar `Atlas-VM-test` a la punta actual de
esta rama y ejecutar el runner completo como root solo dentro de esa VM
desechable. Nunca en `greed` de producción. No se modifica handler,
contrato, `main`, host, cuentas, servicios ni SQLite; no se autoriza
listener persistente ni despliegue.

## A-IPC-02 — CP-08/CP-09 validados; CP-10 implementado (2026-11-21)

El propietario ejecutó `caf7bbb8c83388a3723b66a7f4060a01c97c171d`
en `Atlas-VM-test` (Debian 13, kernel `6.12.117+deb13-amd64`,
Python 3.13.5, EUID 0; SERVICE 2005/2005, OTHER 2006/2006):

- MA-01..MA-10 y CP-01..CP-09: PASS.
- CP-08: 16 KiB exactos alcanzaron schema validation; 16 KiB+1 fue
  `REQUEST_TOO_LARGE`; paquete superior al buffer fue
  `MESSAGE_TRUNCATED` sin respuesta. Response exacto 64 KiB íntegro;
  64 KiB+1 rechazado antes de enviar bytes.
- CP-09: profundidad JSON total 16 llegó a schema validation; profundidad
  17 produjo `INVALID_JSON`.
- CP-05/06/07, backlog y autenticación mutua continuaron PASS.
- Cleanup correcto; duración 22.678 s; global INCOMPLETE porque CP-10..12
  aún no estaban en el commit ejecutado.

CP-10 fue añadido al runner en `e02bbbb7e3eacb45fbeab620d00cf0463e1c827e`
y corregido estáticamente en `bf3c62375fd8a3017b332efe406be9d1fd903568`.
Mide FDs y threads del proceso fixture mediante procfs en baseline, máxima
carga (4 workers + 9 conexiones pendientes) y recuperación. Exige FD count
no superior a 64, 4 threads worker + principal (máximo 5), RLIMIT_NOFILE
soft/hard 64/64, active=0 tras drenar y proceso servidor vivo.

**CP-10 implementado y revisado estáticamente; pendiente de ejecución local.**
CP-11/12 siguen pendientes: ciclos repetidos de saturación/recuperación y
rechazo de startup con RLIMIT_NOFILE insuficiente sin elevarlo. El runner
no cambia el handler ni la configuración del host. No se ejecutaron pruebas,
builds ni workflows desde GitHub. Próximo paso: actualizar y ejecutar solo
en `Atlas-VM-test` desechable; nunca en `greed` producción.


## A-IPC-02 — CP-10 diagnóstico procfs y corrección (2026-11-21)

El propietario ejecutó `cbfe0e20a79ae3ee8fd901ba43ea6df360962398` en `Atlas-VM-test`: MA-01..MA-10 y CP-01..CP-09 PASS; CP-10 terminó en FAIL con `ProbeFailure: CP-10 procfs status omitted Max open files`. El cleanup de ambos sandboxes `/run` fue correcto. Este fallo no contiene una medición de exceso de recursos: el escenario se detuvo al no localizar el campo.

La revisión estática encontró que `Max open files` se buscaba erróneamente en `/proc/<pid>/status`; Linux lo expone en `/proc/<pid>/limits`. Runner corregido en `47b9ed94c21d26b18c415bedd2f1d352894f2620`, manteniendo FD/thread snapshots y la comprobación soft/hard 64/64. **CP-10 corregido estáticamente, pendiente de repetición por el propietario**. CP-11/12 siguen pendientes. No se ejecutaron pruebas, builds ni workflows desde GitHub. Repetir solo en `Atlas-VM-test`, nunca en `greed` producción.


## A-IPC-02 — CP-10 contador de accepts: sincronización y diagnóstico (2026-11-21)

En commit `892d934267684fc8d5a179993f71c2b11c614c7e`, MA-01..MA-10 y CP-01..CP-09 PASS; CP-10 falló al comparar el contador de accepts durante saturación. El mensaje no contenía valores suficientes para distinguir una aceptación real de un baseline incompleto.

Revisión estática: `Server` recibe eventos stdout en una cola alimentada por un reader thread; CP-10 calculaba `accepted_before` sin drenar esa cola. Se corrigió en `7c009dac7fd7c4270ea6edf8bc1a004a8fb8f898`: drenar eventos previos antes del baseline y añadir baseline/expected/observed/pending/workers al error. La aserción estricta permanece. **No marcar CP-10 PASS** hasta una nueva ejecución; no se ha confirmado aún si hubo aceptación real o desincronización del baseline. CP-11/12 pendientes. Sin pruebas/builds/workflows desde GitHub; ejecutar solo en `Atlas-VM-test`.


Ajuste adicional `664c398a5afdafda313eb81379cbb85a5b71007d`: `Server.drain(duration)` espera la ventana completa aunque el queue se vacíe temporalmente, para dar tiempo al reader thread a transferir eventos pendientes desde stdout. Refuerza el baseline CP-10 sin relajar la aserción. Pendiente de ejecución; no implica PASS.

## A-IPC-02 — CP-10 validado por el propietario (2026-11-21)

El propietario ejecutó el commit `75929e1f9f3a17e2a19bb9a98d30e7cd86b26a0a`
como root en `Atlas-VM-test`, Debian 13, kernel
`6.12.117+deb13-amd64`, Python 3.13.5; SERVICE 2005/2005 y OTHER
2006/2006.

- **MA-01..MA-10 y CP-01..CP-10: PASS.**
- CP-10: cuatro workers activos, nueve conexiones pendientes y contador
  accepted estable en 22 durante saturación.
- Snapshots: baseline 4 FDs/5 threads; saturación 8 FDs/5 threads;
  recuperación 4 FDs/5 threads.
- `RLIMIT_NOFILE` soft/hard 64/64; active tras recuperación 0;
  servidor vivo.
- Duración 22.725 s; cleanup de sandboxes privado y traversal bajo
  `/run` completado tras finalizar los procesos hijos.
- **Overall: INCOMPLETE**, porque CP-11 y CP-12 aún no están implementados.

CP-11 cubrirá ciclos repetidos de saturación/recuperación; CP-12 verificará
rechazo de startup con `RLIMIT_NOFILE` insuficiente sin elevarlo. La
evidencia CP-10 aplica únicamente al commit y VM indicados. No autoriza
transporte productivo, listener persistente ni despliegue. El asistente no
ejecutó pruebas, builds ni workflows.

## A-IPC-02 — CP-11 implementado (2026-11-21)

Runner commit: `70ee6a7a77dc671fe4ec26a6ca98a25a2e47e104`.
CP-11 añade tres ciclos consecutivos de saturación/recuperación en el mismo
servidor fixture: cuatro workers ocupados, nueve conexiones pendientes,
contador accepted estable durante saturación, cierre de peers y drenaje de
las trece conexiones aceptadas. Cada ciclo compara snapshots de FDs/threads
en baseline, saturación y recuperación; exige retorno exacto al baseline
y que el servidor permanezca vivo.

**CP-11 implementado y revisado estáticamente; pendiente de ejecución del
propietario.** CP-12 continúa sin implementar: rechazo de startup cuando
el proceso hereda un `RLIMIT_NOFILE` insuficiente, sin elevarlo. Overall
permanece INCOMPLETE. Ejecutar el runner solo en `Atlas-VM-test`
desechable; nunca en `greed` producción. No se ejecutaron pruebas,
builds ni workflows desde GitHub.

## A-IPC-02 — CP-11 validado y CP-12 implementado (2026-11-21)

El propietario ejecutó `da8c6ea9ed0ce36d2c7b4c2c8c5417dd79975fb7`
en `Atlas-VM-test` (Debian 13, kernel 6.12.117, Python 3.13.5):
MA-01..MA-10 y CP-01..CP-11 PASS. CP-11 completó tres ciclos:
accepted 31→35→44, 44→48→57 y 57→61→70; en cada uno FDs 4→8→4,
threads 5→5→5, active=0 al recuperar y servidor vivo. Cleanup correcto;
duración 24.72 s.

CP-12 está implementado en runner commit `0fb5c3989f5ac9e11b14344557b18ad7bd75027b`, pero pendiente de ejecución del propietario. Simula límites heredados soft/hard 32/32 antes de exec y exige rechazo de startup antes de bind, sin elevar límites ni crear socket. **Overall permanece INCOMPLETE hasta validar CP-12.** Ejecutar solo en `Atlas-VM-test` desechable, nunca en `greed` producción. El asistente no ejecutó pruebas, builds ni workflows.



## Registro de validación completa A-IPC-02 — propietario (2026-11-21)

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


## Registro de validación A-IPC-03 — A-THREAT-06 (2026-11-21)

**Ejecución del propietario:** commit `b200c292ac0602593c8dbefafb1bd71b79001b06`, VM desechable `Atlas-VM-test`, Debian 13, kernel `6.12.117+deb13-amd64`, Python 3.13.5, EUID 0. Identidades fixture SERVICE 2005:2005 y OTHER 2006:2006.

- Resultado global `PASS`: 12 escenarios PASS, 0 FAIL, duración 0.062 s; sandbox privado de `/run` eliminado tras finalizar procesos hijos.
- PR-01: 13/13 rutas léxicamente inválidas rechazadas.
- PR-02/07: recorrido de seis componentes y endpoint fixture con SERVICE 2005:2005, modo 0700.
- PR-03: symlinks alpha/beta/gamma rechazados; sentinel intacto.
- PR-04/05/06: componente no-directorio, ancestros group/other-writable y owner externo rechazados.
- PR-08: owner y modo incorrectos rechazados.
- PR-09: snapshot de configuración cargado desde parent dirfd validado.
- PR-10: symlink, FIFO y hardlink rechazados.
- PR-11: descriptor conservó acceso al objeto original (`anchored-original`) después de sustituir el pathname por symlink.
- PR-12: OTHER UID no pudo hacer rename ni symlink; ambos devolvieron errno 13 (`EACCES`).

**Conclusión acotada:** A-THREAT-06 queda validada para los escenarios fixture probados. No se creó socket, no se ejecutó bind/connect, no se examinó configuración real de Atlas y no se probaron colisiones ni stale recovery. No fija ruta/ownership productivos ni aprueba listener persistente.

**Siguiente gate:** A-IPC-04, plan en `docs/design/local-authority-admin-private-listener-stale-recovery-probe.md`, para A-THREAT-05. El runner no está implementado. Resolver primero cobertura de procfs/namespaces, carreras de PID y disponibilidad de namespace adicional. Mantener startup fail-closed y prohibido connect como detector de liveness.


## A-IPC-04 — primera ejecución y correcciones pendientes (2026-11-21)

El propietario ejecutó el commit `27dd83a34e149901f908356668dc119b4491487f`
en `Atlas-VM-test`: 8 PASS, 4 FAIL, 0 INCOMPLETE; inventario de 204
procesos y seis namespaces visibles; cleanup del sandbox confirmado.

- **SR-01/SR-11 FAIL:** los listeners locales activos no aparecieron por
  pathname en las tablas inspeccionadas. No clasificar como stale. SR-03
  sí detectó un listener en un namespace adicional.
- **SR-06 FAIL:** el fixture positivo usaba los caracteres literales
  `\\n` en lugar de saltos de línea.
- **SR-07 FAIL:** las filas positivas omitían el `:` obligatorio de `Num`.

Correcciones estáticas en `b2767ff6a64886fb361bbf7f8f36a016f90c3e7f`
y `48008ff559b8c4f2528e3668d140797266f38844`: fixtures SR-06/SR-07
corregidos y diagnósticos acotados añadidos a SR-01/SR-11 para incluir
filas candidatas de procfs. No se relaja matching ni clasificación.

**Siguiente paso:** ejecutar el HEAD actual en `Atlas-VM-test` desechable
y compartir JSON completo. SR-01/SR-11 siguen sin causa confirmada;
A-THREAT-05 permanece abierta. No ejecutar en `greed`, no usar
recuperación real. El asistente no ejecutó pruebas, builds, workflows ni
probes.


## A-IPC-04 — segunda ejecución del propietario (2026-11-21)

El propietario ejecutó `bd3b0e0a1379c7b034e10a33b9b45b329e6e807a`
en `Atlas-VM-test`: 10 PASS / 2 FAIL / 0 INCOMPLETE; 201 procesos
visibles, seis namespaces inventariados y sandbox eliminado.

SR-06 y SR-07 pasan tras corregir sus fixtures. SR-03 sigue detectando
un listener en un namespace distinto. SR-01 y SR-11 siguen sin encontrar
los listeners locales; `candidate_rows=[]` en ambas ejecuciones.
Esto no demuestra que estén inactivos ni que sus sockets sean stale.

Commit `a7bf92d07d12012d20822b64a57ee0ab17c953e1` añade diagnóstico
solo en caso de fallo: PID y namespace del inspector, inode del FD del
listener, namespaces del snapshot, filas candidatas por pathname o inode
y lectura directa de `/proc/self/net/unix`. No modifica la decisión,
no conecta al socket y no relaja matching.

**Siguiente paso:** ejecutar el HEAD actual exclusivamente en
`Atlas-VM-test` y compartir JSON. A-THREAT-05 sigue abierta; no usar
recuperación real ni ejecutar en `greed`. No se ejecutaron pruebas,
builds, workflows ni probes desde GitHub.

### A-IPC-04 — tercera ejecución del propietario (2026-11-21)

El propietario ejecutó el commit `f10cda09aec5cb0b9d42ab50f3bb9f6617dc8fda` en `Atlas-VM-test`: **10 PASS / 2 FAIL / 0 INCOMPLETE**; 203 procesos visibles, seis network namespaces en el inventario base y siete durante SR-03; cleanup del sandbox confirmado.

- SR-01 sigue FAIL. El listener activo tenía FD inode `39340`; el inspector estaba en `net:[4026531840]`, namespace presente en el snapshot. No hubo filas candidatas ni coincidencias en la lectura directa de `/proc/self/net/unix`; no se informó error de lectura. Esto confirma que no es solo un problema de selección del PID representante, pero no explica la ausencia ni demuestra que el socket esté inactivo/stale.
- SR-11 falló por un defecto de harness: invocó `_listener_diagnostics(snapshot, path)` sin el argumento obligatorio `listener`. No aporta evidencia sobre detección.
- SR-02..SR-10 y SR-12: PASS. SR-03 volvió a detectar el listener de la namespace adicional; SR-04/05 abortaron ante cobertura incompleta; SR-09 preservó el objeto sustituto; SR-10 retiró únicamente el fixture con token de identidad correcto.
- No se llamó connect para comprobar liveness. La limpieza del sandbox privado se completó.

Corrección posterior: commit `8a89bc9f66829886164ed4fe93fd7af232a18f01` pasa el objeto `listener` a `_listener_diagnostics` en SR-11. Es una corrección de diagnóstico, aún no ejecutada por el propietario. SR-01 permanece sin resolver; **A-IPC-04 no está validado y A-THREAT-05 sigue abierta**. No clasificar ausencia de filas como stale ni ejecutar unlink. Próximo paso: revisar la semántica de visibilidad/inode de AF_UNIX en procfs y después repetir el runner corregido solo en `Atlas-VM-test`. Nunca en `greed`.

## A-IPC-04 — cuarta ejecución del propietario y diagnóstico ampliado (2026-11-21)

El propietario ejecutó `e46070e6e1824b06af04a3627feb0f658de9c1f8` en `Atlas-VM-test`: **10 PASS / 2 FAIL / 0 INCOMPLETE**; 204 procesos visibles; seis namespaces en el inventario inicial y siete durante SR-03; cleanup confirmado.

- SR-01 y SR-11 fallaron ambos porque los listeners locales activos no aparecieron en las tablas visibles. La lectura directa de `/proc/self/net/unix` tampoco encontró filas candidatas ni coincidencias por inode, sin error de lectura. Los inodes de FD fueron `39726` y `40202` respectivamente.
- SR-11 ya no falla por el `TypeError`; produce el mismo fallo sustantivo de detección que SR-01.
- SR-02..SR-10 y SR-12: PASS. SR-03 detectó de nuevo el listener en namespace adicional; los abortos por cobertura incompleta y la protección de identidad/token siguen pasando.
- No se llamó connect para probar liveness. El sandbox privado fue eliminado.

La fuente del kernel revisada muestra que la interfaz procfs de AF_UNIX enumera sockets y expone inode/path; la discrepancia requiere diagnóstico adicional, no una relajación del matching. Commit `a3e2d3dcb24842c4ae842f1d8082b4a2dbade374` amplía los diagnósticos de SR-01/SR-11 con FD target, `getsockname()`, `SO_TYPE`, `SO_ACCEPTCONN`, recuento y filas completas (acotadas a 64) de la tabla local. Es un cambio de diagnóstico, no ejecutado aún por el propietario.

**Estado:** A-IPC-04 no validado; A-THREAT-05 abierta. La ausencia de filas no clasifica un socket como stale y no autoriza unlink. Repetir solo en `Atlas-VM-test`, nunca en `greed`. Sin limpieza automática, listener persistente ni despliegue.


## A-IPC-04 — quinta ejecución del propietario (2026-11-21)

El propietario ejecutó el checkout `6f77960c25fba873be67bd29fb40814619e44ee8`
en `Atlas-VM-test` (Debian 13, kernel `6.12.117+deb13-amd64`,
Python 3.13.5, EUID 0; SERVICE 2005:2005, OTHER 2006:2006).
Resultado: **10 PASS / 2 FAIL / 0 INCOMPLETE**, duración 0.161 s;
203 procesos visibles, seis network namespaces en el inventario inicial,
cleanup del sandbox confirmado.

La ampliación diagnóstica confirma en ambos escenarios locales:
- `getsockname()` devuelve el pathname fixture esperado.
- `SO_TYPE=5` (`SOCK_SEQPACKET`) y `SO_ACCEPTCONN=true`.
- El FD apunta a `socket:[41168]` (SR-01) y `socket:[41184]` (SR-11).
- La lectura directa de `/proc/self/net/unix` fue correcta (58 registros),
  pero no contiene pathname, inode ni fila candidata del listener. No hubo
  error de lectura; el namespace del inspector `net:[4026531840]` sí figura
  en el inventario.
- SR-03 detectó el listener adicional `net:[4026532290]` (PID 6051)
  desde el inventario del proceso padre.

SR-01 y SR-11 continúan FAIL por ausencia del listener activo en las tablas
procfs; ya no es un problema de bind/listen fallido según las propiedades
observadas del socket. SR-02..SR-10 y SR-12: PASS. No se llamó connect para
liveness; cleanup eliminó el sandbox.

**Conclusión:** la discrepancia entre un socket local correctamente enlazado
y escuchando y su ausencia completa en `/proc/self/net/unix` sigue sin
explicación. No cambiar el matching, no inferir stale, no ejecutar unlink.
A-IPC-04 no está validado y A-THREAT-05 permanece abierta. Solo investigar y
repetir en `Atlas-VM-test`; nunca en `greed`. Sin limpieza automática,
listener persistente ni despliegue. El asistente no ejecutó pruebas, builds,
workflows ni probes.


### Comparación manual STREAM/SEQPACKET posterior a la quinta ejecución (2026-11-21)

El propietario creó en un mismo proceso dos listeners temporales AF_UNIX:
STREAM (tipo 1, FD inode 40634) y SEQPACKET (tipo 5, FD inode 40638).
Ambos devolvieron pathname esperado y SO_ACCEPTCONN=1. Los filtros
por pathname en /proc/self/net/unix y ss -xl no devolvieron filas para
ninguno. La observación no parece exclusiva de SOCK_SEQPACKET.

La salida filtrada no demuestra que las tablas completas estén vacías
ni identifica la causa. Próximo diagnóstico: obtener ambas salidas
completas mientras los sockets sigan abiertos y registrar
/proc/self/ns/net del proceso creador. No relajar matching, no inferir
stale y no ejecutar unlink. A-IPC-04 sigue no validado y A-THREAT-05 abierta.


## A-IPC-04 — quinta investigación y corrección del lector procfs (2026-11-21)

El propietario comparó la lectura del runner con una lectura buffered completa mientras el listener fixture seguía abierto. La lectura única sin buffering devolvió **4.048 bytes / 58 registros** y omitió el socket; la lectura buffered devolvió **51.172 bytes / 711 registros** e incluyó la fila exacta del listener (Type 0005, estado 01, inode 41747, pathname esperado).

La causa quedó localizada en dos sitios del runner: _read_table() y la lectura diagnóstica de /proc/self/net/unix abrían con buffering=0 y confiaban en una sola llamada read(). Una lectura corta se interpretaba como tabla completa. No era un fallo de bind/listen ni de selección del PID representante.

**Corrección publicada en esta rama:** helper _read_bounded() con acumulación de lecturas cortas, bloques de hasta 64 KiB y límite de 4 MiB + 1; aplicado a ambas rutas de lectura. Se añadió tests/unit/test_private_listener_procfs_read.py con casos de lecturas parciales, límite, EOF y límite inválido.

**Pendiente de validación del propietario:** ejecutar la prueba unitaria nueva y el runner completo solo en Atlas-VM-test. No se ejecutaron pruebas, builds, workflows ni probes desde GitHub. Hasta entonces A-IPC-04 no está validado, SR-01/SR-11 no se marcan PASS y A-THREAT-05 sigue abierta. No relajar matching, no inferir stale, no ejecutar unlink, no usar en greed y no habilitar cleanup automático, listener persistente o despliegue.

## A-IPC-04 — stale recovery probe validado (2026-11-21)

El propietario ejecutó run_stale_recovery_probe.py en la VM desechable
Atlas-VM-test sobre el commit 375fb00a3fee230a57f89ffa7897a29309ff1dd2:
Debian 13, kernel 6.12.117+deb13-amd64, Python 3.13.5, EUID 0,
fixtures SERVICE 2005:2005 / OTHER 2006:2006.

**Resultado: overall=PASS; 12/12 escenarios PASS, 0 FAIL, 0 INCOMPLETE.**
El inventario vio 204 procesos y seis network namespaces; el namespace
principal contenía 710 registros. No hubo reintentos de snapshot y el
sandbox privado bajo /run fue eliminado después de cerrar procesos y sockets.

La corrección _read_bounded() acumuló lecturas cortas de procfs hasta EOF
o hasta el límite, tanto en _read_table() como en el diagnóstico directo.
Con ello SR-01 y SR-11 detectan los listeners locales activos, sin usar
connect/accept/send/recv para comprobar liveness. SR-03 volvió a detectar
un listener en un namespace adicional. SR-04/SR-05 abortaron correctamente
ante cobertura incompleta; SR-08/SR-09 preservaron objetos no admisibles o
sustituidos; SR-10 retiró únicamente el fixture exacto con token ligado a
su identidad; SR-12 mantuvo la clasificación fail-closed.

**Estado:** A-IPC-04 queda validado para los escenarios del harness y el
entorno indicados. El alcance se limita a procesos y namespaces visibles
desde el montaje procfs y PID namespace usados; no es cobertura host-wide,
no es atómico ante creación concurrente de procesos y no elimina el límite
TOCTOU entre revalidación y unlink.

**A-THREAT-05 permanece abierta.** Esta validación no autoriza recuperación
de sockets reales, limpieza automática, listener persistente, activación
systemd ni despliegue. No ejecutar en greed producción. La validación fue
ejecutada por el propietario; el asistente no ejecutó pruebas, builds,
workflows ni probes.
## A-IPC-05 — runner QP-01..QP-15 implementado, pendiente de validación (2026-11-22)

- Archivo: `tests/integration/private_unix_listener/run_listener_quiescence_probe.py`.
- Rama: `experiment/a-ipc-01-private-unix-listener-probe`; permanece separada de `main`.
- Preflight: Debian 13, systemd 257, kernel/Python fijados, cgroup v2 unificado, tmpfs en `/run`, SERVICE 2005:2005 y OTHER 2006:2006; valida acceso de ambas identidades al script y al intérprete.
- D-Bus: `GetUnit`, propiedades tipadas, `Unit.Job`, `Manager.ListJobs`, `ListUnitsByNames`; el orden de object paths de `ListJobs` está corregido. Tras stop, se exige unidad ausente y ningún job; `RefUnit/UnrefUnit` se ejecutan mediante una conexión persistente libsystemd; las observaciones permanecen en busctl.
- Cgroups: observer FD de directorio y `cgroup.events` abierto antes de stop, identidad dev/inode fijada, lecturas repetibles después de stop; se cierra tras confirmar `populated=0`.
- QP-01/02: seccomp para fork/clone/vfork/clone3, duplicación, SCM_RIGHTS e io_uring; QP-02 filtra también el auxiliar creado antes del listener. Dos observaciones de cgroup separadas por 50 ms; QUIESCENT solo si identidad/invocación/jobs/MainPID/cgroup/FD-policy coinciden.
- QP-03/04: transición y job stop pendientes con proceso que ignora SIGTERM; ABORT hasta terminar todo el cgroup.
- QP-05/06/07: separación de ControlGroup; rechazo de Delegate=yes y control Delegate=no con NNP, ProtectControlGroups, capabilities vacías y CAP_SYS_ADMIN/permisos; parser cgroup.events con lecturas parciales y errores.
- QP-08/09/10: filtros de creación de procesos y FD escape (incluido io_uring), execve con mismo PID y CLOEXEC.
- QP-11: `_TestLifecycleSupervisor` interno al harness; valida token, flock, segundo actor, caída simulada, marcador sticky y restart bloqueado. No es proceso supervisor independiente ni producto Atlas.
- QP-12: restart directo de root fuera del supervisor; detecta InvocationID nuevo y separa observers cgroup antiguo/sustituto. Root permanece en TCB.
- QP-13: proceso OTHER recibe listener FD por SCM_RIGHTS; se demuestra que cgroup del servicio vacío no basta mientras el holder conserva el FD. No es socket activation.
- QP-14/15: fallos inyectados de manager/supervisor, timeout acotado y discrepancias ControlGroup/dev/inode.
- Cleanup: detiene primero todos los fixtures; solo después retira endpoint y archivos ready/received si tipo, owner, mode, dev/inode coinciden. Los JSON usan O_NOFOLLOW, límites, UTF-8 estricto y rechazo de claves duplicadas. Reporte schema versionado, límites por escenario/total y timestamps monotónicos.
- El runner no se ha ejecutado ni validado. No se han ejecutado pruebas, builds o workflows; no se crearon unidades/cgroups/usuarios/grupos/rutas en hosts durante esta sesión.
- Próximo paso: completar revisión estática final y pasar a ejecución del propietario exclusivamente en `Atlas-VM-test`. Nunca en `greed`.
- A-THREAT-05 continúa abierta; no hay autorización de stale recovery, listener persistente, cleanup automático de endpoints Atlas ni despliegue.
