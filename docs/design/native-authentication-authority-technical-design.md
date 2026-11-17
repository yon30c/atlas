# Diseño técnico propuesto: Authentication Authority nativa

**Estado:** propuesta técnica para revisión; no aprobada para implementación.  
**Fecha:** 2026-11-17  
**Baseline:** B1-A-06 aprobado; B1-B-03A cerrado normativamente; B1-B-03B/C/D; decisión de autenticación nativa y portabilidad del 17-11-2026.  
**Límite:** diseño únicamente. No modifica contratos normativos, esquema SQLite, credenciales, datos, runtime ni infraestructura.

## 1. Propósito y autoridades

Definir cómo Atlas autentica usuarios mediante credenciales propias sin depender de cuentas Linux y sin crear una ruta de identidad paralela.

Se preservan cuatro responsabilidades:
1. **Authentication Authority:** verifica credenciales nativas y administra autenticadores y sesiones.
2. **Identity Authority:** resuelve la prueba autenticada hacia el binding confiable, Identity(USER) y UserId canónico; emite VerifiedIdentityContext.
3. **CAM:** autoriza cada operación protegida.
4. **Consistency:** coordina invalidaciones, fencing, admisiones y recuperación cuando cambian credenciales, identidad o bindings.

La autenticación no crea Grants ni concede permisos.

## 2. Compatibilidad obligatoria con B1-B-03A/B/C/D

- UserId e identity_id son identificadores distintos, relacionados 1:1 por Identity Authority.
- UserId no se deriva del nombre de acceso, contraseña, host, UID/GID, issuer ni subject.
- Identity(USER) es la identidad canónica; el login handle no es una identidad.
- Los bindings se identifican por la pareja exacta (issuer_id, subject) y no se reasignan después de revocación.
- VerifiedIdentityContext conserva los campos obligatorios de B1-B-03D: context_id, identity_id, identity_type=USER, identity_revision, user_id, binding_id, binding_revision, issuer_id, authenticated_at, verified_at, expires_at y verification_ref.
- El contexto es efímero, no contiene token ni contraseña y no es Grant, sesión ni prueba de delegación.
- OperationContext.user_id no acredita autenticación.
- AuthenticatedUserSubject y AtlasIdentityBindingAdapter siguen siendo legacy; no se reinterpretan como evidencia autenticada.
- AGENT, SERVICE, WATCHER y SYSTEM requieren su propia autenticación/autoridad; este diseño no los autentica.

## 3. Issuer nativo y subject

### 3.1 Realm lógico

Se propone un issuer de primera parte, por ejemplo ATLAS_NATIVE, registrado en el registro confiable de Identity Authority.

Su identidad representa el realm lógico de autenticación de Atlas, no hostname, IP, contenedor, UID/GID ni nodo físico. Debe permanecer estable durante una transferencia autorizada de la misma instalación lógica a otro host.

Una instalación clonada para convertirse en una instalación independiente no puede reutilizar silenciosamente el mismo realm ni sus secretos. La separación de clones queda fuera de este diseño.

### 3.2 Subject nativo

El subject nativo será un identificador opaco, aleatorio, estable y no reutilizable de una cuenta/autenticador nativo. No será:
- login handle, email, nombre o teléfono;
- UserId o identity_id;
- ID del proceso o de la máquina.

Authentication Authority genera el subject en una frontera confiable. Identity Authority mantiene el binding exacto (issuer_id, subject) hacia Identity(USER), conforme a B1-B-03A/B.

El login handle es un atributo de búsqueda de Authentication Authority. Cambiarlo no cambia UserId, identity_id ni subject.

### 3.3 Compatibilidad con B1-B-03D

B1-B-03D describe validación de issuers externos mediante firma, audience, nonce y subject. El issuer nativo no debe fingir que una contraseña es un token externo firmado.

Se propone un perfil de verificación específico para el issuer nativo:
- Authentication Authority verifica la contraseña contra el verificador almacenado.
- La validación produce una prueba interna opaca, denominada conceptualmente VerifiedNativeAuthenticationProof, no construible desde la API pública ni desde el caller.
- La prueba referencia realm, subject nativo, revisión del autenticador, authenticated_at, verified_at, referencia de evidencia y vencimiento/política.
- Identity Authority valida procedencia, issuer activo, revisión y vigencia, resuelve el binding y emite el VerifiedIdentityContext común.
- La prueba no contiene contraseña, hash, token de sesión ni secreto reutilizable.
- La prueba no puede reusarse para una operación distinta ni sobrevivir a su política de expiración.

B1-B-03D requerirá una ampliación explícita para admitir verificadores de issuer por método, manteniendo invariantes comunes de issuer confiable, subject exacto, vigencia, replay, revisión y fail-closed. No se debilita el perfil externo.

## 4. Modelo de credenciales

Se propone un agregado separado, propiedad de Authentication Authority. Campos conceptuales de native_authenticators:
- authenticator_id: ID opaco e inmutable;
- realm/issuer confiable;
- native_subject_id: subject opaco estable asociado al binding;
- login_handle_lookup: clave de búsqueda única según política explícita;
- password_hash: resultado Argon2id, nunca contraseña;
- password_hash_version y parámetros completos/versionados;
- credential_revision: revisión monotónica;
- status: ACTIVE, SUSPENDED o REVOKED;
- created_at, updated_at, password_changed_at y revoked_at.

Reglas:
- Un login handle activo es único dentro del realm conforme a una política documentada de normalización y protección.
- El login handle no participa en la resolución de propiedad ni identidad canónica.
- La respuesta al login no revela si el handle existe.
- Para una cuenta inexistente se realiza trabajo comparable mediante un hash ficticio con parámetros equivalentes.
- Argon2id usa salt aleatorio por credencial y parámetros versionados. Parámetros concretos requieren benchmark y revisión antes de implementar.
- Nunca almacenar contraseñas, secretos reutilizables, hashes rápidos ni secretos en logs, eventos, journal, métricas o backups legibles.
- Actualizar el hash por cambio de parámetros no cambia subject ni identidad.
- Los límites de intentos deben evitar tanto enumeración como bloqueo permanente explotable para denegación de servicio.
- Cambiar login handle no es linking de identidad ni crea un binding nuevo.

No se prescribe aún esquema físico SQLite ni migración. Authentication Authority es propietaria de este agregado; CAM, Identity Authority, Memory y Broker no escriben sus credenciales.

## 5. Flujo de autenticación

1. El cliente envía login handle y contraseña a la frontera confiable mediante transporte protegido.
2. La frontera valida formato y aplica límites.
3. Authentication Authority localiza el autenticador en el realm confiable.
4. Verifica Argon2id con parámetros almacenados; para cuenta inexistente realiza verificación contra hash ficticio equivalente.
5. Comprueba estado ACTIVE, revisión vigente y controles de riesgo.
6. Emite VerifiedNativeAuthenticationProof de vida corta, ligado al subject y revisión exactos.
7. Identity Authority comprueba issuer/realm, binding exacto, Identity(USER), relación 1:1 UserId↔identity_id, estados y revisiones.
8. Identity Authority emite VerifiedIdentityContext con expiración explícita y referencia opaca.
9. La frontera confiable construye OperationContext; el caller no suministra actor, user_id, project_id ni environment como prueba de identidad.
10. CAM autoriza cada capacidad, recurso, scope, proyecto, entorno y delegación.

Ausencia, ambigüedad, estado no activo, revisión obsoleta, binding inconsistente, fuente indisponible o prueba inválida producen DENY.

## 6. Sesiones

La sesión es una credencial de transporte posterior al login, distinta de UserId, identity_id, binding y VerifiedIdentityContext.

Modelo conceptual native_sessions:
- session_id: identificador interno opaco;
- token_digest: digest del token aleatorio de alta entropía;
- authenticator_id y native_subject_id;
- credential_revision y referencias a revisiones de identidad/binding;
- created_at, last_seen_at según política, expires_at y revoked_at;
- referencia de rotación si se adopta.

Reglas:
- Token opaco, aleatorio y de alta entropía; solo se entrega al cliente una vez.
- El token en claro no se persiste ni registra. El servidor conserva un digest criptográfico adecuado.
- Expiración explícita, revocación, rotación y renovación controlada.
- Una sesión no es VerifiedIdentityContext y no se pasa a CAM como permiso.
- Se comprueba estado de cuenta y revisiones relevantes al admitir operaciones protegidas, o se usa un mecanismo de invalidación/fencing cuya garantía esté demostrada.
- Cambio de contraseña, suspensión/revocación del autenticador, revocación de Identity o binding y eventos de seguridad aplicables invalidan sesiones dependientes.
- Rotación invalida el token anterior atómicamente y protege contra replay/fijación.
- TTL, inactividad, reautenticación reciente y renovación se aprueban por clase de operación; no se fija TTL universal aquí.
- Para interfaz web: cookies HttpOnly y Secure, SameSite apropiado, protección CSRF y TLS. Una consola local no expone sesión por red implícitamente.

Primer incremento recomendado: sesión opaca con expiración y revocación explícitas, sin refresh-token separado hasta justificar su necesidad.

## 7. Bootstrap del primer usuario

El bootstrap es separado del login y solo existe cuando la instalación está en estado inicial.

Precondiciones:
- no existe el usuario administrador inicial;
- estado de bootstrap INITIAL y no consumido;
- prueba one-shot generada fuera de la imagen y entregada por canal controlado;
- prueba vigente y digest coincidente;
- ninguna operación concurrente ha reservado el bootstrap.

Secuencia:
1. Reservar consumo con operación atómica e idempotente.
2. Crear Identity(USER) y UserId mediante Identity Authority.
3. Crear subject nativo y autenticador inicial mediante Authentication Authority.
4. Crear binding exacto del issuer nativo mediante Identity Authority.
5. Asignar privilegios iniciales solo mediante procedimiento explícito aprobado por CAM.
6. Consumir irreversiblemente la prueba y cerrar bootstrap.
7. Registrar evidencia mínima y resultado correlacionado.

La creación de UserId, Identity(USER), autenticador y binding debe ser atómica dentro de la misma UoW cuando compartan la misma base local. Si los límites de autoridad impiden una transacción única, se requiere saga durable con estado PENDING/COMMITTED/UNRESOLVED, idempotencia y reconciliación. Nunca dejar una cuenta autenticable sin binding canónico ni un binding sin autenticador usable.

El bootstrap no usa getuser(), UID/GID, hostname, IP, hardware o rutas; no usa contraseña universal; no depende de variable de entorno permanente; no se reinicia por borrar una tabla, restaurar archivo o recrear contenedor; no ofrece ruta implícita para crear otro primer administrador.

La generación, entrega, expiración, digest, consumo y auditoría requieren contrato de bootstrap específico antes de implementar.

## 8. Cambios de estado e invalidación

| Evento | Efecto mínimo |
|---|---|
| Cambio de contraseña | Incrementar credential_revision e invalidar sesiones/pruebas previas según política |
| Suspender autenticador | Bloquear nuevos logins e invalidar sesiones dependientes |
| Revocar autenticador | Estado terminal; invalidar sesiones y conservar tombstone/subject binding |
| Suspender/revocar Identity | Identity Authority y Consistency invalidan contextos/admisiones |
| Revocar binding | Bloquear autenticación por ese binding y coordinar fencing |
| Cambio de issuer/realm trust | Incrementar revisión; pruebas/contextos anteriores no se aceptan |
| Expirar sesión | No renovar por simple presencia; requerir flujo aprobado |

Authentication Authority es propietaria del autenticador y sesión. Identity Authority es propietaria del binding e identidad. Consistency coordina invalidación, no escribe directamente los agregados de esas autoridades.

Si Consistency no confirma fencing requerido, la operación queda BLOCKED/UNRESOLVED y no se declara completada para fines protegidos.

## 9. Recuperación

La recuperación de cuenta continúa DESHABILITADA conforme a B1-B-03C.

No son prueba suficiente por sí solos: email, teléfono, nombre, datos de perfil, UserId, identity_id, subject, login handle, sesión antigua, conocimiento de datos privados, acceso al host/cuenta Linux o afirmación de un agente/administrador sin política aprobada.

No se elimina el último método utilizable sin política de recuperación aprobada. El primer incremento no ofrece unlink de la única credencial nativa ni reset administrativo que eluda recuperación.

## 10. Separación entre nodo, instalación y realm

- El nodo/runtime tiene identidad técnica propia.
- La instalación tiene identificador técnico propio para configuración y auditoría.
- El realm/issuer nativo representa la autoridad lógica que emite y verifica cuentas.
- UserId e Identity(USER) representan a la persona dentro de Atlas.
- Ninguno de esos identificadores concede permisos.

Una transferencia autorizada de la misma instalación puede conservar realm, bindings e identidades según el procedimiento de migración aprobado. Una instalación independiente requiere realm y secretos nuevos; no puede apropiarse de UserId o bindings existentes copiando una imagen.

Una futura arquitectura multi-nodo podrá compartir Authentication Authority e Identity Authority mediante servicio común o almacenamiento transaccional compatible. Este diseño no autoriza varias instancias escribiendo SQLite ni sesiones active-active.

## 11. Puertos conceptuales

Nombres ilustrativos, no API aprobada.

**Authentication Authority**
- authenticate(login_handle, password, request_metadata) → VerifiedNativeAuthenticationProof o Denied;
- create_initial_authenticator(bootstrap_reservation, ...) → NativeAuthenticatorRef;
- create_session(proof, policy) → SessionToken;
- resolve_session(token) → AuthenticatedSession o Denied;
- revoke_session(session_id, reason) → RevocationResult;
- change_password(authenticated_context, old_password, new_password) → CredentialChangeResult;
- suspend_authenticator(authenticator_id, expected_revision) → Result;
- revoke_authenticator(authenticator_id, expected_revision) → Result.

No exponer operación pública que acepte UserId y devuelva una prueba autenticada.

**Identity Authority**
- resolve_native_proof(proof) → VerifiedIdentityContext;
- create_user_identity_and_native_binding(...) solo en bootstrap autorizado y con UoW/saga definida.

Identity Authority no valida contraseñas ni administra hashes.

**Trusted Console/API boundary**
- autentica sesión;
- obtiene contexto verificado desde Identity Authority;
- resuelve proyecto/entorno/workspace desde registros confiables;
- construye OperationContext inmutable;
- no acepta UserId, identity_id, issuer, subject, binding ni estado de autenticación del caller como autoridad.

## 12. Pruebas de conformidad

**Credenciales:** contraseña válida/inválida; cuenta inexistente sin enumeración observable; Argon2id con salt/parámetros versionados; hash corrupto o versión desconocida; throttling; handle duplicado; cambio de handle sin cambio de identidad; cambio de contraseña y revisión monotónica.

**Proof y binding:** proof falsificado, expirado, repetido o de otro realm; subject no vinculado; binding revocado/reservado; issuer suspendido/revocado; revisión obsoleta; Identity no USER/inactiva; UserId/identity_id no correspondientes; caller que suministra UserId/subject/binding; Identity Authority indisponible.

**Sesiones:** token alterado/desconocido/expirado; digest almacenado; ausencia de token en DB/logs; revocación/rotación atómicas; replay del token anterior; cambio de contraseña/autenticador/Identity; sesión usada por actor USER distinto; restore anterior a revocación no reabre sesión.

**Bootstrap:** token one-shot válido/expirado/incorrecto/repetido; dos bootstraps concurrentes; fallo parcial en cada paso; reinicio tras reserva; bootstrap cerrado; ausencia de dependencia de Linux; privilegios iniciales explícitos y auditados.

**Integración:** proof → Identity Authority → VerifiedIdentityContext → OperationContext confiable → CAM; sesión válida sin Grant produce DENY; contexto sintético o UserId del caller produce DENY; actor no USER sin identidad/delegación propia produce DENY; ausencia de secretos en logs, journal, DB y exportaciones legibles.

## 13. Bloqueos antes de implementar

1. Aprobar contrato del issuer nativo y su relación con identity_issuers/identity_bindings.
2. Definir formalmente VerifiedNativeAuthenticationProof y protección contra construcción/replay fuera de Authentication Authority.
3. Seleccionar librería Argon2id, parámetros iniciales y actualización mediante benchmark/revisión.
4. Aprobar normalización, unicidad y protección del login handle.
5. Aprobar contrato físico de credenciales, sesiones y bootstrap, y propiedad de datos.
6. Determinar atomicidad bootstrap entre Authentication Authority e Identity Authority.
7. Definir límites de intentos, TTL, rotación, reautenticación reciente y revocación/fencing.
8. Verificar compatibilidad con código real y baseline exacto antes de migraciones o implementación.

## 14. Orden de trabajo recomendado

1. Revisión de compatibilidad de B1-B-03A/B/C/D con esta propuesta y registro de discrepancias.
2. Aprobar contrato del issuer nativo y VerifiedNativeAuthenticationProof.
3. Diseñar puertos y modelos de Authentication Authority sin modificar contratos legacy.
4. Diseñar almacenamiento y UoW de credenciales/sesiones/bootstrap.
5. Definir frontera confiable de consola que convierte sesión verificada en VerifiedIdentityContext y OperationContext.
6. Reanudar Cycle 3.2: proyecto, entorno y workspace confiables, manteniendo fail-closed.
7. Implementar en ramas aisladas con pruebas; no activar autenticación operativa hasta cerrar gates.

**Conclusión:** esta propuesta integra autenticación nativa con las autoridades y evidencia ya definidas. No introduce identidad paralela ni concede permisos por autenticación. Permanece pendiente de revisión y aprobación; no autoriza código, migraciones, bootstrap operativo ni cambios de host.
