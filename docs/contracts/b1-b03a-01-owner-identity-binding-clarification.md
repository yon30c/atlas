# B1-B-03A-01 — Aclaración propuesta de owner_id e Identity Binding

**Estado:** propuesta documental para revisión; no es todavía una enmienda normativa aprobada.  
**Fecha:** 15 de noviembre de 2026.  
**Decisión de diseño de origen:** aprobada por el propietario el 15 de noviembre de 2026.  
**Ámbito:** DM-01 §4.2 y §6.4; B1-A-06 §§2.1, 4.2 y 5; autorización PRIVATE y su comprobación por CAM.  
**Fuera de alcance:** cambios de esquema, migraciones, repositorios, adaptadores o runtime.

---

## 1. Propósito

Resolver la diferencia aparente entre:

- `Memory.owner_id: UserId` en DM-01;
- `PrivateMemoryConsumerAuthorization.owner_identity_id` en B1-A-06;
- `identity_id` canónico y bindings `(issuer, subject) -> identity_id` en Identity Authority.

La decisión aprobada conserva ambos identificadores con semánticas distintas. No se deben igualar, convertir ni reemplazar por inferencia.

## 2. Decisión de diseño aprobada

1. `Memory.owner_id` permanece como `UserId`, con semántica de subject/user ID autenticado definida por DM-01. No se cambia su tipo.
2. `owner_identity_id` representa el `identity_id` canónico e interno de Identity Authority.
3. La relación entre ambos se demuestra mediante un Identity Binding verificado, vigente y perteneciente a la autoridad de identidad.
4. No se exige igualdad textual entre `owner_id` y `owner_identity_id`.
5. Un email, nombre, identificador declarado por el caller, coincidencia accidental de strings o `context.user_id` aislado no constituyen prueba.
6. Si la relación no puede resolverse de forma única y autoritativa, la operación falla cerrada.

## 3. Texto contractual propuesto para DM-01

### Adición a §4.2 — Memory

Añadir después de los invariantes existentes:

> `Memory.owner_id` conserva el tipo `UserId` y representa el identificador de usuario/subject autenticado al que pertenece la memoria. No representa ni se convierte en `identity_id`. Cuando una operación protegida necesite relacionar el propietario con una identidad canónica, Identity Authority deberá demostrar esa relación mediante un binding verificado y vigente. La comparación del subject con `owner_id` debe ser exacta y no normalizada. La identidad canónica obtenida del binding se conserva como `identity_id` separado. Si el binding está ausente, revocado, vencido, ambiguo o no puede verificarse, CAM deniega.

### Aclaración a §6.4 — Memoria PRIVATE del propietario

Sustituir la frase que relaciona al sujeto autenticado con la identidad USER por:

> El sujeto autenticado en el contexto verificado debe coincidir exactamente con `Memory.owner_id`. Identity Authority debe validar que el par issuer/subject autenticado está asociado, mediante un binding activo y verificado, al `identity_id` USER del actor. La igualdad de `owner_id` y `identity_id` no se exige ni se infiere. CAM solo puede aplicar la ruta PRIVATE del propietario después de validar el binding y las revisiones vigentes de identidad y binding.

Mantener el resto de las restricciones de §6.4: scope PRIVATE explícito, recurso y metadatos confiables, Gateway y CAM obligatorios, acciones limitadas y prueba directa no delegable para approve/reject/forget.

## 4. Texto contractual propuesto para B1-A-06

### Aclaración a §2.1 — Modelo y alcance

Añadir después de la regla que exige propietario canónico coincidente con `owner_identity_id`:

> Para esta comparación, el propietario de Memory y el propietario de la autorización se expresan en espacios de identidad distintos. `Memory.owner_id` conserva el `UserId`/subject definido por DM-01; `owner_identity_id` es el `identity_id` canónico. La coincidencia se acredita mediante Identity Authority: el binding verificado y vigente debe demostrar que el subject del propietario de la memoria corresponde exactamente al `identity_id` indicado por la autorización. No se comparan ambos campos como strings ni se convierte uno en el otro. Si Identity Authority no puede resolver la correspondencia de manera única, CAM deniega.

### Aclaración a §4.2 — Identidad y binding

Añadir:

> Para vincular el propietario de una Memory con `owner_identity_id`, CAM consume evidencia de Identity Authority que identifica el binding exacto, su issuer, subject, `identity_id`, estado y revisión. El binding debe estar activo, verificado y vigente en el momento de la autorización. La prueba no puede ser sustituida por datos enviados por el consumidor ni por coincidencia de atributos personales.

## 5. Reglas de validación derivadas

Para una lectura PRIVATE del propietario:

1. Obtener `VerifiedIdentityContext` desde la frontera de autenticación confiable.
2. Verificar vigencia del contexto y estado USER.
3. Comprobar igualdad exacta entre el subject autenticado y `Memory.owner_id`.
4. Verificar en Identity Authority el binding exacto (issuer, subject) hacia el `identity_id` del actor.
5. Comprobar estado y revisión actuales de Identity y Binding.
6. Comprobar scope PRIVATE y metadatos canónicos de Memory.
7. Evaluar la acción exacta mediante CAM.
8. Ante ausencia, ambigüedad, discrepancia, revocación, expiración o error, denegar.

Para una autorización PRIVATE delegada:

1. Resolver metadatos canónicos de Memory, incluido `owner_id`.
2. Resolver desde Identity Authority la relación del propietario de Memory con el `owner_identity_id` exacto de la autorización.
3. Verificar binding activo, verificado, vigente y revisión actual.
4. Comprobar consumer_id y autorización exactos por separado; el binding no concede el permiso.
5. Evaluar autorización, expiración, revocación, snapshot y fencing por CAM/Consistency.
6. Denegar si la relación owner/identity no es única o verificable.

## 6. Semántica de UserId aprobada y consecuencias

El propietario aprobó expresamente la primera alternativa el 15 de noviembre de 2026:

**`UserId` es global y canónico.** El valor almacenado en `Memory.owner_id` identifica de forma única al usuario dentro del namespace canónico de Atlas, independientemente del issuer/proveedor externo utilizado para autenticarse.

La relación queda definida conceptualmente así:

- `UserId`: identificador canónico y estable del usuario en Atlas; es el valor que conserva `Memory.owner_id` y el `user_id` contextual cuando corresponda.
- `(issuer, subject)`: identificador externo de una cuenta/principal autenticado en un proveedor concreto.
- `identity_id`: identidad canónica interna del actor en Identity Authority.
- Identity Authority mantiene/verifica bindings confiables que permiten resolver la cuenta externa `(issuer, subject)` hacia la identidad interna correspondiente y relacionar la identidad USER con el `UserId` canónico.
- La autoridad que emite y administra el `UserId` debe ser interna/confiable de Atlas; el caller no puede elegirlo ni declararlo como prueba. La autoridad exacta, el modelo de persistencia y el ciclo de vida de estos bindings aún deben especificarse.

La resolución de un propietario de Memory debe ser inequívoca: el subject autenticado se valida exactamente contra el binding confiable del issuer; ese binding conduce a la identidad USER y al `UserId` canónico; el `UserId` resuelto debe coincidir exactamente con `Memory.owner_id`; y el `identity_id` correspondiente debe coincidir con `owner_identity_id` cuando se evalúe una autorización PRIVATE. Una coincidencia textual entre IDs no sustituye ninguna de estas comprobaciones.

La decisión no convierte `UserId` en `identity_id`, no exige que ambos strings sean iguales y no cambia el tipo ni el contenido de registros existentes.

### 6.1. Consecuencias aún por especificar

- Qué autoridad interna de Atlas emite el `UserId` canónico y cómo se autentica su emisión.
- Cómo Identity Authority relaciona de forma verificable `identity_id` USER con `UserId`.
- Cómo se asocian, agregan, cambian o revocan múltiples bindings externos `(issuer, subject)` a una misma identidad/usuario sin transferir propiedad accidentalmente.
- Cómo se tratan unlink, cambio de proveedor, colisión, recuperación de cuenta, merge/split de identidades y cuentas comprometidas.
- Qué evidencia y revisiones se incluyen en `VerifiedIdentityContext` y en snapshots CAM para impedir TOCTOU.

Hasta que estos puntos estén especificados, cualquier relación ambigua o no verificable falla cerrada. No se agrega `owner_issuer_id` a Memory ni se reinterpreta `OperationContext.user_id` como prueba.

## 7. Compatibilidad y no-regresión

- No cambiar `Memory.owner_id: UserId`.
- No reinterpretar registros existentes ni convertir IDs históricos.
- No equiparar `UserId` con `identity_id`.
- No crear bindings automáticamente por coincidencia de correo, nombre o strings.
- No conceder autorización por la existencia de un binding.
- No cambiar la separación entre Identity Authority y CAM.
- No cambiar el catálogo de permisos PRIVATE ni sus reglas de no delegabilidad.
- No introducir tablas, columnas, índices, migraciones o cambios de runtime en esta aclaración.
- Mantener fail-closed ante identidad o procedencia no verificables.

## 8. Trazabilidad de fuentes

- DM-01 §4.2: `Memory.owner_id: UserId`, propietario canónico único e inmutabilidad.
- DM-01 §6.4: el sujeto autenticado debe coincidir con `Memory.owner_id`; el actor USER debe estar vinculado a ese sujeto mediante evidencia confiable.
- DM-01 §6.5 y §6.6: owner/scope provienen de metadatos confiables; resolver ausente o inconsistente produce DENY.
- B1-A-06 §2.1: `owner_identity_id` y coincidencia con el propietario canónico de Memory.
- B1-A-06 §4.2: binding `(issuer, subject) -> identity_id`, binding no concede autorización.
- B1-A-06 §5: CAM comprueba contexto, binding, revisiones, recurso y autorización exactos.

## 9. Estado y siguiente paso

La decisión conceptual está aprobada. Esta propuesta concreta el texto y expone el único punto de precisión pendiente: namespace/unicidad de `UserId` respecto de issuer/subject.

Siguiente paso: especificar la autoridad interna que emite `UserId` y el binding verificable entre `UserId`, `identity_id` y cuentas externas. Después, redactar la enmienda normativa final para DM-01 y B1-A-06 y solicitar aprobación explícita antes de sustituir los contratos aprobados.

No iniciar B1-B-03B ni modificar SQLite hasta cerrar este punto y los restantes bloqueos de B1-B-03A.
