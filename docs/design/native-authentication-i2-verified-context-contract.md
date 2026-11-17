# I-2 — Contrato de autenticación nativa y VerifiedIdentityContext

**Estado:** implementación inicial en revisión; no habilita login operativo. El contexto incorpora attestation HMAC para impedir la fabricación de claims por callers.
**Dependencia:** I-1 en `feature/verified-identity-i1-canonical-lookup`.
**Rama:** `feature/verified-identity-i2-authentication-context`.
**Alcance:** servicio de autenticación de aplicación, admisión one-shot del proof y emisión/validación efímera de `VerifiedIdentityContext`. Sin endpoints, CLI, sesiones persistentes, bootstrap ni CAM.

## 1. Decisiones de arquitectura

### 1.1 Separación estricta de responsabilidades

- `NativeAuthenticationAuthorityPort` conserva autenticadores y proofs. No verifica contraseñas.
- El servicio de autenticación de aplicación es el único flujo previsto para emitir proofs: resuelve el autenticador por realm/login handle, verifica Argon2id y solo entonces persiste proof.
- `NativeIdentityAuthorityPort` resuelve issuer y binding. No autentica.
- `IdentityAuthorityPort.get_user_by_identity_id` (I-1) resuelve el par canónico UserId/Identity(USER).
- El servicio de aplicación de Identity Authority consume proof, verifica toda la cadena y emite VerifiedIdentityContext dentro de una sola UoW local.
- CAM continúa siendo la autoridad exclusiva de permisos. Un contexto autenticado no concede Grants.

No se debe exponer el adaptador SQLite ni su método de creación de proof a callers de request, plugins, herramientas o modelos. La composición confiable debe entregar al entrypoint solo el servicio de aplicación.

### 1.2 Configuración confiable

El servicio de Authentication Authority se construye con configuración inyectada por el composition root:

- realm nativo exacto;
- audience interna exacta del consumidor;
- TTL máximo de proof;
- TTL máximo de VerifiedIdentityContext;
- política Argon2id aprobada;
- reloj UTC;
- guard de intentos de autenticación.

Realm, audience y TTL nunca se toman del request. El request solo aporta login handle, contraseña y la referencia opaca cuando consume proof.

No se habilita ningún issuer externo ni protocolo OIDC/OAuth en este incremento. El perfil es exclusivamente `NATIVE_AUTHORITY_PROOF`.

## 2. Verificación de contraseña y emisión de proof

### 2.1 Puerto de hash

Definir un puerto de password hashing/verificación con operaciones equivalentes a:

- `hash(password) -> PHC Argon2id`;
- `verify(password, phc) -> bool`;
- `needs_rehash(phc) -> bool`.

El adaptador de producción usa `argon2-cffi`, ya declarado como dependencia. No aceptar algoritmo, parámetros Argon2, PHC ni pepper desde el caller. Los parámetros se fijan en configuración de servidor y se validan al componer el servicio.

Las excepciones de mismatch y PHC inválido se convierten en fallo de autenticación genérico. Fallos inesperados del backend de hash son UNAVAILABLE y no generan proof.

### 2.2 Flujo obligatorio

1. Validar el formato de LoginHandle y la entrada de contraseña mediante los value objects existentes.
2. Consultar el issuer usando únicamente el realm configurado.
3. Aplicar el guard de intentos antes de ejecutar el hash.
4. Buscar autenticador por `(issuer_id, login_handle)`.
5. Para handle inexistente, realizar verificación contra un PHC dummy válido para reducir diferencias temporales de enumeración. El PHC dummy se genera al componer el servicio y no se persiste.
6. Para autenticador existente, ejecutar Argon2id incluso si su estado no es ACTIVE, y después denegar uniformemente si no está activo.
7. Registrar fallo en el guard ante usuario inexistente, estado no activo o contraseña incorrecta. La respuesta observable no revela cuál condición falló.
8. Tras verificación correcta, releer el autenticador por ID y exigir mismo issuer, subject, estado ACTIVE y credential_revision. Un cambio concurrente invalida el intento.
9. Si `needs_rehash`, generar nuevo PHC y actualizar con CAS usando la revisión leída. El proof se vincula a la revisión devuelta por la actualización. Un conflicto CAS deniega y requiere nuevo intento.
10. Tomar `authenticated_at` del Clock UTC, generar NativeProofReference aleatoria de 256 bits, guardar únicamente su digest y construir NativeAuthenticationProof con issuer/subject/authenticator/revisión/audience/expiración obtenidos de fuentes confiables.
11. Persistir el proof. Solo después de commit, devolver la referencia raw al caller una única vez.
12. Registrar éxito en el guard sin incluir contraseña, PHC ni referencia raw en logs.

Si issuer no existe, está revocado, o la autoridad no está disponible, no emitir proof. Las indisponibilidades no se transforman en autenticación exitosa ni fallback a otro realm.

### 2.3 Throttling: dependencia obligatoria

No existe hoy un puerto de rate limiting de autenticación. I-2 debe introducir una interfaz explícita para controlar intentos y registrar éxitos/fallos.

Requisitos mínimos del guard:
- clave de cuenta basada en issuer + login handle normalizado;
- ventana y umbral configurables;
- respuesta temporal genérica, sin revelar existencia de cuenta;
- reloj inyectado;
- almacenamiento atómico y compartido entre procesos/instancias;
- límites adicionales por origen de red en el futuro entrypoint, calculados exclusivamente por proxy/servidor confiable;
- fallar cerrado si el guard requerido está indisponible.

No se acepta un contador solo en memoria como protección de producción: reinicios y múltiples workers lo eludirían. La implementación SQLite del guard, sus límites de retención y su migración deben revisarse como cambio separado antes de conectar un entrypoint. Hasta entonces el servicio no se compone para uso operativo; los tests usan un fake determinista del puerto.

## 3. Proof admission y resolución canónica — Identity Authority

La admisión y emisión del VerifiedIdentityContext pertenecen a Identity Authority, conforme B1-B-03D. Native Authentication Authority solo acredita que verificó una credencial y emite un proof opaco; no resuelve bindings ni usuarios.

La operación de Identity Authority recibe solo la referencia opaca. La audience y realm esperados proceden de configuración confiable.

Dentro de una única `SQLiteLocalAuthorityUnitOfWork`:

1. Obtener instante UTC confiable del Clock y consumir proof con audience configurada.
2. Si no se consume exactamente un proof PENDING, DENY.
3. Resolver issuer por realm configurado; exigir issuer_id igual al proof y estado ACTIVE.
4. Calcular `subject_digest` desde el NativeSubject del proof; no aceptar digest del caller.
5. Resolver binding por `(issuer_id, subject_digest)`; exigir ACTIVE, coincidencia exacta de issuer y que `proof.authenticated_at >= binding.verified_at`.
6. Exigir `binding.identity_id` coherente con el issuer/subject del proof.
7. Resolver con I-1 `identity_id -> CanonicalUserIdentity`.
8. Exigir identidad USER y ACTIVE; conservar UserId e identity_id separados.
9. Emitir el contexto efímero con binding_id/revision, issuer_id, identity_revision y timestamps.
10. Identity Authority construye el VerifiedIdentityContext inmutable y efímero con los datos canónicos obtenidos. Confirmar la UoW. Cualquier error previo a commit revierte el consumo del proof.

No abrir transacciones independientes para consumir proof y resolver binding/identidad. La garantía es atomicidad SQLite local solo cuando todas las autoridades comparten la misma instancia de base de datos y la misma UoW. No implica coordinación con Consistency Journal, Recovery Gate ni fencing global.

## 4. Modelo VerifiedIdentityContext

Modelo frozen, efímero y sin secretos. Campos obligatorios conforme B1-B-03D:

- `context_id`: UUIDv4 generado por el servicio;
- `identity_id`;
- `identity_type = USER`;
- `identity_revision`;
- `user_id` canónico;
- `binding_id`;
- `binding_revision`;
- `issuer_id` resuelto desde el issuer registrado;
- `authenticated_at`;
- `verified_at`;
- `expires_at`;
- `verification_ref`: referencia opaca aleatoria de 256 bits, distinta del proof raw.
- `attestation`: HMAC-SHA256 sobre todos los claims canónicos del contexto, generado por Identity Authority con una clave secreta de composición confiable.

No contiene password, PHC, NativeSubject raw, NativeProofReference, tokens, Grant, Project, Environment, rol ni acciones.

La construcción pública del dataclass no es una frontera de seguridad en Python. Por eso el contexto incluye una attestation HMAC-SHA256 calculada sobre todos sus claims, verificada en tiempo constante por un adaptador cuya clave de al menos 256 bits procede de la composición confiable y se comparte de forma segura entre workers autorizados. La clave nunca se persiste junto al contexto ni se acepta del caller. La firma incluye separación de dominio por versión de protocolo, realm y audience configurados, por lo que un contexto no puede reutilizarse entre consumers aunque compartan clave. La rotación invalida los contextos emitidos con la clave anterior; no hay refresh automático. La attestation no reemplaza las relecturas de autoridad. No usar booleanos/sellos declarativos como prueba criptográfica.

## 5. Validación del contexto

Antes de usar el contexto para derivar una operación, el verificador vuelve a consultar dentro de una UoW:

- expiración y timestamps UTC;
- issuer configurado, ID exacto y estado ACTIVE;
- binding por `binding_id`, issuer exacto, identidad exacta, estado ACTIVE y revisión igual;
- Identity(USER) canónica por identity_id, estado ACTIVE, revisión igual y UserId igual.

La referencia opaca identifica evidencia interna, pero no reemplaza las relecturas de autoridad. Ausencia, discrepancia, revisión obsoleta, expiración o indisponibilidad producen DENY. El contexto no se renueva automáticamente; para renovar autenticación se requiere nuevo proof.

## 6. Derivación de OperationContext

I-2 define una fábrica de aplicación para ruta directa de propietario USER:

- actor = Identity canónica resuelta por el verificador;
- actor.identity_id = verified.identity_id;
- actor.revision = verified.identity_revision;
- user_id = verified.user_id;
- delegation = None;
- request_id/correlation_id/origin/purpose/classification son datos asignados/validados por la frontera de aplicación;
- project_id/environment se mantienen None salvo que una operación los resuelva desde fuentes canónicas.

La fábrica no acepta actor ni user_id seleccionados por el caller. No acepta contexto expirado ni fabricado sin verificación de autoridad. La derivación no ejecuta CAM ni concede acceso. Actores AGENT/SERVICE/SYSTEM y rutas delegadas quedan fuera de I-2.

## 7. Pruebas de aceptación

### Password/proof issuance
- contraseña correcta produce proof con audience configurada;
- contraseña incorrecta, handle desconocido y autenticador suspendido/revocado dan fallo indistinguible;
- dummy verify para handle desconocido;
- issuer desconocido/revocado e infraestructura no disponible no emiten proof;
- throttling bloquea antes del hash y registra fallos/éxitos;
- cambio concurrente de credential_revision impide proof;
- rehash incrementa revisión por CAS y proof usa la revisión nueva;
- PHC inválido y errores Argon2 no filtran datos ni emiten proof;
- raw proof solo se devuelve tras persistencia; DB contiene solo digest.

### Admission/context
- proof correcto, no expirado, no consumido y de audience configurada produce contexto;
- audience incorrecta, replay, expiración y proof revocado producen DENY;
- issuer/binding/identity inexistente, revocado, suspendido o inconsistente produce DENY;
- UserId e identity_id distintos se conservan correctamente;
- fallo tras consumir proof revierte el consumo;
- concurrencia: exactamente un consumidor gana;
- expiración y revisión obsoleta invalidan contexto;
- caller no puede elegir realm, audience, issuer, subject, binding, identity_id o user_id;
- ninguna ruta AGENT ni CAM se habilita.

### Secret hygiene
- no aparecen contraseña, PHC, subject raw ni proof raw en logs;
- no se persisten secretos ni el contexto efímero.

## 8. Activación y límites

I-2 no habilita:
- login operativo, endpoint HTTP, CLI ni consola autenticada;
- sesiones persistentes o refresh tokens;
- bootstrap de propietario o provisión inicial de Projects/Environments/Grants;
- acceso a CAM, Memory Gateway, Workspace, Skills o Broker;
- actor AGENT, SERVICE, SYSTEM ni delegación;
- rate limiting productivo hasta que exista adaptador compartido y revisado;
- fencing global, coordinación con Consistency Journal o resistencia anti-rollback.

El cierre de I-2 requiere tests unitarios y de integración, suite completa, compileall, revisión del diff y evidencia de rollback UoW. La implementación debe mantener la propiedad de responsabilidades: Authentication Authority verifica credenciales y emite proofs; Identity Authority consume la evidencia, resuelve el binding y emite VerifiedIdentityContext. No se declarará listo para operación mientras el guard de intentos no tenga adaptador compartido aprobado.

## 9. Brecha de procedencia cerrada en la implementación inicial

Una relectura de issuer/binding/identity por sí sola no demuestra que un objeto `VerifiedIdentityContext` haya sido emitido por Identity Authority: un caller podría fabricar un dataclass con IDs y revisiones actuales. Se añadió una attestation HMAC-SHA256 sobre los claims canónicos para que el verificador distinga contextos emitidos por la composición de confianza de objetos fabricados. `verification_ref` continúa siendo una referencia aleatoria independiente; no es la firma ni un bearer proof.

La clave de attestation debe tener al menos 256 bits, venir de configuración secreta del composition root y compartirse entre workers de confianza. No se guarda en SQLite, logs ni el contexto. Cambiar la clave invalida los contextos vivos emitidos con la clave anterior. La clave no se expone a requests, plugins, herramientas ni modelos.

Para revalidar un contexto sin incluir `NativeSubject` ni `subject_digest` en él, se añadió `get_native_binding_by_id(binding_id)` a Native Identity Authority. El binding ID es inmutable; el verificador compara issuer, identity, estado y revisión contra el registro actual.

## 10. Implementación inicial de proof admission y derivación

Implementado en revisión:
- `VerifiedIdentityContext` frozen con UUIDs canónicos, USER fijo, revisiones positivas, timestamps UTC, referencia aleatoria y attestation HMAC.
- `HmacVerifiedIdentityContextAttestor` y su puerto. La firma usa HMAC-SHA256 y la verificación es constant-time.
- `VerifiedIdentityContextService.admit_proof`: consume proof, resuelve issuer por realm confiable, binding por issuer + subject digest derivado del proof y usuario canónico por I-1; exige que la autenticación no preceda la verificación del binding; crea el contexto y confirma todo dentro de la misma `SQLiteLocalAuthorityUnitOfWork`.
- Si la resolución de issuer, binding o usuario falla después de consumir el proof, la excepción revierte la transacción y el proof permanece pendiente. Los estados terminales que el adaptador marca al no admitir un proof se confirman antes de devolver DENY.
- `VerifiedIdentityContextService.verify`: verifica HMAC, TTL, issuer, binding por ID, identidad USER, estado y revisiones actuales.
- `VerifiedOperationContextFactory`: deriva `OperationContext` con actor y user_id canónicos, delegation/project/environment en None. No acepta actor ni user_id del caller.
- Tests iniciales para IDs distintos, replay, audience incorrecta, HMAC manipulado, clave diferente, binding revocado, identidad suspendida, rollback tras binding inválido y expiración.

**Límite de uso:** la fábrica de OperationContext no hace seguros por sí sola a los consumidores CAM existentes. Hasta I-3, los servicios sensibles deben seguir considerándose no reconciliados; esta implementación no habilita operaciones protegidas, login operativo ni endpoints.

**Validación:** pendiente de ejecución por el propietario en Debian. No se declara este slice validado hasta ejecutar pruebas focalizadas, suite completa y compileall.