# Estado vigente de Atlas

> Corte documental: 16 de noviembre de 2026.
> Prioridad acordada: Atlas funcional de prueba; endurecimiento avanzado de seguridad en pausa.
> Rama revisada: `feature/terminal-commands`.
> Commit base de la validación local: `610f027f1fe91933278e431d8a9ec29dd291b96e`.
> Este documento registra el estado real conocido y prevalece sobre descripciones históricas anteriores que indiquen que la conversación sigue siendo solo en memoria o que la fase 2 no ha sido validada.

## Posicionamiento

Atlas es un proyecto de software funcional en desarrollo incremental: ya ejecuta una experiencia conversacional local con Ollama, persiste conversaciones en SQLite y ofrece administración, exportación y recuperación de conversaciones. No es únicamente un conjunto de contratos o un prototipo visual.

A la vez, Atlas todavía no es la plataforma autónoma completa de la visión. La capacidad conversacional funcional no implica que ya existan todos los gestores, agentes, automatizaciones o flujos protegidos de extremo a extremo.

## Capacidades funcionales verificadas en el repositorio

- Arranque local mediante `python -m atlas` y composición de consola.
- Integración de Assistant con Ollama local, con streaming y endpoint limitado a loopback.
- Modo offline informativo.
- Historial persistente de conversaciones en SQLite independiente de la base de autoridad.
- Recuperación de la conversación activa al reiniciar.
- Gestión de conversaciones: crear, listar, seleccionar, renombrar, cerrar y eliminar con confirmación.
- Exportación JSON versionada.
- Backup cifrado, verificación y restauración a una ruta nueva.
- Proyección limitada al modelo (8 turnos y 2.000 caracteres por mensaje), sin truncar el historial almacenado.
- Eliminación transaccional con rollback ante fallo.

## Evidencia local

El usuario ejecutó en Debian, con `.venv` activado, el 16 de noviembre de 2026:

| Comprobación | Resultado |
|---|---:|
| `python -m unittest tests.unit.test_conversation_deletion -v` | 6/6 OK |
| `python -m unittest discover -s tests -v` | 844/844 OK |

Las pruebas de eliminación utilizan bases temporales. Esta evidencia es una ejecución local reportada por el usuario; no es una ejecución de GitHub Actions ni una prueba de despliegue en producción. No se ejecutaron pruebas en GitHub durante la revisión documental.

También se habían realizado verificaciones manuales locales de persistencia, backup, verificación, restauración, exportación y eliminación sobre bases/rutas temporales.

## Estado de dominios de la visión

| Dominio | Estado documental |
|---|---|
| Atlas Terminal y conversaciones | Funcional en el alcance descrito; validación automatizada local aprobada |
| Assistant / AtlasCore | Composición conversacional local funcional; coordinación general pendiente |
| Identity / CAM | Modelos, servicios, contratos y persistencia local implementados parcialmente; autenticación externa y composición integral pendientes |
| Memory Engine | Infraestructura de dominio, gateway, consistencia, journal, checkpoints y recuperación local implementados parcialmente; persistencia de contenido y autoridad protegida completa pendientes |
| Broker | Tiene desarrollo operativo en su propio contexto; no debe confundirse con la consola conversacional ni atribuirse a este repositorio si no está en su árbol |
| Project / Environment Manager | Pendiente como subsistema operativo completo |
| Skills Manager | Pendiente como subsistema operativo completo; las Skills externas deben pasar por procedencia, análisis, permisos, aprobación, instalación aislada, auditoría y desactivación |
| Agentes y Scheduler | Pendientes como runtime integrado |
| Approval, eventos y notificaciones | Pendientes como flujos integrados completos |
| Ejecución general de herramientas | No habilitada en la consola actual |

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


### Actualización 3.3.3 — sobre de respuesta estructurada

En `tests/evaluation/phase3/` se añadió un contrato cerrado que permite al modelo responder con `proposal` o `refusal`. Las propuestas se validan mediante el validador canónico; las negativas no pueden incluir herramientas ni campos de autoridad. Se añadieron seis pruebas unitarias nuevas. Pendiente de actualización y ejecución local por el usuario; no se ha conectado ninguna herramienta real.


### Preparación P3-SR

Se añadieron nueve casos estructurados que cubren propuestas válidas, negativas, acceso entre proyectos, inyección indirecta, herramientas desconocidas, autoridad falsificada y suplantación de administrador. La política y construcción de solicitudes son exclusivas del harness. No se ha ejecutado Gemma ni se han conectado herramientas reales.


### Bootstrap LOCAL — validador V1, observador V2 y cadena sudo V3

- **V1:** validador aislado de fixtures completado y validado por el propietario en Debian el 16-11-2026. Compilación estricta, matriz ampliada y AddressSanitizer/UndefinedBehaviorSanitizer superados.
- **V2:** observador Linux genérico en `tools/bootstrap-observer/`, validado por el propietario en Debian: build estricto, pruebas automatizadas, observación local y sostenida, detección de foreground, sudo local, SSH con PTY directo, shell intermediario y SSH sin PTY. El resultado genérico no autoriza ni valida cadenas de privilegios.
- **V3:** observador diagnóstico específico de la cadena sudo en `tools/bootstrap-chain-observer/`, con diseño `docs/design/local-bootstrap-chain-observer-v3-design.md`. Implementa revisión del padre directo, metadatos sudo setuid root, UID/GID, cadena sudo contigua, TTY del ancestro de origen, pidfd y doble muestra. Incluye pruebas fixture negativas y smoke test. **Compilación y pruebas Debian del propietario pendientes.**
- Frontera: V3 es solo lectura y no privilegiada; no instala ni ejecuta helper, no modifica PAM, sudoers, systemd, SSH, usuarios/grupos, claves o configuración protegida, y no se conecta a Broker, SQLite, CAM o runtime. `CHAIN_PATTERN_MATCHED_DIAGNOSTICALLY` no es autorización. Candidato A no aprobado para ejecución privilegiada; Recovery Gate permanece cerrado.


### Actualización — evaluación de la cadena sudo y separación de privilegios (16-11-2026)

**Evidencia adicional recibida del propietario en Debian:**

- `sudo -V`: sudo 1.9.16p2; plugins de política, sudoers e I/O en la misma versión.
- `sudo -l`: `greed` conserva autorización irrestricta `(ALL : ALL) ALL`.
- Defaults activos observados: `env_reset`, `mail_badpass`, `secure_path` y `use_pty`. No se observaron excepciones activas `env_keep` en la inspección compartida.
- `visudo -c`: los archivos sudoers inspeccionados parsean correctamente.
- En `sudo -- sh -c`, el listado de procesos mostró un proceso `sudo` y un shell `sh` hijo, ambos asociados a `pts/1); el descriptor 0 del proceso sudo apuntaba a `/dev/pts/0` y el del shell a `/dev/pts/1`.
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
