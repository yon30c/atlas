# Cycle 3.2-C1 — Native Authentication: contratos y diseño físico

**Estado:** diseño técnico para revisión; código y migraciones no iniciados.  
**Depende de:** PR #7 — Cycle 3.2-C, y por transitividad PR #5/#6.  
**Baseline:** schema v18 y head de diseño 3.2-C `082cce843ae603b8d8c2cbea1616e0f698f8268f`.  
**Objetivo:** especificar credenciales nativas, issuer/subject nativo, binding canónico, proof one-shot y bootstrap local. Las sesiones persistentes pertenecen a C2.

---

## 1. Alcance

C1 implementará el primer mecanismo de autenticación nativa de Atlas, pero no expondrá todavía una consola ni endpoints operativos.

Incluye:

- contratos de dominio y puertos de Authentication Authority;
- normalización y unicidad de login handle;
- autenticador de contraseña Argon2id;
- subject nativo opaco;
- perfil de issuer nativo y binding hacia Identity(USER);
- proof de autenticación nativa opaco, respaldado por estado de servidor y consumible una sola vez;
- bootstrap de primer usuario mediante UoW SQLite compartida;
- auditoría sin secretos y pruebas negativas/atómicas.

No incluye:

- sesiones persistentes, refresh tokens ni cookies (C2);
- emisión pública de VerifiedIdentityContext (C3);
- consola/API de usuario, rutas HTTP o CLI protegida (C4);
- autenticación de AGENT/SERVICE/WATCHER/SYSTEM;
- proveedores externos, linking/unlink, recovery, merge o MFA;
- activación en host o base de datos real.

El único uso de C1 antes de C3/C4 será mediante pruebas de integración internas y no expuestas.

## 2. Dependencias y baseline

El baseline exacto contiene:

- `identity_records` y `atlas_users` desde schema v5;
- integridad recíproca diferida desde v6;
- Grants canónicos desde v7;
- composición `SQLiteLocalAuthorityUnitOfWork` sobre una única transacción `BEGIN IMMEDIATE`;
- repositorios de Identity y Grants compartiendo el mismo `SQLiteUnitOfWork`;
- schema actual v18.

Por tanto, C1 no recrea UserId ni Identity(USER). Añade únicamente issuer/binding nativo y agregados de Authentication Authority.

La siguiente migración esperada en la rama integrada será v19. El número final se verificará contra la rama resultante de integrar #5/#6; no se codifica una migración hasta confirmar ese baseline y su checksum histórico.

## 3. Contratos de dominio

### 3.1 LoginHandle

- ASCII solamente.
- Acepta entrada case-insensitive y normaliza a lowercase ASCII antes de cualquier lookup.
- Longitud normalizada: 3–64 caracteres.
- Patrón: `[a-z0-9][a-z0-9._-]{2,63}`.
- No acepta email, espacios, controles ni normalización Unicode implícita.
- Unicidad dentro del realm nativo.
- Cambiar el handle no cambia native subject, binding, UserId o identity_id.
- El handle no es subject, identidad, credencial ni autorización.

El error externo de login para handle inexistente y contraseña incorrecta será indistinguible. La capa de dominio puede distinguirlos internamente para auditoría, sin filtrar esa distinción al caller.

### 3.2 PasswordCredential

Política inicial:

- mínimo 12 puntos de código Unicode;
- máximo 1024 bytes UTF-8 después de codificar;
- no recortar espacios ni normalizar Unicode silenciosamente;
- rechazo de cadena vacía, NUL y entrada que exceda el límite;
- password nunca se conserva en un objeto persistente ni en logs.

El máximo de bytes es un límite de recursos, no un máximo de entropía recomendado. La política puede endurecerse mediante una revisión explícita.

### 3.3 Argon2id

Decisión de biblioteca: `argon2-cffi`, API de alto nivel `PasswordHasher` con parámetros explícitos y tipo `Type.ID`.

- Persistir el PHC encoded hash, que incluye algoritmo, versión, parámetros y salt.
- Salt aleatorio único por autenticador.
- No implementar primitivas Argon2 ni gestión de salt propia.
- Configuración de `time_cost`, `memory_cost`, `parallelism`, `hash_len` y `salt_len` inyectada por composición confiable.
- No depender de defaults implícitos de la biblioteca.
- Seleccionar valores de producción mediante benchmark en el hardware objetivo; objetivo inicial de calibración: coste perceptible pero usable, sin fijar parámetros sin medición.
- Verificación de hash inválido o parámetros no soportados falla cerrada.
- Rehash al verificar si `check_needs_rehash` indica parámetros obsoletos. Rehash no cambia credential_revision porque no cambia la contraseña.
- Cambio/reset de contraseña sí incrementa credential_revision y revoca proofs pendientes de la revisión anterior.

La dependencia se añadirá al grupo de dependencias de runtime en `pyproject.toml`; la versión exacta se resolverá y quedará fijada por el mecanismo de instalación/lock que el repositorio adopte, sin introducir una versión arbitraria.

### 3.4 Native issuer y realm

Identity Authority será propietaria del registro del issuer y del binding.

- Un único issuer nativo por realm lógico de Atlas.
- El realm es estable al mover/restaurar la misma instalación lógica en otro host.
- El issuer no se deriva de hostname, IP, UID/GID, hardware, contenedor o nombre del proceso.
- `issuer_id` es una referencia canónica del registro, generada en bootstrap y no seleccionable por el caller.
- El perfil de verificación será `NATIVE_AUTHORITY_PROOF`, distinto de `EXTERNAL_CRYPTOGRAPHIC`.
- Para el perfil nativo no se requiere `keyset_ref` externo ni se simula una firma JWT/OIDC.
- El registro del issuer conserva estado y revisión monotónica. REVOKED es terminal.
- Clonar una instalación para formar un realm independiente requiere procedimiento de separación de realm y secretos; no se permite copiar silenciosamente la misma identidad lógica.

### 3.5 NativeSubject

- Generado mediante CSPRNG con al menos 256 bits de entropía.
- Opaco, estable, no reutilizable y único dentro del issuer.
- No es login handle, email, UserId, identity_id, token de sesión ni secreto de autorización.
- El cambio de contraseña o login handle no lo cambia.
- La revocación del binding conserva tombstone y reserva el subject.

Para el almacenamiento del binding nativo, persistir SHA-256 del subject aleatorio de alta entropía (hex lowercase de 64 caracteres) en lugar del valor original. SHA-256 es aceptable aquí porque el subject se genera con 256 bits aleatorios y no es una contraseña ni un identificador humano de baja entropía. No reutilizar esta decisión para subjects externos; esos requieren el fingerprint/HMAC y gestión de claves definidos por B1-B-03B.

Authentication Authority conserva el subject original como atributo interno del autenticador, necesario para emitir la prueba. La fuga del subject no autentica por sí sola ni permite obtener un proof.

### 3.6 IdentityBinding

Identity Authority administra el binding canónico:

- binding_id UUIDv4 canónico, opaco e inmutable;
- identity_id FK a Identity(USER);
- issuer_id FK a issuer nativo;
- subject_digest SHA-256;
- status ACTIVE/REVOKED;
- revision monotónica;
- created_at, verified_at y revoked_at;
- UNIQUE(issuer_id, subject_digest), incluso tras revocación;
- tombstones no eliminables;
- binding revocado no se reactiva ni reasigna.

Una identidad USER puede tener varios bindings conforme a B1-B-03A. No se implementa linking de cuentas adicionales en C1; el bootstrap crea exactamente el binding nativo inicial. El mecanismo de vinculación de otros issuers sigue fuera de alcance.

La relación UserId↔Identity(USER) ya existe y no se duplica. El binding referencia identity_id y se resuelve junto al UserId canónico mediante Identity Authority.

## 4. Authentication Authority

### 4.1 Agregado NativeAuthenticator

Propiedad exclusiva de Authentication Authority. Campos conceptuales:

- authenticator_id UUIDv4 opaco;
- realm/issuer_id;
- native_subject;
- login_handle_normalized;
- password_hash_phc;
- password_hash_version/metadata (derivable del PHC más metadatos de implementación);
- credential_revision positiva;
- status ACTIVE/SUSPENDED/REVOKED;
- created_at/updated_at;
- revoked_at cuando aplique.

Restricciones:

- UNIQUE(realm_id, login_handle_normalized);
- UNIQUE(realm_id, native_subject);
- subject y authenticator_id inmutables;
- credential_revision aumenta exactamente uno en cambio de contraseña;
- REVOKED terminal;
- no DELETE físico;
- el hash solo se devuelve a la ruta privada de verificación, nunca al dominio público, API o logs.

No guardar contraseñas en claro, sesiones ni Grants en este agregado.

### 4.2 Operaciones conceptuales

Los nombres son contratos internos ilustrativos, no API pública final:

- `register_native_authenticator(login_handle, password, bootstrap_context)`
- `verify_native_credentials(login_handle, password, request_context) -> NativeAuthenticationProofRef | Denied`
- `consume_native_proof(proof_ref, expected_audience) -> VerifiedNativeAuthenticationEvidence | Denied`
- `change_native_password(authenticator_id, expected_revision, old_password, new_password)`
- `suspend_native_authenticator(authenticator_id, expected_revision)`
- `revoke_native_authenticator(authenticator_id, expected_revision)`

Authentication Authority no recibe ni emite UserId, Identity, IdentityBinding, VerifiedIdentityContext, OperationContext o Grant.

## 5. VerifiedNativeAuthenticationProof

### 5.1 Representación

- referencia aleatoria de al menos 256 bits;
- el valor entregado es opaco;
- persistir solo SHA-256(reference);
- ligar a issuer_id/realm, native_subject, authenticator_id, credential_revision, authenticated_at, expires_at, audience y proof_id;
- TTL corto configurado en composición; valor exacto definido junto a C2 y política de reloj;
- estado PENDING/CONSUMED/EXPIRED/REVOKED;
- no contiene password, hash, session token ni claims elegidos por caller.

### 5.2 Consumo

- Identity Authority invoca un puerto interno confiable de Authentication Authority.
- El consumo valida digest, issuer/profile, audience, estado, expiración, subject y credential_revision.
- Consumo y transición a CONSUMED ocurren en la misma UoW compartida.
- Dos consumidores concurrentes: exactamente uno puede obtener evidencia válida.
- Proof consumido, desconocido, alterado, expirado, de otro audience/realm o con revisión obsoleta se rechaza.
- La referencia no se puede convertir en VerifiedIdentityContext desde la API pública.
- No se considera segura únicamente por tener un constructor privado de Python.

C1 puede probar el consumo con un adaptador interno de Identity Authority. La emisión de VerifiedIdentityContext de producción permanece en C3.

## 6. Bootstrap local todo-o-nada

### 6.1 Condiciones

- Solo permitido cuando no existe el estado INITIAL/COMPLETED de bootstrap.
- Secreto aleatorio de al menos 256 bits, presentado una sola vez.
- Persistir solo digest, expiración, estado y metadatos mínimos.
- Consumo de secreto y creación de los agregados dentro de una sola UoW local.
- Reintento exacto no duplica identidad, subject, autenticador, binding ni Grant.
- Un segundo bootstrap concurrente falla.
- Tras COMPLETED, no existe ruta de bootstrap alterna o reabrible.

### 6.2 Orden dentro de la transacción

1. Verificar estado INITIAL y digest/expiración del secreto.
2. Identity Authority crea Identity(USER) y UserId canónicos usando su repositorio actual.
3. Identity Authority registra el issuer nativo si aún no existe y crea el binding nativo.
4. Authentication Authority crea native subject y NativeAuthenticator con Argon2id.
5. Authentication Authority consume el secreto y persiste bootstrap COMPLETED.
6. CAM crea el Grant administrativo inicial mediante su propia API/repositorio y política explícita.
7. El orquestador comprueba relaciones y estados finales; la UoW hace commit.

Todas las operaciones reciben la misma instancia de `SQLiteLocalAuthorityUnitOfWork` y usan la misma `SQLiteUnitOfWork` activa. No se permite abrir una UoW anidada desde un repositorio.

El Grant inicial no es emitido por Authentication Authority. La política CAM debe definir el scope y acciones mínimos; no se concede un Grant global por ser el primer usuario. Si no existe un perfil administrativo mínimo aprobado, el bootstrap puede crear el usuario pero no activarlo para operaciones protegidas.

### 6.3 Fallo y recuperación

Cualquier error antes del commit revierte todas las escrituras. El estado bootstrap permanece INITIAL y el secreto no se consume. Un resultado de commit ambiguo no se declara éxito; la siguiente ejecución consulta el estado durable y verifica todos los agregados antes de reintentar. No se crea saga para esta composición local.

## 7. Rate limiting y respuesta de login

- Respuesta pública uniforme para handle desconocido, contraseña incorrecta y autenticador no admisible.
- Hash ficticio Argon2id con parámetros equivalentes para handle desconocido, evitando una ruta de coste trivial.
- Rate limiting por handle normalizado y límite global de realm.
- No se confía en IP/headers de caller como identidad; si se usa dirección de transporte, solo se admite desde un proxy explícitamente confiable.
- No se aplica bloqueo permanente de cuenta por fallos.
- Ventanas y demoras son temporales, acotadas y auditables.
- La política debe evitar que un tercero bloquee indefinidamente la cuenta de la víctima.
- Cualquier estado de throttling persistido pertenece a Authentication Authority y no guarda contraseñas ni tokens.

Los valores de umbral se fijarán con pruebas de abuso y rendimiento; no se incrustan números de producción sin medición.

## 8. Migración física candidata

La siguiente migración esperada es v19, pendiente de confirmar el baseline tras integrar #5/#6.

Tablas candidatas:

- `native_authenticators` (Authentication Authority);
- `native_authentication_proofs` (Authentication Authority);
- `native_bootstrap_state` (Authentication Authority);
- `identity_issuers` con perfil de verificación nativo (Identity Authority);
- `identity_bindings` (Identity Authority).

Las tablas y columnas exactas deben respetar:

- FK hacia identity_records y atlas_users sin duplicar su autoridad;
- FK/constraints de issuer y binding;
- unique login handle por realm;
- unique subject digest por issuer, incluyendo tombstones;
- estados terminales y revisiones CAS;
- digest-only para proof y bootstrap;
- ausencia de password/session raw;
- índices para lookup, expiración y estados pendientes.

No se incorpora aún `native_sessions`; eso corresponde a C2.

La migración debe ser aditiva y transaccional, sin editar v1–v18. Se probará desde schema v1 hasta v18 y desde fixtures de datos representativos, verificando checksums, FKs, triggers, índices, rollback y `PRAGMA foreign_key_check`. No se ejecutará sobre una DB real como parte de C1.

## 9. Pruebas obligatorias de C1

### Login handle y contraseña

- normalización ASCII y límites;
- rechazo de caracteres Unicode/lookalikes y controles;
- unicidad por realm;
- password min/max y UTF-8 inválido/limítrofe;
- no trimming ni normalización implícita;
- PHC Argon2id y salt único;
- password correcto/incorrecto;
- hash corrupto/no soportado falla cerrado;
- unknown handle y wrong password misma respuesta pública y coste comparable;
- rehash no incrementa credential_revision;
- cambio de contraseña incrementa revisión exactamente una vez;
- autenticador suspendido/revocado no emite proof.

### Subject y binding

- subject con 256 bits de entropía generado por CSPRNG;
- no deriva de login handle ni UserId;
- binding exacto issuer/subject_digest;
- duplicado incluso después de revocación falla;
- binding apunta solo a Identity(USER);
- tombstone no se elimina ni reactiva;
- identidad y binding creados en una UoW.

### Proof

- referencia aleatoria, digest-only persistence;
- issuer/audience/subject/revision exactos;
- desconocido, alterado, expirado, replay y audience incorrecto fallan;
- dos consumos concurrentes producen exactamente un éxito;
- cambio de contraseña invalida proof pendiente;
- no contiene contraseña, hash ni token de sesión;
- caller no puede construir evidencia admisible.

### Bootstrap

- solo INITIAL;
- secreto válido una vez;
- secreto inválido/expirado/reutilizado falla;
- concurrencia no produce dos usuarios;
- fallo inyectado en cada paso revierte todo;
- Identity, binding, authenticator y Grant quedan todos presentes o ninguno;
- login permanece cerrado antes del commit;
- retry tras resultado ambiguo consulta estado durable sin duplicar;
- Authentication Authority no crea el Grant.

### Regresión y migración

- migraciones v1–v18 preservan nombre/checksum;
- upgrade temporal v18→v19;
- rollback de migración;
- FKs y triggers correctos;
- tests actuales de Identity y CAM no cambian de semántica;
- suite completa y compileall en checkout exacto.

## 10. Secuencia de implementación propuesta

1. Cerrar el contrato de C1 y resolver la revisión del diseño.
2. Añadir dependencia Argon2id y pruebas del hasher aislado.
3. Añadir modelos/puertos de Authentication Authority sin tocar IdentityAuthorityPort salvo la extensión específica para issuer/binding.
4. Añadir repositorios SQLite de issuer/binding y autenticadores/proofs/bootstrap, todos UoW-aware.
5. Añadir migración aditiva siguiente al v18 integrado.
6. Implementar bootstrap orquestado con CAM y Identity Authority en una UoW.
7. Ejecutar pruebas focalizadas, suite completa y compileall.
8. Entregar PR Draft sin merge ni activación de rutas protegidas.

## 11. Gate de salida C1

C1 queda completo únicamente cuando:

- Argon2id está calibrado en el hardware objetivo y parámetros explícitos documentados.
- Login handle/password siguen política y respuestas no enumerativas.
- Native issuer y binding respetan B1-B-03A/B.
- Proof opaco es one-shot y resistente a concurrencia/replay.
- Bootstrap es todo-o-nada en la UoW compartida.
- CAM conserva propiedad del Grant inicial.
- La migración es aditiva y su upgrade/rollback está probado.
- Todas las pruebas pasan en el checkout exacto.
- No hay endpoint público, consola protegida, sesiones ni cambios de host.
- No se habilita ninguna capacidad protegida antes de C2–C4.

**Principio:** Authentication Authority prueba el control de la credencial; Identity Authority mantiene el binding canónico; CAM concede autorización explícita. Ninguno de estos hechos puede inferirse del login handle, del host o del orden de bootstrap.
