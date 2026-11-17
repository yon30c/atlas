# I-3 — inventario de consumidores de OperationContext y plan de cierre

**Estado:** auditoría técnica inicial; no modifica código ni habilita operaciones.
**Base:** `feature/verified-identity-i2-authentication-context` (I-2 validado).
**Objetivo:** identificar cada frontera sensible que usa `OperationContext` y exigir evidencia verificable de identidad sin confundir actor, usuario contextual y autorización CAM.

## 1. Invariantes

1. `actor.identity_id` identifica al actor efectivo; `context.user_id` identifica al usuario Atlas contextual/canónico. No son intercambiables.
2. Para una operación directa del propietario USER, un `VerifiedIdentityContext` vigente debe resolver ambos valores: `identity_id` y `user_id`. El actor y el usuario contextual deben coincidir exactamente con el par canónico devuelto por Identity Authority.
3. Para una operación delegada, el `VerifiedIdentityContext` del propietario no autentica al agente. Se requiere evidencia independiente de identidad AGENT y una delegación vigente que vincule actor, propietario, recurso/scope y acción.
4. `OperationContext`, `Identity(ACTIVE)`, flags de delegación y bindings legacy son datos/relaciones; por sí solos no prueban autenticación.
5. CAM continúa evaluando acción, recurso, scope, estado y revisiones. La evidencia de identidad no concede un Grant ni sustituye CAM.
6. Autoridad no disponible, evidencia ausente/expirada/manipulada o revisión obsoleta producen DENY/fail-closed.
7. No introducir compatibilidad permisiva, igualdad artificial entre UUIDs, bypass por caller legacy ni fallback de autenticación.

## 2. Consumidores sensibles auditados

### 2.1 GrantManagementService — emisión y revocación de Grants

Archivo: `src/atlas/authorization/grant_management.py`.

- `issue(context, grant, now)` valida que `grant.owner_user_id == context.user_id`, scope y UoW transaccional. No recibe ni verifica `VerifiedIdentityContext`.
- `revoke(...)` exige CAM, proof de revocación y coordinador durable; también usa `context.user_id` para ownership y `context.actor.identity_id` como actor de la solicitud.
- `_validate_owner_context` exige `actor.identity_id == context.user_id`, además de USER activo y no delegado. Esa igualdad contradice el contrato canónico y falla cuando UserId e IdentityId son UUID distintos.
- La prueba de revocación CAM es evidencia de autorización de cambio; no reemplaza la prueba de identidad del propietario.

**Riesgo:** caller que fabrique un `OperationContext` con USER activo y un UserId elegido puede llegar a las validaciones de ownership; la igualdad artificial actual no convierte el objeto en evidencia confiable.

### 2.2 GrantRenewalService — agente solicitante y propietario decisor

Archivo: `src/atlas/authorization/renewal_service.py`.

- `request_renewal` separa correctamente el actor AGENT del propietario contextual: verifica AGENT activo, `delegation == DELEGATED`, `context.user_id == grant.owner_user_id` y `context.actor.identity_id == grant.subject_identity_id`.
- Sin embargo, esa ruta no valida evidencia de autenticación del agente ni prueba independiente de delegación; el enum DELEGATED y la coincidencia de IDs son datos caller-controlled.
- `approve_renewal` y `reject_renewal` validan USER activo directo, pero `_validate_owner_context` vuelve a exigir `actor.identity_id == context.user_id`. No verifican evidencia vigente de Identity Authority.
- Las verificaciones transaccionales de propietario, scope, vínculo de solicitud/Grant, estado PENDING, revisión y CAS deben conservarse.

**Riesgo:** la solicitud delegada y la decisión del propietario no tienen fronteras de evidencia independientes. La ruta USER también contiene la igualdad incorrecta de identificadores.

### 2.3 MemoryAuthorizationService — lecturas PRIVATE y PROJECT

Archivo: `src/atlas/authorization/memory_service.py`.

- Para PRIVATE, comprueba USER activo y resuelve un binding legacy mediante `resolve_authenticated_memory_binding`; compara el sujeto resuelto con `memory.owner_id`.
- El binding legacy y la revisión de actor no demuestran autenticación nativa ni emiten `VerifiedIdentityContext`.
- Para PROJECT, valida proyecto/entorno y evalúa Grants usando `AuthorizationRequest(context=...)`; la comprobación de actor se limita al estado ACTIVE. No hay prueba de procedencia del contexto.
- La generación de `AuthorizationSnapshot` conserva actor, owner, scope y revisiones, pero un snapshot no autentica al actor.

**Riesgo:** las rutas PRIVATE y PROJECT pueden recibir contextos fabricados; el binding histórico no debe tratarse como evidencia equivalente a I-2.

### 2.4 WorkspaceCapabilityExecutionService — acceso de lectura al workspace

Archivo: `src/atlas/application/workspace_capability_execution.py`.

- Comprueba USER activo, operación no delegada, revisión/correspondencia canónica mediante `unit.identity.get_user(context.user_id)`, propietario del workspace, Project/Environment y Grant exacto.
- La comparación de actor con Identity canónica y el UoW protegen consistencia de registros, pero no prueban que el caller haya autenticado esa identidad.
- La confirmación explícita del plan y CAM deben conservarse; ninguna de ellas sustituye la evidencia de identidad.

**Riesgo:** un caller que suministre un contexto fabricado con el par canónico actual puede satisfacer la comparación local sin haber pasado por proof admission.

### 2.5 Adaptador de autorización de Memory

Archivo: `src/atlas/adapters/atlas_memory_authorization.py`.

- Convierte `MemoryRequestContext` en `OperationContext` copiando `actor_id`, tipo/estado/revisión, `user_id`, delegación y scope.
- Su docstring declara que solo debe recibir contextos de la frontera confiable, pero el adaptador no valida ni transporta `VerifiedIdentityContext`.

**Riesgo:** confiar en la documentación del caller no constituye una frontera técnica. Debe recibir evidencia verificable o una referencia interna emitida por la frontera confiable.

### 2.6 Consola local y transporte de contexto

- `src/atlas/assistant/local_console.py` crea una identidad USER sintética a partir del usuario del sistema operativo y un UserId `local:<username>`; no es una identidad canónica ni autenticada.
- `AssistantRequest` y `ProactiveProposal` transportan `OperationContext`, pero no son por sí mismos servicios de autorización. Debe asegurarse que no permitan que un contexto sintético o caller-controlled alcance los consumidores sensibles.
- UID/GID, username, HOME, hostname y posesión del proceso no se deben convertir implícitamente en identidad Atlas.

## 3. Riesgos transversales y hallazgos confirmados

- El contrato de `OperationContext` ya especifica que `user_id` procede de evidencia verificada y que no equivale a `actor.identity_id`.
- La fábrica de I-2 produce solo contextos USER directos y no delegados; no protege consumidores legacy automáticamente.
- `VerifiedIdentityContextService.verify(context)` devuelve el `CanonicalUserIdentity` después de comprobar HMAC, expiración, issuer, binding, identidad y revisiones. Puede implementarse un puerto pequeño para que los consumidores sensibles dependan de esa capacidad sin acoplarse a la clase concreta.
- Los tests actuales usan contextos de conveniencia y fixtures que no representan necesariamente evidencia de autenticación. Deben separarse fixtures de dominio/contexto de fixtures de identidad verificada.
- El test de workspace comprueba correspondencia canónica, pero no procedencia criptográfica.
- El test de Memory PRIVATE comprueba binding legacy, no la admisión I-2.
- Los cambios deben conservar las distinciones entre IDs; nunca forzar `identity_id == user_id` para mantener compatibilidad.

## 4. Plan de implementación incremental

### I3-1 — contrato común y operaciones directas de propietario en Grants

- Definir un puerto de verificación de `VerifiedIdentityContext` que devuelva el `CanonicalUserIdentity` revalidado o una denegación tipada.
- Añadir un helper común que compruebe que `context.actor` coincide exactamente con la Identity canónica y `context.user_id` con el UserId canónico; exigir USER activo y `delegation=None`.
- Inyectar el verificador en `GrantManagementService`; exigir evidencia en `issue` y `revoke`.
- Eliminar la comparación `actor.identity_id == context.user_id`; mantener `grant.owner_user_id == canonical.user_id == context.user_id`, scope y todas las garantías UoW/CAM/proof/coordinator.
- Tests positivos con IDs diferentes y negativos para evidencia ausente, expiración, manipulación, actor/UserId cruzados, revisión obsoleta y autoridad indisponible.

### I3-2 — decisiones de renovación y ruta delegada

- `approve_renewal` y `reject_renewal` requieren evidencia USER del propietario; preservar owner/scope/CAS.
- `request_renewal` requiere evidencia AGENT independiente y evidencia de delegación vigente, vinculada al owner, agente, Grant, proyecto, entorno, acción y expiración.
- No reutilizar la evidencia USER del propietario para autenticar al agente.
- Si no existe aún un contrato verificable de delegación/AGENT, mantener la solicitud deshabilitada/fail-closed en lugar de confiar en `DelegationMode.DELEGATED`.

### I3-3 — Memory Authorization

- PRIVATE: exigir evidencia USER y comparar `canonical.user_id` con `memory.owner_id`; binding legacy puede seguir aportando compatibilidad solo si no se interpreta como prueba de autenticación.
- PROJECT: exigir evidencia verificable del actor efectivo; para AGENT delegado, exigir además evidencia de delegación independiente. Mantener CAM, scope y revisiones.
- El snapshot registra el actor canónico y sujeto correcto, sin convertirlo en token de autorización.

### I3-4 — Workspace y cierre de adaptadores/callers

- Exigir evidencia USER vigente dentro de la misma frontera transaccional que revalida workspace/Grant, o establecer un mecanismo de composición que no permita caller arbitrario entre verificación y ejecución.
- Hacer que el adaptador Memory transporte una referencia/evidencia verificable en lugar de confiar en campos de identidad copiados.
- Bloquear explícitamente la identidad sintética de consola local frente a Memory, Workspace, Grants, Skills, Broker, bootstrap y otras capacidades protegidas.
- Auditar call sites, entrypoints y composición; retirar fixtures que fabriquen identidad autenticada sin un fake explícito de autoridad limitado a tests.

## 5. Criterios de salida de I-3

- Ninguna operación sensible usa `OperationContext` como prueba de autenticación.
- USER directo, AGENT delegado y otros actores tienen evidencia y reglas distintas.
- UserId e identity_id permanecen separados en código, tests, persistencia y snapshots.
- La evidencia se revalida contra Identity Authority y revisiones actuales; cualquier error es DENY.
- CAM continúa siendo la autorización ordinaria por acción/recurso/scope.
- Se conserva la atomicidad existente y no se afirman garantías de fencing/consistencia que no estén implementadas.
- Suite completa y `compileall` pasan en Debian después de cada slice.
- No se habilitan endpoints, CLI, login operativo, bootstrap, sesiones ni capacidades protegidas como efecto colateral.

## 6. Fuera de alcance

No modificar DB productiva, migraciones, host, PAM, systemd, sudoers, usuarios, Docker ni privilegios. No fusionar PRs sin autorización explícita. No desplegar ni componer el servicio de autenticación mientras falte un guard de intentos compartido y fail-closed y la provisión segura de la clave HMAC.
