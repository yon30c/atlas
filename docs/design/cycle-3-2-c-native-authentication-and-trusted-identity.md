# Cycle 3.2-C — Autenticación nativa e identidad confiable

**Estado:** diseño del ciclo adoptado; implementación no iniciada.  
**Dependencia Git:** PR #5 (3.2-A) → PR #6 (3.2-B) → este diseño (3.2-C).  
**Rama:** `design/cycle-3-2-c-native-authentication-trusted-identity`.  
**Baseline de esta rama:** head de PR #6 `9a80ba3b8b9c5f8f5048f0ad98905faaf0b5bf7c`.  
**Alcance:** decisiones de integración, contratos entre autoridades, secuencia, seguridad y aceptación. No modifica contratos normativos B1 ni habilita autenticación operativa.

---

## 1. Propósito y relación con los diseños existentes

Cycle 3.2-C cierra la frontera de autenticación e identidad necesaria para conectar de forma confiable la consola con el registro canónico de workspaces de 3.2-A y el gate CAM de 3.2-B.

Este documento **no reemplaza ni duplica** las especificaciones ya existentes:

- [Decisión de autenticación nativa y portabilidad](native-authentication-and-machine-portability-decision.md): dirección de producto y límites de portabilidad adoptados.
- [Contrato de compatibilidad de autenticación nativa e Identity Authority](native-authentication-contract-compatibility.md): compatibilidad lógica con B1-B-03A/B/C/D.
- [Diseño técnico de Authentication Authority nativa](native-authentication-authority-technical-design.md): propuesta técnica de credenciales, proof, sesiones y bootstrap.
- [Diseño físico de Identity Authority](b1-b03b-identity-authority-physical-design.md): propiedad de datos, persistencia y límites físicos.
- [Contrato de OperationContext](../contracts/operation-context.md): estructura y semántica del contexto de operación.
- [3.2-A — Registro canónico](cycle-3-2-a-workspace-registry-implementation.md) y [3.2-B — Mount y gate CAM](cycle-3-2-b-trusted-workspace-mount-cam-gate.md): baseline funcional del workspace.

Las propuestas técnicas previas de autenticación continúan siendo propuestas donde así se declaran. Este documento adopta decisiones de integración para el ciclo, pero **no modifica por sí solo los contratos normativos B1, las migraciones ni el estado de aprobación de los diseños físicos existentes**.

## 1.1 Hallazgos del baseline inspeccionado (PR #6)

La inspección directa del código en `feature/cycle-3-2-b-trusted-workspace-mount-cam-gate` @ `9a80ba3b8b9c5f8f5048f0ad98905faaf0b5bf7c` confirma estas capacidades y límites:

- `SQLiteLocalAuthorityUnitOfWork` abre una transacción SQLite compartida y expone repositorios de Identity, Project/Environment, Workspaces, Grants (heredado), authority-change storage y repositorios de evidencia de recuperación. Esta es una frontera transaccional local real para los repositorios que participan en esa misma UoW.
- El propio módulo declara que la UoW es una composición de persistencia, no un coordinador de autorización o consistencia: no invalida Grants, no aplica fencing de efectos ni libera claims.
- `IdentityAuthorityPort` actualmente expone `create_user()`, `get_user()` y `update_user_status()`. `SQLiteIdentityAuthority` crea UserId e Identity(USER) en una transacción, pero declara expresamente que no implementa issuer externo, binding, autenticación, recovery ni autorización.
- El baseline no contiene todavía en esa composición una Authentication Authority, almacenamiento de autenticadores/sesiones/proofs ni el flujo operativo de issuer/binding nativo.
- `SQLiteAuthorityChangeStore` persiste reservas, identidad de operación e idempotencia. Su propio contrato aclara que no calcula admisiones afectadas, no aplica fencing a rutas, no muta autoridades fuente ni declara reconciliación.
- Los contratos/modelos de Consistency existentes no demuestran por sí solos que haya un coordinador concreto capaz de ejecutar invalidación y fencing de extremo a extremo.

Referencias de código del baseline:
- [SQLiteLocalAuthorityUnitOfWork](../../src/atlas/adapters/sqlite/local_authority_unit_of_work.py)
- [IdentityAuthorityPort](../../src/atlas/ports/identity_authority.py)
- [SQLiteIdentityAuthority](../../src/atlas/adapters/sqlite/identity_authority.py)
- [SQLiteAuthorityChangeStore](../../src/atlas/adapters/sqlite/authority_changes.py)
- [Límite de consistencia de operaciones del Assistant](assistant-operation-consistency-boundary.md)

**Consecuencia:** la UoW compartida es una base viable para atomicidad local, pero no se puede afirmar todavía que bootstrap sea atómico entre todas las autoridades ni que Consistency proporcione fencing genérico. C0 debe verificar la composición exacta y cerrar el contrato de issuer/binding y la coordinación requerida. No se reutilizarán los contratos de consistencia específicos de Memory como si fueran un coordinador universal.

## 2. Objetivo de seguridad y cadena de confianza

Ninguna capacidad protegida de consola podrá ejecutarse salvo que se cumpla la cadena completa:

1. Authentication Authority valida una credencial o sesión nativa vigente.
2. Authentication Authority produce evidencia nativa confiable y de un solo uso.
3. Identity Authority valida esa evidencia, resuelve el issuer y binding exactos, verifica Identity(USER), UserId canónico, estados y revisiones, y emite VerifiedIdentityContext.
4. La frontera confiable construye OperationContext con datos canónicos, sin aceptar identidad ni scope autoritativos del caller.
5. CAM evalúa la acción, recurso, owner, proyecto, entorno, revisiones y Grant exactos.
6. El servicio de capacidad de workspace vuelve a aplicar los controles de 3.2-B y ejecuta únicamente después de ALLOW.

La autenticación no crea Grants. La identidad verificada no equivale a autorización. Una sesión válida sin Grant debe producir DENY.

## 3. Autoridades y propiedad

| Autoridad | Propiedad exclusiva | Prohibiciones |
|---|---|---|
| Authentication Authority | Login handles, autenticadores, hashes, native subjects, credential revisions, sesiones, familias, proofs nativos y bootstrap token | No crea UserId/Identity, no crea bindings, no emite VerifiedIdentityContext, no crea Grants |
| Identity Authority | Identity, UserId, issuer trust, bindings, revisiones y emisión de VerifiedIdentityContext | No verifica contraseñas, no almacena hashes ni administra sesiones, no crea Grants |
| CAM | Grants y decisiones de autorización | No autentica contraseñas ni administra sesiones o bindings |
| Consistency | Coordinación de invalidación, fencing, admisiones y reconciliación | No escribe agregados canónicos de Authentication Authority, Identity Authority o CAM |
| Trusted Console Boundary | Composición de evidencia y construcción de OperationContext | No inventa identidad, binding, UserId, delegación ni permisos |
| Workspace Capability Service | Revalidación de workspace/mount y ejecución de capacidades autorizadas | No sustituye autenticación, Identity Authority ni CAM |

La co-localización de tablas en SQLite o el uso de una UoW compartida no cambia la propiedad lógica de los agregados.

## 4. Decisiones adoptadas para Cycle 3.2-C

### 4.1 Perfil de issuer nativo

- El issuer nativo representa un realm lógico de Atlas, no una máquina, hostname, UID/GID, contenedor o proceso.
- El native subject es opaco, aleatorio, estable y no reutilizable.
- El login handle solo es un atributo de búsqueda de Authentication Authority.
- El binding usa la pareja exacta `(issuer_id, subject)` y conserva las reglas canónicas de unicidad histórica y no reasignación.
- El perfil nativo se distingue explícitamente de los perfiles de issuer externo. No se simula una firma externa ni se exige un keyset externo a una prueba interna.
- La ampliación física del registro de issuers debe definir un `verification_profile` o discriminador equivalente, sin debilitar las validaciones B1-B-03D de otros issuers.

### 4.2 VerifiedNativeAuthenticationProof

Se adopta para el primer perfil local un **proof opaco respaldado por estado del servidor**, no un token autocontenido que el caller pueda construir ni una firma criptográfica casera.

- Authentication Authority genera una referencia aleatoria de alta entropía.
- Solo persiste el digest de esa referencia y los metadatos mínimos de evidencia.
- La evidencia está ligada al issuer/realm, native subject, authenticator, credential revision, instante de autenticación, expiración y operación/audience esperada.
- Un puerto interno privado permite a Identity Authority verificar y consumir la evidencia directamente desde Authentication Authority.
- El consumo es atómico y de un solo uso.
- Un proof desconocido, expirado, ya consumido, de otro realm, con revisión obsoleta o sin procedencia verificable se rechaza.
- No contiene contraseña, password hash, token de sesión ni secreto reutilizable.
- La protección no depende de constructores privados de Python ni de que un DTO no sea importable.

En la composición local inicial, el puerto entre autoridades debe resolverse dentro del proceso confiable y la misma frontera de persistencia/UoW cuando sea posible. Si en el futuro se separan procesos, se requerirá un protocolo autenticado e íntegro entre servicios; no se confiará en datos de red declarados por el caller.

### 4.3 Sesiones nativas

- El token de sesión contiene 256 bits de aleatoriedad criptográfica como mínimo, es opaco y no transporta identidad ni permisos.
- El token en claro solo se entrega al cliente; se persiste un digest SHA-256 del token de alta entropía. No se registran token ni digest.
- La sesión referencia authenticator, native subject, credential revision y session family; no convierte esos campos en identidad canónica.
- Expiración, revocación y rotación son obligatorias.
- El primer incremento no introduce un refresh token separado.
- La rotación invalida atómicamente el token anterior y crea un único sucesor.
- Se conservan tombstones/digests de tokens rotados durante la vida de la familia para detectar reutilización.
- La reutilización de un token rotado revoca la familia afectada y exige reautenticación.
- Rotaciones concurrentes se resuelven mediante transacción y CAS/estado esperado: solo una puede producir el sucesor válido.
- No se fija un TTL universal. Los límites absoluto, inactividad y reautenticación reciente se parametrizan por clase de operación antes de producción.

### 4.4 Proof por solicitud protegida

No se reutilizará un VerifiedIdentityContext entre solicitudes protegidas.

En cada solicitud protegida:

1. Authentication Authority resuelve el token de sesión.
2. Comprueba expiración, revocación, estado del autenticador y credential revision.
3. Emite un proof opaco, nuevo y de un solo uso, ligado a esa solicitud y sesión.
4. Identity Authority consume el proof, vuelve a comprobar issuer, binding, Identity(USER), UserId y revisiones, y emite un VerifiedIdentityContext efímero.
5. La frontera construye un OperationContext nuevo.

Esto evita que un contexto verificado en una solicitud anterior se convierta en una credencial reutilizable. El proof de login y el proof derivado de sesión comparten invariantes, pero tienen propósitos/audiences distintos y no son intercambiables.

### 4.5 Credential revision e invalidación

- Cada cambio de contraseña incrementa monotonamente `credential_revision`.
- El reemplazo del verificador y el incremento de revisión son atómicos.
- Todas las sesiones emitidas bajo revisiones anteriores dejan de ser válidas.
- Los proofs pendientes bajo revisiones anteriores dejan de ser admisibles.
- Un rehash por actualización de parámetros Argon2id, sin cambio de contraseña, no incrementa por sí solo credential revision; debe conservarse trazabilidad de la versión del hash.
- Suspensión o revocación del autenticador bloquea nuevos logins y sesiones dependientes.
- Identity Authority sigue comprobando revisiones y estados canónicos de Identity y binding.
- Consistency coordina invalidación/fencing cuando una modificación afecta admisiones o contextos de más de una autoridad. Authentication Authority no escribe Identity ni CAM para conseguirlo.
- Si el fencing exigido no puede confirmarse, la operación protegida queda bloqueada.

### 4.6 Bootstrap inicial

El bootstrap es un orquestador de una sola instalación y una sola ejecución. **No pertenece exclusivamente a Authentication Authority.**

- Identity Authority crea Identity(USER), UserId y binding nativo.
- Authentication Authority crea el native subject y el autenticador inicial.
- CAM crea el Grant administrativo inicial mediante su propia API y política explícita.
- El primer usuario no obtiene privilegios por ser el primero ni por controlar el host.
- El secreto de bootstrap se genera fuera de la imagen, tiene entropía suficiente, expiración y persistencia exclusiva de digest.
- La reserva y consumo son atómicos; dos solicitudes concurrentes no pueden completar el bootstrap.
- La cuenta no puede autenticarse como inicial/admin hasta que la composición confirme el estado final del bootstrap.

**Atomicidad:** preferir una sola transacción de la UoW SQLite local compartida si, en el checkout exacto, Identity Authority, Authentication Authority, CAM y bootstrap participan realmente en el mismo archivo y transacción. Cada autoridad seguirá escribiendo únicamente sus repositorios/agregados. Si no comparten una UoW transaccional real, se exige una saga durable e idempotente con estados explícitos, reconciliación y bloqueo de login hasta el estado final. No se aceptan escrituras cruzadas directas ni una secuencia best-effort.

La creación del Grant inicial es una operación CAM explícita y auditable. Un fallo no puede dejar una cuenta parcialmente activada con privilegios implícitos.

### 4.7 Argon2id y login handle

- Argon2id es el esquema inicial de derivación de contraseña.
- Parámetros, versión y salt se almacenan con el verificador y son actualizables.
- Los parámetros concretos se eligen después de benchmark en hardware de despliegue objetivo; no se inventan valores de producción.
- Un handle desconocido debe seguir una ruta de trabajo comparable con un hash ficticio, y la respuesta no debe revelar existencia de cuenta.
- Se aplican rate limits y demoras sin bloqueo permanente explotable por terceros.
- Normalización, unicidad y política de cambio de handle deben quedar especificadas antes de migrar datos.

## 5. Construcción de VerifiedIdentityContext y OperationContext

### 5.1 VerifiedIdentityContext

Identity Authority emite el contexto común exigido por B1-B-03D, incluyendo al menos:

- `context_id`
- `identity_id`
- `identity_type=USER`
- `identity_revision`
- `user_id` canónico
- `binding_id`
- `binding_revision`
- `issuer_id`
- `authenticated_at`
- `verified_at`
- `expires_at`
- `verification_ref`

El contexto es efímero, no contiene tokens ni contraseñas y no es un Grant, sesión ni prueba de delegación. Solo acredita Identity(USER). No autentica AGENT, SERVICE, WATCHER o SYSTEM.

### 5.2 OperationContext

La frontera confiable crea una instancia nueva e inmutable a partir de:

- actor USER recuperado de Identity Authority y coincidente exactamente con `VerifiedIdentityContext.identity_id`;
- `user_id` procedente del VerifiedIdentityContext vigente;
- proyecto y entorno leídos de registros canónicos y validados;
- request_id/correlation_id generados o validados en la frontera confiable;
- origin de la frontera real, no un valor que el caller pueda usar como autoridad;
- purpose/classification según la operación y sus reglas;
- delegation solo cuando exista evidencia explícita.

No se acepta del caller un actor, UserId, identity_id, issuer, subject, binding, estado, proyecto, entorno, owner ni mount como prueba de autoridad.

La ausencia de `delegation` no se convierte automáticamente en INDEPENDENT. Se conserva la semántica del contrato OperationContext: `None` significa que no se declara modalidad; si una operación exige modalidad explícita, debe denegarse cuando falte. Este ciclo solo admite la ruta directa USER no delegada ya soportada por el gate 3.2-B; no implementa delegación.

### 5.3 Compatibilidad con 3.2-B

El servicio de workspace mantiene, sin relajación:

- identidad USER activa y correspondencia canónica UserId/Identity;
- workspace ACTIVE y owner_user_id exacto;
- Project y Environment canónicos, activos y coincidentes;
- asociación Project–Environment explícita y activa;
- Grant CAM exacto para acción y recurso;
- resolución de `root_ref` únicamente desde configuración confiable;
- acceso al filesystem solo después de ALLOW;
- UoW abierta durante la operación filesystem conforme a la garantía local existente.

3.2-C no añade escritura, shell, Skills, Broker ni ejecución multi-paso.

## 6. Consistencia, transacciones y fallos

- La primera composición sigue siendo una instalación local SQLite con una UoW compartida real; no se presume coordinación distribuida.
- Las comprobaciones que dependen de Identity, sesión, CAM y workspace deben ejecutarse dentro de la frontera transaccional/fencing demostrada para el checkout.
- No se afirma que una transacción SQLite proteja contra cambios externos al archivo, múltiples hosts o varias réplicas.
- No se mantiene abierta una transacción a través de llamadas de red. La primera implementación mantiene autoridades en el mismo proceso/UoW; una separación futura requiere otro protocolo.
- Cada operación con efectos mantiene idempotencia/correlación conforme a su contrato.
- Ante resultado incierto, timeout o fallo de una autoridad, no se asume éxito ni se reintenta una mutación sin reconciliación.

Fail closed ante autenticador inexistente/inactivo, contraseña incorrecta, proof inválido/replay/expirado, sesión expirada/revocada/rotada, credential revision obsoleta, issuer/binding no confiable, Identity no USER/inactiva, UserId inconsistente, contexto expirado, proyecto/entorno/workspace inválidos, mount desconocido, Grant ausente, CAM/Consistency indisponible o cualquier discrepancia de scope.

## 7. Modelo de datos conceptual y migraciones

Los siguientes agregados pertenecen a Authentication Authority y no deben fusionarse con las tablas canónicas de Identity:

- native_authenticators;
- native_sessions;
- session_families / session_token_history;
- native_authentication_proofs;
- bootstrap_state.

Identity Authority conserva sus propios agregados:

- identity_records;
- atlas_users;
- identity_issuers con perfil de verificación;
- identity_bindings y tombstones.

CAM conserva Grants. Consistency conserva su journal, invalidaciones y fencing.

No se aprueba todavía un esquema SQL definitivo. Antes de elegir tablas/índices/constraints hay que inspeccionar el baseline exacto de la rama 3.2-B, la UoW real y las migraciones actuales. Toda evolución será una migración nueva y aditiva; no se modifica ni recalcula el historial de migraciones. El número de migración se determina desde ese baseline, no se presupone.

La persistencia de tokens, proofs, bootstrap y tombstones debe incluir índices de unicidad, expiración y estados terminales suficientes para impedir replay y reutilización.

## 8. Secuencia de implementación y gates

### 3.2-C0 — Cierre de contratos y baseline físico

- Verificar B1-B-03A/B/C/D y el diseño físico vigente.
- Confirmar perfil nativo de issuer y representación en el registro de issuers.
- Confirmar puerto privado de proof y consumo atómico.
- Confirmar UoW/repositorios reales para Identity, CAM, Consistency y workspace.
- Definir esquema aditivo y estrategia de bootstrap transaccional.
- Resolver normalización de login handle, parámetros Argon2id, rate limiting y política de sesión.
- No modificar código ni migraciones hasta cerrar estos puntos.

**Gate:** contratos compatibles, propiedad inequívoca y atomicidad demostrable.

### 3.2-C1 — Native Authentication

- Contratos/puertos de Authentication Authority.
- Argon2id y verificación uniforme.
- Login handle y native subject.
- Credential revision.
- Proof nativo opaco, privado, efímero y one-shot.
- Bootstrap orquestado con Identity Authority y CAM, sin privilegios implícitos.

**Gate:** pruebas de credenciales/proof/bootstrap; sin sesión persistente ni integración CLI.

### 3.2-C2 — Secure Sessions

- Tokens opacos de alta entropía y digest-only persistence.
- Expiración, revocación y familias.
- Rotación atómica y detección de reuse.
- Proof fresco por cada resolución de sesión.
- Invalidación por credential revision y eventos de seguridad.

**Gate:** pruebas de concurrencia, replay, expiración, revocación y cambio de contraseña.

### 3.2-C3 — Verified Identity

- Perfil de issuer nativo.
- Consumo del proof por Identity Authority.
- Resolución del binding exacto y relación UserId↔Identity(USER).
- Verificación de estados/revisiones y anti-replay.
- Emisión de VerifiedIdentityContext efímero.

**Gate:** ninguna entrada del caller puede producir identidad verificada; pruebas de binding, issuer, revision y replay.

### 3.2-C4 — Trusted Console Integration

- Resolución de sesión y proof fresco.
- Verificación de identidad.
- Construcción confiable de OperationContext.
- Resolución canónica de Project/Environment/Workspace.
- Integración con CAM y Workspace Capability Execution Service.
- Activación únicamente de list/read que ya están dentro del alcance 3.2-B.

**Gate:** pruebas E2E de login → sesión → proof → Identity Authority → OperationContext → CAM → workspace. Las capacidades protegidas permanecen deshabilitadas hasta que este gate pase.

## 9. Matriz mínima de pruebas de aceptación

### Credenciales y login

- Password válido/inválido.
- Handle desconocido con respuesta no enumerativa.
- Hash corrupto o versión/parametrización no soportada.
- Salt único y parámetros versionados.
- Throttling/rate limiting.
- Handle duplicado y cambio de handle sin cambiar subject/identidad.
- Cambio de contraseña incrementa revisión y revoca sesiones/pruebas anteriores.

### Proof

- Referencia aleatoria y digest-only persistence.
- Proof desconocido, manipulado, expirado, consumido o de otro audience/realm.
- Dos consumos concurrentes: exactamente uno puede tener éxito.
- Proof no contiene contraseña, hash ni token.
- No se puede construir evidencia aceptable desde la API/caller.

### Sesiones

- Token aleatorio de alta entropía; raw token ausente de DB/logs.
- Token alterado, desconocido, expirado o revocado.
- Rotación atómica; token anterior no vuelve a ser válido.
- Reuse de token rotado revoca familia.
- Rotaciones concurrentes producen un solo sucesor.
- Cambio de contraseña/autenticador invalida sesiones previas.
- Sesión no se convierte en UserId, VerifiedIdentityContext ni Grant.

### Bootstrap

- Se ejecuta solo en estado INITIAL.
- Secreto inválido/expirado/reutilizado falla.
- Dos bootstraps concurrentes no pueden tener éxito.
- Fallo de cada autoridad no activa login parcial.
- Identity Authority crea UserId/Identity/binding.
- Authentication Authority crea subject/authenticator.
- CAM crea Grant explícito y auditable.
- No hay privilegio por orden de creación ni identidad Linux.
- Reinicio/retry recupera o bloquea según estado durable, sin duplicar agregados.

### Identity y consola

- Issuer desconocido o perfil incorrecto falla.
- Binding ausente, revocado, ambiguo o de otro subject falla.
- Identity no USER/inactiva o revisiones obsoletas fallan.
- UserId e identity_id se resuelven por relación canónica, nunca por igualdad textual.
- VerifiedIdentityContext expirado/replay falla.
- Caller no puede suministrar actor, UserId, issuer, binding, owner o scope autoritativo.
- Delegación no se infiere de None ni de la sesión.
- CAM DENY o indisponible impide ejecución.
- Workspace/Project/Environment/association/mount inválidos impiden ejecución.
- No se invoca filesystem ante cualquier denegación.

### Regresión

- Suite completa de Atlas.
- Pruebas focalizadas de autenticación, Identity, Consistency, CAM y workspace.
- Migración desde el schema previo y verificación de checksums.
- `python -m compileall -q src tests`.
- No declarar pruebas exitosas hasta disponer de salida real del checkout validado.

## 10. No objetivos y límites

Este ciclo no implementa ni autoriza:

- Login Linux/PAM, UID/GID, getuser(), hostname o identidad del proceso como identidad humana.
- Proveedores externos Google/GitHub/OIDC, linking/unlink, recovery o merge de identidades.
- MFA, WebAuthn o passkeys.
- Registro público de usuarios.
- Autenticación de AGENT/SERVICE/WATCHER/SYSTEM.
- Delegación.
- Consola web completa, cookies/CSRF o exposición de red.
- Refresh tokens separados.
- Active-active, varias réplicas o SQLite compartida entre hosts.
- Escritura de workspace, shell, Skills, Broker o runtime.
- Cambios en host, systemd, usuarios, grupos, sudoers, PAM, Docker o base de datos productiva.
- Aplicar migraciones a datos reales o desplegar autenticación operativa.

## 11. Criterio de cierre de Cycle 3.2-C

El ciclo solo se cierra cuando:

1. Authentication Authority administra credenciales, proofs y sesiones sin emitir identidad ni permisos.
2. Identity Authority es la única que emite VerifiedIdentityContext para Identity(USER).
3. Bootstrap crea los registros de cada autoridad mediante transacción compartida demostrada o saga durable aprobada.
4. Credential revision, revocación, rotación y replay tienen garantías probadas.
5. Trusted Console construye OperationContext desde evidencia y registros canónicos.
6. CAM autoriza cada operación de forma independiente.
7. El gate de workspace de 3.2-B conserva todas sus comprobaciones.
8. Las pruebas de regresión y aceptación pasan en el checkout exacto.
9. No se han introducido cambios de host ni privilegios.
10. La autenticación operativa solo se habilita después de un gate explícito de seguridad y validación.

**Principio rector:** Authentication Authority demuestra cómo se autenticó el sujeto; Identity Authority determina a qué Identity(USER) y UserId canónicos corresponde; la frontera confiable compone la operación; CAM decide si puede ejecutarse.
