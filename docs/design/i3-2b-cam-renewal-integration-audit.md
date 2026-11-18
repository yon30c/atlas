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


## 15. I3-2B.7B — política de autoridad aprobada y prerequisite de provisioning

**Decisión del propietario (17 de noviembre de 2026):** las transiciones ACTIVE ↔ SUSPENDED de una asociación Project/Environment corresponden exclusivamente a un USER con autoridad administrativa de plataforma explícita y verificable. La autorización debe ser específica para `association.suspend` o `association.reactivate`.

### Política normativa aprobada

- USER propietario del Project: no obtiene autoridad de lifecycle por ser propietario.
- USER ordinario: denegado.
- AGENT: siempre denegado.
- USER administrador de plataforma: puede ejecutar únicamente las operaciones explícitamente concedidas y vigentes.
- La identidad USER, la autoridad administrativa y la operación deben verificarse contra registros canónicos dentro de la misma UoW.
- No se aceptan claims del cliente, flags, `origin`, pertenencia al Project ni Grants ordinarios como prueba de administración.
- Se conserva el requisito de motivo obligatorio, reloj confiable, expected_revision/CAS y ledger inmutable.
- La transición de estado y el evento de auditoría se confirman en una única transacción.
- La ausencia de la autoridad administrativa, su repositorio o su implementación produce DENY. No hay fallback permisivo.
- No se crean administradores por defecto ni se elevan privilegios de identidades existentes.

### Hallazgo adicional: falta la autoridad canónica de administración

La inspección de `src/atlas` no encontró un modelo, repositorio ni servicio de asignación de roles de administrador de plataforma. Las autoridades USER existentes verifican identidad y binding, pero no representan privilegios administrativos globales. `SQLiteAuthorityChangeStore` tampoco es una autoridad de roles ni un autorizador.

Por tanto, no es seguro implementar un adaptador productivo que derive el privilegio de un atributo de `OperationContext`, del estado USER o de una tabla improvisada sin un contrato de provisioning y revocación. Un puerto aislado con un fake de tests no sería una implementación de producción.

### Plan técnico adoptado para continuar sin ampliar privilegios

1. Introducir una autoridad canónica dedicada para asignaciones administrativas de plataforma, con permisos separados para `association.suspend` y `association.reactivate`, estado/revisión y lectura dentro de la UoW.
2. Mantener el registro inicialmente vacío: esta etapa no provisiona ni promueve ninguna identidad.
3. Definir el provisioning inicial como una operación de bootstrap confiable, fuera de endpoints de usuario/AGENT y fuera de la API normal de lifecycle. El procedimiento deberá tener su propio contrato, evidencia, actor raíz y auditoría antes de habilitarse.
4. Implementar el servicio de lifecycle para requerir tanto el verificador USER transaccional como el autorizador específico; sin ambos, toda transición queda denegada.
5. Añadir ledger inmutable y triggers que exijan el evento correspondiente para cada cambio de estado; el cambio directo del repositorio no podrá omitir la auditoría.
6. No habilitar runtime ni conceder autoridad administrativa hasta que exista y se valide el bootstrap explícito.

### Decisión operativa pendiente antes de habilitar el primer administrador

La recomendación es **bootstrap offline, explícito y controlado por el operador de plataforma**, separado del flujo normal de usuarios. No se debe insertar un administrador por defecto ni asumir que el propietario actual del sistema es automáticamente administrador de Atlas.

El contrato y el diseño de la autoridad pueden prepararse sin conceder privilegios; la operación real permanecerá fail-closed hasta que se implemente y apruebe ese bootstrap.

### Estado

- Política de autorización aprobada por el propietario.
- Ausencia de autoridad canónica de administrador confirmada por inspección estática del árbol `src/atlas`.
- No se ha añadido código, migración ni asignación de privilegios en esta actualización.
- No se afirma ejecución de tests ni CI para esta actualización.
- PR #16 permanece Draft, abierto y sin fusionar.

## 15. I3-2B.7B — política de administración y bootstrap offline (decisión aprobada)

**Estado:** política aprobada por el propietario; contrato de implementación documentado. La implementación de código y su validación todavía no se declaran completadas.

### 15.1 Autoridad administrativa

Solo una identidad canónica USER que posea una concesión administrativa de plataforma vigente y verificable podrá ejecutar transiciones de asociaciones Project/Environment.

La concesión debe autorizar explícitamente cada acción:
- `association.suspend`
- `association.reactivate`

No se infiere autoridad administrativa de:
- ser propietario del Project;
- estar autenticado como USER;
- pertenecer al Project o tener un Grant;
- campos de contexto enviados por el caller;
- roles o booleanos declarados por el cliente;
- identidad AGENT o delegación.

La ausencia, revocación, expiración, revisión obsoleta o imposibilidad de verificar la autoridad produce DENY. No existe fallback permisivo.

### 15.2 Bootstrap del primer administrador

El propietario confirma que el primer administrador se provisionará mediante un procedimiento **offline, explícito y controlado por el operador**.

El bootstrap:
- se ejecuta fuera de endpoints y flujos de usuario ordinarios;
- requiere acceso operativo local al entorno de confianza y una identidad USER canónica ya existente y activa;
- no crea una identidad USER ni cambia su identidad, autenticación o estado;
- no usa un endpoint público, una petición de cliente, una variable booleana ni una cuenta predeterminada;
- crea una concesión administrativa auditable y limitada a las acciones explícitas autorizadas;
- es idempotente para el mismo sujeto/alcance y rechaza conflictos;
- no expone secretos ni credenciales administrativas en logs, argumentos de proceso o archivos versionados;
- no se ejecuta automáticamente durante el arranque, migraciones, instalación o composición normal;
- requiere validación operativa separada antes de habilitar cualquier composición que dependa de esa autoridad.

El procedimiento concreto de bootstrap y su interfaz operativa deben definirse antes de habilitarlo. No se ejecutará sobre la base productiva como parte de esta PR.

### 15.3 Contrato de transición

Una futura operación de lifecycle debe recibir únicamente intención:
- ProjectId y EnvironmentId;
- estado objetivo ACTIVE/SUSPENDED;
- expected_revision;
- motivo obligatorio normalizado;
- OperationContext y VerifiedIdentityContext como evidencia, nunca como claims autoautenticados.

Dentro de una sola SQLiteLocalAuthorityUnitOfWork debe:
1. revalidar identidad USER canónica con `verify_in_unit_of_work`;
2. rechazar AGENT, delegación presente, identidad inactiva o discrepancias actor/UserId;
3. leer la asociación canónica y comprobar IDs, estado y expected_revision;
4. consultar una autoridad administrativa canónica dentro de la misma UoW;
5. exigir el permiso exacto `association.suspend` o `association.reactivate`;
6. obtener tiempo UTC exclusivamente de Clock inyectado;
7. aplicar transición no redundante con revisión exactamente +1 mediante CAS;
8. insertar el evento inmutable con actor USER canónico, estado anterior/nuevo, revisiones anterior/nueva, motivo, timestamp confiable y referencia de contexto;
9. confirmar asociación y evento en la misma transacción.

Cualquier ausencia de repositorio, autoridad, verificador, reloj o evidencia, cualquier discrepancia o cualquier error de persistencia debe abortar la transacción completa.

### 15.4 Ledger y protección de persistencia

La migración siguiente a V24 debe añadir un ledger dedicado de lifecycle, no reutilizar `authority_changes` como coordinador de autorización.

El ledger debe:
- referenciar la asociación mediante su clave compuesta;
- referenciar la identidad USER canónica;
- registrar transición, revisiones consecutivas, motivo normalizado y timestamp UTC;
- imponer unicidad por asociación/revisión;
- impedir UPDATE y DELETE de eventos;
- imponer que toda transición de estado de asociación tenga exactamente un evento compatible dentro de la transacción.

La semántica de creación inicial de asociaciones se mantiene separada: no se inventará actor ni motivo retrospectivo para asociaciones preexistentes. El ledger registra transiciones posteriores a la migración.

### 15.5 Límite de seguridad y alcance

El bootstrap offline no es una API administrativa ni una operación de runtime. La concesión de administrador no se autoconcede, no se amplía por defecto y no se hereda desde propiedad o Grants. La revocación administrativa deberá ser explícita, auditable y protegida por un procedimiento de gobernanza separado.

No se añade cascada automática a Grants, delegaciones ni Workspaces. Los consumidores protegidos deben continuar comprobando asociación ACTIVE en su propia frontera transaccional.

**Checkpoint:** decisión del propietario recibida. Aún no hay implementación, migración, pruebas ni validación Debian para I3-2B.7B.

## 16. I3-2B.7B.1 — contratos de dominio de autoridad administrativa

**Estado:** contratos de dominio y puertos iniciales implementados; persistencia, bootstrap operativo y servicio lifecycle todavía pendientes.

Archivos añadidos:
- `src/atlas/core/platform_admin.py`
- `src/atlas/ports/platform_admin_authority.py`
- `tests/unit/test_platform_admin_domain_contracts.py`

### 16.1 Modelo

`PlatformAdminGrant` vincula una concesión a:
- UserId e Identity(USER) canónicos UUIDv4;
- revisión exacta de Identity(USER);
- conjunto no vacío de permisos enumerados y no wildcard;
- método de provisión explícito `OFFLINE_BOOTSTRAP`;
- identificador UUIDv4 del evento de bootstrap;
- ventana temporal UTC;
- estado ACTIVE/REVOKED, revisión y datos obligatorios de revocación.

Los únicos permisos definidos en este corte son `association.suspend` y `association.reactivate`. No existe permiso administrativo general ni herencia implícita.

`require_platform_admin_permission` comprueba el permiso exacto, sujeto, identidad, revisión y ventana temporal. Esta función solo comprueba claims del grant: **no autentica al actor ni sustituye la relectura de identidad USER y autoridad canónica dentro de la misma UoW**. Su consumidor transaccional debe hacer esas comprobaciones y convertir cualquier ausencia/discrepancia en DENY.

### 16.2 Separación de capacidades

`PlatformAdminAuthorityReaderPort` es read-only y se limita a resolver grants canónicos, incluidos tombstones revocados.

`PlatformAdminBootstrapPort` separa la capacidad de provisión inicial y expone únicamente `provision_first_admin`. Su contrato exige que la implementación sea cableada exclusivamente a un comando offline operado localmente; no debe inyectarse en servicios HTTP, composición runtime ni solicitudes de usuario. La implementación y sus controles de despliegue aún no existen.

### 16.3 Límites deliberados de este corte

- No se ha creado ni concedido ninguna autoridad administrativa real.
- No hay migración SQLite ni tabla de grants todavía.
- No hay adapter de persistencia ni composición UoW todavía.
- No hay servicio de suspensión/reactivación todavía.
- No se ha cambiado el repositorio de asociaciones ni se ha debilitado su protección.
- No se afirma que las pruebas hayan sido ejecutadas en Debian; el nuevo archivo de pruebas queda preparado para validación del propietario.

**Siguiente:** revisar/validar 7B.1 en Debian; después diseñar persistencia y bootstrap offline en 7B.2, manteniendo el bootstrap fuera de runtime.


## 17. I3-2B.7B.1 — validación Debian confirmada (17 de noviembre de 2026)

El propietario ejecutó las comprobaciones en la rama design/verified-agent-delegation-i3-2b, HEAD 8f65c3646987a2402ecd089f9b426568f60f2ec2:

- Pruebas específicas test_platform_admin_domain_contracts.py: **8 tests — OK**.
- python -m compileall -q src tests: **COMPILE_EXIT_CODE=0**.
- Suite completa python -m unittest discover -s tests -v: **1,421 tests en 28.292 s — OK**.

La primera invocación focalizada desde el directorio equivocado devolvió Ran 0 tests y no se considera evidencia. La ejecución válida se repitió desde ~/atlas-dev y confirmó los ocho tests. La suite completa y compileall se ejecutaron después en ese mismo checkout.

Esta evidencia valida los contratos de dominio y puertos de 7B.1 en el HEAD indicado. No valida persistencia SQLite, bootstrap offline, servicio lifecycle, CI ni cambios de infraestructura. No se provisionó ningún administrador ni se modificó ninguna asociación.

**Estado:** I3-2B.7B.1 validada por el propietario en Debian. PR #16 permanece Draft, abierto y sin fusionar.



## 18. I3-2B.7B.2 — persistencia inicial publicada, pendiente de validación

Se publicó una primera implementación de persistencia Platform Admin en la rama de trabajo:

- Migración `CORE_SCHEMA_V25`, registrada después de V24.
- Tablas `platform_admin_bootstrap_events` y `platform_admin_grants`, con integridad diferida evento/concesión para atomicidad al commit.
- Validación SQL de identidad USER canónica exacta, activa y en revisión coincidente; permisos exactos; una concesión activa por USER; eventos inmutables y concesiones retenidas como tombstones.
- Adaptador `SQLitePlatformAdminAuthorityReader` de solo lectura, integrado en `SQLiteLocalAuthorityUnitOfWork`.
- Pruebas focalizadas nuevas en `tests/unit/test_sqlite_platform_admin_authority.py`.

Esta implementación aún no está validada en Debian. El bootstrap writer/CLI no está implementado ni conectado a runtime. No se ha concedido autoridad a ningún USER, ni se han modificado asociaciones o bases productivas.

**Estado:** código publicado; pendiente validación del propietario en Debian. No avanzar al bootstrap offline hasta que las pruebas focalizadas, compileall y suite completa pasen.


## 19. I3-2B.7B.4A — contratos de lifecycle de asociaciones

Se añadieron contratos explícitos de intención y evento, junto con un puerto para el ledger:

- `core/project_environment_lifecycle.py`: `ProjectEnvironmentLifecycleRequest` limita la intención a Project/Environment, estado objetivo ACTIVE/SUSPENDED, expected_revision y motivo normalizado obligatorio. `ProjectEnvironmentLifecycleEvent` vincula transición, revisiones consecutivas, actor USER canónico, referencia de VerifiedIdentityContext, request/correlation IDs y timestamp UTC.
- `ports/project_environment_lifecycle.py`: define append y lectura de eventos de auditoría.
- `tests/unit/test_project_environment_lifecycle_contracts.py`: cubre intención normalizada, transición real, incremento de revisión, IDs de actor/contexto y UTC.

El contrato de motivo elegido es 1–500 caracteres, sin caracteres de control, sin espacios exteriores y con whitespace interno colapsado. Los contratos validan estructura, no autenticación ni autorización.

**Siguiente:** 7B.4B debe diseñar e implementar V26 para ledger inmutable y protección SQL de transiciones. La migración no puede fabricar eventos históricos para asociaciones V18 existentes. Después se implementará el adaptador y finalmente el servicio transaccional con VerifiedIdentityContext, Platform Admin y Clock confiable.

**Estado:** 7B.4A publicado; validación Debian pendiente. No se ha implementado servicio ni migración, no se ha ejecutado bootstrap real y no se ha modificado DB productiva.


## 20. I3-2B.7B.4B — V26 association lifecycle ledger

Published on PR #16 branch: immutable lifecycle event ledger, exact active canonical USER actor/association checks, deferred event-to-transition commit marker, association CAS update requiring event reference, and adversarial SQL tests. Existing associations are preserved without synthetic history. Owner validation is pending; V26 has not been applied to production. See `docs/design/i3-2b-7b4b-association-lifecycle-v26-migration.md`.


## 21. I3-2B.7B.4B — validación Debian confirmada y 7B.4C publicado

El propietario confirmó la validación completa de 7B.4B en Debian: **1,480 tests OK** y `COMPILE_EXIT_CODE=0`. La migración V26, sus triggers y las pruebas adversariales quedan validadas; no se aplicó a producción ni se ejecutó bootstrap real.

Se publicó 7B.4C: `SQLiteProjectEnvironmentLifecycleLedger` implementa append/read ordenado por revisión, reconstrucción validada de eventos y soporte de UoW compartida. El writer no se integra en `SQLiteLocalAuthorityUnitOfWork` ni en runtime composition. Las pruebas nuevas cubren append/transición atómicos, orden, rechazo de evento huérfano, rollback, validación de entradas y ausencia del writer runtime.

**Estado 7B.4C:** implementación publicada; validación owner pendiente. PR #16 continúa Draft, abierto y sin merge.


## 22. I3-2B.7B.4C — validación Debian confirmada

El propietario confirmó la validación del adaptador SQLite lifecycle en Debian: **1,487 tests OK** (`Ran 1487 tests in 29.235s`) y `COMPILE_EXIT_CODE=0`. Quedan validados append/read, orden por revisión, el requisito de transición atómica V26, rollback conjunto y el límite que mantiene el writer fuera de `SQLiteLocalAuthorityUnitOfWork`. No se ejecutó migración productiva ni bootstrap real. PR #16 permanece Draft, abierto y sin merge.


## 23. I3-2B.7B.4D — servicio transaccional publicado

Se publicó `ProjectEnvironmentLifecycleService`: revalida VerifiedIdentityContext USER dentro de la UoW, exige un único Platform Admin ACTIVE y el permiso exacto de suspensión/reactivación, comprueba expected_revision, usa Clock UTC confiable y escribe ledger + CAS de asociación en la misma transacción. El adapter se enlaza mediante `ledger_factory(unit)` y no se agrega writer a `SQLiteLocalAuthorityUnitOfWork`.

Las pruebas iniciales usan un verifier doble controlado; no simulan ni sustituyen la validación criptográfica real de Identity Authority. La validación Debian está pendiente. No se añadió runtime composition, endpoint, CLI ni migración. No se ejecutó bootstrap real ni se tocó DB productiva.

## 24. I3-2B.7B.4D — validación Debian confirmada

El propietario confirmó la suite completa en Debian: **1,493 tests en 29.527 s — OK** y `python -m compileall -q src tests` con **COMPILE_EXIT_CODE=0**. Queda validado el servicio transaccional de lifecycle junto con el ledger SQLite y las protecciones V26 en el HEAD probado.

No se ejecutó bootstrap real, no se aplicó migración a producción y no se añadió runtime composition, endpoint ni CLI. PR #16 permanece Draft, abierto y sin merge.

## 25. I3-2B.7B.4E — endurecimiento adversarial publicado; validación pendiente

Se añadieron cuatro pruebas de servicio para: grant Platform Admin expirado con evidencia USER todavía válida, mismatch de revisión de identidad, fallo de commit con rollback de asociación/evento/marcador y concurrencia de dos transiciones con el mismo expected_revision (solo una puede confirmar). La cobertura existente conserva casos de autoridad revocada/ausente, evidencia expirada, revisión obsoleta y fallo del ledger.

El verifier sigue siendo un doble controlado; no se afirma validar criptografía/issuer/attestation. La prueba de commit fuerza una excepción antes de la confirmación física SQLite; las constraints diferidas V26 se mantienen cubiertas por las pruebas de migración. No hay cambios de servicio, schema, runtime composition, HTTP, CLI ni infraestructura. Validación Debian pendiente: se esperan 1,497 tests y `COMPILE_EXIT_CODE=0`. PR #16 continúa Draft, abierto y sin merge.

### Nota de corrección 7B.4E

El primer ensayo Debian encontró que el doble de prueba de commit pasaba al ledger el wrapper `SQLiteLocalAuthorityUnitOfWork` en lugar del `SQLiteUnitOfWork` interno. Se corrigió el wiring de la prueba a `unit._unit._unit`; no hubo cambios productivos. Validación pendiente de repetición.

### Reejecución focalizada 7B.4E

Tras corregir el doble de prueba, el propietario confirmó **26 tests en 1.664 s — OK**. Suite completa y `compileall` pendientes; la fase no se considera validada todavía.

### Cierre de validación 7B.4E

El propietario confirmó **1,497 tests en 30.888 s — OK** y `compileall` con **`COMPILE_EXIT_CODE=0`**. Las 26 pruebas focalizadas también pasaron (1.664 s). Se considera 7B.4E validada. Sin cambios de producción, esquema, composición runtime o infraestructura en esta fase.

## Revisión de integración 7B.4A–7B.4E — hallazgo corregido, validación pendiente

Se revisaron conjuntamente contratos de dominio, puerto, migración V26, ledger SQLite, servicio transaccional, UoW, autoridad Platform Admin y pruebas adversariales. Se confirmó que la escritura del ledger no está expuesta en `SQLiteLocalAuthorityUnitOfWork`, el servicio comparte la UoW para verificación de identidad/grant/asociación y persistencia, y V26 exige evento + transición + marcador en el mismo commit, conservando asociaciones legacy sin eventos sintéticos.

**Hallazgo:** el servicio capturaba `Clock.now()` antes de adquirir la UoW. Dado que `SQLiteDatabase.unit_of_work()` ejecuta `BEGIN IMMEDIATE` y puede esperar hasta `busy_timeout_ms`, el grant podía evaluarse usando una hora anterior a la adquisición del bloqueo. Se corrigió capturando y validando el Clock dentro de la UoW, después de adquirirla. Se añadió una prueba que simula el avance del reloj durante la entrada a la UoW y exige denegación sin escrituras cuando el grant ya expiró.

**Estado:** corrección y prueba publicadas en la rama; pendientes de validación del propietario (prueba focalizada, suite completa y compileall). No se modificó schema, migraciones, composición runtime ni infraestructura.

### Cierre del hallazgo temporal de la revisión de integración

El propietario confirmó la suite completa tras la corrección: **1,498 tests en 29.777 s — OK** y `compileall` con **`COMPILE_EXIT_CODE=0`**. La prueba de regresión del avance del reloj durante la adquisición de UoW quedó incluida en la suite y validada. El hallazgo se considera corregido y verificado.
