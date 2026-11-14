# ME-D4O-A — Contrato de bootstrap autenticado del dominio

**Estado:** diseño contractual; no implementado.  
**Rama de trabajo:** `feature/atlas-functional-f1`.  
**Alcance:** definir cómo activar por primera vez un dominio SQLite sin convertir el propio journal restaurable en la autoridad de su frescura.

## 1. Decisión

El bootstrap no se tratará como una recuperación vacía ni como una operación administrativa que modifica `recovery_gate_state`.

La activación inicial requiere dos evidencias distintas:

1. **Autorización explícita del propietario**, verificada fuera de SQLite y ligada a un descriptor canónico del dominio.
2. **Ancla externa monotónica**, inicializada fuera del dominio de rollback de SQLite y capaz de impedir que un backup antiguo vuelva a presentarse como estado vigente.

El `TrustAnchorPort` actual solo permite leer y avanzar un ancla existente. No ofrece inicialización autenticada de un ancla nueva. El contrato `ME-03K-C` exige precisamente un procedimiento de bootstrap explícito y autenticado fuera del flujo ordinario de recuperación, pero deja su tecnología y proveedor para una etapa posterior.

Por tanto, **no se añade todavía un evento `DOMAIN_BOOTSTRAPPED` al reducer ni una operación que abra el gate**. Añadir el evento antes de contar con la evidencia externa convertiría una firma del journal en una falsa prueba de anti-rollback.

## 2. Descriptor canónico de bootstrap

La solicitud de bootstrap debe comprometer, como mínimo:

- `consistency_domain_id`;
- `authority_epoch` inicial;
- perfil (`local` o perfil anclado, sin mezclarlos);
- `trust_policy_version`;
- identidad estable del propietario/tenant que controla el dominio;
- `issuer_id`, `issuer_role` y `key_reference` autorizados;
- versión de esquema y reducer;
- identificador único de solicitud;
- instante de autorización emitido/verificado por una fuente confiable;
- compromiso del estado de control de génesis.

El compromiso de génesis solo cubre metadatos de control del journal. No debe contener ni derivarse de contenido de memoria, texto, fragmentos, embeddings, snippets ni hashes de contenido.

La canonicalización debe ser versionada, determinista y compartida por el verificador de autorización, el proveedor del ancla y el journal. El descriptor no puede aceptar campos desconocidos, valores por defecto implícitos ni normalizaciones dependientes de plataforma.

## 3. Frontera de autorización del propietario

Se requiere un contrato independiente para verificar la aprobación del propietario. El caller no puede construir directamente un objeto de autorización verificada ni declarar que una sesión autenticada equivale a aprobación.

La evidencia verificada debe vincular exactamente:

- principal autenticado y rol de propietario autorizado;
- dominio, época y descriptor canónico;
- acción explícita `bootstrap`;
- política de confianza aplicable;
- solicitud/nonce de un solo uso o identificador idempotente;
- fecha de emisión y vigencia;
- referencia y evidencia autenticada verificables fuera de SQLite.

Resultados conceptuales:

- `VERIFIED`: produce evidencia tipada no falsificable por el caller;
- `REJECTED`: autorización inválida, revocada, vencida o contradictoria;
- `UNAVAILABLE`: no se pudo verificar; no permite avanzar.

La identidad del proceso local, el UID del sistema, un flag de configuración, una variable de entorno o una fila SQLite no constituyen por sí solos aprobación del propietario.

## 4. Frontera del proveedor de ancla

El proveedor futuro deberá extender la capacidad actual de `TrustAnchorPort` con una operación de inicialización autenticada equivalente a:

`initialize_anchor(verified_bootstrap_authorization, genesis_anchor) -> TrustAnchorUpdateStatus`

Requisitos:

- almacenamiento y control de acceso independientes de la base SQLite;
- creación atómica create-if-absent para el dominio;
- vinculación exacta de dominio, época, commitment de génesis, emisor, clave y política;
- idempotencia para la misma autorización y descriptor;
- conflicto ante una inicialización distinta para un dominio ya registrado;
- ninguna inicialización automática ante `NOT_FOUND` durante recuperación;
- evidencia verificable del proveedor y protección contra replay;
- capacidad de leer el ancla vigente y avanzar por CAS monotónico;
- `UNKNOWN` o indisponibilidad mantienen el dominio cerrado.

No se permite implementar este contrato con otra tabla dentro del mismo archivo SQLite, un archivo junto al backup, una clave almacenada en la misma base ni una variable de entorno que pueda restaurarse junto con ella. Eso no crea independencia del dominio de rollback.

## 5. Secuencia de activación propuesta

El protocolo futuro debe ser recuperable ante fallos entre el proveedor externo y SQLite. No se presupone una transacción distribuida:

1. Construir el descriptor canónico y obtener aprobación explícita del propietario.
2. Verificar la aprobación con el componente independiente. Cualquier resultado distinto de `VERIFIED` aborta.
3. Inicializar el ancla externa en estado de génesis mediante create-if-absent. Repetir exactamente la misma solicitud debe devolver el mismo resultado; un descriptor distinto debe producir conflicto.
4. Crear/verificar el dominio SQLite en estado cerrado. La operación no abre el gate.
5. Añadir, en una futura UoW, el evento autenticado de bootstrap como primer evento del dominio. El reducer deberá exigir secuencia inicial, ausencia de admisiones/operaciones previas y coincidencia exacta con el descriptor.
6. Avanzar el ancla externa mediante CAS hasta el commitment del evento de bootstrap.
7. Volver a leer y verificar el ancla externa vigente y el journal autenticado.
8. Solo entonces, mediante una operación de gate dedicada, abrir el gate si evento, ancla, descriptor, época, política y proyección coinciden exactamente.

El gate permanece cerrado durante todos los pasos intermedios. Si el proceso cae después de cualquier paso, el reintento debe reconciliar el estado exacto; nunca debe inferir éxito por ausencia de error o por una fila local.

### Fallos y reintentos

| Situación | Resultado requerido |
|---|---|
| Autorización ausente, inválida o vencida | Rechazar; gate cerrado |
| Proveedor externo no disponible | Estado desconocido; gate cerrado |
| Ancla ya inicializada con el mismo descriptor | Replay idempotente; continuar verificando |
| Ancla inicializada con descriptor distinto | Conflicto; no modificar |
| Dominio SQLite incompatible | Rechazar; no cambiar época ni política |
| Evento de bootstrap confirmado, ancla aún en génesis | No admitir; reintentar CAS exacto |
| Ancla avanzada, gate local aún cerrado | Verificar ambos lados y completar apertura exacta |
| Backup anterior al evento con ancla ya avanzada | Rechazar por rollback |
| Journal local por delante del ancla | Estado no confirmado; gate cerrado |
| Ancla ausente tras bootstrap previo | No recrearla automáticamente; intervención de recuperación autenticada |

## 6. Evento de journal futuro

Cuando se implemente, el evento de génesis deberá ser un tipo explícito, no una variante de `RECOVERY_RECONCILED`. El diseño del evento deberá fijar:

- uso exclusivo como primer registro del dominio;
- `sequence = 1`, época y dominio exactos;
- descriptor y commitment de génesis;
- identificador de autorización verificada;
- identidad/rol del propietario autorizante;
- referencia verificable de la inicialización externa;
- política, emisor y clave;
- ID de operación e idempotencia estables.

El reducer rechazará el evento si existe cualquier transición anterior, admisión, emisión, cierre o evidencia de que el dominio ya fue utilizado. El evento no debe permitir reinicializar un dominio existente ni elevar época.

La transición del gate debe ocurrir únicamente después de la verificación externa final. El evento por sí solo no autoriza la apertura.

## 7. Relación con el perfil local y el perfil anclado

El perfil local actual puede validar autenticidad disponible y continuidad interna, pero no demuestra que una base restaurada sea la más reciente. No se cambiará esa afirmación.

El bootstrap autenticado descrito aquí requiere una autoridad externa anti-rollback. No debe introducirse una ancla ficticia en `VerifiedLocalConsistencyRecoveryState` ni degradarse silenciosamente a perfil local cuando el proveedor externo no está disponible.

La decisión ME-03K-C de postergar la implementación real del Trust Anchor hasta la etapa final sigue vigente. Este diseño no revoca esa decisión ni autoriza desplegar ahora un proveedor improvisado.

## 8. Criterios de aceptación antes de escribir código

- [ ] Existe un proveedor de autorización de propietario independiente y verificable.
- [ ] Existe custodia de claves y política de confianza aprobadas.
- [ ] Existe un proveedor de ancla externo con inicialización create-if-absent y CAS monotónico.
- [ ] Se documenta dónde reside el ancla y por qué no comparte el dominio de rollback de SQLite.
- [ ] Se define el formato canónico/versionado del descriptor y commitment de génesis.
- [ ] Se define la reconciliación de fallos en cada frontera externa/local.
- [ ] Se especifica el evento y las reglas del reducer sin permitir reinicialización.
- [ ] Se especifican pruebas de replay, conflicto, backup antiguo, pérdida del proveedor, commit ambiguo, concurrencia y reinicio.
- [ ] El gate se mantiene cerrado ante toda incertidumbre.

Hasta que estos criterios estén satisfechos, ME-D4O-B (admisión durable), ME-D4O-C (egress durable), ME-D4O-D (lifecycle) y ME-D4O-E (composición completa) no deben habilitar operaciones protegidas.

## 9. Estado

ME-D4O-A queda definido a nivel de contrato y protocolo. **No se añadió código, evento, migración, proveedor de ancla, proveedor de autorización ni apertura del gate.** La siguiente tarea segura es resolver y aprobar las dos dependencias externas de confianza, o mantener el bootstrap bloqueado hasta la etapa del proyecto en que se implementará el perfil anclado.
