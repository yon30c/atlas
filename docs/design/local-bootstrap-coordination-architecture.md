# Arquitectura de coordinación del bootstrap LOCAL

**Estado:** propuesta de arquitectura para revisión; no implementada.
**Relacionado:** ME-D4O-A, local-pam-bootstrap-authenticator.md, local-pam-bootstrap-proof-protocol.md.
**Alcance:** resolver la frontera entre configuración previa, decisión interactiva, autenticación PAM y génesis CAM sin crear un emisor circular.

## 1. Decisión de diseño propuesta

No se añadirá un servicio de desafíos separado ni una segunda clave para firmarlos.

El bootstrap LOCAL utilizará tres responsabilidades separadas:

1. **Configuración protegida del host:** declara el descriptor esperado, el sujeto local admitido, el binding/slot de propietario, el perfil LOCAL y los identificadores de emisor/clave. Es provisionada por una acción administrativa fuera de Assistant y no es modificable por procesos Atlas ordinarios.
2. **Helper C/libpam:** lee esa configuración protegida, presenta el descriptor, recoge la decisión directa, reautentica al sujeto configurado y emite una prueba firmada de un solo uso. No consulta ni modifica CAM/SQLite.
3. **Coordinador/verificador CAM:** valida la prueba contra la configuración de claves confiables y el descriptor esperado; verifica el estado de bootstrap pendiente; consume la prueba y realiza la génesis dentro de la misma UoW.

No existe un emisor independiente de desafíos. El helper genera criptográficamente request_id, nonce y proof_id durante la invocación interactiva. El helper no recibe descriptor, subject, action, profile, epoch, owner ID, timestamp ni resultado PAM desde el caller.

## Política de sesión interactiva

El coordinador acepta la prueba firmada del helper tanto si el bootstrap se inició desde un terminal local como desde SSH interactivo con PTY. SSH sin PTY y ejecución no interactiva quedan excluidos. La modalidad de acceso no cambia el sujeto local esperado, el descriptor, la verificación PAM, la confirmación TTY ni las condiciones transaccionales. Un PTY no acredita presencia física.

La comprobación de TTY, foreground, sesión, invocación privilegiada y cancelación por desconexión pertenece al helper; el coordinador verifica criptográficamente la prueba y aplica el consumo de un solo uso y el commit atómico descritos en este documento. Véase [Frontera de privilegios del bootstrap LOCAL](local-bootstrap-privilege-boundary.md).

## 2. Fuente autoritativa previa a CAM

La configuración protegida del host es la fuente de la intención de bootstrap, no la base de datos CAM que se está inicializando.

Debe residir en una ruta bajo control root, con directorio y archivo no modificables por greed como usuario sin privilegios, atlas, atlas-sandbox ni procesos de Assistant. La propiedad/permisos concretos se decidirán al diseñar la invocación privilegiada.

Contenido lógico mínimo:

- versión del formato y de canonicalización;
- consistency_domain_id esperado;
- authority_epoch inicial;
- perfil LOCAL;
- trust_policy_version;
- reducer_version y versión de esquema;
- issuer_id, issuer_role y key_reference autorizados para el evento de génesis;
- bootstrap_binding_id (slot estable, no UserId);
- sujeto PAM esperado: realm/host de autenticación, nombre greed y UID esperado leído/verificado en el host;
- host_binding_id;
- key_id y clave pública que el verificador aceptará;
- huella del descriptor completo.

La clave privada de firma del helper no se guarda en esta configuración ni en SQLite. La ruta/propiedad y mecanismo de lectura se fijarán con el diseño de privilegios. Los archivos desconocidos, duplicados, enlaces simbólicos inesperados, permisos inseguros, campos faltantes o formatos no canónicos producen rechazo.

La configuración no es una prueba de que el bootstrap siga pendiente. Solo declara qué bootstrap puede solicitarse. La autoridad CAM comprueba el estado real del dominio y la ausencia de génesis en su transacción.

## 3. Slot de propietario, no identidad canónica preasignada

El descriptor no puede incluir un UserId canónico que aún no existe. Se utilizará un bootstrap_binding_id estable que representa el slot de propietario inicial aprobado en la configuración protegida.

El helper muestra y confirma que la decisión es crear la identidad canónica inicial y asociarla al slot indicado, bajo el sujeto local greed autenticado en el host configurado.

Durante la transacción de génesis:

1. La autoridad de identidad genera el UserId y Identity(USER) canónicos mediante su mecanismo existente.
2. Un repositorio de binding registra bootstrap_binding_id → UserId/identity_id junto al sujeto local cualificado y la referencia a la prueba verificada.
3. La restricción de unicidad garantiza un solo propietario inicial para ese slot y dominio.
4. El evento de génesis referencia el binding y la prueba consumida.

El bootstrap_binding_id no es identidad, credencial ni permiso. No puede ser elegido por el caller ni utilizado como UserId. La asociación final solo existe tras el commit atómico.

## 4. Flujo propuesto

1. Un operador inicia explícitamente el procedimiento local de bootstrap.
2. El mecanismo de invocación aprobado ejecuta el helper C con acceso al TTY y a la configuración protegida.
3. El helper valida configuración, host y sujeto esperado; calcula y presenta el descriptor canónico completo y sus campos legibles.
4. El operador confirma la acción exacta en el TTY del helper.
5. El helper realiza pam_start, pam_authenticate y pam_acct_mgmt con el servicio dedicado atlas-bootstrap. No acepta credenciales por argv, entorno, archivo, pipe o stdin redirigido.
6. El helper genera request_id, nonce y proof_id aleatorios, construye la prueba ligada al descriptor y sujeto observados, la firma y la entrega por el canal de salida previsto.
7. El coordinador CAM verifica firma, emisor, key_id, timestamps, action, profile, descriptor, host, sujeto y binding contra configuración confiable.
8. Dentro de una única SQLiteUnitOfWork, el coordinador vuelve a comprobar que el dominio no tiene bootstrap/génesis previo, consume la prueba con restricciones únicas, crea la identidad canónica, persiste el binding, registra DOMAIN_BOOTSTRAPPED, actualiza head/proyección/gate y confirma todo junto.
9. Una verificación posterior independiente comprueba evento, firma local, descriptor, binding, head y gate. Solo entonces puede considerarse activado el perfil LOCAL.

El helper no decide si el paso 8 está permitido. El coordinador CAM no puede fingir los pasos 4–6.

## 5. Por qué no se necesita un emisor de desafíos aparte

El helper es el emisor confiable de la evidencia de acción directa. La petición es la invocación interactiva misma; no existe una solicitud de descriptor controlada por Python que el helper deba firmar ciegamente.

La protección se obtiene así:

- el descriptor procede de configuración protegida, no del caller;
- el helper presenta el descriptor exacto y recoge directamente la confirmación;
- PAM verifica el sujeto local en esa misma invocación;
- la firma vincula la evidencia al descriptor y sujeto;
- el verificador solo acepta la clave y el descriptor configurados;
- el estado de bootstrap pendiente se valida y serializa en CAM;
- la prueba se consume en la misma UoW que la génesis.

Por tanto, no hay clave de emisor de desafíos, endpoint de challenge ni tabla de challenges pendiente. Se conserva request_id/nonce/proof_id aleatorios para binding, auditoría e idempotencia/replay.

## 6. Reintentos, concurrencia y fallos

La prueba no se consume en una transacción previa separada. Verificación criptográfica puede ocurrir antes de abrir UoW, pero el consumo único y el evento de génesis se confirman juntos.

- Dos pruebas distintas concurrentes: solo una puede crear la génesis; la segunda observa dominio ya inicializado y falla con conflicto.
- Misma prueba concurrente: restricciones únicas y BEGIN IMMEDIATE permiten un único commit.
- Fallo antes del commit: consumo, identidad, binding, evento y gate revierten juntos; el mismo proof puede reintentarse mientras siga vigente.
- Commit realizado pero respuesta perdida: la operación se resuelve por request_id/idempotency key y devuelve el resultado previo exacto; no crea otra identidad.
- Descriptor distinto: rechazo; exige nueva confirmación interactiva y una configuración administrativa corregida.
- Dominio existente con descriptor igual: no se crea otra identidad ni se reabre el gate. Se devuelve el resultado histórico solo si la auditoría demuestra que corresponde a la misma operación.
- Dominio existente con descriptor distinto: conflicto y Recovery Gate cerrado.

El helper puede emitir más de una prueba si se invoca de nuevo. Eso no crea autoridad múltiple: el estado CAM permite una única génesis y una sola asociación al slot de propietario. El rate-limit PAM limita intentos de contraseña, no sustituye la unicidad transaccional.

## 7. Contrato de configuración y cambio

La configuración protegida se prepara mediante un procedimiento administrativo explícito antes del bootstrap. Assistant, Skills, Broker, usuario técnico y helper no pueden modificarla.

Cambiar domain_id, epoch, binding_id, host, sujeto, issuer, key_reference o trust_policy_version después de que el procedimiento haya sido aprobado requiere una nueva revisión administrativa y una nueva confirmación directa. No se permite reescribir la configuración silenciosamente entre presentación y emisión.

La configuración debe incluir una versión/revisión y su digest. El helper incorpora esa revisión/digest en la prueba; el verificador exige coincidencia exacta con la configuración de confianza vigente.

La política de actualización y backup de esta configuración, así como el tratamiento de una pérdida del archivo antes del bootstrap, se documentarán antes de implementación. La pérdida nunca permite regenerar automáticamente una nueva identidad de propietario.

## 8. Relación con el código existente

- SQLiteIdentityAuthority sigue siendo el único emisor de UserId y Identity(USER). El binding se crea en la misma UoW; no se amplía el helper para emitir identidades.
- SQLiteUnitOfWork proporciona BEGIN IMMEDIATE, rollback y conexión compartida para adaptadores de la misma SQLiteDatabase. Es una primitiva, no el coordinador de génesis.
- SQLiteConsistencyJournal.create_local_domain(...) actualmente crea una fila de dominio LOCAL cerrada sin prueba de propietario ni evento de génesis. Se utiliza en pruebas y no debe confundirse con la activación autenticada. No se debe llamar como sustituto del futuro DOMAIN_BOOTSTRAPPED.
- OwnerDecisionVerifier de DM-01 fue definido para acciones de Memory. No se reutiliza directamente con acciones de bootstrap ni se altera su semántica. Puede servir como referencia conceptual de prueba no delegable y consumo único; el bootstrap requiere un contrato tipado específico.
- El servicio de recuperación/gate actual no implementa la génesis inicial. No se abre el gate mediante create_local_domain, UPDATE manual ni restauración vacía.

## 8.1 Frontera de privilegios

La evaluación de invocación root-owned, sudo, TTY, entorno y alternativa de socket Unix está especificada en [Frontera de privilegios del bootstrap LOCAL](local-bootstrap-privilege-boundary.md). No se ha seleccionado ni instalado todavía el mecanismo. El candidato sudo solo se aceptará tras inspección de solo lectura del host; si no puede demostrarse la procedencia del invocador y la vinculación del TTY, se evaluará un servicio root de socket Unix con `SO_PEERCRED` y `SCM_RIGHTS`.

## 9. Decisiones que permanecen pendientes

1. Mecanismo de invocación privilegiada del helper y prueba de TTY confiable; no setuid.
2. Formato exacto, canonicalización, límites y vectores de prueba del archivo de configuración.
3. Ed25519/OpenSSL EVP y disponibilidad de headers/libs en el host Debian.
4. Custodia de la clave privada, permisos, key_id, rotación y revocación.
5. Transporte de la prueba entre helper y coordinador sin que el caller pueda sustituirla; canal y permisos de salida.
6. Política de expiración/skew y fuente de reloj.
7. Contrato y migración del bootstrap_binding_id, consumo de prueba, evento DOMAIN_BOOTSTRAPPED y gate dentro de una única UoW.
8. Idempotencia exacta de la respuesta tras commit ambiguo.
9. Política de bloqueo PAM en el stack dedicado y pruebas de cuenta bloqueada/inactiva.
10. Auditoría posterior a génesis y recuperación ante corrupción.

## 10. No objetivos y límites

- No implementar Trust Anchor externo ni fingir anti-rollback.
- No modificar PAM general, sudoers, systemd, Broker, usuarios/grupos ni permisos del host en esta etapa.
- No instalar paquetes ni generar claves reales.
- No crear migraciones, identidades, binding, evento ni registros CAM todavía.
- No conectar el bootstrap al Assistant runtime ni habilitar Recovery Gate.
- No implementar shell general, comandos arbitrarios o ejecución remota.

**Criterio de salida:** antes del código deben estar aprobados los puntos 1–8 del §9 y definidos los contratos tipados de prueba, configuración y génesis. Después se implementarán primero los modelos/validadores y pruebas puras; el helper privilegiado y la integración CAM vendrán en etapas separadas.