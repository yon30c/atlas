# Atlas

Atlas es un entorno personal de asistencia, coordinación y automatización de proyectos. Permite al propietario consultar sus proyectos y delegar trabajo a agentes y herramientas bajo límites explícitos, verificables y revocables.

La arquitectura se rige por **seguridad por defecto, mínimo privilegio, aislamiento, mediación, trazabilidad, recuperación segura y portabilidad**. La autonomía nunca equivale a autoridad ilimitada.

> **Estado importante:** el repositorio contiene una primera experiencia conversacional local y una implementación progresiva de dominios, autorización y Memory Engine. No todos los componentes están integrados en un único flujo operativo. La existencia de un módulo, contrato, migración o prueba no demuestra por sí sola que una capacidad esté habilitada en runtime.

## Componentes

### Atlas Assistant y AtlasCore

La experiencia actual se ejecuta desde la consola local:

- Modelos inmutables \`AssistantRequest\` y \`AssistantResponse\`.
- Contexto de operación y correlación por solicitud.
- \`AtlasCore\` como fachada de orquestación de aplicación.
- \`ConversationContextProcessor\` para enriquecer solicitudes con el historial de la conversación.
- Adaptador LLM local \`OllamaProvider\` sobre \`/api/chat\`, con respuestas completas y streaming NDJSON.
- El endpoint Ollama se limita a loopback: \`localhost\`, \`127.0.0.1\` o \`::1\`.

El historial conversacional activo usa \`InMemoryConversationHistory\`:

- Separado por \`conversation_id\`.
- Hasta 8 turnos anteriores.
- Hasta 2.000 caracteres por mensaje histórico.
- Se descartan turnos cuya respuesta sea de tipo \`ERROR\`.
- Desaparece al terminar el proceso; no es memoria persistente.

La consola recoge y presenta texto. El modelo no obtiene acceso directo a archivos, SQL, shell, Docker ni herramientas privilegiadas. Interpretar una solicitud o generar un plan no constituye autorización ni ejecución.

### Memory Engine y Memory Gateway

El repositorio contiene componentes de dominio y de infraestructura para:

- Memory, MemoryVersion, scopes PRIVATE/PROJECT, procedencia y validación.
- \`MemoryGateway\` como frontera de acceso a memoria.
- Journal de consistencia, checkpoints, reducers y recuperación.
- \`SQLiteDatabase\` y \`SQLiteUnitOfWork\`.
- \`LocalSQLiteRecoveryGateAdapter\`, limitado al ciclo del Recovery Gate.
- \`SQLiteAuthorityChangeStore\` para reservas e idempotencia de cambios de autoridad.
- Coordinación de revocación de Grants y sus contratos de autorización/prueba.
- Verificación local de recibos, políticas de confianza y firma del journal.

**La memoria conversacional del Assistant sigue siendo temporal y no está conectada a una persistencia conversacional durable.** La infraestructura SQLite existente es principalmente de consistencia y control; no representa todavía almacenamiento durable completo del contenido de las memorias.

#### Esquema SQLite

La línea de integración incluye migraciones consecutivas **v1–v6**:

- **v1–v3:** dominio local, journal, checkpoints e identidad única de append.
- **v4:** ledger durable de cambios de autoridad, invalidaciones y evidencia de recuperación.
- **v5:** relación canónica entre \`UserId\` interno e \`Identity(USER)\`.
- **v6:** integridad bidireccional entre identidad USER y registro canónico de usuario mediante claves foráneas diferidas.

Las migraciones v5–v6 incorporan persistencia local de identidad canónica. No implementan proveedores externos, bindings de identidad externos ni autenticación externa completa.
El adaptador requiere SQLite 3.26.0 o superior; el workflow de pruebas conserva el filtro de ramas existente y añade una comprobación de compatibilidad antes de ejecutar la suite.

El esquema no incluye tablas de contenido de memorias, embeddings ni snippets. No debe confundirse la persistencia del journal/control con la persistencia del contenido Memory.

#### Límites que siguen vigentes

Todavía no se debe afirmar que existe:

- Una autoridad protegida completa que coordine admisión de lecturas, Recovery Gate y egress bajo una misma unidad de trabajo.
- Una implementación operativa completa de \`admit_read\`.
- Egress protegido completo con fencing e idempotencia verificable en el receptor.
- Integración atómica completa de Forget/invalidation con admisiones y egress.
- Persistencia canónica completa para todos los dominios Memory, Identity, Project, Environment y CAM.
- Integración de MemoryGateway con el flujo conversacional de AtlasCore.

El Recovery Gate debe permanecer cerrado hasta completar bootstrap, autoridad compuesta, recuperación y validación. No se debe abrir ni modificar manualmente mediante SQL.

### Identity y autorización

Se están construyendo la identidad canónica, los bindings, CAM, Grants y la coordinación de cambios de autoridad.

La persistencia SQLite actual cubre el par interno \`UserId\`–\`Identity(USER)\`; no equivale a un sistema completo de autenticación, vinculación con proveedores externos o identidad verificada.

Los accesos protegidos deben pasar por CAM y MemoryGateway. Los scopes PRIVATE no heredan permisos de proyectos, agentes ni otras memorias. La aprobación, el rechazo y el olvido de memorias son decisiones directas y no delegables del propietario.

### Atlas Broker

[Atlas Broker](https://github.com/yon30c/atlas-broker) es un repositorio y componente separado. Su responsabilidad es mediar operaciones del runtime Docker Rootless mediante una interfaz controlada, con autenticación local, autorización y auditoría.

**No existe todavía una integración operativa entre AtlasCore/Assistant y Atlas Broker en este repositorio.** Assistant no debe conectarse directamente a Docker ni saltarse CAM, Scheduler, aprobaciones o la interfaz autorizada del Broker.

## Principios de seguridad

- Denegar por defecto y fallar cerrado ante identidad, contexto, autorización o evidencia incompletos.
- Separar autenticación, identidad y autorización.
- Verificar permisos en cada operación protegida y sobre el recurso concreto.
- No conceder permisos por conocer identificadores.
- Aislar consumidores y proyectos; no permitir acceso cross-consumer/project por defecto.
- No permitir que un modelo, prompt, Skill o herramienta amplíe sus propios permisos.
- Distinguir hechos, inferencias, propuestas y resultados.
- No presentar una propuesta como tarea admitida, autorización concedida u operación ejecutada.
- No restaurar proyectos o Skills automáticamente después de migración o recuperación.

## Ejecución local

Desde la raíz del repositorio:

\`\`\`bash
PYTHONPATH=src python -m atlas
\`\`\`

Para instalar el comando en el entorno activo:

\`\`\`bash
python -m pip install -e .
atlas
\`\`\`

Modo informativo sin proveedor LLM:

\`\`\`bash
ATLAS_MODE=offline PYTHONPATH=src python -m atlas
\`\`\`

Configuración:

- \`ATLAS_MODEL\`: tag del modelo local; predeterminado \`gemma4:e2b\`.
- \`ATLAS_OLLAMA_URL\`: endpoint Ollama, limitado a loopback.
- \`ATLAS_MODE=offline\`: modo informativo sin LLM.

Atlas no instala, descarga ni inicia Ollama automáticamente.

## Pruebas y estado de validación

Ejecutar la suite completa desde el entorno del proyecto:

\`\`\`bash
PYTHONPATH=src python -m unittest discover -s tests -v
\`\`\`

La línea C.4.1 anterior registró 787 pruebas locales reportadas como correctas. Esa evidencia es anterior a la incorporación de las migraciones de identidad v5–v6 y **no valida por sí sola la línea de integración actual**. Las pruebas específicas de identidad y migración v5–v6 están añadidas; se requiere ejecutar la suite completa sobre el commit de integración antes de promoverlo a \`main\`.

No se debe inferir un resultado CI a partir de una ejecución local.

## Documentación normativa y técnica

- [Contrato de diseño Atlas v1](Contrato-de-diseno-Atlas-v1.md)
- [Contrato de Atlas Assistant](docs/contracts/assistant.md)
- [Contrato de memoria](docs/contracts/memory.md)
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
- [ME-D4O-B — admisión durable de lectura](docs/design/ME-D4O-B-durable-read-admission.md)
- [ME-D4O-I C.2 — verificación y consumo de pruebas de revocación](docs/design/me-d4o-i-c2-proof-verification-and-one-shot-consumption.md)
- [ME-D4O-I C.3 — coordinación de revocación de Grants](docs/design/me-d4o-i-c3-grant-revocation-coordination.md)
- [ME-D4O-I C.4 — almacenamiento durable SQLite de cambios de autoridad](docs/design/me-d4o-i-c4-sqlite-durable-authority-store.md)
- [README de Memory Engine](docs/memory-engine/README.md)

## Alcance y cambios controlados

Este repositorio contiene código y documentación de Atlas. No autoriza cambios en Atlas Broker, servicios protegidos, bases de datos reales ni producción. Las migraciones deben validarse primero en bases temporales y con pruebas de upgrade, integridad y recuperación.