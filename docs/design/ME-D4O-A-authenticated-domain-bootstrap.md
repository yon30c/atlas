# ME-D4O-A — Contrato de bootstrap de dominio por perfil

**Estado:** diseño contractual corregido; no implementado.  
**Rama:** `feature/terminal-commands`.  
**Alcance:** definir la activación inicial de un dominio SQLite sin confundir autenticidad local con anti-rollback externo.

## 1. Decisión de arquitectura

ME-03K-B, ME-03K-C y Contrato de diseño Atlas v1 §20.6 establecen dos perfiles:

- **LOCAL:** baseline actual, un servidor, sin Trust Anchor externo. Es el perfil de desarrollo y operación previsto para las etapas actuales.
- **ANCHORED:** capacidad opt-in futura. Su proveedor externo y sus garantías anti-rollback se implementarán en la etapa final. Si se selecciona este perfil y el proveedor no está disponible o no puede verificarse, falla cerrado; nunca degrada automáticamente a LOCAL.

El Trust Anchor externo **no es requisito para desarrollar ni completar el baseline LOCAL**. Su ausencia no elimina la autorización explícita del propietario, la autenticidad local disponible, la idempotencia, la atomicidad, el fencing ni la recuperación fail-closed.

El bootstrap es distinto de una recuperación de un dominio previamente activo. Un journal vacío no prueba por sí solo frescura frente a un backup antiguo.

## 2. Bootstrap del perfil LOCAL

El perfil LOCAL debe disponer de una activación inicial deliberada y autenticada, sin proveedor Trust Anchor externo.

La activación requiere:

1. Descriptor canónico del dominio y compromiso del estado de génesis.
2. Acción explícita del propietario, ligada al dominio, época, perfil y solicitud exactos.
3. Verificación local de esa autorización mediante una frontera confiable separada de la fila SQLite que se activa. El caller no puede fabricar un resultado `VERIFIED`.
4. Firma/autenticación local del evento de génesis usando los puertos de custodia y firma locales configurados.
5. Creación idempotente del evento inicial y actualización del estado del gate dentro de una misma `SQLiteUnitOfWork`.
6. Verificación posterior de la cadena, proyección y estado del gate conforme al perfil LOCAL antes de permitir operaciones.

La autorización del propietario no equivale a Trust Anchor. Una credencial local puede demostrar quién autorizó la activación conforme al mecanismo implementado, pero no demuestra que el conjunto SQLite restaurado sea el más reciente.

El formato de evidencia de acción directa del propietario sigue sujeto al contrato de identidad/CAM y a la decisión pendiente registrada en `docs/contracts/memory.md` §8. No se inventará un bypass ni se tratará UID, variable de entorno, flag o fila SQLite como aprobación por sí solos.

## 2.1 Procedimiento interactivo LOCAL aprobado

**Decisión aprobada por el propietario del proyecto:** el bootstrap inicial se realizará mediante un procedimiento local interactivo, autenticado y de una sola ejecución, independiente de Atlas Assistant.

Requisitos del procedimiento:

1. Se inicia explícitamente desde una sesión administrativa local y presenta el descriptor canónico exacto que se pretende activar.
2. Antes de aceptar la decisión, exige una autenticación reciente del operador mediante un mecanismo confiable del sistema operativo. La autenticación de la sesión ya abierta, la pertenencia a un grupo, el UID del proceso, una variable de entorno o la ejecución con `sudo` sin reautenticación no bastan por sí solos.
3. La identidad autenticada debe estar vinculada a la identidad de propietario que se está estableciendo mediante una configuración/procedencia verificable; no se infiere que el usuario del servicio `atlas`, el usuario del Broker o el usuario que ejecuta la CLI sea automáticamente el propietario.
4. Muestra la acción, el dominio, la época, el perfil LOCAL y el compromiso que se autorizarán. La confirmación debe ser explícita y vinculada a esos valores exactos.
5. Produce una prueba tipada, de un solo uso, con identificador de solicitud, sujeto autenticado, acción y descriptor/recursos exactos. El verificador valida y consume esa prueba; el caller no puede construir un resultado verificado.
6. El procedimiento no pasa por el modelo, la conversación, una Skill ni una decisión del Assistant.
7. Tras el consumo exitoso, el bootstrap aplica el evento de génesis y su estado materializado de forma atómica. Un reintento exacto devuelve el resultado previo; un descriptor distinto o una prueba consumida se rechazan.

La integración de autenticación del sistema operativo (por ejemplo, mediante PAM en Linux) se debe evaluar como proveedor local concreto. No se declara implementada ni se acepta una implementación que solo compruebe UID, grupo, variable de entorno, flag, texto de confirmación o caché de autenticación de una sesión anterior.

Este procedimiento no introduce Trust Anchor externo, no ofrece anti-rollback y no convierte al principal técnico `atlas` en propietario. El mapeo entre el sujeto autenticado y el propietario canónico debe quedar explícito y auditable.

## 3. Descriptor canónico

La solicitud de bootstrap comprometerá, como mínimo:

- `consistency_domain_id`;
- `authority_epoch` inicial;
- perfil explícito (`LOCAL` o `ANCHORED`);
- `trust_policy_version`;
- identidad estable del propietario/tenant;
- `issuer_id`, `issuer_role` y `key_reference` autorizados;
- versión de esquema y reducer;
- identificador único de solicitud;
- compromiso del estado de control de génesis.

El compromiso cubre solo metadatos de control del journal. No contiene ni deriva de contenido de memoria, texto, fragmentos, embeddings, snippets ni hashes de contenido.

La canonicalización debe ser versionada, determinista y rechazar campos desconocidos, valores por defecto implícitos y normalizaciones dependientes de plataforma.

## 4. Evento de génesis LOCAL

El evento futuro debe ser un tipo explícito, por ejemplo `DOMAIN_BOOTSTRAPPED`; no se reutilizará `RECOVERY_RECONCILED`.

Reglas:

- primer y único evento de génesis del dominio;
- secuencia inicial exacta y época/dominio coincidentes;
- descriptor, commitment, perfil y política exactos;
- referencia a la autorización local verificada del propietario;
- emisor/clave y autenticación local válidos;
- operación e idempotency key estables;
- rechazo si hay cualquier transición, admisión u operación previa;
- conflicto ante descriptor distinto o intento de reinicialización.

La creación del evento y la mutación materializada del gate deben confirmarse o revertirse en la misma UoW. El evento no puede autoatestiguar frescura externa.

## 5. Perfil ANCHORED — extensión futura

El perfil ANCHORED añadirá una autoridad externa independiente del dominio de rollback SQLite. Su proveedor deberá soportar:

- inicialización autenticada create-if-absent;
- vinculación de dominio, época, perfil, commitment, emisor, clave y política;
- idempotencia para la misma solicitud y conflicto para una distinta;
- lectura de ancla vigente y avance monotónico mediante CAS;
- evidencia verificable, protección contra replay y reconciliación de resultados ambiguos;
- rechazo de backups por debajo del ancla vigente.

La secuencia de coordinación entre proveedor y SQLite será recuperable ante fallos; no se presupone una transacción distribuida. La ausencia o discrepancia del proveedor en perfil ANCHORED mantiene el gate cerrado. No se permite fallback a LOCAL.

La implementación real del proveedor sigue postergada hasta la etapa final. No se añade ahora una tabla, archivo o clave local que se presente como ancla externa.

## 6. Restauración y límites del perfil LOCAL

El perfil LOCAL puede verificar autenticidad disponible, estructura, dominio, época, secuencias, continuidad interna, inventarios y recibos según sus mecanismos implementados. No puede demostrar que el head recuperado sea el último que existió antes de una restauración coherente del conjunto local.

Por ello:

- el estado recuperado debe declarar explícitamente `LOCAL`;
- no se afirmará anti-rollback externo;
- una restauración que pueda preceder a un Forget, invalidación o fencing requerido no puede exponer la memoria ni reabrir la ruta protegida sin reconciliación contra una fuente independiente aprobada;
- integridad local del backup no equivale a prueba de frescura;
- no se permite que un backup restaure automáticamente la autoridad para admitir lecturas o emitir contenido.

Estas restricciones preservan ME-03K-B y Memory Contract §9.5. Trust Anchor opcional no convierte Forget ni sus garantías en opcionales.

## 7. Criterios de aceptación

### Perfil LOCAL — baseline actual

- [ ] Existe una evidencia de acción directa del propietario verificable y ligada al descriptor exacto.
- [ ] La verificación local usa una frontera confiable y no acepta resultados fabricados por el caller.
- [ ] El evento de génesis está autenticado con los puertos locales configurados.
- [ ] Evento, idempotencia, head y gate se confirman en una sola UoW.
- [ ] Replay idéntico es idempotente; descriptor distinto y reinicialización se rechazan.
- [ ] La recuperación devuelve un resultado tipado LOCAL y declara la ausencia de anti-rollback externo.
- [ ] Restauraciones con incertidumbre sobre Forget/fencing/cierres permanecen bloqueadas hasta reconciliación independiente.
- [ ] Se prueban fallos, rollback, concurrencia, reinicio y resultados ambiguos.

### Perfil ANCHORED — etapa final

- [ ] Proveedor externo independiente con create-if-absent y CAS monotónico.
- [ ] Autorización y evidencia verificables fuera del dominio SQLite.
- [ ] Reconciliación de fallos entre ancla y journal.
- [ ] Backup antiguo rechazado contra el ancla vigente.
- [ ] Indisponibilidad o discrepancia mantiene el gate cerrado, sin fallback.

## 8. Relación con ME-D4O-B–E

La ausencia del proveedor ANCHORED **no bloquea el desarrollo del baseline LOCAL** de admisión, egress, lifecycle ni composición. Estas fases pueden implementarse y probarse bajo las garantías locales, sin habilitar runtime protegido antes de que el bootstrap LOCAL y las pruebas requeridas estén completos.

La autorización directa del propietario y su evidencia tipada siguen siendo una dependencia contractual para implementar la activación LOCAL. Debe resolverse reutilizando/alineando los contratos de identidad/CAM; no se sustituye por Trust Anchor externo.

Ninguna fase puede afirmar anti-rollback externo ni permitir restauraciones de memoria no reconciliadas.

## 9. Estado

La elección del procedimiento interactivo LOCAL de una sola ejecución queda aprobada. El proveedor de autenticación local, el binding verificable entre sujeto autenticado y propietario canónico, la prueba consumible y el flujo de génesis siguen sin implementar.

ME-D4O-A queda corregido para reflejar los perfiles aprobados. No se añadió código, evento, migración, proveedor externo, autorización local concreta ni apertura del gate. El baseline LOCAL puede continuar por etapas; la habilitación operativa queda condicionada a su bootstrap autenticado, atomicidad y validación. El perfil ANCHORED permanece postergado.

## 2.2 Identidad operativa inicial y binding local aprobado

**Decisión aprobada por el propietario: 16 de noviembre de 2026.**

La cuenta Linux `greed` será el sujeto local que autentique la acción administrativa inicial de bootstrap. Esta decisión identifica al operador local del procedimiento; no convierte el nombre Unix en identidad canónica de Atlas ni hace de la cuenta una autoridad autónoma.

Reglas del binding:

1. El proveedor local de autenticación deberá producir evidencia verificable del sujeto autenticado en el host y de la reautenticación reciente. El identificador del sujeto debe estar cualificado por el dominio/host de autenticación para evitar interpretar un nombre Unix aislado como identidad global.
2. Una configuración de bootstrap explícita y protegida vinculará ese sujeto local autenticado con el propietario canónico que se está estableciendo. La configuración no podrá ser modificada por el proceso de Atlas Assistant ni por el principal técnico.
3. La autoridad de identidad generará el `UserId` canónico y la `Identity(USER)` mediante el mecanismo autoritativo existente. No se derivarán UUID, `UserId` ni `identity_id` del texto `greed`, del UID 1000 (o cualquier UID supuesto), de nombres de grupo ni de variables de entorno.
4. La evidencia de bootstrap deberá enlazar la identidad local autenticada, el binding aprobado, la decisión directa del propietario y el descriptor exacto del dominio. El caller no podrá declarar por sí mismo que el sujeto es el propietario.
5. La cuenta Unix `atlas` (UID técnico 999 en el entorno inspeccionado) y la cuenta de servicio `atlas-sandbox` permanecen separadas del propietario. No pueden realizar el bootstrap ni heredar su autoridad por pertenecer a grupos, ejecutar servicios o acceder al Broker.
6. El proceso de servicio central no obtiene privilegios del operador interactivo. La autenticación local de bootstrap es un flujo administrativo explícito, no una sesión permanente ni un permiso implícito para todas las operaciones.
7. Una vez establecido el propietario canónico, el acceso desde móvil, portátil y web deberá autenticarse mediante el futuro gateway de acceso del servicio central y resolverse a ese mismo `UserId`/Identity(USER). Las sesiones remotas y el registro de dispositivos serán independientes de las cuentas Unix.
8. La pérdida, cambio o revocación del sujeto local no debe reasignar automáticamente la propiedad canónica. Cualquier sustitución del mecanismo de recuperación o del operador bootstrap requerirá un procedimiento de cambio de autoridad explícito y auditable.

La cuenta `greed` queda seleccionada como sujeto operativo inicial; esto no selecciona todavía PAM ni otro proveedor concreto, no crea el binding en el sistema, no crea la identidad canónica y no inicializa CAM. La implementación deberá verificar primero qué mecanismo de reautenticación local está disponible y cómo puede emitir una prueba no falsificable por el caller.
