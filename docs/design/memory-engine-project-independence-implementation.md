# Memory Engine — implementación de independencia por proyecto

Fecha: 2026-11-14  
Rama de trabajo: `feature/atlas-functional-f1`

## Objetivo

Convertir Memory Engine en un componente reutilizable por Atlas y por aplicaciones externas, sin permitir que un consumidor sustituya la autorización del motor ni obtenga acceso cruzado por conocer identificadores.

## Implementado en ME-D1 — frontera de contexto y autorización

- `atlas.memory.context.MemoryRequestContext`: contexto neutral para transportar atributos de una solicitud desde un consumidor.
- `atlas.memory.authorization.MemoryAuthorizationDecision` y `MemoryAuthorizationResult`: resultado de autorización propio del dominio Memory Engine. ALLOW exige un `AuthorizationSnapshot`; DENY no puede transportar snapshot.
- `atlas.ports.memory_authorization.MemoryAuthorizationPort`: contrato que desacopla el Gateway de la implementación concreta de CAM.
- `atlas.adapters.atlas_memory_authorization.AtlasMemoryAuthorizationAdapter`: adaptador de compatibilidad que traduce el contexto neutral a `OperationContext` y el resultado CAM de Atlas al resultado neutral.
- `MemoryGatewayService` depende de `MemoryAuthorizationPort` y `MemoryRequestContext`, no directamente de `MemoryAuthorizationService` ni de `OperationContext`.
- `atlas.ports.memory.MemoryGateway` usa el contexto neutral.
- Los contratos neutrales se exportan desde `atlas.memory`.

## Implementado en ME-D2 — contrato neutral de vinculación de identidad

- `atlas.memory.identity.MemoryIdentityBinding`: evidencia tipada e inmutable que relaciona un actor autenticado con un sujeto canónico, incluyendo estado y revisión.
- `MemoryIdentityBindingPort`: contrato neutral para resolver la vinculación desde una fuente de identidad autoritativa.
- `resolve_authenticated_memory_binding`: validación fail-closed de actor, estado, identidad exacta y revisión exacta. No acepta como prueba los atributos que el llamador declara en el contexto.
- `AtlasIdentityBindingAdapter`: adapta el puerto histórico de Atlas (`resolve_user_subject`) al nuevo contrato neutral (`resolve_subject`).
- `MemoryAuthorizationService` consume el binding neutral mediante el adaptador Atlas. La política CAM, los Grants y la evaluación de permisos permanecen en Atlas; no se han movido ni debilitado.
- Se conservó `AuthenticatedUserSubject` y `IdentitySubjectBindingPort` como contratos de compatibilidad para no forzar una migración simultánea de consumidores existentes.

## Límite de confianza obligatorio

`MemoryRequestContext` transporta atributos, no es una credencial ni una prueba criptográfica de autenticación. No debe construirse directamente a partir de campos controlados por el usuario final.

Cada consumidor debe emitir el contexto desde su propia frontera de identidad confiable. El adaptador de autorización debe verificar identidad, estado, revisión, propietario, proyecto y entorno contra fuentes autoritativas. Si no puede verificar esos atributos, debe denegar.

`MemoryIdentityBinding` tampoco concede acceso por sí solo. Solo aporta una vinculación verificada actor-sujeto. La política de autorización debe comprobar después el propietario canónico, scope, clasificación, estado de versión y, cuando corresponda, proyecto, entorno y Grants. No se aceptan permisos suministrados por el solicitante.

La autorización sigue siendo obligatoria antes de admitir una lectura. Los snapshots, admisiones, rutas, fencing y egress protegido no se sustituyen ni se debilitan con estas extracciones.

## Compatibilidad y alcance

Esta entrega es incremental, no la finalización de la independencia.

- El adaptador Atlas mantiene la integración heredada con `OperationContext`, `Identity`, CAM, Grants y metadatos Atlas.
- La política de autorización PROJECT continúa usando `AuthorizationRequest`, `AuthorizationEvaluator` y `GrantRepository` de Atlas.
- Modelos y validadores de memoria todavía utilizan algunos tipos/errores compartidos de `atlas.core`.
- Los identificadores UUIDv7 conservan el validador histórico `validate_atlas_id`.
- La resolución de metadatos de memoria/proyecto/entorno sigue siendo implementación Atlas detrás de contratos existentes.
- Los mecanismos locales de consistencia, claves y recuperación aún no están extraídos como adaptadores reemplazables.
- La persistencia del contenido de memorias, versiones y propuestas no está implementada; SQLite continúa persistiendo el diario/control de consistencia.
- Los puertos de listado y envío de propuestas están definidos, pero sus servicios operativos no están completos.

## Próximas fases

1. Desacoplar metadatos de memoria, proyecto y entorno, preservando la autoridad canónica y el fail-closed.
2. Extraer consistencia y recuperación local detrás de puertos sin cambiar sus garantías.
3. Implementar repositorios persistentes para Memory, MemoryVersion y MemoryProposal.
4. Completar propuesta, aprobación/rechazo explícitos, Forget operativo e integración con AtlasCore.
5. Añadir pruebas de conformidad con al menos dos consumidores distintos y pruebas negativas de aislamiento.

## Validación pendiente

Por instrucción del propietario, no se ejecutaron pruebas ni builds durante ME-D1/ME-D2. La compatibilidad con los fakes y consumidores actuales, la construcción de los paquetes y los casos negativos de identidad quedan pendientes de la fase de pruebas.

## No incluido

- No se modifica el contrato normativo `docs/contracts/memory.md`.
- No se cambian los scopes PRIVATE/PROJECT, sus reglas de visibilidad ni las decisiones de aprobación.
- No se crea una base de datos de contenido ni se cambia infraestructura de producción.
- No se declara completada la independencia hasta validar al menos un segundo consumidor sin dependencias de AtlasCore.
