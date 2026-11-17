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

> **Estado de esta documentación:** sincronizado con el estado conocido de la rama `feature/terminal-commands` al 16 de noviembre de 2026. La evidencia de pruebas corresponde al commit de código `610f027f1fe91933278e431d8a9ec29dd291b96e`; las actualizaciones documentales posteriores no modifican código. Este README diferencia capacidades funcionales, composición parcial y trabajo pendiente. Un contrato, puerto, modelo o reducer no demuestra por sí solo que una capacidad esté habilitada en un runtime completo.

## Estado general del desarrollo

Atlas es software funcional en desarrollo incremental, no solamente un conjunto de contratos o un prototipo. Ya dispone de una experiencia conversacional local ejecutable, integración con Ollama y gestión durable de conversaciones, incluyendo administración, exportación, backup cifrado, verificación y restauración. La suite completa local ha sido ejecutada y aprobada. A la vez, Atlas todavía no es el entorno autónomo completo descrito por su visión. Consulta el [estado vigente del proyecto](docs/status-current.md).

| Área | Estado real |
|---|---|
| Assistant local y consola | **Funcional: consola, composición local y conversación con Ollama** |
| Integración con Ollama | **Implementada** |
| Contexto conversacional | **Persistente en SQLite; historial durable y proyección acotada al modelo** |
| AtlasCore | **Fachada de aplicación implementada; orquestación completa pendiente** |
| Identidad canónica local | **Persistencia SQLite implementada para UserId–Identity(USER)** |
| Autenticación externa e identidad verificada completa | **Pendiente** |
| CAM y autorización de memoria | **Servicios y contratos implementados parcialmente** |
| Grants, renovación y revocación | **Servicios y coordinación implementados; composición completa depende de puertos/adaptadores** |
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

## Desarrollo actual: Atlas Terminal

Atlas Terminal ya es una superficie funcional en `feature/terminal-commands`: inicia la consola, conversa con Ollama cuando está disponible, conserva conversaciones en SQLite y permite administrarlas. Las fases 1 y 2 están implementadas y validadas en el alcance descrito. Consulta la [documentación de Atlas Terminal](docs/terminal/README.md), la [hoja de ruta](docs/terminal/roadmap.md) y la [guía de conversaciones](docs/conversations.md). Esta rama no debe confundirse con `main`; el estado aquí documentado corresponde a la rama indicada en el encabezado. La hoja de ruta general marca las fases 1 y 2 como completadas. La Fase 3 (evaluación de inteligencia y seguridad) queda pausada por decisión del propietario; sus resultados y pendientes se conservan, pero no serán el foco inmediato. La prioridad pasa a construir un Atlas funcional de prueba, ampliando las capacidades del Assistant de forma incremental en un entorno local controlado. Consulta [roadmap](docs/roadmap.md), [estado vigente](docs/status-current.md) y el [plan de Atlas funcional de prueba](docs/functional-test-roadmap.md).

## Documentación del proyecto

- [Estado vigente de Atlas](docs/status-current.md)
- [Plan de Atlas funcional de prueba](docs/functional-test-roadmap.md)
- [Mapa de composición funcional F0](docs/functional-architecture-map.md)
- [Atlas Workstation — entorno operativo aislado](docs/design/atlas-workstation.md)
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

**Persistencia de identidad SQLite v1–v6:**

- **v1–v3:** dominio local de consistencia, journal, checkpoints e identidad de append.
- **v4:** ledger durable de cambios de autoridad, invalidaciones y evidencia de recuperación.
- **v5:** relación canónica entre `UserId` interno e `Identity(USER)`.
- **v6:** integridad bidireccional de la relación USER mediante claves foráneas diferidas.

La migración v6 exige que una identidad USER tenga su registro canónico de usuario correspondiente y viceversa al confirmar la transacción. Las migraciones son consecutivas, inmutables y verificadas mediante checksum.

**Límites pendientes:**

- Autenticación real del propietario y proveedores externos.
- Bindings externos y un flujo completo de `VerifiedIdentityContext`.
- Fuentes durables y canónicas para todos los dominios Identity, Project y Environment.
- Composición de una autoridad común que coordine todos los cambios protegidos.
- Verificación de extremo a extremo de los límites de autorización en un runtime integrado.

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

**Última evidencia local reportada por el usuario (16 de noviembre de 2026):**

- Pruebas específicas de eliminación: **6/6 aprobadas**.
- Suite completa: **844 pruebas aprobadas**, 0 fallos y 0 errores (3.304 segundos).
- Entorno: Debian, dentro del entorno virtual `.venv`.
- Código probado: commit `610f027f1fe91933278e431d8a9ec29dd291b96e`.

Estas son ejecuciones locales; no son resultados de GitHub Actions ni validación de despliegue productivo. No se ejecutaron pruebas en GitHub durante esta revisión documental.

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
- [Autenticador PAM local para bootstrap](docs/design/local-pam-bootstrap-authenticator.md)
- [Protocolo de prueba para bootstrap LOCAL](docs/design/local-pam-bootstrap-proof-protocol.md)
- [ME-D4O-B — admisión durable de lectura](docs/design/ME-D4O-B-durable-read-admission.md)
- [ME-D4O-I C.2 — verificación y consumo de pruebas de revocación](docs/design/me-d4o-i-c2-proof-verification-and-one-shot-consumption.md)
- [ME-D4O-I C.3 — coordinación de revocación de Grants](docs/design/me-d4o-i-c3-grant-revocation-coordination.md)
- [ME-D4O-I C.4 — almacenamiento durable SQLite de cambios de autoridad](docs/design/me-d4o-i-c4-sqlite-durable-authority-store.md)
- [README de Memory Engine: configuración local y estado](docs/memory-engine/README.md)

## Próximas fases recomendadas

El orden recomendado evita conectar el Assistant a capacidades que aún no tienen persistencia y autoridad completas:

1. **Cerrar el núcleo durable de Memory Engine:** persistencia de dominio, repositorios, UoW y contratos de contenido.
2. **Completar la autoridad protegida:** admisión, invalidación, fencing, egress y recuperación dentro de una única composición durable.
3. **Completar Forget:** autorización directa del propietario, inventario exhaustivo, adaptadores de eliminación y verificación de todos los destinos.
4. **Cerrar bootstrap y recuperación:** evidencia autenticada, reconciliación y anti-rollback para el perfil que lo requiera; mantener el Gate cerrado hasta entonces.
5. **Demostrar independencia de Memory Engine:** contrato público, composición mínima y pruebas desde un consumidor externo a Atlas.
6. **Integrar MemoryGateway con AtlasCore:** solo después de superar las fases anteriores.
7. **Desarrollar Project/Environment Manager, Skills Manager, agentes y Scheduler.**
8. **Completar aprobaciones, eventos, notificaciones, runtime de herramientas y recuperación integral de Atlas.**

## Alcance de este repositorio

Este repositorio contiene el código y la documentación de Atlas. La existencia de un contrato o componente no autoriza cambios en infraestructura, servicios, datos o entornos externos. Las migraciones y adaptadores deben validarse primero con bases temporales y pruebas de upgrade, integridad, concurrencia y recuperación.
