# ME-03L — Autoridad externa de continuidad y protección anti-rollback

**Estado:** propuesta de diseño; no implementada ni aprobada para activación operativa.  
**Rama:** `feature/me-03l-external-continuity-anchor`.  
**Base:** `13cb752a0143cc6ee7945ba5b8df21d64350d131`.  
**Dependencia:** ME-03K — perfil local, journal SQLite, checkpoints y almacén local de proyecciones.  
**Alcance:** definir la autoridad externa monotónica, su protocolo, estados de reconciliación, amenazas y criterios de aceptación.  
**Fuera de alcance:** seleccionar proveedor, desplegar servicios, provisionar credenciales, cambiar systemd/Broker/Registry, modificar el esquema SQLite o implementar código.

## 1. Problema que resuelve

ME-03K autentica localmente el journal y permite reconstruir el estado desde un checkpoint y su proyección. El almacén de proyecciones es independiente de SQLite, pero sigue siendo local al host.

Por tanto, un atacante o una recuperación operativa que restaure conjuntamente una copia antigua y coherente de:
- la base SQLite;
- el almacén local de proyecciones;
- las claves y la configuración local disponibles en esa copia;

puede presentar una historia local que pase sus verificaciones criptográficas aunque no sea la historia más reciente que Atlas había confirmado.

**ME-03L introduce una autoridad de continuidad fuera del dominio de fallo y administración del host Atlas.** Su función es recordar el último checkpoint confirmado y rechazar una historia local anterior o contradictoria.

No se atribuye anti-rollback a HMAC, a los hashes, al filesystem local ni a un backup. La garantía nueva depende de que la autoridad externa y su estado monotónico permanezcan fuera del control del atacante considerado.

## 2. Garantía exacta y límites

### 2.1 Garantía propuesta

Para cada dominio de consistencia y época de autoridad, la autoridad externa conserva un registro monotónico del último checkpoint confirmado.

Si Atlas presenta una copia local cuyo checkpoint no coincide con el registro vigente, la recuperación **no puede declararla operativa**. Debe:
1. obtener la evidencia vigente directamente de la autoridad;
2. verificarla;
3. recuperar el checkpoint exacto indicado por ella desde el archivo externo de recuperación; o
4. permanecer bloqueado en modo de recuperación si no puede hacerlo.

La garantía se refiere a checkpoints que la autoridad confirmó, no a cualquier escritura local que todavía no se haya anclado.

### 2.2 Límite de granularidad

ME-03L no promete que cada transición local quede protegida individualmente. Si Atlas crea transiciones después del último checkpoint anclado, estas forman un sufijo local aún no confirmado externamente.

La pérdida o restauración de ese sufijo puede producir una pérdida de datos dentro de la ventana entre checkpoints. No se debe presentar como anti-rollback completo.

El diseño debe fijar explícitamente:
- intervalo máximo entre checkpoints anclados;
- operaciones que requieren un checkpoint anclado inmediatamente antes o después;
- si ciertas operaciones irreversibles requieren una confirmación externa por operación.

Hasta que esos valores se aprueben, el RPO de la continuidad externa queda **sin especificar**.

### 2.3 Lo que no garantiza

No protege frente a:
- compromiso o colusión del administrador de la autoridad externa y del host;
- rollback o corrupción del propio servicio de autoridad si este no dispone de almacenamiento monotónico fiable;
- robo de las credenciales autorizadas para actualizar el ancla;
- pérdida simultánea del ancla y de todos los archivos de recuperación externos;
- acciones que Atlas haya ejecutado fuera de su flujo de autorización y continuidad.

Tampoco sustituye la autenticación local, el CAM, las políticas, la auditoría ni las verificaciones de inventario.

## 3. Separación de tres responsabilidades

No se debe convertir un solo componente en almacenamiento, autoridad y mecanismo de recuperación.

1. **Local Checkpoint Store (ME-03K):** conserva checkpoint y journal local, y permite recuperación local autenticada.
2. **External Recovery Archive:** conserva, de forma inmutable y recuperable, los artefactos necesarios para reconstruir el checkpoint confirmado. Debe estar fuera del host y del dominio de administración local. Los artefactos sensibles deben cifrarse; el archivo no decide cuál versión es vigente.
3. **External Continuity Authority (ECA):** mantiene únicamente el estado mínimo necesario para identificar el último checkpoint confirmado y emitir evidencia autenticada. No necesita recibir memoria en claro ni contenido de proyectos.

El archivo externo y la autoridad deben tener credenciales, permisos y dominios de fallo separados. Guardar una segunda copia en otro directorio del mismo host no cumple el requisito.

La autoridad no debe depender de una fila en SQLite, de un archivo local ni de un recibo restaurado desde el backup que se está verificando.

## 4. Registro monotónico de continuidad

La ECA conserva un registro por `continuity_domain_id`. Como mínimo:

| Campo | Significado |
|---|---|
| `continuity_domain_id` | Identidad estable del dominio protegido. |
| `authority_epoch` | Época de autoridad; solo cambia mediante procedimiento explícito de recuperación y aprobación del propietario. |
| `anchor_revision` | Contador monotónico administrado por la ECA, independiente de la secuencia SQLite. |
| `checkpoint_id` | Identidad estable del checkpoint confirmado. |
| `checkpoint_position` | Dominio, época y secuencia representada por el checkpoint. |
| `checkpoint_commitment` | Compromiso criptográfico del checkpoint autenticado. |
| `projection_state_ref` | Referencia opaca al artefacto de estado archivado. |
| `projection_integrity_ref` | Referencia opaca al manifiesto/artefacto de integridad archivado. |
| `schema_version`, `reducer_version`, `trust_policy_version` | Versiones necesarias para interpretar y validar la proyección. |
| `previous_anchor_record_digest` | Enlace al registro anterior de la autoridad, si se conserva historial encadenado. |

La ECA debe rechazar:
- una revisión menor o igual que la vigente para una nueva actualización;
- la reutilización de un `checkpoint_id` con contenido diferente;
- la misma revisión con un compromiso distinto;
- un avance que no coincida con la época y la revisión esperadas;
- cambios de época no autorizados.

El contador `anchor_revision` es la fuente monotónica del protocolo externo. La secuencia del journal local no sustituye ese contador.

## 5. Protocolo propuesto

### 5.1 Confirmación de un checkpoint

Orden propuesto:

1. Atlas verifica su estado local mediante la ruta ME-03K.
2. Genera y confirma el checkpoint local con identidad estable.
3. Publica la proyección y los artefactos necesarios en el External Recovery Archive mediante escritura inmutable y read-back.
4. Envía a la ECA una solicitud de avance con:
   - dominio y época;
   - revisión externa esperada;
   - checkpoint ID y posición;
   - commitment del checkpoint;
   - referencias opacas de archivo;
   - versiones de schema, reducer y política;
   - identidad autenticada del emisor;
   - nonce de solicitud.
5. La ECA verifica autorización, época, revisión esperada y consistencia de la solicitud.
6. La ECA realiza compare-and-swap atómico de la revisión y persiste el nuevo registro monotónico.
7. La ECA devuelve un recibo firmado que vincula exactamente la solicitud, el nuevo registro, la revisión, el nonce y la identidad de la autoridad.
8. Atlas verifica el recibo y lo conserva localmente como evidencia/caché; el recibo local no se convierte por sí mismo en autoridad.
9. Atlas vuelve a consultar la ECA con un desafío nuevo antes de habilitar operaciones protegidas, y comprueba que el registro vigente coincide con el checkpoint local.

El orden evita que la autoridad apunte a una proyección que todavía no está archivada. Un fallo entre el commit local y el avance de la ECA deja un checkpoint local no anclado; no se debe presentar como confirmado externamente.

### 5.2 Confirmación incierta

Si la ECA pudo haber persistido el avance pero la respuesta se perdió:
- Atlas conserva el mismo `checkpoint_id`, referencias, posición y semántica;
- consulta el registro vigente con un desafío nuevo;
- si el registro coincide exactamente, resuelve como confirmado;
- si sigue en la revisión anterior, puede reintentar el mismo compare-and-swap;
- si existe una revisión o compromiso contradictorio, bloquea y clasifica el caso como conflicto;
- nunca genera automáticamente una identidad nueva para ocultar el resultado incierto.

### 5.3 Reconciliación al iniciar

Antes de habilitar operaciones protegidas, Atlas obtiene evidencia fresca de la ECA y compara el registro con el estado local verificado.

| Estado | Condición | Acción |
|---|---|---|
| `MATCH` | Dominio, época, checkpoint, posición y commitment coinciden. | Puede continuar la verificación local restante; no implica autorización para otras operaciones. |
| `LOCAL_BEHIND` | La ECA conoce un checkpoint posterior al checkpoint local. | No activar. Recuperar el checkpoint exacto desde el archivo externo y verificarlo. |
| `LOCAL_AHEAD_UNANCHORED` | El checkpoint local es posterior al registro ECA. | No promoverlo automáticamente. Mantener modo recuperación; reconciliar con aprobación explícita o descartar el sufijo no anclado según política aprobada. |
| `SAME_REVISION_DIFFERENT_COMMITMENT` | Misma revisión, distinto checkpoint o commitment. | Rechazo crítico; posible corrupción, clonación o compromiso. |
| `EPOCH_MISMATCH` | Época local y externa diferentes. | Bloquear; no inferir cuál es correcta. Requiere procedimiento explícito de recuperación. |
| `AUTHORITY_UNAVAILABLE` | No se obtiene respuesta verificable y fresca. | Bloquear operaciones que requieran continuidad externa. No aceptar un recibo local antiguo como sustituto. |
| `RECEIPT_INVALID` | Firma, identidad, nonce, dominio o campos no coinciden. | Rechazar y registrar incidente. |
| `ARCHIVE_UNAVAILABLE` | La ECA indica un checkpoint vigente, pero sus artefactos no se pueden recuperar. | Permanecer bloqueado; no degradar silenciosamente a un checkpoint local antiguo. |

### 5.4 Restauración desde un backup antiguo

1. Restaurar en modo de recuperación, sin ejecutar proyectos, agentes ni Skills.
2. Verificar criptográficamente la copia local usando ME-03K.
3. Consultar la ECA directamente, con desafío fresco.
4. Si la copia está por detrás, recuperar desde el archivo externo el checkpoint que la ECA declara vigente.
5. Verificar referencias, hashes, manifiesto, envelope, política, replay e inventarios.
6. Reconstruir el journal/sufijo de acuerdo con un procedimiento de restore separado.
7. Exigir aprobación del propietario antes de reactivar operaciones protegidas.

Si la autoridad no está disponible o el archivo no contiene el checkpoint requerido, la recuperación no se declara completa.

## 6. Autenticidad, frescura y claves

El protocolo debe distinguir tres evidencias:

- **Autenticidad:** firma verificable del recibo emitido por una clave pública de autoridad previamente confiada.
- **Frescura:** respuesta vinculada a un nonce impredecible de la consulta actual; un recibo antiguo copiado desde un backup no demuestra el estado vigente.
- **Monotonicidad:** la ECA rechaza retrocesos y actualizaciones fuera de secuencia mediante compare-and-swap persistente.

Un timestamp, por sí solo, no prueba frescura ni monotonicidad.

La identidad de Atlas que puede solicitar avances debe estar autorizada fuera del control de los artefactos locales. El material de firma de la autoridad no se almacena en Atlas. La rotación de claves de autoridad requiere transición autenticada y verificable; no se acepta una clave nueva solo porque venga en una respuesta.

No se define todavía algoritmo de firma, transporte, protocolo de identidad ni proveedor. Deben elegirse después de fijar las amenazas y capacidades de custodia.

## 7. Modelo de amenazas

| Amenaza | Resultado esperado |
|---|---|
| Restauración conjunta de SQLite y almacén local antiguos | ECA detecta que el checkpoint local está detrás. |
| Reemplazo local de un checkpoint por otro con mismo ID | Commitment distinto; rechazo. |
| Reproducción de un recibo viejo | Falla el desafío de frescura o no coincide con el registro vigente. |
| Dos escritores intentan avanzar a la vez | Solo un compare-and-swap gana; el otro recibe conflicto y debe reconciliar. |
| Caída después de publicar el archivo y antes de actualizar ECA | Artefactos huérfanos; no se consideran confirmados. |
| Caída después del avance ECA y antes de persistir el recibo local | Consulta fresca resuelve el estado exacto. |
| ECA inaccesible durante arranque | No se habilitan operaciones que exijan continuidad externa. |
| Archivo externo ausente o corrupto | No se sustituye por una proyección local anterior. |
| Restauración del propio almacenamiento de ECA a una copia vieja | Fuera de garantía salvo que el servicio ECA disponga de almacenamiento monotónico resistente a rollback y controles administrativos independientes. |
| Host Atlas comprometido mientras está autorizado | Puede solicitar avances falsos dentro de su autoridad; mitigar con aprobación, límites y auditoría, no afirmar que el ancla lo impide. |

## 8. Aprobación del propietario y cambio de época

Un cambio de `authority_epoch` no es una reparación automática ni una forma de ignorar un conflicto.

Debe requerir:
- explicación del incidente y evidencia disponible;
- selección explícita del estado que se quiere conservar;
- verificación de la cadena/archivo de recuperación elegido;
- aprobación explícita del propietario;
- registro de la transición que referencia el último registro externo conocido;
- incremento de época y revisión sin reutilizar identidades previas;
- modo de recuperación hasta completar la verificación posterior.

No se permite que un agente, una Skill, un archivo restaurado o el host local apruebe su propio cambio de época.

## 9. Política de disponibilidad y operaciones

La disponibilidad de la ECA es una dependencia de seguridad, no una optimización opcional.

El diseño de producto debe clasificar operaciones:
- **Lecturas no sensibles:** pueden tener una política degradada si no exponen datos ni confieren autoridad.
- **Mutaciones locales no críticas:** solo podrían continuar dentro de un presupuesto de riesgo explícitamente aprobado; deben permanecer marcadas como no ancladas.
- **Operaciones irreversibles, externas o privilegiadas:** deben exigir continuidad vigente y, si la política lo determina, un checkpoint anclado inmediatamente antes de ejecutarse.

No se debe resolver la indisponibilidad con fail-open, aceptación indefinida de recibos cacheados, generación de una nueva autoridad ni desactivación silenciosa de la verificación.

## 10. Privacidad y minimización

La ECA debe almacenar solo identificadores, revisiones, compromisos, referencias opacas, versiones y evidencia mínima de auditoría. No debe recibir contenido de memoria, mensajes, credenciales ni datos de proyectos en claro.

El archivo externo puede contener proyecciones necesarias para recuperación y debe:
- cifrarlas antes de salir del host;
- restringir lectura y escritura por identidad;
- usar objetos inmutables o versionados;
- verificar integridad al publicar y recuperar;
- tener retención y eliminación controladas;
- no compartir las credenciales de escritura con la autoridad.

La gestión de claves de cifrado y recuperación debe diseñarse separadamente. Perder la clave no se resuelve ignorando la autenticación.

## 11. Criterios de aceptación de diseño

ME-03L no debe pasar a implementación hasta que se pueda demostrar en un diseño revisado que:

1. Una restauración antigua coherente no puede ser declarada vigente solo por verificaciones locales.
2. La consulta de autoridad demuestra frescura y autenticidad, no solo integridad de un recibo archivado.
3. La ECA impone monotonicidad con compare-and-swap y no depende de SQLite ni del filesystem Atlas.
4. El archivo externo conserva los artefactos necesarios para recuperar el checkpoint que la ECA declara vigente.
5. El orden de publicación, avance de autoridad y commit local tiene resolución explícita para cada punto de caída.
6. Dos escritores concurrentes no pueden confirmar revisiones divergentes.
7. Indisponibilidad, conflicto, pérdida de archivo y cambio de época bloquean la activación de forma segura.
8. No se filtra contenido sensible a la autoridad.
9. Las operaciones que dependen de continuidad externa están clasificadas y tienen un RPO aprobado.
10. Las aprobaciones de recuperación y cambio de época pertenecen al propietario, fuera del flujo de autoaprobación del agente.

## 12. Decisiones pendientes antes de implementar

No asumir decisiones por defecto para los siguientes puntos:

- **ECA:** servicio remoto administrado, dispositivo/medio físico independiente u otra arquitectura.
- **Dominio de administración:** quién administra la autoridad y cómo se separa de la máquina Atlas.
- **Almacenamiento monotónico:** qué mecanismo impide restaurar silenciosamente el estado interno de la propia ECA.
- **Archivo externo:** proveedor, cifrado, retención, disponibilidad y recuperación de claves.
- **Identidad de Atlas:** autenticación de solicitudes de avance y revocación.
- **Firma de recibos:** algoritmo, formato, rotación y anclaje inicial de clave pública.
- **Cadencia:** intervalo de checkpoints y RPO aceptable.
- **Operaciones críticas:** cuáles exigen anclaje por operación.
- **Recuperación de sufijo:** cómo conservar o descartar transiciones locales posteriores al último checkpoint anclado.
- **Cambio de época:** ceremonia exacta de aprobación y recuperación.
- **Auditoría:** dónde se registra cada intento, avance, conflicto y reconciliación sin crear una dependencia circular.

## 13. Secuencia de trabajo propuesta

1. Revisar y aprobar el modelo de amenazas y las garantías exactas de este documento.
2. Elegir arquitectura ECA y archivo externo sin desplegarlos.
3. Especificar contratos de puertos, solicitud, recibo, consulta fresca y estados tipados.
4. Diseñar la máquina de estados de recuperación y las pruebas de fallos/concurrencia.
5. Implementar adaptadores en una rama de desarrollo aislada, con dobles de prueba primero.
6. Validar en entorno de desarrollo; la activación operativa queda como fase independiente y requiere autorización expresa.

**Regla de salida:** ningún componente externo se instala, ninguna credencial se crea y ninguna operación protegida cambia su política como consecuencia de aprobar este documento.