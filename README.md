# Atlas

Atlas es un entorno personal de asistencia, coordinación y automatización de proyectos. Su objetivo es permitir que el propietario consulte información, conserve contexto útil y delegue trabajo a componentes, agentes y herramientas sin entregarles autoridad ilimitada.

La visión de Atlas se apoya en estos principios:

- **Seguridad por defecto:** denegar cuando falten identidad, contexto, autorización o evidencia.
- **Mínimo privilegio:** cada actor recibe únicamente las capacidades necesarias.
- **Aislamiento:** separar propietarios, proyectos, entornos, memorias y consumidores.
- **Mediación:** las operaciones protegidas pasan por las fronteras responsables.
- **Trazabilidad:** correlacionar solicitudes, decisiones, cambios y resultados.
- **Recuperación verificable:** no reabrir operaciones protegidas a partir de datos estructurales no autenticados.
- **Portabilidad:** evitar que los dominios dependan innecesariamente de un proveedor o infraestructura concreta.
- **Control humano:** las decisiones sensibles y no delegables permanecen bajo control del propietario.

La autonomía de Atlas no equivale a autoridad. Comprender una solicitud, generar una respuesta o proponer un plan no autoriza ni ejecuta una operación.

> **Corte documental:** 19 de noviembre de 2026. Rama de trabajo revisada: `work/authority-admin-protocol-contract-alignment` (PR #28, Draft, sin merge). HEAD documental revisado antes de esta actualización: `4d8ba9d652cc8fa0174863ecfa3bdc656bf20a47`. La suite completa más reciente comunicada por el propietario en Debian ejecutó **1,583 pruebas — OK (1 skipped)**; esa ejecución no debe atribuirse al HEAD actual porque después se incorporó una corrección final del decoder para enteros JSON extremos. La nueva validación focalizada y completa de esa corrección sigue pendiente en Debian. Este README distingue implementación, evidencia local comunicada y capacidades no habilitadas. Un contrato, puerto, modelo o reducer no demuestra por sí solo que una capacidad esté habilitada en un runtime completo.

## Estado general del desarrollo

Atlas es software funcional en desarrollo incremental, no solamente un conjunto de contratos o un prototipo. Ya dispone de una experiencia conversacional local ejecutable, integración con Ollama y gestión durable de conversaciones, incluyendo administración, exportación, backup cifrado, verificación y restauración. La suite completa local ha sido ejecutada y aprobada. A la vez, Atlas todavía no es el entorno autónomo completo descrito por su visión. Consulta el [estado vigente del proyecto](docs/status-current.md).

| Área | Estado real |
|---|---|
| Assistant local y consola | **Funcional: consola, composición local y conversación con Ollama** |
| Integración con Ollama | **Implementada** |
| Contexto conversacional | **Persistente en SQLite; historial durable y proyección acotada al modelo** |
| AtlasCore | **Fachada de aplicación implementada; orquestación completa pendiente** |
| Identidad canónica y autenticación nativa | **Primitivas, persistencia y servicios USER/AGENT implementados; login operativo y bootstrap de producción pendientes** |
| Contexto de identidad verificada | **Servicios USER/AGENT y revalidación transaccional implementados; integración de clientes/runtime pendiente** |
| CAM y autorización | **Evaluación de Grants y flujos de renovación implementados parcialmente; no equivale a runtime protegido completo** |
| Delegación AGENT | **Identidad, binding, delegación del propietario, evidencia verificada y renovación delegada implementados; runtime AGENT no habilitado** |
| Project/Environment y Workspace | **Persistencia canónica, asociación lifecycle, registro Workspace y gate CAM read-only implementados; integración con consola pendiente** |
| Autoridad administrativa local IPC (`atlas-admin/1`) | **Contrato de siete operaciones y prototipo de `authority.ping`; seis operaciones no implementadas y denegadas. Listener persistente y despliegue no aprobados** |
| Memory Engine | **Dominio, Gateway, consistencia, journal, recuperación local y reducers implementados parcialmente** |
| Persistencia durable del contenido Memory | **Pendiente** |
| Forget de extremo a extremo | **Modelos y reducer implementados; adaptadores y ejecución completa pendientes** |
| Recovery Gate | **Adaptador SQLite gate-only implementado; autoridad protegida completa pendiente** |
| Project Manager y ciclo de vida operativo de proyectos | **Pendiente** |
| Skills Manager e instalación controlada de Skills | **Pendiente** |
| Agentes, Scheduler y ejecución de tareas | **Pendiente** |
| Aprobaciones, notificaciones y event collector completos | **Pendientes** |
| Runtime integrado de extremo a extremo | **Pendiente** |
| Memory Engine como producto/paquete independiente | **Diseño parcialmente desacoplado; independencia ejecutable no demostrada** |

## Desarrollo actual: autoridad, identidad y delegación

La consola local y las conversaciones persistentes siguen siendo funcionales. El desarrollo de autoridad incluye autenticación nativa, identidad verificada USER/AGENT, delegaciones del propietario, renovación delegada bajo CAM, lifecycle de asociaciones Project–Environment y el protocolo IPC administrativo local `atlas-admin/1`. En el IPC, el contrato normativo ya define siete operaciones y el prototipo implementa únicamente `authority.ping`; las otras seis siguen sin implementar y denegadas. El contrato IPC revisión 1.1 cierra documentalmente `operator_evidence`, la normalización de `reason`, las gramáticas, la serialización canónica de `plan_digest` y del digest de intención (§§9.11.1–9.11.6), los resultados exactos de las siete operaciones (§9.12) y el mapeo de códigos/estados (§10.4). Esto no habilita las seis operaciones aún no implementadas. La suite completa más reciente comunicada fue de 1,583 pruebas OK con una omitida, pero precede a la corrección final del decoder y no valida el HEAD actual. No se habilitan login de producción, endpoints protegidos, runtime AGENT, herramientas de consola ni ejecución privilegiada. Consulta el [estado vigente](docs/status-current.md), el [contrato IPC normativo](docs/contracts/local-authority-admin-ipc-atlas-admin-1.md), el [contexto de proyecto](docs/PROJECT_CONTEXT.md), el [plan funcional](docs/functional-test-roadmap.md), el [mapa de arquitectura](docs/functional-architecture-map.md) y la [hoja de ruta general](docs/roadmap.md).

## Documentación del proyecto

- [Estado vigente de Atlas](docs/status-current.md)
- [Plan de Atlas funcional de prueba](docs/functional-test-roadmap.md)
- [Mapa de composición funcional F0](docs/functional-architecture-map.md)
- [Atlas Workstation — entorno operativo aislado](docs/design/atlas-workstation.md)
- [Validador bootstrap LOCAL V1](tools/bootstrap-validator/README.md)
- [Observador bootstrap LOCAL V2](tools/bootstrap-observer/README.md)
- [Observador diagnóstico de cadena sudo V3](tools/bootstrap-chain-observer/README.md)
- [Diseño V1 del validador bootstrap](docs/design/local-bootstrap-validator-v1-design.md)
- [Diseño V2 del observador LOCAL de procesos](docs/design/local-bootstrap-observer-v2-design.md)
- [Diseño V3 del observador de cadena sudo](docs/design/local-bootstrap-chain-observer-v3-design.md)
- [Evaluación Candidate A/B y separación de privilegios](docs/design/local-bootstrap-candidate-evaluation-2026-11-16.md)
- [Contrato IPC administrativo local `atlas-admin/1`](docs/contracts/local-authority-admin-ipc-atlas-admin-1.md)
- [Contexto técnico vigente del proyecto](docs/PROJECT_CONTEXT.md)
- [Contrato de delegación verificada AGENT I3-2B](docs/design/verified-agent-delegation-contract-i3-2b.md)
- [Auditoría CAM de renovación delegada](docs/design/i3-2b-cam-renewal-integration-audit.md)
- [Auditoría de frontera lifecycle 7B.6A](docs/design/i3-2b-7b6a-lifecycle-write-boundary-audit.md)
- [Separación de capacidades lifecycle 7B.6B](docs/design/i3-2b-7b6b-lifecycle-write-capability-separation.md)
- [Hoja de ruta general por fases](docs/roadmap.md)
- [Fase 3 — Inteligencia y comportamiento seguro](docs/phase-3-intelligence.md)
- [Atlas Terminal](docs/terminal/README.md)
- [Hoja de ruta](docs/terminal/roadmap.md)
- [Gestión de conversaciones](docs/conversations.md)

## Arquitectura y componentes

### 1. Atlas Assistant y AtlasCore

**Implementado:**

- Modelos inmutables `AssistantRequest`, `AssistantResponse` y contexto asociado.
- Identificadores de solicitud, correlación y conversación.
- `AtlasCore` como fachada que crea solicitudes, delega el procesamiento y valida que la respuesta corresponda a la solicitud y contexto originales.
- Servicio `AssistantService` separado del proveedor generativo.
- Puerto LLM intercambiable y adaptador `OllamaProvider` para la API local `/api/chat`.
- Respuestas completas y streaming NDJSON.
- Validación del endpoint Ollama para limitarlo a loopback: `localhost`, `127.0.0.1` o `::1`.
- Consola local y composición mínima del Assistant.

El prompt del adaptador Ollama limita expresamente al modelo a generar texto conversacional: no dispone de herramientas ni debe afirmar que ejecutó acciones.

**Contexto conversacional actual:**

El flujo conversacional utiliza persistencia SQLite durable, independiente de la base de autoridad:

- Conversaciones y mensajes se conservan entre ejecuciones.
- Se recupera la conversación activa al iniciar Atlas.
- El historial se conserva íntegro en almacenamiento.
- La proyección enviada al modelo se limita a los últimos 8 turnos y a 2.000 caracteres por mensaje.
- Los turnos exitosos se incorporan al historial; las respuestas de tipo `ERROR` no se guardan como turnos exitosos.
- La administración incluye crear, listar, seleccionar, renombrar, cerrar y eliminar con confirmación.
- Se dispone de exportación JSON versionada, backup cifrado, verificación y restauración a una ruta nueva.

La ruta predeterminada de la base es `~/.local/state/atlas/conversations.sqlite3`. Los detalles de permisos y operaciones están en [docs/conversations.md](docs/conversations.md).

**Pendiente:**

- Conectar AtlasCore con los dominios operativos de Atlas.
- Incorporar identidad y contexto verificados en la composición real, no solo contexto local de consola.
- Integrar MemoryGateway de forma controlada, una vez que el runtime protegido de memoria esté completo.
- Convertir planes en solicitudes formales para Scheduler y componentes responsables.
- Incorporar herramientas únicamente mediante contratos, autorización y mediación explícitos.

### 2. Identity y autorización (CAM)

**Implementado en código:**

- Modelos de identidad, tipo, estado y revisión.
- Contratos de identidad canónica y de vinculación entre identidad y sujeto.
- Adaptador de compatibilidad de Atlas hacia el contrato neutral de identidad del dominio Memory.
- `SQLiteIdentityAuthority` para crear, consultar y cambiar el estado de la identidad canónica interna.
- Creación atómica del par `UserId`–`Identity(USER)`.
- Revisión compare-and-swap para cambios de estado; una identidad revocada es terminal.
- `AuthorizationEvaluator`, modelos de solicitudes, decisiones y Grants.
- `MemoryAuthorizationService` para autorizar lecturas sobre una memoria y versión concretas, usando metadatos, identidad y Grants confiables.
- `GrantManagementService` para emisión y coordinación de revocación.
- `GrantRenewalService` para solicitar, aprobar y rechazar renovaciones.
- Verificación y consumo de pruebas de revocación, coordinación de cambios de autoridad y reservas durables con idempotencia semántica.
- Contratos y pruebas de autorización, renovación, revocación y límites de acceso.

**Persistencia SQLite de identidad — referencia histórica v1–v6:**

- **v1–v3:** dominio local de consistencia, journal, checkpoints e identidad de append.
- **v4:** ledger durable de cambios de autoridad, invalidaciones y evidencia de recuperación.
- **v5:** relación canónica entre `UserId` interno e `Identity(USER)`.
- **v6:** integridad bidireccional de la relación USER mediante claves foráneas diferidas.

La migración v6 exige que una identidad USER tenga su registro canónico de usuario correspondiente y viceversa al confirmar la transacción. Las migraciones son consecutivas, inmutables y verificadas mediante checksum. El esquema evolucionó posteriormente con persistencia nativa de autenticación/identidad, delegación AGENT, renovaciones y lifecycle Project–Environment; el detalle vigente se registra en `docs/status-current.md` y los diseños de Cycle 3.2/I3-2B.

**Límites pendientes:**

- Login de usuario operativo y bootstrap inicial seguro para despliegue; las primitivas nativas actuales no constituyen por sí solas un flujo de acceso desplegado.
- Integración de `VerifiedIdentityContext` con clientes y operaciones protegidas de extremo a extremo.
- Completar las fronteras de autoridad y coordinación/fencing que aún no están implementadas.
- Integración verificada de Project/Environment, Workspace y CAM en el runtime real.
- Pruebas E2E de los límites de autorización en una composición desplegada.

La persistencia local de `UserId` e `Identity(USER)` no debe describirse como autenticación externa ni como identidad verificada completa.

### 3. Memory Engine

Memory Engine es el dominio con mayor desarrollo de infraestructura después de la base conversacional. Su diseño busca que pueda ser consumido por Atlas sin depender conceptualmente de Assistant, y que sus fronteras de persistencia, autorización, consistencia y recuperación sean explícitas.

#### 3.1 Dominio y contratos

**Implementado:**

- Modelos inmutables para `Memory`, `MemoryVersion`, `MemoryProposal`, scopes, clasificación, estados y procedencia.
- Ámbitos `PRIVATE` y `PROJECT`.
- Estados de versión `pending_review`, `approved`, `rejected`, `superseded` y `forgotten`.
- Clasificación por versión y referencias opacas de procedencia/evidencia.
- Validación de identificadores, fechas UTC, revisiones y relaciones entre modelos.
- Contexto de solicitud de memoria y contratos de autorización.
- Puertos para metadatos, contenido protegido, journal, checkpoints, recuperación, firma y autoridad.

Los modelos de dominio contienen un campo de contenido para una versión de memoria. Esto **no significa que exista persistencia durable del contenido**: los adaptadores SQLite actuales no guardan el contenido de Memory, embeddings ni snippets.

#### 3.2 MemoryGateway y lectura protegida

Existe `MemoryGatewayService`, que implementa una frontera de lectura protegida. El flujo del servicio coordina:

1. Solicitud de autorización CAM para la memoria y versión exactas.
2. Validación del snapshot de autorización, identidad, revisiones, contexto y expiración del Grant.
3. Admisión de lectura ante la autoridad de consistencia.
4. Obtención de un handle opaco condicionado a esa admisión.
5. Emisión mediante el punto de egress controlado.
6. Finalización, acknowledgements y reconciliación de la operación.

Gateway no devuelve un objeto `MemoryVersion` ni contenido crudo al consumidor: entrega una capacidad opaca que solo puede utilizarse mediante sus operaciones de emisión y finalización.

**Límite importante:** el servicio depende de puertos `ProtectedMemoryContentPort`, `ProtectedMemoryConsistencyPort` y de egress. La sesión interna que mantiene la capacidad de lectura reside en memoria del proceso. La presencia del servicio y de sus pruebas no demuestra que exista una composición durable de todos esos puertos en producción.

#### 3.3 Consistencia, journal y checkpoints

**Implementado:**

- Modelos de admisión de lectura, snapshots de autorización, revisiones de autoridad, invalidaciones, fencing, recibos de egress, acknowledgements y reconciliación.
- Journal de consistencia con transiciones tipadas, posiciones, secuencias y reducers.
- Append autenticado, control de posición, idempotencia y resolución de resultados inciertos.
- Checkpoints vinculados a posiciones exactas del journal.
- Proyección de checkpoints en filesystem mediante publicación inmutable y verificación por referencia de integridad.
- Firmante HMAC local a través de un proveedor explícito de claves.
- Verificador local de recuperación y política de confianza.
- Adaptadores que conectan el perfil local de recuperación con puertos neutrales.

La lectura estructural del journal es diagnóstica; no constituye por sí misma evidencia autenticada de recuperación.

#### 3.4 SQLite y unidad de trabajo

**Implementado:**

- `SQLiteDatabase` con WAL, claves foráneas activadas, `synchronous=FULL`, timeout configurable y conexiones por operación.
- `SQLiteUnitOfWork` para compartir una transacción entre adaptadores ligados a la misma instancia de base de datos.
- Migraciones consecutivas e inmutables con checksum.
- Journal SQLite, checkpoints, metadatos de consistencia y ledger de cambios de autoridad.
- Persistencia SQLite de identidad canónica interna.
- Adaptador SQLite del Recovery Gate.

La versión mínima requerida de SQLite es **3.26.0**.

El adaptador `LocalSQLiteRecoveryGateAdapter` implementa el ciclo del Recovery Gate y comparte la transacción con el journal. Su alcance es **gate-only**: no implementa por sí solo la autoridad protegida completa que debe serializar admisiones, invalidaciones, Forget, recuperación y egress dentro de una misma frontera transaccional.

#### 3.5 Forget y eliminación verificable

**Implementado:**

- Modelos de cierre de Forget y supresión lógica.
- Captura de admisiones afectadas, rutas y generaciones de fencing.
- `ForgetCoordinatorReducer` con estados de operación: cierre, supresión, inventario, purga, verificación, bloqueo y finalización.
- Modelos de inventario de destinos, intentos de eliminación y recibos de verificación.
- Tratamiento explícito de resultados desconocidos, destinos aún presentes, inventarios incompletos y evidencia contradictoria.
- Reglas para no declarar completado el olvido mientras falte evidencia requerida.

**No está implementado como flujo operativo completo:**

- Adaptadores concretos para enumerar y eliminar datos en cada destino (almacenamiento principal, versiones, índices, cachés, réplicas, backups, exports y copias operativas).
- Coordinación durable de todos esos destinos con la autoridad de consistencia.
- Integración atómica de Forget con admisiones, invalidación, egress y estado canónico.
- Una política completa de retención y su evidencia operativa.
- Un flujo completo de autorización directa, no delegable y verificada del propietario conectado a todos los pasos.

Por tanto, los modelos y reducers de Forget no permiten afirmar que Atlas ya pueda borrar de extremo a extremo todas las copias de una memoria.

#### 3.6 Qué falta para considerar terminado Memory Engine

- Persistencia canónica de `Memory`, `MemoryVersion`, `MemoryProposal` y sus metadatos/procedencia.
- Adaptadores durables de contenido y repositorios de memoria.
- Autoridad protegida común para `admit_read`, Recovery Gate, invalidaciones, Forget y egress.
- Egress con fencing y aceptación verificable en los receptores reales.
- Recuperación durable de sesiones/admisiones no terminales y reconciliación tras reinicios.
- Bootstrap autenticado y evidencia directa del propietario.
- Perfil ANCHORED con anti-rollback independiente; el perfil LOCAL no demuestra anti-rollback externo.
- Forget de extremo a extremo, incluyendo inventario y verificación de todos los destinos.
- Integración del Gateway con la conversación de AtlasCore.
- Pruebas de composición real y operación independiente sin depender de Atlas.

**El Recovery Gate debe permanecer cerrado** hasta completar bootstrap, autoridad compuesta, recuperación y validación. No debe abrirse ni modificarse manualmente mediante SQL.

### 4. Separación del Memory Engine

Hay trabajo real de desacoplamiento:

- Existe un espacio de dominio `atlas.memory` separado de la capa conversacional.
- Se definieron puertos neutrales para journal, consistencia, firma, checkpoints, recuperación, metadatos y lecturas protegidas.
- Algunos contratos genéricos evitan importar modelos concretos de Atlas, SQLite o el perfil local.
- Los adaptadores de infraestructura están separados de los modelos y servicios de dominio.

Pero Memory Engine **todavía no es un paquete o servicio independiente verificablemente ejecutable**:

- El código vive dentro del paquete Python `atlas`.
- Parte del dominio importa contratos y errores de `atlas.core`.
- La composición de dependencias sigue siendo responsabilidad del repositorio Atlas.
- No se ha demostrado bootstrap, persistencia, recuperación y operación completa sin Atlas.

La dirección arquitectónica es mantener Memory Engine como un núcleo independiente y hacer que Atlas sea uno de sus consumidores. Para afirmar que esa separación está terminada se necesita extraer o aislar el paquete, definir su contrato público y probarlo en un proceso/proyecto consumidor independiente.

### 5. Proactividad

Existe el modelo inmutable `ProactiveProposal`, que representa una propuesta vinculada a un propietario, una justificación, una acción sugerida y un contexto.

No existe todavía un motor proactivo completo: no hay ciclo operativo de observación, detección, planificación, priorización, aprobación, notificación y ejecución.

### 6. Áreas de Atlas aún no implementadas

El árbol de código actual no contiene implementaciones completas de los siguientes subsistemas previstos en la visión:

- **Project Manager:** registro operativo completo, ciclo de vida, aislamiento y gestión integral de recursos de proyectos.
- **Environment Manager:** gestión durable y composición de entornos por proyecto.
- **Skills Manager:** catálogo, procedencia, análisis de código/dependencias, permisos declarados, aprobación explícita, instalación controlada, aislamiento por riesgo, auditoría, actualización y desactivación/eliminación de Skills externas.
- **Agent Manager y agentes especializados:** ciclo de vida, capacidades, identidad, aislamiento y coordinación.
- **Scheduler:** admisión, colas, dependencias, ejecución y reconciliación de tareas.
- **Approval Manager:** flujo operativo de aprobación humana para acciones sensibles.
- **Event Collector y Notification Manager:** infraestructura integrada de eventos y notificaciones.
- **Runtime de herramientas:** invocación mediada y auditable de herramientas bajo autorización explícita.
- **Backup, manifest, restore y verification de Atlas:** ciclo completo de exportación, restauración, verificación y activación deliberada.

Los contratos y documentos de diseño pueden describir responsabilidades futuras, pero no sustituyen esas implementaciones.

## Seguridad y límites operativos

Las reglas que deben mantenerse en todas las fases son:

- Denegar por defecto y fallar cerrado ante contexto o evidencia incompletos.
- Separar identidad, autenticación y autorización.
- Autorizar cada operación sobre el recurso concreto.
- No conceder permisos por conocer identificadores.
- No permitir acceso entre propietarios o proyectos por defecto.
- No permitir que modelos, prompts, herramientas o Skills amplíen sus propios permisos.
- Separar propuesta, admisión, autorización y ejecución.
- No presentar un resultado desconocido como éxito.
- No reintentar automáticamente una operación cuyo resultado sea incierto sin reconciliarla primero.
- No abrir el Recovery Gate ni habilitar lecturas protegidas antes de completar sus controles.
- No restaurar automáticamente proyectos o Skills después de una recuperación.

La consola/Assistant actual no tiene acceso directo a archivos, SQL, shell, contenedores ni herramientas privilegiadas. Esta limitación es deliberada.

## Ejecución local

Desde la raíz del repositorio, en Debian/Linux, activa primero el entorno virtual del proyecto:

```bash
source .venv/bin/activate
python -m atlas
```

Si todavía no está instalado en el entorno activo:

```bash
python -m pip install -e .
atlas
```

Modo informativo sin proveedor LLM:

```bash
ATLAS_MODE=offline python -m atlas
```

Configuración principal:

- `ATLAS_MODEL`: tag del modelo local; predeterminado `gemma4:e2b`.
- `ATLAS_OLLAMA_URL`: endpoint Ollama, limitado a loopback.
- `ATLAS_MODE=offline`: modo informativo sin LLM.

Atlas no instala, descarga ni inicia Ollama automáticamente.

## Pruebas y evidencia de validación

Ejecutar las pruebas desde la raíz del repositorio con `.venv` activado:

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
```

**Última evidencia de pruebas comunicada por el propietario (18–19 de noviembre de 2026):**

- Suite completa: **1,583 tests — OK (skipped=1)**; ejecución comunicada en Debian, dentro del entorno virtual del proyecto.
- Esa ejecución es evidencia del checkout probado en ese momento, **no del HEAD actual**: posteriormente se incorporó la corrección final del decoder para enteros JSON extremos.
- La nueva validación focalizada y completa de esa corrección está pendiente de ejecución local en Debian. No se debe presentar el HEAD actual como validado.
- La validación de 7B.6B (37 tests OK) y `python -m compileall -q src tests` con exit code 0 pertenecen al checkpoint anterior de autoridad/almacenamiento documentado en `docs/status-current.md`; no son validación del IPC ni del HEAD actual.

La evidencia de 844, 1,513 y 1,547 tests pertenece a checkpoints históricos distintos y no debe mezclarse con la ejecución de 1,583. Las ejecuciones son locales; no son resultados de GitHub Actions ni validación de despliegue productivo.

## Documentación técnica y contractual

- [Contrato de diseño Atlas v1](Contrato-de-diseno-Atlas-v1.md)
- [Arquitectura](docs/architecture.md)
- [Contrato de Atlas Assistant](docs/contracts/assistant.md)
- [Contrato de memoria](docs/contracts/memory.md)
- [Contrato de identidad](docs/contracts/identity.md)
- [Contrato de eventos](docs/contracts/events.md)
- [Contrato de contexto de operación](docs/contracts/operation-context.md)
- [Contrato de proactividad](docs/contracts/proactivity.md)
- [B1-A-06 — identidad, Project/Environment y persistencia compartida](docs/contracts/b1-a06-identity-project-environment-and-persistence.md)
- [B1-B-02 — modelo lógico integrado y consistencia contractual](docs/design/b1-b02-logical-model-and-contract-consistency.md)
- [B1-B-03B — diseño físico de Identity Authority](docs/design/b1-b03b-identity-authority-physical-design.md)
- [B1-B-03C — ciclo de vida y seguridad de cuentas](docs/design/b1-b03c-identity-lifecycle-and-account-security.md)
- [B1-B-03D — VerifiedIdentityContext y evidencia](docs/design/b1-b03d-verified-identity-and-evidence.md)
- [B1-B-03E — migración legacy y rollout](docs/design/b1-b03e-legacy-migration-and-rollout.md)
- [ME-D4J — unidad de trabajo SQLite](docs/design/ME-D4J-sqlite-unit-of-work.md)
- [ME-D4N — adaptador SQLite del Recovery Gate](docs/design/ME-D4N-sqlite-recovery-gate.md)
- [ME-D4O — bootstrap e integración de autoridad SQLite](docs/design/ME-D4O-sqlite-authority-bootstrap-and-integration.md)
- [ME-D4O-A — bootstrap autenticado por perfil](docs/design/ME-D4O-A-authenticated-domain-bootstrap.md)
- [Autenticador PAM local para bootstrap](docs/design/local-pam-bootstrap-authenticator.md)
- [Protocolo de prueba para bootstrap LOCAL](docs/design/local-pam-bootstrap-proof-protocol.md)
- [Arquitectura de coordinación del bootstrap LOCAL](docs/design/local-bootstrap-coordination-architecture.md)
- [Frontera de privilegios del bootstrap LOCAL](docs/design/local-bootstrap-privilege-boundary.md)
- [Contrato de validación de privilegios del bootstrap LOCAL](docs/design/local-bootstrap-privilege-validation-contract.md)
- [Diseño V1 del validador aislado de bootstrap LOCAL](docs/design/local-bootstrap-validator-v1-design.md)
- [Diseño V2 del observador LOCAL de procesos](docs/design/local-bootstrap-observer-v2-design.md)
- [Diseño V3 del observador de cadena sudo](docs/design/local-bootstrap-chain-observer-v3-design.md)
- [Autenticador PAM local para bootstrap](docs/design/local-pam-bootstrap-authenticator.md)
- [Protocolo de prueba para bootstrap LOCAL](docs/design/local-pam-bootstrap-proof-protocol.md)
- [ME-D4O-B — admisión durable de lectura](docs/design/ME-D4O-B-durable-read-admission.md)
- [ME-D4O-I C.2 — verificación y consumo de pruebas de revocación](docs/design/me-d4o-i-c2-proof-verification-and-one-shot-consumption.md)
- [ME-D4O-I C.3 — coordinación de revocación de Grants](docs/design/me-d4o-i-c3-grant-revocation-coordination.md)
- [ME-D4O-I C.4 — almacenamiento durable SQLite de cambios de autoridad](docs/design/me-d4o-i-c4-sqlite-durable-authority-store.md)
- [README de Memory Engine: configuración local y estado](docs/memory-engine/README.md)

## Próximas fases recomendadas

El orden recomendado evita conectar el Assistant a capacidades que aún no tienen persistencia y autoridad completas:

1. **Cerrar 7B.6B y completar 7B.6C:** validar lifecycle writer/ledger/workspace en Debian y auditar imports, call-sites y exports antes de exponer nuevas capacidades.
2. **Cerrar el bootstrap e integración de identidad:** terminar login/sesiones de usuario y el contexto verificado de clientes; no inferir autoridad desde el sistema operativo.
3. **Completar la autoridad protegida:** admisión, invalidación, fencing, egress y recuperación dentro de una composición durable.
4. **Integrar Project/Environment y Workspace al flujo de aplicación:** mantener el gate read-only hasta demostrar autorización y composición E2E.
5. **Completar el núcleo durable de Memory Engine y Forget:** persistencia de contenido, inventario de destinos, adaptadores de eliminación y verificación.
6. **Demostrar independencia de Memory Engine:** contrato público, composición mínima y pruebas desde un consumidor externo a Atlas.
7. **Integrar MemoryGateway con AtlasCore** solo después de superar las fases anteriores.
8. **Desarrollar Task Manager, Skills Manager, agentes en runtime, Scheduler, aprobaciones, eventos, notificaciones y recuperación integral.**

## Alcance de este repositorio

Este repositorio contiene el código y la documentación de Atlas. La existencia de un contrato o componente no autoriza cambios en infraestructura, servicios, datos o entornos externos. Las migraciones y adaptadores deben validarse primero con bases temporales y pruebas de upgrade, integridad, concurrencia y recuperación.


## Estado del incremento de autoridad e IPC — 19 de noviembre de 2026

La rama de trabajo incorpora, además de la base conversacional y del trabajo de Memory descrito arriba:

- Autenticación nativa: credenciales Argon2id, autenticadores, proofs de un solo uso y persistencia separada de Authentication Authority e Identity Authority.
- Identidad verificada USER y AGENT, con bindings canónicos y revalidación mediante servicios confiables.
- Delegación AGENT emitida/revocada por el propietario verificado, con scopes explícitos, evidencia de corta duración y revalidación.
- Renovaciones delegadas de Grants bajo evaluación CAM exacta y revalidación de identidad, delegación y asociación Project–Environment.
- Bootstrap administrativo local de Platform Admin y lifecycle de asociaciones Project–Environment con ledger de eventos.
- Separación de lectura y escritura lifecycle: el repositorio general de Workspace no expone la transición; el writer lifecycle se limita a la composición del servicio autorizado.
- Protocolo IPC administrativo local `atlas-admin/1`: transporte Unix `SOCK_SEQPACKET`, autenticación del peer mediante `SO_PEERCRED`, envelope y límites estrictos, catálogo cerrado de siete operaciones y contratos individuales para cada una.
- Prototipo actual: solo `authority.ping` está implementada. `authority.diagnose`, `authority.migrations.plan`, `authority.operation.status`, `authority.initialize`, `authority.migrations.apply` y `authority.project_environment.provision` están especificadas pero no implementadas y deben permanecer denegadas.
- `operator_evidence`: semántica y estructura JSON aprobadas (§§9.11.1–9.11.2); evidencia declarativa no confiable del frontend, no sustituye `SO_PEERCRED`, identidad Atlas ni autorización de dominio.
- `reason`: normalización canónica aprobada (§9.11.3).
- Gramáticas aprobadas (§9.11.4): `project_id`/`environment_id` ASCII lowercase/dígitos/guion, 1–128 caracteres; `canonical_database_name` literal `authority.sqlite3`; versiones enteras JSON estrictas en rango 1..`2^63-1` y target mayor que current; `plan_digest` SHA-256 hexadecimal lowercase de 64 caracteres.
- Pendiente: serialización canónica exacta del contenido del plan antes de SHA-256, esquemas completos de resultados y mapeo exhaustivo de códigos/estados.

**Límites:** el IPC no implica listener persistente, daemon, systemd, permisos definitivos del host, acceso directo del frontend a SQLite ni autorización para ejecutar mutaciones sobre la base real. Estos componentes tampoco habilitan por sí solos login público, endpoints, agentes en runtime, ejecución de herramientas, shell, Docker ni privilegios del host. PR #28 permanece abierto y Draft; no está integrado. No se ejecutaron pruebas durante las actualizaciones documentales descritas aquí. El detalle normativo está en [el contrato IPC](docs/contracts/local-authority-admin-ipc-atlas-admin-1.md), y el estado de trabajo y validación en [PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md). Para el checkpoint anterior de autoridad/almacenamiento, consulta [docs/status-current.md](docs/status-current.md); no confundirlo con el estado de esta rama.
