# Memory Engine — implementación de independencia por proyecto

Fecha: 2026-11-14  
Rama de trabajo: `feature/atlas-functional-f1`

## Objetivo

Convertir Memory Engine en un componente reutilizable por Atlas y por aplicaciones externas, sin permitir que un consumidor sustituya la autorización del motor ni obtenga acceso cruzado por conocer identificadores.

## Implementado en ME-D1 — frontera de contexto y autorización

- `atlas.memory.context.MemoryRequestContext`: contexto neutral para transportar atributos de una solicitud desde un consumidor.
- `atlas.memory.authorization.MemoryAuthorizationDecision` y `MemoryAuthorizationResult`: resultado de autorización propio del dominio Memory Engine.
- `atlas.ports.memory_authorization.MemoryAuthorizationPort`: contrato que desacopla el Gateway de la implementación concreta de CAM Atlas.
- `atlas.adapters.atlas_memory_authorization.AtlasMemoryAuthorizationAdapter`: adaptador de compatibilidad con CAM Atlas.
- `MemoryGatewayService` depende del puerto y contexto neutrales, no directamente de `MemoryAuthorizationService` ni de `OperationContext`.

## Implementado en ME-D2 — contrato neutral de vinculación de identidad

- `atlas.memory.identity.MemoryIdentityBinding`: relación verificada actor-sujeto, activa y versionada.
- `MemoryIdentityBindingPort` y `resolve_authenticated_memory_binding`: contrato de resolución y validación fail-closed.
- `AtlasIdentityBindingAdapter`: adapta el contrato histórico de identidad de Atlas.
- `MemoryAuthorizationService` consume el binding neutral. La política CAM, Grants y evaluación PROJECT permanecen en Atlas.

## Implementado en ME-D3 — metadatos independientes del consumidor

- `atlas.memory.ports.metadata` contiene `MemoryMetadataPort`, `ProjectMetadataPort` y `EnvironmentMetadataPort`. Son contratos que cada consumidor debe implementar contra sus fuentes canónicas.
- `atlas.memory.metadata_resolver.MemoryMetadataResolver` se trasladó al núcleo de Memory Engine. Valida IDs exactos, tipo de respuesta y correspondencia del recurso; errores, excepciones, respuestas ausentes o IDs discordantes devuelven ausencia y no habilitan fallback.
- Los DTO `MemoryVersionMetadata`, `ProjectMetadata` y `EnvironmentMetadata` usan `MemoryContractError`; la validación UUIDv7 de sus identificadores de memoria se realiza sin importar `atlas.core.errors.ContractError` ni el validador de Atlas.
- `MemoryAuthorizationService` importa el resolver desde `atlas.memory`, mientras la política CAM continúa siendo específica de Atlas.
- Se conservaron los módulos anteriores `atlas.ports.memory_metadata` y `atlas.authorization.memory_metadata_resolver` como reexportaciones de compatibilidad para consumidores existentes.

## Implementado en ME-D4A — puertos neutrales de custodia y firma de consistencia

- Se añadieron `atlas.memory.ports.consistency_keys.MemoryConsistencyKeyPort` y `atlas.memory.ports.consistency_signing.MemoryConsistencySignerPort` al paquete de puertos del dominio.
- El verificador de recuperación local consume el puerto neutral de custodia de claves; el adaptador HMAC consume el puerto neutral de firma.
- Los módulos históricos `atlas.ports.local_consistency_keys` y `atlas.ports.local_consistency_signer` se conservaron como reexportaciones de compatibilidad. Los nombres anteriores siguen disponibles.
- La separación mantiene la custodia fuera del journal: el núcleo recibe referencias opacas y no material de clave. La verificación continúa separada de la firma.
- No se modificaron canonicalización JSON, HMAC-SHA-256, envelopes, allowlists, checkpoints, reducer, estados de recuperación ni garantías anti-rollback.

## Implementado en ME-D4B — contratos neutrales de proyección y recuperación

- Se añadió `atlas.memory.ports.recovery`, que define contratos neutrales para posiciones, checkpoints, estados y proyecciones mediante protocolos estructurales; no importa modelos del journal Atlas, SQLite ni el reducer.
- Los DTO neutrales `CheckpointProjectionRequest/Result`, `VerifiedCheckpointProjection`, `RecoveryInventoryRequest/Result` y `VerifiedRecoveryInventories` enlazan cada atestación con el dominio, época, secuencia, referencias exactas y versión de política solicitada.
- Se añadieron `CheckpointProjectionPort` y `RecoveryInventoryVerifierPort` al paquete neutral de puertos.
- `LocalCheckpointProjectionAdapter` y `LocalRecoveryInventoryAdapter` traducen entre los contratos neutrales y los DTO históricos del perfil local. La validación histórica de evidencia sigue ejecutándose antes de convertirla; evidencia malformada o discordante se rechaza.
- `LocalConsistencyRecoveryVerifier` y `LocalCheckpointCoordinator` consumen ahora los contratos neutrales. El reducer sigue recibiendo la proyección concreta del adaptador local, sin aceptar proyecciones arbitrarias.
- Los contratos antiguos de `atlas.ports.local_consistency_recovery` permanecen disponibles para los adaptadores y consumidores existentes.

**Composición local:** construir una instancia de cada adaptador local y compartir la misma instancia de `LocalCheckpointProjectionAdapter` entre `LocalConsistencyRecoveryVerifier`, el journal y `LocalCheckpointCoordinator`. La instancia compartida mantiene la comprobación de identidad del resolver. El adaptador de inventarios se inyecta en el verificador de recuperación.

**Límite de confianza:** que un objeto satisfaga el protocolo neutral no demuestra por sí solo que la evidencia sea auténtica. La confianza depende de los puertos concretos configurados en la raíz de composición. En el perfil local, los adaptadores delegan en los verificadores locales existentes y validan el enlace exacto antes de devolver `VERIFIED`.

## Implementado en ME-D4C — contrato neutral del journal

- Se añadió `atlas.memory.ports.journal` con protocolos estructurales para posición, transición, commit, resolución de operaciones, entrada, checkpoint y estado de recuperación.
- `ConsistencyJournalPort` es genérico y parametrizado por los modelos inmutables del consumidor. Así, Memory Engine no obliga a una aplicación externa a importar `ConsistencyPosition`, `ConsistencyTransition`, envelopes o DTO del perfil Atlas.
- El contrato distingue carga estructural de recuperación operativa: `load_recovery_state` es solo diagnóstico. La autenticidad, continuidad, inventarios y anti-rollback deben verificarse mediante puertos de confianza separados.
- Los contratos se exportan desde `atlas.memory.ports`. La implementación SQLite y los modelos históricos no se sustituyeron en esta entrega; su adaptación al nuevo puerto queda pendiente de un adaptador de perfil local.
- No se cambiaron la forma canónica de idempotencia, el esquema persistido, las migraciones, la firma, el reducer ni la política de recuperación.



## Implementado en ME-D4D — adaptador del journal SQLite local

- Se refinó `atlas.memory.ports.journal.ConsistencyJournalPort`: el commit de checkpoint ahora conserva explícitamente el `expected_continuity_reference` y devuelve un resultado de checkpoint que incluye el checkpoint autenticado y el commit del marcador.
- Se añadió `LocalSQLiteConsistencyJournalAdapter` en `atlas.adapters.sqlite.local_consistency_journal`. Traduce la firma neutral del checkpoint a la firma interna SQLite (`expected_position`, compromiso esperado de cabecera, checkpoint), y delega append, resolución y lectura estructural sin reconstruir ni modificar DTO persistidos.
- El adaptador no expone `load_verified_recovery_state`. La recuperación operativa continúa exclusivamente en el journal local concreto, que pasa por `LocalConsistencyRecoveryVerifier`.
- `load_recovery_state` sigue siendo diagnóstico y no una fuente autorizada para reducer, admisión ni egress.
- El journal SQLite no ofrece actualmente una operación completa de inventario de recibos por admisión. Por ello, el adaptador devuelve `None` para `load_endpoint_receipts`, incluso cuando se proporciona una admisión válida. No devuelve una tupla vacía ni afirma que no existan recibos.
- La escritura de checkpoint mantiene el compare-and-swap contra la posición y el compromiso previo exactos; el marcador y el checkpoint continúan en una transacción atómica. No se cambiaron tablas, migraciones, canonicalización, envelopes ni HMAC.

**Composición:** construir el `SQLiteConsistencyJournal` como hasta ahora para los flujos operativos de recuperación local. Cuando un consumidor necesite la interfaz neutral de persistencia, envolver esa misma instancia con `LocalSQLiteConsistencyJournalAdapter`. No sustituir el journal concreto inyectado en el coordinador/verificador de recuperación por el adaptador neutral.

## Alcance pendiente de ME-D4

- El nuevo contrato del journal es neutral, pero `SQLiteConsistencyJournal` todavía utiliza los DTO Atlas/local y no se ha adaptado al puerto genérico.
- Los modelos neutrales de proyección son estructurales y transportan la proyección concreta del consumidor; aún no existe un reducer neutral reutilizable. El reducer y las políticas de replay siguen ligados al perfil Atlas/local.
- `LocalConsistencyTrustPolicy`, `LocalConsistencyRecoveryVerifier`, `LocalCheckpointCoordinator` y `SQLiteConsistencyJournal` siguen siendo componentes del perfil local/Atlas.
- La extracción de validadores y modelos concretos de transición/replay como modelos de dominio neutrales sigue pendiente. No se debe sustituirlos por `object`, ni aceptar evidencia creada por el consumidor sin verificar su correspondencia exacta.
- El perfil local sigue sin ofrecer protección anti-rollback externa. Ninguna extracción de puertos cambia esa limitación.

## Límite de confianza obligatorio

Los contextos transportan atributos, no credenciales. Los bindings de identidad solo acreditan una relación actor-sujeto; no conceden permisos. Los metadatos de memoria, proyecto y entorno deben proceder de las fuentes canónicas implementadas por el consumidor, nunca de valores declarados por el solicitante.

Los adaptadores deben verificar identidad, estado, revisión, propietario, proyecto y entorno. Si no pueden verificar un atributo necesario, deben denegar. La política de autorización debe comprobar propietario, scope, clasificación, estado de versión y Grants aplicables después de resolver los metadatos.

La reutilización del resolver no convierte al consumidor en autoridad de autorización ni cambia las reglas PRIVATE/PROJECT. Los snapshots, admisiones, rutas, fencing y egress protegido permanecen obligatorios.

## Compatibilidad y alcance

Esta entrega es incremental, no la finalización de la independencia.

- CAM, Grants, evaluación de permisos y construcción de snapshots siguen siendo Atlas.
- Los modelos de dominio y validadores generales aún conservan dependencias de tipos/errores de `atlas.core`.
- La política local de confianza, los modelos del journal, el reducer y el orquestador de recuperación siguen ligados al perfil Atlas/local. Los puertos de custodia de claves, firma, proyección/inventario y journal ya tienen contratos neutrales, pero los adaptadores de persistencia siguen usando modelos del perfil local.
- La persistencia del contenido de memorias, versiones y propuestas no está implementada; SQLite continúa persistiendo el diario/control de consistencia.
- Los servicios operativos de propuestas, revisión y Forget no están completos.

## Próximas fases

1. Adaptar el perfil local/SQLite al contrato neutral del journal mediante una frontera explícita, preservando sus DTO y compatibilidad históricos.
2. Separar modelos neutrales de transición/replay y diseñar un reducer reutilizable sin debilitar la verificación de evidencia.
3. Implementar repositorios persistentes para Memory, MemoryVersion y MemoryProposal.
4. Completar propuesta, aprobación/rechazo explícitos, Forget operativo e integración con AtlasCore.
5. Añadir pruebas de conformidad con al menos dos consumidores distintos y pruebas negativas de aislamiento.

## Validación pendiente

Por instrucción del propietario, no se ejecutaron pruebas ni builds durante ME-D1, ME-D2, ME-D3, ME-D4A, ME-D4B ni ME-D4C. La compatibilidad con fakes y consumidores actuales, imports, construcción de paquetes y casos negativos quedan pendientes de la fase de pruebas.

## No incluido

- No se modifica el contrato normativo `docs/contracts/memory.md`.
- No se cambian los scopes PRIVATE/PROJECT, sus reglas de visibilidad ni las decisiones de aprobación.
- No se crea una base de datos de contenido ni se cambia infraestructura de producción.
- No se declara completada la independencia hasta validar al menos un segundo consumidor sin dependencias de AtlasCore.
