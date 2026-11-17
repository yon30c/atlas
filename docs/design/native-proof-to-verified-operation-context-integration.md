# Diseño de integración: Native Proof → VerifiedIdentityContext → OperationContext

**Estado:** diseño de integración propuesto; requiere revisión antes de implementación.
**Rama:** `feature/cycle-3-2-c1-native-credentials`.
**Alcance:** definir la frontera de confianza entre las primitivas C1 ya persistidas y el contexto de operación de Atlas. No habilita login, bootstrap ni operaciones protegidas.

## 1. Resumen ejecutivo

C1 aporta persistencia de autenticadores Argon2id, proofs nativos one-shot y bindings nativos issuer/subject → Identity(USER). Todavía no aporta un flujo de autenticación completo ni un `VerifiedIdentityContext` productivo.

La integración debe mantener cuatro etapas separadas:

1. **Authentication Authority:** verifica la contraseña contra el PHC Argon2id del autenticador y emite un proof opaco de corta duración.
2. **Proof admission:** consume el proof una sola vez, ligado a una audience esperada.
3. **Identity Authority:** resuelve el binding exacto y la pareja canónica UserId/Identity(USER), validando estados y revisiones.
4. **Application identity boundary:** construye un `VerifiedIdentityContext` efímero y, solo para una operación concreta, deriva un `OperationContext` con actor y UserId canónicos.

CAM sigue siendo una decisión posterior e independiente. Ninguna de estas etapas emite un Grant ni concede permisos.

## 2. Estado real de las capacidades existentes

### 2.1 Ya implementado en C1

- `NativeAuthenticator`: issuer, subject nativo, login handle, PHC Argon2id, credential revision y estado.
- `NativeAuthenticationProof`: proof id, digest de referencia, issuer, subject, authenticator, credential revision, timestamps, audience y estado.
- `SQLiteNativeAuthenticationAuthority`: persistencia de autenticadores, emisión de metadatos de proof y consumo one-shot mediante actualización condicional.
- `NativeIdentityIssuer` y `NativeIdentityBinding`: issuer nativo y binding no reasignable hacia Identity(USER).
- `SQLiteNativeIdentityAuthority`: creación/lectura de issuer y binding, revocación CAS.
- `SQLiteIdentityAuthority`: crea y recupera la relación canónica UserId/Identity(USER).
- `SQLiteLocalAuthorityUnitOfWork`: permite que esas autoridades compartan una transacción SQLite física cuando reciben la misma UoW.

### 2.2 Todavía no implementado

- Servicio de login que busque el autenticador por login handle, verifique Argon2id y aplique throttling.
- Política/servicio que construya y emita el proof desde una autenticación realmente verificada.
- Consumo de proof integrado con resolución de binding e identidad.
- Modelo y emisor productivo de `VerifiedIdentityContext`.
- Validador de vigencia/revisión del contexto para cada operación.
- Fábrica confiable que derive `OperationContext`.
- Sesiones C2, API/CLI de autenticación y bootstrap de propietario.

No tratar la capacidad de persistir un `NativeAuthenticationProof` como evidencia de que una contraseña fue verificada. El adaptador de persistencia recibe un objeto ya construido y no verifica credenciales.

## 3. Secuencia propuesta de autenticación

### Paso A — resolver y verificar credenciales

La frontera de autenticación recibe el login handle y la contraseña. No acepta del caller `issuer_id`, `native_subject`, `identity_id`, `user_id`, `binding_id`, credential revision ni audience como autoridad.

1. Resolver el issuer nativo por un realm configurado en la composición confiable.
2. Buscar el autenticador por `(issuer_id, login_handle)`.
3. Rechazar de forma uniforme handles inexistentes, autenticadores no activos y credenciales inválidas; evitar diferencias observables que permitan enumerar cuentas.
4. Verificar la contraseña con Argon2id usando el PHC almacenado y el adaptador de hash aprobado.
5. Releer o comprobar estado y `credential_revision` para impedir emitir proof a partir de una credencial que cambió concurrentemente.
6. Solo tras verificación exitosa, generar `NativeProofReference` aleatoria, persistir el digest del proof y devolver la referencia raw una sola vez.

Los límites de intentos, backoff, respuesta temporal, límites de concurrencia y política de rehash deben diseñarse explícitamente. No se asume que C1 ya los implementa.

### Paso B — consumir proof y resolver identidad

La frontera que crea contexto recibe la referencia opaca del proof. La audience esperada se fija en configuración de servidor para el consumidor; no se copia del request.

En una única UoW SQLite:

1. Consumir el proof con `expected_audience` y un instante UTC confiable. Si falla, DENY.
2. Revalidar issuer y autenticador activos, credential revision vigente y timestamps.
3. Calcular `subject_digest` desde el `NativeSubject` contenido en el proof; no aceptar un digest suministrado por el caller.
4. Resolver el binding exacto por `(issuer_id, subject_digest)`; exigir binding ACTIVE.
5. Resolver la Identity(USER) canónica vinculada; exigir Identity ACTIVE y revisión actual.
6. Verificar que issuer, subject, authenticator, proof y binding forman la misma cadena de procedencia.
7. Emitir el contexto verificado solo si todas las condiciones se cumplen; cualquier ausencia, inconsistencia, expiración o error de autoridad produce DENY.

El consumo y las lecturas deben participar en la misma transacción física. No confirmar el consumo y después intentar resolver el binding en una segunda transacción: un fallo intermedio perdería el proof sin producir contexto y complicaría la recuperación. La UoW local puede ofrecer atomicidad SQLite para estas lecturas/escrituras, pero no se presenta como coordinador de Consistency ni como fencing global.

## 4. Bloqueo de API detectado: resolución inversa Identity → UserId

El binding nativo almacena `identity_id`, no `user_id`. Esto es correcto porque el binding pertenece a Identity Authority y no debe duplicar la propiedad del UserId.

Sin embargo, el puerto actual `IdentityAuthorityPort` expone `get_user(user_id)`, pero no una operación canónica para resolver por `identity_id`. `NativeIdentityAuthorityPort` devuelve el binding con `identity_id`, y no debe resolver por sí misma el agregado de usuario.

Antes de implementar el paso B se debe decidir y aprobar una de estas alternativas:

- **Preferida:** añadir a Identity Authority una operación explícita `get_user_by_identity_id(identity_id)`, con contrato de unicidad, validación UUID, retorno `CanonicalUserIdentity | None` y pruebas de consistencia. Su implementación SQLite debe hacer JOIN sobre las tablas canónicas existentes.
- Alternativa: crear un servicio de aplicación Identity Authority que haga esa resolución mediante un puerto canónico ya aprobado, sin consultas SQL fuera de la autoridad.
- No permitido: consultar tablas de Identity Authority desde Native Authentication Authority, duplicar `user_id` en el binding, inferir UserId del UUID de Identity, buscar por login handle o usar un mapeo local paralelo.

La primera alternativa es la más directa y preserva ownership: Native Identity Authority resuelve binding→identity_id; Identity Authority resuelve identity_id→(user_id, Identity).

## 5. Contrato del VerifiedIdentityContext

El modelo debe respetar B1-B-03D y ser efímero, inmutable y no serializar secretos:

- `context_id`
- `identity_id`
- `identity_type = USER`
- `identity_revision`
- `user_id`
- `binding_id`
- `binding_revision`
- `issuer_id`
- `authenticated_at`
- `verified_at`
- `expires_at`
- `verification_ref` opaca

Reglas adicionales para el perfil nativo:

- El proof consumido es evidencia de autenticación; el contexto no contiene la referencia raw ni PHC.
- `verification_ref` referencia evidencia interna/auditable y no permite recuperar un secreto.
- La expiración del contexto es independiente de la expiración del proof, aunque nunca puede extender la validez de la autenticación más allá de la política aprobada.
- Una revisión obsoleta, identidad suspendida/revocada, binding revocado, issuer revocado, fuente indisponible o reloj no confiable produce DENY.
- El contexto no contiene Project, Environment, Grant, roles ni acciones implícitas.
- Un contexto para USER autentica al propietario; no autentica actores AGENT/SERVICE/SYSTEM ni demuestra delegación.

## 6. Derivación segura de OperationContext

`OperationContext` es un DTO de atribución. Su constructor actual valida estructura y tipos, no autenticidad. No debe convertirse en token ni ser aceptado como evidencia de autenticación.

La frontera confiable debe construirlo con:
- `actor` releído como Identity canónica correspondiente a `verified.identity_id`;
- `user_id` igual a `verified.user_id`;
- `delegation=None` para la ruta directa USER de esta fase;
- `project_id` y `environment` resueltos por la operación desde asociaciones canónicas, nunca seleccionados como permisos por el login;
- propósito, clasificación, origen, request/correlation IDs y timestamps asignados por la aplicación según política.

Antes de ejecutar una operación sensible, el consumidor debe validar el contexto contra la fuente de autoridad y las revisiones actuales. No basta con recibir un objeto `VerifiedIdentityContext` fabricado por el caller.

En Python, una clase frozen, un constructor privado por convención, un nombre con guion bajo o un sello booleano no son una frontera criptográfica contra código arbitrario dentro del mismo proceso. La garantía real depende de la composición de confianza: solo el entrypoint autenticado recibe acceso a la autoridad/fábrica y los servicios privilegiados no se exponen a inputs que permitan fabricar el actor/contexto. Si hay callers no confiables dentro del proceso, el servicio sensible debe validar una referencia/evidencia verificable por un puerto confiable en cada operación.

No pasar un `OperationContext` construido por el request, plugin, modelo LLM o herramienta externa a un servicio privilegiado.

## 7. Consola local actual: estado provisional, no identidad autenticada

`src/atlas/assistant/local_console.py` usa `getuser()` para crear:
- `user_id = local:<OS username>`;
- `identity_id = local-user:<OS username>`;
- actor `Identity(USER, ACTIVE)`;
- `OperationContext` directo sin evidencia de autenticación.

Este comportamiento es una identidad sintética de conveniencia para la conversación local. No es un registro de `IdentityAuthority`, no tiene UserId UUIDv4 canónico, no tiene issuer/binding, no consume proof y no produce `VerifiedIdentityContext`.

Reglas:

- No vincular automáticamente el nombre de usuario Linux/Windows a un UserId Atlas.
- No convertir UID/GID, nombre de cuenta, ruta HOME, sesión de terminal ni posesión del proceso en identidad Atlas sin un mecanismo local de autenticación explícito y revisado.
- No permitir que el contexto sintético alcance CAM, Memory Gateway, Workspace, Skills, Broker, bootstrap ni ninguna capacidad protegida.
- Mantener el comportamiento actual únicamente como modo conversacional provisional hasta que se diseñe su reemplazo. No cambiarlo dentro de este incremento documental.

## 8. Invariantes y pruebas de aceptación

Pruebas positivas:
- login válido produce proof con audience configurada;
- proof válido y binding activo resuelven exactamente el par canónico;
- UserId e identity_id distintos se conservan correctamente;
- contexto válido deriva actor USER y UserId canónicos separados;
- todas las lecturas/escrituras del paso B usan una UoW compartida.

Pruebas negativas:
- contraseña incorrecta, handle desconocido, autenticador suspendido/revocado;
- cambio concurrente de credential revision;
- proof inexistente, expirado, replay o audience incorrecta;
- issuer suspendido/revocado;
- binding inexistente, revocado, con subject/issuer incorrectos;
- Identity inexistente, no USER, suspendida/revocada o revisión obsoleta;
- caller que intenta enviar user_id/identity_id/binding/audience propios;
- contexto expirado, manipulado o verificado para otra solicitud;
- reloj o autoridad indisponible;
- contexto sintético local usado para una capacidad protegida;
- fallo a mitad de la resolución: rollback íntegro del consumo de proof y de las escrituras asociadas.

No registrar contraseñas, PHC, NativeSubject en claro, proof raw, tokens ni referencias secretas.

## 9. Decisiones que deben cerrarse antes de código

1. Aprobar la resolución canónica `identity_id → CanonicalUserIdentity` dentro de Identity Authority.
2. Definir el servicio de autenticación nativa (lookup, Argon2id, throttling, proof issuance y rehash).
3. Definir la transacción de proof consumption + binding lookup + canonical identity resolution.
4. Aprobar el modelo/puerto/emisor/verificador de `VerifiedIdentityContext` y sus TTL/política de reautenticación.
5. Definir la frontera de aplicación que deriva `OperationContext` y cómo impide callers no confiables.
6. Definir la política de la consola local provisional y su bloqueo explícito frente a capacidades protegidas.
7. Reconciliar los consumidores CAM que hoy equiparan `actor.identity_id` con `context.user_id`, sin eliminar sus validaciones de ownership `Grant.owner_user_id == context.user_id`.

**Límite de este documento:** no cambia código, contratos normativos, migraciones, DB productiva, host, PAM, systemd, sudoers ni privilegios. No habilita login, bootstrap, sesiones, grants iniciales ni capacidades protegidas.
