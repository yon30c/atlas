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

## Límite de confianza obligatorio

Los contextos transportan atributos, no credenciales. Los bindings de identidad solo acreditan una relación actor-sujeto; no conceden permisos. Los metadatos de memoria, proyecto y entorno deben proceder de las fuentes canónicas implementadas por el consumidor, nunca de valores declarados por el solicitante.

Los adaptadores deben verificar identidad, estado, revisión, propietario, proyecto y entorno. Si no pueden verificar un atributo necesario, deben denegar. La política de autorización debe comprobar propietario, scope, clasificación, estado de versión y Grants aplicables después de resolver los metadatos.

La reutilización del resolver no convierte al consumidor en autoridad de autorización ni cambia las reglas PRIVATE/PROJECT. Los snapshots, admisiones, rutas, fencing y egress protegido permanecen obligatorios.

## Compatibilidad y alcance

Esta entrega es incremental, no la finalización de la independencia.

- CAM, Grants, evaluación de permisos y construcción de snapshots siguen siendo Atlas.
- Los modelos de dominio y validadores generales aún conservan dependencias de tipos/errores de `atlas.core`.
- Los mecanismos locales de consistencia, claves y recuperación no están extraídos como adaptadores reemplazables.
- La persistencia del contenido de memorias, versiones y propuestas no está implementada; SQLite continúa persistiendo el diario/control de consistencia.
- Los servicios operativos de propuestas, revisión y Forget no están completos.

## Próximas fases

1. Extraer consistencia y recuperación local detrás de puertos sin cambiar sus garantías.
2. Implementar repositorios persistentes para Memory, MemoryVersion y MemoryProposal.
3. Completar propuesta, aprobación/rechazo explícitos, Forget operativo e integración con AtlasCore.
4. Añadir pruebas de conformidad con al menos dos consumidores distintos y pruebas negativas de aislamiento.

## Validación pendiente

Por instrucción del propietario, no se ejecutaron pruebas ni builds durante ME-D1, ME-D2 o ME-D3. La compatibilidad con fakes y consumidores actuales, imports, construcción de paquetes y casos negativos quedan pendientes de la fase de pruebas.

## No incluido

- No se modifica el contrato normativo `docs/contracts/memory.md`.
- No se cambian los scopes PRIVATE/PROJECT, sus reglas de visibilidad ni las decisiones de aprobación.
- No se crea una base de datos de contenido ni se cambia infraestructura de producción.
- No se declara completada la independencia hasta validar al menos un segundo consumidor sin dependencias de AtlasCore.
