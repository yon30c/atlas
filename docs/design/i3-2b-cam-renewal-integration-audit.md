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

### Relación Project/Environment — corrección de inspección

La asociación canónica **sí existe** desde `CORE_SCHEMA_V18` (`atlas_project_environments`). La implementan `ProjectEnvironmentAssociation`, `ProjectEnvironmentStatus` y `SQLiteWorkspaceRegistryRepository.get_association/create_association/update_association`. La clave compuesta es (project_id, environment_id), la identidad de la asociación es inmutable, tiene revisión CAS y estado active/suspended. La creación exige que Project y Environment existan; el workspace registry ya exige asociación activa al crear Workspaces.

La auditoría anterior se limitó incorrectamente a `SQLiteProjectEnvironmentRepository` y no siguió la autoridad del workspace registry. La renovación 6C resolvía Project y Environment pero omitía consultar la asociación existente. No hace falta nueva migración ni nuevo modelo: I3-2B.6E conecta la renovación a `uow.workspaces.get_association` dentro de la misma UoW y falla cerrada si la relación falta o está suspendida.

### Estado

- I3-2B.6B/6C: checkpoint validado por el propietario con 1,396 tests y compileall 0.
- I3-2B.6D: validado por el propietario en Debian con 1,397 tests y compileall 0.
- Project-Environment association: existe desde V18 y se exige en la ruta AGENT desde I3-2B.6E.
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

**Límites sin cambio:** no se habilitan endpoints, login ni runtime AGENT. La asociación canónica Project-Environment sí existe desde V18; la omisión de su consulta en la renovación se corrigió en 6E. PR #16 permanece Draft, abierto y sin fusionar.


### I3-2B.6E — exigir la asociación canónica Project/Environment

- `GrantRenewalService.request_renewal` exige ahora el repositorio `workspaces` en la UoW compartida.
- Después de resolver Project y Environment activos, consulta la asociación exacta por ambos IDs mediante `uow.workspaces.get_association`.
- La solicitud AGENT se deniega si la asociación no existe, está suspendida o sus IDs no coinciden exactamente.
- El puerto mínimo `ProjectEnvironmentAssociationReaderPort` hace explícita la dependencia del servicio y declara `get_association` como lectura dentro de la UoW compartida.
- Se prueba también que una UoW sin la autoridad `workspaces` falla cerrada.
- No se añadió migración: se reutiliza el contrato y la tabla V18 existentes.
- Se añadieron pruebas de servicio para asociación inexistente y suspendida, ambas sin escritura ni commit.

**Validación I3-2B.6E confirmada por el propietario en Debian:** suite completa **1,400 tests en 21.235 s — OK**; `python -m compileall -q src tests` → **COMPILE_EXIT_CODE=0**. El propietario validó el HEAD `b98c091243475d3c660e8b67e3414d53c6b31d98`.


### Seguimiento — I3-2B.6E validado por el propietario

El propietario confirmó en Debian, sobre el HEAD `b98c091243475d3c660e8b67e3414d53c6b31d98`:
- Suite completa: **1,400 tests en 21.235 s — OK**.
- `python -m compileall -q src tests`: **COMPILE_EXIT_CODE=0**.

La validación cubre la consulta transaccional de la asociación canónica Project/Environment y las denegaciones fail-closed añadidas para asociación inexistente, suspendida o autoridad ausente. No implica habilitar runtime AGENT, endpoints ni login.


## 12. I3-2B.7 — auditoría de lifecycle y revocación efectiva (17 de noviembre de 2026)

### Alcance y método

Auditoría estática de la rama `design/verified-agent-delegation-i3-2b` en el HEAD inspeccionado. Se siguieron:
- `CORE_SCHEMA_V18` y sus triggers para `atlas_project_environments` y `atlas_workspaces`.
- `ProjectEnvironmentAssociation`, `ProjectEnvironmentStatus` y `SQLiteWorkspaceRegistryRepository`.
- `GrantRenewalService.request_renewal/approve_renewal/reject_renewal`.
- `VerifiedAgentDelegationContextService` y la persistencia V24 de evidencia de renovación.
- Tests de lifecycle de la asociación y de decisiones de renovación.

Esta sección documenta comportamiento observado; no afirma validación de runtime ni introduce cambios de implementación.

### Hallazgos confirmados

**F1 — suspender la asociación no propaga el estado a Workspaces.**

`update_association` realiza CAS de estado/revisión y actualiza `updated_at`. No actualiza Workspaces asociados. V18 exige asociación ACTIVE al insertar un Workspace, pero no contiene trigger equivalente para una transición posterior ACTIVE → SUSPENDED. Por tanto, los Workspaces existentes conservan su estado ACTIVE. La asociación suspendida impide crear nuevos Workspaces, no demuestra por sí sola que todo consumidor de un Workspace existente vaya a denegar operaciones.

**F2 — la suspensión sí bloquea nuevas solicitudes AGENT de renovación, pero no decisiones pendientes.**

Desde 6E, `request_renewal` consulta la asociación exacta dentro de la UoW y exige estado ACTIVE. Sin embargo, `approve_renewal` vuelve a validar USER owner, solicitud PENDING, vínculo/revisión/vencimiento del Grant y vigencia del Grant, pero no consulta la asociación Project/Environment. Una solicitud AGENT creada antes de suspender la asociación todavía puede ser aprobada mientras el Grant siga vigente y su revisión no haya cambiado. La aprobación incrementaría la revisión y extendería el Grant a pesar de la suspensión.

**F3 — revocar la delegación después de la solicitud tampoco bloquea actualmente su aprobación.**

La solicitud V24 conserva `delegation_id` y `delegation_revision` inmutables, pero `approve_renewal` no carga ni revalida la delegación actual. La verificación de evidencia durante la solicitud no es una garantía permanente para la decisión posterior. Si la delegación se revoca o cambia después de crear la solicitud, el camino de aprobación actual no detecta ese cambio; la revocación no tiene efecto retroactivo sobre la solicitud pendiente.

**F4 — la revocación/suspensión no equivale a un cambio del Grant.**

La asociación Project/Environment, el Grant y la delegación son autoridades separadas. El estado de asociación no actualiza el Grant ni la delegación. La revocación de delegación tampoco modifica la solicitud V24. No hay en V18/V24 una cascada que convierta solicitudes PENDING en un estado terminal. El enum actual de renovación solo contiene PENDING, APPROVED y REJECTED.

**F5 — la asociación es reactivable y la transición no lleva actor/motivo en su registro.**

El dominio solo define ACTIVE/SUSPENDED; el trigger exige incremento exacto de revisión e identidad inmutable, pero no impone una máquina de estados terminal. `update_association` persiste estado, revisión y timestamp, no actor ni motivo. Esto limita la trazabilidad de quién suspendió/reactivó la relación y por qué, al menos en el registro canónico inspeccionado.

### Matriz del comportamiento actual

| Evento | Solicitud AGENT nueva | Solicitud AGENT ya PENDING |
|---|---|---|
| Asociación suspendida | DENY desde 6E | **Puede aprobarse actualmente**; F2 |
| Delegación revocada | DENY si se vuelve a verificar evidencia actual | **Puede aprobarse actualmente**; F3 |
| Grant revocado/expirado | DENY | La aprobación ya valida Grant vigente y deniega |
| Grant cambia de revisión | La nueva evidencia/delegación debe coincidir con Grant actual | La aprobación AGENT deniega revisión obsoleta |
| Asociación reactivada | Puede volver a pasar el gate de asociación | No hay invalidación terminal automática; sigue sujeto a las demás validaciones |

El rechazo USER owner debe seguir disponible para cerrar una solicitud PENDING aunque la asociación esté suspendida o la delegación haya sido revocada: rechazar no amplía autoridad ni modifica el Grant.

### Política recomendada para aprobación explícita

1. **Revalidación de asociación en el momento de aprobar.** Para toda solicitud con evidencia AGENT, exigir dentro de la misma UoW que la asociación canónica (Project, Environment) exista, permanezca ACTIVE y coincida exactamente con el Grant. No basta con haberla validado al solicitar.
2. **Revalidación de delegación en el momento de aprobar.** Para toda solicitud con `delegation_id`, exigir dentro de esa misma UoW que la delegación siga ACTIVE, coincida en ID/revisión, owner, AGENT, Grant/revisión, Project/Environment, issuer, acción `grant.renewal.request`, scope exacto y ventana temporal. Si fue revocada, sustituida o expiró, denegar aprobación.
3. **No cascada automática de autoridad por defecto.** Suspender una asociación no debe revocar silenciosamente Grants ni delegaciones: son autoridades separadas y la cascada podría destruir permisos ajenos a esta operación. La suspensión debe funcionar como gate de nuevas operaciones y decisiones que dependan de la asociación.
4. **No cambiar silenciosamente Workspaces existentes.** Mantener su estado histórico; cada consumidor que ejecute operaciones sobre ellos debe comprobar la asociación activa en su propio límite transaccional. Una futura política de suspensión/cascada de Workspaces requeriría identificar todos los consumidores y definir recuperación/reactivación.
5. **Solicitud PENDING preservada, aprobación bloqueada.** No convertir automáticamente una solicitud en REJECTED ni borrarla. Si asociación o delegación deja de estar vigente, mantener el registro PENDING para auditoría, denegar APPROVE y permitir al owner REJECT. Si se desea invalidación terminal automática, diseñar un estado explícito (por ejemplo CANCELLED/INVALIDATED), actor/motivo y reglas de concurrencia en una etapa separada.
6. **Auditoría de lifecycle.** Añadir una autoridad de transición que registre actor USER verificado, motivo, timestamp confiable, revisión anterior/nueva y decisión. El repositorio CAS debe permanecer como mecanismo de persistencia, no como sustituto de la autorización de la transición.

### Decisiones que requieren confirmación del propietario

- Adoptar los puntos 1–6 como política normativa para I3-2B.7.
- Confirmar si la reactivación de una asociación permite reanudar una solicitud PENDING que nunca fue aprobada, siempre que la delegación siga ACTIVE y vigente. La recomendación es sí, porque conserva el registro y no revive una delegación revocada.
- Confirmar si Workspaces existentes deben permanecer ACTIVE pero sujetos a gate de asociación en cada operación, o si se desea suspensión explícita en cascada.
- Definir quién puede suspender/reactivar una asociación y qué motivo es obligatorio.

### Estado

- Auditoría estática completada; no se modificó código, esquema ni datos.
- Hallazgos críticos F2 y F3 requieren resolver el gate de aprobación antes de considerar efectivo el lifecycle de revocación.
- No se atribuyen pruebas ejecutadas ni validación Debian a esta auditoría.
- PR #16 permanece Draft, abierto y sin fusionar.


## 13. I3-2B.7A — revalidación al aprobar (17 de noviembre de 2026)

Se implementó el cierre de los hallazgos F2/F3 para solicitudes AGENT:

- `approve_renewal` detecta solicitudes con `delegation_id` y vuelve a leer la delegación canónica dentro de la misma UoW que actualiza Grant y solicitud.
- Exige delegación ACTIVE, misma revisión registrada, ventana temporal vigente, mismo owner, AGENT, Grant/revisión, Project/Environment, resource type y conjunto exacto de recursos.
- Exige `grant.renewal.request` tanto en la delegación como en el Grant.
- Revalida identidad USER owner y AGENT canónicas, ambas ACTIVE, y binding nativo AGENT/issuer activo.
- Revalida Project y Environment activos y la asociación exacta ACTIVE.
- Para solicitudes AGENT usa el reloj confiable inyectado para la ventana temporal y `decided_at`; el parámetro legacy `now` no decide la autorización temporal.
- Si falta cualquier autoridad o la revalidación falla, la aprobación falla cerrada antes de escribir.
- La solicitud sigue PENDING ante una denegación; el rechazo USER owner no consulta asociación/delegación y permanece disponible.
- La ruta de renovaciones históricas sin `delegation_id` conserva su comportamiento previo; la nueva revalidación estricta aplica a solicitudes AGENT identificadas por evidencia V24.

Tests añadidos en `tests/unit/test_agent_renewal_approval_lifecycle.py`:
- aprobación válida con autoridades activas;
- asociación suspendida;
- delegación revocada;
- revisión de delegación cambiada;
- binding nativo inactivo;
- scope parcial/cambiado;
- rechazo USER owner permitido incluso después de suspensión y revocación;
- reloj confiable ausente: aprobación AGENT fail-closed.

**Validación confirmada por el propietario en Debian (HEAD `8f65c3646987a2402ecd089f9b426568f60f2ec2`):** suite completa **1,413 tests en 22.259 s — OK**; `python -m compileall -q src tests` → **COMPILE_EXIT_CODE=0**. La suite incluye los ocho casos de lifecycle añadidos para I3-2B.7A. Esta evidencia procede de la ejecución reportada por el propietario; no implica que GitHub Actions/CI haya corrido.

### Límites deliberados

- No se propagan suspensiones a Workspaces existentes.
- No se revocan Grants ni delegaciones automáticamente.
- No se añade todavía autoridad de lifecycle para suspender/reactivar asociaciones ni un ledger de actor/motivo. Esa es la siguiente parte de I3-2B.7 y requiere un contrato explícito de autorización: el servicio no debe asumir que cualquier USER autenticado puede administrar asociaciones.


### Validación I3-2B.7A — confirmada por el propietario

Sobre el HEAD `8f65c3646987a2402ecd089f9b426568f60f2ec2`, el propietario ejecutó en Debian:
- Suite completa: **1,413 tests en 22.259 s — OK**.
- `python -m compileall -q src tests`: **COMPILE_EXIT_CODE=0**.

La validación incluye la suite `tests/unit/test_agent_renewal_approval_lifecycle.py`, incluida la corrección de los dos tests que preparaban el fixture `SimpleNamespace` mediante `dataclasses.replace`. No se afirma ejecución de CI. I3-2B.7A queda validada por el propietario en Debian.


## 14. I3-2B.7B — auditoría de autoridad para lifecycle Project/Environment

**Estado:** inspección de diseño completada; implementación de transiciones suspend/reactivate aún no iniciada.  
**Base inspeccionada:** commit `2fe3386535a29a89075998c82f46401eba5c90bf` (incluye el registro de validación 7A).

### 14.1 Comportamiento actual confirmado

- `ProjectEnvironmentAssociation` contiene únicamente `project_id`, `environment_id`, `status` y `revision`. No conserva actor, motivo ni timestamp de la decisión.
- `SQLiteWorkspaceRegistryRepository.update_association` acepta directamente una asociación y `expected_revision`; ejecuta CAS y escribe `updated_at` usando el reloj del sistema dentro del adaptador. No recibe `OperationContext`, evidencia USER verificada, política de autorización ni motivo.
- El puerto `ProjectEnvironmentAssociationPort` expone `update_association` como mutación de persistencia, sin distinguir una operación autorizada de un cambio administrativo interno.
- El modelo de asociación permite ACTIVE ↔ SUSPENDED y el repositorio no define por sí mismo quién puede realizar ninguna de las dos transiciones.
- No se encontró un servicio de aplicación dedicado a suspender/reactivar asociaciones dentro de `src/atlas/workspace`. El repositorio es una primitiva de persistencia, no una frontera de autorización.
- `SQLiteAuthorityChangeStore` es una infraestructura genérica de reserva/idempotencia y declara expresamente que no es el coordinador de autoridad. No se debe reutilizar como si autorizara o ejecutara por sí solo el lifecycle de Project/Environment.

### 14.2 Consumers y gate de asociación

- `WorkspaceCapabilityExecutionService.execute` lee la asociación exacta dentro de `SQLiteLocalAuthorityUnitOfWork` y exige ACTIVE antes de resolver el mount y ejecutar listado/lectura. Este es el gate de ejecución observado para esas capacidades.
- `WorkspaceListingService`, `WorkspaceFileReadingService` y `WorkspaceFileWritingService` son coordinadores de adaptadores de bajo nivel; no validan identidad, asociación ni CAM por sí solos. No deben exponerse como fronteras de capacidad protegida.
- `LocalWorkspaceWriteAdapter` declara expresamente que no sustituye CAM ni coordina autoridad. Su uso debe permanecer detrás de una frontera de aplicación autorizada.
- Los Workspaces existentes no se modifican automáticamente al suspender la asociación. Los consumidores protegidos deben seguir comprobando la asociación activa dentro de su propia frontera transaccional.

### 14.3 Contrato técnico propuesto para 7B

La transición debe componerse en una sola UoW SQLite local y fallar cerrada:

1. Recibir una solicitud explícita con Project/Environment, estado destino, `expected_revision`, motivo y `OperationContext`; no aceptar actor, owner ni timestamp como claims libres.
2. Verificar identidad USER y evidencia verificada con `verify_in_unit_of_work(context, unit)` dentro de la UoW.
3. Leer asociación canónica y comprobar identidad exacta, estado actual, revisión esperada y transición permitida.
4. Exigir un puerto de autorización específico de lifecycle, por ejemplo `ProjectEnvironmentAssociationLifecycleAuthorizerPort`. La ausencia de implementación o una decisión no-ALLOW debe denegar. No crear un authorizer permisivo por defecto.
5. Obtener timestamp exclusivamente de un `Clock` confiable inyectado.
6. Persistir un evento inmutable con asociación, estado anterior/nuevo, revisión anterior/nueva, actor USER canónico, motivo, timestamp confiable y referencia de contexto.
7. Ejecutar CAS de la asociación y escribir evento dentro de la misma UoW; cualquier fallo debe revertir ambos.
8. Rechazar transición redundante, revisión obsoleta, motivo vacío, actor no USER, identidad inactiva/no verificada o falta de política.

### 14.4 Integridad de persistencia propuesta

Se recomienda una migración aditiva (siguiente versión disponible después de V24) para un ledger de lifecycle dedicado, sin alterar el significado de V18:

- FK a la asociación compuesta y a la identidad USER canónica.
- estado anterior/nuevo restringidos a ACTIVE/SUSPENDED;
- revisiones positivas y consecutivas;
- motivo obligatorio y normalizado;
- timestamp UTC;
- unicidad por asociación y revisión resultante;
- triggers que impidan UPDATE/DELETE de eventos;
- trigger que exija un evento compatible para cada cambio de estado de la asociación, evitando que una escritura directa omita la auditoría;
- evento y cambio canónico dentro de la misma transacción.

La creación inicial de la asociación debe conservar una semántica separada; este ledger cubre transiciones posteriores ACTIVE ↔ SUSPENDED. No se deben inventar actor ni motivo para filas históricas.

### 14.5 Decisión de autorización aún necesaria

El repositorio no define si la autoridad corresponde al propietario USER del Project, a un administrador de plataforma, a un rol organizacional o a una combinación. No hay evidencia suficiente para escoger una de esas políticas.

Por seguridad, 7B no debe conceder la transición a cualquier USER autenticado ni inferir autoridad de `context.user_id`, `origin`, pertenencia a un Project o posesión de un Grant ordinario. El puerto específico propuesto deja esta política explícita y fail-closed hasta que se defina una autoridad concreta.

### Estado de 7B

- Auditoría estática y contrato técnico propuesto completados.
- No se modificó código productivo ni esquema.
- No se afirma validación de tests ni CI para 7B.
- 7A permanece validada por el propietario: 1,413 tests OK y compileall exit 0 sobre HEAD `8f65c3646987a2402ecd089f9b426568f60f2ec2`.
- PR #16 permanece Draft, abierto y sin fusionar.
