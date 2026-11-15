# B1-B-03D — VerifiedIdentityContext, autenticación y evidencia

**Estado:** contrato técnico de evidencia propuesto; no se habilita autenticación externa.  
**Baseline normativo:** B1-A-06 §§4.2 y 5; B1-B-03A cerrado normativamente.  
**Dependencias:** B1-B-03B y B1-B-03C.

## 1. Separación de responsabilidades

- Authentication Authority verifica una prueba criptográfica emitida por un issuer confiable.
- Identity Authority resuelve el binding exacto hacia Identity(USER) y UserId canónico, y emite VerifiedIdentityContext.
- CAM evalúa actor, acción, recurso, scope, revisiones y delegación.
- Consistency coordina invalidación, fencing, admisiones y recuperación.
- Memory Gateway sigue siendo la única frontera de acceso a Memory.

Un token externo válido no concede autorización Atlas. Un binding no concede autorización. VerifiedIdentityContext no es Grant ni sesión de vida indefinida.

## 2. VerifiedIdentityContext

Campos obligatorios:
- context_id;
- identity_id;
- identity_type = USER;
- identity_revision;
- user_id (UserId canónico);
- binding_id;
- binding_revision;
- issuer_id resuelto contra registro confiable;
- authenticated_at;
- verified_at;
- expires_at;
- verification_ref opaca.

Invariantes:
1. Solo se emite para Identity(USER).
2. UserId e identity_id se resuelven desde la misma relación canónica 1:1.
3. binding_id pertenece a esa Identity y issuer_id.
4. El subject validado coincide exactamente con el subject asociado al binding.
5. Identity, binding e issuer están vigentes y sus revisiones coinciden con las fuentes actuales.
6. El contexto tiene expiración explícita y no se extiende automáticamente.
7. No contiene token, secreto, clave privada ni assertion original.
8. Su mera presencia no prueba que actor sea el usuario autenticado ni demuestra delegación.
9. Contexto expirado, revocado, con revisión obsoleta o fuente indisponible produce DENY.

El objeto es efímero. La persistencia conserva referencias de evidencia y datos mínimos de replay/auditoría, no una credencial reutilizable.

## 3. Validación por issuer

Cada adaptador de issuer debe implementar una política explícita que cubra, como mínimo:
- issuer exacto y configuración confiable;
- firma y algoritmo permitidos;
- key id y vigencia de clave;
- audience/client id esperado;
- expiry y not-before;
- nonce y protección anti-replay;
- subject opaco y exacto;
- protocolo, endpoint y transporte permitidos;
- timestamps y tolerancia de reloj;
- manejo de rotación y compromiso de claves.

No se permite:
- aceptar issuer o audience del caller sin resolverlo contra configuración;
- algoritmos débiles o elección de algoritmo controlada por el token;
- omitir nonce cuando el protocolo lo requiere;
- aceptar token expirado por tolerancia indefinida;
- resolver usuario por email/nombre/teléfono;
- fallback a otro issuer si el issuer esperado falla;
- emitir contexto con validación parcial.

No se fija un protocolo concreto (OIDC/OAuth u otro) ni proveedor hasta que se seleccione y revise explícitamente. Los adaptadores no deben introducir endpoints, scopes o permisos implícitos.

## 4. Nonce, replay e idempotencia

El nonce se genera en una frontera confiable, es impredecible, de vida corta y queda vinculado a issuer, audience, solicitud y operación de autenticación.

La aceptación consume el nonce una sola vez. Un segundo uso se rechaza, incluso si la assertion tiene firma válida. El almacenamiento de replay conserva digest no reversible, issuer, audience, expiración y fecha de consumo; no conserva token ni assertion.

La unicidad y consumo deben ser atómicos localmente. La idempotencia de una operación de linking no convierte una prueba de autenticación en reutilizable: la operación puede recuperar su resultado original, pero no volver a aceptar una assertion consumida para una operación distinta.

Los límites temporales y la política de reautenticación reciente se configuran por issuer/operación y deben aprobarse antes de producción. No se inventa un TTL universal.

## 5. Actor, usuario contextual y delegación

VerifiedIdentityContext identifica al usuario autenticado, no necesariamente al actor ejecutor.

Si actor.kind = USER:
- actor.identity_id debe coincidir exactamente con context.identity_id;
- actor debe estar activo y su revisión debe coincidir;
- context.user_id debe corresponder a esa misma Identity(USER).

Si actor es AGENT, SERVICE, WATCHER o SYSTEM:
- VerifiedIdentityContext no lo autentica;
- CAM debe verificar actor por una fuente independiente y confiable;
- debe existir delegación explícita y vigente cuando la operación se realice en nombre del usuario;
- actor.identity_id y context.identity_id no se equiparan;
- la presencia de context.user_id no amplía las capacidades del actor.

La autenticación de actores no USER permanece fuera de esta fase y requiere contrato independiente.

## 6. Auditoría y evidencia

La evidencia se registra con minimización:
- request_id y correlation_id;
- actor identity_id, UserId contextual y binding_id cuando corresponda;
- issuer_id y revisiones verificadas;
- resultado y causa categorizada;
- instante de verificación;
- verification_ref opaca;
- operación de Consistency relacionada.

No registrar:
- tokens, refresh tokens, contraseñas, client secrets;
- claves privadas o assertions completas;
- subject en claro salvo decisión de protección explícita;
- contenido de Memory, snippets o embeddings;
- datos de perfil que no sean necesarios.

Consistency Journal registra transiciones coordinadas. Una auditoría administrativa/seguridad separada solo se crea si tiene propósito, permisos de lectura, integridad y retención independientes; no duplicar el journal por conveniencia.

La evidencia debe permitir atribuir y verificar una transición sin convertirse en credencial de acceso ni conservar secretos.

## 7. Reloj, expiración y LOCAL

La verificación temporal requiere reloj UTC confiable y política explícita de skew. Si no se puede evaluar expiración de forma confiable, no se emite contexto.

El perfil LOCAL no dispone de anti-rollback externo. No se afirmará resistencia a restauración de snapshots antiguos por el mero uso de SQLite, WAL o hashes locales. Restaurar un backup requiere modo de recuperación, reconciliar identidades, bindings, issuers, revocaciones, admissions y fencing antes de reabrir operaciones. Trust Anchor ANCHORED continúa postergado y no existe fallback automático.

## 8. Pruebas obligatorias

- issuer desconocido/suspendido/revocado;
- firma inválida, key id desconocido o algoritmo no permitido;
- audience/issuer/subject incorrectos;
- token expirado/no válido aún;
- nonce ausente, repetido o asociado a otra operación;
- binding revocado o de otra Identity;
- UserId/identity_id no correspondientes;
- Identity inactiva/revocada;
- revisión obsoleta o cambio concurrente;
- contexto usado por actor USER diferente;
- actor no USER sin identidad propia/delegación;
- CAM o Identity Authority indisponible;
- reloj no confiable;
- restore con estado anterior a revocación/fencing;
- ausencia de secretos en logs, journal y DB.

## 9. Bloqueos de activación

Antes de activar un issuer se requiere seleccionar protocolo y proveedor, aprobar configuración, validación criptográfica, key management, rotación, expiración, replay, recuperación, auditoría y pruebas de conformidad específicas. No se emite VerifiedIdentityContext desde el adaptador legacy ni por inferencia.

**Resultado B1-B-03D:** semántica y controles de evidencia especificados; ningún issuer ni flujo de autenticación queda habilitado por este documento.
