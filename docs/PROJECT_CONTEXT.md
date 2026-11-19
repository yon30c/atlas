# Atlas — contexto operativo del proyecto

> **Última actualización:** 2026-11-18 (hora local del propietario; los commits más recientes de GitHub aparecen fechados 2026-11-19 UTC).
> **Repositorio:** [yon30c/atlas](https://github.com/yon30c/atlas)
> **Propósito:** documento de transferencia de contexto para continuar el desarrollo sin reconstruir decisiones ni confundir código publicado, código en ramas y validación local.

## 1. Visión del proyecto

Atlas es un entorno personal de asistencia, coordinación y automatización de proyectos. Debe permitir consultar información, conservar contexto útil y delegar trabajo a componentes, agentes y herramientas sin concederles autoridad ilimitada.

Principios no negociables:

- **Seguridad por defecto:** denegar cuando falten identidad, contexto, autorización o evidencia.
- **Mínimo privilegio:** conceder únicamente las capacidades necesarias.
- **Aislamiento:** separar propietario, proyectos, entornos, memorias y consumidores.
- **Mediación:** las operaciones protegidas pasan por la frontera responsable; el modelo no ejecuta acciones por producir texto.
- **Trazabilidad:** correlacionar solicitud, decisión, cambio y resultado.
- **Recuperación verificable:** no recuperar operaciones protegidas a partir de datos estructurales no autenticados.
- **Portabilidad:** mantener los dominios desacoplados de proveedores e infraestructura cuando sea posible.
- **Control humano:** las decisiones sensibles y no delegables permanecen bajo control del propietario.

Atlas no es todavía la plataforma autónoma completa de esta visión. La consola conversacional local con Ollama y la persistencia de conversaciones son funcionales; buena parte de la infraestructura de identidad, autoridad, delegación, memoria y operaciones administrativas está implementada por etapas, pero no toda está conectada a un runtime de extremo a extremo.

## 2. Reglas de trabajo acordadas

Estas reglas gobiernan todas las sesiones futuras:

1. **Trabajar directamente en GitHub.** Leer documentación, inspeccionar código, comparar ramas, crear/editar archivos y publicar commits mediante la integración de GitHub.
2. **No usar ChatGPT Work.** No cambiar a Work ni usar su navegador/entorno para estas tareas.
3. **No ejecutar pruebas desde GitHub ni durante la edición remota.** GitHub es el entorno de lectura, revisión, edición y documentación; no es el entorno de validación.
4. **Debian es el único entorno de pruebas del propietario.** El propietario ejecuta allí los comandos acordados y comparte resultados. No declarar una fase validada hasta revisar esa evidencia.
5. **No afirmar que se ejecutaron pruebas** por haber leído tests, CI, commits o documentación. Distinguir siempre: implementado, documentado, pendiente de validación y validado por el propietario.
6. **Inspeccionar antes de modificar.** Leer el estado de la rama, los archivos relevantes, sus diferencias con la base y la documentación normativa antes de editar.
7. **No modificar `main` directamente.** Trabajar en la rama de trabajo indicada; respetar la jerarquía de ramas y los PR existentes. No hacer merge ni cambiar el destino de un PR sin decisión explícita.
8. **No cambiar contratos aprobados, invariantes de seguridad ni decisiones funcionales silenciosamente.** Si aparece una decisión nueva, presentar el problema, las alternativas relevantes y una recomendación; esperar aprobación cuando afecte comportamiento, autoridad o arquitectura.
9. **Cambios pequeños y trazables.** Evitar rehacer componentes funcionales. Cada incremento debe incluir implementación necesaria, pruebas que el propietario ejecutará y documentación actualizada.
10. **Mantener el estado del proyecto actualizado.** Al cerrar cada incremento actualizar este documento y el documento canónico afectado (por ejemplo `docs/status-current.md`, roadmap o diseño). Registrar commit, rama, validación exacta, pendientes y siguiente paso.
11. **No desplegar ni tocar el host por inferencia.** Cambios en usuarios, grupos, sudoers, PAM, systemd, Docker, permisos, servicios o bases reales requieren diseño, revisión y aprobación explícitos.
12. **No tratar la presencia de una interfaz, puerto, test o adaptador como prueba de capacidad operativa completa.**

### Formato de cada ciclo de trabajo

- Estado inicial: rama, HEAD, base, PR y working tree conocido cuando aplique.
- Documentos/contratos que gobiernan el cambio.
- Objetivo acotado y exclusiones.
- Inspección de archivos y diferencias en GitHub.
- Implementación/documentación en la rama autorizada.
- Commit(s) y enlaces a los archivos/PR.
- Comandos exactos para Debian.
- Resultado recibido del propietario y clasificación: PASS / FAIL / pendiente.
- Actualización del estado y siguiente paso único.

## 3. Repositorio y estado GitHub observado

Repositorio: `yon30c/atlas`; rama predeterminada: `main`.

### Ramas relevantes al corte

| Rama | HEAD | Relación / función |
|---|---|---|
| `main` | `e9c36dad2061b1c4786d1e1447309e916675a971` | Base estable publicada observada. Último commit: diseño de operaciones administrativas de autoridad local (PR #22). |
| `test/authority-admin-systemd-activation` | `f96db3f8dc55fab282b084a940b152d0cdeac545` | Rama base de pruebas del canal administrativo y prototipo de socket activation. 26 commits por delante de `main`, 0 por detrás en la comparación observada. |
| `work/authority-admin-protocol-contract-alignment` | `9f3cf520639bb892b75fc59efedc7e490a94ee2a` | Rama de trabajo más reciente para alinear IPC con `atlas-admin/1`; 20 commits por delante de la rama `test/...`, 0 por detrás. |
| PR #28 | Draft / abierto | “Alinear IPC administrativo con atlas-admin/1 y completar ping”; head `work/...`, base `test/...`. No está integrado. |

La rama de trabajo actual se deriva de la rama de pruebas, que a su vez se deriva de `main`. Por tanto, **no comparar la rama de trabajo solo con `main` para decidir qué contiene PR #28**: revisar también la comparación `test/...` → `work/...` y el PR.

En el momento de esta actualización, GitHub informó que el último commit de la rama de trabajo era `9f3cf520` (“test(ipc): assert complete filesystem ping envelope”). Los nombres y SHA deben volver a consultarse al iniciar una sesión; no asumir que siguen iguales.

### Cambios recientes de main

- PR #21 integró la composición compartida de almacenamiento SQLite de autoridad (`5deb6bf1...`).
- PR #22 integró el diseño de operaciones administrativas de autoridad local; HEAD actual observado de `main`: `e9c36dad...`.
- `docs/status-current.md` aún conserva como referencia de código `5deb6bf`, por lo que debe reconciliarse al actualizar el estado canónico. No presentar el prototipo IPC de las ramas como integrado en main.

## 4. Estado funcional y arquitectura

### Base conversacional

- Consola local ejecutable mediante `python -m atlas`.
- Integración con Ollama local, streaming y modo offline informativo.
- Persistencia SQLite de conversaciones, recuperación de conversación activa, administración, exportación JSON y backup cifrado con verificación/restauración.
- La consola no es un shell y no dispone de acceso general a archivos, SQL, Docker ni contenedores.

### Identidad, autenticación, CAM y delegación

- Persistencia canónica de USER, AGENT, Project, Environment, Grants, asociaciones Project–Environment y Workspaces.
- Primitivas de autenticación nativa con Argon2id, autenticadores, proofs de un solo uso y autoridades separadas de autenticación e identidad.
- Servicios de identidad verificada USER/AGENT y revalidación transaccional.
- Identidad AGENT, binding nativo, delegaciones explícitas emitidas/revocadas por el propietario y evidencia verificada de corta duración.
- Renovación delegada de Grants bajo CAM y lifecycle de asociaciones con CAS y ledger.
- La infraestructura no equivale a login desplegado ni a runtime AGENT habilitado.

### Autoridad SQLite compartida

- Existe `SQLiteDatabase`, `SQLiteUnitOfWork` y composición `SQLiteLocalAuthorityUnitOfWorkFactory`.
- La composición compartida de autoridad fue integrada en PR #21.
- La misma UoW permite compartir la transacción entre repositorios/servicios autorizados.
- La composición no crea archivos, no inicializa SQLite, no aplica migraciones y no demuestra que exista un runtime principal conectado.
- La separación de writer lifecycle evita entregar la capacidad de transición a repositorios generales; los límites siguen siendo de proceso Python, no un sandbox frente a código arbitrario en el mismo proceso.

### Memory Engine

- Dominio, Gateway, consistencia, journal, checkpoints, recuperación local y reducers implementados parcialmente.
- Persistencia durable del contenido Memory, autoridad protegida completa, egress con fencing real y Forget de extremo a extremo siguen pendientes.
- El Recovery Gate debe permanecer cerrado hasta completar bootstrap, autoridad compuesta, recuperación y validación requeridos.
- El Memory Engine aún no ha demostrado independencia ejecutable fuera del paquete/composición Atlas.

### Skills, agentes y automatización

- Skills Manager, Scheduler/Task Manager y runtime integrado de agentes/herramientas siguen pendientes.
- Las Skills externas deberán pasar por procedencia, análisis de código/dependencias, declaración y revisión de permisos, aprobación explícita, instalación controlada, aislamiento según riesgo, auditoría, actualización controlada y desactivación/eliminación.
- Ninguna Skill puede elevar sus propios permisos.
- No conectar herramientas reales al modelo sin contratos, autorización y mediación explícitos.

## 5. Línea de trabajo reciente: operaciones administrativas de autoridad (Fase 2.5)

### Diseño normativo

Documento principal: `docs/design/local-authority-administrative-operations-design.md`.

Principios:
- Operador humano, frontend privilegiado y servicio ejecutor son identidades/fronteras separadas.
- El frontend privilegiado no abre SQLite, no recibe rutas de DB y no ejecuta SQL ni comandos genéricos.
- Las escrituras SQLite deben ocurrir bajo UID/GID dedicado `atlas-runtime`, sin root ni capabilities recuperables.
- El servicio vuelve a validar invariantes dentro de la transacción.
- Operaciones mutables usan operation ID, digest de intención, idempotencia y resolución explícita de resultados ambiguos.
- Una sola instancia `SQLiteDatabase` y UoW compartida por transacción.
- Sin endpoints HTTP, consola conversacional, plugins, Skills o AGENT para estas operaciones.
- El CLI de provisioning existente que abre SQLite como EUID 0 **no es apto para la futura DB principal** y no debe ejecutarse contra ella.
- El socket Unix es candidato experimental, no mecanismo aprobado para producción.

### Catálogo cerrado `atlas-admin/1`

El contrato acordado contiene exactamente siete operaciones; no añadir alias, batch, extensiones dinámicas ni ejecución genérica:

1. `authority.ping`
2. `authority.diagnose`
3. `authority.migrations.plan`
4. `authority.operation.status`
5. `authority.initialize`
6. `authority.migrations.apply`
7. `authority.project_environment.provision`

En la rama de trabajo actual solo `authority.ping` está implementada. Las otras seis se reconocen como nombres del catálogo, pero se rechazan con `OPERATION_DENIED`. Los nombres fuera del catálogo reciben `UNKNOWN_OPERATION`.

### Rama IPC actual

PR #28 y rama `work/authority-admin-protocol-contract-alignment`:

- Alineación con envelope exacto `protocol: "atlas-admin/1"`.
- Request máximo 16 KiB; response máximo 64 KiB.
- Validación estricta de UTF-8/JSON, claves duplicadas, campos exactos, números finitos, profundidad máxima 16 y UUIDv4 canónico.
- Códigos estables de rechazo; respuestas `rejected` cuando es seguro responder.
- Peer no autorizado, truncamiento, ancillary prohibido o desconexión: cierre sin respuesta.
- Timeouts independientes de lectura/escritura, default 5 s y máximo 60 s.
- Transporte `AF_UNIX/SOCK_SEQPACKET`, credenciales de peer obtenidas mediante `SO_PEERCRED` antes de leer el paquete, una solicitud por conexión.
- `authority.ping` informa únicamente versión de protocolo, versión de servicio y disponibilidad del handler. No abre SQLite ni inspecciona el filesystem de la DB.
- No hay listener persistente, daemon ni activación systemd implementados por este PR.
- La auditoría de contrato está en `docs/design/local-authority-admin-ipc-contract-audit.md`; el prototipo está documentado en `docs/design/local-authority-admin-ipc-prototype.md`.

### Estado de validación de PR #28

La descripción actual del PR reporta:
- Pruebas específicas IPC: 27/27 OK antes del último ajuste.
- `python -m compileall -q src tests`: correcto.
- `git diff --check`: correcto.
- Suite completa: 1.583 ejecutadas, 1 omitida y 2 errores iniciales en `test_platform_admin_ipc_filesystem.py`, debidos a expectativas antiguas del envelope experimental.
- Se actualizaron esas expectativas para `atlas-admin/1`, respuesta ping `completed` y desconexión `AdminPeerDisconnected`.
- **Validación completada por el propietario en Debian 13:** la suite completa reportó `Ran 1583 tests in 34.367s` y `OK (skipped=1)`: 1.583 ejecutadas, cero fallos, cero errores y una omitida. Esto confirma que desaparecieron los dos errores previos de `test_platform_admin_ipc_filesystem.py` tras alinear sus expectativas con `atlas-admin/1` y `AdminPeerDisconnected`. La evidencia fue comunicada por el propietario; no se ejecutaron pruebas desde GitHub. La auditoría `docs/design/local-authority-admin-ipc-contract-audit.md` registra el resultado. **Pendiente:** revisión final de seguridad/diff y aprobación explícita antes de integrar; PR #28 permanece Draft.

La rama base `test/authority-admin-systemd-activation` contiene el prototipo de socket activation en entorno de pruebas aislado. No equivale a instalación ni activación del servicio Atlas en el host. El diseño del lifecycle del listener sigue siendo propuesta y exige pruebas adversariales; no se deben tocar las unidades/servicios existentes.

## 6. Restricciones de seguridad y alcance

- No abrir ni modificar la DB principal real durante esta fase.
- No inicializar ni provisionar un administrador real ni una asociación real.
- No ejecutar migraciones reales ni activar Recovery Gate.
- No crear/modificar usuarios, grupos, sudoers, PAM, systemd, SSH, Docker, permisos o servicios del host sin decisión y plan aprobados.
- No reutilizar el UID de desarrollo/operador como identidad de servicio.
- No asumir que UID 0/TTY demuestra identidad humana; registrar la procedencia como evidencia técnica limitada.
- No presentar `SO_PEERCRED` como autorización de dominio: identifica al peer del sistema operativo, no concede autoridad Atlas.
- No permitir que el modelo, una Skill o un agente invoque SQL, shell o una operación administrativa genérica.
- No relajar controles para hacer pasar pruebas ni ocultar errores de la suite.
- No declarar producción, seguridad completa, atomicidad distribuida o anti-rollback externo sin evidencia específica.

## 7. Próximo paso acordado

**Realizar la revisión final de seguridad y del diff del PR #28**, manteniéndolo en Draft hasta completar esa revisión y recibir aprobación explícita para integrar. La suite completa ya fue validada por el propietario en Debian 13: 1.583 tests, `OK (skipped=1)`, 34.367 s.

Comandos previstos por la documentación de la rama:

```bash
git status --short --branch
git log -1 --oneline

python -m unittest -v tests.unit.test_platform_admin_ipc
python -m compileall -q src tests
git diff --check

# Después, ejecutar la suite completa con el mecanismo de discovery
# ya utilizado y validado en este checkout de Debian.
```

La suite completa ya fue ejecutada y reportada por el propietario: `Ran 1583 tests in 34.367s` / `OK (skipped=1)`. La corrección de expectativas filesystem está validada por esa ejecución. El siguiente trabajo es revisión final del PR y de los límites de seguridad. No avanzar a listener/daemon, operaciones administrativas reales ni merge sin revisión y aprobación explícita.

## 8. Fuentes que deben releerse al iniciar una sesión

Leer primero, desde la rama activa y directamente en GitHub:

1. `README.md` — visión y alcance general.
2. `docs/status-current.md` — estado canónico (verificar corte/HEAD porque puede estar atrasado respecto a main).
3. `docs/roadmap.md` y `docs/functional-test-roadmap.md` — secuencia de producto.
4. `docs/architecture.md` y `docs/functional-architecture-map.md` — composición y límites.
5. `docs/design/local-authority-storage-operational-contract.md` — contrato operativo de almacenamiento.
6. `docs/contracts/local-authority-admin-ipc-atlas-admin-1.md` — fuente normativa única del protocolo y especificaciones individuales del catálogo.
6. `docs/design/local-authority-administrative-operations-design.md` — diseño/catálogo de operaciones.
8. `docs/design/local-authority-admin-ipc-contract-audit.md` y `docs/design/local-authority-admin-ipc-prototype.md` — estado IPC actual.
9. `docs/design/local-authority-admin-listener-lifecycle.md` — lifecycle propuesto; no aprobado.
10. `docs/design/ME-D4J-sqlite-unit-of-work.md` — evolución y límites de UoW/Recovery Gate.
11. Documentos I3-2B/7B pertinentes cuando se trabaje sobre identidad, Platform Admin o lifecycle.

Al iniciar cada sesión, volver a consultar ramas, HEADs, PRs, comparación con base y contenido real de los documentos. Este archivo es una guía de contexto, no reemplaza los contratos normativos ni la inspección del estado vivo de GitHub.


---

## 9. Continuación de revisión de seguridad — 2026-11-19

Esta sección prevalece sobre los SHA y recuentos de commits históricos indicados en §3; al iniciar una sesión nueva, volver a consultar GitHub.

- PR #28 continúa abierto y en Draft, con base `test/authority-admin-systemd-activation`; no está integrado.
- La rama de trabajo es `work/authority-admin-protocol-contract-alignment`. En la revisión se observaron 24 commits sobre la base y cero detrás.
- El propietario confirmó en Debian 13 la suite completa previa: 1.583 tests, `OK (skipped=1)`, cero fallos y cero errores. Esta evidencia corresponde al estado anterior a la corrección adicional descrita abajo.
- La revisión del decoder encontró un caso no cubierto: un literal entero JSON de más de 4.300 dígitos puede hacer que `json.loads` lance `ValueError` por el límite de conversión de enteros de Python, escapando del rechazo protocolario.
- Corrección publicada: `decode_admin_request` captura `ValueError` y `RecursionError` y los convierte en `INVALID_JSON`. Se añadió una prueba con un entero de 5.000 dígitos y se actualizó la auditoría IPC y el documento del prototipo.
- **Validación de esta corrección:** pendiente. No atribuir el resultado anterior de 1.583 tests a este cambio nuevo.
- No se implementó listener, daemon, socket activation, acceso SQLite ni ninguna de las seis operaciones administrativas no habilitadas.

### Siguiente acción única

El propietario debe actualizar su checkout desde la rama remota de trabajo, ejecutar primero la prueba focalizada y después la suite completa. Solo tras recibir el resultado se continúa la revisión final del diff. Mantener PR #28 en Draft; no hacer merge ni tocar `main`.

### Resultado de validación posterior y corrección del request_id — 2026-11-19

- El propietario ejecutó la suite tras la primera corrección de enteros extremos: 1.584 tests, FAILED (failures=1, skipped=1).
- Falló únicamente test_rejects_integer_literals_exceeding_python_conversion_limit: el código de rechazo fue correctamente INVALID_JSON, pero request_id resultó None en vez del UUIDv4 válido del sobre.
- Causa: capturar ValueError alrededor de json.loads impide la excepción no controlada, pero aborta el parseo antes de que el decoder pueda extraer el identificador.
- Corrección publicada en la rama: parse_int convierte enteros normales; cuando Python rechaza un literal por el límite de conversión, devuelve un sentinel privado. El decoder termina de construir la estructura, recupera y valida request_id, y rechaza el sentinel como INVALID_JSON. El sentinel nunca puede llegar a una solicitud aceptada. No se modifica el límite global de Python.
- Estado de la segunda corrección: pendiente de validación local Debian. No considerar validado el caso ni la suite de 1.584 tests.
- Siguiente acción: ejecutar primero la prueba focalizada test_rejects_integer_literals_exceeding_python_conversion_limit, luego el módulo IPC y finalmente la suite completa. Mantener PR #28 en Draft; no merge ni cambios en main.

---

## 10. Fuente normativa consolidada de atlas-admin/1 — 2026-11-18

Se creó `docs/contracts/local-authority-admin-ipc-atlas-admin-1.md` como fuente normativa única del protocolo IPC administrativo.

Reglas consolidadas:
- Envelope exacto `protocol/request_id/operation/payload`; protocolo `atlas-admin/1`, UUIDv4 canónico.
- Transporte de prototipo `AF_UNIX/SOCK_SEQPACKET`, una solicitud y como máximo una respuesta por conexión; peer kernel `SO_PEERCRED` antes de leer.
- Request 16 KiB; response 64 KiB; profundidad JSON 16; timeout independiente de lectura/escritura, 5 s por defecto y 60 s máximo.
- JSON UTF-8 estricto, claves duplicadas/campos desconocidos/valores no finitos rechazados; truncamiento y ancillary data prohibidos.
- Envelope de respuesta con `protocol`, `request_id`, `status`, `code`, `summary`, `result`, `audit_ref`.
- Estados normativos cerrados: `completed`, `rejected`, `pending`, `unknown`.
- Catálogo cerrado de siete operaciones. `authority.ping` está implementada en el prototipo. Las otras seis cuentan ahora con especificaciones individuales trasladadas desde el diseño aprobado: payloads, precondiciones, resultados, efectos y restricciones; permanecen sin implementar y deshabilitadas.
- La allowlist de UID es configuración explícita del caller; `SO_PEERCRED` no es identidad humana ni autorización Atlas. No se aprueba aquí UID de producción, listener persistente ni systemd.
- Los límites 16/64 KiB sustituyen expresamente la propuesta anterior de 64 KiB para request en el diseño administrativo.

Documentos subordinados alineados:
- `docs/design/local-authority-administrative-operations-design.md`: diseño de dominio; ya no es fuente del envelope ni del catálogo IPC completo.
- `docs/design/local-authority-admin-ipc-contract-audit.md`: auditoría descriptiva; se eliminaron referencias normativas erróneas a §§10.5/11/15 del contrato raíz.
- `docs/design/local-authority-admin-ipc-prototype.md`: descripción de implementación; referencia el contrato §7 para el envelope.
- `docs/design/local-authority-admin-listener-lifecycle.md`: continúa siendo diseño separado y no aprobado para despliegue.

**Validación:** no se ejecutaron pruebas durante la edición documental. La suite 1.583/1 omitida es evidencia histórica anterior a la corrección final del decoder; esa corrección permanece pendiente de validación local Debian. No declarar el HEAD actual validado.

**Siguiente paso:** revisar la coherencia final de referencias/citas normativas y actualizar el estado/PR para que la nueva fuente sea visible, sin habilitar operaciones adicionales ni avanzar a despliegue.


---

## 11. Contratos individuales consolidados — 2026-11-18

Se recuperaron las especificaciones aprobadas previamente para las siete operaciones y se incorporaron en `docs/contracts/local-authority-admin-ipc-atlas-admin-1.md`, §§9.1–9.10.

- Lecturas: `authority.ping`, `authority.diagnose`, `authority.migrations.plan`, `authority.operation.status`. No mutan estado de dominio ni crean DB/ledger/sidecars/directorios/archivos. `operation.status` recibe `operation_id` solo como identificador de consulta.
- Mutaciones: exactamente `authority.initialize`, `authority.migrations.apply`, `authority.project_environment.provision`. Requieren `operation_id` UUIDv4, `reason` normalizado de 1–500 caracteres, `operator_evidence`, TTY foreground y confirmación tipada/exacta en frontend.
- Idempotencia: mismo operation ID + digest canónico devuelve resultado registrado; mismo ID con intención distinta => `IDEMPOTENCY_CONFLICT`. Commit no demostrable => `unknown/RESULT_UNKNOWN`, resolver mediante `authority.operation.status`.
- `diagnose`: perfiles `quick` y `deep`; ruta solo de configuración protegida; resultados PASS/FAIL/UNKNOWN/NOT_APPLICABLE; nunca repara ni muta.
- `migrations.plan`: payload vacío; DB/ledger/manifiesto read-only; plan ordenado con digest; historial divergente => BLOCKED.
- `operation.status`: payload con operation ID; solo ledger read-only; COMMITTED_EXACT / NOT_COMMITTED / UNKNOWN.
- `initialize`: bootstrap exclusivo de DB nueva, frase `INITIALIZE <canonical-database-name>`; no acepta ruta y no borra automáticamente restos parciales.
- `migrations.apply`: forward-only, plan/digest revalidado, frase `MIGRATE <expected_current_version> -> <target_version>`; ledger schema + evento administrativo en el mismo commit.
- `project_environment.provision`: crea solo asociación inicial ACTIVE/revision 1, frase `PROVISION <project_id> -> <environment_id>`; no crea ni modifica Project/Environment/USER/AGENT/Grant u otros recursos.
- El contrato especifica los detalles de comportamiento recuperados, pero §9.11 deja explícitos cierres de representación pendientes: esquema campo por campo de `operator_evidence`, normalización de `reason`, gramáticas canónicas de IDs/versiones/digests, esquemas completos de resultados y tabla exhaustiva de códigos/mapeo de estados. No inventar estos detalles.
- Solo ping está implementada; las otras seis permanecen deshabilitadas. La incorporación documental no autoriza ejecución real, listener, systemd ni acceso a la DB real.

No se ejecutaron pruebas en esta actualización. La corrección final del decoder continúa pendiente de validación local Debian. PR #28 permanece Draft.


---

## 12. Cierre de semántica y representación de operator_evidence — 2026-11-19

La revisión cerró primero la semántica y frontera de confianza de los cinco elementos de evidencia: UID real observado, UID efectivo del frontend, TTY/sesión, timestamp de autorización y alcance confirmado. Todos son declaraciones no confiables del frontend; no sustituyen `SO_PEERCRED`, identidad Atlas ni autorización de dominio.

La representación JSON se aprobó posteriormente según las decisiones expresas del propietario y quedó incorporada en el contrato normativo, §9.11.2. La subsección §9.11.1 conserva las restricciones semánticas y de confianza.

**Estado actual:** estructura y tipos JSON de `operator_evidence` aprobados; la normalización canónica de `reason` también quedó aprobada y documentada en §9.11.3 del contrato. Siguen pendientes las gramáticas canónicas de otros valores, esquemas completos de resultados y mapeo exhaustivo de códigos/estados. Esto no aprueba implementación ni despliegue.

## 13. Revisión y aprobación del esquema operator_evidence — 2026-11-19

**Contrato normativo actualizado:** `docs/contracts/local-authority-admin-ipc-atlas-admin-1.md`, §§9.11.1–9.11.2.

Decisiones del propietario:
- TTY/sesión: conservar los cuatro campos (`terminal_device`, `session_id`, `process_group_id`, `foreground_process_group_id`).
- UID: `operator_real_uid` y `frontend_effective_uid` admiten cualquier entero JSON no negativo; no se exige UID 0 ni se concede autorización por el valor.
- Alcance: `reason` se incluye también en `confirmed_scope` y debe coincidir exactamente con el `reason` del payload.

Esquema aprobado:
- `operator_evidence` tiene exactamente cinco propiedades obligatorias no anulables: `operator_real_uid`, `frontend_effective_uid`, `tty_session`, `authorized_at`, `confirmed_scope`.
- `tty_session` contiene exactamente los cuatro campos acordados. `terminal_device` es cadena UTF-8 no vacía, ruta absoluta, sin NUL y máximo 256 bytes; los tres IDs de sesión/grupos son enteros positivos representables por el tipo PID del sistema operativo. Ambos UID son enteros no negativos representables por el tipo UID del sistema operativo.
- `authorized_at` usa UTC estricto `YYYY-MM-DDTHH:MM:SS.ffffffZ`, generado después de la aceptación de confirmación y antes de transmitir.
- `confirmed_scope` tiene un esquema exacto por mutación: initialize incluye operación, nombre canónico de DB y motivo; migrations.apply incluye operación, versiones, digest y motivo; provision incluye operación, project ID, environment ID y motivo.
- El campo `operation` debe coincidir con el envelope. Los valores de alcance y el motivo deben coincidir exactamente y por tipo con su fuente autoritativa: payload para migrations.apply/provision, configuración protegida y frase de confirmación para initialize. No se permite coerción ni normalización oportunista.
- `confirmation_phrase` permanece en el payload y se valida por separado; no se duplica en `confirmed_scope`.

**Criterio de confianza importante:** el servicio puede validar la coherencia estructural declarada —incluida la igualdad entre process group y foreground process group—, pero no puede demostrar solo con esos valores que el frontend observó realmente el TTY foreground. La comprobación local de terminal, sesión, grupos de proceso y foreground corresponde al frontend privilegiado. La evidencia no es autenticación fuerte, prueba de presencia humana ni autorización de dominio.

**Pendiente, sin bloquear el cierre estructural:** esquemas completos de resultados y tabla exhaustiva de códigos/mapeo status-code. Las gramáticas canónicas de IDs, nombre de DB, versiones y representación textual del digest quedaron aprobadas posteriormente y se registran en §9.11.4. La serialización canónica del plan que alimenta SHA-256 sigue pendiente.

**Alcance del cambio:** documentación únicamente. No se modificó código ejecutable ni se ejecutaron pruebas. Las seis operaciones administrativas no implementadas continúan deshabilitadas; solo `authority.ping` está implementada. PR #28 sigue Draft y sin merge. No se aprobó listener persistente, systemd, UID de producción, acceso real a SQLite ni ejecución de mutaciones.

**Siguiente paso recomendado:** especificar la serialización canónica exacta del plan para `plan_digest`; después cerrar esquemas completos de resultados y mapeo status-code, sin habilitar operaciones.


---

## 14. Aprobación de la normalización canónica de reason — 2026-11-19

El propietario aprobó expresamente la propuesta de normalización de `reason`, incluida la ampliación del rechazo de controles Unicode para cubrir C1 además de C0 y DEL. La regla normativa completa está en el contrato `atlas-admin/1`, §9.11.3.

Decisión aprobada:
- Entrada Unicode válida; sin NFC/NFD/NFKC/NFKD.
- Rechazo de todos los caracteres Unicode de categoría general `Cc` (incluidos C0, DEL y C1); no se convierten controles en espacios.
- Cada secuencia de Unicode `White_Space` se colapsa a un espacio ASCII `U+0020`, y se eliminan espacios iniciales/finales.
- Resultado entre 1 y 500 puntos de código Unicode inclusive.
- Frontend prepara y confirma el valor canónico; servicio rechaza entradas no canónicas sin corrección silenciosa.
- `confirmed_scope.reason` coincide carácter por carácter con `payload.reason`; el digest de idempotencia usa ese valor canónico exacto.
- La regla no altera motivos históricos y no extiende el rechazo a categorías como `Cf` sin aprobación separada.

**Alcance:** documentación únicamente. No se modificó código ejecutable ni se ejecutaron pruebas. Las seis operaciones administrativas no implementadas continúan deshabilitadas; solo `authority.ping` está implementada. PR #28 permanece Draft y sin merge.

**Siguiente paso:** especificar las gramáticas canónicas restantes de IDs, nombre de DB, versiones y digest. Cada gramática debe revisarse contra los modelos y contratos existentes antes de proponerla.


## 14. Aprobación de gramáticas canónicas IPC — 2026-11-19

El propietario aprobó la recomendación de gramáticas canónicas para los valores administrativos restantes. La fuente normativa es `docs/contracts/local-authority-admin-ipc-atlas-admin-1.md`, §9.11.4.

- `project_id` y `environment_id`: ASCII lowercase, dígitos y guion; 1–128 caracteres; primer y último carácter alfanumérico; regex `^[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?$`. Sin normalización ni corrección silenciosa. Siguen siendo IDs opacos y deben resolverse contra registros canónicos.
- `canonical_database_name`: literal exacto `authority.sqlite3`, derivado por el servicio de configuración protegida; no es un selector de ruta del cliente.
- Versiones de migración: enteros JSON estrictos (no bool/float/string), rango 1..`2^63-1`; `target_version > expected_current_version`; sin coerción ni notación alternativa en la representación JSON canónica.
- `plan_digest`: SHA-256 expresado como 64 caracteres hexadecimales ASCII en minúsculas, sin prefijo. Payload, alcance confirmado y digest recalculado deben coincidir exactamente.

**Compatibilidad:** la gramática IPC no modifica retroactivamente los tipos de dominio ni registros históricos. Antes de habilitar provisioning, debe comprobarse que los IDs existentes cumplen la gramática; no renombrar ni migrar automáticamente.

**Pendiente:** la serialización canónica exacta del contenido del plan antes de calcular SHA-256 no quedó decidida. También siguen pendientes los esquemas completos de resultados y la tabla exhaustiva de códigos/mapeo status-code. Por ello `authority.migrations.apply` y las demás operaciones no implementadas continúan deshabilitadas.

**Alcance:** documentación únicamente. No se modificó código ejecutable ni se ejecutaron pruebas. Solo `authority.ping` está implementada. PR #28 permanece Draft y sin merge; no se aprobó listener persistente, systemd, UID de producción, acceso real a SQLite ni ejecución de mutaciones.

**Siguiente paso:** definir la serialización canónica del plan/digest, contrastándola con la representación determinista existente en Atlas sin introducir incompatibilidad ni ampliar el payload.


## 15. Revisión de integridad documental de gramáticas IPC — 2026-11-19

Se corrigió y verificó la incorporación de §9.11.4 en el contrato normativo. La revisión confirmó una sola cabecera del documento y una sola sección §9.11.4; la expresión regular quedó completa, el tratamiento de guiones consecutivos está explícito y la referencia de `reason` en `confirmed_scope` quedó alineada con §9.11.3.

**HEAD de la rama observado antes de esta actualización:** `fbc0fba60f225fbdd6a30bcabc0537f38b090946`. Este SHA identifica el estado revisado, no el commit que añade esta sección de contexto.

**Estado de la rama:** PR #28 abierto, Draft y sin merge. No se modificó `main`.

**Validación:** no se ejecutaron pruebas ni se modificó código ejecutable. La revisión fue documental y de integridad del texto publicado. La suite reportada previamente no valida los commits documentales actuales ni la corrección del decoder pendiente.

**Siguiente paso:** definir la serialización canónica exacta del plan para `plan_digest`, revisando los mecanismos deterministas ya existentes en Atlas; después cerrar esquemas completos de resultados y mapeo de códigos/estados.
