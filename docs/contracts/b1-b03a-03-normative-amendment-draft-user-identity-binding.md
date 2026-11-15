# B1-B-03A-03 — Borrador de enmienda normativa: UserId e Identity Binding

**Estado:** BORRADOR NORMATIVO — decisiones A–G aprobadas; texto de enmienda pendiente de aprobación final.  
**Fecha:** 15 de noviembre de 2026.  
**Documento de decisión:** [B1-B-03A-02 — Modelo lógico de UserId canónico y bindings externos](b1-b03a-02-canonical-user-and-external-identity-binding.md).  
**Alcance:** proponer texto coordinado para B1-A-06, identity.md y operation-context.md.  
**No autorizado por este documento:** editar los contratos normativos vigentes, cambiar código, esquema SQLite, datos, migraciones o runtime.

---

## 1. Decisiones de base ya aprobadas

El propietario aprobó A–G de B1-B-03A-02:

- Identity Authority es la autoridad canónica que emite UserId y administra su relación con Identity(USER).
- Existe una relación 1:1 entre UserId e Identity(USER).
- Una identidad USER puede tener múltiples bindings externos.
- Cada pareja exacta (issuer_id, subject) es única y no reasignable; un binding revocado permanece reservado.
- Vincular una cuenta requiere una sesión verificada existente, prueba reciente de control de la cuenta nueva y confirmación explícita. No se vincula por email ni se fusionan identidades automáticamente.
- Desvincular es irreversible y requiere conservar un método de acceso/recuperación utilizable.
- VerifiedIdentityContext incorpora UserId canónico y binding_id/revisión exactos.
- Los contratos y adaptadores legacy se conservan hasta una migración explícita y no se reinterpretan como evidencia completa de autenticación externa.

La aprobación de A–G es aprobación del modelo lógico, no de este texto normativo todavía.

## 2. Propuesta para B1-A-06 §4.2 — Identidad y binding

**Reemplazar la sección §4.2 vigente por el siguiente texto:**

### 4.2 Identidad, usuario canónico y binding externo

Atlas distingue tres conceptos:

- **UserId:** identificador global y canónico del usuario Atlas. Es opaco, estable, único, inmutable y no reutilizable. No deriva de correo, nombre, teléfono, issuer, subject ni identity_id. Su emisión y administración corresponden a Identity Authority.
- **identity_id:** identificador interno, canónico, estable, único y no reutilizable de una Identity. Para una cuenta de usuario Atlas, la Identity correspondiente debe ser de tipo USER.
- **External Identity Binding:** vínculo verificable entre una cuenta autenticada de un proveedor externo, identificada por la pareja exacta (issuer_id, subject), y una Identity(USER).

La relación entre UserId e Identity(USER) es exactamente 1:1: cada UserId corresponde a una única Identity(USER), y cada Identity(USER) corresponde a un único UserId. UserId e identity_id son identificadores distintos y no se exige igualdad textual entre ellos.

Una Identity(USER) puede tener cero o varios bindings externos. Cada binding pertenece a una única Identity(USER). Una pareja exacta (issuer_id, subject) no puede vincularse a más de una identidad. La pareja permanece reservada después de la revocación de su binding y no puede reasignarse silenciosamente.

Identity Authority es la autoridad canónica responsable de emitir UserId, mantener la relación UserId↔identity_id y administrar el ciclo de vida de los bindings. Los issuers externos autentican cuentas conforme a la configuración de confianza de Atlas; no emiten ni eligen UserId o identity_id.

El issuer debe resolverse contra un registro/configuración confiable de Atlas. El subject se trata como identificador opaco dentro del espacio de nombres del issuer. Email, nombre, teléfono y otros atributos de perfil no son claves de binding ni prueba suficiente de control o identidad.

Una pareja issuer/subject solo puede vincularse después de verificar la evidencia de autenticación del issuer y la unicidad de la pareja. La vinculación de una cuenta adicional exige una sesión existente verificada de la identidad propietaria, prueba reciente de control de la cuenta nueva y confirmación explícita del propietario. No se permite linking automático por coincidencia de atributos.

La revocación de un binding es irreversible. Un binding revocado se conserva como registro no reutilizable. Desvincular una cuenta no cambia UserId, identity_id, propietario de memorias, Grants ni recursos. El procedimiento debe preservar al menos un método de acceso o recuperación utilizable. El detalle del proceso de recuperación se definirá en un contrato separado.

No se fusionan identidades por coincidencia de atributos. Una fusión, si alguna vez se autoriza, requiere procedimiento separado, prueba de control de ambas identidades, revisión de propiedad, Grants y recursos, y un plan explícito de migración. No se reasignan memorias ni UserId por efecto de vincular o desvincular una cuenta.

Un binding no concede autorización, Grants, permisos PRIVATE, delegación ni propiedad. Toda operación protegida continúa sujeta a CAM y Consistency. Los cambios de binding, revocación o estado invalidan los contextos y admisiones dependientes mediante las revisiones, invalidación y fencing aplicables.

## 3. Propuesta para B1-A-06 §5 — VerifiedIdentityContext

**Reemplazar la lista de campos del contexto de §5 por:**

Identity emite un contexto inmutable conceptual VerifiedIdentityContext con:

- context_id
- identity_id
- identity_type
- identity_revision
- user_id (UserId canónico Atlas)
- binding_id
- binding_revision
- issuer_id (referencia al issuer registrado y confiable)
- authenticated_at
- verified_at
- expires_at
- verification_ref

El contexto acredita que la autenticación externa fue validada y resuelta por Identity Authority hacia la Identity(USER) y UserId indicados, dentro de su vigencia y revisiones. No es un Grant, no constituye autorización permanente y no transporta credenciales ni secretos.

El contexto queda ligado a la revisión de Identity y del binding. CAM debe comprobar vigencia, estado, revisiones actuales y correspondencia exacta del actor y usuario contextual antes de admitir la operación. Una revisión obsoleta, binding revocado, issuer no confiable, expiración o evidencia incompleta producen denegación.

El resto de §5 —separación de Identity y CAM, ausencia de permisos implícitos y coordinación con Consistency— permanece vigente sin cambios.

## 4. Propuesta para identity.md

Añadir después de la sección 5, como nueva sección 5.1:

### 5.1. Relación con el usuario canónico Atlas

Una Identity de tipo USER representa el actor interno de un usuario Atlas, pero identity_id no es el UserId del usuario. Atlas mantiene un UserId global y canónico separado, emitido por Identity Authority.

La relación entre UserId e Identity(USER) es 1:1 y autoritativa. No se almacena ni se infiere mediante igualdad textual entre identificadores. La resolución se obtiene de Identity Authority y debe estar respaldada por un binding interno vigente.

Una Identity(USER) puede tener varios bindings externos verificados, cada uno identificado por (issuer_id, subject) y binding_id. Estos bindings permiten autenticar cuentas externas distintas para la misma identidad interna. La autenticación externa, el binding y la autorización son responsabilidades separadas.

El modelo Identity no incorpora credenciales externas ni secretos. Un binding no concede permisos. La autorización de cada operación corresponde a CAM.

Añadir a la sección 7, decisiones técnicas abiertas:

- **UserId canónico:** el significado global de UserId, su relación 1:1 con Identity(USER) y la autoridad emisora se rigen por B1-A-06 §4.2. Formato físico, generación concreta, persistencia y migración siguen siendo decisiones de implementación pendientes.
- **Bindings externos:** el ciclo de vida lógico y las invariantes de issuer/subject se rigen por B1-A-06 §4.2. Los protocolos concretos de autenticación, registro de issuers y verificación criptográfica requieren especificación técnica por proveedor.

No agregar UserId como campo a la entidad Identity en esta enmienda.

## 5. Propuesta para operation-context.md

**Añadir al final de §3.2 Usuario contextual:**

Para operaciones autenticadas de un usuario Atlas, el user_id contextual debe proceder de un VerifiedIdentityContext vigente emitido por Identity Authority, o de otro mecanismo de autoridad expresamente definido para el tipo de operación. La frontera confiable de Atlas debe construir el OperationContext y establecer el UserId canónico; no debe aceptar un user_id enviado por el caller como prueba de identidad, propiedad o autenticación.

El UserId canónico no es equivalente a actor.identity_id. Para un actor USER, la correspondencia entre ambos se resuelve mediante Identity Authority y la relación 1:1 vigente. En operaciones delegadas, user_id identifica al usuario contextual y actor.identity_id identifica al actor efectivo; la delegación requiere verificación independiente y evaluación de CAM.

**Añadir a §3.3 Separación de responsabilidades:**

La presencia de user_id en OperationContext sigue siendo dato contextual y no concede autorización. Su procedencia confiable permite identificar el usuario contextual, pero CAM debe evaluar por separado acción, recurso, scope, permisos, revisiones y vigencia. Un caller no puede elegir un UserId arbitrario para obtener acceso a memorias u otros recursos.

No se cambia la estructura actual de OperationContext ni se redefine su campo user_id en esta enmienda.

## 6. Compatibilidad y límites

- Se conservan AuthenticatedUserSubject, IdentitySubjectBindingPort y AtlasIdentityBindingAdapter como contratos legacy hasta una migración aprobada.
- subject_user_id no se reinterpretará como subject externo de un issuer.
- La implementación legacy no podrá emitir VerifiedIdentityContext nuevo por inferencia.
- No se introduce tabla, columna, índice ni migración SQLite en esta enmienda.
- No se modifica Memory.owner_id ni se añade owner_issuer_id.
- No se equiparan consumer_id, UserId e identity_id.
- PRIVATE_MEMORY_AUTHORIZATION sigue siendo una autoridad CAM independiente.
- La aprobación de esta enmienda no habilita autenticación externa, linking operativo, migraciones ni runtime protegido.

## 7. Cuestiones deliberadamente no resueltas

Deben especificarse antes de implementar flujos de cuenta:

1. Procedimiento de recuperación, factores admitidos, revisión, notificaciones y protección contra account takeover.
2. Política operativa exacta para impedir que unlink elimine el último método de acceso utilizable, incluidos fallos simultáneos del proveedor.
3. Autoridad y procedimiento para revisar una eventual fusión de identidades; la fusión permanece deshabilitada por defecto.
4. Validación criptográfica y parámetros concretos por issuer/proveedor.
5. Persistencia, generación física, unicidad y retención de UserId, identity_id y binding_id.
6. Matriz de revisiones, invalidación, fencing, CAS, idempotencia y recuperación ante cambios de Identity o binding.
7. Migración del binding legacy y prueba de no regresión; sin fallback silencioso cuando la nueva autoridad falle.

Estas cuestiones no reabren las decisiones A–G ya aprobadas; limitan el alcance de implementación hasta que se definan.

## 8. Aprobación solicitada

Solicito aprobación del propietario del texto propuesto en §§2–6 como enmienda normativa coordinada a B1-A-06, identity.md y operation-context.md.

Hasta esa aprobación final:
- los documentos normativos vigentes permanecen sin cambios;
- este archivo es solo un borrador;
- B1-B-03A no se considera cerrado;
- B1-B-03B (diseño físico SQLite) no debe comenzar.

**Estado final:** decisiones A–G aprobadas; texto normativo propuesto pendiente de aprobación; ninguna implementación autorizada.
