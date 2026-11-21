# Atlas — contexto operativo del proyecto

> **Última actualización:** 2026-11-21 (A-IPC-02: propietario validó MA-01..MA-10 y CP-01..CP-06 en 0db2628. CP-05 5.002 s; CP-06 15.006 s desde accept, con EOF y cero respuesta. CP-07..CP-12 pendientes; overall INCOMPLETE).
> **Repositorio:** [yon30c/atlas](https://github.com/yon30c/atlas)
> **Propósito:** documento de transferencia de contexto para continuar el desarrollo sin reconstruir decisiones ni confundir código publicado, código en ramas y validación local.

## Estado operativo vigente — 2026-11-21

> Esta sección es la referencia operativa prioritaria. Las secciones posteriores conservan decisiones y snapshots históricos; cuando un dato histórico contradiga este bloque, prevalece este bloque para el estado actual.

- **Repositorio:** `yon30c/atlas`.
- **Base estable:** `main` HEAD `1bd73d149dbd98e7ee2e5fdc36880883b6b03d16`; PR #29 integrado. Esta actualización no modifica `main`.
- **Rama activa:** `experiment/a-ipc-01-private-unix-listener-probe`; separada de `main`, sin PR propio. PR #30 sigue abierto en Draft en su rama original de diseño.
- **IPC existente:** contrato `atlas-admin/1` y handler para conexiones ya aceptadas. Solo `authority.ping` está implementada. No hay listener persistente, daemon administrativo ni acceso administrativo real a SQLite.
- **A-IPC-01:** el propietario reportó en Debian 13, commit `1d5bdb122a8480c36b445be7dd961b93806de74b`, resultado 16 PASS, 0 SKIP, 0 FAIL. Registro: `docs/status-aipc01-validation-2026-11-21.md`. No demuestra despliegue.
- **A-IPC-02:** el propietario validó MA-01..MA-10 y CP-01..CP-06 en `0db2628`. CP-02/03 observó cola 8/9, novena conexión admitida y décima EAGAIN errno 11. CP-05 observó read timeout 5.002 s, sin alcanzar deadline global; CP-06 inició read a 11.004 s con 3.996 s restantes y cerró a 15.006 s desde accept. Ambos cerraron con EOF y cero respuesta. CP-07..CP-12 pendientes; overall `INCOMPLETE`.
- **Alternativa A:** elegida como línea principal de evaluación, no aprobada para producción. Alternativa B suspendida por colisión destructiva en systemd; C no priorizada.
- **TCB-1 aceptada:** todos los procesos bajo la cuenta dedicada `atlas-runtime` pertenecen a la TCB; no se exige aislamiento intra-UID. La exclusividad operativa de esa cuenta aún debe definirse/verificarse.
- **Identidad del cliente aceptada:** el frontend administrativo debe conectar con **EUID 0**; la política de diseño del servicio es exactamente `client_uids={0}`. No se admiten otros consumidores sin nueva decisión. El entrypoint IPC real aún no existe/revisado; la decisión no es evidencia operativa.
- **Autenticación mutua:** A-IPC-02 validó MA-01..MA-10 en la última ejecución reportada: UID servidor antes de send, UID cliente antes de recv, rechazo pre-connect de EUID no-root, claims UID/GID/PID falsos, configuración fixture estricta/snapshot inmutable, desconexión previa a request y rechazo de transportes no soportados antes de leer. El entrypoint cliente/servidor de producción sigue sin existir/revisar.
- **Configuración confiable:** `docs/design/local-authority-admin-private-listener-identity-config.md` propone archivo root-managed `/etc/atlas/admin-ipc.conf`, root:root 0644 sin secretos, parser estricto y snapshot inmutable. Ruta candidata, no existente; no crear en host.
- **Resolución de rutas:** `docs/design/local-authority-admin-private-listener-path-resolution.md` define recorrido desde `/` por descriptores y validación de cada componente. Bajo TCB-1, el baseline es bind al pathname absoluto canónico después de verificar que UIDs externos no pueden escribir en ningún ancestro. El bind no es dirfd-atómico. La técnica procfs queda como alternativa experimental, no baseline.
- **A-THREAT-04:** ventana TOCTOU de unlink aceptada como residual bajo TCB-1 solo con directorio privado, instancia única y revalidación por descriptor; unlink no es atómico.
- **A-THREAT-05:** procedimiento manual candidato publicado en `local-authority-admin-private-listener-stale-recovery.md`; falta validarlo en sandbox. Startup siempre falla cerrado ante pathname existente y nunca intenta stale cleanup ni usa connect como detector.
- **A-THREAT-06:** especificación de resolución publicada; falta probe aislado de symlinks, sustitución de ancestros, colisiones y connect canónico.
- **A-THREAT-07:** perfil experimental: 4 workers, `listen(8)`, cola 0, read/write 5 s, deadline global 15 s y `RLIMIT_NOFILE=64`. CP-01..CP-06 validados por el propietario en `0db2628`; AF_UNIX admite 9 pendientes y la décima recibe EAGAIN. CP-07..CP-12 pendientes. No es configuración de producción.
- **A-THREAT-08:** máquina de estados de readiness/shutdown, drenaje, deadlines y ownership de FDs pendiente.
- **A-THREAT-09:** A09 usó runner UID 1000 y peer UID 1001; no valida cliente UID 0, servicio `atlas-runtime` ni permisos finales del despliegue.
- **Próximo paso:** actualizar Atlas-VM-test al commit `fbd4512d163b31e53b355280e636fb47cf8d66a9` y ejecutar A-IPC-02 para validar CP-07; después revisar CP-08..CP-12. Solo en la VM desechable.
- **Estado de cambios:** la rama experimental contiene MA-01..MA-10 y CP-01..CP-06 implementados y validados por el propietario en `0db2628`. CP-07..CP-12 siguen pendientes. No se modificó handler productivo, contrato normativo, runtime, SQLite, `main` ni host de producción. No se ejecutaron pruebas, compilaciones ni workflows desde GitHub. No se creó PR ni se aprobó listener persistente o despliegue.

**Límites vigentes:** A-IPC-01 valida únicamente los escenarios experimentales ejecutados en el commit/entorno indicados. No demuestra protección frente a root/capabilities suficientes ni procesos maliciosos del mismo UID; no valida separación de privilegios, system-manager, listener persistente, daemon, integración systemd, acceso/autorización SQLite ni operaciones mutantes. No autoriza cambios del host, usuarios, grupos, permisos, privilegios, servicios, provisioning o despliegue.


------

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

> **Snapshot histórico superado:** la tabla y las referencias de rama/PR de esta sección describen un corte anterior al merge de PR #28 y al PR #29. Se conservan como historial de la evolución; no deben usarse como estado operativo actual. Consultar «Estado operativo vigente» al inicio de este documento.

Repositorio: `yon30c/atlas`; rama predeterminada: `main`.

### Ramas relevantes al corte

| Rama | HEAD | Relación / función |
|---|---|---|
| `main` | `e9c36dad2061b1c4786d1e1447309e916675a971` | Base estable observada; no modificada por este trabajo. |
| `test/authority-admin-systemd-activation` | `f96db3f8dc55fab282b084a940b152d0cdeac545` | Base del PR; 26 commits por delante de `main`, 0 por detrás en la comparación consultada. |
| `work/authority-admin-protocol-contract-alignment` | `87fde61cf2ebbef7e5d72e00ffeebb369f46c2d2` | HEAD observado al iniciar la revisión final; 94 commits por delante de `test/...`, 0 por detrás. Los commits documentales de cierre posteriores pueden mover este SHA. |
| PR #28 | Draft / abierto | “Alinear IPC administrativo con atlas-admin/1 y completar ping”; head `work/...`, base `test/...`; 9 archivos cambiados. No está integrado. |

La rama de trabajo actual se deriva de la rama de pruebas, que a su vez se deriva de `main`. Por tanto, **no comparar la rama de trabajo solo con `main` para decidir qué contiene PR #28**: revisar también la comparación `test/...` → `work/...` y el PR.

El SHA de la rama de trabajo de la tabla es una observación al inicio de la revisión final del 19 de noviembre de 2026, no una referencia inmutable: volver a consultar el PR y la rama al iniciar cada sesión. La comparación consultada confirmó que la rama `work/...` está 94 commits por delante y 0 por detrás de `test/...`; no comparar PR #28 solo contra `main`.

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


## 14.1 Aprobación de gramáticas canónicas IPC — 2026-11-19

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


## 16. Cierre de canonicalización, resultados y códigos IPC — 2026-11-19

Esta sección prevalece sobre los pendientes y siguientes pasos históricos de §§12–15. El contrato normativo `docs/contracts/local-authority-admin-ipc-atlas-admin-1.md` pasó a revisión 1.1 sin cambiar el identificador wire `atlas-admin/1` ni ampliar las siete operaciones.

**Último HEAD de contrato revisado antes de esta actualización:** `4305c5bf712642a8deb77751cf9db7167d127d8d`.
**HEAD de la rama observado al registrar este contexto:** `5d2427426da49ab897d98c7ddb84ed898075bbb6`.

### 16.1 Serialización y digest

- `plan_digest` se calcula sobre la proyección exacta `atlas-admin-migration-plan` de §9.11.5, serializada mediante `atlas.memory.local_auth.canonical_json_bytes` (canonical JSON v1) y SHA-256 lowercase.
- La proyección fija protocolo, nombre lógico canónico de DB, versiones y migraciones pendientes ordenadas con sus nombres/checksums. Excluye timestamps, rutas físicas, datos de operador y datos de transporte.
- Un plan BLOCKED devuelve `plan_digest=null`. Un plan APPLICABLE sin migraciones puede tener digest con current=target y array vacío, pero no se puede aplicar.
- El digest de intención de mutación es independiente (`atlas-admin-operation-intent`, §9.11.6). Incluye campos semánticos y `reason`; excluye operation ID, request ID, frase de confirmación y evidencia de cada intento. La autoridad lo calcula para idempotencia.

### 16.2 Resultados y códigos

- §9.12 define esquemas exactos de `result` para las siete operaciones, incluidos arrays de checks/migraciones, resultados discriminados de `authority.operation.status`, timestamps UTC y referencias de auditoría.
- §10.4 cierra códigos de dominio y su mapeo a `status/code`. Los códigos de transporte/protocolo existentes permanecen en §10.1–10.2.
- Las siete operaciones son síncronas en esta revisión; ninguna emite `pending`. `authority.operation.status` puede devolver `operation_state=UNKNOWN` dentro de un envelope `completed/OK` cuando la consulta sí pudo determinar que el resultado subyacente no es demostrable.
- Una mutación solo responde `completed/OK` tras commit durable demostrado. Si el commit es incierto responde `unknown/RESULT_UNKNOWN` con `result={}`. `audit_ref` de envelope es obligatorio en éxitos mutables y coincide con `result.audit_ref`.

### 16.3 Estado y límites

- Fuente normativa: contrato IPC revisión 1.1, §§9.11.1–9.11.6, §9.12 y §10.4.
- Documentación subordinada alineada: `docs/design/local-authority-admin-ipc-contract-audit.md` y `docs/design/local-authority-administrative-operations-design.md`.
- Solo `authority.ping` está implementada. Las otras seis operaciones siguen reconocidas pero denegadas/no habilitadas.
- No se modificó código ejecutable ni se ejecutaron pruebas. El resultado histórico de 1.583 tests no valida estos commits documentales ni la corrección del decoder pendiente en Debian.
- No se aprobó listener persistente, daemon, systemd, UID de producción, acceso real a SQLite, ejecución de mutaciones ni merge.

**Siguiente paso histórico al cierre documental:** revisión cruzada de consistencia y diff de seguridad; esta revisión se registra en §16.4. El siguiente paso operativo actual es que el propietario valide en Debian la corrección del decoder y la regresión de UID/GID. Mantener PR #28 en Draft y no tocar `main`.

### 16.4 Revisión adversarial de consistencia y credenciales — 2026-11-19

- Se revisaron contrato 1.1, prototipo, tests, README y documentos subordinados en el HEAD de la rama; no se ejecutaron pruebas ni workflows.
- Se corrigió la lectura de `SO_PEERCRED`: PID se interpreta como entero con signo y UID/GID como enteros unsigned de 32 bits. La allowlist rechaza UID fuera de ese rango. Se añadió una regresión para UID/GID mayores que `INT_MAX`; en ese corte aún faltaba ejecutarla. La validación posterior consta en §16.5.
- Se eliminó en §9.5 una frase ambigua sobre la comparación del digest en `authority.operation.status`: la autoridad valida coherencia interna del ledger; el cliente compara el digest devuelto con su intención local.
- Se corrigió el bloque IPC del README, que conservaba pendientes ya cerrados en revisión 1.1.
- El futuro caller/listener debe cerrar cada conexión después de una sola solicitud/respuesta; el handler no es un listener y el lifecycle permanece fuera del alcance implementado.
- No se encontraron razones para habilitar operaciones nuevas. Solo `authority.ping` continúa implementada; las otras seis permanecen denegadas. No se aprueba listener, systemd, acceso SQLite, UID de producción ni mutaciones reales.
- En ese corte, la regresión nueva y la corrección del decoder de enteros JSON extremos requerían validación focalizada y suite completa por el propietario en Debian; ambas quedaron validadas posteriormente según §16.5.

**Estado en ese corte:** revisión adversarial documental/código completada con correcciones publicadas; la validación local seguía pendiente. Este estado fue sustituido por la validación PASS registrada en §16.5.


### 16.5 Validación local posterior de la revisión adversarial — 2026-11-19

El propietario actualizó su checkout Debian mediante fast-forward hasta `aae8beda568dee6996ce603fe936085e61fd1165` y comunicó los siguientes resultados:

- Prueba focalizada: `python -m unittest -v tests.unit.test_platform_admin_ipc` — 29 tests, `OK`.
- Suite completa: `Ran 1590 tests in 36.674s`, `OK (skipped=1)`.
- Resultado de la suite completa: 1.590 ejecutadas, cero fallos, cero errores y una omitida.
- La ejecución completa incluye la corrección de decodificación `SO_PEERCRED` (PID signed, UID/GID unsigned) y la regresión de enteros JSON extremos/request_id. La evidencia fue ejecutada y comunicada por el propietario en Debian; no se ejecutaron pruebas ni workflows desde GitHub.

**Clasificación:** validación local PASS para el HEAD `aae8beda568dee6996ce603fe936085e61fd1165`, limitada a la suite de pruebas ejecutada. No equivale a auditoría de seguridad completa, prueba de despliegue ni autorización de integración.

**Límites sin cambio:** solo `authority.ping` está implementada; las otras seis operaciones continúan denegadas/no habilitadas. No hay listener persistente, daemon, systemd ni acceso administrativo real a SQLite. PR #28 permanece Draft y sin merge; no se toca `main`.

**Siguiente paso al cierre de esta actualización:** revisión final de seguridad y del diff completo del PR #28; sus resultados se registran en §16.6. Cualquier integración requiere aprobación explícita del propietario.


### 16.6 Revisión final del diff y cierre documental — 2026-11-19

La revisión final se realizó directamente en GitHub sobre los nueve archivos del PR #28, incluyendo el contrato normativo, el módulo IPC, sus dos archivos de pruebas y los documentos subordinados.

**Resultado técnico:**
- No se identificó habilitación accidental de operaciones: `_IMPLEMENTED_OPERATIONS` conserva únicamente `authority.ping`; las otras seis siguen rechazadas con `OPERATION_DENIED`.
- No se añadieron listener, loop de aceptación, socket activation, daemon, unidad systemd, acceso SQLite ni mutaciones administrativas.
- El transporte mantiene las comprobaciones de tipo de socket, `SO_PEERCRED`, allowlist, recepción acotada, rechazo de truncamiento/ancillary, JSON estricto, timeouts independientes y respuesta única.
- El resultado de ping no afirma salud de SQLite ni capacidad de operaciones de dominio.
- La separación entre evidencia declarada del frontend, credenciales kernel y autorización de dominio permanece explícita en el contrato.
- No se encontró un hallazgo que requiera cambiar código ejecutable o decisiones normativas en este PR.

**Deriva documental corregida:**
- README actualizado de 1,583 a 1,590 tests y con HEAD exacto probado.
- Auditoría y prototipo actualizados para reflejar validación local PASS.
- Contexto actualizado con el estado de ramas/PR observado, la validación y la revisión final; se corrigió una numeración duplicada §14.

**Validación:** 29 tests focalizados y 1,590 tests de suite completa comunicados por el propietario en Debian sobre el HEAD de código `aae8beda568dee6996ce603fe936085e61fd1165`. Los commits de este ciclo son documentales y no modifican código ejecutable. No se ejecutaron pruebas, compilaciones ni workflows remotos durante la revisión.

**Límites:** PR #28 permanece abierto, Draft y sin merge. La rama sigue 94 commits por delante de su base en la comparación consultada al inicio de esta revisión (la cifra puede cambiar con commits documentales). No se modifica `main`, no se cambia la base del PR y no se autoriza despliegue ni integración. Cualquier merge requiere aprobación explícita del propietario.

**Siguiente paso:** revisión/decisión del propietario sobre si desea marcar PR #28 como Ready for review o mantenerlo Draft. No se realizará ese cambio sin autorización expresa.

### 16.7 Merge de PR #28, baseline de main y auditoría de preparación del listener — 2026-11-19

**Estado confirmado por el propietario en Debian:**
- PR #28 integrado en `main`; merge commit `74fcc6461c3ad8b802ef765b9d1e8aa478dcc552`.
- Checkout local: rama `main`, `HEAD` igual a `origin/main`, árbol de trabajo limpio.
- Suite completa: `Ran 1590 tests in 34.895s`, `OK (skipped=1)`.
- Entorno: Python 3.13.5 en `.venv`.
- Esta es la línea base local validada posterior al merge. La prueba omitida no es un fallo; su identidad debe localizarse antes de atribuir cobertura a ese caso.

**Auditoría de preparación del listener (revisión estática de GitHub; sin ejecutar pruebas ni workflows):**
- `src/atlas/platform_admin_ipc.py` sigue siendo un handler de una conexión ya aceptada. No crea/bindea/escucha sockets, no ejecuta `accept()`, no crea daemon ni valida un descriptor heredado de systemd. Solo `authority.ping` está implementada.
- El diseño lifecycle conserva las invariantes de directorio confiable, no sobrescritura, rechazo de rutas stale, verificación de inode, cleanup limitado, una solicitud por conexión, límites y cierre.
- La prueba de colisión del user-manager registró en Debian systemd 257.13 que una ruta preexistente con archivo regular perdió su contenido aunque `systemctl start` devolvió éxito. El probe evita repetir ese experimento destructivo y usa una ruta ausente dentro de directorio privado. Socket activation sobre filesystem permanece no aprobada.
- Hallazgo adicional: `run_user_manager_test.py` construía un request con `version: 1` en vez de `protocol: "atlas-admin/1"` y esperaba `status: "ok"`; el handler real requiere el envelope normativo y responde `completed/OK`. La rama de trabajo `work/systemd-socket-activation-probe-contract-alignment` corrige el probe para usar y validar el contrato real. La corrección aún requiere ejecución local del propietario en Debian.
- El probe sigue limitado al systemd **user manager** y al UID del usuario que lo ejecuta. No demuestra system-manager, socket root-owned, ejecución bajo `atlas-runtime`, separación real de privilegios ni cliente administrativo privilegiado.
- No se aprueba listener propio ni socket activation. No se aprueba instalación/configuración de systemd, creación de usuarios, cambios de permisos, acceso SQLite ni mutaciones administrativas.
- Puertas abiertas: resolver la propiedad segura de la ruta del socket frente a colisiones; decidir listener propio vs activación; definir identidad/UID real del cliente; revisar TOCTOU de cleanup y hardening systemd; validar el probe corregido en Debian; diseñar y probar lifecycle/concurrencia/shutdown antes de implementar el listener.

**Próximo paso:** el propietario ejecutará el probe corregido en Debian desde la rama indicada. El resultado del probe no elimina por sí solo la puerta de colisión ni aprueba despliegue. Los estados históricos de PR/HEAD y validación de las secciones anteriores deben leerse como snapshots de su fecha; esta sección es el estado posterior al merge de PR #28.

### 16.8 Evaluación de propiedad del endpoint IPC — 2026-11-19

La auditoría de preparación separa la propiedad del endpoint del mecanismo de activación. Socket activation sobre filesystem permanece suspendida por la colisión destructiva observada en Debian systemd 257.13.

El diseño lifecycle ahora compara:
1. Listener creado por el proceso en un directorio privado preaprovisionado de `atlas-runtime`: candidato para el siguiente probe aislado, con fallo cerrado ante cualquier ruta preexistente, sin stale cleanup automático y con límites TOCTOU de cleanup documentados.
2. Socket activation systemd sobre filesystem: suspendida; no desplegar.
3. Socket abstracto AF_UNIX/SOCK_SEQPACKET: alternativa experimental; evita pathname/inode y unlink, pero carece de permisos filesystem, permite intentos de conexión local y presenta riesgo de preclaim/DoS.

No se selecciona ni aprueba transporte para producción. Próximo trabajo: diseñar probes temporales independientes para A y C, ejecutar por el propietario en Debian, comparar evidencias y solicitar decisión explícita. No usar sudo, rutas Atlas existentes, system-manager de producción ni bases de autoridad. No implementar listener persistente.


### 16.9 Validación local de PR #29 — 2026-11-21

El propietario confirmó que Debian estaba en `4e84eab1fd03ddd9057525ee18a3c02a1d804cd6`, con árbol limpio y rama sincronizada con `origin/work/systemd-socket-activation-probe-contract-alignment`. Sobre ese HEAD comunicó:

- Probe `tests/integration/systemd_socket_activation/run_user_manager_test.py`: ambos mensajes `PASS`; activación systemd user-manager, validación del descriptor, dos activaciones, ownership/mode privados y `RemoveOnStop=no` dejando cleanup del pathname al harness.
- Suite completa: `Ran 1590 tests in 34.753s` y `OK (skipped=1)`.

Esta evidencia cierra la validación local del alcance de PR #29. No demuestra comportamiento del system-manager, separación real de privilegios, seguridad frente a procesos del mismo UID/root, ni aprueba transporte o despliegue. La activación systemd sobre filesystem permanece suspendida por la colisión destructiva observada previamente. Los probes de alternativas A y C siguen pendientes y separados.


### 16.11 Diseño del probe A-IPC-01 — 2026-11-21

Se creó en la rama `design/isolated-private-unix-listener-probe` el documento [Diseño del probe A-IPC-01 — listener Unix propio en directorio privado](design/local-authority-admin-private-unix-listener-probe.md).

- Alcance: experimento opt-in, sin privilegios, en directorio temporal privado, usando AF_UNIX/SOCK_SEQPACKET y el contrato existente `atlas-admin/1`.
- Casos: pathname libre; colisiones con archivo, symlink, socket activo y stale; propiedad/cleanup condicionado por identidad de inode; lifecycle; SO_PEERCRED y autorización separada; desconexión, truncamiento, ancillary, timeout y límites de recursos.
- Regla de seguridad: nunca hacer unlink preventivo ni stale cleanup automático; ante colisión, fallar sin modificar el objeto. Si la identidad del pathname no coincide durante cleanup, no eliminarlo.
- Límites: la comprobación inode + unlink conserva una ventana TOCTOU; el directorio privado no protege frente a root ni procesos del mismo UID. La prueba multi-UID queda condicional y no puede requerir sudo ni cambios del host.
- Exclusiones: no listener persistente, daemon, systemd, SQLite, operaciones administrativas, cambios del host ni despliegue.
- Estado: diseño propuesto, pendiente de revisión/aprobación; no implementado ni ejecutado. No hay comandos de prueba todavía.
- La rama de diseño se creó desde `main`; no se modificó `main` ni se abrió/mergeó un PR.

### 16.10 Integración de PR #29 — 2026-11-21

PR #29 se marcó Ready for review y se integró en `main` mediante merge commit `c4e5655c37f4d7bd21d431d1c855b8f0cb2c0d0b`. La validación local reportada por el propietario fue ejecutada sobre el HEAD de código `4e84eab1fd03ddd9057525ee18a3c02a1d804cd6`, con árbol limpio: probe systemd user-manager `PASS` (descriptor, dos activaciones, ownership/mode privados y `RemoveOnStop=no`) y suite completa `Ran 1590 tests in 34.753s`, `OK (skipped=1)`. Los commits posteriores fueron documentales; no se ha reportado una nueva ejecución de la suite sobre el merge commit.

El merge no habilita listener persistente, system-manager, separación de privilegios, acceso SQLite ni operaciones administrativas. Socket activation sobre filesystem permanece suspendida por la colisión destructiva observada. Las alternativas A y C requieren probes independientes y una decisión explícita posterior.


### Decisión del propietario — A-IPC-01 (2026-11-20)

El propietario aceptó avanzar con el diseño del probe A-IPC-01. El documento `docs/design/local-authority-admin-private-unix-listener-probe.md` fue revisado y queda como base para preparar su implementación experimental en una rama separada.

- El experimento se limita a un directorio temporal privado creado por el ejecutor sin privilegios.
- Los modos fijados para el experimento son directorio `0700` y socket `0600`; no son una política de producción.
- La matriz incorpora una carrera de dos binds simultáneos: exactamente un ganador y ninguna alteración del listener ganador.
- No se modifica `src/atlas/platform_admin_ipc.py`, el handler, el contrato `atlas-admin/1`, el runtime ni la autoridad SQLite.
- No se ejecutan pruebas, compilaciones ni workflows desde GitHub. La validación será realizada por el propietario en Debian.
- La aceptación del diseño no selecciona A como transporte de producción ni autoriza listener persistente, daemon, systemd, cambios del host, usuarios/grupos, privilegios, acceso SQLite, mutaciones administrativas o despliegue.

**Siguiente paso:** preparar la implementación aislada del probe A-IPC-01 en una rama separada; después revisar el diff y entregar comandos exactos para validación local.


### 16.12 Implementación del probe A-IPC-01 — 2026-11-20

Se preparó la implementación experimental en la rama separada `experiment/a-ipc-01-private-unix-listener-probe`, basada en el HEAD documental `d7a14302061e1cfc52df5097a42d65bd4ba482bb` de `design/isolated-private-unix-listener-probe`. La rama no se ha integrado ni se ha abierto PR; `main` permanece intacta.

Archivos añadidos:
- `tests/integration/private_unix_listener/run_probe.py`: entrypoint opt-in, sandbox por escenario, comprobaciones de propiedad y modos, colisiones, lifecycle, ping, peer credentials, fallos de transporte, límites acotados y carrera concurrente de dos binds. Emite JSON con clasificación por escenario, observaciones de peer y cleanup.
- `tests/integration/private_unix_listener/README.md`: alcance, comando local, interpretación de resultados y límites.

Escenarios implementados: A01–A08 y A10–A16. A09 (UID distinto) queda SKIP deliberado: el runner no cambia UID/GID, no usa sudo ni crea identidades. Por ello, aunque los demás escenarios pasen, el resultado general será INCOMPLETE. A14 usa un harness de prueba con máximo dos workers y backlog ocho; esos valores no son política de producción.

El runner importa el handler actual y ejecuta únicamente `authority.ping`. No modifica `src/atlas/platform_admin_ipc.py`, el contrato, runtime, autoridad SQLite ni servicios. No instala ni invoca systemd. Usa directorios temporales `0700`, sockets `0600`, no realiza unlink preventivo y limita cleanup a identidades registradas; el límite TOCTOU permanece documentado.

Comando para el propietario desde la raíz del checkout, sin sudo:

```bash
PYTHONPATH=src python tests/integration/private_unix_listener/run_probe.py
```

**Revisión y validación:** se realizó revisión manual del código y del diff en GitHub. No se han ejecutado pruebas, compilaciones ni workflows desde GitHub y no existe evidencia local aún. El propietario debe ejecutar el comando en Debian; el JSON completo y el commit exacto serán la evidencia. No declarar PASS si A09 permanece omitido.

**No autorizado:** listener persistente, daemon, systemd, cambios de host, usuarios/grupos, permisos, privilegios, acceso SQLite, operaciones administrativas o despliegue. La alternativa A sigue siendo candidata experimental, no transporte aprobado.


### Revisión estática A-IPC-01 — 2026-11-20

La inspección de `run_probe.py`, README, diseño y `src/atlas/platform_admin_ipc.py` confirmó que el experimento solo invoca `authority.ping` y no modifica handler, contrato, SQLite, runtime ni servicios. Se detectó una condición potencialmente no determinista en A14 y se corrigió: el harness ahora mantiene los workers admitidos en una compuerta temporal hasta observar la saturación, comprueba que los dos slots estén ocupados y registra excepciones inesperadas. La compuerta tiene un timeout acotado por `MAX_ACCEPT_WAIT_SECONDS` y se libera durante el cierre del harness.

**HEAD revisado:** `909d658e5ba177941f46b87a50c891869e5ca6d7`. **Validación:** pendiente; no se ejecutaron pruebas ni compilaciones. El propietario debe actualizar Debian, inspeccionar el diff y ejecutar el probe manualmente sin sudo. A09 seguirá SKIP deliberado, por lo que el resultado sin otros fallos será INCOMPLETE.


### Resultado de ejecución local A-IPC-01 — 2026-11-20

El propietario ejecutó manualmente, sin sudo, el comando opt-in desde Debian:

```bash
PYTHONPATH=src python tests/integration/private_unix_listener/run_probe.py
```

Evidencia del JSON comunicado:
- Checkout: `314e7395fbc972f8b9ab4a10dd800e85c11c7b59`; Debian kernel `6.12.117+deb13-amd64`; Python `3.13.5`; UID efectivo `1000`.
- Resultado global: `INCOMPLETE`, duración `0.876 s`; cleanup: `empty sandbox root removed`.
- **15 PASS:** A01–A08 y A10–A16. **A09 SKIP:** no se intentó una conexión desde un UID diferente porque el probe no cambia credenciales, no usa sudo y no presupone una segunda identidad. No hubo escenarios FAIL.
- A01 observó directorio `0700` (448 decimal) y socket `0600` (384 decimal). Las colisiones A02–A05 preservaron los objetos; A06 conservó el pathname sustituto y A07 eliminó el socket propio sin sustitución.
- A08/A10 observaron credenciales del peer desde el kernel (PID 3751, UID/GID 1000) y completaron el ping permitido.
- A14: máximo activo 2, seis conexiones rechazadas, ocho manejadas y cero activas tras recuperación.
- A16: dos binds concurrentes, exactamente un ganador; el listener ganador siguió operativo.

**Interpretación:** la ejecución respalda los invariantes experimentales cubiertos para un único UID y el harness temporal. No demuestra rechazo multi-UID (A09), autorización completa, separación real de privilegios, resistencia frente a root/procesos del mismo UID, lifecycle de servicio persistente, integración con systemd/SQLite ni idoneidad para producción. El resultado debe conservarse como `INCOMPLETE`, nunca reclasificarse como PASS.

**Siguiente paso:** revisión estática de los resultados y decidir si se puede preparar un mecanismo seguro, separado y explícito para probar A09 sin modificar credenciales ni host desde el runner. No implementar ni desplegar listener persistente ni seleccionar A como transporte de producción sin una decisión posterior del propietario. No se ejecutaron pruebas, compilaciones ni workflows desde GitHub.


### Revisión de capas A09 — DAC frente a autorización SO_PEERCRED (2026-11-21)

La revisión estática de A-IPC-01 identificó que el A09 original mezclaba dos controles diferentes:

- **A09a — DAC del endpoint candidato:** conservar directorio 0700 y socket 0600; un cliente de UID distinto debe ser bloqueado por el filesystem antes de que el listener acepte la conexión. Este resultado demuestra aislamiento de pathname, no autorización de aplicación.
- **A09b — autorización SO_PEERCRED:** requiere un fixture temporal distinto, deliberadamente conectable por el UID externo (por ejemplo, directorio 0711 y socket 0666). El handler debe obtener las credenciales reales del kernel y rechazar el UID no permitido con UNAUTHORIZED_PEER, sin respuesta de protocolo. Los permisos del fixture nunca se aplican al endpoint candidato.
- Ambos escenarios requieren una identidad no privilegiada preexistente y un cliente lanzado externamente. El runner no crea usuarios, cambia UID/GID, usa sudo ni modifica el host.
- La implementación actual no cubre A09a ni A09b. El resultado reportado de 15 PASS + A09 SKIP sigue siendo INCOMPLETE y no se reclasifica.
- Esta actualización es de diseño/documentación únicamente. No modifica runner, handler, contrato, runtime, SQLite, servicios ni configuración del host. No se ejecutaron pruebas, compilaciones ni workflows desde GitHub.

Referencias: [diseño A-IPC-01](design/local-authority-admin-private-unix-listener-probe.md) y [README del probe](../tests/integration/private_unix_listener/README.md).


#### A09 fixture topology and execution prerequisite

Static review found an additional DAC constraint: an A09b fixture with mode 0711 cannot be nested beneath the probe's private root 0700, because traversal is denied at the parent. The fixture must be a separate sibling directory directly under a verified shared sticky temporary parent (for example /tmp), with fixture mode 0711 and socket mode 0666. The private sandbox and candidate endpoint retain their original modes. Both A09 checks require a second, already-authenticated ordinary-user session under a distinct pre-existing UID; no sudo/su/runuser/setuid or account creation is allowed. This topology and orchestration are design requirements only; runner implementation and validation remain pending.


## A09 — identidad temporal multi-UID provisionada (2026-11-20)

El propietario autorizó expresamente crear una identidad temporal dedicada para proporcionar un peer real con UID distinto en A09a/A09b. La cuenta y el grupo ya fueron creados por el propietario y su salida de verificación se revisó en esta conversación.

**Identidad verificada**
- Cuenta atlas-a09-test: UID 1001, GID primario 984, shell /bin/bash.
- Grupo dedicado atlas-a09-test; id muestra únicamente el grupo primario dedicado.
- Contraseña bloqueada (passwd -S: L).
- HOME /var/lib/atlas-a09-test, propietario/grupo atlas-a09-test, modo 0700.
- UID 1001 es distinto del runner (greed, UID 1000). Preflight posterior comunicado por el propietario: `ps -u atlas-a09-test` sin procesos; `loginctl show-user` informa que UID 1001 no está conectado ni tiene linger; `user@1001.service` está `inactive`; no existe `/var/lib/systemd/linger/atlas-a09-test`; `sudo -l -U atlas-a09-test` confirma que no puede usar sudo. Esto no demuestra ausencia de cualquier unidad de sistema externa que pudiera referenciar la cuenta.

**SSH y red**
- Configuración efectiva: public-key sí; password sí; keyboard-interactive no; usepam sí; strictmodes sí; permituserenvironment no. X11, TCP y agent forwarding aparecen habilitados globalmente.
- sshd escucha en 0.0.0.0:22 y [::]:22. El ruleset nftables reportado muestra INPUT ACCEPT para IPv4 e IPv6; no afirmar que SSH esté limitado globalmente a loopback.
- Fingerprint ED25519 presentado por 127.0.0.1 coincide con la host key local inspeccionada: SHA256:txiDPT+/ldcIwnN6BPotbeL7QsofAieAeqF3GKMa9xI.
- SSH/PAM/firewall no fueron modificados. No se ha generado ni instalado clave, ni probado login SSH. Si se aprueba esa fase, la clave deberá tener restrict, from=127.0.0.1 y comando forzado; esto limita la clave de prueba, no el daemon global.

**Puertas pendientes**
- La fase de creación de cuenta/grupo/HOME está completada; su autorización no se extiende a instalación de clave, sesión SSH ni A09.
- Instalar clave Ed25519 y probar un comando fijo SSH requiere aprobación explícita separada.
- La coordinación cliente/runner de A09a/A09b aún requiere diseño, revisión estática e implementación aprobada. A09a/A09b siguen SKIP/no validados; el último resultado del probe continúa 15 PASS, A09 SKIP, 0 FAIL, global INCOMPLETE.
- Eliminar cuenta/grupo/HOME al finalizar también requerirá aprobación explícita separada.
- No se ejecutaron pruebas, compilaciones ni workflows desde GitHub. main permanece intacta, no hay PR abierto y ningún transporte IPC está aprobado para producción.


## A09 — SSH restringido confirmado y coordinación diseñada (2026-11-21)

El propietario confirmó que la clave Ed25519 temporal está instalada en `atlas-a09-test` con opciones `from="127.0.0.1",restrict` y comando forzado `/usr/bin/id -u`. La conexión SSH local a `127.0.0.1:22`, con identidad explícita, autenticación solo por clave, verificación estricta de host key ED25519 y sin PTY, devolvió `1001`. Esto confirma autenticación de la cuenta UID 1001; no ejecuta A09a ni A09b.

La clave privada permanece en `/run/user/1000/atlas-a09.IG1QPj/id_ed25519`, dentro del runtime privado del propietario; no se añadió a GitHub. La clave cliente tiene fingerprint `SHA256:aUAfFBWJfzoPUX9eErhAfltPrKPWTt7OtFQCa4m5oE4`. El archivo temporal known_hosts `/tmp/tmp.htQpm2wvEm` es propiedad de greed, modo 0600. La host key ED25519 de loopback coincide con `SHA256:txiDPT+/ldcIwnN6BPotbeL7QsofAieAeqF3GKMa9xI`. No se modificaron sshd_config, PAM ni firewall; sshd sigue escuchando en todas las interfaces según el preflight anterior.

Se documentó una propuesta de coordinación en la sección 16 de [A-IPC-01](design/local-authority-admin-private-unix-listener-probe.md): el runner UID 1000 orquesta un proceso SSH local y un helper remoto fijo ejecutado por sshd como UID 1001; stdin/stdout transportan un esquema JSON acotado, sin shell ni órdenes arbitrarias. A09a conserva 0700/0600 y verifica EACCES antes de accept. A09b usa fixture temporal independiente hermano bajo /tmp sticky, con 0711/0666 solo para el fixture, y exige rechazo del handler real por UNAUTHORIZED_PEER antes de recvmsg y sin bytes de respuesta.

**Estado en aquella actualización:** diseño solamente. Esa nota histórica queda supersedida por la implementación publicada posteriormente en esta rama. El helper/runner A09a/A09b ya están implementados, pero no ejecutados ni validados. La clave todavía fuerza `/usr/bin/id -u`; sustituirlo por el helper fijo requiere autorización explícita específica para modificar `authorized_keys`. El resultado anterior del probe permanece 15 PASS, A09 SKIP, 0 FAIL, global INCOMPLETE. `main` permanece intacta; no hay PR ni transporte de producción aprobado.


## A09 — implementación del helper/runner en rama experimental (2026-11-21)

La rama `experiment/a-ipc-01-private-unix-listener-probe` ahora contiene:

- `tests/integration/private_unix_listener/a09_ssh_client.py`: helper remoto fijo, stdlib-only, entrada JSON acotada, escenarios permitidos A09a/A09b, sin shell arbitraria, sin cambio UID/GID y sin acceso al checkout.
- `tests/integration/private_unix_listener/run_probe.py`: orquestación de SSH local con clave explícita, `IdentityAgent=none`, autenticación pública únicamente, host key ED25519 fijada y estricta, sin PTY/forwarding/proxy/multiplexación; A09a/A09b separados y opt-in deshabilitado por defecto.
- A09a exige `EACCES` del cliente UID externo, ningún accept y preservación del endpoint candidato 0700/0600.
- A09b utiliza fixture independiente directamente bajo `/tmp` sticky, directorio 0711/socket 0666, compara SO_PEERCRED PID/UID/GID con el helper remoto, exige rechazo real `UNAUTHORIZED_PEER` y cero bytes de respuesta.
- Helper temporal `/tmp/atlas-a09-client.py` creado con `O_EXCL`, modo 0644 y cleanup condicionado por inode/owner/mode. Si el archivo ya existe, no se sobrescribe.
- El opt-in requiere `--enable-a09`, paths de clave/known_hosts y dos confirmaciones explícitas: `--a09-forced-command-confirmed` y `--a09-shell-startup-reviewed`.

**Host todavía no preparado para A09:** la clave instalada en `authorized_keys` sigue forzando `/usr/bin/id -u`; el helper espera `/usr/bin/python3 -I /tmp/atlas-a09-client.py`. No se cambió `authorized_keys`; hacerlo requiere autorización explícita específica. También falta inspección read-only de `.bashrc`, `.bash_profile`, `.profile` y comportamiento del shell de `atlas-a09-test`. No ejecutar A09 antes de completar ambas puertas y recibir autorización independiente de ejecución.

**Estado de validación:** implementación de código no ejecutada; no se ejecutaron pruebas, compilaciones ni workflows desde GitHub. La evidencia previa del runner sigue 15 PASS + A09 SKIP + 0 FAIL, global INCOMPLETE. La implementación nueva no cambia esa clasificación. `main` intacta, sin PR, sin transporte de producción aprobado. No modificar SSH/PAM/firewall, handler, contrato, runtime, SQLite, systemd o servicios.


## A09 — revisión estática completada (2026-11-21)

Se completó la revisión estática en GitHub del helper y runner A09a/A09b. Se revisaron las acciones cerradas del helper, validación de path shape, canal JSON acotado, SSH con clave/host key explícitas y agente desactivado, autenticación pública únicamente, límites de salida/tiempo, comparación de PID/UID/GID SO_PEERCRED, rechazo real del handler y cleanup por identidad. La revisión no valida la configuración SSH del host ni reemplaza pruebas Debian.

No se ejecutaron pruebas, compilaciones ni workflows. A09a/A09b permanecen sin validar. La clave instalada aún fuerza `/usr/bin/id -u`; `authorized_keys` no se ha modificado. Falta inspección read-only del shell startup y aprobación explícita específica para el cambio de comando forzado, más autorización independiente para ejecutar A09.


## Actualización de estado A-IPC-01 — 2026-11-21

**La evidencia anterior de 15 PASS + A09 SKIP / INCOMPLETE queda supersedida para el commit experimental más reciente** por una ejecución opt-in completa comunicada por el propietario:

- Rama: `experiment/a-ipc-01-private-unix-listener-probe`.
- Commit probado: `1d5bdb122a8480c36b445be7dd961b93806de74b`.
- Debian 13; kernel `6.12.117+deb13-amd64`; Python `3.13.5`; runner UID 1000.
- Peer temporal `atlas-a09-test`: UID 1001, GID 984.
- Resultado: `overall=PASS`; A01–A16: 16 PASS, 0 SKIP, 0 FAIL; duración 1.72 s.
- Cleanup: `empty sandbox root removed`.
- A09a: UID 1001 obtuvo `EACCES` (errno 13) al conectar al endpoint candidato; cero conexiones aceptadas; directorio 0700/socket 0600 preservados.
- A09b: el handler real rechazó al peer UID 1001 con `UNAUTHORIZED_PEER`; solicitud ping de 122 bytes enviada; cero bytes de respuesta; cierre observado por reset. Fixture independiente 0711/0666.
- A14: `peak_active=2`, `rejected_connections=6`, `handled_connections=8`, `active_after_recovery=0`.
- A16: exactamente un ganador en los dos binds simultáneos; listener ganador operativo.

Registro completo y límites: [docs/status-aipc01-validation-2026-11-21.md](status-aipc01-validation-2026-11-21.md). README del runner actualizado en `tests/integration/private_unix_listener/README.md`.

**Interpretación:** A-IPC-01 está validado como probe experimental para el commit y entorno indicados. No selecciona transporte de producción ni autoriza listener persistente, daemon, systemd, cambios operativos adicionales, acceso SQLite, separación de privilegios, operaciones administrativas mutantes o despliegue. No demuestra resistencia frente a root/capabilities ni procesos maliciosos del mismo UID.

El propietario informó que actualizó únicamente la entrada temporal de `authorized_keys` para forzar `/usr/bin/python3 -I /tmp/atlas-a09-client.py`, conservando `from="127.0.0.1",restrict`, la clave y modo 0600; creó respaldo. Los archivos de inicio fueron revisados de forma read-only. No se reportaron cambios en sshd_config, PAM ni firewall. No asumir que la identidad temporal, clave, respaldo o artefactos temporales ya fueron eliminados.

La validación fue ejecutada por el propietario en Debian. No se ejecutaron pruebas, compilaciones ni workflows desde GitHub. `main` no se modificó; no se creó PR ni se seleccionó transporte de producción.


## Decisiones de diseño — identidad cliente y rutas IPC (2026-11-21)

El propietario confirmó que el frontend administrativo debe ejecutarse con **EUID 0**. La política de diseño para el listener alternativo A queda fijada en `client_uids={0}`: el frontend valida su EUID antes de conectar, el servicio valida `SO_PEERCRED.uid == 0` antes de leer, y el frontend valida el UID de `atlas-runtime` antes de enviar cualquier byte. Esto identifica dominios UID, no un ejecutable concreto. El entrypoint IPC real aún no existe/revisado, por lo que la decisión no equivale a evidencia operativa.

Se publicó `docs/design/local-authority-admin-private-listener-path-resolution.md`, que especifica resolución de todos los componentes desde `/` mediante descriptores y `openat`/`dir_fd`, `O_DIRECTORY|O_NOFOLLOW`, validación `fstat`, lectura de configuración desde descriptor y cleanup relativo. A-THREAT-06 queda especificado a nivel de diseño, pero no cerrado: el pathname de `bind()` no admite `dir_fd` en la API Python estándar y falta probar la correspondencia entre directorio validado y ruta usada por bind. La ventana TOCTOU de unlink permanece; bajo TCB-1 se confía en los procesos de `atlas-runtime` y root, mientras UIDs externos deben quedar excluidos por ownership/modos.

Siguiente trabajo: resolver el método seguro de bind/pathname, definir recuperación manual de socket stale (A-THREAT-05) y preparar un probe aislado de resolución de rutas/autenticación mutua. No modificar handler, contrato, runtime, SQLite ni host; no crear listener persistente, usuarios, grupos, permisos, servicios o archivos `/etc`. No se ejecutaron pruebas, compilaciones ni workflows; `main` permanece intacta y no hay PR.


### Investigación de bind AF_UNIX anclado a descriptor (2026-11-21)

La API estándar de Python no expone `bindat()`/`dir_fd` para AF_UNIX. Se investigó un candidato Linux procfs: la biblioteca abierta `sockat` documenta un bind mediante `/proc/self/fd/<D-fd>/R/<socket-name>` (directorio temporal privado `D` más symlink `R` al directorio endpoint) y connect mediante `/proc/self/fd/<endpoint-dir-fd>/<socket-name>`. La dirección devuelta por `getsockname()` puede ser la forma procfs temporal, no la ruta canónica. Este patrón es referencia técnica, no dependencia ni aprobación.

El diseño Atlas propone probarlo de forma aislada: D bajo directorio privado Atlas, R único, bind corto a través de procfs, verificación del socket por descriptor endpoint, cleanup de D/R y connect desde otro proceso mediante descriptor. Debe fallar cerrado si procfs no está disponible o cualquier identidad no coincide. Falta demostrar semántica en Debian/kernel objetivo y tratar artefactos ante crash. Referencias: Linux `unix(7)` y documentación `sockat` 0.4.1.


### Recuperación manual de socket residual (A-THREAT-05) — 2026-11-21

Se publicó `docs/design/local-authority-admin-private-listener-stale-recovery.md`. Define un procedimiento manual, no automático: servicio detenido, ausencia de procesos que retengan el listener, inspección de tablas AF_UNIX en todos los network namespaces visibles mediante `/proc/<pid>/net/unix`, validación del socket filesystem por descriptor y confirmación humana específica antes de `unlinkat`. No se usa `connect()` como prueba de liveness. Cualquier evidencia incompleta obliga a dejar el objeto intacto.

A-THREAT-05 sigue abierto hasta validar el procedimiento en un sandbox, especialmente la enumeración de namespaces y la correlación con el pathname canónico. El diseño presupone que cliente y servicio comparten network namespace y que el descriptor listener no se hereda ni se pasa mediante SCM_RIGHTS. Si se adopta el bind procfs experimental, la recuperación debe revisarse porque la ruta registrada por el kernel puede no ser el pathname canónico.

**Baseline de rutas:** bajo TCB-1, el bind pathname absoluto canónico después de validar toda la cadena y demostrar que UIDs externos no pueden escribir en ningún ancestro es el baseline más simple. El candidato procfs se conserva como alternativa experimental, no requisito; añade complejidad de observabilidad y recuperación. No hay código ni cambios de host.


### Presupuesto de recursos del listener — A-THREAT-07 (2026-11-21)

Se publicó `docs/design/local-authority-admin-private-listener-resource-budget.md`. Revisión del handler: request 16 KiB, response 64 KiB, JSON depth 16, read/write timeout por defecto 5 s cada uno y máximo configurable 60 s por timeout individual; no existe deadline global ni accept loop. A14 usa 2 workers/backlog 8 solo en el harness.

Perfil aprobado por el propietario para probes aislados: 4 conexiones/workers fijos, backlog 8, sin cola de aplicación, 5 s read/write, 15 s deadline global y `RLIMIT_NOFILE=64`. No equivale a configuración de producción. Mutaciones SQLite deben serializarse; operaciones largas no deben retener una conexión IPC y necesitan identificador/status. Memoria/CPU/TasksMax/shutdown e inventario real de FDs quedan pendientes.

A-THREAT-07 permanece abierto hasta implementar y validar el probe aislado; no se modificó handler ni se ejecutaron pruebas/workflows.


## A-IPC-02 — autenticación mutua y capacidad, primera iteración (2026-11-21)

Se añadió `tests/integration/private_unix_listener/run_mutual_auth_capacity_probe.py`, runner separado de A-IPC-01. Es un harness temporal, no un servicio ni listener de Atlas.

Cobertura implementada (revisión estática; todavía no ejecutada):
- Cliente con EUID 0 obtiene `SO_PEERCRED` y verifica UID esperado del servidor antes de enviar `authority.ping`; frente a un servidor bajo UID alternativo cierra sin enviar bytes.
- Servidor fixture obtiene credenciales kernel antes de `recv`; acepta UID 0 y rechaza peer alternativo sin leer ni responder.
- Procesos hijos usan credenciales reales/effective/saved numéricas y grupos suplementarios vacíos. El servicio limita `RLIMIT_NOFILE` a 64.
- Pool fijo de cuatro workers con semáforo antes de accept; prueba estructural de cuatro slots ocupados, quinta conexión pendiente y recuperación al liberar un slot.
- Configura backlog 8, timeouts read/write 5 s y deadline global 15 s. No declara validados sus comportamientos adversariales todavía.

El runner requiere root directo dentro de VM desechable, cuatro IDs numéricos reservados exclusivamente para fixtures y dos confirmaciones explícitas. No crea usuarios/grupos, no cambia configuración del host y no invoca sudo/su. Usa un sandbox privado 0700 y una raíz de traversal 0711 root-owned/no-writable-by-group-or-other para que el peer de UID alternativo alcance el socket de fixture. Staging temporal de script/módulo con permisos de solo lectura permite ejecución tras reducir UID. La limpieza comprueba identidad del socket; si detecta sustitución o no puede parar un proceso, conserva sandbox y falla.

Escenarios implementados: MA-01, MA-02, MA-04, MA-05, CP-01 y CP-04. El runner marca explícitamente INCOMPLETE los escenarios no implementados (EUID negativo, configuración, variantes de transporte, saturación exacta de backlog, deadlines adversariales, excepciones, límites JSON/payload y FD accounting). El overall no puede ser PASS todavía.

**Estado actual:** código y documentación actualizados en la rama experimental, revisión estática solamente. No se ejecutaron pruebas, compilaciones ni workflows. El propietario debe revisar el diff y ejecutar el runner únicamente en VM desechable, nunca en el servidor Debian de producción. A-THREAT-01 y A-THREAT-07 siguen abiertos hasta validar y completar cobertura. No se modifica handler, contrato, SQLite, host, `main` ni PR; no se aprueba listener persistente ni despliegue.


## A-IPC-02 — actualización posterior (2026-11-21)

Validación del propietario en `Atlas-VM-test`, commit
`069dbb9520f9e640955d9122f3a8012b2f55ba1a`, Debian 13, kernel
`6.12.117+deb13-amd64`, Python 3.13.5, EUID 0, fixtures 2005/2005 y
2006/2006:
- MA-01..MA-05 PASS; MA-03 rechazó EUID 2006 antes de connect y el servidor
  no observó conexión.
- CP-01/CP-04 PASS; máximo 4 workers y 0 activos tras recuperación.
- Backlog 8 configurado, no saturado.
- Overall INCOMPLETE; 1.339 s; cleanup de sandboxes `/run` completado.

MA-06 se añadió después en `9a8380eb4a4051763699b7c07c3ad9dfcf1eeccd`:
el probe envía claims de identidad `uid/gid/pid` como campos adicionales
del envelope y exige que el decoder los rechace como `INVALID_REQUEST`;
SO_PEERCRED sigue siendo la fuente de identidad. MA-06 está implementado,
pendiente de ejecución local. No atribuirle PASS basándose en el commit
anterior.

Próximo paso: ejecutar el nuevo commit solo en `Atlas-VM-test`; nunca en
`greed` de producción. El probe permanece INCOMPLETE y no autoriza
transporte persistente ni despliegue.



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


## A-IPC-02 — implementación MA-07/MA-08 (2026-11-21)

El runner incorpora `probe_config.py`, código temporal exclusivo de `tests/integration/private_unix_listener/`. Su gramática cerrada `clave=valor` es deliberadamente un formato de fixture, no una decisión para producción. La carga usa un descriptor de directorio del sandbox privado y valida archivo regular, root:root, modo 0644, hardlink único y tamaño máximo. MA-07 cubre archivo ausente, duplicados, claves desconocidas/ausentes, identidad alterada, symlink, FIFO, owner/mode inseguros, tamaño excesivo y hardlink. MA-08 comprueba que el reemplazo atómico del archivo no modifica el snapshot congelado en memoria.

La prueba no lee ni crea `/etc/atlas/admin-ipc.conf`, no cambia el handler y no implementa el recorrido de ancestros desde `/`; ese recorrido sigue siendo una etapa PA separada. MA-07/08 están implementados, pero **pendientes de ejecución del propietario** en `Atlas-VM-test`.

## A-IPC-02 — validación MA-07/MA-08 por el propietario (2026-11-21)

Evidencia recibida de `Atlas-VM-test`, Debian 13, kernel `6.12.117+deb13-amd64`, Python 3.13.5, EUID 0 real, fixtures SERVICE `2005/2005` y OTHER `2006/2006`, commit `585dd3d979bc1b800550e4b9c79c382b22cf1f6c`:

- MA-01..MA-08: PASS; MA-01..06 agrupados en el reporte, MA-07 y MA-08 reportados individualmente.
- MA-07: configuración válida aceptada (`client_uids=[0]`); 11 variantes inválidas rechazadas, incluidas symlink, FIFO, owner/mode incorrectos, hardlink y archivo oversized.
- MA-08: reemplazo atómico de la configuración no alteró el snapshot ya cargado; dataclass frozen y tuple inmutables.
- CP-01/CP-04: PASS; máximo 4 workers activos y recuperación a 0. Backlog 8 configurado, no saturado.
- Duración 1.497 s; cleanup de los dos sandboxes `/run` confirmado; cero filas FAIL; global INCOMPLETE.

La evidencia solo aplica al commit indicado. Permanecen MA-09..MA-10 y CP-02..CP-03/CP-05..CP-12. No implica configuración de producción, path-walk completo, listener persistente ni despliegue. Próximo paso: revisar diseño/runner e implementar MA-09/MA-10 sin ampliar el alcance a código productivo.

## A-IPC-02 — MA-09/MA-10 implementados (2026-11-21)

Commit `f41df94d0f87d288bfc7e3df45c66295fa19d570` añade escenarios del handler real:

- MA-09: cierre de la dirección de escritura del peer autorizado antes de enviar una petición; se exige `PEER_DISCONNECTED`, cero bytes de respuesta y ninguna petición aceptada.
- MA-10: AF_UNIX/SOCK_STREAM y AF_INET/SOCK_STREAM son rechazados con `INVALID_REQUEST` antes de consumir un paquete ping encolado; se comprueba con `MSG_PEEK` y ausencia de respuesta.
- La implementación fue revisada estáticamente; el propietario aún debe ejecutar el runner. No se ejecutaron pruebas/builds/workflows desde GitHub.
- MA-01..MA-08 y CP-01/04 conservan evidencia de propietario únicamente sobre `585dd3d`. No se atribuye PASS al nuevo commit hasta recibir el resultado local.
- CP-02/03 y CP-05..12 permanecen pendientes; global INCOMPLETE.


## Continuación A-IPC-02 — CP-02/CP-03 (2026-11-21)

La última ejecución comunicada por el propietario, sobre el checkout
`901c792cb723d920da4970ecce98ea7f871c4f85` (el JSON indicó
`commit: null`), obtuvo MA-01..MA-10 PASS y CP-01/CP-04 PASS en
`Atlas-VM-test`; global INCOMPLETE por los escenarios de capacidad restantes.
La evidencia confirma autenticación mutua root↔UID fixture, rechazo previo
a lectura/escritura cuando corresponde, MA-07/08, desconexión, transportes
no soportados y cuatro workers con recuperación a cero. No valida el cambio
posterior de backlog.

Commit actual de implementación CP-02/CP-03:
`1e213b2f7a254cd2718e644e415670dca08435f5`.
El runner:
- exige iproute2 `ss` como ejecutable regular root-owned, ejecutable y no
  escribible por grupo/otros;
- ocupa cuatro workers y crea ocho conexiones pendientes;
- observa `Recv-Q=8` y `Send-Q=8` en la fila LISTEN AF_UNIX;
- intenta una novena conexión no bloqueante y exige EAGAIN/EWOULDBLOCK;
- verifica que no aumenten cola ni conexiones aceptadas por la aplicación.

**Validación:** revisión estática del código y documentación; no se ejecutaron
pruebas, builds ni workflows desde GitHub. CP-02/CP-03 pendientes de
ejecución por el propietario en `Atlas-VM-test`. CP-05..CP-12 pendientes.
Siguiente paso único: ejecutar el runner actualizado en la VM desechable,
nunca en `greed` producción. No se autoriza listener persistente, systemd,
acceso SQLite, cambios de host ni despliegue.


### Seguimiento de CP-02/CP-03 — endurecimiento estático

Commit posterior: `67526c21a1edc2938b5caefb699aa6c6576c5b73`.
El preflight ya no valida únicamente el archivo ejecutable `ss`: resuelve
la ruta real, comprueba que el archivo sea root-owned y no escribible por
grupo/otros, y valida cada directorio ancestro hasta `/` con las mismas
restricciones de ownership/escritura. La ejecución usa la ruta resuelta.
Sigue pendiente que el propietario ejecute el runner en `Atlas-VM-test`;
no se ejecutaron pruebas desde GitHub.


### Corrección de revisión estática del preflight

En commit `4ab6a1b7762f4d45a745ea2c36f7289411a9c848` se declaró
explícitamente `global SS_BIN` dentro de `_preflight`; sin ello, la
asignación de la ruta resuelta habría sombreado el global y provocado
`UnboundLocalError`. La corrección fue inspeccionada en GitHub; no se
ejecutaron pruebas ni el probe. La validación local CP-02/CP-03 sigue pendiente.


## A-IPC-02 — resultado CP-02/CP-03 y ajuste (2026-11-21)

El propietario ejecutó `1ebf930a6559c3d6a81965f0f94c28ed8e6eef56`
como root en `Atlas-VM-test`. MA-01..MA-10 y CP-01/CP-04 PASS; CP-02/CP-03
falló porque connect_ex devolvió 0 después de observar Recv-Q=8/Send-Q=8.
Cleanup completado.

La inspección del código AF_UNIX de Linux encontró que el kernel evalúa
`skb_queue_len(...) > sk_max_ack_backlog`; en consecuencia `listen(8)`
admite una conexión pendiente adicional y el siguiente intento no bloqueante
debe ser rechazado. El runner se corrigió en commit
`634e19decce2322e94ca0d1fe410b259f23dcb67` para comprobar:
- ocho conexiones pendientes: Recv-Q=8, Send-Q=8;
- conexión novena admitida: Recv-Q=9, Send-Q=8;
- conexión décima rechazada con EAGAIN/EWOULDBLOCK;
- cola sin cambios y sin accepts/workers adicionales.

Esta es semántica de implementación Linux AF_UNIX, no garantía portable.
La corrección solo fue revisada estáticamente; requiere nueva ejecución del
propietario. CP-02/CP-03 no se consideran PASS. CP-05..CP-12 pendientes.


### Evidencia A-IPC-02 — CP-02/CP-03 (2026-11-21)

El propietario ejecutó `b5b0128e2646e41e3a2f927251c6fa6dafa897d7`: MA-01..MA-10, CP-01/04 y CP-02/03 PASS; overall INCOMPLETE por CP-05..12. Cola 8/8, novena conexión admitida 9/8, décima rechazada EAGAIN errno 11; sin accepts/workers extra y cleanup correcto. CP-05 queda bloqueado por aclaración: read timeout 5 s precede al deadline global 15 s para un peer silencioso.


### CP-05 / CP-06 — incremento implementado (2026-11-21)

- Runner: 59fafb801a31d7adf51a6598db78440255744321.
- CP-05 verifica que un peer autorizado que no envía datos sea cerrado por el read timeout de 5 s, no por el deadline global.
- CP-06 utiliza un servidor fixture separado y una espera controlada de 11 s entre accept/autenticación y read. La lectura debe recibir solo el tiempo restante del deadline global de 15 s desde accept (aprox. 4 s), y cerrar al alcanzarlo.
- La espera de 11 s es instrumentación test-only, no lógica productiva. El escenario no simula una escritura bloqueada ni demuestra una suma real de read+write; verifica que una fase posterior no reinicia el presupuesto global.
- Ambos escenarios están implementados, pendientes de ejecución del propietario. El global debe seguir INCOMPLETE hasta CP-07..CP-12.
- Diseño: docs/design/local-authority-admin-private-listener-mutual-auth-capacity-probe.md; instrucciones: tests/integration/private_unix_listener/README.md.


### A-IPC-02 — CP-05 / CP-06 validados por el propietario (2026-11-21)

Commit ejecutado: 0db262802ce30ec38a4ce52a4f5bfaa3081fc2b1. Entorno: Atlas-VM-test, Debian 13, kernel 6.12.117+deb13-amd64, Python 3.13.5, EUID 0; SERVICE 2005/2005, OTHER 2006/2006.

- MA-01..MA-10 y CP-01..CP-06: PASS.
- CP-05: timeout de lectura observado 5.002 s; deadline global no alcanzado; EOF y cero bytes de respuesta.
- CP-06: espera test-only 11 s; lectura inicia a 11.004 s con 3.996 s restantes; cierre a 15.006 s desde accept; EOF y cero bytes de respuesta.
- CP-02/03: Recv-Q 8 y 9; novena conexión admitida, décima EAGAIN errno 11; máximo cuatro workers.
- Cleanup correcto; duración 22.095 s.
- CP-07..CP-12 siguen pendientes; overall INCOMPLETE.
- CP-06 demuestra contabilidad del presupuesto global mediante instrumentación del harness, no simula trabajo productivo ni escritura bloqueada.


### CP-07 — excepción de worker implementada (2026-11-21)

- Runner commit: fbd4512d163b31e53b355280e636fb47cf8d66a9.
- Un servidor fixture dedicado inyecta una RuntimeError de un solo uso después de aceptar una conexión y entrar en el contexto del socket.
- El escenario exige EOF y cero bytes de respuesta en el peer fallido, evento worker_error, contador active=0, servidor aún vivo y una segunda petición authority.ping exitosa que vuelve a active=0.
- La secuencia comprueba el cierre del socket, liberación del slot por finally y continuidad del accept loop. La inyección es test-only; no modifica handler productivo.
- CP-07 implementado y revisado estáticamente; pendiente de ejecución del propietario. CP-08..CP-12 pendientes; overall INCOMPLETE.
