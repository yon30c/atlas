# Estado vigente de Atlas

> **Corte documental:** 21 de noviembre de 2026.
> **Main actual:** PR #29 integrado mediante merge commit `c4e5655c37f4d7bd21d431d1c855b8f0cb2c0d0b` (21-11-2026). La suite comunicada fue ejecutada sobre el HEAD de PR `4e84eab1fd03ddd9057525ee18a3c02a1d804cd6`, antes de los commits documentales y del merge; no se ha reportado una nueva ejecución sobre el merge commit.
> **PR #29:** cerrado e integrado en `main`; HEAD probado `4e84eab1fd03ddd9057525ee18a3c02a1d804cd6`.
> **PR integrado:** [#29](https://github.com/yon30c/atlas/pull/29), merge commit `c4e5655c37f4d7bd21d431d1c855b8f0cb2c0d0b`.
> **Suite completa reportada:** sobre el HEAD de PR #29 `4e84eab1fd03ddd9057525ee18a3c02a1d804cd6`: **1,590 tests — OK (skipped=1)**, 34.753 s, Python 3.13.5. La validación precede al merge commit; no afirmar que se ejecutó sobre `main` después del merge.
> **Validación local de PR #29:** en Debian 13, HEAD `4e84eab1fd03ddd9057525ee18a3c02a1d804cd6`, árbol limpio y sincronizado con origin. Probe user-manager: `PASS` (descriptor, dos activaciones, ownership/mode privados y `RemoveOnStop=no`). Suite completa: `Ran 1590 tests in 34.753s`, `OK (skipped=1)`. Esta evidencia cubre ese HEAD y no demuestra system-manager, separación de privilegios ni despliegue. No se ejecutaron pruebas, compilaciones ni workflows desde GitHub.
> **Estado IPC:** handler/prototipo para conexiones ya aceptadas; solo `authority.ping` está implementado. No hay listener persistente, daemon administrativo ni acceso administrativo real a SQLite.
> **Estado de transporte:** ninguno aprobado para producción. Listener propio en filesystem privado: candidato para probe aislado; socket activation systemd sobre filesystem: suspendida por colisión destructiva observada; AF_UNIX abstracto: alternativa experimental con riesgos de preclaim/DoS y sin DAC.
> **Este documento diferencia** implementación publicada, cambios en PR, validación local reportada y capacidades conectadas al runtime.

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
