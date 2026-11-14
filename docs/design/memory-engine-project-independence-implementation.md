# Memory Engine — implementación de independencia por proyecto

Fecha: 2026-11-14  
Rama de trabajo: `feature/atlas-functional-f1`

## Objetivo

Convertir Memory Engine en un componente reutilizable por Atlas y por aplicaciones externas, sin permitir que un consumidor sustituya la autorización del motor ni obtenga acceso cruzado por conocer identificadores.

## Implementado en ME-D1 — frontera de contexto y autorización

- `atlas.memory.context.MemoryRequestContext`: contexto neutral para transportar atributos de una solicitud desde un consumidor.
- `atlas.memory.authorization.MemoryAuthorizationDecision` y `MemoryAuthorizationResult`: resultado de autorización propio del dominio Memory Engine.
- `atlas.ports.memory_authorization.MemoryAuthorizationPort`: contrato que desacopla el Gateway de la implementación concreta de CAM.
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

## Alcance pendiente de ME-D4

- Los contratos de proyección de checkpoints e inventarios de recuperación siguen acoplados a DTO del journal local.
- `LocalConsistencyTrustPolicy`, `LocalConsistencyRecoveryVerifier`, `LocalCheckpointCoordinator` y `SQLiteConsistencyJournal` siguen siendo componentes del perfil local/Atlas.
- La extracción de estos elementos requiere separar primero los modelos neutrales de posición, transición, checkpoint y evidencia verificada; no se debe sustituirlos por `object`, ni aceptar evidencia creada por el consumidor sin verificar su correspondencia exacta.
- El perfil local sigue sin ofrecer protección anti-rollback externa. Ninguna extracción de puertos cambia esa limitación.

## Límite de confianza obligatorio

Los contextos transportan atributos, no credenciales. Los bindings de identidad solo acreditan una relación actor-sujeto; no conceden permisos. Los metadatos de memoria, proyecto y entorno deben proceder de las fuentes canónicas implementadas por el consumidor, nunca de valores declarados por el solicitante.

Los adaptadores deben verificar identidad, estado, revisión, propietario, proyecto y entorno. Si no pueden verificar un atributo necesario, deben denegar. La política de autorización debe comprobar propietario, scope, clasificación, estado de versión y Grants aplicables después de resolver los metadatos.

La reutilización del resolver no convierte al consumidor en autoridad de autorización ni cambia las reglas PRIVATE/PROJECT. Los snapshots, admisiones, rutas, fencing y egress protegido permanecen obligatorios.

## Compatibilidad y alcance

Esta entrega es incremental, no la finalización de la independencia.

- CAM, Grants, evaluación de permisos y construcción de snapshots siguen siendo Atlas.
- Los modelos de dominio y validadores generales aún conservan dependencias de tipos/errores de `atlas.core`.
- La política local de confianza, los modelos del journal, el reducer y el orquestador de recuperación siguen ligados al perfil Atlas/local. Los puertos de custodia de claves y firma ya tienen contratos neutrales, pero los puertos de proyección/inventario y los adaptadores de persistencia aún usan modelos del perfil local.
- La persistencia del contenido de memorias, versiones y propuestas no está implementada; SQLite continúa persistiendo el diario/control de consistencia.
- Los servicios operativos de propuestas, revisión y Forget no están completos.

## Próximas fases

1. Completar ME-D4 separando modelos neutrales de consistencia y contratos de recuperación/checkpoints.
2. Implementar repositorios persistentes para Memory, MemoryVersion y MemoryProposal.
3. Completar propuesta, aprobación/rechazo explícitos, Forget operativo e integración con AtlasCore.
4. Añadir pruebas de conformidad con al menos dos consumidores distintos y pruebas negativas de aislamiento.

## Validación pendiente

Por instrucción del propietario, no se ejecutaron pruebas ni builds durante ME-D1, ME-D2, ME-D3 ni ME-D4A. La compatibilidad con fakes y consumidores actuales, imports, construcción de paquetes y casos negativos quedan pendientes de la fase de pruebas.

## No incluido

- No se modifica el contrato normativo `docs/contracts/memory.md`.
- No se cambian los scopes PRIVATE/PROJECT, sus reglas de visibilidad ni las decisiones de aprobación.
- No se crea una base de datos de contenido ni se cambia infraestructura de producción.
- No se declara completada la independencia hasta validar al menos un segundo consumidor sin dependencias de AtlasCore.
