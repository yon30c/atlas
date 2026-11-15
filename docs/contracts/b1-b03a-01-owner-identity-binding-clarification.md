# B1-B-03A-01 — Aclaración propuesta de owner_id e Identity Binding

**Estado:** decisiones conceptuales y textos propuestos aprobados; consolidación normativa documental ejecutada en la rama `docs/b1-b02-logical-model-and-next-phase`; verificación cruzada final pendiente. La consolidación no autoriza implementación, migraciones ni activación de runtime protegido.  
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

1. `Memory.owner_id` permanece como `UserId` global y canónico de Atlas. No representa un subject externo ni se cambia su tipo.
2. `owner_identity_id` representa el `identity_id` canónico e interno de Identity Authority.
3. La relación entre `UserId` e Identity(USER) es 1:1 y autoritativa; Identity Authority debe mantenerla y resolverla mediante evidencia interna verificable y vigente. El mecanismo físico de persistencia/verificación no queda definido aquí.
4. La cuenta externa se identifica mediante la pareja exacta `(issuer_id, subject)`, que se resuelve mediante un binding externo verificado hacia Identity(USER). El subject no se compara directamente con `Memory.owner_id`.
5. `Memory.owner_id` debe coincidir exactamente con el `UserId` canónico resuelto. Cuando corresponda, `owner_identity_id` debe coincidir exactamente con el `identity_id` de esa misma Identity(USER). No se exige igualdad textual entre UserId e identity_id.
6. Un email, nombre, identificador declarado por el caller, coincidencia accidental de strings o `context.user_id` aislado no constituyen prueba.
7. Si cualquier relación no puede resolverse de forma única, vigente y autoritativa, la operación falla cerrada.

## 3. Texto contractual propuesto para DM-01

### Adición a §4.2 — Memory

**Texto aprobado por el propietario el 15 de noviembre de 2026.** Añadir después de los invariantes existentes:

> `Memory.owner_id` conserva el tipo `UserId` y representa exclusivamente el identificador global y canónico del propietario dentro de Atlas. No representa un subject externo, un `identity_id` ni un identificador elegido o declarado por el caller.
>
> El valor de `owner_id` debe proceder de la autoridad confiable de Atlas. Para una operación autenticada externamente, la frontera confiable debe resolver la cuenta `(issuer_id, subject)` mediante Identity Authority y obtener el `UserId` canónico asociado a la Identity(USER) verificada.
>
> La correspondencia entre `UserId` e `identity_id` es 1:1 y autoritativa. Identity Authority debe poder verificar que ambos identificadores corresponden a la misma Identity(USER), sin exigir ni inferir igualdad textual entre ellos.
>
> Cuando una operación protegida requiera comprobar la propiedad, CAM debe comparar exactamente el `UserId` canónico resuelto con `Memory.owner_id`. Cuando también intervenga `PrivateMemoryConsumerAuthorization`, debe comprobar que `owner_identity_id` corresponde al `identity_id` de la misma Identity(USER).
>
> Un subject externo, `identity_id`, `OperationContext.user_id` aislado o identificador declarado por el caller no sustituye esta resolución. La ausencia, ambigüedad, discrepancia, revocación, expiración o imposibilidad de verificar la relación produce `DENY`.

### Aclaración a §6.4 — Memoria PRIVATE del propietario

**Texto aprobado por el propietario el 15 de noviembre de 2026.** Sustituir el punto que relaciona directamente el subject autenticado con `Memory.owner_id` por:

> - actor de tipo `USER`;
> - identidad USER activa y verificada mediante evidencia vigente de Identity Authority;
> - `VerifiedIdentityContext.user_id` debe coincidir exactamente con `Memory.owner_id`;
> - `VerifiedIdentityContext.identity_id` debe identificar la Identity(USER) asociada al `UserId` resuelto;
> - si interviene `PrivateMemoryConsumerAuthorization`, su `owner_identity_id` debe coincidir exactamente con ese `identity_id`;
> - la cuenta externa autenticada debe haber sido validada mediante el binding exacto `(issuer_id, subject)` registrado y verificado por Identity Authority. El subject externo no se compara directamente con `Memory.owner_id`;
> - `context.user_id` por sí solo no demuestra autenticación, propiedad ni autoridad.

Mantener el resto de las restricciones de §6.4: scope PRIVATE explícito, recurso y metadatos confiables, Gateway y CAM obligatorios, acciones limitadas y prueba directa no delegable para approve/reject/forget.

## 4. Texto contractual propuesto para B1-A-06

### Sustitución de la última oración de §2.1 — Modelo y alcance

**Texto aprobado por el propietario el 15 de noviembre de 2026.** Sustituir únicamente la última oración de §2.1 por:

> La autorización vincula exactamente un propietario, consumidor y memoria. La memoria debe tener scope `PRIVATE` y `project_id = NULL`.
>
> `Memory.owner_id` conserva el `UserId` global y canónico de Atlas. `PrivateMemoryConsumerAuthorization.owner_identity_id` identifica el `identity_id` de la Identity(USER) correspondiente al propietario.
>
> Identity Authority debe resolver y verificar la relación 1:1 vigente entre el `UserId` y el `identity_id` de esa misma Identity(USER), mediante evidencia interna autoritativa. CAM debe comprobar que el `UserId` resuelto coincide exactamente con `Memory.owner_id` y que el `identity_id` resuelto coincide exactamente con `owner_identity_id`.
>
> Cuando la operación se base en autenticación externa, la cuenta `(issuer_id, subject)` debe resolverse separadamente mediante su binding externo verificado hacia esa Identity(USER). El subject externo no se compara directamente con `Memory.owner_id` ni con `owner_identity_id`.
>
> La imposibilidad de resolver cualquiera de estas relaciones de forma única, vigente y verificable produce `DENY`.

### Adición a §4.2 — Identidad y binding

**Texto aprobado por el propietario el 15 de noviembre de 2026.** Añadir después de las reglas actuales de binding:

> **Relación entre UserId e Identity(USER)**
>
> Atlas mantiene un `UserId` global y canónico, independiente de cualquier proveedor externo. Identity Authority es responsable de emitirlo, mantenerlo y resolver su correspondencia con la identidad interna.
>
> La relación entre `UserId` e Identity(USER) es 1:1 y autoritativa: cada `UserId` corresponde a exactamente una Identity(USER), y cada Identity(USER) corresponde a exactamente un `UserId`. Ambos identificadores son distintos y no se establece ni demuestra su correspondencia mediante igualdad textual.
>
> El binding externo `(issuer_id, subject)` identifica una cuenta autenticada dentro de un issuer confiable y se vincula a como máximo una Identity(USER). Una Identity(USER) puede tener varios bindings externos verificados mediante un procedimiento explícito.
>
> Identity Authority debe poder verificar conjuntamente:
>
> - el `UserId` canónico;
> - el `identity_id` de Identity(USER);
> - la relación 1:1 vigente entre ambos;
> - el binding externo exacto `(issuer_id, subject)`, cuando la operación dependa de autenticación externa;
> - el estado y las revisiones vigentes de la identidad y del binding.
>
> La evidencia debe permitir que CAM compruebe esas relaciones sin depender de identificadores declarados por el consumidor, coincidencias de atributos personales ni igualdad textual entre identificadores de espacios distintos.
>
> La relación UserId–Identity(USER) no constituye una autorización. Los bindings externos tampoco conceden permisos. CAM conserva la responsabilidad exclusiva de decidir la autorización de cada operación.
>
> El mecanismo físico de emisión, almacenamiento y verificación de UserId y de su relación con `identity_id` queda sujeto a una especificación posterior. Esta disposición no agrega campos a `Identity`, no modifica `Memory.owner_id` y no autoriza cambios de persistencia.

### 4.1. Registro de aprobación

El propietario aprobó el 15 de noviembre de 2026 las propuestas de B1-A-06 §§2.1 y 4.2 en los términos anteriores. La aprobación confirma que la comparación de propiedad se realiza entre el `UserId` canónico de Memory y el `identity_id` de la autorización mediante una relación 1:1 verificada por Identity Authority; no se comparan los identificadores entre sí ni se usa el subject externo como sustituto. También confirma que la relación UserId–Identity(USER) no concede autorización y que su mecanismo físico permanece pendiente.

Esta aprobación no modifica por sí misma B1-A-06 vigente ni autoriza implementación, cambios de persistencia, migraciones o activación de flujos protegidos.

---
 
## 5. Reglas de validación derivadas

Para una lectura PRIVATE del propietario:

1. Obtener `VerifiedIdentityContext` vigente desde la frontera confiable.
2. Verificar que el contexto identifica una Identity(USER) activa y que la autenticación externa fue validada para el issuer confiable.
3. Resolver y verificar el binding exacto `(issuer_id, subject)` hacia la Identity(USER), incluyendo estado y revisión actuales.
4. Resolver mediante Identity Authority el `UserId` canónico asociado a esa Identity(USER).
5. Comprobar igualdad exacta entre el `UserId` resuelto y `Memory.owner_id`.
6. Cuando intervenga `PrivateMemoryConsumerAuthorization`, comprobar que `owner_identity_id` coincide exactamente con el `identity_id` de esa misma Identity(USER).
7. Comprobar scope PRIVATE, recurso y metadatos canónicos de Memory.
8. Evaluar la acción exacta mediante CAM.
9. Ante ausencia, ambigüedad, discrepancia, revocación, expiración, revisión obsoleta o error, denegar.

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

- DM-01 §4.2: `Memory.owner_id: UserId`, propietario canónico único e inmutabilidad; la adición aprobada aclara que UserId no es subject externo.
- DM-01 §6.4: la ruta PRIVATE compara el UserId canónico resuelto con `Memory.owner_id` y verifica separadamente el `identity_id` correspondiente; el subject externo se valida mediante binding y no se compara con owner_id.
- DM-01 §6.5 y §6.6: owner/scope provienen de metadatos confiables; resolver ausente o inconsistente produce DENY.
- B1-A-06 §2.1: `owner_identity_id` y coincidencia con el propietario canónico de Memory.
- B1-A-06 §4.2: binding `(issuer, subject) -> identity_id`, binding no concede autorización.
- B1-A-06 §5: CAM comprueba contexto, binding, revisiones, recurso y autorización exactos.

## 9. Estado y siguiente paso

La decisión conceptual y los textos propuestos para DM-01 §§4.2 y 6.4, B1-A-06 §§2.1, 4.2 y 5, `identity.md` y `operation-context.md` han sido aprobados por el propietario. La separación entre VerifiedIdentityContext de Identity(USER) y la identidad del actor AGENT/SERVICE/WATCHER/SYSTEM también está aprobada.

La consolidación documental de los cuatro contratos normativos se ha ejecutado en la rama `docs/b1-b02-logical-model-and-next-phase`. El cierre de B1-B-03A permanece condicionado a la verificación cruzada final de contenido, referencias, diff, rama y SHA de los siete documentos del paquete.

Los criterios de cierre aprobados son acumulativos: decisiones y trazabilidad completas; enmiendas incorporadas; coherencia entre contratos; separación de autoridades; compatibilidad legacy; cuestiones pendientes delimitadas; y verificación documental final. Las cuestiones técnicas aplazadas no bloquean el cierre normativo si permanecen explícitas y los flujos dependientes siguen deshabilitados.

No iniciar B1-B-03B ni modificar SQLite. No se autoriza implementación, migración, PR, merge ni despliegue por esta consolidación.
