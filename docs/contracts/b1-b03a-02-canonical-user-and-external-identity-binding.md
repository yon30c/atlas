# B1-B-03A-02 — Modelo lógico de UserId canónico y bindings externos

**Estado:** decisiones A–G APROBADAS; propuestas normativas coordinadas aprobadas; consolidación documental ejecutada; verificación cruzada final pendiente antes del cierre de B1-B-03A.  
**Fecha:** 15 de noviembre de 2026.  
**Decisiones de origen aprobadas:** UserId global/canónico en Atlas; Memory.owner_id: UserId separado de identity_id.  
**Fuentes revisadas:** Identity, OperationContext, B1-A-06 §§4.2–5, DM-01, identity_binding.py, memory/identity.py y memory_service.py.  
**Fuera de alcance:** diseño físico SQLite, migraciones, cambios de código, selección de proveedor de autenticación y despliegue.

---

## 1. Objetivo

Definir cómo Atlas mantiene un identificador global de usuario independiente de proveedores externos y cómo relaciona ese usuario con:
- la identidad canónica interna identity_id de tipo USER;
- una o varias cuentas externas autenticadas mediante (issuer, subject);
- Memory.owner_id y PrivateMemoryConsumerAuthorization.owner_identity_id.

Identidad, cuenta externa, usuario canónico y autorización son conceptos distintos. Ninguna relación por sí sola concede permisos.

## 2. Hechos de contratos y código actual

### 2.1 Contratos

- identity.md define Identity(identity_id, kind, status) y deja fuera de alcance el mecanismo de autenticación y vinculación de cuentas externas.
- operation-context.md distingue actor.identity_id de user_id. El user_id contextual no demuestra autenticación, autorización ni delegación.
- B1-A-06 §4.2 define el binding (issuer, subject) -> identity_id, permite varios bindings verificados por identidad, exige unicidad de cada pareja activa, prohíbe fusiones por coincidencia de atributos y establece que revocar un binding es irreversible.
- B1-A-06 §5 define VerifiedIdentityContext con identity_id, revisiones de identidad/binding, issuer, tiempos y referencia de verificación. No incluye explícitamente UserId en la lista actual de campos.
- DM-01 conserva Memory.owner_id: UserId; B1-A-06 usa owner_identity_id para identificar la identidad interna del propietario.

### 2.2 Implementación inspeccionada

- Identity actual contiene identity_id, kind, status y revision; no contiene UserId.
- OperationContext.user_id es una cadena estructuralmente validada, pero el contrato prohíbe tratarla como evidencia de autenticación.
- AuthenticatedUserSubject es descrito en código como contrato legado y contiene actor_identity_id, subject_user_id, is_active y revision. No contiene issuer, binding_id ni evidencia temporal del proveedor.
- AtlasIdentityBindingAdapter adapta ese contrato legado al puerto neutral de Memory Engine.
- MemoryAuthorizationService compara el subject_id devuelto por el puerto con Memory.owner_id. El flujo actual no demuestra por sí mismo la verificación de (issuer, subject) de un proveedor externo.

**Conclusión:** existe una resolución confiable histórica actor→subject/user, pero no está acreditado que sea el registro completo de cuentas externas requerido por el modelo aprobado. No se debe reinterpretar subject_user_id como el subject de un proveedor sin evidencia contractual y técnica.

## 3. Modelo lógico recomendado

Se propone que Identity Authority sea la autoridad canónica responsable de emitir y mantener UserId, identity_id y los bindings externos. Esto no fusiona autenticación externa y autorización: el proveedor autentica la cuenta; Identity Authority resuelve la vinculación; CAM decide permisos.

### 3.1 Entidades conceptuales

| Entidad | Identificador | Responsabilidad |
|---|---|---|
| Atlas User | user_id: UserId | Usuario canónico global y estable, propietario de datos y memorias. |
| Identity | identity_id | Actor interno de Atlas; para esta relación, identidad de tipo USER. |
| External Identity Binding | binding_id | Vincula una cuenta externa verificada (issuer_id, subject) con una identidad USER. |
| Issuer Registry Entry | issuer_id | Configuración confiable de un proveedor/issuer aceptado por Atlas. |
| Verified Identity Context | context_id | Evidencia temporal de autenticación y resolución, consumida por CAM. |

### 3.2 Cardinalidades propuestas

- Un UserId corresponde a exactamente una identidad canónica Identity(USER).
- Una identidad Identity(USER) corresponde a exactamente un UserId.
- Una identidad USER puede tener cero o varias cuentas externas vinculadas.
- Cada pareja exacta (issuer_id, subject) puede estar vinculada a como máximo una identidad USER, incluso si el binding fue revocado; la pareja no se reasigna silenciosamente.
- Un binding pertenece a una sola identidad USER.
- Una cuenta externa no es un UserId ni un identity_id.

**Decisión aprobada:** la relación es 1:1 entre UserId e Identity(USER), para evitar identidades USER paralelas con propiedad divergente.

### 3.3 Emisión de UserId

- Identity Authority (o un componente de provisioning interno bajo su autoridad) emite UserId al crear un usuario canónico.
- El valor es opaco, globalmente único, estable e inmutable; no deriva de email, nombre, teléfono, issuer, subject ni identity_id.
- El proveedor externo nunca elige ni suministra el UserId canónico.
- El caller no puede declarar un UserId y convertirlo en identidad autenticada.
- La generación debe impedir reutilización, colisiones y reasignación tras eliminación o revocación.
- Formato y mecanismo de generación quedan pendientes; no se prescribe UUID, ULID u otro formato en esta fase.

### 3.4 Registro de issuer

- Atlas mantiene una lista/configuración confiable de issuers aceptados.
- El issuer se resuelve contra esa configuración; no se confía en un issuer arbitrario declarado por el caller.
- Cada issuer define cómo validar firma, audiencia, expiración, nonce, algoritmos permitidos y semántica del subject.
- El subject se trata como identificador opaco y sensible al issuer. No se normaliza salvo regla explícita y documentada del issuer.
- Email, nombre visible y teléfono no son claves de binding.

La selección de proveedores concretos y el mecanismo técnico de verificación quedan fuera de esta propuesta.

## 4. Flujos lógicos

### 4.1 Primer registro

1. El proveedor externo autentica una cuenta y Atlas valida la evidencia contra un issuer permitido.
2. Identity Authority busca la pareja exacta (issuer_id, subject).
3. Si existe binding activo, resuelve la identidad USER y su UserId existente.
4. Si no existe binding, el flujo de registro autorizado puede crear un UserId y una identidad USER nuevos, y vincular la cuenta externa después de verificar unicidad.
5. Creación y binding se registran con procedencia, revisión e idempotencia; un fallo parcial no debe dejar una cuenta autenticable sin propietario canónico.
6. Identity Authority emite VerifiedIdentityContext solo después de completar la resolución autoritativa.

No se crea automáticamente una cuenta nueva en un flujo de login ambiguo ni se enlaza por coincidencia de correo.

### 4.2 Vincular una segunda cuenta externa

1. La sesión existente pertenece a una identidad USER activa y tiene contexto verificado vigente.
2. El propietario inicia explícitamente la vinculación.
3. La nueva cuenta externa se autentica de nuevo y se valida contra un issuer permitido.
4. Identity Authority comprueba que (issuer_id, subject) no está asignado a otra identidad ni reservado por un binding revocado.
5. Se solicita confirmación explícita del propietario.
6. La operación registra actor, binding nuevo, evidencia, revisiones e idempotency key.
7. La nueva cuenta queda asociada al mismo UserId e identity_id; no se crea un segundo usuario.
8. El binding nuevo no hereda Grants ni permisos; todas las operaciones continúan pasando por CAM.

### 4.3 Inicio de sesión posterior

1. Validar criptográficamente la autenticación del issuer.
2. Resolver la pareja exacta (issuer_id, subject) en Identity Authority.
3. Exigir binding ACTIVE, identidad USER ACTIVE y revisiones vigentes.
4. Resolver el UserId canónico asociado.
5. Emitir VerifiedIdentityContext temporal con referencias y revisiones exactas.
6. La frontera confiable crea OperationContext; no copia user_id no verificado del caller.
7. CAM evalúa la operación y el recurso exactos.

### 4.4 Desvincular una cuenta

- Requiere sesión verificada de la identidad propietaria y prueba reciente de control, conforme a una política de reautenticación pendiente.
- La revocación del binding es irreversible.
- El binding revocado se conserva como tombstone/no reutilizable para evitar reasignación de la misma pareja.
- No se elimina ni cambia UserId, identity_id, memorias o propiedad histórica.
- No se permite dejar al usuario sin método de acceso o recuperación utilizable; la regla exacta requiere decisión específica.
- La revocación invalida contextos y admisiones dependientes mediante CAM/Consistency según D4O-F/G/H.

### 4.5 Cambio de proveedor

El cambio de proveedor es la vinculación de una cuenta nueva a la identidad existente, no un cambio de UserId ni identity_id. La cuenta anterior solo se revoca después de comprobar que la nueva cuenta está vinculada y que existe una vía de recuperación segura.

### 4.6 Colisión y posible fusión

- Si la pareja (issuer_id, subject) ya pertenece a otra identidad, la vinculación se rechaza.
- Dos identidades no se fusionan por coincidencia de email, nombre, teléfono u otro atributo.
- Cualquier fusión requiere procedimiento administrativo separado, prueba fuerte de control de ambas identidades, revisión de propiedad/Grants/recursos y contrato de migración explícito.
- Hasta resolver el conflicto, la operación se deniega o queda en cuarentena; no se elige una identidad por heurística.
- Nunca se reasignan memorias ni UserId como efecto secundario de vincular una cuenta.

### 4.7 Recuperación de cuenta

La recuperación no puede basarse únicamente en email, nombre, teléfono, conocimiento de un UserId o posesión de una sesión antigua. Requiere un proceso de prueba de control independiente y auditable. Su autoridad, factores aceptados, revisión humana, demora, notificación y protección contra toma de cuenta quedan pendientes de contrato separado. La recuperación no fusiona identidades ni revierte bindings revocados; crea un binding nuevo después de verificar la identidad canónica.

## 5. VerifiedIdentityContext y OperationContext

Se recomienda ampliar conceptualmente VerifiedIdentityContext para incluir:
- context_id;
- identity_id e identity_revision;
- user_id canónico;
- binding_id y binding_revision;
- issuer_id (identificador del registro confiable, no string arbitrario del caller);
- authenticated_at, verified_at y expires_at;
- verification_ref opaca.

OperationContext.user_id debe ser poblado por la frontera confiable desde este contexto, nunca aceptado como prueba del caller. Para operaciones delegadas, user_id sigue representando al usuario contextual y actor.identity_id al actor efectivo; la delegación se valida separadamente.

Incluir user_id en VerifiedIdentityContext es una propuesta de ampliación de B1-A-06 §5 y requiere aprobación normativa. No implica agregar una columna a Identity ni a Memory en esta fase.

## 6. Compatibilidad con el código legado

- Mantener AuthenticatedUserSubject e IdentitySubjectBindingPort como contratos de compatibilidad hasta que exista migración explícita.
- No renombrar ni reinterpretar subject_user_id en código existente sin revisar todos sus consumidores y datos.
- El binding legado actor→subject no reemplaza el binding externo (issuer, subject); no aporta issuer, binding_id ni prueba de autenticación externa.
- El adaptador legacy puede seguir atendiendo flujos ya autorizados, pero no debe emitir evidencia del nuevo modelo por inferencia.
- Una transición posterior debe definir lectura dual, precedencia, verificación cruzada, rollback seguro y pruebas negativas; no permitir fallback de evidencia nueva a legacy cuando la verificación nueva falle.
- No modificar ni migrar registros existentes en B1-B-03A.

## 7. Invariantes de seguridad

1. UserId es global, opaco, único, estable y no reutilizable.
2. identity_id es interno, canónico, único, estable y no reutilizable.
3. La relación UserId↔Identity USER es única y autoritativa.
4. La pareja (issuer_id, subject) se resuelve solo contra issuer confiable y no puede asignarse a dos identidades.
5. Un binding no concede permisos ni Grants.
6. El caller no puede elegir UserId, identity_id, issuer confiable ni binding.
7. Email, nombre, teléfono y coincidencia de strings no demuestran identidad ni autorizan merge.
8. Binding revocado no se reactiva ni reasigna.
9. Vincular o desvincular una cuenta no transfiere propiedad, no copia Grants y no altera Memory.owner_id.
10. Indisponibilidad, expiración, colisión, ambigüedad o revisión obsoleta producen DENY.
11. Los contextos verificados son temporales, ligados a revisiones y sujetos a invalidación/fencing.
12. CAM conserva autoridad exclusiva sobre autorización; Identity Authority solo resuelve identidad.

## 8. Decisiones A–G aprobadas

El propietario aprobó explícitamente el modelo lógico de §§3–7 y las siguientes decisiones:

- **A. Autoridad emisora:** Identity Authority es la autoridad canónica que emite UserId y administra su relación con una identidad USER.
- **B. Cardinalidad:** un UserId ↔ una Identity(USER); una identidad puede tener múltiples bindings externos.
- **C. Binding externo:** (issuer_id, subject) único y no reasignable; un binding revocado permanece reservado.
- **D. Account linking:** requiere sesión verificada existente, prueba reciente de la nueva cuenta y confirmación explícita; no hay linking por email ni merge automático.
- **E. Unlink:** irreversible y condicionado a mantener un método de acceso/recuperación utilizable.
- **F. VerifiedIdentityContext:** incluir el UserId canónico y el binding_id/revisión exactos.
- **G. Legacy:** preservar los puertos y modelos históricos hasta migración explícita; nunca tratarlos como evidencia externa completa.

**Aprobación registrada:** A–G quedan aprobadas como decisiones de diseño lógico. La aprobación no define todavía el procedimiento de recuperación de cuenta, la autoridad de revisión de merges, los detalles criptográficos por issuer ni la política exacta para evitar la pérdida del último método de acceso; esos asuntos requieren contratos específicos antes de implementar.

## 9. Estado y siguientes pasos

Las decisiones A–G permanecen aprobadas. La propuesta normativa coordinada B1-B-03A-03 fue aprobada por el propietario, y las enmiendas correspondientes se incorporaron documentalmente en DM-01, B1-A-06, `identity.md` y `operation-context.md` dentro de la rama `docs/b1-b02-logical-model-and-next-phase`.

La verificación cruzada final se completó: los cuatro contratos normativos son coherentes en las secciones modificadas; Identity Authority, CAM, Consistency y Memory Gateway conservan sus responsabilidades separadas; se preserva la compatibilidad legacy; y los siete documentos del paquete, referencias, diff, rama y SHA fueron revisados. La comparación con `docs/b1-a06-normative-consolidation` registró 36 commits ahead y 0 behind en el momento de la verificación.

B1-B-03A queda **CERRADO NORMATIVAMENTE** en su alcance documental. Las nueve cuestiones posteriores son: recuperación de cuenta; política operativa linking/unlink; ciclo de vida y confianza de issuers; fusión de identidades; validación criptográfica por issuer; garantías físicas y persistencia de identificadores; revisiones, invalidación y consistencia; migración legacy; y evidencia/auditoría. Permanecen abiertas y deben especificarse antes de habilitar los flujos correspondientes.

**Estado:** cerrado normativamente; no implementado. No hay migraciones, cambios de SQLite ni cambios de runtime autorizados. B1-B-03B no debe comenzar sin autorización explícita.
