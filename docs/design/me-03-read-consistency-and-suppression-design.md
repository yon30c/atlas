# ME-03 — Diseño de consistencia para lecturas y supresión de memoria

**Estado:** propuesta técnica para revisión; no normativa ni implementada.  
**Rama de trabajo:** `implementation/me-01-to-me-04-memory-engine`  
**Alcance:** lectura versionada a través de MemoryGateway y su interacción con cambios de estado y Forget.  
**Fuera de alcance:** selección de base de datos, motor de índices, caché, proveedor de almacenamiento, despliegue, adapters reales y ejecución de Forget.

## 1. Problema observado

La ruta actual ejecuta esta secuencia:

1. `MemoryGatewayService.get_version()` obtiene la hora.
2. `MemoryAuthorizationService.authorize_read()` resuelve metadatos y autoriza.
3. Si CAM devuelve `ALLOW`, el Gateway llama a `MemoryVersionContentPort.get_version_content()`.
4. El Gateway valida IDs, estado `approved` y clasificación distinta de `RESTRICTED`.

La secuencia impide que una denegación ordinaria consulte el puerto de contenido, pero no constituye una operación atómica. Entre los pasos 2 y 3, o durante la lectura, la versión podría pasar a `superseded` o `forgotten`, cambiar su clasificación/metadatos, o quedar bajo supresión lógica. La comprobación final del objeto devuelto reduce algunos riesgos, pero no prueba que la comprobación y la entrega observen el mismo estado autoritativo.

## 2. Requisitos normativos que debe preservar

Esta propuesta se deriva de los contratos existentes; no los modifica:

- Toda lectura protegida atraviesa MemoryGateway y CAM.
- CAM autoriza el recurso concreto y falla cerrado ante ausencia, inconsistencia o error.
- Solo una versión `approved` puede ser leída; `pending_review`, `rejected`, `superseded` y `forgotten` no son conocimiento aprobado vigente.
- La aprobación de una versión nueva, el supersede de la anterior y el cambio del puntero vigente son atómicos.
- Una vez validada una solicitud de olvido, la supresión lógica debe impedir inmediatamente la exposición por rutas ordinarias, incluidas consultas, índices, cachés, exportaciones y recuperación.
- La supresión lógica debe mantenerse mientras la eliminación física y su verificación estén incompletas.
- Restauración, reindexación, replicación e importación deben aplicar la supresión antes de volver a exponer contenido.
- No puede declararse `forgotten` hasta completar la verificación de todos los destinos aplicables.

Referencias principales: `docs/contracts/memory.md` §§5.2–5.4, 7 y 9; DM-01 §§4.3–4.4 y 9.3.8–9.3.9; CT-05 y CT-08.

## 3. Objetivo de consistencia

Definir un punto de linealización para una lectura protegida y otro para la activación de supresión lógica, de forma que exista un orden observable entre ambos.

**Garantía mínima propuesta:** una lectura no puede comenzar a entregar contenido si, en su punto de validación atómica, la memoria o versión está suprimida, no está aprobada, tiene clasificación no permitida o sus metadatos ya no coinciden con los que CAM autorizó.

**Garantía para Forget aceptada por el propietario del proyecto:** al validar e iniciar Forget, la autoridad cierra inmediatamente nuevas admisiones y avanza el fencing del alcance afectado. Desde ese punto no puede emitirse ningún byte, fragmento o contenido pendiente de una admisión anterior. Una admisión solo cuenta como **completada** si toda su entrega terminó antes de que el cierre/fencing surtiera efecto; cualquier admisión que todavía pudiera emitir debe quedar cercada y confirmarse como **cancelada**. Forget confirma que la supresión lógica está aplicada únicamente después de verificar que todas las admisiones previas están en uno de esos estados terminales y que ningún punto de entrega puede reanudar una emisión antigua. Si no puede verificarse, la operación permanece no completada/fail-closed. Esta interpretación preserva la supresión inmediata exigida por CT-05 y no selecciona el mecanismo físico.

Esta garantía es más fuerte que consultar un tombstone antes de leer y luego recuperar contenido por separado: esa secuencia también tiene una carrera entre la consulta del tombstone y la entrega.

## 4. Diseño recomendado: autorización vinculada a una lectura condicional atómica

### 4.1 Snapshot de autorización

CAM debe producir, además de la decisión, un snapshot opaco e inmutable de los hechos que justificaron el permiso. Conceptualmente debe vincular como mínimo:

- `memory_id` y `version_id` exactos;
- `owner_id` y scope canónicos de Memory;
- `project_id` y entorno cuando apliquen;
- estado y clasificación de la versión;
- relación de la versión con su memoria;
- revisión/epoch de los metadatos usados para autorizar;
- identidad del actor y contexto de la operación;
- identificador/revisión de la decisión de autorización, si el repositorio de Grants permite obtenerlo.

El snapshot no contiene contenido ni concede permisos por sí mismo. Debe ser emitido por la ruta confiable CAM, no aceptado desde el solicitante. Su formato criptográfico, almacenamiento y caducidad quedan pendientes; no se debe inventar un token firmado sin seleccionar y aprobar antes el mecanismo de confianza.

### 4.2 Lectura condicional

El puerto de contenido debe evolucionar conceptualmente de una lectura incondicional por IDs a una operación equivalente a:

`read_version_if_visible(authorization_snapshot) -> MemoryVersion | None`

La operación debe comprobar en un mismo límite de consistencia:

1. IDs exactos de memoria y versión.
2. Que la versión siga perteneciendo a esa memoria.
3. Que la revisión/epoch de metadatos coincida con el snapshot autorizado.
4. Que la versión siga en estado `approved` y mantenga la clasificación autorizada.
5. Que no exista supresión lógica activa para la memoria ni para la versión.
6. Que el mecanismo de lectura/supresión otorgue una admisión válida que cubra la entrega, no solo la consulta inicial.

Si una condición falla, devuelve ausencia genérica y no entrega contenido. No debe degradarse a una lectura sin snapshot ni a un fallback de ID solamente.

### 4.3 Autoridad de supresión

La supresión lógica debe ser una autoridad consultada obligatoriamente por todas las rutas capaces de volver a exponer contenido. No basta con marcar una fila en el almacén primario si índices, cachés, réplicas, exportaciones o restauraciones pueden responder sin comprobarla.

El diseño debe permitir suprimir por identificadores opacos de memoria/versión y conservar solo los metadatos mínimos exigidos por CT-05. No almacenar contenido olvidado, fragmentos ni hashes de contenido como sustituto del tombstone.

El estado operativo de supresión no debe introducir un nuevo estado normativo de `MemoryVersion`. `forgotten` continúa significando olvido físico verificado y completado, no solicitud recibida ni supresión provisional.

### 4.4 Coordinación con lecturas en curso

Una lectura admitida debe tener una duración/lease acotada o una forma equivalente de coordinación. Al comenzar Forget, el sistema cierra nuevas admisiones y avanza el fencing de inmediato. Ninguna emisión posterior puede atravesar ese cierre. Las admisiones cuya entrega terminó antes del cierre se registran como completadas; las demás deben ser cercadas y confirmadas como canceladas. Solo después de que todas las admisiones previas sean terminales y los puntos de entrega confirmen el fencing puede confirmarse que la supresión lógica está aplicada.

Si una lectura no responde, el proceso cae o no puede determinarse si todavía puede entregar contenido, Forget no puede confirmar la supresión. La recuperación debe conservar el bloqueo de nuevas lecturas hasta reconciliar de forma segura las admisiones pendientes. La semántica exacta de cancelación, expiración, bloqueo y recuperación tras caída queda pendiente. No se debe elegir un mecanismo de locks distribuidos, leases, transacciones o mensajería hasta definir los requisitos operativos y el proveedor.

### 4.5 Autoridad lógica de admisión y supresión — recomendación de diseño

Se recomienda modelar una única **autoridad lógica de supresión y admisión de lecturas**, separada conceptualmente de:

- `MemoryMetadataPort`, que sigue siendo autoridad de los metadatos canónicos de memoria;
- CAM, que decide si el actor puede realizar la operación;
- los almacenes, índices, cachés y demás destinos, que conservan o derivan contenido.

Esta separación evita convertir los metadatos de memoria en un registro operativo de Forget y evita que cada destino mantenga una interpretación independiente del estado de supresión. No implica elegir un servicio, base de datos, protocolo de red ni topología física.

El límite lógico debe serializar dos operaciones incompatibles:

1. **Admitir lectura:** aceptar una lectura solo si no hay supresión activa ni una operación de Forget que haya cerrado nuevas admisiones para la memoria/versión.
2. **Cerrar admisiones para Forget:** impedir nuevas lecturas y enumerar o contabilizar todas las lecturas admitidas previamente que todavía no estén en estado terminal.

Cada lectura debe conservar una admisión vinculada a los IDs exactos y al snapshot CAM durante todo el periodo en que pueda entregar contenido. La admisión no sustituye CAM ni constituye por sí misma autorización. Su propósito es coordinar concurrencia y supresión.

Una admisión solo puede terminar en uno de estos resultados verificables:

- **Completada:** toda la entrega terminó antes de que el cierre/fencing de Forget surtiera efecto; no quedan bytes, fragmentos ni trabajo pendiente que esa operación pueda emitir.
- **Cancelada:** la admisión no había terminado al surtir efecto el cierre; todos sus puntos de entrega confirman que las emisiones posteriores fueron cercadas y que no puede continuar entregando contenido.

Forget solo puede confirmar la supresión lógica cuando la autoridad haya cerrado nuevas admisiones y todas las admisiones previas afectadas estén en estado terminal. La operación de cierre y el registro de admisiones deben compartir un mismo orden de consistencia: no puede existir una lectura que se cuele entre el cierre y el inventario de lecturas previas.

La admisión debe cubrir también rutas derivadas que entreguen contenido —por ejemplo, cachés, búsquedas con fragmentos, exportaciones y recuperación—, no solo el almacén primario. Los índices que devuelvan únicamente candidatos opacos todavía deben pasar por Gateway antes de exponer contenido o metadatos protegidos.

Si la autoridad lógica no está disponible, no se admiten lecturas ni se confirma supresión. Si un proceso cae y deja una admisión sin estado terminal verificable, esta permanece pendiente y bloquea la confirmación de Forget hasta que un mecanismo seguro de recuperación demuestre que ya no puede emitir contenido. No se debe liberar una admisión únicamente porque haya vencido un timeout, salvo que el mecanismo aprobado pueda demostrar que el emisor quedó efectivamente cercado (*fenced*) y no puede reanudar la entrega.

**Límite de la garantía:** esta coordinación impide nuevas exposiciones después de confirmar la supresión y resuelve entregas que estaban en curso dentro del sistema. No puede retirar copias que un consumidor ya recibió legítimamente antes de comenzar Forget.

**Dirección de diseño aceptada por el propietario del proyecto:** adoptar una única autoridad lógica de admisión y supresión, independiente de los proveedores físicos y responsable de serializar admisiones, cierre por Forget y resolución verificable de lecturas en curso. Esta aceptación fija la arquitectura lógica objetivo; no la convierte por sí sola en contrato normativo ni selecciona un mecanismo de implementación.

### 4.6 Recuperación de admisiones abandonadas — propuesta

La expiración de una lease no demuestra que el proceso titular haya dejado de ejecutarse. Un proceso pausado puede reanudarse después del timeout; por tanto, una lease vencida no debe convertir automáticamente una admisión pendiente en cancelada.

Se propone utilizar **generaciones de admisión y fencing** como abstracción lógica, sin fijar todavía su implementación:

1. Cada admisión recibe un identificador único y queda vinculada a una generación vigente de la memoria/versión.
2. Al comenzar Forget, la autoridad cierra nuevas admisiones e incrementa la generación o emite una época de fencing superior, invalidando todas las admisiones anteriores para futuras entregas.
3. Todo punto capaz de emitir contenido debe validar la generación vigente antes de permitir la entrega. No puede existir una ruta de salida que acepte contenido de una admisión antigua sin comprobar ese fencing.
4. La autoridad solo marca una admisión antigua como cancelada cuando el sistema de entrega confirma que el token quedó cercado y que el emisor ya no puede producir más contenido.
5. Si el proceso antiguo se reanuda, sus intentos de continuar deben ser rechazados por el punto de entrega, incluso si el proceso conserva memoria local o una respuesta previamente preparada.

El fencing debe cubrir la salida completa, no solo la lectura del almacén: streaming, buffers administrados por la aplicación, fragmentos, exportaciones y cualquier otro canal que pueda seguir emitiendo contenido. Antes de confirmar la supresión también deben quedar resueltos los datos ya aceptados por componentes intermedios que todavía puedan entregarse al consumidor.

**Caída del coordinador:** el reinicio no debe asumir que las admisiones desaparecieron. Debe recuperar el estado durable de cierre, generación y admisiones; mantener cerrado el acceso mientras reconcilia estados; y volver a cercar cualquier admisión cuyo resultado no sea verificable.

**Condición de seguridad:** si no existe un punto de entrega que pueda hacer cumplir fencing de forma verificable, el sistema no puede declarar cancelada una admisión abandonada ni confirmar la supresión lógica. Debe permanecer bloqueado/fail-closed.

Esta propuesta no afirma que un contador, token, lease o registro local sea suficiente por sí solo. La propiedad decisiva es que un emisor antiguo no pueda reanudar la entrega después de que Forget haya confirmado la supresión.

**Garantía de fencing aceptada por el propietario del proyecto:** todo punto capaz de emitir contenido protegido DEBE validar y hacer cumplir el fencing vigente para la admisión concreta antes de cada emisión efectiva. La validación debe estar acoplada al límite que autoriza la emisión, de modo que no exista una ventana entre comprobar el token y entregar bytes en la que una generación antigua pueda continuar. Una comprobación única al iniciar el stream no es suficiente si después pueden producirse nuevas emisiones.

La cobertura incluye, cuando existan, respuestas completas, streaming, fragmentos, buffers de aplicación, colas de salida, exportaciones, descargas, cachés con contenido y cualquier intermediario que conserve capacidad de entregar contenido al consumidor. Los componentes que solo transporten datos deben preservar la identidad de la admisión y no pueden convertir una autorización antigua en una entrega independiente. Si un canal no puede validar el fencing de forma verificable, no puede transportar contenido protegido dentro de una operación cuya supresión vaya a declararse completada.

La generación/fencing se vincula al conjunto exacto de recursos afectados por la operación de Forget. Un Forget de memoria debe cubrir todas las versiones, propuestas, referencias y destinos que formen parte de su alcance; un Forget de versión no debe ampliar silenciosamente su alcance a otras memorias o versiones. La resolución del conjunto afectado debe proceder de metadatos canónicos y del inventario de destinos, no de una lista aportada por el solicitante.

La autoridad debe mantener durablemente el cierre y la generación vigente. Una caída o reinicio no reinicia generaciones ni reabre admisiones por defecto. La recuperación conserva el cierre, reconcilia admisiones y puntos de entrega, y solo permite avanzar cuando cada emisor previo esté completado o efectivamente cercado. Los acknowledgements de fencing deben estar vinculados a la admisión/generación y al punto de entrega que los emite; una confirmación genérica de proceso detenido no basta si buffers o intermediarios todavía pueden entregar datos.

La garantía se refiere a emisiones futuras controladas por Atlas. No puede retirar bytes o copias que un consumidor ya recibió legítimamente antes de que comenzara Forget. Los buffers o datos aún bajo control de Atlas sí deben drenarse, descartarse o quedar cercados antes de confirmar la supresión.

Esta garantía es un requisito de arquitectura aceptado, no una afirmación de que el código actual disponga de fencing ni una selección de su mecanismo físico.

### 4.7 Revocación de autorización durante una lectura admitida — recomendación adoptada

La admisión de una lectura no debe convertir una autorización CAM revocable en un permiso irrevocable durante toda la vida del stream. El snapshot CAM vincula la decisión que permitió iniciar la operación, pero no debe impedir que una suspensión de identidad, revocación de Grant, expiración aplicable o cambio de autoridad detenga entregas futuras.

Se adopta como dirección de diseño que:

1. La admisión conserva la identidad del actor, el recurso exacto y la revisión/época de autorización que justificó el acceso.
2. Una revocación, suspensión o invalidación de esa autoridad debe invalidar las admisiones afectadas para emisiones futuras.
3. Cada punto de entrega debe hacer cumplir tanto el fencing de supresión/Forget como la vigencia de la autorización vinculada a la admisión. Son controles independientes: superar uno no sustituye al otro.
4. Una admisión invalidada por revocación solo puede considerarse cancelada cuando los puntos de entrega confirmen que ya no pueden emitir contenido. Se aplica la misma regla de buffers e intermediarios que para Forget.
5. Si no puede comprobarse la vigencia de autorización en el límite requerido, no se entrega contenido adicional. No se renueva ni sustituye silenciosamente el snapshot dentro de la misma admisión; una nueva lectura requiere una nueva operación y autorización CAM.

Esta recomendación no cambia la regla de que CAM autoriza cada recurso concreto, ni convierte el snapshot en un Grant. Tampoco decide todavía cómo se propagan las revisiones de Grants/identidades ni qué mecanismo técnico comunica su revocación a los puntos de entrega.

### 4.8 Revisiones canónicas de metadatos — recomendación adoptada

Los snapshots de autorización necesitan detectar cualquier cambio en los hechos canónicos que CAM utilizó. Se adopta una revisión monotónica por agregado/autoridad como abstracción lógica; no se fija su representación física.

El snapshot debe vincular revisiones independientes para todos los hechos mutables que puedan cambiar la decisión o la visibilidad:

- Memory: propietario, scope, proyecto y puntero a la versión aprobada vigente.
- MemoryVersion: pertenencia a la memoria, estado y clasificación. Aunque el contenido de una versión sea inmutable, sus transiciones de estado requieren una nueva revisión de metadatos.
- Project y Environment: estado y atributos que condicionen el acceso.
- Identity: estado y revisión de autoridad del actor autenticado.
- Grant: identidad exacta del Grant, alcance, acciones, vigencia, revocación y revisión aplicable.
- Supresión/admisión: generación de fencing y estado de cierre del conjunto de recursos.

Cada cambio que pueda afectar autorización o visibilidad DEBE incrementar la revisión correspondiente en la misma operación lógica que hace efectivo el cambio. No se permite reutilizar revisiones, retrocederlas ni inferir que un valor idéntico implica que no hubo cambio. El cambio del puntero vigente, el supersede y la revisión del agregado Memory deben permanecer coherentes con la atomicidad ya exigida por DM-01.

La validación no compara solo un número aislado: comprueba identidad exacta, relación padre/hijo y revisión de cada autoridad implicada. Una revisión ausente, repetida, regresiva, no verificable o incoherente produce rechazo. Una nueva autorización debe crear una nueva admisión; no se reescribe el snapshot anterior.

Los snapshots son pruebas de los hechos evaluados, no permisos autónomos. Su integridad y origen deben estar protegidos por la frontera confiable, pero esta decisión no selecciona firma, MAC, formato de token ni proveedor criptográfico.

### 4.9 Revocación y expiración durante la entrega — semántica adoptada

Se adopta la siguiente regla de orden: una revocación, suspensión, reducción de alcance o expiración aplicable debe invalidar las admisiones afectadas para cualquier emisión posterior. El punto efectivo de revocación debe quedar serializado respecto de las emisiones, no depender de propagación eventual no verificable.

Para una transición administrativa de Identity o Grant, el sistema debe cerrar o invalidar las admisiones afectadas y obtener fencing de los puntos de entrega antes de considerar efectiva la transición frente a contenido protegido. Esto no autoriza a retrasar indefinidamente una revocación: si no puede detenerse una ruta, se bloquea esa ruta y se falla cerrado. En ningún caso una identidad REVOKED puede seguir participando en operaciones dependientes, ni una identidad SUSPENDED puede ampliar o continuar una operación más allá del punto seguro permitido por CT-01.

La expiración no necesita una mutación administrativa: cada emisión debe comprobar que el instante confiable no excede la vigencia del Grant y que la revisión/época sigue vigente. Si el reloj confiable no está disponible o su resultado es ambiguo, no se emite contenido. Los límites de expiración conservan la semántica exacta del contrato de Grant; esta propuesta no inventa tolerancias ni periodos de gracia.

La autoridad lógica de admisión/supresión coordina la invalidez y el fencing, pero CAM conserva la responsabilidad de decidir si la acción está autorizada. La autoridad de admisión no crea Grants, no interpreta políticas alternativas y no sustituye la reevaluación CAM para una nueva lectura.

No se admite una ventana en la que una revocación ya efectiva en la fuente autoritativa todavía permita emisiones por retraso de una notificación. La implementación deberá lograr orden consistente entre cambio autoritativo, avance del fencing y emisión. Si no puede demostrarlo, la transición o la emisión queda bloqueada; no se acepta consistencia eventual para este límite de seguridad.

### 4.10 Inventarios separados y evidencia de cobertura — recomendación adoptada

Se mantendrán dos inventarios relacionados, pero distintos:

**A. Inventario de persistencia y derivados:** almacenes primarios, versiones/copias históricas, índices, embeddings, cachés persistentes, réplicas, backups, exportaciones y cualquier otro lugar donde el contenido pueda sobrevivir o reconstruirse. Determina el alcance de eliminación y verificación física conforme a CT-05.

**B. Inventario de rutas de entrega:** Gateway, endpoints, respuestas completas, streaming, fragmentos, buffers, colas, exportaciones/descargas, cachés que sirvan contenido, intermediarios y cualquier componente que pueda emitir o liberar contenido a un consumidor. Determina el alcance de admisión, revocación y fencing.

Cada entrada debe identificar responsable lógico, tipo de capacidad, recursos/ámbitos que puede contener o entregar, rutas de entrada/salida, mecanismo de supresión o fencing requerido y evidencia de verificación. Los nombres de tecnologías concretas y los adaptadores permanecen pendientes hasta que exista un inventario real.

La cobertura no se prueba únicamente enumerando componentes conocidos. Cada ruta de lectura/entrega debe poder trazarse desde la entrada pública hasta el último punto que puede liberar contenido; cada destino de persistencia debe tener un responsable y un procedimiento de verificación. Los componentes inexistentes deben registrarse como no aplicables con evidencia de alcance, no omitirse silenciosamente.

Todo componente que pueda entregar contenido protegido y no esté registrado o no pueda demostrar fencing queda fuera de servicio para ese contenido. Todo destino de persistencia desconocido o no verificable impide declarar Forget completado. El inventario debe revisarse cuando se agregue, quite o cambie una ruta, adaptador, exportación, integración, backup o mecanismo de recuperación.

La evidencia de cobertura puede demostrar qué se inspeccionó y qué se encontró; no debe incluir contenido olvidado, payloads, hashes de contenido ni datos privados innecesarios.

### 4.11 Protocolo lógico de orden, emisión y recuperación — recomendación adoptada

Esta sección fija la semántica observable que deberán respetar los futuros puertos y adaptadores. No prescribe transacciones, base de datos, transporte, protocolo de red ni topología.

#### 4.11.1 Punto de compromiso de emisión

Se define **compromiso de emisión** (*egress commit*) como el instante en que el último punto de control de Atlas acepta irrevocablemente una unidad de contenido para entregarla al transporte o consumidor siguiente. En una respuesta completa puede ser el cuerpo completo; en streaming puede ser cada fragmento; en una exportación puede ser cada bloque o unidad publicada.

Toda unidad debe pasar por una operación lógica indivisible que:

1. Identifique la admisión, recurso, generación y punto de entrega exactos.
2. Compruebe que la admisión no fue cerrada ni invalidada por Forget, revocación, cambio de revisión o expiración.
3. Compruebe el tiempo confiable y las revisiones vigentes que correspondan.
4. Ordene el compromiso de emisión respecto de los cierres e invalidaciones.
5. Registre un resultado correlacionado antes de permitir que el punto de entrega libere esa unidad.

No es suficiente comprobar el token al abrir una respuesta, stream o exportación. Tampoco es válido comprobarlo y después liberar datos mediante una cola o buffer que pueda emitirlos sin volver a pasar por el punto de compromiso.

**Regla de orden:** para cada recurso y ámbito de invalidación debe existir un orden total observable entre los compromisos de emisión y el cierre/fencing. Si el compromiso precede al cierre, esa unidad cuenta como emitida antes del cierre. Si el cierre precede al compromiso, la unidad se rechaza. No existe un tercer resultado que permita liberar contenido mientras se resuelve la carrera.

El límite de Atlas es el último punto de entrega controlado. Los bytes cuyo compromiso de emisión se completó antes del cierre pueden llegar físicamente al consumidor después por latencia del transporte; Atlas no puede retirar datos que ya cruzaron ese límite. En cambio, ningún buffer, cola o intermediario que siga bajo control de Atlas puede liberar unidades no comprometidas después del cierre.

Si el resultado de un compromiso es ambiguo —por ejemplo, se pierde la confirmación y no puede saberse si el transporte aceptó la unidad—, la admisión queda **no resuelta**. No puede declararse completada ni cancelada hasta reconciliar evidencia del punto de entrega. Forget y las transiciones afectadas permanecen pendientes/fail-closed mientras esa incertidumbre pueda permitir una emisión.

#### 4.11.2 Ciclo de vida lógico de una admisión

Cada admisión se vincula a un identificador único, recurso(s) exactos, actor, snapshot CAM, revisiones de autoridades, generación de fencing y conjunto de puntos de entrega autorizados.

Estados lógicos monotónicos:

- **ADMITTED:** la autoridad aceptó la lectura después de CAM y registró la admisión.
- **ACTIVE:** al menos un punto de entrega puede solicitar compromisos de emisión para esa admisión.
- **COMPLETED:** se comprometió el final de la entrega y no queda ninguna unidad, buffer o trabajo pendiente que pueda emitir contenido.
- **CANCELLED:** un cierre o invalidación precedió al final de la entrega y todos los puntos de entrega confirmaron que la admisión quedó cercada y no puede emitir más.
- **UNRESOLVED:** el estado de uno o más puntos no puede determinarse. Es no terminal y bloquea cualquier operación que requiera demostrar la ausencia de emisiones futuras.

Reglas:
- ADMITTED -> ACTIVE -> COMPLETED es la ruta normal.
- ADMITTED o ACTIVE -> CANCELLED solo después de fencing verificable de todos los puntos aplicables.
- Cualquier transición incierta puede quedar UNRESOLVED; solo puede salir mediante reconciliación con evidencia correlacionada.
- COMPLETED y CANCELLED son terminales e incompatibles. No se reabren ni se sustituyen.
- Un acknowledgement tardío, duplicado o de otra generación no puede alterar una admisión terminal.
- La expiración de lease, timeout, heartbeat perdido o caída aparente no constituyen por sí mismos evidencia de CANCELLED.

#### 4.11.3 Cierre por Forget

El inicio autorizado de Forget produce, en este orden lógico:

1. Validar CAM y la prueba directa y no delegable del propietario para el objetivo exacto, conforme a DM-01.
2. Registrar durablemente la intención de cierre y el conjunto exacto de recursos afectados.
3. Cerrar nuevas admisiones y avanzar el fencing del alcance. Desde ese punto, todo nuevo compromiso de emisión queda rechazado.
4. Cercar las admisiones previas que no hayan completado su entrega y obtener confirmación correlacionada de todos sus puntos de entrega.
5. Confirmar **supresión lógica aplicada** únicamente cuando el cierre es efectivo, ninguna admisión previa puede emitir y todos los puntos de entrega aplicables están cercados o han confirmado su finalización.
6. Ejecutar eliminación física y verificación por el inventario de persistencia, según CT-05. Solo después de verificar todos los destinos aplicables se puede completar Forget y reflejar forgotten.

El paso 3 aplica el bloqueo lógico inmediatamente: mientras no exista confirmación completa del paso 5, el estado público/operativo es pendiente y no se comunica éxito. La indisponibilidad de un punto de entrega no permite saltar pasos; ese punto debe permanecer bloqueado para contenido protegido.

#### 4.11.4 Revocación, suspensión, reducción de alcance y cambios canónicos

Toda mutación que pueda invalidar una admisión debe participar en el mismo orden lógico de emisiones:

- La solicitud aceptada de suspensión, revocación o reducción de alcance bloquea nuevas admisiones afectadas y compromisos de emisión posteriores.
- La actualización canónica de Identity/Grant y su nueva revisión deben quedar vinculadas a la época de invalidación. No puede existir una ventana en la que la fuente autoritativa ya haya aplicado el cambio, pero un punto de entrega todavía acepte una revisión antigua.
- Si no se puede ordenar la mutación y el fencing respecto de las emisiones, la ruta afectada se bloquea y falla cerrado; no se acepta propagación eventual como sustituto.
- La expiración de Grant se evalúa en cada compromiso de emisión mediante tiempo confiable y las reglas exactas del contrato de Grant. Una admisión previa no prolonga la vigencia.
- Si no hay tiempo confiable, revisión vigente o evidencia de fencing, no se comprometen nuevas unidades.

La autoridad de admisión coordina el orden y el fencing; CAM conserva la decisión de autorización. Ninguno sustituye al otro.

#### 4.11.5 Recuperación y evidencia mínima

El registro lógico recuperable debe permitir reconstruir, sin contenido protegido:

- ID de operación y clave de idempotencia;
- objetivo exacto y alcance de recursos;
- estado de la operación y su secuencia de transición;
- ID de admisión, actor y correlación con el snapshot CAM;
- revisiones/épocas y generación de fencing;
- puntos de entrega participantes;
- secuencia/ID de cada compromiso de emisión cuando aplique;
- acknowledgements de finalización o fencing, vinculados a admisión, generación y punto de entrega;
- resultado de reconciliación y evidencia mínima de cobertura.

Las escrituras repetidas con la misma clave y el mismo objetivo devuelven el resultado de la operación existente; la misma clave con un objetivo diferente se rechaza. Los eventos duplicados o fuera de orden no pueden hacer retroceder estados ni cerrar una operación sin evidencia completa.

Después de reiniciar, la autoridad restaura cierres y generaciones antes de admitir tráfico. Las admisiones no terminales se recuperan como pendientes/no resueltas hasta reconciliarlas con todos sus puntos. Si un punto no puede demostrar su estado, permanece deshabilitado para contenido protegido. No se recrean admisiones antiguas ni se reutilizan generaciones.

La evidencia no debe contener payloads, fragmentos, contenido olvidado ni hashes de contenido. La evidencia de entrega y la evidencia de eliminación física son conjuntos distintos y no se sustituyen mutuamente.

## 5. Reglas de fallo cerrado

- Snapshot ausente, inválido, caducado o con IDs distintos: no leer.
- Revisión de metadatos cambiada: no leer; solicitar nueva autorización en una operación nueva.
- Estado distinto de `approved`: no leer.
- Clasificación distinta de la autorizada o `RESTRICTED`: no leer.
- Supresión no disponible, timeout o respuesta inconsistente: no leer.
- No se puede confirmar el límite atómico entre validación y lectura: no leer.
- Cache, índice, réplica o destino derivado no puede verificar supresión: no exponer contenido.
- Un proceso de restauración/reindexación no puede comprobar supresión: bloquear publicación/visibilidad.
- No se puede drenar o cancelar una lectura en curso: Forget no puede declarar aplicada la barrera.

La respuesta pública debe seguir evitando distinguir denegación, inexistencia y no disponibilidad cuando esa distinción pueda revelar la existencia de una memoria protegida.

## 6. Consecuencias para la implementación actual

La implementación avanzó parcialmente respecto de la línea base inicial:

- `AuthorizationResult` ahora exige un `AuthorizationSnapshot` cuando la decisión es ALLOW.
- Memory, MemoryVersion, Identity, Project, Environment y Grant tienen revisiones representadas en el snapshot según el ámbito aplicable.
- El puerto anterior `MemoryVersionContentPort.get_version_content()`, que recuperaba una versión completa por IDs, fue retirado.
- `ProtectedMemoryContentPort.read_version_if_admitted(snapshot, admission)` sustituye esa lectura por IDs y devuelve un handle opaco vinculado al objetivo y admisión exactos.
- `MemoryGatewayService.get_version()` coordina CAM, admisión y lectura condicional; devuelve `ProtectedMemoryRead`, no `MemoryVersion`.
- El Gateway expone `emit_version()`, `finish_version()` y `reconcile_version()` para compromisos de entrega y acknowledgements correlacionados.
- La expiración de Grant se comprueba en el Gateway en cada emisión como defensa adicional; el último punto de egress sigue obligado a validarla atómicamente junto con revisiones, supresión y fencing.

Estos cambios eliminan la ruta directa de contenido crudo en el Gateway implementado, pero **no constituyen todavía una garantía completa de consistencia ni supresión**:

- No hay adaptador real/durable de `ReadConsistencyAuthorityPort` ni de `ProtectedEgressPort`.
- El fake de pruebas es de proceso único y no demuestra persistencia, recuperación, fencing entre procesos ni transporte real.
- La comprobación efectiva de supresión debe formar parte de la admisión autoritativa; no existe todavía un servicio/operación completa de Forget ni una autoridad de supresión implementada.
- El inventario real de rutas de entrega y de destinos de persistencia/derivados, cachés, índices, réplicas, exportaciones y backups sigue pendiente.
- No se han ejecutado las pruebas añadidas para el flujo protegido ni se ha validado runtime.

Por tanto, la implementación actual demuestra la estructura de integración y el fail-closed de sus límites locales; no demuestra consistencia concurrente, fencing distribuido ni supresión global.

## 7. Plan de verificación propuesto

Antes de integrar un proveedor real, construir pruebas deterministas con puertos falsos coordinados por barreras:

| Caso | Intercalado | Resultado exigido |
|---|---|---|
| C01 | La versión cambia a `superseded` después de CAM y antes de lectura condicional | No se entrega contenido |
| C02 | La versión cambia a `forgotten` después de CAM | No se entrega contenido |
| C03 | Se activa supresión de memoria entre CAM y lectura | No se entrega contenido |
| C04 | Se activa supresión de versión entre CAM y lectura | No se entrega contenido |
| C05 | Cambia la revisión de metadatos | Snapshot rechazado |
| C06 | El servicio de supresión no responde | Fail closed |
| C07 | La lectura se admite primero y Forget empieza después | Forget bloquea nuevas admisiones; espera finalización verificable o cancelación confirmada antes de confirmar la supresión |
| C08 | Forget activa la barrera primero y llega una lectura después | Lectura rechazada; no se entrega contenido |
| C09 | Se intenta restaurar/reindexar contenido suprimido | No se publica ni expone |
| C10 | El destino derivado no puede consultar la supresión | No expone contenido |
| C11 | Una admisión de generación anterior intenta emitir después de que Forget incrementó el fencing | El punto de entrega rechaza la emisión, aunque el emisor conserve buffers o estado local |
| C12 | Un stream valida fencing al abrirse, pero intenta emitir un fragmento después del cierre | El fragmento no se entrega; validar solo al abrir el stream no satisface la garantía |
| C13 | Un buffer o cola intermedia conserva contenido de una admisión invalidada | El contenido se descarta o queda cercado; no puede alcanzar al consumidor |
| C14 | Un punto de entrega no confirma fencing o su confirmación no identifica admisión/generación | La admisión sigue pendiente y Forget no confirma supresión |
| C15 | El coordinador cae después de cerrar admisiones y avanzar generación | Tras reinicio, el cierre se conserva; no se admiten lecturas hasta reconciliar admisiones y puntos de entrega |
| C16 | El proceso emisor se pausa, vence su lease y luego se reanuda | No se declara cancelado por timeout; la emisión antigua es rechazada por fencing |
| C17 | Un destino/canal existente no figura en el inventario o no puede demostrar fencing | No se declara cobertura global ni se confirma supresión |
| C18 | Forget de memoria afecta varias versiones, propuestas y destinos | El cierre cubre el conjunto completo autorizado; ninguna versión o ruta derivada queda accesible |
| C19 | Forget de una versión concreta | El cierre afecta exactamente el alcance autorizado y no amplía silenciosamente la supresión a otras versiones |
| C20 | Llegan acknowledgements duplicados, tardíos o de una generación distinta | No alteran el estado terminal de otra admisión ni permiten confirmar con evidencia no correlacionada |
| C21 | Se revoca el Grant después de admitir una lectura y antes del siguiente fragmento | El punto de entrega rechaza nuevas emisiones y la admisión no se considera cancelada hasta confirmación de fencing |
| C22 | La identidad del actor pasa a SUSPENDED o REVOKED durante una lectura | Se detienen nuevas emisiones; no se conserva el permiso por el snapshot inicial |
| C23 | No se puede consultar/verificar la vigencia de autorización para una emisión | No se entrega contenido adicional; no se renueva el snapshot por fallback |
| C36 | Un compromiso de emisión y un cierre por Forget compiten simultáneamente | Ambos quedan ordenados: si el cierre gana, la unidad se rechaza; si el compromiso gana, esa unidad cuenta como emitida antes del cierre |
| C37 | Se pierde el acknowledgement después de solicitar liberar una unidad | La admisión queda UNRESOLVED; no se presume que la unidad no fue emitida |
| C38 | Una cola contiene fragmentos no comprometidos cuando se activa el fencing | Los fragmentos pendientes se descartan y no cruzan el último punto de entrega |
| C39 | Un stream termina y después llega un acknowledgement duplicado o tardío | El estado terminal COMPLETED/CANCELLED no cambia |
| C40 | Forget se reintenta con la misma clave y el mismo objetivo | Se devuelve la misma operación y no se crea un segundo cierre incompatible |
| C41 | Se reutiliza la clave de idempotencia para otro objetivo | La solicitud se rechaza; no se modifica el alcance original |
| C42 | Tras reinicio existe una admisión sin evidencia completa de terminalidad | Se restaura como UNRESOLVED; no se reabre tráfico ni se confirma supresión |
| C43 | La expiración del Grant ocurre entre dos fragmentos de un stream | El siguiente compromiso de emisión se rechaza según el límite temporal contractual |
| C44 | Una revocación/suspensión es aceptada mientras un compromiso de emisión compite | El orden autoritativo determina el ganador; ninguna emisión puede comprometerse después del punto efectivo de invalidación |
| C24 | Cambia la revisión de Memory o MemoryVersion después de emitir el snapshot CAM | La admisión basada en la revisión anterior se rechaza; se requiere nueva autorización y admisión |
| C25 | Cambia el estado del Project o Environment que participó en CAM | La revisión de autoridad no coincide y no se emite contenido |
| C26 | Se revoca o reduce un Grant durante un stream | La revocación y el fencing se ordenan antes de cualquier emisión posterior; si no puede probarse, la ruta se bloquea |
| C27 | Una Identity pasa a SUSPENDED durante una operación dependiente | Se detiene la ampliación y se alcanza el punto seguro definido por CT-01; no se permiten emisiones fuera de ese límite |
| C28 | Una Identity pasa a REVOKED durante una operación dependiente | No puede continuar participando; toda emisión posterior queda cercada |
| C29 | Un Grant expira entre dos fragmentos o el reloj confiable no está disponible | No se emite el siguiente fragmento; no se concede periodo de gracia implícito |
| C30 | El inventario de rutas de entrega omite un intermediario o canal capaz de emitir | La cobertura no se considera completa y el componente no sirve contenido protegido |
| C31 | Un destino de persistencia/backup no está inventariado o no puede verificarse | Forget permanece incompleto y la supresión lógica se conserva |
| C32 | Un componente se declara no aplicable en un inventario | Se exige evidencia de que no persiste ni puede entregar contenido dentro del alcance declarado |
| C33 | Forget cierra admisiones mientras un stream tiene fragmentos pendientes en buffers | El fencing impide entregar cualquier fragmento después del cierre; la admisión solo termina como cancelada |
| C34 | La última emisión de una lectura termina antes del cierre y su confirmación llega después | Puede registrarse completada solo con evidencia correlacionada de que la entrega terminó antes del punto de cierre |
| C35 | Un emisor intenta marcar completada una admisión después del cierre aunque conserve bytes pendientes | La finalización se rechaza; debe confirmarse fencing/cancelación de todos los puntos de entrega |

Las pruebas de concurrencia deben usar eventos/barreras explícitas, no sleeps ni temporizadores, para que los intercalados sean reproducibles.

## 8. Decisiones pendientes antes de implementar

Los bloqueos conceptuales de revisiones, revocación, inventarios y protocolo de emisión quedan especificados en §§4.8–4.11. Antes de implementar siguen siendo necesarios trabajos de contrato, inventario y evidencia:

1. Traducir las revisiones canónicas y el snapshot a contratos de puertos tipados, manteniendo separados los hechos y autoridades que representa cada revisión.
2. Traducir el protocolo de compromiso de emisión, cierre e invalidación a contratos de puertos; el orden lógico está definido, pero no se ha seleccionado su mecanismo físico.
3. Completar por inspección el inventario real de persistencia/derivados y el inventario real de rutas de entrega.
4. Definir evidencia verificable por tipo de destino para eliminación física, reconciliación y restauración, incluidos backups.
5. Traducir el registro lógico de admisiones, compromisos, cierres y acknowledgements a un contrato durable e idempotente.
6. Derivar y ejecutar pruebas deterministas para los casos C01–C44 antes de integrar adaptadores reales.

**Decisión 1 — aceptada y precisada:** al iniciar Forget se cierran nuevas admisiones y se aplica fencing inmediato. Una lectura previa solo se considera completada si terminó toda su entrega antes de ese cierre; de lo contrario debe cancelarse con confirmación verificable de que no puede emitir más contenido. No se confirma la supresión lógica mientras alguna admisión previa pueda entregar contenido o su estado no pueda determinarse.

**Decisión 2 — aceptada:** la dirección de diseño será una autoridad lógica única que coordine admisión de lecturas y supresión. Su mecanismo físico, disponibilidad y recuperación ante fallos siguen pendientes de diseño.

**Decisión 3 — aceptada:** toda ruta de entrega de contenido debe aplicar fencing verificable de la admisión/generación vigente en cada punto efectivo de emisión. Las admisiones antiguas solo pueden declararse canceladas cuando todos los puntos de entrega relevantes confirmen que no pueden continuar emitiendo; el timeout o la caída aparente del emisor no bastan.

**Decisión 4 — recomendación adoptada para continuar el diseño:** el cierre de Forget, el avance de generación y el registro de admisiones deben ser recuperables de forma durable y conservarse cerrados tras reinicios hasta reconciliación. La recuperación no puede inferir finalización a partir de expiración de lease, pérdida de heartbeat o desaparición temporal de un proceso.

**Decisión 5 — recomendación adoptada para continuar el diseño:** cada admisión debe estar correlacionada con un identificador único, el conjunto exacto de recursos afectados, la generación/fencing vigente y los puntos de entrega que puedan emitir contenido. La terminación debe registrar un resultado verificable por admisión y por punto de entrega aplicable.

**Decisión 6 — recomendación adoptada para continuar el diseño:** la cobertura de Forget se determina por su alcance autorizado y por un inventario verificable de destinos y canales de entrega. Un canal que no pueda aplicar o demostrar fencing se excluye de la exposición de contenido protegido; no puede tratarse como una excepción silenciosa.

**Decisión 7 — recomendación adoptada para continuar el diseño:** una admisión no congela la autorización CAM durante toda la entrega. La revocación de Grant, suspensión/revocación de identidad u otra invalidación aplicable debe impedir emisiones posteriores en todos los puntos de entrega, con confirmación verificable de detención antes de declarar cancelada la admisión.

**Decisión 8 — recomendación adoptada para continuar el diseño:** los hechos canónicos mutables que intervienen en autorización/visibilidad tendrán revisiones monotónicas e independientes por autoridad/agregado. El snapshot CAM vincula las revisiones exactas de Memory, MemoryVersion, Project/Environment, Identity, Grant y supresión/admisión que sean aplicables. Cualquier cambio relevante invalida la admisión anterior; revisión ausente o incoherente produce DENY.

**Decisión 9 — recomendación adoptada para continuar el diseño:** una revocación, suspensión o reducción de alcance no puede depender de propagación eventual para detener entregas. El cambio autoritativo y el fencing deben quedar ordenados respecto de las emisiones. Si no puede probarse ese orden, no se permite emitir contenido ni declarar efectiva la transición para esa ruta hasta bloquearla de forma segura.

**Decisión 10 — recomendación adoptada para continuar el diseño:** la vigencia temporal de Grants se comprueba en cada emisión usando tiempo confiable. La expiración no se extiende por una admisión previa ni por un snapshot antiguo. Falta de reloj confiable o resultado ambiguo produce rechazo.

**Decisión 11 — recomendación adoptada para continuar el diseño:** se mantienen inventarios separados de destinos de persistencia/derivados y de rutas de entrega. El primero determina eliminación/verificación física; el segundo determina fencing y revocación de emisiones. Ninguno puede sustituir al otro.

**Decisión 12 — recomendación adoptada para continuar el diseño:** componentes de entrega no inventariados o incapaces de demostrar fencing no pueden servir contenido protegido. Destinos de persistencia desconocidos/no verificables impiden declarar Forget completado. La cobertura exige trazabilidad de rutas y evidencia de inspección, incluidos componentes declarados no aplicables.

**Decisión 13 — recomendación adoptada para continuar el diseño:** cada unidad de contenido cruza un punto de compromiso de emisión ordenado respecto de cierres e invalidaciones. La comprobación separada de un token seguida de una liberación posterior no satisface la garantía. Una unidad comprometida antes del cierre cuenta como emitida; una unidad cuyo compromiso ocurre después se rechaza.

**Decisión 14 — recomendación adoptada para continuar el diseño:** las admisiones usan estados monotónicos ADMITTED, ACTIVE, COMPLETED, CANCELLED y UNRESOLVED. COMPLETED y CANCELLED son terminales incompatibles; UNRESOLVED bloquea la confirmación de operaciones que requieren demostrar ausencia de emisiones futuras.

**Decisión 15 — recomendación adoptada para continuar el diseño:** Forget y las invalidaciones de autorización se ordenan respecto de cada compromiso de emisión. Los resultados ambiguos no se interpretan como ausencia de entrega; requieren reconciliación y mantienen el sistema fail-closed.

**Decisión 16 — recomendación adoptada para continuar el diseño:** el registro lógico de admisiones, compromisos, cierres y acknowledgements debe ser durable, monotónico, correlacionado e idempotente. La recuperación restaura cierres antes de admitir tráfico y nunca resuelve una admisión por timeout solamente.

Ninguno de estos puntos autoriza a seleccionar una base de datos, caché, índice, proveedor, scheduler o plataforma.

## 9. Criterio de salida

ME-03 de diseño estará listo para implementación cuando se hayan aceptado las garantías de §3–4 y cerrado los bloqueos de §8 que afecten al límite de lectura. La implementación posterior deberá:

- cambiar el contrato del puerto para exigir lectura condicional y admisión vinculada al snapshot;
- vincular el resultado CAM con el snapshot exacto y las revisiones monotónicas de todas las autoridades aplicables;
- implementar el compromiso de emisión como operación ordenada respecto de cierres e invalidaciones;
- mantener inventarios separados y verificables de persistencia/derivados y rutas de entrega;
- comprobar la supresión en el mismo límite de admisión/lectura;
- coordinar lecturas en curso con Forget y con revocaciones/suspensiones;
- aplicar fencing en cada compromiso de emisión y cubrir buffers/intermediarios;
- recuperar durablemente cierres, generaciones, admisiones y acknowledgements sin reabrir antes de reconciliar;
- añadir y ejecutar pruebas deterministas C01–C44;
- mantener los adaptadores de prueba separados de cualquier afirmación de integración real.

**Estado actual:** este documento registra una propuesta de diseño. No implementa snapshots, leases, supresión, Forget, persistencia ni garantías de runtime.
