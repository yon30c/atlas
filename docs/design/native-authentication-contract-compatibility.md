# Contrato de compatibilidad: autenticación nativa e Identity Authority

**Estado:** decisión arquitectónica aprobada; contrato técnico propuesto para revisión antes de implementación.  
**Fecha:** 2026-11-17  
**Rama:** `feature/terminal-commands`  
**Baseline:** B1-B-03A cerrado normativamente; diseños B1-B-03B, B1-B-03C y B1-B-03D; `native-authentication-authority-technical-design.md`.  
**Alcance:** contrato lógico y compatibilidad. No modifica código, esquema SQLite, migraciones, credenciales, sesiones, bootstrap ni infraestructura.

## 1. Decisión aprobada

Atlas utilizará una única ruta de identidad canónica hacia CAM para autenticación nativa y para futuros proveedores externos:

1. Authentication Authority verifica el método de autenticación y produce evidencia de autenticación confiable.
2. Identity Authority valida la evidencia, resuelve el issuer y binding exactos, confirma Identity(USER) y UserId canónico, y emite `VerifiedIdentityContext`.
3. La frontera confiable de Atlas construye el `OperationContext` a partir de ese contexto verificado y de registros confiables de proyecto/entorno.
4. CAM autoriza cada operación de forma independiente.

La diferencia entre autenticación nativa y externa reside en el verificador de evidencia específico del issuer. No habrá una ruta alternativa que convierta un login, una sesión, un `UserId` o un `OperationContext` declarado por el caller en identidad autenticada.

Esta aprobación no activa autenticación ni autoriza implementación operativa.

## 2. Compatibilidad normativa

### 2.1 B1-B-03A — modelo canónico y bindings

- Identity Authority es la única autoridad que crea/resuelve la relación 1:1 `UserId ↔ Identity(USER)`.
- `UserId`, `identity_id`, `binding_id`, issuer y subject son identificadores distintos.
- El login handle es un atributo de búsqueda de Authentication Authority; nunca es UserId, identity_id ni subject.
- El subject nativo es opaco, estable y no reutilizable.
- El binding nativo usa la pareja exacta `(issuer_id, subject)`, con las mismas reglas de unicidad histórica y no reasignación que un binding externo.
- Un binding identifica una relación de autenticación; no concede Grants ni permisos.
- No se reinterpretan `AuthenticatedUserSubject` ni `AtlasIdentityBindingAdapter` legacy como prueba autenticada.

### 2.2 B1-B-03B — persistencia y ownership

- Authentication Authority será propietaria de autenticadores, verificadores de contraseña y sesiones.
- Identity Authority será propietaria de `identity_records`, `atlas_users`, issuers, bindings y sus revisiones.
- CAM será propietaria de Grants y autorizaciones.
- Consistency coordinará invalidación/fencing; no escribirá los agregados canónicos de las otras autoridades.
- La persistencia canónica de identidad y el agregado de credenciales no se fusionan por conveniencia.
- El diseño físico actual de issuer contempla referencias de configuración y keyset externos. Antes de implementar el issuer nativo se debe ampliar explícitamente el modelo con un perfil de verificación por método; no se debe insertar un issuer nativo fingiendo que dispone de keyset externo.
- No se editarán migraciones históricas. Cualquier evolución física requerirá migración nueva, pruebas de upgrade y autorización específica.

### 2.3 B1-B-03C — lifecycle y seguridad

- Suspender/revocar un autenticador bloquea el método nativo afectado y obliga a invalidar las sesiones y pruebas que dependan de él.
- Revocar un binding conserva su tombstone y reserva la pareja issuer/subject.
- Revocar un autenticador no revoca automáticamente Identity(USER), ni revocar un binding revoca automáticamente todos los demás bindings.
- No hay transición de binding/issuer REVOKED a ACTIVE.
- Recovery, merge, unlink de la única credencial y reset privilegiado permanecen deshabilitados hasta aprobar políticas específicas.
- Cambiar contraseña incrementa `credential_revision`; una sesión o prueba con revisión obsoleta no puede admitirse.

### 2.4 B1-B-03D — evidencia y VerifiedIdentityContext

B1-B-03D define un perfil de validación por issuer, con issuer confiable, audience, subject exacto, expiración, nonce/replay y revisiones. El issuer nativo no debe simular una firma o assertion externa.

Se añade conceptualmente un perfil nativo en el que Authentication Authority verifica Argon2id y presenta a Identity Authority una prueba interna verificable. Se mantienen los invariantes comunes: procedencia confiable, issuer activo, subject exacto, vigencia, consumo anti-replay, binding/Identity activos y revisiones actuales.

Los campos y semántica de `VerifiedIdentityContext` permanecen comunes y sin relajación: `context_id`, `identity_id`, `identity_type=USER`, `identity_revision`, `user_id`, `binding_id`, `binding_revision`, `issuer_id`, `authenticated_at`, `verified_at`, `expires_at` y `verification_ref`.

El contexto es efímero; no es contraseña, token de sesión, Grant ni prueba de delegación.

## 3. Contrato lógico entre autoridades

Los siguientes nombres son ilustrativos y no constituyen todavía API pública ni firmas Python aprobadas.

### 3.1 Authentication Authority

Responsabilidades:
- localizar el autenticador por login handle dentro del realm nativo confiable;
- verificar la contraseña con Argon2id y parámetros versionados;
- aplicar protección contra enumeración, abuso y fuerza bruta;
- comprobar estado y revisión del autenticador;
- emitir evidencia nativa de corta duración;
- crear, resolver, rotar y revocar sesiones opacas;
- registrar evidencia mínima de seguridad sin secretos.

Operaciones conceptuales:

- `authenticate(login_handle, password, request_context) -> NativeAuthenticationProofRef | Denied`
- `create_session(proof_ref, session_policy) -> SessionCredential`
- `resolve_session(session_credential) -> AuthenticatedSession | Denied`
- `revoke_session(session_id, reason) -> RevocationResult`
- `change_password(authenticated_context, old_password, new_password) -> CredentialChangeResult`

Authentication Authority no emite UserId, no crea bindings, no crea VerifiedIdentityContext y no decide permisos.

### 3.2 Prueba nativa

La prueba debe ser una referencia opaca a evidencia generada y controlada por Authentication Authority, no un DTO que el caller pueda construir con `issuer_id`, `subject` y timestamps arbitrarios.

Requisitos mínimos:
- referencia aleatoria no predecible;
- issuer/realm nativo y subject exactos;
- revisión del autenticador;
- `authenticated_at`, `verified_at`, expiración y referencia de auditoría;
- vinculación a la solicitud de autenticación y consumo de un solo uso;
- rechazo por replay, expiración, revisión obsoleta, estado no activo o realm incorrecto;
- ninguna contraseña, hash, token de sesión o secreto reutilizable en la prueba;
- validación de procedencia por un puerto privado entre autoridades, no por confianza en datos proporcionados por el caller.

La implementación debe escoger un mecanismo verificable de procedencia (por ejemplo, referencia opaca respaldada por un store privado y consumo atómico, o evidencia autenticada criptográficamente). No se acepta que la privacidad del constructor de una clase Python sea la única barrera de seguridad.

### 3.3 Identity Authority

Responsabilidades:
- resolver el issuer nativo contra el registro de confianza;
- verificar el perfil de verificación nativo y la procedencia de la prueba;
- resolver el subject exacto al binding existente;
- verificar issuer, binding e Identity(USER), estados y revisiones;
- resolver la relación canónica 1:1 UserId↔Identity(USER);
- emitir el VerifiedIdentityContext común.

Operación conceptual:

- `resolve_native_authentication(proof_ref) -> VerifiedIdentityContext | Denied`

Identity Authority no verifica contraseñas, no almacena hashes de contraseñas, no administra sesiones y no concede permisos.

### 3.4 Frontera confiable de consola/API

- Resuelve la sesión mediante Authentication Authority.
- Solicita a Identity Authority un contexto verificado fresco o dentro de la política de vigencia aprobada.
- Resuelve proyecto, entorno y workspace desde registros confiables.
- Construye `OperationContext` inmutable.
- No acepta del caller `user_id`, `identity_id`, issuer, subject, binding, proyecto, entorno ni estado de autenticación como evidencia de autoridad.
- Pasa la operación a CAM; la autenticación satisfactoria no equivale a autorización.

## 4. Ciclo de sesión y operación

1. Login handle y contraseña llegan a la frontera confiable por transporte protegido.
2. Authentication Authority verifica credenciales y controles de riesgo.
3. Se crea una prueba nativa de un solo uso.
4. Identity Authority consume/valida la prueba y emite VerifiedIdentityContext.
5. Authentication Authority entrega una sesión opaca al cliente, almacenando únicamente su digest.
6. En cada solicitud protegida, la frontera resuelve la sesión y obtiene contexto verificado vigente conforme a la política.
7. La frontera obtiene proyecto/entorno/workspace confiables y construye OperationContext.
8. CAM evalúa la operación, scope, recurso, Grant, revisiones y condiciones adicionales.

La sesión no se pasa a CAM como permiso. No se cachea VerifiedIdentityContext más allá de su expiración ni se admite una revisión obsoleta. La estrategia de renovación y reautenticación reciente se definirá por clase de operación, sin TTL universal implícito.

## 5. Bootstrap y atomicidad

El bootstrap inicial debe crear, de forma consistente, Identity(USER), UserId, subject nativo, autenticador y binding. No se permitirá una cuenta autenticable sin binding canónico ni un binding huérfano.

- Si todas las escrituras pertenecen a la misma base y UoW, la creación debe ser atómica.
- Si las fronteras de autoridad impiden una transacción única, se requiere saga durable con estados PENDING/COMMITTED/UNRESOLVED, idempotencia y reconciliación.
- La asignación inicial de privilegios es un paso CAM separado, explícito y auditado.
- La prueba bootstrap es one-shot, generada fuera de la imagen, con digest, expiración y consumo atómico.
- Bootstrap de usuario Atlas no es bootstrap de privilegios del host.

El mecanismo exacto de coordinación queda bloqueado hasta inspeccionar las UoW y composiciones de la rama objetivo.

## 6. Fail-closed e invalidación

Debe producir DENY/BLOCKED cuando:
- autenticador inexistente, suspendido, revocado o con hash/parámetros no soportados;
- prueba desconocida, falsificada, expirada, repetida o de otro realm;
- issuer no confiable o revisión obsoleta;
- subject sin binding exacto, binding revocado o reservado;
- Identity no USER, suspendida/revocada o revisión inconsistente;
- relación UserId↔Identity(USER) ausente o ambigua;
- sesión expirada, revocada, rotada o ligada a revisión anterior;
- Consistency no confirma el fencing requerido;
- CAM no concede la operación solicitada.

El cambio de contraseña, suspensión/revocación de autenticador, cambio/revocación de binding e Identity o pérdida de confianza del issuer deben invalidar los contextos/admisiones dependientes según el dominio de Consistency. Si la invalidación no puede confirmarse, no se admite la operación protegida.

## 7. Discrepancias y decisiones aún abiertas

1. **Issuer nativo en el esquema:** definir `verification_profile` o discriminador equivalente y reglas para `configuration_ref`/`keyset_ref`; no asumir que el esquema B1-B-03B actual lo soporta.
2. **Protección del subject:** escoger proveedor de secretos, fingerprint determinista, almacenamiento cifrado y rotación que preserve unicidad histórica.
3. **Prueba interna:** elegir store/artefacto de procedencia, consumo atómico, replay, TTL y correlación.
4. **Sesiones:** algoritmo de digest, generación, rotación, expiración, inactividad, almacenamiento y cookies/CSRF para interfaz web.
5. **Argon2id:** librería, parámetros y benchmark; parámetros versionados y rehash controlado.
6. **Login handle:** normalización, unicidad, cambios y throttling sin enumeración ni bloqueo permanente explotable.
7. **Bootstrap:** transacción común o saga; reserva, concurrencia, fallo parcial y reconciliación.
8. **Consistency:** confirmar qué coordinator/fencing real existe en el checkout objetivo y cómo se invalida por cambios de credenciales/issuer/binding.
9. **Composición:** identificar UoW, repositorios y migraciones realmente presentes en `feature/terminal-commands`; el código consultado hasta ahora muestra `IdentityAuthorityPort` y `CanonicalUserIdentity`, pero eso no demuestra autenticación ni binding operativo.
10. **Recovery:** permanece deshabilitado; requiere decisión separada.

## 8. Secuencia de implementación propuesta

1. Cerrar este contrato y las decisiones bloqueantes sin tocar código.
2. Inspeccionar en el checkout exacto el schema, migraciones, UoW, Identity Authority, Consistency y composición de consola.
3. Diseñar modelos/puertos de Authentication Authority y el perfil de issuer nativo sin alterar contratos legacy.
4. Diseñar persistencia de autenticadores/sesiones/bootstrap y estrategia de UoW/saga.
5. Implementar pruebas de dominio y persistencia aisladas, sin habilitar login en consola.
6. Integrar sesión → prueba nativa → Identity Authority → VerifiedIdentityContext en un adaptador de prueba no expuesto.
7. Reanudar Cycle 3.2 para contexto de consola y ownership de proyecto/entorno/workspace; mantener fail-closed.
8. Solo después de cerrar pruebas y gates, solicitar aprobación separada para habilitar autenticación operativa.

## 9. No incluido ni autorizado

Este documento no:
- modifica B1-B-03A/B/C/D ni reabre sus decisiones normativas;
- aprueba linking/unlink/recovery/merge externos;
- habilita login, bootstrap, sesiones o cambios de credenciales;
- aprueba una migración SQLite ni cambia schema v4/v5;
- autoriza migrar datos, desplegar, cambiar el host o modificar PAM/sudoers/systemd/SSH;
- permite usar UID/GID, `getuser()`, hostname o acceso al host como identidad Atlas;
- cambia el gate de Cycle 3.1 ni autoriza escrituras en workspace;
- convierte autenticación en autorización CAM.

**Conclusión:** autenticación nativa y externa convergen en la misma Identity Authority y VerifiedIdentityContext; solo cambia el perfil de verificación del issuer. Las interfaces y el perfil nativo quedan definidos a nivel lógico, con decisiones físicas y de implementación todavía bloqueadas.
