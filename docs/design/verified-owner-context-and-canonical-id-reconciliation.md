# Contrato de reconciliación: identidad canónica y contexto de propietario

**Estado:** hallazgos y propuesta técnica para revisión; no modifica contratos normativos ni autoriza implementación.
**Rama de inspección:** `feature/cycle-3-2-c1-native-credentials`.
**Propósito:** fijar la semántica que debe respetar la frontera de autenticación y detectar incompatibilidades antes de conectar bootstrap o emisión inicial de CAM.

## 1. Decisión base ya establecida

Este documento no redefine la identidad canónica. Consolida los contratos existentes:

- `UserId` identifica al usuario propietario de Atlas.
- `Identity.identity_id` identifica al principal interno que ejecuta la operación.
- Para una identidad USER, Identity Authority mantiene una relación canónica 1:1 entre ambos; son identificadores distintos y no se derivan uno del otro ni tienen que ser textualmente iguales.
- `(issuer_id, subject)` identifica una cuenta/principal en un issuer concreto y se resuelve mediante un binding confiable hacia `identity_id`.
- `binding_id`, `issuer_id`, `subject`, `identity_id` y `user_id` son conceptos/identificadores distintos.
- Un binding no concede permisos.

Fuentes de precedencia: `docs/design/b1-b03d-verified-identity-and-evidence.md`, `docs/contracts/operation-context.md`, `docs/contracts/b1-b03a-02-canonical-user-and-external-identity-binding.md` y `docs/design/native-authentication-contract-compatibility.md`. En caso de diferencia, prevalecen los contratos normativos aprobados B1-A-06/B1-B-03A y sus aclaraciones aprobadas, no este documento de hallazgos.

## 2. Flujo de confianza y correspondencia

La ruta de usuario autenticado debe mantener separadas estas etapas:

1. Authentication Authority verifica una credencial/método y produce evidencia interna confiable.
2. Identity Authority valida procedencia, issuer, subject exacto, binding, estados y revisiones; resuelve la relación canónica y emite `VerifiedIdentityContext`.
3. La frontera confiable de Atlas valida la vigencia del contexto y construye `OperationContext` usando datos confiables.
4. CAM evalúa por separado actor, acción, recurso, scope, revisiones, vigencia y delegación.

El `VerifiedIdentityContext` debe conservar los campos B1-B-03D:
`context_id`, `identity_id`, `identity_type=USER`, `identity_revision`, `user_id`, `binding_id`, `binding_revision`, `issuer_id`, `authenticated_at`, `verified_at`, `expires_at` y `verification_ref`.

Para una acción directa de propietario USER, la frontera debe comprobar como mínimo:

- `actor.kind == USER` y `actor.status == ACTIVE`;
- `actor.identity_id == verified.identity_id`;
- `actor.revision == verified.identity_revision`;
- `context.user_id == verified.user_id`;
- `context.delegation is None`;
- binding, issuer e identidad siguen vigentes y en las revisiones verificadas;
- el contexto verificado no ha expirado y su evidencia corresponde a la solicitud.

Para un actor no USER, el `VerifiedIdentityContext` del propietario no autentica al actor. La identidad del actor y la delegación requieren sus propias autoridades y verificaciones; no se debe comparar `actor.identity_id` con `context.user_id`.

## 3. Qué significa OperationContext

`OperationContext` es un contenedor inmutable de atribución/contexto, no una credencial. Sus campos `actor` y `user_id` no demuestran por sí solos que hubo autenticación, que el binding existe o que el usuario autorizó la operación.

Por tanto:

- Nunca aceptar `user_id`, `actor`, issuer, subject o binding enviados por el caller como evidencia de identidad.
- No convertir el constructor de `OperationContext` en autoridad de autenticación.
- No tratar `origin`, `created_at`, `request_id` o `correlation_id` como evidencia de autenticación.
- La procedencia de `OperationContext` debe ser una frontera confiable que recibió y validó un `VerifiedIdentityContext` vigente, o un mecanismo de autoridad distinto expresamente aprobado para la operación.
- Los servicios sensibles deben tener una frontera de invocación que impida que un caller no confiable fabrique un contexto y llame directamente a la operación privilegiada. Si el servicio necesita verificar esa procedencia por sí mismo, debe recibir evidencia/puerto verificable; no debe confiar en un booleano o DTO declarativo.

El contexto puede transportar `user_id` canónico para correlación y evaluación CAM, pero ese campo no sustituye la evidencia de autenticación.

## 4. Hallazgos del código inspeccionado

### 4.1 Modelos canónicos

`src/atlas/core/user_identity.py` define `CanonicalUserIdentity(user_id, identity)`, valida ambos UUIDv4 y exige `identity.kind == USER`. No exige igualdad textual entre los IDs.

`src/atlas/adapters/sqlite/identity_authority.py` crea UUIDv4 independientes para `user_id` e `identity_id`, los persiste como pareja canónica y los recupera mediante JOIN. Esta implementación confirma que cualquier comparación directa entre ambos campos es incorrecta.

### 4.2 Contrato OperationContext

`src/atlas/core/context.py` valida que `actor` sea `Identity`, que `user_id` sea una cadena no vacía y que `created_at` sea UTC. No contiene un `VerifiedIdentityContext`, una referencia verificable a él ni una prueba de procedencia. Esto es coherente con que el contexto sea un DTO de operación, pero obliga a cerrar la frontera confiable en otra capa.

### 4.3 Servicios CAM con comparación incompatible

En la rama inspeccionada:

- `GrantManagementService._validate_owner_context` exige `actor.identity_id == context.user_id`.
- `GrantRenewalService._validate_owner_context` exige la misma igualdad.
- Ambos servicios usan después `context.user_id` para comparar `Grant.owner_user_id`, lo cual sí corresponde al significado de UserId.
- Por tanto, la comparación actor↔usuario es la parte semánticamente incompatible; la comparación owner_user_id↔context.user_id debe mantenerse.

No corregirlo reemplazando una comparación por otra sin introducir la verificación del contexto canónico. La validación correcta para actor USER compara `actor.identity_id` con el `identity_id` verificado y compara `context.user_id` con el `user_id` canónico verificado.

### 4.4 Cobertura de pruebas actual

`tests/unit/test_grant_management.py` construye su fixture con `actor.identity_id = "user-001"` y `context.user_id = "user-001"`; el test de propietario inválido también prueba IDs diferentes como rechazo. Esta suite codifica la igualdad accidental y no contiene un caso válido donde UserId e identity_id sean distintos pero estén relacionados por una pareja canónica verificada.

La cobertura debe evolucionar para incluir:
- pareja canónica válida con IDs distintos;
- actor USER distinto del identity_id verificado;
- UserId contextual distinto del user_id verificado;
- identidad o binding con revisión obsoleta;
- contexto expirado;
- contexto fabricado por caller sin evidencia verificable;
- actor no USER sin identidad propia/delegación válida;
- actor USER delegado o contexto con delegación no permitida para acción directa.

No se afirma aquí que las pruebas existentes fallen; se identifica un hueco de especificación y cobertura.

## 5. Requisitos para la reconciliación futura

Antes de reutilizar emisión/renovación de Grants en bootstrap:

1. Definir el puerto/servicio confiable que valida o emite `VerifiedIdentityContext` y resuelve la pareja canónica.
2. Definir cómo la frontera construye `OperationContext` exclusivamente desde ese resultado y desde Project/Environment obtenidos de fuentes confiables.
3. Reemplazar conceptualmente la igualdad `actor.identity_id == context.user_id` por comprobaciones separadas contra `verified.identity_id` y `verified.user_id`.
4. Mantener la comparación `grant.owner_user_id == context.user_id`.
5. Hacer que la emisión inicial de Grant requiera además la evidencia independiente de acción directa definida por el contrato de bootstrap; un contexto autenticado no es por sí solo evidencia suficiente de confirmación de provisión.
6. Mantener CAM como evaluador ordinario para operaciones posteriores; la evidencia excepcional de provisión no se convierte en Grant ni en bypass general.
7. Asegurar que la frontera privilegiada no pueda ser invocada con un `OperationContext` construido por el caller.
8. Añadir pruebas de IDs distintos, falsificación, replay, expiración, revisión, delegación y fallos de las autoridades.

No se prescribe todavía una firma Python ni un cambio físico. La implementación debe preservar las autoridades y contratos existentes y coordinar las escrituras con la estrategia de consistencia aprobada.

## 6. Límites

Este documento no:

- cambia `Identity`, `CanonicalUserIdentity` ni `OperationContext`;
- introduce o modifica `VerifiedIdentityContext` en código;
- cambia servicios CAM, Grant, renovación o sus pruebas;
- crea bindings, issuers, sesiones, proyectos, entornos o Grants;
- autoriza migraciones, login operativo, bootstrap, PAM, host, systemd, sudoers o despliegue;
- declara que la UoW actual coordine el Consistency Journal o Recovery Gate.

**Estado final:** hallazgo documentado para revisión. Mantener los gates cerrados hasta aprobar el contrato de procedencia y verificar la reconciliación de los servicios consumidores.
