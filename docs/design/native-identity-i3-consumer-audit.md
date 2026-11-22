# I-3 — inventario de consumidores de OperationContext y plan de cierre

**Estado histórico:** auditoría incremental por slices I3-1/I3-2; las secciones 1–19 conservan el estado de sus checkpoints. **Revisión estática vigente 2026-11-22:** véase §20, que inspecciona el código presente en `main` y `work/atlas-mvp-runtime`. Este documento no habilita operaciones.
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


## 7. Estado de I3-1 — operaciones directas de propietario en Grants

**Implementado en PR #13; validado por el propietario en Debian.**

Añadido en la rama de I3-1:
- Puerto `VerifiedIdentityContextVerifierPort`, compatible estructuralmente con `VerifiedIdentityContextService.verify`.
- Helper `require_verified_owner_context`: exige `VerifiedIdentityContext`, revalidación mediante autoridad confiable, par canónico `CanonicalUserIdentity`, actor exacto, UserId exacto, revisión exacta, USER activo y `delegation=None`. La indisponibilidad o excepción del verificador falla cerrado.
- `GrantManagementService.issue` y `revoke` requieren ahora el argumento keyword-only `verified_identity` y un verificador inyectado. Sin evidencia o sin verificador, deniegan antes de acceder a la coordinación o persistencia.
- Se eliminó la comparación incorrecta `actor.identity_id == context.user_id`. Ownership se compara con `canonical.user_id`; actor se compara con `canonical.identity`. No se igualan los UUIDs.
- Se conservan la UoW transaccional, scope, comprobación de ownership y la evidencia CAM/proof/coordinador ya requerida para revocación.
- Tests actualizados para usar IDs UUID distintos y un fake explícito de verificador limitado a tests; añadidos casos de evidencia ausente, identidad manipulada, mismatch actor/UserId y autoridad no disponible.

**Validación confirmada:** 31 tests específicos OK; suite completa 1,296/1,296 OK; `python -m compileall -q src tests` con exit code 0.

**Límite:** este slice solo cubre operaciones directas de propietario en `GrantManagementService`. No cierra todavía renovación, Memory, Workspace, adaptadores, callers ni identidad sintética local. El fake de tests no es un adaptador productivo y no debe componerse en runtime.


## 8. I3-2 — auditoría de renovación: hallazgos y límite de capacidad

**Base de código inspeccionada:** rama `feature/verified-identity-i3-grant-owner-evidence`, que incorpora I-2 e I3-1.

### 8.1 Decisiones directas del propietario

`GrantRenewalService.approve_renewal` y `reject_renewal` actualmente:
- Validan USER activo, pero usan la igualdad incorrecta `actor.identity_id == context.user_id`.
- No reciben `VerifiedIdentityContext` ni verifican su attestation contra Identity Authority.
- Ya conservan validaciones importantes que no deben eliminarse: owner de la solicitud y Grant, proyecto/entorno, vínculo entre renovación y Grant, estado PENDING, versión/CAS y UoW compartida.

**Cambio previsto para I3-2A:** reutilizar `VerifiedIdentityContextVerifierPort` y `require_verified_owner_context` de I3-1. Exigir evidencia USER explícita para aprobar y rechazar. Ownership se resuelve con `canonical.user_id`; el actor debe coincidir con `canonical.identity`. No comparar ni igualar directamente UserId e IdentityId. Mantener todas las validaciones transaccionales actuales.

### 8.2 Solicitud delegada por AGENT

`GrantRenewalService.request_renewal` actualmente acepta:
- `Identity(AGENT, ACTIVE)`;
- `context.delegation == DelegationMode.DELEGATED`;
- coincidencia entre `context.user_id`, el propietario del Grant y `context.actor.identity_id`, el sujeto del Grant.

Esto no constituye evidencia verificable de autenticación ni de delegación. Todos esos valores provienen del `OperationContext` entregado por el caller.

### 8.3 Límite confirmado en I-2

La implementación I-2 actual no proporciona una ruta de autenticación AGENT:
- `VerifiedIdentityContext` declara explícitamente que solo admite `IdentityKind.USER`.
- `VerifiedIdentityContextService.admit_proof` resuelve el binding mediante `get_user_by_identity_id` y rechaza cualquier identidad que no sea USER.
- `CanonicalUserIdentity` solo representa un par UserId + Identity(USER).
- `NativeIdentityAuthorityPort` y `SQLiteNativeIdentityAuthority` describen y persisten bindings inmutables exclusivamente para Identity(USER).
- No se encontró un contrato de autoridad de delegación que certifique emisor, agente, propietario, Grant, proyecto, entorno, acción, vigencia, revisión y revocación.

Por tanto, no es correcto reutilizar la evidencia USER del propietario para autenticar al agente, ampliar el tipo USER mediante casts, ni aceptar `DelegationMode.DELEGATED` como sustituto de una prueba.

### 8.4 Decisión de seguridad y slices

1. **I3-2A — propietario:** implementar evidencia USER en `approve_renewal` y `reject_renewal`, conservando UoW, CAS, scope y binding de la solicitud.
2. **I3-2B — agente/delegación:** mantener `request_renewal` bloqueado/fail-closed hasta diseñar e implementar contratos independientes para autenticación AGENT y delegación verificable. El contrato debe vincular, como mínimo, agente, propietario, Grant, proyecto, entorno, acciones permitidas, expiración, revisión y revocación.
3. La habilitación futura de I3-2B requiere su propio slice, pruebas positivas y negativas, y revisión de persistencia/atomicidad. No forma parte implícita de I3-2A.

**Estado de esta auditoría:** inspección de código completada. No se han modificado servicios ni se ha habilitado/deshabilitado una ruta en runtime en este commit documental.


## 9. I3-2A — evidencia del propietario y bloqueo de solicitudes AGENT

**Implementación en PR #15; validada en Debian.**

- `GrantRenewalService` recibe un `VerifiedIdentityContextVerifierPort` opcional. La ausencia del verificador o de la evidencia produce DENY mediante `require_verified_owner_context`.
- `approve_renewal` y `reject_renewal` requieren `verified_identity` explícito. El actor debe coincidir con la Identity USER canónica y `context.user_id` con el UserId canónico; los IDs permanecen distintos.
- La decisión se atribuye a `canonical.user_id`, nunca al valor sin verificar del contexto.
- Se conservan UoW, ownership del Grant y la solicitud, proyecto/entorno, binding, estado PENDING, CAS, revisión y rollback.
- `request_renewal` ahora deniega siempre antes de acceder a repositorios: no existe todavía autenticación AGENT ni autoridad verificable de delegación. No hay bypass basado en `Identity(ACTIVE)` o `DelegationMode.DELEGATED`.
- Los tests usan un fake explícito para evidencia USER, crean solicitudes pendientes directamente como fixtures de dominio y comprueban que la ruta AGENT no persiste ninguna solicitud.

**Límite:** el bloqueo de `request_renewal` es deliberado y temporal hasta I3-2B. No se ha creado autenticación AGENT, autoridad de delegación, wiring productivo ni endpoint. Los tests aún deben ejecutarse en Debian; no declarar I3-2A validado antes de recibir resultados.


**Resultado de validación I3-2A (confirmado por el propietario en Debian):**
- `test_renewal_service.py`: 11/11 OK.
- `test_sqlite_authorization_unit_of_work.py`: 9/9 OK.
- Suite completa: 1,292/1,292 OK.
- `python -m compileall -q src tests`: `COMPILE_EXIT_CODE=0`.

I3-2A queda validado. I3-2B (autenticación AGENT y autoridad verificable de delegación) sigue pendiente y la ruta de solicitud AGENT permanece bloqueada.


## 10. I3-2B — contrato de identidad AGENT y delegación verificable

**Diseño documentado en la rama `design/verified-agent-delegation-i3-2b`; implementación pendiente.**

Se añadió `docs/design/verified-agent-delegation-contract-i3-2b.md`, que define:
- identidad AGENT canónica y prueba de autenticación independiente de USER;
- autoridad de delegación emitida por el propietario USER autenticado;
- delegación vinculada a un Grant concreto y limitada por su revisión, acciones, recursos, proyecto, entorno y expiración;
- revalidación de identidad, binding, delegación y Grant, incluida revocación;
- CAM como autorización final y `DelegationMode.DELEGATED` como metadata, nunca evidencia;
- requisitos de UoW/fencing, concurrencia, idempotencia y pruebas negativas;
- secuencia de slices I3-2B.1 a I3-2B.6.

**Estado:** solo documentación. `GrantRenewalService.request_renewal` permanece fail-closed. No se amplían tipos USER, no se crea persistencia ni se habilitan rutas AGENT.


## 11. I3-2B.1 — contratos AGENT separados

Se añadieron contratos puros en `src/atlas/core` y puertos en `src/atlas/ports` para:
- `CanonicalAgentIdentity` sin UserId;
- `VerifiedAgentIdentityContext` AGENT-only;
- `NativeAgentIdentityBinding` separado del binding USER;
- `AgentDelegation`, scope explícito y `VerifiedAgentDelegationContext`;
- autoridades y verificadores independientes para identidad, binding y delegación AGENT.

La prueba unitaria focalizada es `tests/unit/test_agent_delegation_domain_contracts.py`. No hay adaptadores, persistencia, migraciones, proof admission, composition root ni cambios a `GrantRenewalService`.

**Límite transaccional confirmado:** la auditoría `assistant-operation-consistency-boundary.md` describe UoWs/SQLite independientes para Identity y CAM/Grant/Renewal. No existe evidencia de una transacción común entre esas fuentes. I3-2B.5 debe resolver y probar ese límite o mantener fail-closed. No afirmar atomicidad global en el diseño actual.

**Estado de validación:** pruebas añadidas pero todavía no ejecutadas en Debian por el propietario.


## 12. I3-2B.2 — autoridad canónica AGENT

Se añadió la autoridad SQLite separada SQLiteAgentIdentityAuthority y su suite focalizada. Reutiliza exclusivamente el almacenamiento identity_records ya existente: los registros AGENT tienen identity_kind='agent' y user_id=NULL, mientras que atlas_users sigue reservado para pares USER.

La autoridad crea UUIDv4, resuelve solo registros AGENT, actualiza estado mediante CAS/revision y respeta revocación terminal. Acepta una SQLiteUnitOfWork explícita para participar en una transacción ya compuesta. No gestiona autenticación, proof, binding, delegación ni CAM; request_renewal permanece fail-closed.

Pruebas: tests/unit/test_sqlite_agent_identity_authority.py. Cubren UUID canónico, no resolución cruzada USER/AGENT, ausencia, duplicados, CAS, estados terminales, entradas inválidas, concurrencia y UoW.

**Estado:** implementación publicada en PR #16. La suite completa del branch fue validada posteriormente en Debian: 1,329/1,329 tests OK y compileall exit 0. No se habilita autenticación AGENT.


### 12.1. Extensión de I3-2B.2: binding nativo AGENT

Se completó el slice de binding persistente AGENT:
- CORE_SCHEMA_V21 añade native_agent_identity_bindings con FK a identidad/issuer, restricciones UUID/digest, estado y revisión.
- CORE_SCHEMA_V22 añade exclusividad cruzada de subject: un issuer+subject_digest no puede estar vinculado simultáneamente a USER y AGENT. La protección se aplica tanto si se inserta primero USER como si se inserta primero AGENT.
- SQLiteNativeAgentIdentityAuthority valida CanonicalAgentIdentity contra identity_records, exige AGENT ACTIVE y issuer ACTIVE, y permite lookup y revocación CAS terminal.
- Se conserva intacta la tabla y el trigger USER native_identity_bindings.

Tests añadidos: tests/unit/test_sqlite_native_agent_identity_authority.py. La suite completa del branch fue validada posteriormente en Debian: 1,329/1,329 tests OK y compileall exit 0.


### 13. I3-2B.3A — persistencia de delegaciones

Se publicó CORE_SCHEMA_V23 y SQLiteAgentDelegationRepository como sustrato de persistencia, no como autoridad de emisión. La tabla mantiene owner/USER, AGENT, Grant/revision, project/environment, scope explícito, issuer, ventana temporal y tombstones de revocación.

La inserción valida mediante SQLite el propietario canónico activo, identidad AGENT activa, Grant exacto vigente, issuer activo y binding AGENT activo. El subconjunto de recursos/acciones se valida en Python y en triggers SQLite. Claims inmutables, CAS de revisión, revocación terminal y no-delete quedan protegidos en la base.

SQLiteLocalAuthorityUnitOfWork ahora expone USER identity, AGENT identity, USER/AGENT native bindings, Grants, renewals y delegations sobre una sola SQLiteUnitOfWork.

**Bloqueo en el checkpoint I3-2B.3A:** todavía no existía soporte productivo para revalidar evidencia USER/AGENT dentro de la misma UoW. I3-2B.3B.3 cerró ese punto para los verificadores de identidad. La autoridad de delegación/verificador de contexto delegado sigue pendiente; el repositorio no prueba consentimiento del owner y no debe usarse como API de aplicación. No se emiten contextos delegados ni se habilitan operaciones delegated.

**Validación del slice de persistencia:** suite completa del branch ejecutada por el propietario en Debian: 1,329/1,329 tests OK en 17.000s; `python -m compileall -q src tests` con `COMPILE_EXIT_CODE=0`. Esta validación no elimina el bloqueo de autoridad descrito arriba.


### 14. I3-2B.3B.1 — servicio de contexto verificado AGENT

Se añadió `VerifiedAgentIdentityContextService`, con admisión one-shot de proofs y revalidación canónica exclusivamente AGENT. La resolución usa `native_agent_identity` + `agent_identity`; no crea ni resuelve `atlas_users`. El contexto incluye realm/audience y attestation HMAC con domain separation distinto del protocolo USER. Proof consumption, binding lookup y canonical resolution comparten `SQLiteLocalAuthorityUnitOfWork`; cualquier fallo de binding/identidad revierte el consumo.

El método `verify` vuelve a comprobar firma, TTL, issuer, binding activo/revisión y canonical AGENT activo/revisión, implementando el puerto `VerifiedAgentIdentityContextVerifierPort`.

**Pendiente de validación Debian.** No se emite aún `VerifiedAgentDelegationContext`, no existe todavía autoridad de delegación y no se habilitan operaciones AGENT en runtime.


### Validación Debian — I3-2B.3B.1

El propietario ejecutó la suite completa sobre el HEAD de esta fase: `Ran 1341 tests in 17.171s`, `OK`; `python -m compileall -q src tests` terminó con `COMPILE_EXIT_CODE=0`. Esta evidencia corresponde a la rama de diseño actual y no implica activación de autenticación AGENT en runtime ni habilitación de delegaciones.


### Validación Debian — I3-2B.3B.2

El propietario ejecutó `test_agent_delegation_domain_contracts.py`: `Ran 12 tests in 0.486s`, `OK`; `python -m compileall -q src tests` devolvió `COMPILE_EXIT_CODE=0`.


### I3-2B.3B.3 — revalidación dentro de UoW compartida

Ambos servicios de contexto ahora exponen `verify_in_unit_of_work(context, unit)`, que revalida la evidencia sin abrir ni confirmar transacciones. Los métodos `verify(context)` conservan compatibilidad y usan una UoW propia. La futura autoridad de delegación podrá validar owner USER, AGENT y estado de Grant/delegación en una única transacción, evitando la falsa atomicidad de verificadores que abren conexiones independientes.



## 15. I3-2B.3B.3 — verificación de identidad dentro de UoW compartida

Los servicios USER y AGENT ahora ofrecen `verify_in_unit_of_work(context, unit)`. Esta ruta usa las autoridades de issuer, binding e identidad canónica que expone la UoW recibida y deja commit/rollback bajo control del llamador. `verify(context)` conserva el uso autónomo con una UoW propia.

La composición `SQLiteLocalAuthorityUnitOfWork` expone las autoridades USER/AGENT, bindings nativos y repositorios de Grant/delegación sobre el mismo `SQLiteUnitOfWork`. Esto elimina la necesidad de que la futura autoridad de delegación invoque verificadores que abran transacciones independientes. La garantía sigue limitada a la base SQLite y UoW compartidas; no implica atomicidad con efectos externos ni sustituye CAM.

**Validación del propietario en Debian:** suite completa **1,344/1,344 tests OK** y `python -m compileall -q src tests` con `COMPILE_EXIT_CODE=0`. No se habilita todavía la autoridad de emisión/revocación/verificación de delegaciones; `GrantRenewalService.request_renewal` permanece fail-closed.


## 16. I3-2B.4A — emisión owner-verified de delegación

La autoridad de emisión `SQLiteAgentDelegationAuthority.create_for_grant` ya consume el seam UoW compartido. El USER verifier revalida el contexto del propietario dentro de la misma transacción que resuelve AGENT, binding nativo, Grant y persiste la delegación.

La autoridad requiere que el binding AGENT activo pertenezca al mismo issuer nativo que el contexto USER verificado, porque CORE_SCHEMA_V23 vincula el issuer de la delegación con ese binding. No basta con que exista cualquier binding activo de la identidad AGENT.

La implementación se limita a emitir consentimiento acotado por un Grant exacto. No añade `revoke_delegation`, verificación operativa ni `VerifiedAgentDelegationContext`; CAM continúa siendo la decisión de autorización final y `GrantRenewalService.request_renewal` permanece fail-closed. Las pruebas focalizadas están pendientes de ejecución en Debian.


## 17. I3-2B.4B — revocación owner-verified

La autoridad de delegación ahora implementa revocación terminal owner-only. La operación exige `VerifiedIdentityContext` USER, revalida la evidencia dentro de la misma `SQLiteLocalAuthorityUnitOfWork`, resuelve la delegación canónica y compara el par propietario `user_id + identity_id` con el USER verificado. La revisión esperada se aplica mediante CAS en el repositorio; el timestamp procede del reloj confiable inyectado y el actor de auditoría se deriva del propietario canónico. El rollback cubre la verificación y la mutación.

No se implementa todavía `verify_for_operation`, emisión de `VerifiedAgentDelegationContext`, autorización CAM delegada ni renovación AGENT. `GrantRenewalService.request_renewal` permanece fail-closed.

Tests focalizados añadidos: éxito y auditoría, evidencia manipulada/expirada, otro propietario, revisión obsoleta, registro ausente y rollback tras escritura.

**Validación Debian:** pendiente de ejecución por el propietario; no declarar el slice validado hasta recibir resultados.


## 18. I3-2B.5 — evidencia de operación delegada

Se implementó un servicio separado `VerifiedAgentDelegationContextService` para emitir y revalidar evidencia efímera de consentimiento AGENT. La configuración de realm, audience, TTL, reloj y attestor pertenece al composition root; los argumentos del caller ya no permiten elegir esos parámetros. `SQLiteAgentDelegationAuthority.verify_for_operation` delega a un verificador configurado y deniega si falta.

La emisión revalida el contexto AGENT dentro de la UoW compartida, enlaza identidad AGENT e issuer con la delegación exacta, y comprueba propietario USER activo, AGENT activo, binding nativo activo, delegación ACTIVE/ventana/revisión, Grant exacto/no revocado/revisión, proyecto, entorno y subconjuntos de recursos/acciones. La evidencia se firma con HMAC y TTL máximo de un minuto.

La revalidación posterior verifica attestation, configuración confiable, TTL, claims, estado/revisión de delegación y Grant, propietario, identidad AGENT y binding nativo. La variante `verify_in_unit_of_work` no controla el commit del caller. Esta evidencia no es autorización CAM.

**Límite preservado:** no se conecta a `GrantRenewalService.request_renewal`, no se habilita runtime AGENT, login ni endpoints. La ruta de renovación sigue fail-closed. Validación Debian pendiente del propietario; no se declaran pruebas aprobadas hasta recibir el resultado de la suite y compileall.


## 19. I3-2B.5 validation and I3-2B.6 CAM renewal integration

**Owner validation of I3-2B.5:** 1,369/1,369 tests passed on Debian; `python -m compileall -q src tests` returned exit code 0.

I3-2B.6B/6C implementation now exists on the PR branch:
- CAM action `grant.renewal.request` is explicit and checked against the exact Grant and delegated scope.
- The first version requires exact resource-set equality because approval renews the whole Grant.
- Each resource is evaluated by `AuthorizationEvaluator`; all must ALLOW against the same Grant ID and revision.
- AGENT and delegation evidence are revalidated inside the same local SQLite UoW that reads Grant/Project/Environment and persists the renewal request.
- The request stores immutable Grant/delegation revisions; CORE_SCHEMA_V24 enforces complete evidence, canonical delegation/Grant/binding/issuer match, and immutable audit claims.
- Only USER owner evidence may approve/reject. Approval rejects a stale Grant revision.
- Duplicate request ID is idempotent only for the same intent; only one PENDING request per Grant is allowed.

**I3-2B.6B/6C Debian validation remains pending.** The implementation is not considered validated until the owner reports focused tests, full unit suite and compileall. No AGENT login, endpoint or runtime was enabled. PR #16 remains Draft/open/unmerged.


## 20. Revisión estática vigente de consumidores — 2026-11-22

**Base inspeccionada:** `main` y `work/atlas-mvp-runtime`. Los archivos revisados de `GrantRenewalService`, contextos AGENT y consumidores sensibles tienen el mismo SHA en ambas referencias. Esta sección actualiza el estado del código sin borrar el historial de los slices anteriores.

### 20.1 Renovación de Grants

El código actual de `GrantRenewalService`:

- `request_renewal` exige `VerifiedAgentIdentityContext` y `VerifiedAgentDelegationContext` explícitos, y ambos verificadores ejecutan `verify_in_unit_of_work` dentro de la UoW de la operación.
- Revalida Grant, Project, Environment y asociación Project–Environment, incluyendo estado/revisión y vínculo entre delegación y Grant.
- `approve_renewal` y `reject_renewal` usan `require_verified_owner_context_in_unit_of_work` dentro de la UoW de mutación.

Esto corrige el checkpoint histórico donde la ruta AGENT se describía como completamente bloqueada. La existencia de esta ruta de aplicación no habilita login AGENT, endpoints ni runtime delegado; la autorización CAM y el cierre de la composición siguen siendo necesarios.

### 20.2 Emisión y revocación directa de Grants

**Actualización tras commit 1f43d29:**

- `GrantManagementService.issue` ya llama a `require_verified_owner_context_in_unit_of_work` dentro de la misma UoW que comprueba unicidad e inserta el Grant. El propietario canónico y su par Identity/UserId se resuelven dentro de la transacción de escritura. La ruta falla cerrada si el verificador no ofrece `verify_in_unit_of_work`.
- Se añadió una prueba que comprueba que la emisión no usa `verify()` fuera de la transacción y que el verificador recibe exactamente la UoW de inserción. La prueba está publicada, pero **pendiente de ejecución local**.
- `GrantManagementService.revoke` todavía llama a `require_verified_owner_context` antes de la coordinación durable de revocación. Su reserva/aplicación atraviesa un coordinador separado; no se debe envolver ingenuamente en la UoW SQLite de grants ni afirmar atomicidad global. Requiere un contrato de fencing que ate la evidencia de identidad a la reserva y al commit de cambio.

El cambio de `issue` reduce la ventana TOCTOU en la emisión, pero no cierra toda la superficie I-3 ni autoriza conectar Grant Management al runtime.

### 20.3 Memory y Workspace

- `MemoryAuthorizationService` continúa aceptando `OperationContext` y usando el binding legacy `AuthenticatedUserSubject`; no exige ni revalida `VerifiedIdentityContext`. No habilitar lecturas protegidas desde identidad nativa por inferencia.
- `WorkspaceCapabilityExecutionService` ahora exige un `VerifiedIdentityContext` y un verificador que implemente `verify_in_unit_of_work`. La evidencia USER se revalida dentro de la misma UoW que consulta identidad, Workspace, Project/Environment, asociación y Grants, antes de resolver el mount o tocar filesystem. La ruta falla cerrada si falta el verificador transaccional.
- Se añadieron pruebas con un fake explícito para comprobar revalidación dentro de la UoW y rechazo de evidencia manipulada. **Estas pruebas están pendientes de ejecución local.** El fake es solo test support; no constituye un verificador productivo ni compone login.
- `LocalConsoleRequestFactory` continúa creando identidad y `user_id` sintéticos desde el usuario Unix. Debe permanecer aislada de Workspace, Memory, Grants, Broker y cualquier capacidad protegida.

### 20.4 Orden de cierre

1. Cambiar `GrantManagementService.issue` para verificar `VerifiedIdentityContext` dentro de la UoW que inserta el Grant.
2. Revisar `revoke` con el coordinador de autoridad: la verificación de identidad debe estar ligada a la reserva/commit y al fencing de la operación, no solo al inicio.
3. Exigir evidencia USER verificable en Workspace dentro de la UoW de ejecución; no aceptar solo `OperationContext`.
4. Exigir evidencia USER verificable en Memory PRIVATE/PROJECT y conservar la distinción entre USER y AGENT delegado.
5. Mantener la consola sintética desconectada y cubrir pruebas negativas de caller/contexto fabricado.
6. Validar localmente carreras de suspensión/revocación frente a emisión, renovación, lectura y ejecución antes de conectar runtime.

**Límite:** revisión estática solamente. No se ejecutaron pruebas ni se modificó código ejecutable. La suite completa 1,611/1,611 (con un skip) fue validada por el propietario en la rama MVP, pero no demuestra fencing frente a cambios concurrentes de identidad/Grant ni integración protegida end-to-end.


## 21. Evidencia transaccional en Workspace read-only — 2026-11-22

Commit 0315d52db9505998244dace068828723bb5b424f endurece Workspace:

- El constructor exige un verificador con `verify_in_unit_of_work`; sin él no se puede construir el servicio.
- `execute` recibe explícitamente `VerifiedIdentityContext` y lo revalida dentro de la UoW compartida antes de consultar Workspace/Grant o resolver el mount.
- El par canónico devuelto por el verificador se compara además con el registro de Identity leído desde esa misma UoW.
- La API ya no acepta una mera coincidencia de `OperationContext` como prueba suficiente de autenticación.

Las pruebas del slice usan un fake de test y comprueban evidencia ausente en composición, revalidación transaccional y manipulación. **Pendiente de ejecutar en Debian.** No hay todavía composition root productivo que proporcione el verificador HMAC; por tanto, Workspace sigue sin estar habilitado en el runtime y la consola sintética permanece desconectada.
