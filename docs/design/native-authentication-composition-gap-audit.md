# Auditoría de brecha: composición de autenticación nativa

**Fecha:** 2026-11-22  
**Rama revisada:** `work/atlas-mvp-runtime`  
**HEAD de código validado por el propietario:** `29e900a1129efbb83c8e4b867c99d37d66473c55`  
**Estado:** revisión estática completada; no implementa ni autoriza login operativo.  
**Alcance:** identificar qué piezas existen, qué puntos de composición las conectan (o no) y qué decisiones faltan antes de exponer autenticación al runtime.

## 1. Conclusión

El guard de intentos y el servicio de autenticación nativa están implementados y la suite completa de la rama fue validada localmente por el propietario. Sin embargo, **no existe una composición operativa de login**.

La implementación actual es una capacidad de aplicación/persistencia aislada. No se debe conectar a la consola cotidiana ni a Workspace hasta cerrar la cadena de bootstrap, consumo del proof, identidad USER verificada y autorización CAM. La identidad sintética que produce la consola no puede sustituir esa cadena.

## 2. Piezas verificadas en GitHub

| Componente | Evidencia revisada | Alcance actual |
|---|---|---|
| Servicio de autenticación | `src/atlas/authentication/service.py` | `NativeAuthenticationService` verifica credenciales, reserva intentos, revalida autoridad y persiste un proof de un solo uso. No es un endpoint ni un entrypoint de login. |
| Guard SQLite | `src/atlas/adapters/sqlite/authentication_attempt_guard.py` | `SQLiteAuthenticationAttemptGuard` ejecuta transacciones `BEGIN IMMEDIATE` independientes sobre una instancia `SQLiteDatabase`. |
| Migración | `src/atlas/adapters/sqlite/authentication_attempt_migration.py`, `migrations.py` | V28 crea tablas e índices de reservas/fallos y está registrada en `SQLITE_MIGRATIONS`. |
| UoW de autoridad | `src/atlas/adapters/sqlite/local_authority_unit_of_work.py` | Expone repositorios `native_identity` y `native_authentication` sobre una UoW compartida. |
| Composición de almacenamiento | `src/atlas/adapters/sqlite/authority_storage_composition.py` | Vincula una instancia `SQLiteDatabase` con `SQLiteLocalAuthorityUnitOfWorkFactory`; no crea directorios, no inicializa ni migra la base y no compone el servicio de autenticación. |
| Consola | `src/atlas/cli.py` | Compone conversación, proveedor Ollama y planificación F1. No instancia `NativeAuthenticationService` ni el guard. |
| Bootstrap de aplicación | `src/atlas/bootstrap.py` | Construye el planificador; no compone autenticación. |

La revisión cubrió los puntos de composición de consola, bootstrap y almacenamiento de autoridad mencionados arriba. No se encontró una ruta de login conectada a la consola en esos puntos.

## 3. Frontera transaccional que debe preservar una futura composición

La composición futura debe construir **una sola instancia canónica** de `SQLiteDatabase` y derivar de ella tanto:

- `SQLiteLocalAuthorityUnitOfWorkFactory(database)`, para que el servicio lea issuer/autenticador y persista proofs mediante los repositorios nativos;
- `SQLiteAuthenticationAttemptGuard(database)`, para que cada reserva/finalización use el mismo archivo SQLite canónico en una transacción corta e independiente.

No se debe crear accidentalmente un segundo archivo para el guard ni pasar una base distinta a cada dependencia. La identidad del objeto de base de datos debe comprobarse en el composition root, además de verificar la ruta canónica.

La composición de almacenamiento no aplica migraciones. La inicialización y aplicación de `SQLITE_MIGRATIONS` deben permanecer en un procedimiento explícito de provisión/administración; no deben introducirse como efecto lateral del arranque cotidiano de la consola.

Se mantienen las reglas aprobadas:

1. Resolver issuer en una UoW breve.
2. Reservar el intento antes de consultar el autenticador.
3. Ejecutar Argon2id fuera de UoW y de transacciones SQLite de escritura.
4. Releer issuer, autenticador, estado, subject y `credential_revision` antes de persistir el proof.
5. No devolver la referencia raw si no se confirma la finalización exitosa del guard.
6. Abandono/expiración no suma un fallo; la reserva conserva su TTL acotado.

## 4. La autenticación no termina al emitir un proof

El proof emitido por `NativeAuthenticationService` es una evidencia intermedia, opaca, de un solo uso y ligada a una audience. No es por sí solo un `VerifiedIdentityContext`, un `OperationContext` ni un Grant CAM.

La cadena posterior documentada debe mantenerse separada:

1. Admitir/consumir el proof exactamente una vez y para la audience esperada.
2. Resolver el binding nativo issuer/subject hacia la identidad canónica USER.
3. Revalidar estado y revisiones de identidad.
4. Construir un `VerifiedIdentityContext` efímero mediante la frontera de identidad verificada.
5. Derivar un `OperationContext` para una operación concreta.
6. Evaluar un Grant CAM exacto para el recurso, acción y scope solicitados.
7. Reconciliar los consumidores protegidos (I-3) antes de permitir que usen ese contexto.

El diseño `docs/design/native-proof-to-verified-operation-context-integration.md` sigue siendo una propuesta de integración; no autoriza a omitir etapas ni a conectar consumidores legacy.

## 5. Decisiones y dependencias pendientes

### 5.1 Bootstrap y Grant CAM inicial del propietario

El bootstrap de propietario no debe crear un Grant global ni inventar Project, Environment o Workspace. Antes de implementarlo hay que decidir expresamente el perfil CAM inicial: sujeto, recursos, acciones, scope, duración, renovación/revocación y límites de uso. No se deducen permisos a partir de que el actor sea el propietario ni de que el bootstrap sea local.

El contrato de Memory mantiene pendiente la evidencia técnica de acción directa del propietario para decisiones no delegables. El diseño de bootstrap LOCAL propone autenticación interactiva reciente mediante PAM y confirmación vinculada al descriptor, pero el protocolo de desafío/prueba todavía contiene decisiones técnicas pendientes y no está implementado.

### 5.2 Clave HMAC para identidad verificada

`HmacVerifiedIdentityContextAttestor` recibe una clave de al menos 256 bits por constructor. El código exige que la composición entregue esa clave; no define su procedencia, carga, permisos, rotación ni recuperación. Esas responsabilidades pertenecen a una fuente/proveedor confiable fuera de SQLite y fuera de entradas del caller.

No reutilizar por inferencia la clave del firmante de consistencia local: son usos y contratos distintos. Antes de componer el attestor deben fijarse la fuente de secreto, la referencia de clave, el propietario/permisos, la rotación y el comportamiento fail-closed cuando no esté disponible.

### 5.3 Otras dependencias

- La admisión/consumo del proof debe seguir siendo one-shot y audience-bound.
- La construcción de contexto USER debe revalidar autoridad; un proof válido no concede permisos CAM.
- La consola sintética actual permanece fuera de toda capacidad protegida.
- No habilitar Workspace read-only hasta completar identidad, bootstrap, Grant CAM e I-3.

## 6. Próximo incremento recomendado

**No implementar todavía un login de producción.** El siguiente trabajo debe ser una revisión/decisión explícita de:

1. perfil CAM mínimo del Grant inicial del propietario;
2. fuente y ciclo de vida de la clave HMAC del attestor de identidad verificada;
3. contrato final del desafío y prueba de acción directa del propietario para bootstrap LOCAL.

Una vez resueltas esas decisiones, se puede diseñar una composición autenticada aislada, sin conectarla inicialmente a la consola ni a Workspace. La implementación debe incluir pruebas de que UoW y guard usan la misma base canónica, que las migraciones se ejecutan solo mediante provisión explícita, que un proof no consumido no crea contexto USER y que cualquier fallo de guard/attestor/identidad deniega.

## 7. Validación y límites

El propietario confirmó en Debian 13 / `Atlas-VM-test`:

```text
Ran 1611 tests in 40.322s

OK (skipped=1)
```

También confirmó `.venv/bin/python -m compileall -q src tests` sin errores reportados. Esta evidencia valida la suite unitaria de la rama, no una migración sobre una base persistente real, un login desplegado, el bootstrap de propietario, el consumo E2E del proof ni Workspace/CAM.

No se ejecutaron pruebas, compilaciones, migraciones ni workflows desde GitHub. No se modificó código ejecutable, `main`, el host ni una base real.


## 8. Revisión ampliada: bootstrap, claves y frontera de privilegios

### 8.1 Separación de génesis y provisión inicial

El contrato `initial-owner-authority-provisioning-contract.md` propone dos operaciones no delegables:

- **A — génesis:** crea la identidad canónica USER y el binding sujeto local → propietario. No crea Project, Environment ni Grant.
- **B — provisión:** requiere una nueva reautenticación y confirmación directa, y crea un Project, Environment y primer Grant con scope exacto. La prueba A no se reutiliza.

La separación es correcta como diseño propuesto, pero el contrato sigue marcado **no aprobado para implementación**. La lista exacta de recursos, tipos, acciones, IDs, expiración y sujeto destinatario del primer Grant no está decidida. No existe permiso implícito por ser el primer usuario o el propietario.

**Corrección de consistencia normativa:** el borrador de provisión decía que Identity Authority generaría UUIDv4 para ambos IDs. B1-B-03A §3.3 deja pendiente el formato y mecanismo de generación de UserId. El borrador se corrigió para no fijar UUIDv4 para UserId por inferencia.

### 8.2 Project/Environment: actualización del hallazgo físico

La auditoría anterior citaba el esquema V9, donde Project y Environment se creaban como tablas separadas. La revisión del HEAD actual confirma que V18 añadió `atlas_project_environments` con claves foráneas a Project y Environment, clave primaria compuesta y una referencia compuesta desde `atlas_workspaces`. `SQLiteLocalAuthorityUnitOfWork` expone un lector de asociaciones.

Esto corrige el hallazgo histórico de que no existía ninguna relación canónica. No demuestra que el bootstrap pueda crear esa asociación de forma autorizada: el repositorio expuesto en la UoW es de lectura; la escritura corresponde al lifecycle específico. El flujo B debe usar esa capacidad y coordinarla con Project, Environment, Grant, evidencia y journal.

### 8.3 Atomicidad real disponible

La UoW actual incluye Identity, Native Identity, Native Authentication, Project/Environment, asociaciones Project–Environment, Workspace y Grants, compartiendo una instancia SQLite. La composición `SQLiteLocalAuthorityStorageComposition` verifica que la fábrica UoW usa exactamente la misma instancia `SQLiteDatabase`.

No se encontró en esa UoW la composición del `SQLiteConsistencyJournal`, Recovery Gate ni un repositorio de bootstrap_binding_id para el sujeto local. Por tanto, no está demostrado el commit atómico exigido para consumir la prueba PAM, crear UserId/Identity, persistir binding, registrar DOMAIN_BOOTSTRAPPED, actualizar head/proyección/gate y dejar la autoridad en estado coherente. No se debe presentar la UoW actual como solución completa de génesis.

### 8.4 PAM y frontera privilegiada

El diseño aprobado selecciona un helper C separado con libpam como proveedor local candidato y a `greed` como sujeto operativo inicial. Esto no aprueba la invocación privilegiada ni instala el helper.

- El servicio PAM dedicado `atlas-bootstrap` no existe todavía; no se debe modificar el stack PAM general.
- La política exacta de `pam_faillock` y sus valores sigue pendiente.
- La alternativa A (helper root-owned invocado mediante sudo) es preferida, pero no aprobada. El contrato de validación V3 está implementado como observador diagnóstico y sigue pendiente de validación local; sus resultados no son autorización.
- La alternativa B (servicio root con socket y SO_PEERCRED/SCM_RIGHTS) permanece como reserva, no seleccionada.
- setuid/capabilities y privilegios generales del runtime están rechazados.
- El diseño permite SSH interactivo con PTY, pero un PTY no prueba presencia física; SSH sin PTY y ejecución no interactiva deben rechazarse.

El siguiente paso de esta rama no debe ser escribir el helper. Primero debe cerrarse el contrato de invocación/TTY y el estado pendiente de V3 con evidencia local; después el propietario debe aprobar expresamente la implementación privilegiada.

### 8.5 Claves: dos usos HMAC que no deben confundirse

Se revisaron `me-03k-local-key-custody-design.md` y `HmacVerifiedIdentityContextAttestor`.

- ME-03K implementa una ruta de custodia de clave HMAC de 32 bytes mediante systemd credentials para firmar/verificar envelopes de Local Consistency. El documento aún declara no provisionadas las credenciales reales ni activada la unidad systemd.
- `HmacVerifiedIdentityContextAttestor` recibe directamente bytes de clave de al menos 256 bits en su constructor. No carga secretos ni decide referencias, rotación o custodia.
- No existe una composición productiva del attestor con un proveedor secreto. Tampoco debe reutilizarse la clave de Consistency: dominio, propósito, autoridad y ciclo de vida son distintos.

La infraestructura de systemd credentials podría evaluarse como mecanismo de entrega de un secreto distinto, con referencia y política independientes; eso sería una decisión nueva y requeriría permisos, rotación, fail-closed y pruebas propias. No equivale a que la provisión de la clave del attestor esté resuelta.

### 8.6 Consumidores I-3: evidencia y carreras

Se inspeccionaron los servicios actuales, no solo el documento histórico de I-3:

| Consumidor | Resultado estático | Consecuencia |
|---|---|---|
| `GrantRenewalService.request_renewal` | Exige contextos verificados de AGENT y delegación y los revalida dentro de la UoW; aprobación/rechazo del propietario también usa verificación dentro de UoW. | Mejor alineado con la frontera de evidencia; no implica que AGENT esté habilitado en runtime ni que el ciclo entero esté cerrado. |
| `GrantManagementService.issue` | `require_verified_owner_context` llama a `verifier.verify()` antes de abrir la UoW de inserción del Grant. | Existe una ventana TOCTOU entre revalidar identidad y escribir el Grant. Antes de uso operativo debe revalidarse dentro de la misma UoW de mutación o demostrarse un fencing equivalente. |
| `GrantManagementService.revoke` | La evidencia del propietario se verifica antes de iniciar la coordinación de revocación. | La autenticidad de la solicitud no sustituye el fencing de Identity/Grant/Consistency; mantener la ruta bloqueada si no puede cerrarse la carrera. |
| `MemoryAuthorizationService` | Usa el binding legacy `AuthenticatedUserSubject`; no recibe ni verifica `VerifiedIdentityContext`. | No habilitar Memory protegido desde un contexto sintético o nativo por inferencia. |
| `WorkspaceCapabilityExecutionService` | Comprueba actor USER, busca identidad canónica y evalúa Grant dentro de `BEGIN IMMEDIATE`, pero solo recibe `OperationContext`; no recibe/verifica `VerifiedIdentityContext`. | La UoW protege cambios SQLite concurrentes, pero no autentica al caller. Un contexto fabricado puede pasar la comprobación canónica. Mantener Workspace desconectado. |
| `LocalConsoleRequestFactory` | Construye `Identity` y `user_id` sintéticos desde el usuario Unix. | No puede ser fuente de identidad ni alcanzar ningún consumidor protegido. |

El servicio Workspace mantiene checks útiles de workspace ACTIVE, propietario, Project/Environment, asociación V18, Grant exacto y mount registrado. Esos checks no sustituyen la evidencia de identidad. Tampoco se debe afirmar que `BEGIN IMMEDIATE` ofrece fencing distribuido o de filesystem.

### 8.7 Estado documental reconciliado

Se corrigieron las siguientes contradicciones de documentos heredados:

- El protocolo PAM ya no declara como pendiente un emisor separado de desafíos: la arquitectura posterior establece que el helper emite la prueba y CAM comprueba el estado pendiente.
- El borrador de provisión inicial ya no fija UUIDv4 para UserId contra B1-B-03A §3.3.
- El contrato I-2 ahora refleja que el guard SQLite V28 existe y fue validado en la suite local, aunque no está compuesto en login operativo.
- El contrato de provisión inicial refleja la asociación Project–Environment V18, sin declarar resuelta su provisión ni la atomicidad global.



### 8.8 Provisión real de Project/Environment y primer Grant

La inspección adicional de `ProjectEnvironmentLifecycleService`, su composición y los adaptadores SQLite precisa el estado:

- V18 ya persiste la asociación Project–Environment con claves foráneas.
- `SQLiteProjectEnvironmentAssociationRepository` expone lectura, no creación.
- `SQLiteProjectEnvironmentLifecycleAssociationWriter` expone actualización CAS de una asociación existente; no crea la asociación inicial.
- `ProjectEnvironmentLifecycleService.transition` cambia estado de una asociación existente, requiere `VerifiedIdentityContext` revalidado dentro de la UoW y un Platform Admin Grant activo. No es el flujo de bootstrap del primer Project/Environment.
- `GrantManagementService.issue` emite Grants ordinarios con identidad USER verificada, pero no consume `InitialAuthorityProvisioningEvidence` ni crea Project/Environment/association. Su verificación de identidad ocurre antes de la UoW de inserción.

Por tanto, la Operación B del contrato de provisión inicial aún no tiene un application service que coordine de forma autorizada la creación de Project, Environment, asociación y primer Grant. No se debe improvisar una secuencia de llamadas a repositorios ni reutilizar el lifecycle de Platform Admin como sustituto del bootstrap CAM. Se necesita un servicio específico que consuma evidencia excepcional de provisión, aplique las restricciones CAM y persista el conjunto con atomicidad/idempotencia demostradas.

## 9. Orden de cierre recomendado

No hay una única tarea de código que cierre todo. El orden seguro es:

1. **Decisión CAM B:** definir el descriptor mínimo del primer Project, Environment, Workspace (si se incluye), recurso, acciones, sujeto y expiración. Mantener separadas génesis A y provisión B.
2. **Decisión de clave I-2:** aprobar proveedor de secreto independiente para el attestor HMAC, referencia, permisos, rotación y recuperación. No reutilizar la clave ME-03K.
3. **Cierre de protocolo PAM:** terminar layout binario/vectores, firma Ed25519 y límites, key_id, expiración/skew, binding protegido y prueba de consumo/replay.
4. **Cierre de privilegios:** validar V3 en Debian, decidir A/B con pruebas negativas y obtener aprobación explícita antes de cualquier helper privilegiado/PAM.
5. **Diseño de transacción de génesis:** incorporar binding de bootstrap, consumo one-shot, Identity, Native Identity/Authentication, evento/journal y Recovery Gate en una UoW real o diseñar una saga durable fail-closed. No aceptar la UoW actual como si ya lo hiciera.
6. **Cierre de I-3:** corregir la verificación fuera de UoW de `GrantManagementService.issue/revoke`, exigir evidencia en Workspace y Memory, y demostrar invalidación/fencing. Mantener todos los consumidores sin wiring operativo hasta cerrar sus contratos.
7. **Composition root aislado:** solo después de lo anterior, componer Authentication Authority, guard V28, attestor, Identity Authority y CAM sobre recursos canónicos. La provisión de schema debe seguir siendo explícita y administrativa.
8. **Validación local y gate:** pruebas focalizadas, fallos/concurrencia/replay/rollback, migración sobre DB temporal persistente, suite completa y compileall en Debian. No activar login ni Workspace hasta un gate de seguridad explícito.

## 10. Evidencia y límites de esta revisión

Esta revisión fue estática sobre archivos de la rama `work/atlas-mvp-runtime` en GitHub. No se ejecutaron pruebas, compilaciones, migraciones, PAM, comandos del host ni cambios de servicios. Los hallazgos describen el código y los contratos revisados; no constituyen autorización para desplegar, inicializar CAM ni cambiar el host.
