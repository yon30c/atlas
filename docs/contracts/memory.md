# Contrato de memoria de Atlas

## 1. Propósito

Este contrato define las garantías funcionales, de autorización, ciclo de vida, versionado, procedencia y olvido de las memorias de Atlas. Su objetivo es permitir que Atlas utilice memoria sin crear accesos implícitos a información privada, entre proyectos o fuera de las decisiones expresas de su propietario.

## 2. Alcance y autoridad normativa

Este documento desarrolla el dominio de memoria de Atlas Core y debe interpretarse junto con el Contrato de diseño de Atlas v1 y el contrato técnico del Memory Engine. En caso de discrepancia, prevalece el contrato de diseño principal.

No autoriza cambios en Atlas Broker, Registry v2, infraestructura protegida ni entornos de producción.

Los términos OBLIGATORIO/DEBE y PROHIBIDO/NO DEBE expresan requisitos normativos; APROBADO identifica decisiones acordadas; PENDIENTE identifica parámetros técnicos que requieren decisión explícita y no deben resolverse por inferencia.

Este contrato no selecciona base de datos, motor de búsqueda, proveedor de embeddings, Cognee, scheduler, transporte ni plataforma de despliegue.

## 3. Modelo conceptual

- **Memory:** identidad lógica de una memoria y su propietario canónico.
- **MemoryScope:** ámbito PRIVATE o PROJECT.
- **MemoryVersion:** versión concreta e inmutable del contenido, con clasificación y procedencia propias.
- **MemoryProposal:** solicitud para crear una memoria o proponer una nueva versión.
- **MemoryProvenance:** procedencia y evidencias asociadas a una versión.
- **Versión aprobada vigente:** referencia a la versión aprobada que se utiliza como memoria actual.

El propietario se define de forma canónica en Memory; no se duplica como autoridad independiente en MemoryScope. Una propuesta de nueva versión identifica la memoria objetivo sin crear un segundo propietario canónico. Este es un modelo lógico y no obliga a que cada concepto sea una tabla, colección o clase independiente.

## 4. Ámbitos de memoria

### 4.1 PRIVATE

Una memoria PRIVATE pertenece a un propietario explícito. El acceso del propietario a su propia memoria se autoriza mediante una regla explícita de CAM y siempre atraviesa MemoryGateway. Esta regla no requiere un Grant de proyecto, pero tampoco permite omitir Gateway o CAM.

Ningún otro usuario, agente, servicio, Skill o proyecto obtiene acceso por defecto.

### 4.2 PROJECT

Una memoria PROJECT debe incluir un project_id explícito y válido. La operación debe presentar un contexto cuyo project_id coincida con el ámbito de la memoria y superar la autorización de CAM.

La pertenencia al mismo proyecto no concede por sí sola todos los permisos: CAM evalúa la operación, el actor, el recurso concreto y las reglas aplicables. La ausencia de project_id, un identificador distinto o un ámbito no verificable implica denegación.

### 4.3 Sin transferencias implícitas

No se permite convertir una memoria PRIVATE en PROJECT, cambiarla de proyecto ni transferir su propiedad como efecto secundario de una consulta, importación, propuesta o cambio de contexto. La semántica y el procedimiento de transferencia quedan PENDIENTES de decisión explícita.

## 5. Ciclo de vida

### 5.1 Estados normativos

Los estados de una versión de memoria son exactamente:

- pending_review
- approved
- rejected
- superseded
- forgotten

Los estados proposed, active y archived no forman parte del nuevo ciclo de vida normativo. Una propuesta es una entidad del proceso de revisión; no equivale a una versión aprobada.

### 5.2 Transiciones permitidas

- pending_review → approved
- pending_review → rejected
- approved → superseded
- approved → forgotten

No se permiten transiciones implícitas ni reactivaciones de versiones rechazadas, superseded o forgotten. Una corrección posterior se presenta como una nueva propuesta/versionado según corresponda.

### 5.3 Versión vigente y atomicidad

Una nueva versión en pending_review no reemplaza ni invalida la versión aprobada vigente.

La aprobación de una nueva versión, la transición de la versión aprobada anterior a superseded y la actualización del puntero de versión vigente DEBEN ejecutarse como una única operación atómica. Si no puede completarse íntegramente, debe conservarse el estado anterior consistente.

Una memoria nueva no se vuelve utilizable como memoria aprobada por el mero hecho de registrar su propuesta.

### 5.4 Estado forgotten

forgotten representa la finalización verificada del proceso de olvido definido en la sección 9. No es un estado provisional para indicar que la solicitud fue recibida o que se aplicó la supresión lógica.

Los estados operativos intermedios, si se necesitan, pertenecen al seguimiento de la operación y no amplían el conjunto normativo de estados de memoria.

## 6. Versionado, clasificación y procedencia

### 6.1 Versiones y clasificación

Cada versión conserva su propio contenido, clasificación y procedencia. Una nueva propuesta no modifica el contenido histórico de una versión existente.

La clasificación es explícita por versión. No se permite reducir automáticamente el nivel de clasificación ni inferir que una nueva versión hereda una clasificación menos restrictiva. Cualquier cambio requiere revisión y decisión del propietario conforme a las reglas aplicables.

El catálogo definitivo de clasificación y sus reglas de propagación quedan PENDIENTES.

### 6.2 Procedencia obligatoria

Toda versión debe conservar información de procedencia suficiente para identificar el origen declarado y las evidencias que sustentaron su creación o actualización.

Las referencias de evidencia sirven para trazabilidad; no conceden autorización de lectura ni amplían permisos. Si una fuente deja de estar disponible, la referencia histórica puede conservarse como no disponible. Su desaparición no autoriza a inventar evidencia sustitutiva ni a exponer contenido protegido.

### 6.3 Integridad histórica

Las versiones conservan su identidad e historial de decisiones conforme a las reglas de retención que se definan. La conservación histórica nunca prevalece sobre una operación de olvido completada. Los plazos y políticas de retención quedan PENDIENTES.

## 7. MemoryGateway y autorización CAM

### 7.1 Frontera obligatoria

MemoryGateway es la única frontera de acceso al sistema de memoria. Todo componente que lea, proponga, revise, apruebe, rechace, actualice, exporte u olvide memorias DEBE hacerlo a través de Gateway y de la autorización CAM correspondiente.

Gateway no debe exponer directamente sesiones, consultas SQL, archivos, repositorios subyacentes, índices ni mecanismos internos de almacenamiento. No se permite acceso directo desde Assistant, Watchers, Skills u otros componentes a los adaptadores o almacenes.

### 7.2 Autorización por recurso concreto

CAM debe verificar el resource_id concreto de la memoria o versión sobre la que se realiza la operación. Un Grant limitado a un tipo de recurso no autoriza por sí solo el acceso a cualquier instancia de ese tipo.

Si falta el identificador, no coincide con el recurso solicitado o no puede verificarse, la operación se deniega. Las operaciones colectivas requieren semántica explícita y autorización definida; no se presumen a partir de permisos individuales.

La autorización debe fallar de forma segura: errores, contexto incompleto o imposibilidad de verificar una condición necesaria no se interpretan como permiso.

### 7.3 Operaciones lógicas

El contrato contempla capacidades sujetas a autorización individual: enumerar memorias visibles en el contexto actual, obtener una versión concreta, enviar propuestas de memoria nueva o nueva versión, revisar propuestas, aprobar/rechazar propuestas, solicitar actualizaciones permitidas, solicitar el olvido y exportar cuando exista autorización expresa.

Esta lista define capacidades del dominio; no obliga a implementar ahora un método público por cada elemento ni fija una API completa.

La interfaz actual list_visible(context) se mantiene como referencia para enumerar memorias visibles. Este contrato NO añade un parámetro query. Filtros, búsqueda, paginación y firmas futuras quedan PENDIENTES de diseño técnico explícito.

### 7.4 Identificadores de permisos y no delegabilidad

Los identificadores de operación pueden incluir memory.read, memory.propose, memory.review, memory.approve, memory.reject, memory.update, memory.forget y memory.export.

Estos identificadores permiten expresar y auditar qué operación se intenta realizar. NO constituyen por sí mismos una concesión de autoridad ni anulan las restricciones de propietario, ámbito, recurso o no delegabilidad.

En particular, memory.approve y memory.reject no hacen delegables esas decisiones. CAM debe aplicar las restricciones especiales de la sección 8.

### 7.5 Sin acceso lateral

Ninguna respuesta del Gateway debe revelar memorias fuera del ámbito autorizado, aunque el identificador sea conocido, aparezca en una referencia de evidencia o haya sido proporcionado por otro componente. Los errores de autorización no deben filtrar contenido protegido.

## 8. Autoridad de aprobación y rechazo

La aprobación y el rechazo de memorias son decisiones exclusivas del propietario y no delegables.

CAM debe verificar que la decisión proviene directamente del propietario de la memoria mediante el mecanismo de evidencia de acción del propietario que se defina para la implementación.

Ningún Assistant, agente, servicio, Watcher, Skill, administrador técnico o proceso automático puede aprobar o rechazar una memoria en nombre del propietario. Tampoco puede convertir una recomendación, puntuación, clasificación automática o ausencia de respuesta en aprobación.

El Assistant puede explicar una propuesta y recomendar que el propietario la revise, pero no puede tomar la decisión.

El formato técnico de la evidencia verificable de acción directa del propietario queda PENDIENTE. Esta decisión pendiente no reduce ni suspende la regla normativa de no delegabilidad.

## 9. Olvido, supresión y eliminación verificable

### 9.1 Autoridad y solicitud

El olvido es una operación protegida, iniciada por decisión directa del propietario y no delegable. CAM debe verificar identidad, propiedad, recurso concreto y autorización antes de iniciar la operación. Una solicitud recibida no equivale a olvido completado.

### 9.2 Supresión lógica inmediata

Una vez validada la solicitud, el sistema debe aplicar supresión lógica para impedir inmediatamente que la memoria y sus versiones afectadas se expongan mediante las rutas ordinarias de lectura.

La supresión debe cubrir consultas y procesos que puedan volver a presentar el contenido, incluidos índices, búsquedas, cachés, exportaciones y procesos de recuperación.

El mecanismo debe utilizar identificadores opacos y conservar únicamente los metadatos mínimos necesarios para impedir la reaparición. No debe almacenar el contenido original ni depender de hashes vulnerables a ataques de diccionario sobre contenidos previsibles.

La supresión lógica no demuestra que el contenido haya sido eliminado físicamente.

### 9.3 Inventario de destinos

La eliminación verificable debe contemplar todos los destinos donde pueda persistir o derivarse el contenido, según el inventario real del sistema:

- Almacenamiento primario.
- Versiones y copias históricas.
- Índices de búsqueda y estructuras derivadas.
- Embeddings e índices vectoriales, si existen.
- Cachés.
- Réplicas.
- Backups.
- Exportaciones y copias operativas.

El inventario definitivo, la identificación de destinos y el procedimiento de verificación quedan PENDIENTES. La implementación no puede asumir que un destino no existe sin evidencia del inventario.

### 9.4 Eliminación y verificación

El proceso debe eliminar el contenido afectado de todos los destinos incluidos en el alcance y obtener evidencia verificable de cada resultado.

Si un destino está fuera de servicio, no responde, no puede inspeccionarse o no permite confirmar la eliminación, el proceso no puede declararse completado. La supresión lógica debe mantenerse mientras exista incertidumbre.

La operación debe distinguir:
1. Solicitud validada.
2. Supresión lógica aplicada.
3. Eliminación física ejecutada en los destinos.
4. Verificación completa de todos los destinos.

Solo después del cuarto punto puede marcarse la memoria/versión afectada como forgotten y comunicarse que el olvido fue completado.

### 9.5 Restauración, reindexación e importación

Todo proceso de restauración, reindexación, reconstrucción, replicación o importación debe consultar y aplicar la supresión antes de hacer que cualquier contenido vuelva a estar disponible.

Una copia restaurada no puede revivir una memoria olvidada. Si no es posible comprobar la supresión antes de exponer los datos, el proceso debe bloquear la exposición. Esta comprobación requiere una fuente de supresión vigente e independiente del backup restaurado, o una reconciliación explícita aprobada. El perfil local de Atlas sin Trust Anchor externo no puede demostrar por sí solo que el registro local restaurado sea el más reciente. Si no existe esa fuente independiente, la restauración de datos que puedan preceder a un Forget debe permanecer bloqueada; la integridad local del backup no basta para declarar satisfecha la garantía.

### 9.6 Registro mínimo

La evidencia de la operación debe permitir auditar su resultado sin conservar el contenido olvidado. El registro de supresión se limita a identificadores opacos y metadatos operativos mínimos; no debe convertirse en un archivo alternativo del contenido.

Los detalles de reconciliación, retención de evidencia operativa y tratamiento de backups quedan PENDIENTES, sin alterar las garantías anteriores.

**Decisión de arquitectura — 13 de noviembre de 2026:** Trust Anchor externo es opcional y su implementación queda postergada hasta la etapa final de Atlas. El perfil local conserva las reglas de supresión, pero no ofrece anti-rollback externo. Por ello, no se permite restaurar ni exponer datos de memoria potencialmente anteriores a un Forget sin reconciliar la supresión contra una fuente independiente aprobada.

## 10. Límites de los componentes

### 10.1 Atlas Assistant

El Assistant puede solicitar lecturas contextuales y presentar propuestas mediante Gateway. No puede acceder directamente a almacenes, saltarse CAM, aprobar/rechazar memorias, conceder permisos ni ejecutar el olvido por decisión propia.

### 10.2 Memory Engine

El Memory Engine aplica las reglas del dominio y coordina operaciones autorizadas a través de las fronteras definidas. No adquiere autoridad para aprobar memorias automáticamente ni para relajar reglas CAM.

### 10.3 Watchers y proactividad

Los Watchers y componentes de proactividad son observadores de solo lectura respecto de la memoria protegida. Pueden identificar señales y generar propuestas para revisión, pero no aprobar, rechazar, modificar permisos ni ejecutar acciones de olvido.

### 10.4 Skills y componentes externos

Una Skill o integración externa no obtiene acceso a memoria por estar instalada o habilitada. Todo acceso requiere autorización explícita, recurso concreto, ámbito válido y paso por Gateway/CAM. Ninguna Skill puede elevar sus propios permisos.

## 11. Correspondencia con el código actual

La implementación actual es una base inicial y no debe confundirse con la totalidad del contrato normativo.

El modelo Memory existente contiene memory_id, owner_id, content, status y created_at. MemoryProposal contiene owner_id, content y context, y valida la correspondencia entre owner_id y context.user_id. Esa validación de consistencia no demuestra por sí sola autenticación ni autorización.

El código actual utiliza estados iniciales proposed, active, archived y rejected, y el puerto MemoryGateway dispone de list_visible(context) y submit_proposal(context, proposal).

Estos elementos deberán evolucionar para cumplir el ciclo de vida normativo, el versionado, la procedencia, la autorización CAM por recurso concreto y el proceso de olvido verificable. La interfaz actual no autoriza a omitir esos requisitos ni obliga a fijar ahora todas las firmas futuras.

## 12. Decisiones técnicas pendientes

Las siguientes cuestiones requieren decisiones explícitas antes de cerrar su diseño de implementación:

1. Formato, generación y normalización de identificadores.
2. Semántica y procedimiento de transferencia de propiedad o ámbito.
3. Catálogo de clasificación y reglas de propagación entre versiones.
4. Evidencia técnica verificable de aprobación, rechazo y olvido por acción directa del propietario.
5. Retención de versiones, evidencias y backups.
6. Inventario de almacenes, índices, cachés, réplicas, embeddings, backups y exportaciones.
7. Formato del registro de supresión, reconciliación y verificación de eliminación.
8. Semántica y límites de operaciones colectivas.
9. Límites de índices globales y búsquedas entre ámbitos.
10. Matriz de permisos por clasificación y operación.
11. Filtros, búsqueda y paginación de list_visible, si se requieren.

Estas decisiones no deben resolverse anticipadamente mediante la selección de una base de datos, Cognee, embeddings, scheduler, Telegram o infraestructura de despliegue.

La implementación de SecurityAudit y sus garantías operativas se mantiene pospuesta según la planificación arquitectónica; esta postergación no elimina los requisitos de autorización y trazabilidad definidos aquí.

## 13. Criterios de aceptación

El contrato se considera implementado únicamente cuando existan pruebas que demuestren, como mínimo, los siguientes comportamientos:

- **MEM-01:** toda lectura y mutación pasa por MemoryGateway y CAM.
- **MEM-02:** no existe acceso directo desde Assistant, Watchers o Skills a los almacenes.
- **MEM-03:** la memoria tiene un propietario canónico.
- **MEM-04:** una memoria PRIVATE solo es visible al propietario mediante autorización explícita.
- **MEM-05:** una memoria PROJECT requiere project_id explícito y coincidente.
- **MEM-06:** ausencia o discrepancia de ámbito produce denegación.
- **MEM-07:** CAM verifica el recurso concreto y no autoriza instancias arbitrarias por tipo.
- **MEM-08:** identificadores ausentes, incorrectos o no verificables producen denegación.
- **MEM-09:** los errores de autorización no revelan contenido protegido.
- **MEM-10:** una propuesta no se convierte automáticamente en memoria aprobada.
- **MEM-11:** se distinguen propuestas de memoria nueva y de nueva versión.
- **MEM-12:** los estados implementados coinciden con el conjunto normativo.
- **MEM-13:** solo se permiten las transiciones definidas en este contrato.
- **MEM-14:** una propuesta pendiente no reemplaza la versión aprobada vigente.
- **MEM-15:** aprobación, superseding y actualización del puntero vigente son atómicos.
- **MEM-16:** cada versión conserva su clasificación explícita.
- **MEM-17:** una clasificación no se degrada automáticamente.
- **MEM-18:** cada versión conserva procedencia.
- **MEM-19:** referencias de evidencia no conceden permisos.
- **MEM-20:** una fuente no disponible queda identificada como referencia histórica no disponible.
- **MEM-21:** aprobación y rechazo requieren decisión directa del propietario.
- **MEM-22:** ningún agente, Assistant, servicio, Watcher o Skill puede aprobar/rechazar por delegación.
- **MEM-23:** los identificadores memory.approve y memory.reject no anulan la no delegabilidad.
- **MEM-24:** el olvido requiere decisión directa del propietario y autorización CAM.
- **MEM-25:** la solicitud de olvido no se presenta como operación completada.
- **MEM-26:** la supresión lógica bloquea inmediatamente la exposición ordinaria.
- **MEM-27:** el registro de supresión no conserva contenido original ni hashes vulnerables a diccionario.
- **MEM-28:** el proceso contempla todos los destinos del inventario.
- **MEM-29:** destinos no disponibles o no verificables impiden declarar el olvido completado.
- **MEM-30:** forgotten solo se asigna después de verificar todos los destinos del alcance.
- **MEM-31:** restauraciones, reindexaciones e importaciones aplican supresión antes de exponer contenido.
- **MEM-32:** una copia restaurada no puede revivir una memoria olvidada.
- **MEM-33:** la evidencia operativa de olvido no conserva el contenido eliminado.
- **MEM-34:** Watchers y proactividad no mutan memoria ni toman decisiones reservadas al propietario.
- **MEM-35:** una Skill no puede elevar sus permisos ni omitir Gateway/CAM.
- **MEM-36:** list_visible(context) conserva la interfaz actual hasta que se apruebe un cambio de diseño.
- **MEM-37:** filtros y paginación no se presuponen como parte de la firma actual.
- **MEM-38:** las decisiones técnicas pendientes quedan documentadas y no se resuelven por inferencia.
- **MEM-39:** la implementación no introduce dependencias tecnológicas o de despliegue no aprobadas.
- **MEM-40:** las operaciones protegidas fallan de forma segura ante contexto incompleto o imposibilidad de verificar una condición obligatoria.

Los criterios que dependan de parámetros técnicos pendientes deberán concretarse en el plan de pruebas cuando dichos parámetros se aprueben. Esto no suspende las garantías normativas ya establecidas.

## 14. Secuencia de implementación

1. Ajustar los modelos de dominio y los estados normativos.
2. Implementar validaciones de ámbito, propietario, clasificación y procedencia.
3. Definir y probar las fronteras de MemoryGateway y su integración con CAM.
4. Implementar propuestas, revisión, aprobación, rechazo y versionado atómico.
5. Diseñar el inventario de persistencia y el mecanismo de supresión.
6. Implementar olvido, eliminación y verificación de todos los destinos.
7. Asegurar restauración, reindexación e importación frente a supresiones existentes.
8. Integrar Atlas Assistant exclusivamente mediante Gateway.
9. Incorporar proactividad como observador de solo lectura.
10. Ejecutar la matriz de aceptación y revisar las garantías de seguridad.

Cada etapa requiere pruebas y revisión antes de avanzar. La aprobación de este contrato valida las reglas de diseño aquí descritas; no significa que estas capacidades ya estén implementadas ni autoriza cambios fuera del alcance de Atlas Core.

## 15. Referencias a CT-08

CT-08 complementa este contrato como matriz transversal; las resoluciones siguientes precisan su aplicación sin duplicar sus reglas:

- [CT-08 R08-06](consistency-matrix-ct-08.md#r08-06-clasificacion-y-proteccion-de-evidencia-derivada): Clasificación y protección de evidencia derivada; una referencia no concede acceso.
- [CT-08 R08-10](consistency-matrix-ct-08.md#r08-10-memoria-protegida): Acceso protegido mediante MemoryGateway y CAM, con ámbitos PRIVATE/PROJECT y autoridad no delegable del propietario.
