# Memory Engine — implementación de independencia por proyecto

Fecha: 2026-11-14  
Rama de trabajo: `feature/atlas-functional-f1`

## Objetivo

Convertir Memory Engine en un componente reutilizable por Atlas y por aplicaciones externas, sin permitir que un consumidor sustituya la autorización del motor ni obtenga acceso cruzado por conocer identificadores.

## Implementado en ME-D1 (primera extracción)

- `atlas.memory.context.MemoryRequestContext`: contexto neutral para transportar atributos de una solicitud desde un consumidor.
- `atlas.memory.authorization.MemoryAuthorizationDecision` y `MemoryAuthorizationResult`: resultado de autorización propio del dominio Memory Engine. ALLOW exige un `AuthorizationSnapshot`; DENY no puede transportar snapshot.
- `atlas.ports.memory_authorization.MemoryAuthorizationPort`: contrato que desacopla el Gateway de la implementación concreta de CAM.
- `atlas.adapters.atlas_memory_authorization.AtlasMemoryAuthorizationAdapter`: adaptador de compatibilidad que traduce el contexto neutral a `OperationContext` y el resultado CAM de Atlas al resultado neutral.
- `MemoryGatewayService` ahora depende de `MemoryAuthorizationPort` y `MemoryRequestContext`, no de `MemoryAuthorizationService` ni de `OperationContext`.
- `atlas.ports.memory.MemoryGateway` usa el contexto neutral.
- Se exportan los contratos neutrales desde `atlas.memory`.

## Límite de confianza obligatorio

`MemoryRequestContext` es un contrato de transporte de atributos, no una credencial ni una prueba criptográfica de autenticación. No autentica al actor y no debe construirse directamente a partir de campos controlados por el usuario final.

Cada consumidor debe emitirlo desde su propia frontera de identidad confiable. El adaptador de autorización debe validar identidad, estado, revisión, propietario, proyecto y entorno contra fuentes autoritativas. Si no puede verificar esos atributos, debe denegar. El adaptador Atlas existente conserva el comportamiento de CAM actual; no convierte el contexto neutral en una fuente de confianza independiente.

La autorización sigue siendo obligatoria antes de admitir una lectura. Los snapshots, admisiones, rutas, fencing y egress protegido no se sustituyen ni se debilitan con esta extracción.

## Compatibilidad y alcance

Esta entrega es una extracción incremental, no la finalización de la independencia. El adaptador Atlas mantiene la integración heredada con `OperationContext`, `Identity`, `MemoryAuthorizationService` y los Grants existentes.

Los siguientes acoplamientos permanecen pendientes de fases posteriores:

- Modelos y validadores de memoria todavía utilizan algunos tipos/errores compartidos de `atlas.core`.
- Los identificadores UUIDv7 conservan el validador histórico `validate_atlas_id`.
- La metadata resolver y CAM siguen siendo implementación Atlas, detrás del nuevo puerto de autorización.
- Los mecanismos locales de consistencia, claves y recuperación aún no están extraídos como adaptadores reemplazables.
- La persistencia del contenido de memorias, versiones y propuestas no está implementada; SQLite continúa persistiendo el diario/control de consistencia.
- Los puertos de listado y envío de propuestas están definidos, pero sus servicios operativos no están completos.

## Próximas fases

1. Extraer/normalizar los contratos neutrales de identidad y contexto, con una frontera de emisión verificable.
2. Separar CAM Atlas como adaptador completo y documentar el contrato de decisión de propietario.
3. Desacoplar metadatos de proyecto/entorno y resolverlos exclusivamente desde fuentes autoritativas del consumidor.
4. Extraer consistencia y recuperación local detrás de puertos sin cambiar sus garantías.
5. Implementar repositorios persistentes para Memory, MemoryVersion y MemoryProposal.
6. Completar propuesta, aprobación/rechazo explícitos, Forget operativo e integración con AtlasCore.
7. Añadir pruebas de conformidad con al menos dos consumidores distintos y pruebas negativas de aislamiento.

## No incluido

- No se modifica el contrato normativo `docs/contracts/memory.md`.
- No se cambian los scopes PRIVATE/PROJECT, sus reglas de visibilidad ni las decisiones de aprobación.
- No se crea una base de datos de contenido ni se cambia infraestructura de producción.
- No se declara completada la independencia hasta validar al menos un segundo consumidor sin dependencias de AtlasCore.
