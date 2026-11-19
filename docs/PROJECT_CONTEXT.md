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
- **Pendiente obligatorio:** repetir en Debian la suite IPC específica y la suite completa después del último cambio. No declarar PR validado ni listo para integrar hasta recibir esos resultados.

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

**Esperar la validación del propietario en Debian sobre el HEAD exacto `9f3cf520639bb892b75fc59efedc7e490a94ee2a` de `work/authority-admin-protocol-contract-alignment`.**

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

El propietario debe compartir el comando exacto, número de tests, skips y resultado. Si hay fallos, inspeccionar y corregir en GitHub sobre la rama correspondiente; repetir validación local en Debian. No avanzar a listener/daemon, operaciones administrativas reales ni merge hasta cerrar esta validación y revisar el PR.

## 8. Fuentes que deben releerse al iniciar una sesión

Leer primero, desde la rama activa y directamente en GitHub:

1. `README.md` — visión y alcance general.
2. `docs/status-current.md` — estado canónico (verificar corte/HEAD porque puede estar atrasado respecto a main).
3. `docs/roadmap.md` y `docs/functional-test-roadmap.md` — secuencia de producto.
4. `docs/architecture.md` y `docs/functional-architecture-map.md` — composición y límites.
5. `docs/design/local-authority-storage-operational-contract.md` — contrato operativo de almacenamiento.
6. `docs/design/local-authority-administrative-operations-design.md` — diseño/catálogo de operaciones.
7. `docs/design/local-authority-admin-ipc-contract-audit.md` y `docs/design/local-authority-admin-ipc-prototype.md` — estado IPC actual.
8. `docs/design/local-authority-admin-listener-lifecycle.md` — lifecycle propuesto; no aprobado.
9. `docs/design/ME-D4J-sqlite-unit-of-work.md` — evolución y límites de UoW/Recovery Gate.
10. Documentos I3-2B/7B pertinentes cuando se trabaje sobre identidad, Platform Admin o lifecycle.

Al iniciar cada sesión, volver a consultar ramas, HEADs, PRs, comparación con base y contenido real de los documentos. Este archivo es una guía de contexto, no reemplaza los contratos normativos ni la inspección del estado vivo de GitHub.
