# B1-B-03A-03 — Borrador de enmienda normativa: UserId e Identity Binding

**Estado:** BORRADOR NORMATIVO — decisiones A–G aprobadas; propuestas para B1-A-06 §§2.1, 4.2 y 5 aprobadas; §§4–7 de este borrador aprobadas por el propietario el 15 de noviembre de 2026. Los contratos normativos vigentes aún no han sido modificados y la implementación no está autorizada.  
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

La propiedad de una memoria y la identidad interna de su propietario se representan mediante identificadores distintos. `Memory.owner_id` conserva el `UserId` canónico de Atlas. Cuando una autorización u operación requiera identificar la Identity(USER) correspondiente al propietario, Identity Authority debe resolver y verificar la relación vigente entre ambos identificadores. En el caso de `PrivateMemoryConsumerAuthorization`, `owner_identity_id` debe corresponder exactamente a la Identity(USER) asociada al UserId propietario de la memoria. No se permite inferir esta correspondencia mediante igualdad textual entre `UserId` e `identity_id`. La ausencia, ambigüedad, inconsistencia o invalidez de la relación verificada produce denegación.

Una Identity(USER) puede tener cero o varios bindings externos. Cada binding pertenece a una única Identity(USER). Una pareja exacta (issuer_id, subject) no puede vincularse a más de una identidad. La pareja permanece reservada después de la revocación de su binding y no puede reasignarse silenciosamente.

Identity Authority es la autoridad canónica responsable de emitir UserId, mantener la relación UserId↔identity_id y administrar el ciclo de vida de los bindings. Los issuers externos autentican cuentas conforme a la configuración de confianza de Atlas; no emiten ni eligen UserId o identity_id.

`issuer_id` identifica una entrada del registro confiable de issuers de Atlas; no es una cadena arbitraria suministrada por el proveedor o por el caller. El issuer debe resolverse contra ese registro/configuración confiable. El subject se trata como identificador opaco dentro del espacio de nombres del issuer. Email, nombre, teléfono y otros atributos de perfil no son claves de binding ni prueba suficiente de control o identidad.

Una pareja issuer/subject solo puede vincularse después de verificar la evidencia de autenticación del issuer y la unicidad de la pareja. La vinculación de una cuenta adicional exige una sesión existente verificada de la identidad propietaria, prueba reciente de control de la cuenta nueva y confirmación explícita del propietario. No se permite linking automático por coincidencia de atributos.

La revocación de un binding es irreversible. Un binding revocado se conserva como registro no reutilizable. Desvincular una cuenta no cambia UserId, identity_id, propietario de memorias, Grants ni recursos. La operación de revocación no puede completarse si no se ha verificado que permanece disponible al menos un método de acceso o recuperación utilizable conforme a una política de recuperación aprobada. El procedimiento que demuestra esa condición y el detalle del proceso de recuperación se definirán en un contrato separado.

No se fusionan identidades por coincidencia de atributos. Una fusión, si alguna vez se autoriza, requiere procedimiento separado, prueba de control de ambas identidades, revisión de propiedad, Grants y recursos, y un plan explícito de migración. No se reasignan memorias ni UserId por efecto de vincular o desvincular una cuenta.

Un binding no concede autorización, Grants, permisos PRIVATE, delegación ni propiedad. Toda operación protegida continúa sujeta a CAM y Consistency. Los cambios de binding, revocación o estado invalidan los contextos y admisiones dependientes mediante las revisiones, invalidación y fencing aplicables.

### 2.1. Registro de aprobación de §4.2

El propietario aprobó el 15 de noviembre de 2026 el texto propuesto para B1-A-06 §4.2, incorporando las precisiones sobre la relación entre `Memory.owner_id` y `PrivateMemoryConsumerAuthorization.owner_identity_id`, la semántica de `issuer_id` y la condición verificable de conservar un método de acceso o recuperación utilizable.

Esta aprobación se limita a B1-A-06 §4.2. No constituye por sí sola aprobación de las propuestas para identity.md y operation-context.md incluidas en las secciones 4 y 5 de este borrador, ni autoriza modificar los contratos normativos vigentes.

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

El contexto queda ligado a la revisión de Identity y del binding. CAM debe comprobar vigencia, estado, revisiones actuales y correspondencia del usuario contextual antes de admitir la operación. Una revisión obsoleta, binding revocado, issuer no confiable, expiración o evidencia incompleta producen denegación.

`VerifiedIdentityContext.identity_id` identifica exclusivamente la Identity(USER) cuya autenticación externa ha sido verificada. `VerifiedIdentityContext.user_id` identifica el UserId canónico asociado a esa identidad. Estos campos no identifican necesariamente al actor ejecutor de todas las operaciones realizadas dentro del contexto.

CAM debe comprobar separadamente la identidad del actor efectivo y, cuando corresponda, la delegación explícita que relaciona al actor con el usuario contextual. Si el actor es el propio usuario, debe verificarse la correspondencia entre el actor y la identidad autenticada. Si el actor es un agente o servicio, debe verificarse su propia identidad y la delegación aplicable. La delegación no puede deducirse de la mera presencia de `user_id` ni de VerifiedIdentityContext.

La presencia de VerifiedIdentityContext o de `user_id` no concede autoridad de ejecución ni demuestra por sí sola una delegación válida. Una discrepancia de identidad, ausencia de delegación exigible o evidencia incompleta produce denegación.

El resto de §5 —separación de Identity y CAM, ausencia de permisos implícitos y coordinación con Consistency— permanece vigente sin cambios.

### 3.1. Registro de aprobación de §5

El propietario aprobó el 15 de noviembre de 2026 la propuesta para B1-A-06 §5, incorporando la distinción entre identidad autenticada, UserId contextual y actor ejecutor, así como la verificación independiente de la identidad del actor y de la delegación cuando corresponda.

Esta aprobación se limita a B1-A-06 §5. No constituye por sí sola aprobación de las propuestas para identity.md y operation-context.md incluidas en las secciones 4 y 5 de este borrador, ni autoriza modificar los contratos normativos vigentes.

## 4. Propuesta para identity.md

Añadir después de la sección 5, como nueva sección 5.1:

### 5.1. Relación con el usuario canónico Atlas

Una Identity de tipo USER representa el actor interno de un usuario Atlas, pero identity_id no es el UserId del usuario. Atlas mantiene un UserId global y canónico separado, emitido por Identity Authority.

La relación entre UserId e Identity(USER) es 1:1 y autoritativa. Identity Authority mantiene y resuelve esta correspondencia mediante evidencia interna verificable y vigente. La relación no se establece ni se demuestra mediante igualdad textual entre identificadores. La resolución debe confirmar que ambos identificadores pertenecen a la misma identidad canónica y que sus revisiones y estados son válidos.

Una Identity(USER) puede tener varios bindings externos verificados, cada uno identificado por (issuer_id, subject) y binding_id. Estos bindings permiten autenticar cuentas externas distintas para la misma identidad interna. La autenticación externa, el binding y la autorización son responsabilidades separadas.

El modelo Identity no incorpora credenciales externas ni secretos. Un binding no concede permisos. La autorización de cada operación corresponde a CAM.

Añadir a la sección 7, decisiones técnicas abiertas:

- **UserId canónico:** el significado global de UserId, su relación 1:1 con Identity(USER) y la autoridad emisora se rigen por B1-A-06 §4.2. Formato físico, generación concreta, persistencia y migración siguen siendo decisiones de implementación pendientes.
- **Bindings externos:** el ciclo de vida lógico y las invariantes de issuer/subject se rigen por B1-A-06 §4.2. Los protocolos concretos de autenticación, registro de issuers y verificación criptográfica requieren especificación técnica por proveedor.

No agregar UserId como campo a la entidad Identity en esta enmienda.

### 4.1. Registro de aprobación de la propuesta para identity.md

El propietario aprobó el 15 de noviembre de 2026 la propuesta de esta sección, con la siguiente corrección normativa: la relación entre UserId e Identity(USER) es 1:1 y autoritativa; Identity Authority mantiene y resuelve esta correspondencia mediante evidencia interna verificable y vigente. La resolución debe confirmar que ambos identificadores pertenecen a la misma identidad canónica y que sus revisiones y estados son válidos.

Esta aprobación no define el mecanismo físico de persistencia o verificación, no agrega UserId como campo a Identity y no autoriza modificar todavía el contrato vigente identity.md.

## 5. Propuesta para operation-context.md

**Añadir al final de §3.2 Usuario contextual:**

Para operaciones autenticadas de un usuario Atlas, el user_id contextual debe proceder de un VerifiedIdentityContext vigente emitido por Identity Authority, o de otro mecanismo de autoridad expresamente definido para el tipo de operación. La frontera confiable de Atlas debe construir el OperationContext y establecer el UserId canónico; no debe aceptar un user_id enviado por el caller como prueba de identidad, propiedad o autenticación.

El UserId canónico no es equivalente a actor.identity_id. Para un actor USER, la correspondencia entre ambos se resuelve mediante Identity Authority y la relación 1:1 vigente. En operaciones delegadas, user_id identifica al usuario contextual y actor.identity_id identifica al actor efectivo; la delegación requiere verificación independiente y evaluación de CAM.

**Añadir a §3.3 Separación de responsabilidades:**

La presencia de user_id en OperationContext sigue siendo dato contextual y no concede autorización. Su procedencia confiable permite identificar el usuario contextual, pero CAM debe evaluar por separado acción, recurso, scope, permisos, revisiones y vigencia. Un caller no puede elegir un UserId arbitrario para obtener acceso a memorias u otros recursos.

No se cambia la estructura actual de OperationContext ni se redefine su campo user_id en esta enmienda.

### 5.1. Registro de aprobación de la propuesta para operation-context.md

El propietario aprobó el 15 de noviembre de 2026 la propuesta de esta sección. Se confirma que la frontera confiable construye OperationContext y establece el UserId canónico desde VerifiedIdentityContext vigente u otro mecanismo de autoridad expresamente definido; el caller no puede aportar user_id como prueba. Se conserva la distinción entre UserId y actor.identity_id, así como la verificación independiente de la delegación.

Esta aprobación no cambia la estructura de OperationContext ni autoriza modificar todavía el contrato vigente operation-context.md.

## 6. Compatibilidad y límites

- Se conservan `AuthenticatedUserSubject`, `IdentitySubjectBindingPort` y `AtlasIdentityBindingAdapter` como contratos legacy hasta que exista una migración explícita, aprobada y verificable.
- `subject_user_id` no se reinterpretará como subject externo de un issuer ni se asumirá que equivale automáticamente al UserId canónico. Cualquier relación entre el dato legacy y el modelo canónico requiere una migración y verificación explícitas.
- `AtlasIdentityBindingAdapter` solo adapta el contrato legacy al contrato neutral del Memory Engine. No constituye Identity Authority, no administra bindings externos y no emite VerifiedIdentityContext.
- La implementación legacy no podrá emitir VerifiedIdentityContext nuevo por inferencia ni reutilizar evidencia incompleta como si fuera evidencia del modelo nuevo.
- No se introduce tabla, columna, índice ni migración SQLite en esta enmienda. No se alteran migraciones históricas ni se reconstruye la base de datos.
- No se modifica `Memory.owner_id`, no se añade `owner_issuer_id` y no se altera la propiedad de memorias.
- No se equiparan `consumer_id`, UserId e `identity_id`; son identificadores distintos con autoridades y semánticas propias.
- `PRIVATE_MEMORY_AUTHORIZATION` sigue siendo una autoridad CAM independiente de Grants PROJECT. Consistency puede reconocer su revisión y coordinar invalidación, fencing y recuperación, pero no se convierte en autoridad canónica de esa autorización ni en un Grant.
- La aprobación de esta sección no habilita autenticación externa, linking operativo, emisión de VerifiedIdentityContext, migraciones, persistencia nueva ni runtime protegido.
- No se permite fallback silencioso del modelo nuevo al legacy cuando falle la autoridad o la evidencia requerida. Cualquier transición de compatibilidad debe ser explícita, autorizada y verificable.

### 6.1. Registro de aprobación de §6

El propietario aprobó el 15 de noviembre de 2026 esta versión de §6. La aprobación fija los límites de compatibilidad y evita reinterpretaciones automáticas de los contratos legacy, cambios de esquema o propiedad, emisión inferida de evidencia nueva y fallback silencioso.

La aprobación se limita a esta sección y no autoriza implementación, migración, cambios de SQLite ni activación de flujos protegidos.

## 7. Cuestiones deliberadamente no resueltas

Las siguientes cuestiones requieren contratos o especificaciones adicionales antes de habilitar los flujos correspondientes. Su carácter pendiente no revoca ni debilita las invariantes lógicas aprobadas en B1-B-03A-02 y §§2–3 de este borrador.

1. **Recuperación de cuenta y protección contra account takeover.** Deben definirse la autoridad responsable, factores admitidos, nivel de prueba, revisión, notificaciones, demoras o periodos de seguridad y tratamiento de señales de compromiso. La recuperación no puede basarse únicamente en email, nombre, teléfono, UserId o una sesión antigua.

2. **Política operativa de linking y unlink.** Deben especificarse la reautenticación reciente, la prueba de control de la cuenta nueva, la confirmación explícita, las notificaciones, la concurrencia de operaciones y el tratamiento de fallos parciales o indisponibilidad de proveedores. Un unlink no puede dejar al usuario sin un método de acceso o recuperación utilizable; deben definirse las comprobaciones y garantías operativas para sostener esa condición.

3. **Ciclo de vida y confianza de issuers.** Deben definirse la autoridad y el procedimiento para incorporar, actualizar, suspender y retirar issuers del registro confiable de Atlas; gestionar rotación o compromiso de claves, cambios de configuración y pérdida de confianza; y determinar cómo esos eventos afectan bindings, contextos verificados, sesiones y admisiones dependientes.

4. **Fusión de identidades.** Deben definirse la autoridad, el procedimiento, las pruebas de control de ambas identidades, la revisión de propiedad, Grants y recursos, y la evidencia auditable para una eventual fusión. La fusión permanece deshabilitada por defecto y nunca puede producirse automáticamente por coincidencia de atributos.

5. **Validación criptográfica por issuer.** Deben especificarse los algoritmos y parámetros admitidos y las comprobaciones aplicables a cada issuer, incluyendo firma, audiencia, expiración, nonce, subject y demás validaciones propias del protocolo. La selección de proveedores y mecanismos concretos permanece pendiente.

6. **Garantías físicas y persistencia de identificadores.** Deben definirse el diseño físico, generación, almacenamiento, unicidad, restricciones, retención y tombstones de UserId, identity_id y binding_id. Estas decisiones de implementación deben preservar las propiedades lógicas ya aprobadas: opacidad, estabilidad, unicidad, no reutilización y relación 1:1 entre UserId e Identity(USER), así como la unicidad y no reasignación de cada pareja (issuer_id, subject). No se reabre la semántica lógica aprobada.

7. **Revisiones, invalidación y consistencia.** Deben definirse la matriz de revisiones de Identity, binding e issuer; los conjuntos de autoridades serializadas por operación; invalidación y fencing de contextos y admisiones dependientes; CAS o mecanismo equivalente; idempotencia; orden de coordinación; y recuperación ante cambios parciales, timeouts o resultados inciertos. Debe mantenerse la separación de autoridades y aplicarse el marco de Consistency y D4O-F/G/H, sin convertir Consistency en autoridad canónica de Identity o CAM.

8. **Migración de contratos y datos legacy.** Deben inventariarse consumidores y datos afectados, definirse la correspondencia verificable de `subject_user_id` con UserId canónico, la secuencia de transición, cualquier dual-read temporal si se justifica, precedencia, reconciliación, rollback seguro y pruebas de no regresión. No se reinterpretarán datos por inferencia ni se permitirá fallback silencioso. La migración requiere aprobación explícita y no forma parte de esta enmienda.

9. **Evidencia y auditoría.** Deben definirse formato, procedencia, integridad, protección, retención y verificación de evidencias de autenticación, linking, unlink, recuperación, revocación y cambios en el registro de issuers. La auditoría debe conservar separación respecto de Identity Authority y CAM: registrar evidencia no convierte al registro de auditoría en autoridad de identidad o autorización.

### 7.1. Registro de aprobación de §7

El propietario aprobó el 15 de noviembre de 2026 la versión ampliada de §7. La aprobación incorpora explícitamente la separación entre invariantes lógicas aprobadas y garantías físicas pendientes, el ciclo de vida y la confianza del registro de issuers, y los requisitos operativos de linking/unlink, además de las cuestiones de recuperación, fusión, validación criptográfica, persistencia, consistencia, migración legacy y auditoría.

Estas cuestiones permanecen deliberadamente abiertas y deben especificarse antes de habilitar los flujos correspondientes. La aprobación de §7 no autoriza implementar soluciones implícitas, conceder permisos, alterar propiedad, modificar SQLite o habilitar operaciones protegidas. No reabre las decisiones A–G ya aprobadas.

## 8. Aprobación solicitada y estado del paquete

El propietario ha aprobado las propuestas para B1-A-06 §§2.1, 4.2 y 5, así como las secciones 4–7 de este borrador. La aprobación de B1-A-06 §§2.1 y 4.2 confirma que `Memory.owner_id` conserva el `UserId` global y canónico, que `owner_identity_id` identifica la Identity(USER) correspondiente y que Identity Authority debe verificar la relación 1:1 vigente entre ambos mediante evidencia interna autoritativa. La cuenta externa se resuelve separadamente mediante el binding exacto `(issuer_id, subject)`; no se comparan identificadores de espacios distintos por igualdad textual. El mecanismo físico permanece pendiente.

Hasta la aprobación final del paquete coordinado:
- los documentos normativos vigentes permanecen sin cambios;
- este archivo continúa siendo un borrador;
- B1-B-03A no se considera cerrado;
- B1-B-03B (diseño físico SQLite) no debe comenzar;
- no se autoriza implementación, migración ni activación de runtime protegido.

**Estado final:** decisiones A–G aprobadas; propuestas de B1-A-06 §§2.1, 4.2 y 5 aprobadas; §§4–7 de este borrador aprobadas; contratos normativos vigentes sin cambios; ninguna implementación, migración ni activación de runtime protegido autorizada.
