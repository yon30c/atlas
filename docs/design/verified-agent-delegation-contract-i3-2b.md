# I3-2B — contrato de identidad AGENT y delegación verificable

**Estado:** propuesta de diseño; no implementa ni habilita autenticación AGENT ni operaciones delegadas.  
**Base:** `feature/verified-identity-i3-renewal-owner` (I3-2A validado por el propietario).  
**Alcance inicial:** permitir, en una fase posterior, que una identidad AGENT autenticada solicite la renovación de un Grant concreto cuando exista delegación vigente del propietario.  
**Decisión de seguridad:** I3-2B separa tres decisiones: autenticación del agente, prueba de delegación del propietario y autorización CAM. Ninguna sustituye a las otras.

## 1. Hallazgo de partida

La implementación inspeccionada ya dispone de:

- `IdentityKind.AGENT` en el modelo general de identidad.
- `Grant` con `owner_user_id`, `subject_identity_id`, proyecto, entorno, conjunto explícito de recursos, acciones, expiración, revocación y revisión.
- Evidencia nativa USER en I-2: `VerifiedIdentityContext`, `CanonicalUserIdentity` y `NativeIdentityBinding`.

Pero la ruta nativa está expresamente limitada a USER:

- `VerifiedIdentityContext` rechaza cualquier `identity_type` distinto de USER.
- `CanonicalUserIdentity` representa un par UserId + Identity(USER).
- `NativeIdentityBinding` y `NativeIdentityAuthorityPort` declaran bindings USER.
- `IdentityAuthorityPort.get_user_by_identity_id` resuelve únicamente identidades USER.

Por tanto, no se debe ensanchar esos tipos USER mediante casts, valores AGENT dentro de `CanonicalUserIdentity`, ni excepciones en el verificador actual. El tipo de prueba USER debe seguir siendo USER-only.

## 2. Modelo de confianza: tres planos separados

### 2.1 Autenticación AGENT

Demuestra quién es el principal AGENT que controla la credencial usada en esta sesión.

Propuesta de contratos nuevos e independientes:

- `CanonicalAgentIdentity`: agregado canónico que contiene una Identity de tipo AGENT activa y su revisión. No contiene un UserId.
- `AgentIdentityAuthorityPort`: crea/resuelve/retira identidades AGENT y devuelve el agregado canónico. No acepta un IdentityId elegido por el caller como identidad canónica.
- `NativeAgentIdentityBinding` y `NativeAgentIdentityAuthorityPort`: binding de un sujeto de issuer a un AGENT canónico, con issuer, digest, estado, revisión, timestamps y tombstone de revocación. No reutiliza ni cambia la semántica del binding USER existente.
- `VerifiedAgentIdentityContext`: evidencia efímera attested, de tipo AGENT-only, con context_id, identity_id, identity_revision, binding_id, binding_revision, issuer_id, authenticated_at, verified_at, expires_at, verification_ref y attestation.
- `VerifiedAgentIdentityContextVerifierPort.verify(context)`: revalida attestation, TTL, issuer activo, binding activo y sin cambios, identidad AGENT canónica activa y revisión exacta. Devuelve `CanonicalAgentIdentity` o deniega.

La admisión de proof debe reutilizar las garantías criptográficas de I-2 (dominio separado, audiencia/realm, proof one-shot y digest-only persistence), pero con audiencia y tipo de sujeto AGENT explícitos. No aceptar un proof USER como proof AGENT ni viceversa. Un AGENT no se crea automáticamente porque exista un Grant cuyo `subject_identity_id` coincida.

### 2.2 Delegación otorgada por USER

Demuestra qué autorizó el propietario para ese agente. No autentica al agente.

Nuevo agregado propuesto: `AgentDelegation` (nombre provisional), administrado exclusivamente por una Delegation Authority.

Claims mínimos:

| Campo | Semántica |
|---|---|
| `delegation_id` | UUID canónico e inmutable |
| `owner_user_id` | UserId canónico del propietario |
| `agent_identity_id` | IdentityId canónico AGENT |
| `grant_id` | Grant concreto al que queda vinculada |
| `grant_revision` | Revisión del Grant al emitir la delegación |
| `project_id`, `environment` | Scope exacto del Grant |
| `resource_scope` | Subconjunto explícito del scope del Grant |
| `actions` | Subconjunto explícito de acciones del Grant |
| `issued_at`, `not_before`, `expires_at` | Ventana UTC acotada |
| `status`, `revision` | ACTIVE/REVOKED y revisión monotónica |
| `issuer_id` | Autoridad que registró la decisión |
| `created_by_user_identity_id` | Identity(USER) que aprobó; nunca un ID suministrado sin verificar |
| `revoked_at`, `revoked_by_user_id` | Tombstone/auditoría de revocación |

Invariantes de emisión:

1. Solo una operación explícita del propietario autenticado con `VerifiedIdentityContext` USER puede crear una delegación.
2. El verificador USER resuelve el par canónico; `owner_user_id` debe coincidir con `canonical.user_id`. La identidad decisora debe ser `canonical.identity`. Nunca comparar UserId con IdentityId.
3. El Grant debe existir, pertenecer al mismo propietario y tener como sujeto al AGENT indicado.
4. Proyecto y entorno deben coincidir exactamente con el Grant.
5. Recursos delegados deben ser un subconjunto estricto o igual del `GrantResourceScope`; acciones delegadas deben ser subconjunto de `Grant.actions`. Wildcards siguen prohibidos.
6. `not_before >= grant.issued_at`; `expires_at > not_before`; `expires_at <= grant.expires_at`. La delegación nunca extiende el Grant.
7. La revisión del Grant queda fijada. Si el Grant cambia de revisión, scope, acciones, expiración, sujeto o propietario, la delegación anterior deja de ser válida; debe emitirse otra mediante nueva aprobación.
8. No existe auto-delegación por el AGENT, herencia implícita, delegación transitiva ni elevación de privilegios.

La delegación es un mandato independiente, no un segundo Grant CAM. No amplía los permisos: solo acredita el consentimiento del propietario dentro de límites que ya están concedidos por CAM.

### 2.3 Autorización CAM

CAM sigue siendo la autoridad ordinaria que evalúa la acción concreta, recurso, propietario, proyecto, entorno, vigencia, revocación y revisión del Grant.

Para una operación delegada deben cumplirse simultáneamente:

- identidad AGENT autenticada y canónica;
- delegación vigente emitida por autoridad confiable para ese AGENT y ese propietario;
- Grant exacto vigente, no revocado y coincidente;
- acción y recurso permitidos por CAM;
- límites de la delegación no más amplios que el Grant;
- `OperationContext` coherente con la evidencia verificada.

`DelegationMode.DELEGATED` solo describe el modo del contexto. Nunca es prueba ni permiso.

## 3. Contratos/puertos propuestos

Los nombres son conceptuales; se deben ajustar a convenciones del código antes de implementar.

### 3.1 `DelegationAuthorityPort`

Operaciones mínimas:

- `create_for_grant(..., verified_owner_identity, ...)`: crea una delegación después de revalidar identidad USER, ownership y restricciones del Grant.
- `get_by_id(delegation_id)`: devuelve el registro canónico, incluido tombstone.
- `revoke(delegation_id, expected_revision, verified_owner_identity, revoked_at)`: revocación owner-only con CAS; terminal, nunca se reactiva ni reasigna.
- `verify_for_operation(delegation_id, expected_revision, ...)`: comprueba estado, ventana, vínculos, scope y revisiones actuales. No debe confiar en claims copiados del caller.

La autoridad debe ser única y explícita en composition root. Sin autoridad, key, registro, UoW o issuer disponible, la operación deniega.

### 3.2 `VerifiedDelegationContext`

Evidencia efímera producida por la Delegation Authority después de verificar el registro canónico. Debe incluir como mínimo:

- delegation_id y delegation_revision;
- owner_user_id y agent_identity_id;
- grant_id y grant_revision;
- project_id y environment;
- digest/canonical representation de resource_scope y actions;
- issuer_id;
- verified_at y expires_at (TTL corto, no mayor que el fin de la delegación);
- context_id/verification_ref y attestation.

La attestation debe usar serialización canónica, HMAC-SHA-256 o mecanismo equivalente ya aprobado, separación de dominio específica (`atlas:delegation:v1`), issuer/realm/audience fijos y comparación en tiempo constante. Claves separadas de las claves de VerifiedIdentityContext USER y rotación explícita. No incluir secretos ni credenciales.

**La attestation no es la fuente de verdad:** cada consumidor revalida el registro actual y sus revisiones contra Delegation Authority. Una firma válida sobre una delegación ya revocada no la revive.

### 3.3 Verificador de operación delegada

Un helper común (provisional `require_verified_agent_delegation`) debe recibir contexto, `VerifiedAgentIdentityContext`, `VerifiedDelegationContext`, Grant actual y verificadores confiables. Comprueba:

- actor == Identity AGENT canónica devuelta por el verificador AGENT;
- el AGENT verificado coincide con `agent_identity_id` de la delegación y `subject_identity_id` del Grant;
- `context.user_id` coincide con el propietario canónico de la delegación/Grant;
- `context.delegation is DelegationMode.DELEGATED`;
- proyecto/entorno coinciden exactamente;
- Grant ID/revisión/propietario/sujeto/scope/acciones/expiry coinciden con la delegación;
- acción y recurso de la operación están dentro de ambos límites;
- delegación y Grant están vigentes y no revocados;
- ninguna revisión ha cambiado desde la emisión/verificación.

No debe devolver un `CanonicalUserIdentity` para un AGENT ni transformar la evidencia AGENT en identidad USER. Los tipos de evidencia permanecen separados.

## 4. Ciclo de vida y revocación

Estados mínimos: ACTIVE y REVOKED. No reactivar ni editar una delegación existente.

- **Creación:** decisión USER autenticada; validación de Grant; registro inmutable de la delegación; revisión inicial 1.
- **Uso:** autenticación AGENT por operación/sesión de corta duración; revalidación de binding, delegación y Grant.
- **Revocación:** solo propietario autenticado (y, opcionalmente, una autoridad de seguridad explícitamente autorizada en un contrato separado); CAS sobre revisión; tombstone permanente.
- **Cambios del Grant:** invalidan la delegación por mismatch de `grant_revision`; no actualizar silenciosamente la delegación.
- **Revocación del binding AGENT/issuer:** invalida cualquier contexto AGENT, aunque la delegación siga ACTIVE.
- **Expiración:** se evalúa con reloj UTC confiable en el momento de la operación, no solo al emitir el contexto.
- **Eliminación:** no borrar físicamente los registros necesarios para auditoría/replay defense.

La revocación de un Grant invalida de inmediato todas las delegaciones vinculadas. La revocación de una delegación no modifica el Grant ni otras delegaciones.

## 5. Consistencia, concurrencia y límites transaccionales

La comprobación de identidad, binding, delegación, Grant y escritura de la solicitud no debe crear una ventana TOCTOU.

Contrato requerido para habilitar una operación:

1. La operación entra en una UoW que pueda leer de forma consistente Identity/AgentBinding, Delegation, Grant y Renewal.
2. Revalida estado y revisiones dentro de esa frontera.
3. Crea la solicitud con CAS/idempotencia bajo la misma transacción o con un mecanismo de fencing explícito equivalente.
4. Si una revocación/cambio concurrente gana la carrera, la solicitud debe abortar.
5. Si las autoridades no comparten la misma transacción/DB o no existe fencing demostrado, no afirmar atomicidad: mantener la operación bloqueada.

La garantía actual de `SQLiteLocalAuthorityUnitOfWork` solo aplica a authorities que comparten exactamente la misma instancia de `SQLiteDatabase`. El diseño no presupone atomicidad global con el journal ni con sistemas externos.

Se recomienda idempotencia por `request_id` (y una restricción para impedir solicitudes PENDING duplicadas para el mismo Grant, si el producto decide esa regla). Reintentos no deben crear múltiples renovaciones ni repetir efectos.

## 6. Aplicación a `GrantRenewalService.request_renewal`

Firma conceptual futura:

```python
request_renewal(
    context,
    renewal_id,
    grant_id,
    proposed_expires_at,
    now,
    *,
    verified_agent_identity,
    verified_delegation,
)
```

Antes de persistir, la operación debe verificar:

- actor AGENT canónico y autenticado;
- propietario USER canónico vinculado al Grant;
- delegación ACTIVE para el par exacto owner/agent y Grant;
- permiso explícito `grant.renewal.request` en la delegación y en el Grant/CAM;
- scope exacto de proyecto/entorno y recurso aplicable;
- Grant vigente/no revocado y revisión esperada;
- propuesta de expiración posterior a la actual y dentro de límites de política; la solicitud no renueva por sí misma el Grant;
- ausencia de una solicitud PENDING incompatible/duplicada;
- persistencia atómica y atribución de `requested_by_identity_id` al AGENT canónico.

La solicitud no debe cambiar `Grant.expires_at`. Solo el propietario autenticado puede aprobar/rechazar mediante I3-2A. La aprobación debe volver a validar el Grant, su revisión/expiry y la solicitud; una delegación vencida después de solicitar no convierte al agente en decisor.

Hasta que existan todos los contratos, UoW y pruebas, el método permanece fail-closed como está en PR #15.

## 7. Amenazas y pruebas obligatorias

### Autenticación AGENT
- proof USER presentado como AGENT y viceversa;
- Identity(USER) en contexto AGENT;
- AGENT desconocido, inactivo, revocado o revisión obsoleta;
- issuer/audience/realm incorrectos, TTL vencido, attestation manipulada;
- proof reutilizado, credencial inválida y autoridad indisponible.

### Delegación
- ausencia de delegación, delegación fabricada o firmada por actor no confiable;
- owner/agent/Grant/project/environment mismatch;
- recurso/acción fuera de subconjunto;
- expiración mayor que Grant, delegación futura o expirada;
- Grant revision cambiada, Grant revocado o binding/issuer revocado;
- delegación revocada con attestation anterior todavía criptográficamente válida;
- revocación concurrente con solicitud;
- revisión CAS incorrecta, rollback y UoW no compartida;
- delegación transitiva, self-delegation y escalada de scope;
- replay de request_id y duplicados PENDING.

### Renovación
- AGENT válido pero sin delegación: DENY;
- delegación válida pero AGENT no autenticado: DENY;
- ambos válidos pero CAM no permite acción/recurso: DENY;
- agente solicita; solo USER owner puede decidir;
- solicitud no altera Grant; aprobación posterior valida el estado actual;
- IDs UserId e IdentityId distintos en todos los casos positivos.

Fakes de verificador solo en tests, con tipos explícitos y nunca componibles en runtime. Tests negativos deben comprobar ausencia de escrituras y rollback, no solo la excepción.

## 8. Secuencia de implementación recomendada

1. **I3-2B.1 — contratos de dominio y puertos:** tipos canónicos AGENT, contexto verificado AGENT, agregado de delegación, evidencia verificada de delegación y protocolos. Sin persistencia ni ruta habilitada.
2. **I3-2B.2 — autoridad de identidad AGENT:** ciclo de vida canónico y bindings AGENT; pruebas de separación USER/AGENT.
3. **I3-2B.3 — autoridad de delegación:** persistencia, emisión owner-only, revocación terminal/CAS, auditoría y revalidación.
4. **I3-2B.4 — admisión de proof AGENT:** proof one-shot, attestation y guard fail-closed; sin exponer login/endpoints.
5. **I3-2B.5 — UoW y verificación de operación delegada:** comprobar atomicidad/fencing real con Identity, Binding, Delegation, Grant y Renewal.
6. **I3-2B.6 — habilitación acotada de `request_renewal`:** solo cuando los slices anteriores estén validados; mantener aprobación/rechazo owner-only de I3-2A.

Cada slice tendrá PR Draft, pruebas focalizadas, suite completa y compileall validados en Debian por el propietario. No se fusiona ningún PR sin aprobación explícita.

## 9. No objetivos y restricciones

- No convertir `OperationContext`, `Identity(ACTIVE)` o `DelegationMode.DELEGATED` en evidencia.
- No ampliar `VerifiedIdentityContext` ni `CanonicalUserIdentity` para incluir AGENT.
- No permitir que un AGENT emita, delegue o amplíe su propia autoridad.
- No permitir delegación transitiva en esta fase.
- No sustituir CAM con la Delegation Authority.
- No implementar login operativo, endpoints, CLI, bootstrap o wiring de producción en este diseño.
- No cambiar DB productiva, host, systemd, sudoers, usuarios, Docker ni privilegios.
- No afirmar garantías de consistencia distribuida que no estén demostradas.

## 10. Criterio de salida de diseño

El contrato queda listo para implementación cuando la revisión confirme:
- separación de tipos y autoridades USER/AGENT;
- owner consent verificable e independiente de agent proof;
- delegación estrecha, vinculada a Grant y no elevadora;
- revocación/expiración/revisión revalidadas en cada operación;
- CAM como autorización final;
- límites transaccionales y concurrencia explícitos;
- pruebas negativas y fail-closed definidas.

**Estado actual:** propuesta documental únicamente. `GrantRenewalService.request_renewal` permanece bloqueado. No se ha añadido código, migración, autoridad productiva ni endpoint.


## 11. I3-2B.1 — contratos de dominio y puertos

**Implementación contractual en curso en la rama `design/verified-agent-delegation-i3-2b`; sin adaptadores ni persistencia.**

Tipos añadidos:
- `CanonicalAgentIdentity`, separado de `CanonicalUserIdentity` y sin `UserId`.
- `VerifiedAgentIdentityContext`, AGENT-only, con revisión de identidad/binding, issuer, realm, audience, timestamps, reference y attestation redactadas en repr.
- `NativeAgentIdentityBinding`, binding separado de USER y con revocación terminal.
- `AgentDelegationScope`, `AgentDelegation` y `VerifiedAgentDelegationContext`, con recursos/acciones explícitos, vínculo al Grant/revisión, propietario/identidad AGENT, estado, revocación, realm/audience y payload canónico de attestation.
- Puertos separados para autoridad AGENT, binding AGENT, verificación de identidad AGENT, ciclo de vida de delegación y verificación de evidencia de delegación.

Invariantes en modelos:
- AGENT canónico exige UUIDv4 y `IdentityKind.AGENT`; USER no se acepta.
- La evidencia AGENT rechaza `IdentityKind.USER`, revisiones inválidas, timestamps no UTC y TTL inválido.
- Scope no admite conjuntos vacíos ni wildcards.
- Delegación exige owner/agent distintos, atribución al IdentityId del propietario, revisión del Grant, ventana temporal y auditoría de revocación coherentes.
- La evidencia de delegación incluye protocolo, realm/audience, owner/agent, Grant/revisión, proyecto/entorno, scope y vigencia en serialización canónica ordenada.

**Límite:** los modelos validan estructura e invariantes locales; no demuestran autenticidad, estado canónico, subset contra un Grant real ni autorización CAM. Esas verificaciones pertenecen a las autoridades/verificadores y deben fallar cerrado.

### Hallazgo de consistencia que condiciona I3-2B.5

La auditoría existente `docs/design/assistant-operation-consistency-boundary.md` registra que la composición actual de Identity abre su propia SQLite/UoW y que Grants/Renewals usan una UoW distinta; no se ha demostrado una base/UoW canónica compartida entre esas autoridades. Por ello no se puede afirmar hoy atomicidad entre Identity, binding, delegación, Grant y renovación. I3-2B.5 deberá diseñar y probar una UoW compartida o un mecanismo de fencing/consistencia equivalente antes de habilitar cualquier solicitud AGENT. Si no se demuestra, la ruta permanece bloqueada.

**Validación:** se añadieron pruebas unitarias focalizadas en `tests/unit/test_agent_delegation_domain_contracts.py`. No se ha ejecutado la suite en Debian desde esta rama; la validación queda pendiente del entorno del propietario.


### 11.1. Precisión sobre revocación terminal y objetos inmutables

Un dataclass inmutable valida un **snapshot**, pero no conoce el snapshot anterior. Por ello, `AgentDelegation.__post_init__` valida que:
- un estado ACTIVE no tenga metadatos de revocación;
- un estado REVOKED tenga `revoked_at` y `revoked_by_user_id`.

La irreversibilidad histórica se valida con `validate_agent_delegation_transition(current, updated)`: una fila REVOKED no puede volver a ACTIVE ni alterar su auditoría de revocación; la revisión debe avanzar exactamente en una unidad. La autoridad debe invocar esta función tras leer el registro canónico y dentro de la misma transacción o frontera de fencing que realiza CAS. La función aislada no sustituye el control transaccional.

Las pruebas de redacción deben comprobar que el **valor secreto** no aparece en `repr`, no que desaparezca el nombre del campo: `verification_ref=<redacted>` y `attestation=<redacted>` son marcadores esperados y no revelan los valores.


## 12. I3-2B.2 — autoridad canónica de identidad AGENT

**Implementación inicial añadida en la rama de trabajo; pendiente de validación del propietario en Debian.**

La inspección de CORE_SCHEMA_V6 confirmó que identity_records ya admite los tipos user, agent, service, watcher y system, y exige user_id IS NULL para todo tipo distinto de USER. Por tanto, I3-2B.2 no introduce una tabla paralela ni modifica el esquema histórico.

Implementación:
- SQLiteAgentIdentityAuthority crea Identity(AGENT) con UUIDv4 y user_id=NULL.
- La resolución filtra simultáneamente por identity_id, identity_kind='agent' y user_id IS NULL; identidades USER y otros tipos nunca se devuelven.
- Los cambios de estado usan compare-and-swap sobre revision, mantienen revocación terminal y participan en una SQLiteUnitOfWork suministrada cuando existe.
- La autoridad no crea atlas_users, no gestiona credenciales/proofs, bindings, autenticación, delegaciones ni autorización.
- El adaptador se exporta desde atlas.adapters.sqlite.

Pruebas añadidas en tests/unit/test_sqlite_agent_identity_authority.py: creación UUIDv4, aislamiento USER/AGENT, desconocidos, UUID inválido, duplicados, CAS, revocación terminal, entradas inválidas, concurrencia y UoW suministrada.

**Límite:** el esquema común identity_records es el almacenamiento de identidad canónica ya existente; la autoridad AGENT mantiene API y responsabilidad separadas. El binding persistente AGENT se incorpora en la subsección 12.1. Este slice no implementa proof admission, delegación, composition root de producción ni habilita GrantRenewalService.request_renewal.

**Validación:** el código y las pruebas están publicados, pero no se declara que hayan sido ejecutados. Se requiere validación focalizada, suite completa y compileall en Debian antes de cerrar I3-2B.2.


### 12.1. Binding nativo AGENT y separación de subject

La implementación se amplió para cubrir el binding persistente sin relajar el trigger existente que reserva native_identity_bindings a Identity(USER).

- CORE_SCHEMA_V21 crea native_agent_identity_bindings, con FK a identity_records y native_identity_issuers, UUIDv4, digest SHA-256, revisión, estado y tombstone.
- El trigger de inserción exige una identidad AGENT canónica ACTIVE con user_id=NULL y un issuer ACTIVE.
- SQLiteNativeAgentIdentityAuthority implementa lookup, creación de binding y revocación CAS terminal, aceptando una CanonicalAgentIdentity y revalidándola contra el registro persistido.
- CORE_SCHEMA_V22 impide que el mismo par issuer_id/subject_digest se vincule a la vez con USER y AGENT, en cualquiera de los dos órdenes de inserción.
- La tabla native_identity_bindings y su trigger USER no se amplían ni se debilitan.

Pruebas adicionales en tests/unit/test_sqlite_native_agent_identity_authority.py cubren creación/lookup, rechazo de USER, identidad AGENT suspendida, duplicados, colisión cruzada USER/AGENT en ambos órdenes y revocación CAS.

**Estado:** implementación publicada, pendiente de validación en Debian. La autoridad no autentica credenciales, no emite proofs y no habilita delegación ni solicitudes de renovación.


## 13. I3-2B.3A — persistencia canónica de delegaciones (substrato)

**Validada en Debian:** suite completa 1,329/1,329 tests OK; `python -m compileall -q src tests` con exit code 0. No equivale todavía a una autoridad de emisión/verificación.

Se añadió CORE_SCHEMA_V23 y SQLiteAgentDelegationRepository para persistir el agregado AgentDelegation:
- FKs a atlas_users, identity_records, authorization_grants y native_identity_issuers.
- Restricciones de UUID, revisión, estado, timestamps UTC, JSON de scopes y auditoría de revocación.
- Trigger de inserción que exige USER propietario activo y emparejado con UserId, AGENT activo, Grant vigente y exacto (owner/subject/project/environment/revision), issuer activo y binding AGENT activo.
- Verificación de subset de resource_ids y actions tanto en el repositorio como en triggers SQLite, para que un INSERT directo no pueda ampliar el Grant.
- Claims inmutables, revision +1, revocación terminal y no-delete tombstones.
- El repositorio participa en SQLiteUnitOfWork explícita. SQLiteLocalAuthorityUnitOfWork expone identity, agent_identity, native_identity, native_agent_identity, grants y agent_delegations sobre la misma transacción.

Pruebas añadidas en tests/unit/test_sqlite_agent_delegation_repository.py y ampliación de test_sqlite_local_authority_unit_of_work.py.

**Validación del propietario en Debian:** `Ran 1329 tests in 17.000s — OK`; `COMPILE_EXIT_CODE=0`. Esto valida el estado actual del branch, incluyendo las pruebas de repositorio de delegaciones y la integración con la UoW. No se afirma que exista autoridad de emisión/verificación.

### Límite de seguridad y siguiente trabajo

Esto es una capa de persistencia, **no una autoridad de delegación**. El repositorio no verifica VerifiedIdentityContext ni puede decidir por sí solo que quien invoca create/revoke es el propietario. La inspección del repositorio actual confirma que existen puertos de verificación USER/AGENT, pero no un verificador productivo concreto/composición transaccional que pueda revalidar esas evidencias sobre la misma SQLiteUnitOfWork.

Por esa razón:
- No se implementó todavía AgentDelegationAuthorityPort.create_for_grant, revoke_delegation ni verify_for_operation.
- No se emiten VerifiedAgentDelegationContext ni attestations.
- No se habilita request_renewal ni ninguna operación delegada.
- No debe exponerse el repositorio como API de aplicación ni llamarse sin un servicio de autoridad que valide owner evidence y revalide el Grant dentro de la misma transacción.

En el checkpoint de I3-2B.3A, I3-2B.3B aún debía implementar el verificador USER/AGENT transaccional y la autoridad de emisión/revocación. El soporte de verificación dentro de UoW compartida quedó implementado en I3-2B.3B.3 (sección 16); la autoridad de delegación y la emisión de contexto delegado siguen pendientes. No se afirmará atomicidad fuera de la UoW compartida.


## 14. I3-2B.3B.1 — admisión y revalidación de identidad AGENT

**Implementación publicada; pendiente de validación en Debian.**

Se añade `VerifiedAgentIdentityContextService` en `src/atlas/identity/verified_agent_identity_context_service.py`, separado del servicio USER existente:
- Consume el mismo formato de proof nativo one-shot, pero resuelve el sujeto exclusivamente mediante `native_agent_identity` y `agent_identity`.
- Verifica issuer/realm y perfil nativo, audience del proof, binding AGENT activo, timestamp de verificación del binding, identidad canónica AGENT activa y revisiones exactas.
- Proof consumption, binding lookup y resolución canónica ocurren dentro de una sola `SQLiteLocalAuthorityUnitOfWork`; los errores posteriores revierten el consumo.
- Emite exclusivamente `VerifiedAgentIdentityContext`, sin UserId, con protocolo, realm y audience incluidos en el payload HMAC y en el dominio criptográfico `atlas.verified-agent-identity-context.v1`.
- `verify(context)` revalida attestation, TTL, realm/audience, issuer, binding y revisión/estado de identidad en cada llamada; satisface el contrato de `VerifiedAgentIdentityContextVerifierPort`.
- No amplía ni reutiliza `VerifiedIdentityContext` USER.

Pruebas nuevas: `tests/unit/test_verified_agent_identity_context_service.py`, incluyendo admisión, replay, audience/realm, HMAC adulterado, clave distinta, binding revocado, identidad suspendida, proof anterior a la verificación del binding, rollback y expiración.

### Límites pendientes

Este slice no implementa la autoridad de delegación ni emite `VerifiedAgentDelegationContext`. La autenticación nativa que emite proofs sigue siendo un servicio separado y requiere composición/guardia de intentos; no se habilita endpoint/login AGENT. El siguiente paso es construir la autoridad de delegación sobre owner USER verificado + AGENT verificado y Grant exacto dentro de la misma UoW.


### Validación Debian — I3-2B.3B.1

El propietario ejecutó la suite completa sobre el HEAD de esta fase: `Ran 1341 tests in 17.171s`, `OK`; `python -m compileall -q src tests` terminó con `COMPILE_EXIT_CODE=0`. Esta evidencia corresponde a la rama de diseño actual y no implica activación de autenticación AGENT en runtime ni habilitación de delegaciones.


## 15. I3-2B.3B.2 — caller-bound delegation verification contract

The `AgentDelegationAuthorityPort.verify_for_operation` contract now requires a `VerifiedAgentIdentityContext` argument. A delegation identifier is not a bearer credential: implementations must revalidate the supplied AGENT evidence and require its canonical identity ID to equal the delegation's `agent_identity_id` before issuing any `VerifiedAgentDelegationContext`.

A focused domain-contract test asserts that this argument is mandatory and typed. This is a contract-hardening slice only; no production authority implementation or delegated operation is enabled.


### Validación Debian — I3-2B.3B.2

El propietario ejecutó `test_agent_delegation_domain_contracts.py`: `Ran 12 tests in 0.486s`, `OK`; `python -m compileall -q src tests` devolvió `COMPILE_EXIT_CODE=0`.


## 16. I3-2B.3B.3 — verificadores compatibles con UoW compartida

Los servicios `VerifiedIdentityContextService` y `VerifiedAgentIdentityContextService` exponen ahora `verify_in_unit_of_work(context, unit)`. El método revalida attestation, TTL, issuer, binding, identidad canónica y revisiones usando los repositorios asociados a la UoW recibida. No abre, confirma ni cierra transacciones; la autoridad llamadora conserva el control de commit/rollback.

Los métodos existentes `verify(context)` mantienen su contrato y delegan en la nueva ruta abriendo su propia UoW, por lo que los consumidores actuales no necesitan cambiar.

Se añadieron pruebas para ambos protocolos que llaman al verificador dentro de una UoW ya activa y comprueban que no se abre una transacción anidada. Esto permite que la futura autoridad valide owner USER, AGENT, Grant y delegación dentro de una sola transacción SQLite.


### Validación Debian — I3-2B.3B.3

El propietario validó el HEAD que incorpora los dos tests de UoW compartida: suite completa **1,344/1,344 tests OK**; `python -m compileall -q src tests` devolvió `COMPILE_EXIT_CODE=0`. La validación confirma el soporte transaccional de los verificadores USER y AGENT, pero no equivale a una implementación de la autoridad de delegación ni habilita operaciones AGENT.


## 16. I3-2B.4A — autoridad de emisión de delegaciones (implementación publicada; validación pendiente)

Se añadió `SQLiteAgentDelegationAuthority.create_for_grant` como autoridad de emisión. El slice requiere `VerifiedIdentityContext` USER y revalida su attestation, TTL, issuer, binding y canonical identity mediante `verify_in_unit_of_work` dentro de la misma `SQLiteLocalAuthorityUnitOfWork` que lee AGENT/Grant y persiste la delegación.

Antes de insertar, la autoridad exige:
- propietario USER canónico ACTIVE; los IDs de propietario y `created_by_user_identity_id` proceden exclusivamente del resultado canónico del verificador;
- AGENT canónico ACTIVE y un native binding AGENT ACTIVE asociado al mismo issuer USER verificado, cuyo issuer también esté ACTIVE;
- Grant exacto, vigente, no revocado, cuyo owner coincide con el USER autenticado y cuyo subject coincide con el AGENT solicitado;
- `resource_type`, `resource_ids` y `actions` solicitados estrictamente dentro del Grant;
- ventana UTC con `issued_at` tomado después de adquirir la transacción, `not_before >= issued_at` y `expires_at <= grant.expires_at`.

El issuer persistido se toma del contexto USER ya verificado. La escritura del repositorio participa en la misma UoW; cualquier excepción antes de `commit()` provoca rollback. Se añadió `has_active_native_agent_binding` al puerto/adaptador AGENT para que el chequeo de binding e issuer ocurra en esa misma transacción.

Pruebas nuevas: `tests/unit/test_sqlite_agent_delegation_authority.py`. Incluyen emisión canónica, contexto manipulado/expirado, binding revocado, Grant revocado, scope expansion, tipo de recurso distinto, ventana inválida y rollback después de insertar.

**Límite del slice:** solo se implementa emisión `create_for_grant`. No implementa revocación de autoridad, `verify_for_operation`, emisión de `VerifiedAgentDelegationContext`, CAM final, runtime/login AGENT ni renueva Grants. `GrantRenewalService.request_renewal` continúa fail-closed. La suite y compileall están pendientes de ejecución por el propietario en Debian.
