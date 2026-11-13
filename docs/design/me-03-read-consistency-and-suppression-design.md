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

**Garantía para Forget aceptada por el propietario del proyecto:** después de confirmar la activación de la supresión lógica, no se admiten nuevas lecturas de la memoria/versión afectada. Toda lectura admitida antes de que comience Forget debe finalizar de forma verificable o ser cancelada, con confirmación de que ya no puede entregar contenido, antes de que Forget confirme que la supresión lógica está aplicada. Si no puede verificarse una de esas dos condiciones, Forget no puede confirmar la supresión y debe permanecer en un estado no completado/fail-closed. Esta aceptación no selecciona todavía el mecanismo técnico de coordinación.

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

Una lectura admitida debe tener una duración/lease acotada o una forma equivalente de coordinación. Al comenzar Forget, el sistema debe cerrar la admisión de nuevas lecturas afectadas y resolver todas las admisiones anteriores: cada una debe finalizar de forma verificable o ser cancelada, confirmando que no puede entregar contenido. Solo después puede confirmarse la supresión lógica.

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

- **Completada:** la entrega controlada terminó y no quedan bytes, fragmentos ni trabajo pendiente que esa operación pueda emitir.
- **Cancelada:** el emisor fue detenido y existe confirmación de que ya no puede continuar entregando contenido.

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

La implementación actual no ofrece todavía esta garantía:

- `AuthorizationResult` contiene solo la decisión, no un snapshot de autorización.
- `MemoryVersionMetadata` no contiene revisión/epoch.
- `MemoryVersionContentPort.get_version_content()` es una lectura por IDs y no declara atomicidad, supresión ni coordinación de lecturas en curso.
- No existe aún un puerto ni servicio de supresión/Forget.
- No existe inventario de destinos, cachés, índices, réplicas, exportaciones o backups.

Por tanto, las pruebas existentes demuestran orden de llamadas y fail-closed básico, pero no consistencia concurrente ni supresión global.

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

Las pruebas de concurrencia deben usar eventos/barreras explícitas, no sleeps ni temporizadores, para que los intercalados sean reproducibles.

## 8. Decisiones pendientes antes de implementar

1. Definir la autoridad única de supresión y cómo la consultan todos los destinos.
2. Definir cómo se versionan los metadatos canónicos y cómo se detecta un cambio desde el snapshot CAM.
3. Definir la semántica de lease/admisión y su recuperación ante caída del proceso, respetando la política aceptada para lecturas en curso.
4. Definir cómo una revocación de Grant o expiración durante el intervalo se refleja en la admisión de lectura.
5. Inventariar destinos reales antes de afirmar que la supresión es global.
6. Definir evidencia verificable para que Forget avance de supresión lógica a eliminación física y finalmente a `forgotten`.

**Decisión 1 — aceptada:** las lecturas admitidas antes de comenzar Forget deben finalizar o cancelarse de forma verificable antes de confirmar la supresión lógica. No se confirma la supresión si una lectura previa aún puede entregar contenido o si su estado no puede determinarse.

**Decisión 2 — aceptada:** la dirección de diseño será una autoridad lógica única que coordine admisión de lecturas y supresión. Su mecanismo físico, disponibilidad y recuperación ante fallos siguen pendientes de diseño.

**Decisión 3 — aceptada:** toda ruta de entrega de contenido debe aplicar fencing verificable de la admisión/generación vigente en cada punto efectivo de emisión. Las admisiones antiguas solo pueden declararse canceladas cuando todos los puntos de entrega relevantes confirmen que no pueden continuar emitiendo; el timeout o la caída aparente del emisor no bastan.

**Decisión 4 — recomendación adoptada para continuar el diseño:** el cierre de Forget, el avance de generación y el registro de admisiones deben ser recuperables de forma durable y conservarse cerrados tras reinicios hasta reconciliación. La recuperación no puede inferir finalización a partir de expiración de lease, pérdida de heartbeat o desaparición temporal de un proceso.

**Decisión 5 — recomendación adoptada para continuar el diseño:** cada admisión debe estar correlacionada con un identificador único, el conjunto exacto de recursos afectados, la generación/fencing vigente y los puntos de entrega que puedan emitir contenido. La terminación debe registrar un resultado verificable por admisión y por punto de entrega aplicable.

**Decisión 6 — recomendación adoptada para continuar el diseño:** la cobertura de Forget se determina por su alcance autorizado y por un inventario verificable de destinos y canales de entrega. Un canal que no pueda aplicar o demostrar fencing se excluye de la exposición de contenido protegido; no puede tratarse como una excepción silenciosa.

**Decisión 7 — recomendación adoptada para continuar el diseño:** una admisión no congela la autorización CAM durante toda la entrega. La revocación de Grant, suspensión/revocación de identidad u otra invalidación aplicable debe impedir emisiones posteriores en todos los puntos de entrega, con confirmación verificable de detención antes de declarar cancelada la admisión.

Ninguno de estos puntos autoriza a seleccionar una base de datos, caché, índice, proveedor, scheduler o plataforma.

## 9. Criterio de salida

ME-03 de diseño estará listo para implementación cuando se hayan aceptado las garantías de §3–4 y cerrado los bloqueos de §8 que afecten al límite de lectura. La implementación posterior deberá:

- cambiar el contrato del puerto para exigir lectura condicional;
- vincular el resultado CAM con el snapshot exacto;
- comprobar la supresión en el mismo límite de admisión/lectura;
- coordinar lecturas en curso con Forget;
- aplicar fencing en cada punto efectivo de emisión y cubrir buffers/intermediarios;
- recuperar durablemente cierres, generaciones y admisiones sin reabrir antes de reconciliar;
- añadir pruebas deterministas de carreras, reanudación de emisores antiguos, caída/reinicio y fencing de cada canal;
- mantener los adaptadores de prueba separados de cualquier afirmación de integración real.

**Estado actual:** este documento registra una propuesta de diseño. No implementa snapshots, leases, supresión, Forget, persistencia ni garantías de runtime.
