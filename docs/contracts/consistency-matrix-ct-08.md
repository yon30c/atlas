# CT-08 — Matriz de consistencia entre CT-01 y CT-07

**Estado:** aprobado para publicación documental por instrucción expresa del propietario.  
**Fecha:** 13 de noviembre de 2026.  
**Repositorio:** `yon30c/atlas`.  
**Rama:** `main`.  
**Alcance:** armonización de contratos CT-01 a CT-07 con el contrato principal de Atlas v1.  
**Naturaleza:** addendum de consistencia arquitectónica; no declara componentes implementados.

---

## 1. Propósito

CT-08 identifica y resuelve las ambigüedades de responsabilidad, autoridad, contexto y flujo entre los contratos CT-01 a CT-07 y el contrato principal de Atlas v1.

Este documento convierte las decisiones de armonización aprobadas por el propietario en reglas transversales verificables. Su objetivo es que los contratos puedan implementarse conjuntamente sin duplicar autoridad, abrir rutas de acceso alternativas ni confundir observaciones, eventos, conclusiones, incidencias, propuestas y tareas.

La revisión distingue:

- Contradicción normativa explícita.
- Ambigüedad o responsabilidad solapada.
- Frontera de autoridad incompleta.
- Dependencia o correspondencia de datos insuficientemente definida.
- Diferencia entre contrato normativo y estado de implementación.
- Parámetro técnico que debe permanecer pendiente.

No se modificaron CT-01 a CT-07 ni el contrato principal durante esta publicación. CT-08 establece las reglas de integración y las aclaraciones aprobadas que deberán incorporarse en futuras revisiones de los documentos fuente.

## 2. Autoridad, alcance y reglas de interpretación

### 2.1 Autoridad

CT-08 complementa los contratos CT-01 a CT-07 exclusivamente en las relaciones entre ellos que se revisan aquí.

Las reglas específicas de identidad, autorización, memoria, eventos, autonomía y seguridad de los contratos fuente mantienen su autoridad. CT-08 no debilita ni sustituye esas reglas.

Cuando una integración admita más de una interpretación, deberá aplicarse la que preserve el mínimo privilegio, la separación de responsabilidades, el aislamiento y las garantías ya aprobadas. Una ambigüedad no puede utilizarse para crear autoridad implícita.

Las aclaraciones de CT-08 son decisiones de arquitectura aprobadas para la integración documental. No equivalen a aprobación de una tecnología, mecanismo de persistencia, despliegue o implementación.

### 2.2 Límites

CT-08:

- No modifica el código ni declara implementado ningún componente.
- No modifica CT-01 a CT-07 ni el contrato principal.
- No autoriza cambios en Atlas Broker, Registry v2, infraestructura protegida o producción.
- No selecciona bases de datos, transportes, colas, schedulers concretos, frameworks, proveedores de modelos o mecanismos de persistencia.
- No reabre decisiones aprobadas ni convierte parámetros técnicos pendientes en decisiones resueltas.
- No modifica el alcance de implementación definido en §20.5 del contrato principal.

### 2.3 Vocabulario de hallazgos

| Clasificación | Significado |
|---|---|
| Contradicción | Dos reglas no pueden cumplirse simultáneamente tal como están redactadas. |
| Ambigüedad | Las reglas pueden coexistir, pero no delimitan suficientemente responsabilidades o interacción. |
| Frontera incompleta | Falta una regla explícita para transferir control, validar autoridad o tratar un ciclo de vida. |
| Diferencia de implementación | El contrato normativo y el código descrito no coinciden; no es necesariamente una contradicción contractual. |
| Pendiente técnico | El contrato deja deliberadamente un mecanismo o parámetro sin especificar. |

## 3. Fuentes revisadas

Se recuperaron las versiones vigentes de `main` el 13 de noviembre de 2026:

| Documento | Blob SHA |
|---|---|
| `Contrato-de-diseno-Atlas-v1.md` | `54dc6dc796a7ac3e549e8a580632f180c15fc9f9` |
| CT-01 `docs/contracts/identity.md` | `fdbc2e1c4ba1f73d6ddf4d83523f6ab734e9422a` |
| CT-02 `docs/contracts/operation-context.md` | `35e290b2c6c7b6b66d84a5a8c8a96895e8bb5d96` |
| CT-03 `docs/contracts/errors.md` | `4cc7231b3877ca01b7f0d360f4dec056554363cb` |
| CT-04 `docs/contracts/events.md` | `39808a1de1f37deb7b9671c0d9f952290c096fcc` |
| CT-05 `docs/contracts/memory.md` | `01377f7b432c68f147b30d0fc2a48cca1e48d9b5` |
| CT-06 `docs/contracts/assistant.md` | `3a68142cee1375bdf72a83e570db7e420eeef01c` |
| CT-07 `docs/contracts/proactivity.md` | `8b889e5e5f6f8094310f53fc70d7bb243f5e0176` |
| Resumen de armonización de memoria | `72c9421ce2be7b084cf690933fd3f0628bc9f972` |

La revisión del contrato principal cubrió especialmente arquitectura y responsabilidades (§§2–3), contexto y esquemas (§§4–5), Scheduler (§7), Registry/RLM (§8), Memory Engine (§9), eventos e incidencias (§10), aprobaciones y notificaciones (§11), Skills (§12), errores y recuperación (§13), ciclo de vida (§14), decisiones del propietario (§16), parámetros pendientes (§17) y alcance (§20.5).

## 4. Matriz de consistencia

| ID | Dimensión | Contratos relacionados | Hallazgo | Severidad |
|---|---|---|---|---|
| C08-01 | Topología y responsabilidades | Principal §3; CT-04; CT-06; CT-07 | Watchers, Event Collector y Analysis Engine aparecen en la arquitectura principal. CT-07 introduce Proactivity con responsabilidades de observación, análisis, seguimiento y propuestas. La frontera entre esas responsabilidades no estaba suficientemente delimitada. | Alta |
| C08-02 | Ciclo de vida de identidades observadoras | CT-01 §§3–5; CT-02; CT-07 §§4, 6 y 9 | CT-01 define suspensión y revocación para toda identidad, incluido el tipo WATCHER, pero CT-07 no explicitaba cómo afectan a observaciones y reevaluaciones activas o pendientes. | Alta |
| C08-03 | Admisión de reevaluaciones | Principal §§2.1, 6 y 7; CT-06 §6; CT-07 §§3.4, 9 y 16 | CT-07 permite reevaluación automática, pero no establece expresamente que el trabajo en segundo plano respete la admisión y coordinación de Scheduler. | Alta |
| C08-04 | Locks y lecturas | Principal §8.3; CT-02 §5; CT-07 §§4 y 6 | No se distinguía con suficiente precisión cuándo una observación de solo lectura necesita RLM. Una lectura no debe convertirse en una vía para omitir Scheduler, CAM o las políticas del recurso; tampoco debe imponerse un lock indiscriminado sin que corresponda. | Media |
| C08-05 | Actor, origen y fuente | CT-01; CT-02 §§3 y 6; CT-04 §§2 y 5; CT-07 §5 | `OperationContext.actor`, `OperationContext.origin`, `DomainEvent.actor`, `DomainEvent.source` y la fuente de una Observation son conceptos distintos. Sin una regla transversal, una implementación podría fusionarlos y perder atribución. | Alta |
| C08-06 | Clasificación de observaciones y propuestas | Principal §4.7; CT-02 §6.3; CT-04 §4; CT-05 §6; CT-07 §§5–8 | CT-07 requiere clasificación aplicable para Observation, pero no fija la propagación hacia Finding y ProactiveProposal. CT-02 conserva una cadena declarada y no valida por sí mismo el catálogo. | Alta |
| C08-07 | Evento, observación, hallazgo e incidencia | Principal §10; CT-04 §6; CT-07 §§5, 9 y 12 | CT-04 diferencia evento, observación, conclusión e incidencia. Finding y FollowUpRecord de CT-07 podrían confundirse con conclusión e incidencia si no se delimitan. | Alta |
| C08-08 | Frontera Proactivity–Assistant | CT-06 §§3.4, 5.4 y 6; CT-07 §§3.3, 11 y 14 | CT-07 define Assistant como destinatario exclusivo de propuestas, pero CT-06 no enumera expresamente Proactivity en su tabla de integraciones. Tampoco se define el protocolo técnico de entrega y confirmación. | Alta |
| C08-09 | Errores, concurrencia y reintentos | CT-03 §§3–5; CT-04 §7; CT-07 §13 | No existe contradicción: CT-03 ya define ConcurrencyError y exige reevaluar estado y autorización antes de reintentar. CT-07 deja correctamente los mecanismos de reintento pendientes, pero debe quedar explícito que una reevaluación fallida no demuestra desaparición de la condición. | Media |
| C08-10 | Memoria protegida | CT-05 §§4, 7–10; CT-06 §§9–10; CT-07 §6.3 | Las reglas son consistentes: las lecturas protegidas pasan por MemoryGateway y CAM, respetan PRIVATE/PROJECT y no pueden derivarse permisos de una referencia de evidencia. No se detectó contradicción normativa. | Sin contradicción |
| C08-11 | Skills y contenido no confiable | Principal §12; CT-06 §8; CT-07 §§6.2 y 16 | Las fuentes externas están fuera del MVP de Proactivity y el contenido externo/no confiable no puede modificar instrucciones ni permisos. La política futura de fuentes externas debe mantenerse separada del proceso de gobierno de Skills. | Media |
| C08-12 | Eventos y SecurityAudit | Principal §10; CT-04 §§3, 7 y 8; CT-07 §12 | Los eventos son inmutables y no son órdenes. EventStore no sustituye SecurityAudit, cuya implementación continúa postergada. No se detectó contradicción; debe evitarse presentar la trazabilidad de Proactivity como auditoría de seguridad completa. | Media |
| C08-13 | Correspondencia normativa e implementación | CT-04 §10; CT-05 §11; CT-06 §14; CT-07 §15 | Los propios contratos documentan diferencias entre modelos actuales y objetivos normativos. Son brechas de implementación, no contradicciones entre contratos, y no deben resolverse debilitando los criterios de aceptación. | Media |

## 5. Resoluciones y decisiones de armonización aprobadas

Las siguientes resoluciones se incorporan como reglas transversales de CT-08. La autorización expresa del propietario para implementar las recomendaciones de esta revisión cubre estas decisiones de arquitectura. No autoriza elegir los parámetros técnicos que se mantienen pendientes.

### R08-01. Separación lógica entre observación, ingestión, análisis y proactividad

Se establecen las siguientes responsabilidades:

1. **Project Connectors y Watchers:** obtienen señales de fuentes habilitadas y autorizadas. No modifican los recursos observados ni ejecutan operaciones protegidas.
2. **Event Collector:** valida y registra hechos como eventos conforme a CT-04. No transforma eventos en órdenes.
3. **Analysis Engine:** realiza análisis general de eventos y puede producir conclusiones conforme a sus responsabilidades.
4. **Proactivity:** mantiene el ciclo especializado de observación analítica, Finding, ProactiveProposal y FollowUpRecord definido por CT-07. Consume señales y datos mediante interfaces autorizadas.
5. **Atlas Assistant:** recibe propuestas de Proactivity y decide su tratamiento conversacional y su eventual presentación al usuario.

Estas son fronteras lógicas y de autoridad. No obligan a desplegar cada responsabilidad como un proceso, servicio o contenedor independiente. Una futura decisión de implementación puede compartir infraestructura o código, siempre que conserve las responsabilidades, controles y trazabilidad separados.

Proactivity no sustituye a Watchers, Event Collector, Analysis Engine ni Assistant. Tampoco adquiere sus permisos.

### R08-02. Aplicación del ciclo de vida de Identity a Watchers y Proactivity

Toda identidad que actúe como observador, incluida una identidad de tipo WATCHER, queda sujeta a CT-01 y a la autorización CAM aplicable.

- **ACTIVE:** puede participar en nuevas observaciones o reevaluaciones únicamente si la fuente, el recurso y la operación continúan autorizados.
- **SUSPENDED:** no inicia nuevas observaciones ni reevaluaciones. Las tareas activas dependientes de esa identidad siguen la detención cooperativa y el punto seguro definidos por CT-01. No se amplía su alcance. Los registros internos ya creados se preservan.
- **REVOKED:** no inicia ni continúa participando en operaciones dependientes de esa identidad. Se aplica la detención segura definida por CT-01. La misma identidad no se reactiva; cualquier sustitución requiere una identidad nueva y autorizaciones independientes.

La suspensión o revocación de una identidad no borra observaciones, hallazgos, propuestas ni eventos históricos. Su conservación no autoriza a continuar consultando la fuente ni a reevaluar la condición. Una propuesta ya generada sigue siendo información analítica, no una autorización.

Cada reevaluación debe volver a comprobar la identidad vigente, la autorización de CAM y el acceso a la fuente. Una autorización anterior no se presume vigente.

### R08-03. Scheduler como frontera de admisión para trabajo automático

Toda reevaluación automática que se ejecute como trabajo en segundo plano debe someterse a la admisión y coordinación de Scheduler, conforme al contrato principal.

Proactivity puede determinar que una condición merece seguimiento y solicitar una reevaluación, pero no puede crear una ruta de ejecución paralela que omita Scheduler.

La admisión no equivale a autorización: CAM continúa evaluando las lecturas protegidas y Scheduler aplica sus controles de admisión, concurrencia, presupuesto y dependencias según corresponda.

La reevaluación mantiene el contexto y la correlación adecuados. Si la fuente o la autorización dejan de ser válidas, la operación se bloquea o finaliza de forma segura.

### R08-04. Aplicación proporcionada de RLM a observaciones de solo lectura

Una observación de solo lectura no requiere automáticamente un lock exclusivo.

RLM se aplica cuando la operación accede a un recurso compartido protegido cuya política exige coordinación mediante locks, conforme al contrato principal. La modalidad de lock y el recurso concreto dependen de la política del recurso.

Esta precisión no permite omitir RLM cuando sea obligatorio. Tampoco convierte un lock en autorización: CAM conserva la decisión de acceso y Scheduler conserva la admisión de tareas.

Las lecturas que no requieran lock según la política siguen sujetas a identidad, autorización, clasificación, scope y límites de consulta.

### R08-05. Separación de actor, origen, fuente y contexto

Se mantienen diferenciados los siguientes conceptos:

- `OperationContext.actor`: identidad que ejecuta la operación.
- `OperationContext.user_id`: usuario contextual; no demuestra autenticación ni autorización.
- `OperationContext.origin`: origen declarado de la solicitud.
- `DomainEvent.source`: fuente que produjo u originó el hecho registrado.
- `DomainEvent.actor`: identidad asociada al actor del evento, cuando corresponda.
- Fuente de `Observation`: fuente concreta de la señal observada.
- Identidad observadora: identidad que realizó la lectura u observación, cuando corresponda.

No se copiará un valor de un campo a otro por semejanza nominal. La correspondencia deberá establecerse explícitamente por el flujo y conservar la atribución original.

Los eventos emitidos por el ciclo de Proactivity conservarán el OperationContext asociado a la operación que los produce y los campos `source` y `actor` según la semántica de CT-04. La correlación deberá ser coherente con `context.correlation_id`.

### R08-06. Clasificación y protección de evidencia derivada

La clasificación de seguridad es independiente de severidad, relevancia y confianza.

Se aplican estas reglas:

1. La clasificación de una fuente, recurso, memoria o evidencia no se sustituye por la severidad analítica de un Finding.
2. Una referencia a evidencia no concede acceso al contenido.
3. La clasificación original de cada evidencia debe conservarse en sus referencias y trazabilidad.
4. Un Finding o ProactiveProposal no puede reducir ni eliminar restricciones de la información que incorpora.
5. No se introduce en CT-08 un orden jerárquico, algoritmo de agregación ni catálogo nuevo de clasificación.
6. Cuando no pueda determinarse que el contenido de una propuesta puede exponerse al destinatario, se evita incluir el contenido protegido y se conserva únicamente una referencia no reveladora, o se bloquea su entrega hasta resolver la autorización.
7. Assistant solo puede mostrar o recuperar evidencia mediante las rutas autorizadas y conforme a CT-05 y CT-06.

La propagación detallada de clasificación entre múltiples fuentes y los formatos técnicos permanecen pendientes, pero no pueden utilizarse para rebajar la protección ya aplicada.

### R08-07. Diferencia entre Finding, FollowUpRecord e Incidence

Se establecen las siguientes correspondencias:

- **Observation:** señal obtenida de una fuente. No es automáticamente un evento ni una conclusión.
- **Finding:** conclusión analítica derivada de observaciones y evidencias. No es el evento original ni una incidencia.
- **ProactiveProposal:** propuesta de atención dirigida a Assistant. No es una tarea, aprobación, autorización ni incidencia por sí misma.
- **FollowUpRecord:** registro interno de seguimiento de Proactivity. Permite reevaluar una condición y conservar su historial analítico. No es automáticamente una incidencia del sistema.
- **Incidencia CT-04 / contrato principal §10.2:** entidad separada de gestión de una situación que requiere atención y que puede relacionar eventos. No se crea automáticamente por la existencia de un Finding o FollowUpRecord.

Los estados de seguimiento de Proactivity no se equiparan ni se mapean automáticamente a `open`, `acknowledged`, `resolved` o `reopened` de las incidencias. Cualquier integración futura deberá definirla explícitamente y conservar los ciclos de vida separados.

Los eventos relevantes del ciclo de Proactivity se registran como eventos inmutables conforme a CT-04. La actualización de un registro interno no modifica eventos históricos.

### R08-08. Entrega de propuestas a Atlas Assistant

Atlas Assistant es el único destinatario funcional de las ProactiveProposal.

Proactivity no contacta directamente al usuario, no selecciona canales de notificación y no ejecuta acciones a partir de una propuesta.

Assistant decide si presenta, agrupa, conserva, solicita aclaraciones o descarta una propuesta. Si se requiere notificación, Assistant utiliza los mecanismos autorizados de Atlas y respeta las preferencias y políticas aplicables.

La entrega de una propuesta no equivale a aceptación, aprobación o admisión de tarea. Si Assistant decide iniciar una operación, esta comienza un flujo independiente de autorización CAM, admisión Scheduler y controles de ejecución.

No se fija aquí un protocolo de transporte, confirmación, reintentos, cola ni garantía de entrega. Hasta que ese mecanismo se especifique, un intento de entrega no puede comunicarse como entrega confirmada sin evidencia del resultado. Un fallo o resultado incierto no habilita notificación alternativa ni ejecución automática.

### R08-09. Errores y reevaluación

CT-03 es el catálogo normativo de errores conocido del núcleo. Proactivity utiliza el tipo específico que corresponda, incluido `AuthorizationError`, `NotFoundError`, `ContractError` o `ConcurrencyError`.

- Una fuente no disponible no demuestra que la condición haya desaparecido.
- Una lectura denegada no se reintenta por una ruta alternativa.
- Un conflicto de concurrencia no autoriza un reintento automático.
- Antes de repetir una lectura o reevaluación se vuelve a comprobar identidad, autorización, alcance y estado actual.
- Una reevaluación interrumpida o con resultado incierto conserva ese resultado como indeterminado; no se convierte en una conclusión de ausencia.
- Los mecanismos, límites y políticas técnicas de reintento continúan sujetos a CT-03 y a la especificación de implementación correspondiente.

### R08-10. Memoria protegida

Se confirma que CT-05 gobierna el acceso a memoria desde todos los componentes, incluidos Watchers y Proactivity:

- Toda lectura protegida pasa por MemoryGateway y CAM.
- PRIVATE y PROJECT no se cruzan implícitamente.
- PROJECT exige `project_id` explícito, válido y coincidente.
- CAM evalúa el recurso concreto y la operación.
- Una referencia de evidencia o identificador conocido no concede acceso.
- Aprobación, rechazo y olvido permanecen bajo autoridad exclusiva y no delegable del propietario.

Proactivity puede referenciar memoria como evidencia solo después de obtenerla por la ruta autorizada. No puede aprobar, rechazar, versionar, suprimir ni olvidar memorias.

### R08-11. Separación entre eventos y SecurityAudit

Los eventos de CT-04 y los registros internos de Proactivity proporcionan trazabilidad funcional, pero no sustituyen SecurityAudit.

SecurityAudit conserva el estado aprobado y la implementación postergada descritos en el contrato principal. CT-08 no declara que exista auditoría de seguridad completa ni autoriza a usar EventStore como sustituto.

Los eventos siguen siendo append-only e inmutables. Los hallazgos y seguimientos pueden actualizarse en sus propios ciclos de vida sin reescribir los eventos que los originaron.

### R08-12. Gobierno de fuentes externas y Skills

El MVP de Proactivity observa únicamente fuentes internas habilitadas.

La habilitación futura de fuentes externas requiere una política específica de fuentes, identidad, permisos, clasificación, límites, errores, retención y revocación. No se considera aprobada por el solo hecho de que el sistema pueda instalar una Skill o integración.

Las Skills externas mantienen el proceso de procedencia, análisis de código y dependencias, declaración y revisión de permisos, aprobación explícita, instalación controlada, aislamiento según riesgo, auditoría, actualización controlada y desactivación o eliminación. Ninguna Skill puede elevar sus propios permisos.

El contenido recibido de fuentes, herramientas, modelos o Skills se trata como dato no confiable y no puede cambiar las políticas ni las instrucciones normativas de Atlas.

## 6. Parámetros técnicos que permanecen pendientes

Las resoluciones de CT-08 no seleccionan mecanismos de implementación. Permanecen pendientes, entre otros:

1. Catálogo y registro de fuentes internas, adaptadores y permisos específicos.
2. Identificadores y formatos definitivos de Observation, Finding, EvidenceReference, ProactiveProposal y FollowUpRecord.
3. Frecuencia, disparadores, límites de duración y concurrencia de reevaluaciones.
4. Persistencia y recuperación de los registros propios de Proactivity.
5. Protocolo técnico de entrega, confirmación, recuperación y reconciliación de propuestas con Assistant.
6. Política técnica de reintentos, límites y backoff, compatible con CT-03.
7. Catálogo completo de tipos de eventos y reglas operativas de severidad de CT-04.
8. Catálogo específico y reglas de propagación de clasificación, sin debilitar las garantías de CT-05 y CT-04.
9. Algoritmos y umbrales de relevancia y confianza.
10. Correlación y deduplicación, sin inferir idempotencia.
11. Estados, transiciones, expiración y cierre del FollowUpRecord.
12. Reglas técnicas para determinar cuándo un recurso de solo lectura requiere lock según su política.
13. Tratamiento de contenido malicioso o instrucciones no confiables presentes en fuentes.
14. Política futura para habilitar fuentes externas.
15. Integración técnica y observabilidad de los límites lógicos definidos en R08-01.

Estos parámetros no bloquean la aprobación de las fronteras de autoridad y las reglas de integración de CT-08. Sí deben resolverse antes de implementar los mecanismos que dependen de ellos.

## 7. Criterios de aceptación transversales

| ID | Criterio | Resultado exigido |
|---|---|---|
| C08-AC-01 | Separación de responsabilidades | Watchers, Event Collector, Analysis Engine, Proactivity y Assistant conservan las responsabilidades definidas en R08-01, aunque compartan infraestructura. |
| C08-AC-02 | Identidad activa | Una observación o reevaluación protegida no comienza con una identidad suspendida o revocada. |
| C08-AC-03 | Suspensión | La suspensión detiene nuevas operaciones dependientes y aplica la detención cooperativa de CT-01 sin borrar registros internos existentes. |
| C08-AC-04 | Revocación | Una identidad revocada no continúa participando en operaciones dependientes ni se reactiva como la misma identidad. |
| C08-AC-05 | Autorización vigente | Cada nueva lectura y reevaluación vuelve a verificar CAM, fuente, recurso y alcance. |
| C08-AC-06 | Scheduler | El trabajo automático en segundo plano no omite la admisión y coordinación de Scheduler. |
| C08-AC-07 | RLM | Las operaciones usan RLM cuando la política del recurso lo exige; ninguna ruta omite un lock obligatorio. |
| C08-AC-08 | Atribución | Fuente, actor, origen, usuario contextual y contexto de operación no se confunden ni se copian implícitamente. |
| C08-AC-09 | Clasificación | La severidad analítica no sustituye la clasificación de seguridad ni reduce la protección de evidencia. |
| C08-AC-10 | Tipos analíticos | Finding y FollowUpRecord no se convierten automáticamente en eventos o incidencias. |
| C08-AC-11 | Inmutabilidad | Los eventos del ciclo de Proactivity cumplen CT-04 y no se reescriben al actualizar registros internos. |
| C08-AC-12 | Handoff | Proactivity entrega propuestas únicamente a Assistant; no notifica ni ejecuta directamente. |
| C08-AC-13 | Autorización de acciones | Una propuesta no crea Grant, aprobación, tarea admitida ni permiso. |
| C08-AC-14 | Fallos de fuente | Una fuente inaccesible o una reevaluación interrumpida produce estado indeterminado, no conclusión de desaparición. |
| C08-AC-15 | Reintentos | Un conflicto o error no provoca repetición automática sin reevaluar estado, autorización y seguridad. |
| C08-AC-16 | Memoria | Toda lectura de memoria protegida pasa por MemoryGateway y CAM, respetando PRIVATE/PROJECT. |
| C08-AC-17 | No delegabilidad | Proactivity, Watchers y Assistant no aprueban, rechazan ni olvidan memorias por el propietario. |
| C08-AC-18 | Fuentes externas | El MVP no observa fuentes externas y una Skill instalada no habilita una fuente automáticamente. |
| C08-AC-19 | Auditoría | La trazabilidad funcional no se presenta como sustituto de SecurityAudit. |
| C08-AC-20 | Estado de implementación | La aprobación documental no se comunica como implementación, integración o despliegue verificado. |

## 8. Brechas de implementación identificadas, fuera del alcance de esta publicación

CT-08 es una revisión contractual, no una auditoría de código. Se registran las siguientes diferencias ya descritas por los contratos fuente para que no se confundan con contradicciones normativas:

- **CT-04:** su sección 10 describe que el modelo actual de `DomainEvent` no contiene todos los campos normativos, incluida `classification`, y advierte que un mapping interno mutable puede impedir la inmutabilidad profunda.
- **CT-05:** su sección 11 describe estados e interfaces de código iniciales que todavía no cumplen el ciclo normativo completo de versiones, procedencia, autorización CAM y olvido verificable.
- **CT-06 y CT-07:** describen capacidades objetivo y criterios de aceptación, pero no certifican que Assistant o Proactivity estén implementados e integrados.

Estas diferencias deben resolverse en sus fases de implementación y mediante pruebas. CT-08 no modifica código ni autoriza ampliar el alcance de implementación.

## 9. Resultado de la revisión

La revisión no encontró una contradicción normativa directa que obligue a invalidar CT-01 a CT-07. Sí identificó ambigüedades de responsabilidad y fronteras incompletas, especialmente en la relación entre Watchers, Event Collector, Analysis Engine y Proactivity; en el ciclo de vida de las identidades observadoras; en la admisión de reevaluaciones; en la atribución de fuentes y actores; en la clasificación de evidencia derivada; y en el handoff a Assistant.

Las resoluciones R08-01 a R08-12 establecen las reglas transversales aprobadas para cerrar esas ambigüedades sin seleccionar prematuramente mecanismos técnicos ni debilitar decisiones previas.

**Estado documental:** CT-08 preparado y autorizado para publicación.  
**Implementación:** no declarada.  
**Contratos fuente:** sin modificación en esta publicación.  
**Infraestructura y producción:** sin cambios.

---

**Fin de CT-08.**
