# B1-B-03B — Diseño físico de Identity Authority y persistencia

**Estado:** DISEÑO TÉCNICO PROPUESTO; no es autorización de migración ni implementación.  
**Baseline normativo:** B1-A-06 aprobado; B1-B-03A cerrado normativamente el 15-11-2026.  
**Baseline de código inspeccionado:** `feature/me-d4o-i-c4-sqlite-durable-authority-store`, commit `fba7c70933a77d883a7bdc1d86a755bd3b1a8674`.  
**Schema actual:** SQLite v4.  
**Objetivo:** especificar el modelo físico incremental para la autoridad canónica de identidad, sin habilitar autenticación externa ni modificar datos.

---

## 1. Resultado del inventario

Se inspeccionaron los contratos B1-A-06, DM-01, Identity, OperationContext, B1-B-03A-01/02/03 y los siguientes módulos del commit de referencia:

- `src/atlas/core/identity.py`
- `src/atlas/memory/identity.py`
- `src/atlas/authorization/identity_binding.py`
- `src/atlas/memory/consistency.py`
- `src/atlas/adapters/sqlite/database.py`
- `src/atlas/adapters/sqlite/migrations.py`
- `src/atlas/adapters/sqlite/authority_changes.py`
- `src/atlas/adapters/sqlite/recovery_gate.py`
- `tests/unit/test_sqlite_core_schema.py`

Hallazgos:

1. `Identity` es actualmente un modelo inmutable en memoria con tipos USER/AGENT/SERVICE/WATCHER/SYSTEM y estados ACTIVE/SUSPENDED/REVOKED.
2. `AuthenticatedUserSubject`, `IdentitySubjectBindingPort` y `AtlasIdentityBindingAdapter` constituyen el contrato legacy. El adaptador no es Identity Authority y no emite VerifiedIdentityContext.
3. `MemoryIdentityBinding` es un contrato neutral actor→subject; no representa el modelo canónico UserId↔Identity(USER).
4. SQLite aplica WAL, foreign keys, synchronous FULL, busy_timeout y UoW BEGIN IMMEDIATE. El ledger de migraciones exige secuencia completa y checksum/nombre inmutables.
5. Schema v4 contiene siete tablas de coordinación de cambios de autoridad. Su `authority_kind` CHECK no incluye `private_memory_authorization`.
6. `AuthorityKind` y `AuthorizationRevisionSet` tampoco expresan aún una revisión independiente de PRIVATE_MEMORY_AUTHORIZATION.
7. No se encontró una Identity Authority persistente canónica completa ni una persistencia operativa de bindings externos.

La inspección confirma estructuras y contratos, no acredita runtime integrado ni CI. El inventario debe repetirse sobre el commit exacto antes de cualquier implementación.

## 2. Autoridades y límites

| Dominio | Autoridad canónica | Persistencia propuesta |
|---|---|---|
| Identity | Identity Authority | Identidades, UserId y bindings |
| PRIVATE/PROJECT authorization | CAM | Autorizaciones y Grants separados |
| Coordinación | Consistency | Journal, invalidaciones, fencing y recovery |
| Memoria | Memory | Metadatos y referencias opacas |
| Runtime | Broker como frontera de ejecución | Fuera de esta fase |

Identity Authority no concede permisos, no crea Grants, no decide acceso a Memory y no modifica datos de CAM. Consistency no se convierte en autoridad de identidad ni copia los registros canónicos de Identity. El Broker Registry no se reutiliza para ninguna de estas responsabilidades.

## 3. Modelo relacional candidato

El diseño usa la misma SQLite local compartida y propiedad lógica de tablas por dominio. Las tablas siguientes son candidatas; los nombres no se consideran API pública hasta aprobar el contrato físico definitivo.

### 3.1 `identity_records`

Una fila por Identity interna.

Campos propuestos:

- `identity_id` — PK, UUIDv4 aleatorio en representación canónica lowercase con guiones; opaco, inmutable y no reutilizable. Lo genera exclusivamente Identity Authority. No se normaliza ni se regenera silenciosamente ante una colisión.
- `identity_kind` — USER, AGENT, SERVICE, WATCHER o SYSTEM.
- `identity_status` — ACTIVE, SUSPENDED o REVOKED, preservando el vocabulario legacy.
- `revision` — entero positivo, monotónico por identidad.
- `created_at`, `updated_at` — UTC.

Reglas:
- No convertir estados legacy a ACTIVE/INACTIVE/DELETING/DELETED por similitud nominal.
- REVOKED es terminal.
- La creación de una identidad USER canónica debe ocurrir en la misma UoW que su UserId.
- SERVICE permanece reservado y no adquiere autenticación ni capacidades por estar modelado.
- Los registros no USER existentes se preservan; su migración operacional requiere especificación separada.

### 3.2 `atlas_users`

Tabla de la autoridad emisora de UserId.

Campos propuestos:

- `user_id` — PK global y canónico Atlas (`UserId`), UUIDv4 aleatorio en representación canónica lowercase con guiones; opaco, estable, inmutable y no derivado de atributos. Lo genera exclusivamente Identity Authority. No se normaliza ni se regenera silenciosamente ante una colisión.
- `identity_id` — FK a `identity_records`, UNIQUE y NOT NULL.
- `created_at`.

Restricciones:
- `identity_id` debe identificar una Identity de tipo USER. La regla se valida en servicio y mediante trigger SQLite, porque una CHECK no puede consultar otra tabla.
- UNIQUE(identity_id) y PK(user_id) materializan la relación 1:1.
- Para una nueva identidad canónica, alta de `identity_records` y `atlas_users` es una sola UoW.
- No se deriva UserId de email, nombre, teléfono, issuer, subject ni identity_id.
- UserId e identity_id usan UUIDv4 aleatorio y canónico. No se aplica la política UUIDv7 de `src/atlas/memory/identifiers.py`: su alcance corresponde a identificadores de Memory y no se generaliza a Identity Authority.

Los USER legacy sin correspondencia canónica demostrable no se insertan aquí ni se convierten por inferencia.

### 3.3 `identity_issuers`

Registro confiable de issuers configurados por Atlas.

Campos propuestos:

- `issuer_id` — PK interno estable.
- `issuer_state` — ACTIVE, SUSPENDED o REVOKED.
- `revision` — entero positivo.
- `configuration_ref` — referencia opaca a configuración validada.
- `keyset_ref` — referencia opaca a material de claves administrado fuera de SQLite.
- `trust_policy_version` — versión de política aplicada.
- `created_at`, `updated_at`, `revoked_at`.

Reglas:
- El caller nunca declara un issuer arbitrario como confiable.
- La URL/identificador presentado por un proveedor solo se acepta después de resolverlo contra este registro.
- No almacenar claves privadas, tokens, client secrets ni credenciales en SQLite.
- SUSPENDED bloquea nuevas verificaciones y admisiones dependientes hasta una decisión de recuperación de confianza.
- REVOKED es terminal; no se reactiva la misma entrada como si no hubiera ocurrido la revocación.
- El protocolo, discovery, rotación y validación criptográfica se especifican en B1-B-03D; no se infieren de estos campos.

### 3.4 `identity_bindings`

Un binding externo exacto hacia una Identity(USER).

Campos propuestos:

- `binding_id` — PK, UUIDv4 aleatorio en representación canónica lowercase con guiones; opaco e inmutable. Lo genera exclusivamente Identity Authority. Esta decisión fija el formato futuro, pero no autoriza implementar bindings externos en esta fase.
- `identity_id` — FK a Identity(USER).
- `issuer_id` — FK a `identity_issuers`.
- `binding_state` — ACTIVE o REVOKED.
- `revision` — entero positivo.
- `verified_at`, `created_at`, `revoked_at`.
- Referencia opaca a la evidencia de verificación, sin tokens ni credenciales.

El subject externo no se trata como email ni como identificador global. La pareja exacta `(issuer_id, subject)` es única y no reasignable, incluso después de revocar el binding.

**Decisión física pendiente y bloqueante:** el subject no debe guardarse en claro sin una política de protección. La opción preferida para lookup es un digest determinista con clave (HMAC) por issuer, conservando el material de clave fuera de SQLite y usando una referencia de almacenamiento cifrado si se necesita recuperar el valor original. La rotación debe preservar la unicidad histórica; no se puede retirar una clave mientras sea necesaria para detectar una pareja ya registrada. Algoritmo, proveedor de secretos, backup y rotación deben aprobarse antes de habilitar bindings externos.

Una futura tabla auxiliar `identity_binding_subject_keys` puede conservar fingerprints por versión de clave para rotación sin perder unicidad. No se implementa hasta fijar el contrato criptográfico.

### 3.5 Evidencia y replay

La evidencia de autenticación es externa a los agregados canónicos. El modelo persistente solo conserva referencias opacas y el mínimo dato de replay necesario.

Se recomienda una tabla de consumos one-shot para nonce/replay, con unicidad por issuer, audience y digest de nonce, y expiración explícita. El material original de token, assertion, firma o secreto no se persiste. El esquema exacto pertenece a B1-B-03D y depende del protocolo seleccionado.

## 4. VerifiedIdentityContext

Es un objeto efímero emitido por Identity Authority después de verificar una cuenta externa y resolver el binding canónico. No es una fila de identidad, binding, Grant ni sesión permanente.

Debe contener como mínimo los campos aprobados en B1-A-06: context_id, identity_id, identity_type=USER, identity_revision, user_id, binding_id, binding_revision, issuer_id confiable, authenticated_at, verified_at, expires_at y verification_ref opaca.

No se emite si:
- issuer desconocido, suspendido, revocado o no verificable;
- firma, audience, nonce, expiry o subject no válidos;
- Identity o binding no activos;
- revisión obsoleta o discrepante;
- no se puede resolver UserId↔Identity(USER) de forma única.

CAM verifica el contexto y el actor efectivo por separado. La presencia del contexto no concede delegación ni autorización.

## 5. PRIVATE_MEMORY_AUTHORIZATION y schema v4

PRIVATE authorization permanece como agregado CAM propio, separado de Grant PROJECT. Su persistencia futura debe contener como mínimo los campos conceptuales aprobados en B1-A-06 §2.1: authorization_id, owner_identity_id, consumer_id, memory_id, permissions, revision, status, created_at, expires_at y revoked_at.

La autoridad canónica de `consumer_id` no está seleccionada. No crear tabla consumers ni derivar el identificador de identity_id.

La ampliación exige:
- `AuthorityKind.PRIVATE_MEMORY_AUTHORIZATION`;
- revisión independiente en AuthorizationRevisionSet cuando el scope sea PRIVATE;
- validación que prohíba usar revisión Grant para PRIVATE;
- invalidation mapping, source CAS, idempotencia y recovery evidence;
- pruebas negativas de separación PRIVATE/PROJECT.

**Evolución de v4:** las tablas `authority_change_operations` y `authority_change_invalidations` contienen CHECK constraints que enumeran AuthorityKind y hoy excluyen PRIVATE_MEMORY_AUTHORIZATION. La solución propuesta es una migración v5 aditiva que reconstruya transaccionalmente las tablas afectadas y sus dependencias FK, copie y verifique cada fila existente, amplíe los CHECK y recree índices. No se modifica el SQL ni los checksums de v1–v4. No se reconstruye la base completa. La migración solo se aprobará tras pruebas de preservación de todas las filas, claves, índices y FKs, `PRAGMA foreign_key_check` e integridad.

La implementación debe decidir si la reconstrucción integral del conjunto de siete tablas de authority-change es necesaria para preservar correctamente las referencias; no se permite una modificación parcial que deje FKs apuntando a tablas antiguas.

## 6. Fronteras UoW y concurrencia

- Crear UserId + Identity(USER): una UoW local, una sola vez.
- Añadir binding externo: validar evidencia fuera de SQLite; luego CAS de Identity/issuer y alta de binding en una UoW.
- Revocar binding: CAS de estado/revisión y tombstone; Consistency coordina invalidación/fencing fuera de una falsa atomicidad con el proveedor externo.
- Cambiar issuer trust: CAS de issuer/revisión y coordinación de todos los contextos/admisiones afectados.
- Crear/revocar PRIVATE authorization: CAM persiste su agregado y revisión; Consistency coordina invalidación, sin escribir la autoridad canónica de CAM.
- Los endpoints externos nunca participan en la transacción SQLite.
- Las operaciones con efectos externos se reservan de forma idempotente; timeout o respuesta ambigua conserva estado BLOCKED/UNRESOLVED hasta reconciliación.

No se comparan revisiones de autoridades diferentes. Cada CAS compara autoridad, ID y revisión exactos.

## 7. Migraciones y compatibilidad

1. Preservar migrations v1–v4 exactamente, incluyendo nombre y checksum.
2. Añadir una migración v5 nueva; no editar migraciones históricas.
3. Aplicar primero sobre DB temporal generada desde v1, v2, v3 y v4, y sobre copias de fixtures representativas.
4. Validar conteos, IDs, revisiones, tombstones, FKs, índices, constraints y checksums antes/después.
5. No migrar automáticamente `AuthenticatedUserSubject.subject_user_id` a UserId canónico ni a subject de proveedor.
6. No reescribir `Memory.owner_id`.
7. No ejecutar migración sobre la DB real hasta tener backup verificado, restore probado y autorización de ejecución específica.

Rollback: antes del commit de una migración transaccional fallida, SQLite revierte la UoW. Después de aceptar nuevas escrituras, no se promete downgrade destructivo; se requiere restauración controlada y reconciliación, especialmente si existen revocaciones, tombstones o Forget posteriores.

## 8. Matriz de propiedad y prohibiciones

| Tabla/objeto | Dominio propietario | No permitido |
|---|---|---|
| identity_records / atlas_users / identity_issuers / identity_bindings | Identity Authority | CAM o Consistency no escriben su estado canónico |
| PRIVATE authorization | CAM | Identity no la crea ni la revoca |
| authority-change ledger / journal / projections | Consistency | No replica datos de identidad ni Grants |
| Memory metadata | Memory | Identity no modifica owner/scope |
| runtime state | Broker/adaptador correspondiente | Identity no ejecuta Docker |

## 9.1 Alcance del primer incremento de implementación

El primer incremento autorizado se limita a la persistencia interna de `UserId` y `Identity(USER)`, su relación 1:1, restricciones SQLite, operaciones transaccionales y control de revisión/CAS, con pruebas de unicidad, concurrencia, conflicto CAS y rollback. Aunque el formato UUIDv4 de `binding_id` queda decidido para mantener coherencia del modelo futuro, los issuers, bindings externos, evidencia, replay y autenticación externa permanecen fuera de este incremento. Tampoco se implementa `PRIVATE_MEMORY_AUTHORIZATION` ni se amplía el alcance de la migración v5 de coordinación en este trabajo.

## 9. Criterios de conformidad B1-B-03B

- Cardinalidad UserId↔Identity(USER) 1:1 demostrada por constraints y pruebas.
- Un binding exacto solo puede apuntar a una Identity(USER).
- La pareja issuer/subject no se reasigna tras revocación.
- Identity Authority no concede permisos.
- PRIVATE authorization no usa Grant ni depende de él.
- El schema v4 histórico permanece verificable; v5 conserva íntegramente sus datos.
- Ningún secreto, token, clave privada, payload Memory o embedding se almacena en estas tablas.
- Toda ambigüedad, excepción, revisión obsoleta o autoridad no disponible produce DENY/BLOCKED.
- No se habilitan flujos externos hasta cerrar B1-B-03C y B1-B-03D.

## 10. Decisiones adoptadas y decisiones bloqueantes restantes

### 10.1 Decisiones adoptadas (15-11-2026)

- `UserId`, `identity_id` y `binding_id` serán UUIDv4 aleatorios, en representación canónica lowercase con guiones.
- Identity Authority será el único componente autorizado para generar estos identificadores.
- Los identificadores son opacos, estables e inmutables; no se derivan de email, teléfono, nombre, issuer, subject, cuenta externa ni de otro identificador.
- No se normalizan entradas no canónicas. Una colisión o conflicto de unicidad rechaza la operación; no se reintenta con otro ID de forma silenciosa ni se sobrescribe un registro.
- Los identificadores no son credenciales, tokens de sesión ni prueba de autenticación o autorización.
- La relación `UserId` ↔ `Identity(USER)` es 1:1, reforzada por PK/UNIQUE/FK y validación de tipo USER. Su alta ocurre en una única UoW atómica.
- Las actualizaciones usan revisión monotónica y CAS sobre la revisión esperada; una revisión obsoleta produce conflicto sin sobrescribir el estado vigente.
- Las operaciones de escritura SQLite utilizan la infraestructura transaccional existente (`BEGIN IMMEDIATE`); cualquier fallo revierte la operación completa.
- Las migraciones históricas v1–v4 son inmutables. La persistencia canónica requerirá una nueva migración aditiva, diseñada y probada antes de aplicarse a cualquier base real.
- Los contratos legacy y los componentes de Memory se conservan; la política UUIDv7 de Memory no se extiende a Identity Authority.

### 10.2 Decisiones bloqueantes restantes

1. Proveedor de secretos y representación segura/lookup del subject externo.
3. Protocolo(s) de issuer y política de claves/rotación.
4. Fuente canónica verificable de consumer_id.
5. Política de recuperación de cuenta y protección del último método de acceso.
6. Mapeo legacy verificable.
7. Diseño y pruebas de la migración v5 sobre el código exacto de implementación.

**Salida B1-B-03B:** modelo físico candidato y estrategia de migración definidos; implementación y activación permanecen bloqueadas por las decisiones anteriores y por aprobación específica de migración.
