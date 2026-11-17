# Contrato propuesto de provisión inicial de autoridad del propietario

**Estado:** propuesta de diseño para revisión; no aprobado para implementación.  
**Ámbito:** bootstrap LOCAL, identidad canónica inicial y primera provisión explícita de Project, Environment y CAM Grant.  
**Dependencias:** `ME-D4O-A-authenticated-domain-bootstrap.md`, `local-bootstrap-privilege-boundary.md`, `local-bootstrap-privilege-validation-contract.md`, `local-pam-bootstrap-authenticator.md`, `local-pam-bootstrap-proof-protocol.md`, `docs/contracts/memory.md` §8 y contratos CAM vigentes.  
**Restricción:** este documento no autoriza cambios de host, PAM, sudoers, systemd, usuarios, base de datos productiva, migraciones ni runtime.

## 1. Decisión propuesta

El bootstrap LOCAL se compone de dos operaciones administrativas distintas y no delegables:

1. **Génesis del propietario:** establece la primera identidad canónica y el binding verificable con el sujeto local autenticado. No crea Projects, Environments ni Grants.
2. **Provisión inicial de autoridad:** una acción posterior, explícita y autenticada del propietario crea un Project y un Environment concretos y emite el primer Grant CAM con scope y acciones concretos.

La separación es normativa. La existencia de una identidad, de un binding local o de un dominio LOCAL no implica autorización para crear recursos ni para conceder permisos.

La segunda operación no se autoriza mediante un Grant previo: se autoriza mediante una evidencia excepcional de acción directa del propietario, emitida por la frontera local de bootstrap aprobada y verificada por un componente independiente del caller. Esta evidencia es una autoridad de bootstrap limitada a una sola operación, no un Grant CAM general ni una regla permanente de autorización.

## 2. Invariantes

- No existe propietario canónico hasta que la autoridad de identidad haya creado el par `UserId` / `Identity(USER)`.
- El nombre Unix, UID, grupo, proceso de servicio, usuario del Broker, variable de entorno o sesión abierta no son por sí solos una identidad Atlas ni prueba de propiedad.
- El sujeto local debe estar cualificado por el dominio/host de autenticación y vinculado mediante configuración protegida al propietario canónico.
- El proceso técnico `atlas`, `atlas-sandbox`, Assistant, Skills y servicios no adquieren la autoridad del operador.
- Génesis no crea un Project, Environment, Workspace ni Grant.
- Provisión inicial no puede crear un Grant global, wildcard, sin expiración o con IDs de recurso vacíos.
- Un Grant inicial solo puede referirse al propietario canónico ya establecido, a un Project y Environment concretos, a un tipo de recurso y a IDs concretos, a acciones explícitas y a una expiración.
- La evidencia de acción directa no puede ser construida, modificada, reusada ni declarada verificada por el caller.
- El procedimiento debe ser idempotente para el mismo request y descriptor; una solicitud distinta o una prueba consumida produce conflicto/rechazo.
- Cualquier ambigüedad, discrepancia de binding, fallo de verificación, error de persistencia o imposibilidad de garantizar atomicidad mantiene el gate cerrado.
- No se permite que la recuperación de un backup convierta un estado anterior en una autoridad vigente ni que reabra el gate sin reconciliación requerida.

## 3. Operación A — génesis del propietario

### 3.1 Entrada comprometida

La solicitud de génesis debe comprometer de forma canónica y versionada, como mínimo:

- `request_id` y nonce únicos;
- `consistency_domain_id`, época inicial y perfil LOCAL;
- versión de política de confianza y versión de esquema/reducer;
- sujeto autenticado cualificado (dominio/host + identificador estable);
- referencia/versionado del binding protegido sujeto-local → propietario;
- descriptor exacto y commitment de génesis;
- acción permitida, emisor, clave y vigencia de la prueba.

No se aceptan campos desconocidos, defaults implícitos ni normalizaciones dependientes de plataforma.

### 3.2 Secuencia lógica

1. El procedimiento interactivo presenta el descriptor exacto.
2. El helper PAM aprobado autentica recientemente al sujeto configurado y comprueba autenticación y estado de cuenta; la confirmación directa se liga al descriptor.
3. El helper emite una prueba tipada, de un solo uso, ligada al request, sujeto, host, acción y descriptor.
4. Un verificador confiable valida firma/emisor, host, sujeto, binding protegido, descriptor, acción, vigencia, nonce y no-replay.
5. La autoridad canónica genera los UUIDv4 de `UserId` e `Identity(USER)`; nunca se derivan del nombre Unix ni de su UID.
6. Se registra el binding de propietario con procedencia y revisión.
7. Se registra el evento de génesis y se actualizan head y Recovery Gate.
8. Se consume la prueba dentro de la misma frontera transaccional que los cambios de génesis.
9. El gate solo puede quedar abierto para el perfil LOCAL después de verificar el evento, su proyección y todos los invariantes de recuperación.

### 3.3 Resultado

La operación establece una identidad de propietario y su binding local verificable. No concede permisos CAM y no habilita por sí sola operaciones de memoria, Projects, Environments o recursos.

Si una transacción atómica entre consumo de prueba, identidad, binding, journal y gate no puede implementarse y demostrarse, la operación no se implementa como una secuencia de escrituras independientes. Se debe diseñar un protocolo recuperable con estados intermedios fail-closed, idempotencia y reconciliación; no se simula atomicidad.

## 4. Operación B — provisión inicial de autoridad

### 4.1 Por qué no requiere un Grant previo

La provisión inicial ocurre antes de que exista un Grant CAM. Por tanto, no debe fingirse una evaluación CAM ordinaria que no puede producir un permiso válido.

La propuesta define una capacidad de bootstrap excepcional, denominada conceptualmente `InitialAuthorityProvisioningEvidence`. No es una nueva clase de Grant ni un permiso implícito. Es evidencia verificable de una decisión directa del propietario, con uso único, que autoriza exclusivamente la creación del conjunto inicial de recursos descrito en la propia evidencia.

Su verificador debe estar fuera del control del caller y no aceptar un booleano, enum o resultado `VERIFIED` fabricado por el proceso que solicita la provisión.

### 4.2 Decisión directa y descriptor de provisión

La segunda operación exige una nueva interacción autenticada del propietario. No hereda automáticamente la confirmación de génesis ni reutiliza la prueba consumida en la operación A.

Antes de confirmar, el procedimiento presenta una vista canónica y legible de:

- propietario canónico destinatario;
- `project_id` exacto y estado inicial;
- `environment_id` exacto y estado inicial;
- relación Project–Environment que se pretende establecer;
- `grant_id` o identificador de operación;
- `resource_type` y conjunto no vacío de IDs concretos;
- conjunto explícito de acciones;
- `issued_at` y `expires_at`;
- identidad sujeto destinataria del Grant;
- política y versión de canonicalización.

La confirmación se vincula criptográficamente al commitment de todos esos campos. Cambiar cualquier campo requiere una nueva confirmación y nueva prueba.

### 4.3 Restricciones del primer Grant

El primer Grant debe satisfacer todas las validaciones ordinarias del modelo CAM y además:

- `owner_user_id` corresponde al UserId canónico creado en A;
- `subject_identity_id` corresponde a la identidad activa seleccionada explícitamente;
- `project_id` y `environment` identifican los recursos concretos recién provisionados;
- `resource_type` es explícito;
- `resource_ids` es un conjunto no vacío de IDs concretos;
- `actions` es un conjunto no vacío de acciones explícitas, sin wildcard;
- `issued_at < expires_at`, con expiración obligatoria;
- el Grant no incluye delegación ni facultad de emitir Grants, salvo que una capacidad específica y futura se diseñe y apruebe por separado;
- el Grant no autoriza automáticamente todos los recursos presentes o futuros del Project;
- el Grant no se extiende a otros Projects, Environments, propietarios o identidades.

La lista exacta de acciones iniciales, tipos de recurso, IDs y duración no se fijan aquí. Deben formar parte de la decisión directa del propietario y de una matriz CAM aprobada; no se rellenan con valores predeterminados amplios.

### 4.4 Secuencia lógica

1. Resolver y verificar el propietario canónico y su binding activo.
2. Presentar el descriptor exacto de provisión.
3. Obtener reautenticación reciente y confirmación directa del propietario mediante el procedimiento local aprobado.
4. Emitir una prueba de un solo uso ligada a la operación B y al commitment exacto.
5. Verificar la prueba y comprobar que el dominio LOCAL y la génesis están válidos.
6. Comprobar que no existe una provisión inicial incompatible ni un resultado previo con descriptor distinto.
7. Crear Project y Environment explícitos.
8. Crear el Grant inicial usando el modelo y las validaciones CAM ordinarias.
9. Registrar el evento de provisión, su evidencia no sensible y el resultado.
10. Consumir la prueba y confirmar los cambios como una única operación lógica atómica.
11. Releer los registros canónicos y validar que el Grant evalúa únicamente para el scope solicitado.

Un reintento idéntico debe devolver el resultado ya confirmado sin crear otro Grant ni duplicar recursos. Un descriptor diferente, una prueba expirada o consumida, un Grant preexistente conflictivo o un fallo parcial debe rechazarse y dejar la autoridad en estado cerrado/no provisionado hasta reconciliación.

## 5. Relación con CAM y evaluación ordinaria

La evidencia excepcional solo autoriza el acto de provisión inicial descrito. No puede utilizarse como contexto de autorización para lecturas/escrituras ordinarias ni como sustituto de Grants posteriores.

Una vez confirmado el Grant inicial, las operaciones ordinarias siguen pasando por CAM y por el evaluador vigente. Deben coincidir, como mínimo:

- identidad activa del actor;
- propietario del recurso;
- Project y Environment del contexto;
- tipo e ID concreto del recurso;
- acción explícita;
- ventana de vigencia;
- estado no revocado del Grant.

La regla de no delegabilidad de decisiones del propietario (incluidas aprobación/rechazo de memoria) prevalece aunque el Grant contenga identificadores de acción relacionados. La provisión inicial no concede facultades para aprobar/rechazar memorias en nombre del propietario.

## 6. Atomicidad y composición de autoridades

### 6.1 Estado observado

La implementación actual contiene piezas reutilizables:

- `SQLiteIdentityAuthority` es el emisor canónico de UserId e Identity(USER), pero declara expresamente que no autentica, vincula sujetos ni autoriza.
- `SQLiteProjectEnvironmentRepository` persiste Project y Environment con revisiones, pero es un repositorio de metadatos y no impone por sí solo propiedad ni autorización.
- `SQLiteGrantRepository` persiste Grants y revisiones; el evaluador CAM compara el contexto con el Grant concreto.
- `SQLiteLocalAuthorityUnitOfWork` comparte una transacción SQLite entre Identity, Project/Environment y las autoridades incluidas en su composición; hereda Grants/Renewals de la UoW de autorización.
- `SQLiteConsistencyJournal` tiene actualmente su propio ciclo transaccional. El método `create_local_domain` no implementa el evento autenticado `DOMAIN_BOOTSTRAPPED` ni prueba por sí mismo que identidad, binding, journal y gate se confirmen en una única transacción.

### 6.2 Consecuencia

No se puede afirmar hoy que génesis o provisión inicial sean atómicas de extremo a extremo. Antes de implementación debe diseñarse y probarse una frontera de coordinación que incluya las escrituras necesarias o un protocolo de saga estrictamente fail-closed con outbox/receipts, idempotencia y reconciliación verificable.

No se debe extender artificialmente la UoW actual ni describirla como coordinador de consistencia/fencing. Tampoco se debe consumir una prueba en una transacción separada y luego asumir que el resto de la operación siempre terminará.

### 6.3 Requisito de salida

La arquitectura elegida debe demostrar mediante pruebas de fallos y concurrencia:

- rollback completo ante error en cualquier paso;
- ausencia de identidad huérfana o Grant parcialmente emitido;
- consumo único de la prueba bajo concurrencia;
- idempotencia tras timeout/crash y resultado ambiguo;
- imposibilidad de reabrir el gate con operación incompleta;
- reconciliación determinista tras reinicio;
- consistencia entre journal, proyección, binding, Project, Environment y Grant.

Si no puede demostrarse, se pospone la habilitación; no se reduce la garantía.


## 6.4 Hallazgos de implementación que condicionan el diseño

La inspección del código actual precisa los siguientes límites:

- La migración v9 crea `atlas_projects` y `atlas_environments` como tablas independientes. Cada una conserva ID, estado y revisión; no existe una FK ni un vínculo canónico Project–Environment en esas tablas. No se debe inventar la relación usando el valor de `environment` del Grant como sustituto de una pertenencia validada.
- `SQLiteLocalAuthorityUnitOfWork` sí compone en una misma transacción local Identity, Project/Environment, Grants y otras autoridades. Esto permite reutilizar una base transaccional para esas fuentes si todas usan exactamente la misma instancia `SQLiteDatabase`.
- `SQLiteConsistencyJournal` no participa actualmente en esa UoW compartida. Por tanto, la UoW actual no hace atómica la combinación de identidad, binding, Grant, Project/Environment, evento de génesis y Recovery Gate.
- `GrantManagementService.issue` exige un contexto de usuario activo no delegado, coincidencia del propietario/proyecto/entorno y una UoW para insertar. Sin embargo, su ruta de emisión no consume una prueba independiente de acción directa del propietario ni demuestra por sí sola que el `OperationContext` provenga de un `VerifiedIdentityContext`. No debe reutilizarse sin cerrar esa frontera de autenticidad.
- Además, `SQLiteIdentityAuthority` emite un `UserId` y un `identity_id` distintos. La validación de contexto de `GrantManagementService` compara actualmente `actor.identity_id` con `context.user_id`; esta semántica debe reconciliarse con el contrato de identidad/contexto antes de reutilizar el servicio para provisión inicial. No se debe hacer que ambos identificadores coincidan artificialmente ni derivar uno del otro.
- El modelo `Grant` ya impone scope de recursos no vacío, acciones no vacías, ausencia de wildcard y expiración posterior a emisión. Estas validaciones estructurales son útiles, pero no prueban que el sujeto, propietario, Project, Environment o decisión de emisión sean auténticos y estén autorizados.

Consecuencia: la estrategia no requiere duplicar los repositorios SQLite existentes. Sí requiere diseñar el binding sujeto–propietario, completar la relación Project–Environment, cerrar la autenticidad del contexto/acción directa y coordinar el journal/gate con las escrituras de autoridad. Hasta entonces, ni la emisión directa de `GrantManagementService.issue` ni la UoW compartida son una implementación completa del bootstrap.

## 7. Modelo de estados propuesto

Estados conceptuales mínimos, sin imponer todavía nombres de tablas:

### Génesis
- `NOT_STARTED`
- `EVIDENCE_VERIFIED`
- `COMMITTED`
- `REJECTED`
- `RECONCILIATION_REQUIRED`

### Provisión inicial
- `NOT_PROVISIONED`
- `EVIDENCE_VERIFIED`
- `COMMITTED`
- `REJECTED`
- `RECONCILIATION_REQUIRED`

Los estados intermedios no significan autorización operativa. Solo `COMMITTED`, después de relectura y validación de las autoridades canónicas, acredita que la operación concluyó. Estados ambiguos mantienen el Recovery Gate cerrado.

No se deben persistir estados que permitan al caller reanudar desde un paso privilegiado sin volver a verificar evidencia, request y descriptor.

## 8. Auditoría y datos mínimos

El registro de auditoría puede conservar identificadores opacos, actor canónico, sujeto autenticado cualificado, request ID, commitment, decisión, timestamps, referencias de emisor/clave, resultado y revisiones afectadas.

No debe registrar contraseñas PAM, tokens, claves privadas, material de sesión, contenido de memoria ni secretos reutilizables. La evidencia de auditoría no concede permisos ni sustituye la verificación de la prueba.

La retención, integridad y autoridad de SecurityAudit se mantienen sujetas a sus contratos y planificación; este documento no adelanta su implementación.

## 9. Amenazas y pruebas negativas obligatorias

La implementación futura debe demostrar rechazo ante:

- caller `atlas`, `atlas-sandbox`, Assistant o Skill;
- nombre/UID local distinto del binding aprobado;
- binding ausente, cambiado, no verificable o con revisión obsoleta;
- PAM fallido, cuenta inactiva, reautenticación expirada o ausencia de TTY confiable;
- confirmación de descriptor diferente;
- alteración de Project, Environment, recurso, acciones, sujeto o expiración tras confirmar;
- prueba repetida, expirada, emitida por otro host/issuer o para otra acción;
- identidad revocada/inactiva;
- Project/Environment suspendido o incompatible;
- Grant wildcard, scope vacío, expiración ausente o delegación no aprobada;
- replay concurrente;
- crash entre cada par de pasos;
- journal ausente, inconsistente o restaurado a una revisión anterior;
- intento de abrir gate con operación incompleta;
- uso de la evidencia excepcional para una operación CAM ordinaria.

## 10. Decisiones todavía abiertas

Este documento no cierra ni inventa:

1. Contrato y almacenamiento del binding sujeto-local ↔ propietario canónico.
2. Formato criptográfico y transporte de pruebas de A y B, incluyendo issuer, key rotation, nonce, consumo y revocación.
3. Diseño de coordinación atómica o protocolo recuperable entre Identity, binding, Project/Environment, Grants, journal y Recovery Gate.
4. Tipo de evento y reducer para `DOMAIN_BOOTSTRAPPED` y evento de provisión inicial.
5. Relación formal Project–Environment y validación de pertenencia, ausente del snapshot mínimo actual.
6. Política exacta de IDs iniciales, resource types, acciones, expiración y no delegabilidad.
7. Modelo de propiedad de recursos y si el primer Grant se emite a la identidad del propietario o a otra identidad explícitamente seleccionada.
8. Política de reautenticación y ventana temporal para cada operación.
9. Semántica de recuperación cuando el resultado de una operación es ambiguo.
10. Requisitos de auditoría y pruebas independientes.

Ninguna de estas cuestiones se resuelve con un Grant global, un Project ficticio, un Environment por defecto, una identidad técnica o un bypass de CAM.

## 11. Criterios de aceptación del diseño

Antes de autorizar implementación deben existir decisiones explícitas para los puntos de la sección 10 y revisiones que demuestren:

- separación inequívoca entre génesis y provisión;
- prueba independiente, consumible y ligada al descriptor exacto para cada operación;
- binding verificable sin derivar identidad canónica de datos Unix;
- alcance mínimo del primer Grant;
- ausencia de autoridad implícita de Assistant/servicios;
- estrategia de atomicidad/reconciliación técnicamente viable;
- compatibilidad con Memory Contract §8 y no delegabilidad;
- pruebas negativas y de recuperación definidas;
- ninguna apertura de runtime protegido antes de completar las validaciones.

## 12. Estado

**Propuesta para revisión.** No se ha implementado código, migración, tabla, evento, helper PAM, binding, Grant, Project ni Environment. No se ha aplicado nada a la base de datos ni al host. La aceptación de este diseño no debe interpretarse como aprobación de la implementación privilegiada ni de cambios operativos.

