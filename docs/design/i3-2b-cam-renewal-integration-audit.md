# I3-2B.6A — auditoría de integración CAM para solicitudes AGENT de renovación

**Estado:** auditoría de diseño; no habilita solicitudes AGENT ni modifica código productivo.  
**Base inspeccionada:** rama design/verified-agent-delegation-i3-2b, PR #16.  
**Validación previa:** el propietario confirmó 1,369/1,369 tests y compileall exit 0 para I3-2B.5.  
**Decisión de seguridad:** identidad AGENT, consentimiento delegado y decisión CAM son tres verificaciones independientes.

## 1. Resultado ejecutivo

I3-2B.5 aporta evidencia AGENT y de delegación verificable. La composición SQLite actual ofrece una UoW que agrupa las autoridades y repositorios necesarios: Identity, AGENT, native bindings, delegaciones, Grants, renovaciones y Project/Environment.

Esto permite diseñar una solicitud bajo una transacción local compartida, pero no equivale a una autorización CAM ni a un coordinador genérico de admisión/fencing.

Se identificó un bloqueo de alcance: AgentDelegationScope permite delegar un subconjunto del Grant, mientras que GrantRenewalRequest solo solicita cambiar la expiración del Grant completo. Permitir que una delegación parcial solicite la renovación del Grant entero daría al AGENT capacidad para iniciar una decisión sobre permisos que no recibió en delegación. La primera integración debe denegar ese caso.

## 2. CAM existente: comportamiento real

### 2.1 Evaluador

AuthorizationEvaluator.evaluate(request, grants, now) es una función pura. Para devolver ALLOW exige, entre otras cosas:

- actor ACTIVE;
- grant.subject_identity_id igual a context.actor.identity_id;
- owner del recurso igual a grant.owner_user_id;
- project y environment exactos;
- resource_type, resource_id y action exactos;
- Grant vigente y no revocado.

No valida VerifiedAgentIdentityContext, VerifiedAgentDelegationContext, attestation, issuer, binding ni consentimiento del propietario. Tampoco produce por sí solo una admisión transaccional. Es el evaluador de una política CAM, no un autenticador ni una autoridad de delegación.

### 2.2 Precedente de ejecución

WorkspaceCapabilityExecutionService demuestra el patrón de ejecución local: abre SQLiteLocalAuthorityUnitOfWork, resuelve identidad y metadatos canónicos, construye AuthorizationRequest, evalúa el Grant exacto y mantiene la UoW durante el efecto.

Ese servicio rechaza expresamente cualquier actor distinto de USER y cualquier DelegationMode. No debe ampliarse para admitir AGENT; su política de workspace sigue siendo USER-direct.

MemoryAuthorizationService es una política específica de Memory, con reglas adicionales de propietario, clasificación y snapshots. No es un autorizador genérico reutilizable para renovación de Grants.

## 3. Frontera transaccional disponible

SQLiteLocalAuthorityUnitOfWork extiende SQLiteAuthorizationUnitOfWork y crea repositorios sobre la misma SQLiteUnitOfWork:

- Identity USER y AGENT;
- native identity y native AGENT binding;
- delegaciones AGENT;
- Grants y solicitudes de renovación;
- Project/Environment;
- authority-change ledger y otros registros locales.

La factory usa una única instancia SQLiteDatabase. Los verificadores USER y AGENT y el verificador de delegación ofrecen variantes verify_in_unit_of_work para participar en la transacción recibida.

Esto permite que una futura solicitud lea y revalide evidencia, delegación, Grant y Project/Environment, evalúe CAM y persista la renovación dentro de la misma transacción SQLite.

**Límite:** esta garantía solo existe si el composition root inyecta la misma base y todos los caminos de mutación relevantes la respetan. No implementa el coordinador general de invalidación/admisión/fencing descrito en F2.3.4 ni garantiza consistencia con sistemas externos. No afirmar atomicidad distribuida.

La integración debe usar SQLiteLocalAuthorityUnitOfWorkFactory, no una factory aislada que no exponga las autoridades AGENT y la delegación.

## 4. Hallazgo crítico: delegación parcial frente a renovación completa

El modelo actual permite:
- AgentDelegationScope.resource_ids y actions como subconjuntos del Grant;
- GrantRenewalRequest con grant_id, owner, subject, requester, vencimiento actual y propuesto;
- approve_renewal actualiza Grant.expires_at del Grant completo; no recibe ni aplica un scope parcial.

Por tanto, una delegación limitada a un recurso o a unas acciones podría permitir solicitar la extensión temporal de un Grant con más recursos/acciones. Aunque la decisión final siga siendo del propietario, el AGENT habría podido iniciar una solicitud fuera del alcance delegado.

### Gate obligatorio para la primera versión

La solicitud AGENT solo podrá continuar si:
1. delegation.grant_id == grant.grant_id y delegation.grant_revision == grant.revision;
2. delegation.scope.resource_type == grant.resource_type;
3. delegation.scope.resource_ids == grant.resource_ids (cobertura exacta del conjunto completo);
4. grant.renewal.request aparece explícitamente tanto en grant.actions como en delegation.scope.actions;
5. el AGENT no puede cambiar scope, acciones, owner, subject ni vencimiento actual del Grant.

La delegación puede limitar sus acciones a la acción de solicitar renovación; no necesita recibir todas las acciones operativas del Grant. Pero no puede tener cobertura de recursos menor mientras la solicitud/decisión siga extendiendo el Grant completo.

Alternativa futura, fuera del primer slice: modelar solicitudes de renovación de un subconjunto y que la aprobación del propietario emita un Grant nuevo y acotado. El modelo actual de renovación no soporta esa semántica.

## 5. Semántica CAM propuesta

La acción `grant.renewal.request` fue incorporada explícitamente en I3-2B.6B y se exige tanto en el Grant como en la delegación. No se infiere de DelegationMode.DELEGATED.

Para reutilizar el evaluador actual sin convertir la delegación en ALLOW:
1. Definir una constante de dominio grant.renewal.request.
2. Construir un AuthorizationRequest con actor AGENT autenticado, owner canónico, project/environment del Grant, resource_type=grant.resource_type y la acción explícita.
3. Evaluar el Grant objetivo exacto, no una lista caller-supplied ni un Grant distinto del solicitado.
4. Evaluar cada resource_id de grant.resource_ids; todos deben devolver ALLOW y matched_grant debe ser el mismo grant_id + revision.
5. Exigir la coincidencia de la acción y de todos los recursos con el scope de la delegación verificada.

Así, CAM comprueba el permiso sobre cada recurso real cubierto por el Grant. No se debe usar resource_type="grant" y resource_id=grant_id salvo que el modelo de permisos defina expresamente que los Grants son recursos autorizables; hoy GrantResourceScope representa recursos del permiso, no necesariamente el propio Grant.

Esta propuesta necesita aprobación como semántica de producto antes de implementar el slice. La acción nueva debe ser emitida explícitamente al crear Grants; los Grants históricos que no la incluyan deben denegar renovación AGENT.

## 6. Contrato de contexto delegado

Antes de CAM, la operación debe exigir simultáneamente:
- context.actor.kind == AGENT y estado ACTIVE;
- context.delegation == DelegationMode.DELEGATED;
- context.actor.identity_id igual al AGENT canónico devuelto por el verificador;
- context.user_id == verified_delegation.owner_user_id;
- project/environment del contexto iguales a los de Grant y delegación;
- verified_delegation.agent_identity_id, grant_id, grant_revision, delegation_id y revisiones exactas coincidentes;
- revalidación de VerifiedAgentIdentityContext y VerifiedAgentDelegationContext dentro de la misma UoW que lee el Grant y escribe la solicitud.

user_id en OperationContext es metadata caller-controlled; solo se acepta después de compararlo con el owner incluido en la evidencia de delegación revalidada. No convierte al AGENT en USER ni crea un CanonicalUserIdentity.

## 7. Cambios de modelo requeridos antes de habilitar

GrantRenewalRequest no conserva hoy la revisión del Grant al momento de solicitar ni el identificador/revisión de la delegación que permitió la solicitud.

El slice de integración debe añadir claims de auditoría inmutables y persistidos:
- grant_revision: revisión exacta autorizada al solicitar;
- delegation_id y delegation_revision: mandato exacto que cubrió la solicitud;
- requested_by_identity_id: AGENT canónico, nunca tomado de un campo libre del caller.

La aprobación/rechazo USER debe seguir siendo owner-only. En aprobación, revalidar que el Grant conserve la revisión y vencimiento capturados por la solicitud; luego actualizar Grant y solicitud en una misma UoW. La aprobación no debe requerir que la delegación siga vigente: el decisor es el propietario USER autenticado, no el AGENT.

También debe definirse idempotencia de renewal_id y si se permite más de una solicitud PENDING por Grant. La primera implementación debe rechazar duplicados incompatibles, no crear solicitudes paralelas ambiguas.

## 8. Implementación

### I3-2B.6A — Auditoría CAM
Auditoría documental completada. El usuario aprobó la política conservadora: cobertura exacta de recursos, acción explícita en Grant/delegación y decisiones USER owner-only.

### I3-2B.6B — Contrato y pruebas CAM (implementado; checkpoint validado por el propietario)
- Nuevo módulo `src/atlas/authorization/agent_renewal_policy.py` define `grant.renewal.request`.
- Exige contexto AGENT activo con `DelegationMode.DELEGATED` y evidencia AGENT/delegación coincidente.
- Exige que la delegación cubra exactamente todos los `resource_ids` del Grant y que la acción esté explícita en ambos.
- Ejecuta `AuthorizationEvaluator` para cada recurso y exige ALLOW del mismo Grant y revisión.
- Tests cubren scope parcial, acción ausente, actor/owner/project/environment, binding/revisiones, Grant expirado/revocado y evaluación de todos los recursos.

### I3-2B.6C — Solicitud AGENT bajo UoW compartida (implementado; checkpoint validado por el propietario)
- `GrantRenewalService` recibe verificadores AGENT/delegación, reloj confiable y CAM evaluator por composición.
- Revalida evidencia AGENT y `VerifiedAgentDelegationContext` dentro de la misma UoW local.
- Resuelve Grant y Project/Environment canónicos dentro de esa UoW y ejecuta CAM antes de escribir.
- La hora de solicitud proviene exclusivamente de `Clock`; el argumento legacy `now` se ignora.
- La solicitud persiste `grant_revision`, `delegation_id` y `delegation_revision` inmutables. `CORE_SCHEMA_V24` agrega columnas, FK, triggers de integridad y validación de coincidencia con Grant/delegación/issuer/binding activos.
- Se admite una sola solicitud PENDING por Grant. `renewal_id` es idempotente para la misma intención y rechaza reutilización conflictiva.
- `approve_renewal` sigue exigiendo USER owner verificado y rechaza una revisión de Grant obsoleta. AGENT no puede aprobar ni rechazar.
- No se altera el Grant al solicitar; la solicitud y las verificaciones se confirman en una única transacción SQLite local.

## 9. Pruebas obligatorias y cobertura añadida

- AGENT válido sin delegación, delegación revocada/expirada o revisión obsoleta: DENY sin escritura.
- Contexto USER presentado en ruta AGENT o viceversa: DENY.
- owner, AGENT, Grant, issuer, binding, project o environment mismatch: DENY.
- acción ausente de Grant o delegación: DENY.
- recurso fuera de Grant/delegación o delegación parcial: DENY.
- Grant expirado/revocado o revisión cambiada: DENY.
- `context.user_id` alterado respecto del owner verificado: DENY.
- CAM ALLOW para otro Grant no satisface el Grant solicitado.
- duplicado de `renewal_id` o PENDING incompatible: idempotencia y sin doble escritura.
- rollback antes de commit ante cualquier fallo.
- aprobación/rechazo por AGENT: DENY; solo USER owner verificado puede decidir.
- la solicitud no cambia `Grant.expires_at`; solo la aprobación USER puede hacerlo.

**Checkpoint Debian de I3-2B.6B/6C confirmado por el propietario:** 1,396 tests OK y `compileall` exit 0. La validación es anterior al endurecimiento 6D documentado en la sección 11; el HEAD actual requiere nueva validación.

## 10. Estado y conclusión

- I3-2B.5: validado por el propietario con 1,369 tests y `compileall` exit 0.
- I3-2B.6A: auditoría documental completada y política aprobada por el usuario.
- I3-2B.6B/6C: implementación completada en la rama; validación Debian pendiente.
- `GrantRenewalService.request_renewal`: ya no está globalmente fail-closed; solo admite el camino AGENT con evidencia verificable, CAM ALLOW y UoW local compartida. Sin configuración/evidencia válida, deniega.
- No se habilitó login, endpoint ni runtime AGENT.
- No se ha fusionado PR #16.

La primera versión deniega deliberadamente cualquier delegación con cobertura parcial, y los Grants históricos sin la acción explícita `grant.renewal.request` no pueden iniciar solicitudes AGENT.

## 11. Seguimiento — 17 de noviembre de 2026

### Validación del checkpoint I3-2B.6B/6C

El propietario ejecutó en Debian sobre el checkpoint anterior a este endurecimiento adicional:

- Suite completa: **1,396 tests, OK** (22.894 s).
- `python -m compileall -q src tests`: **COMPILE_EXIT_CODE=0**.

Esta evidencia valida el checkpoint 6B/6C informado por el propietario. No debe atribuirse automáticamente a los commits posteriores de I3-2B.6D descritos abajo; esos cambios requieren una nueva validación focalizada y luego la suite completa.

### I3-2B.6D — revalidación USER owner dentro de la UoW

La revisión posterior detectó que `approve_renewal` y `reject_renewal` llamaban al verificador USER standalone antes de abrir la UoW. Eso dejaba la validación de identidad fuera de la transacción que lee la solicitud/Grant y escribe la decisión.

Cambio aplicado en la rama:
- El puerto `VerifiedIdentityContextVerifierPort` declara `verify_in_unit_of_work(context, unit)`.
- `identity_evidence.py` añade una validación owner USER que exige el método transaccional, compara identidad canónica, tipo USER, estado ACTIVE, revisiones, UserId, actor y ausencia de delegación.
- `approve_renewal` y `reject_renewal` abren primero la UoW y revalidan la evidencia USER mediante la misma UoW antes de leer y decidir la renovación.
- Si el verificador no implementa la ruta compartida, la operación falla cerrada.
- Los tests verifican que no se invoque el método standalone y que ambas decisiones usen la ruta transaccional; se añadió un caso para verificador legacy-only.

**Validación de I3-2B.6D pendiente:** los tests y compileall deben ejecutarse en Debian sobre el HEAD actualizado.

### Relación Project/Environment — resultado de inspección

El adaptador canónico actual expone `get_project(project_id)` y `get_environment(environment_id)` sobre catálogos separados (`atlas_projects` y `atlas_environments`). Los modelos recuperados solo contienen identificador, estado y revisión; no existe una tabla, clave o contrato de asociación Project-Environment en esta capa.

Por tanto, 6C puede comprobar que ambos registros existen, están activos y coinciden con los IDs del Grant, pero no puede afirmar que el Environment pertenezca al Project. No se añadió una asociación implícita ni una regla ad hoc. Si el producto requiere esa relación, deberá modelarse explícitamente —incluyendo migración, autoridad/puerto, reglas de lifecycle y pruebas— antes de hacerla obligatoria en la renovación.

### Estado

- I3-2B.6B/6C: checkpoint validado por el propietario con 1,396 tests y compileall 0.
- I3-2B.6D: implementación publicada en la rama; validación pendiente.
- Project-Environment association: no representada por el modelo canónico actual; decisión de diseño pendiente.
- PR #16 continúa Draft, abierto y sin fusionar.


### 11. Seguimiento — 17 de noviembre de 2026 (actualización)

#### I3-2B.6B/6C — validación confirmada

El propietario confirmó en Debian:
- Suite completa: **1,396 tests en 22.894 s — OK**.
- `python -m compileall -q src tests`: **COMPILE_EXIT_CODE=0**.

#### I3-2B.6D — validación confirmada

Tras implementar la revalidación USER owner dentro de la misma UoW para `approve_renewal` y `reject_renewal`, el propietario confirmó:
- Suite completa: **1,397 tests en 21.871 s — OK**.
- `python -m compileall -q src tests`: **COMPILE_EXIT_CODE=0**.

El servicio productivo `VerifiedIdentityContextService` ya implementa `verify_in_unit_of_work(context, unit)`: valida attestation, TTL, issuer, binding y revisión canónica USER mediante los repositorios de la UoW recibida, sin abrir ni confirmar la transacción del caller. Por tanto, 6D no queda limitado al fake de tests.

**Estado de validación:** I3-2B.6B/6C y 6D están validados por el propietario en Debian. La evidencia se refiere al HEAD correspondiente a los cambios 6D reportados; confirmar SHA local/remoto antes de etiquetar releases o habilitar runtime.

**Límites sin cambio:** no se ha modelado una asociación canónica Project-Environment; no se habilitan endpoints, login ni runtime AGENT. PR #16 permanece Draft, abierto y sin fusionar.
