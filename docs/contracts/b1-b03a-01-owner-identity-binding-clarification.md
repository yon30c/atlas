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

## 6. Hallazgo documental y punto que sigue requiriendo precisión

La revisión de las fuentes adicionales confirma que esta cuestión no está definida todavía:

- `docs/contracts/identity.md` §5 deja fuera de alcance el mecanismo para vincular `identity_id` con una cuenta externa; §7 mantiene pendientes autenticación, espacio de nombres, unicidad y normalización de identificadores.
- `docs/contracts/operation-context.md` §§3.2–3.3 establecen que `user_id` es distinto de `actor.identity_id`, puede representar al usuario en cuyo contexto opera un agente y no demuestra autenticación, autorización ni delegación.
- DM-01 §4.2 define `Memory.owner_id: UserId`, y §6.4 exige coincidencia con el subject autenticado, pero no define el namespace/issuer que hace único ese UserId.
- B1-A-06 §4.2 define `(issuer, subject) -> identity_id`, pero no resuelve cómo se asocia el `UserId` persistido en Memory con el issuer correspondiente.

Por tanto, la decisión conceptual aprobada es clara, pero no basta para seleccionar una clave física ni para resolver una autorización delegada en todos los casos. Antes de diseño físico debe aprobarse una de estas semánticas sin alterar el identificador existente por inferencia:

1. **UserId es global y canónico:** una autoridad confiable garantiza que el valor almacenado en `Memory.owner_id` identifica de forma única al subject en un namespace global, y expone su relación con el binding/issuer activo.
2. **UserId es issuer-scoped:** el valor solo es único junto con un issuer; una fuente confiable externa al caller debe resolver el issuer canónico asociado a cada Memory.owner_id. No se puede elegir el issuer usando solo el contexto de un actor delegado.

No se recomienda agregar silenciosamente `owner_issuer_id` a Memory ni reinterpretar `OperationContext.user_id` como prueba. Si la fuente confiable no puede resolver de forma única el propietario, la operación falla cerrada. Esta decisión de namespace es un bloqueo contractual explícito, no una autorización para crear una tabla o migración.

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

Siguiente paso: el propietario debe elegir/confirmar la semántica canónica de UserId (global o issuer-scoped) y la autoridad confiable que puede resolverla. Después se redactará la enmienda normativa final que actualice DM-01 y B1-A-06 de forma consistente y se solicitará aprobación explícita del texto antes de sustituir los documentos aprobados.

No iniciar B1-B-03B ni modificar SQLite hasta cerrar este punto y los restantes bloqueos de B1-B-03A.
