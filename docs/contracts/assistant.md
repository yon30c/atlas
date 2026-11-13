# Contrato de Atlas Assistant

**Identificador:** CT-06  
**Estado:** Aprobado  
**Base normativa:** `Contrato-de-diseno-Atlas-v1.md` y contratos CT-01 a CT-05.  
**Alcance:** Responsabilidades, límites de autoridad, autonomía, contexto, memoria, modelos, herramientas y coordinación de Atlas Assistant.

## 1. Propósito

Atlas Assistant es el componente de interacción y coordinación inteligente entre el propietario y el entorno Atlas. Comprende solicitudes, interpreta intenciones, utiliza contexto autorizado, prepara planes y coordina solicitudes de trabajo con los componentes responsables.

Assistant es una capa de inteligencia y coordinación, no una autoridad independiente sobre los recursos de Atlas.

## 2. Principios obligatorios

1. El propietario conserva las decisiones que requieren su intervención.
2. Se aplica mínimo privilegio; Assistant no recibe permisos amplios por ser el componente principal de interacción.
3. Interpretar, planificar, autorizar y ejecutar son responsabilidades diferentes.
4. La autonomía se limita a capacidades y políticas explícitamente permitidas.
5. Las operaciones protegidas pasan por CAM.
6. Todo acceso a memoria protegida utiliza Memory Gateway y CAM.
7. El contexto conversacional y la memoria persistente son sistemas conceptualmente separados.
8. La arquitectura no depende de un proveedor o modelo específico.
9. El modelo puede proponer herramientas; Atlas valida y controla su invocación.
10. Las solicitudes y operaciones relevantes conservan contexto y correlación.
11. Se distinguen hechos, inferencias, propuestas y resultados.
12. Ningún modelo, prompt, herramienta o Skill puede modificar por sí mismo los permisos.
13. La información entre proyectos no se comparte fuera del alcance autorizado.
14. Los fallos e interrupciones no se presentan como operaciones completadas.

## 3. Responsabilidades

### 3.1 Interacción

Assistant recibe solicitudes, interpreta lenguaje natural, identifica intenciones, detecta ambigüedades, solicita aclaraciones y mantiene la relación entre solicitudes y trabajos derivados. La interpretación del lenguaje natural no constituye autorización.

### 3.2 Comprensión contextual

Puede utilizar la solicitud actual, contexto conversacional, identidad y contexto operativo verificados, proyecto y entorno, memorias visibles y autorizadas, eventos y resultados relacionados, y estado conocido de tareas anteriores.

La disponibilidad de un dato no implica que sea válido, actual o suficiente para autorizar una operación. La información insuficiente, contradictoria o no verificable debe señalarse, no completarse mediante suposiciones presentadas como hechos.

### 3.3 Planificación

Assistant puede preparar planes con objetivo, operaciones propuestas, dependencias, proyecto y entorno, recursos requeridos, riesgos, restricciones, autorizaciones potencialmente necesarias, resultados esperados y condiciones de finalización.

Un plan es una propuesta; no equivale a una tarea admitida por Scheduler, una autorización de CAM ni una ejecución iniciada.

### 3.4 Coordinación

Assistant remite solicitudes a componentes responsables mediante interfaces autorizadas:

| Componente | Responsabilidad |
|---|---|
| Identity / Authentication | Identidad y autenticación verificadas. |
| CAM | Decisiones de autorización. |
| Memory Gateway | Lectura y propuestas de memoria. |
| Scheduler | Admisión y coordinación de tareas. |
| Approval Manager | Gestión de aprobaciones humanas. |
| Event Collector | Registro de eventos. |
| Analysis Engine | Análisis autorizado. |
| Notification Manager | Comunicaciones permitidas. |
| Project Manager | Operaciones y estado de proyectos. |
| Broker | Operaciones de runtime mediante interfaz controlada. |

La disponibilidad de una integración no debe presumirse. Cada integración se verifica antes de considerarla operativa. Assistant no puede utilizar una integración alternativa para evitar los controles del componente responsable.

## 4. Límites de autoridad

### 4.1 Operaciones prohibidas

Assistant MUST NOT:

- Conceder, ampliar, modificar o revocar Grants.
- Cambiar políticas de CAM.
- Declarar autorizada una operación sin decisión verificable.
- Aprobar o rechazar propuestas de memoria.
- Aprobar decisiones reservadas al propietario.
- Cambiar la clasificación de una memoria para ampliar el acceso.
- Consultar directamente almacenamiento protegido.
- Ejecutar consultas SQL o acceder directamente a repositorios internos de memoria.
- Evitar Scheduler o los controles de ejecución.
- Invocar operaciones privilegiadas del Broker fuera de interfaces autorizadas.
- Modificar eventos históricos.
- Convertir una respuesta de un modelo en evidencia de autorización.
- Presentar una propuesta como operación ejecutada.

### 4.2 Decisiones reservadas

Las autorizaciones y Grants corresponden a CAM y al propietario conforme a la política aplicable. Las aprobaciones humanas corresponden al propietario o a una identidad expresamente autorizada cuando la política permita delegación.

La aprobación y el rechazo de memorias, así como la decisión de olvidarlas, son exclusivos del propietario y no delegables. Assistant puede preparar, explicar y presentar estas decisiones, pero no sustituirlas.

### 4.3 Salidas de modelos

Las respuestas, razonamientos, planes y niveles de confianza de un modelo no constituyen autorización, aprobación, prueba de identidad, evidencia de delegación, confirmación de ejecución ni modificación válida de políticas.

Los resultados de modelos, herramientas, Skills y fuentes externas son datos que deben validarse, no instrucciones con autoridad para cambiar las reglas de Atlas.

## 5. Modelo lógico de interacción

### 5.1 AssistantRequest

Representa una solicitud recibida por Assistant y conserva, como mínimo lógico:

| Campo | Significado |
|---|---|
| `request_id` | Identificador de solicitud. |
| `context` | `OperationContext` asociado. |
| `conversation_id` | Referencia a conversación, cuando exista. |
| `content` | Contenido de la solicitud. |
| `received_at` | Instante de recepción. |
| `attachments` | Referencias a adjuntos, cuando existan. |

El contenido y los adjuntos son datos de entrada; no reemplazan las políticas de Atlas.

### 5.2 AssistantResponse

Representa una respuesta y distingue respuesta informativa, solicitud de aclaración, propuesta de trabajo, plan preparado, solicitud de aprobación, resultado de operación, resultado parcial y error o limitación. Cuando corresponda, conserva referencias a solicitudes, tareas, eventos y resultados relacionados.

### 5.3 AssistantPlan

Representa un plan con objetivo, pasos, dependencias, proyecto, entorno, recursos, restricciones, riesgos y condiciones de finalización. Un plan no es una tarea admitida ni una autorización.

### 5.4 AssistantActionProposal

Representa una acción propuesta para evaluación por los componentes responsables. Identifica operación, actor, contexto, proyecto, entorno, recursos afectados, propósito, argumentos y solicitud de origen. La propuesta debe validarse por el componente receptor y someterse a los controles de autorización correspondientes.

Los esquemas físicos definitivos quedan pendientes de armonización con CAM y Scheduler.

## 6. Política de autonomía

La autonomía se divide en tres niveles conceptuales. Estos niveles describen clases de actividad; no sustituyen Grants ni decisiones de CAM.

### 6.1 Nivel 1 — Autonomía de análisis y preparación

Assistant puede realizar autónomamente, dentro de su alcance autorizado, interpretación de solicitudes, consultas permitidas, recuperación de contexto y memoria autorizados, análisis de eventos y resultados, preparación de planes y recomendaciones, detección de problemas, propuestas de solución y solicitudes de aclaración.

Estas actividades no deben producir por sí mismas efectos externos o mutaciones protegidas.

### 6.2 Nivel 2 — Ejecución bajo autorización explícita

Assistant puede solicitar y coordinar operaciones cuando exista un Grant explícito, vigente y suficiente para la operación y el recurso involucrado. Deben cumplirse estas condiciones:

- La operación está permitida por la política.
- CAM verifica la autorización.
- El recurso y el alcance están identificados.
- El proyecto y entorno corresponden.
- Se respetan límites de recursos y concurrencia.
- Scheduler y los componentes ejecutores aplican sus controles.
- Se conserva trazabilidad de la solicitud y el resultado.

Assistant coordina el flujo, pero no sustituye la decisión de CAM ni la admisión de Scheduler. Una autorización para una operación no implica autorización para otras operaciones relacionadas.

### 6.3 Nivel 3 — Decisión humana obligatoria

Las operaciones que requieren decisión humana se detienen hasta recibir aprobación válida. Incluyen, según la política aplicable, operaciones privilegiadas o sensibles, cambios que amplíen permisos, modificaciones importantes de políticas, aprobación o rechazo de memorias, olvido de memorias y otras decisiones reservadas al propietario.

Assistant puede explicar el impacto, preparar la solicitud y presentar alternativas, pero no aprobar en nombre del propietario. La aprobación debe vincularse a la operación y al alcance concretos; no constituye autorización ilimitada para acciones futuras.

### 6.4 Reglas comunes

- Una instrucción general no crea permisos ilimitados.
- La continuidad de una conversación no extiende automáticamente una autorización.
- La confianza del modelo no amplía el alcance.
- La ausencia de respuesta de CAM no equivale a autorización.
- Un permiso vigente no permite ignorar aprobaciones humanas adicionales.
- Las operaciones fuera del alcance autorizado se detienen.
- Los cambios de estado y resultados se verifican antes de comunicarlos como completados.

El catálogo operativo, los riesgos y los requisitos de aprobación se definirán en contratos y políticas específicas.

## 7. Modelos y arquitectura de inteligencia

### 7.1 Independencia del proveedor

Atlas Assistant no depende de un modelo, proveedor o framework específico. La arquitectura permite sustituir, incorporar o retirar modelos sin modificar los límites de autoridad de CAM, Memory Gateway, Scheduler o ejecutores. La selección de un modelo no modifica los permisos de Assistant.

### 7.2 Model Router

Se establece conceptualmente un componente de selección y enrutamiento denominado **Model Router**. Selecciona modelos según tipo de tarea, capacidades requeridas, disponibilidad, latencia, coste y presupuesto, privacidad, clasificación de datos y políticas aplicables.

Model Router no concede permisos ni autoriza operaciones. Su función se limita a la selección y gestión de modelos. Puede seleccionar modelos locales o remotos únicamente cuando la política de datos permita el tratamiento correspondiente.

### 7.3 Modelos especializados

La arquitectura puede utilizar distintos modelos para interpretación, análisis y planificación, clasificación, extracción estructurada, revisión de resultados y generación de respuestas.

La existencia de múltiples modelos no crea una cadena de autoridad. Ningún modelo puede aprobar las decisiones de otro ni concederle permisos. La selección definitiva y la asignación de tareas quedan pendientes de evaluación técnica.

### 7.4 Control externo al modelo

El modelo nunca es la frontera de seguridad. Antes de invocar una herramienta u operación, Atlas valida externamente identidad y contexto, operación, argumentos y estructura, recurso afectado, proyecto y entorno, permisos, aprobaciones requeridas y restricciones.

El modelo puede proponer una llamada a herramienta. La capa de control de Atlas decide si puede realizarse y mediante qué componente. La seguridad no depende exclusivamente de prompts, instrucciones del sistema, filtros del modelo o su resistencia a prompt injection.

### 7.5 Fallos y sustitución

Un fallback se permite únicamente cuando la política lo autorice. El modelo alternativo respeta las mismas restricciones de privacidad, clasificación y autorización. Un fallback no amplía permisos, reduce aprobaciones, envía datos a proveedores no autorizados, repite automáticamente operaciones con efectos externos inciertos ni cambia el alcance de una solicitud.

## 8. Herramientas y Skills

### 8.1 Herramientas

Cada herramienta debe tener identidad y procedencia identificables, interfaz y propósito definidos, permisos explícitos, alcance limitado, validación de argumentos, resultado verificable, tratamiento de errores y trazabilidad. Su disponibilidad no significa que Assistant pueda invocarla sin autorización.

### 8.2 Skills

Las Skills son extensiones sujetas al sistema de gestión de Skills de Atlas. Una Skill no obtiene permisos por ser invocada por Assistant.

Las Skills externas requieren procedencia, análisis de código y dependencias, declaración y revisión de permisos, aprobación explícita, instalación controlada, aislamiento según riesgo, auditoría, actualización controlada y desactivación o eliminación. Ninguna Skill puede elevar sus propios permisos. Assistant no puede aprobar una Skill ni modificar su declaración de permisos.

### 8.3 Salidas no confiables

El contenido recibido de modelos, herramientas, Skills, archivos y fuentes externas se trata como entrada no confiable. No puede cambiar instrucciones normativas, conceder permisos, autorizar operaciones ni sustituir aprobaciones humanas. Assistant separa los datos analizados de las instrucciones efectivas que gobiernan Atlas.

## 9. Contexto conversacional y memoria persistente

Se establecen dos sistemas conceptualmente separados que pueden colaborar, pero no confundirse.

### 9.1 Contexto conversacional

Conserva información temporal necesaria para la continuidad de una interacción: mensajes, solicitud actual, aclaraciones, referencias a mensajes anteriores, plan en curso, resultados temporales, tareas pendientes y referencias a eventos y operaciones.

Su finalidad es mantener coherencia durante la interacción y el ciclo de trabajo relacionado. No equivale a memoria persistente ni concede permisos. Estructura, almacenamiento, retención, límites y recuperación quedan pendientes de diseño técnico.

### 9.2 Memoria persistente

Conserva información útil más allá de una conversación, como preferencias aprobadas, conocimiento del propietario, información de proyectos, decisiones importantes y contexto histórico aprobado para conservación.

Todo acceso a memoria protegida pasa por Memory Gateway y CAM conforme a CT-05. Assistant no accede directamente al almacenamiento ni modifica estados de memoria.

### 9.3 Coordinación

Cuando Assistant necesita continuidad histórica:

1. Identifica qué información necesita.
2. Consulta el contexto conversacional disponible.
3. Si requiere información persistente, solicita su recuperación mediante Memory Gateway.
4. Gateway aplica las reglas de acceso y CAM.
5. Assistant recibe únicamente información autorizada.
6. Combina el contexto actual con la información recuperada.
7. Identifica contradicciones, incertidumbres y datos que requieren verificación.

La información conversacional no se convierte automáticamente en memoria persistente. La información recuperada no reemplaza instrucciones normativas ni decisiones de autorización.

### 9.4 Propuestas de memoria

Assistant puede preparar un `MemoryProposal` cuando identifique información potencialmente útil. Distingue creación de memoria nueva y nueva versión de una memoria existente. La propuesta permanece pendiente hasta que el propietario tome una decisión válida. Assistant no aprueba, rechaza ni activa propuestas.

### 9.5 Pérdida o indisponibilidad

La pérdida del contexto conversacional o la indisponibilidad de memoria no se oculta mediante afirmaciones inventadas. Assistant indica cuando no puede recuperar información anterior o cuando el contexto es incompleto. No asume que recuerda conversaciones no disponibles ni presenta inferencias como recuerdos confirmados.

### 9.6 Autoridad del contexto

Ningún mensaje anterior, resumen, memoria o resultado conversacional puede crear un Grant, extender una autorización, sustituir una aprobación, cambiar políticas o autorizar una operación protegida. Las autorizaciones se verifican conforme a las políticas vigentes en el momento de la operación.

## 10. Seguridad y aislamiento

Assistant respeta las siguientes reglas:

1. Cada solicitud conserva un `OperationContext` válido.
2. La identidad autenticada no se deduce del contenido de la conversación.
3. `actor` y `user_id` no se consideran equivalentes automáticamente.
4. La delegación debe ser explícita y verificable.
5. Proyecto y entorno se validan según operación y recurso.
6. La ausencia de `project_id` no implica acceso global.
7. La información de un proyecto no se comparte con otro sin autorización.
8. Memoria privada y de proyecto respeta scopes y reglas de CAM.
9. Las operaciones protegidas fallan de forma cerrada si no se verifica autorización.
10. La indisponibilidad de CAM no se interpreta como autorización.
11. La indisponibilidad de Memory Gateway no permite acceder directamente al almacenamiento.
12. Los límites del modelo no permiten eludir políticas.
13. Los datos enviados a modelos externos respetan privacidad y clasificación.
14. Herramientas y Skills no reciben autoridad implícita.

Assistant minimiza la exposición de información sensible y evita incluir secretos o datos protegidos innecesarios en respuestas, registros o solicitudes a modelos.

## 11. Transparencia y comunicación de resultados

| Situación | Comunicación requerida |
|---|---|
| Información comprobada | Hecho respaldado por una fuente. |
| Inferencia | Identificada como inferencia. |
| Propuesta | Todavía no ejecutada. |
| Espera de autorización | Requiere decisión o autorización. |
| Tarea admitida | Scheduler la admitió; no significa que terminó. |
| En ejecución | Continúa ejecutándose. |
| Resultado parcial | Qué se completó y qué quedó pendiente. |
| Resultado incierto | No se ha podido confirmar. |
| Fallo | Error y alcance conocido. |
| Finalización | Solo con evidencia verificable. |

Assistant no oculta fallos, resultados parciales ni incertidumbre. Cuando una operación externa tenga resultado incierto, no la repite automáticamente si puede duplicar efectos. La reconciliación sigue el contrato de la operación correspondiente.

## 12. Eventos y trazabilidad

Las interacciones y operaciones relevantes conservan, cuando corresponda, identificador de solicitud, correlación, actor y usuario contextual, origen, proyecto y entorno, propósito, operación solicitada, decisión de autorización, aprobación asociada, resultado, referencias a tareas y eventos, y procedencia y versión de modelos, herramientas y Skills participantes.

Assistant no modifica eventos históricos ni sustituye mecanismos de auditoría. Registrar una solicitud no demuestra que haya sido autorizada o ejecutada. La implementación respeta CT-04 y las políticas de auditoría aplicables.

## 13. Errores y recuperación

Assistant gestiona diferenciadamente solicitudes inválidas, contextos incompletos, identidades no válidas, denegaciones, recursos inexistentes, conflictos de estado, errores de contrato, indisponibilidad de componentes, errores de modelos o herramientas, resultados parciales e inciertos.

No transforma una denegación en éxito ni busca vías alternativas para ejecutar sin autorización. Cuando un componente no está disponible, informa de la limitación y conserva el estado conocido. Los errores respetan CT-03.

## 14. Correspondencia con la implementación

Este contrato describe comportamiento objetivo, no afirma que las capacidades estén implementadas. La existencia de modelos, puertos o estructuras iniciales no demuestra un servicio funcional de Assistant.

La implementación verificará expresamente servicio de recepción y procesamiento, modelos de solicitudes, respuestas y planes, propagación de `OperationContext`, integración con CAM y Memory Gateway, Model Router, control de herramientas, coordinación con Scheduler, gestión de aprobaciones, trazabilidad y recuperación, y separación entre contexto conversacional y memoria persistente.

La creación de interfaces o modelos no equivale a implementar el comportamiento completo.

## 15. Criterios de aceptación

### Identidad y contexto

- **AST-01:** cada solicitud conserva un `OperationContext`.
- **AST-02:** el contenido conversacional no prueba identidad.
- **AST-03:** actor y usuario contextual permanecen diferenciados.
- **AST-04:** la delegación no se infiere automáticamente.
- **AST-05:** proyecto y entorno se validan según la operación.
- **AST-06:** contexto conversacional y memoria persistente permanecen diferenciados.
- **AST-07:** la pérdida de contexto no se oculta mediante recuerdos inventados.

### Interpretación y planificación

- **AST-08:** Assistant distingue solicitudes informativas de operativas.
- **AST-09:** solicita aclaraciones cuando la información es insuficiente.
- **AST-10:** puede presentar propuestas sin ejecutarlas.
- **AST-11:** los planes conservan referencia a su solicitud.
- **AST-12:** una propuesta no se presenta como tarea admitida.

### Autonomía

- **AST-13:** las actividades autónomas de análisis y preparación no producen mutaciones protegidas por sí solas.
- **AST-14:** la ejecución requiere permisos explícitos y vigentes.
- **AST-15:** CAM verifica las operaciones protegidas.
- **AST-16:** las decisiones humanas obligatorias detienen la operación hasta recibir aprobación válida.
- **AST-17:** una instrucción general no se convierte en autorización ilimitada.
- **AST-18:** una autorización no se extiende automáticamente a operaciones futuras o diferentes.

### Modelos y herramientas

- **AST-19:** sustituir un modelo no altera las políticas de autorización.
- **AST-20:** Model Router no concede permisos.
- **AST-21:** las llamadas a herramientas se validan fuera del modelo.
- **AST-22:** la indisponibilidad de un modelo no reduce los controles de seguridad.
- **AST-23:** los datos enviados a modelos externos respetan las políticas de privacidad.
- **AST-24:** las herramientas tienen procedencia e interfaces identificables.
- **AST-25:** Assistant no invoca herramientas fuera de su autorización.
- **AST-26:** las Skills externas pasan por el proceso de revisión y aprobación establecido.
- **AST-27:** ninguna Skill puede elevar sus propios permisos.

### Memoria

- **AST-28:** toda lectura protegida utiliza Memory Gateway.
- **AST-29:** las propuestas de memoria permanecen pendientes hasta decisión válida del propietario.
- **AST-30:** Assistant no aprueba ni rechaza memorias.
- **AST-31:** memorias olvidadas o suprimidas no se presentan como disponibles.
- **AST-32:** la memoria recuperada no concede autoridad.
- **AST-33:** el contexto conversacional no se convierte automáticamente en memoria persistente.

### Seguridad y resultados

- **AST-34:** la indisponibilidad de CAM no autoriza operaciones.
- **AST-35:** Assistant no concede ni amplía Grants.
- **AST-36:** la información de proyectos permanece aislada.
- **AST-37:** la ausencia de alcance no se interpreta como alcance global.
- **AST-38:** Assistant distingue propuesta, admisión, ejecución y finalización.
- **AST-39:** los resultados parciales e inciertos se identifican expresamente.
- **AST-40:** Assistant no modifica eventos históricos.
- **AST-41:** los errores respetan el contrato de errores.
- **AST-42:** una denegación no se transforma en éxito.
- **AST-43:** no se repiten automáticamente operaciones con efectos externos inciertos.

Los criterios se convertirán posteriormente en pruebas unitarias, contractuales, de integración y seguridad.

## 16. Decisiones técnicas pendientes

1. Transporte, sesiones y persistencia de conversaciones.
2. Proveedores y modelos locales o remotos.
3. Criterios y política de Model Router.
4. Selección, fallback y límites de contexto de modelos.
5. Representación y versionado de solicitudes, respuestas y planes.
6. Ciclo de vida de planes y propuestas.
7. Interfaz concreta de CAM.
8. Interfaz concreta de Memory Gateway.
9. Registro, descubrimiento y ejecución de herramientas.
10. Integración con Skill Manager.
11. Persistencia, retención y recuperación del contexto conversacional.
12. Relación entre conversación, memoria y `OperationContext`.
13. Streaming, cancelación y recuperación.
14. Concurrencia y solicitudes simultáneas.
15. Límites de tokens, tiempo, llamadas y recursos.
16. Política de reintentos y reconciliación.
17. Protección frente a prompt injection y contenido externo malicioso.
18. Privacidad y tratamiento de datos enviados a modelos externos.
19. Observabilidad y correlación.
20. Catálogo concreto de operaciones por nivel de autonomía.
21. Clasificación de riesgos y matriz de aprobaciones.

Estas decisiones no reabren las políticas arquitectónicas aprobadas: Assistant no concede permisos; CAM es la autoridad central de autorización; Memory Gateway es la única frontera de acceso a memoria; las decisiones reservadas al propietario no son delegables; las operaciones protegidas requieren autorización; las Skills no pueden elevar sus propios permisos; la autonomía permanece limitada por Grants y políticas explícitas; los proyectos permanecen aislados.

No es necesario decidir todavía proveedor de modelos, framework de agentes, protocolo de transporte, base de datos o proveedor de embeddings para aprobar el contrato conceptual.

## 17. Secuencia de implementación propuesta

1. Definir modelos de solicitud, respuesta, plan y propuesta.
2. Definir la separación entre contexto conversacional y memoria persistente.
3. Implementar validación y propagación de `OperationContext`.
4. Construir el servicio mínimo de interpretación y respuesta.
5. Incorporar Model Router detrás de una interfaz intercambiable.
6. Integrar consultas autorizadas mediante Memory Gateway.
7. Integrar CAM para solicitudes protegidas.
8. Incorporar propuestas de trabajo y coordinación con Scheduler.
9. Integrar Approval Manager cuando corresponda.
10. Incorporar herramientas bajo interfaces y permisos explícitos.
11. Integrar Skills conforme a su contrato.
12. Añadir trazabilidad, recuperación y manejo de resultados parciales.
13. Ejecutar pruebas contractuales, negativas, de aislamiento y seguridad.

Cada etapa conserva las garantías de los contratos previos. La implementación inicial no activa operaciones privilegiadas ni despliegues de producción sin sus controles correspondientes.

---

**Regla final:** Atlas Assistant debe ser suficientemente inteligente para comprender, planificar y coordinar el trabajo del propietario, pero nunca debe convertirse en una autoridad independiente sobre la seguridad, los permisos, la memoria o los recursos de Atlas.

## 15. Armonización transversal con CT-08

Este contrato se interpreta conjuntamente con **CT-08 — Matriz de consistencia entre CT-01 y CT-07** (`docs/contracts/consistency-matrix-ct-08.md`). CT-08 complementa las fronteras de integración sin sustituir las responsabilidades específicas de CT-06 ni ampliar la autoridad de Assistant.

Reglas aplicables:

- **CT-08 R08-01:** Assistant recibe las propuestas de Proactivity y conserva la responsabilidad de interacción y presentación. La separación entre Watchers, Event Collector, Analysis Engine, Proactivity y Assistant es lógica y de autoridad; no exige procesos o despliegues independientes.
- **CT-08 R08-05:** Assistant conserva diferenciados `OperationContext.actor`, `user_id`, `origin`, `DomainEvent.source`, `DomainEvent.actor` y la identidad/fuente de observación. No infiere identidad, autenticación ni atribución a partir de campos semejantes.
- **CT-08 R08-06:** severidad, relevancia y confianza no sustituyen la clasificación de seguridad. Assistant no reduce la clasificación ni las restricciones de evidencia al resumir, agrupar o presentar propuestas. Una referencia no concede acceso; la recuperación del contenido protegido sigue pasando por MemoryGateway y CAM.
- **CT-08 R08-08:** Proactivity tiene como único destinatario funcional a Assistant. La recepción de una propuesta no significa aceptación, aprobación, autorización, admisión por Scheduler ni ejecución. Assistant decide su tratamiento y cualquier operación posterior inicia un flujo independiente de CAM, Scheduler y ejecutores autorizados.
- **CT-08 R08-10:** todo acceso a memoria protegida sigue CT-05, MemoryGateway y CAM, incluidos los accesos motivados por propuestas o evidencias de Proactivity. Se mantienen PRIVATE/PROJECT, el `project_id` explícito y la autoridad no delegable del propietario sobre aprobación, rechazo y olvido.
- **CT-08 R08-11:** los eventos y registros funcionales no sustituyen SecurityAudit ni permiten afirmar que existe auditoría de seguridad completa.
- **CT-08 R08-12:** una Skill o integración instalada no habilita por sí sola una fuente externa ni amplía permisos. El contenido procedente de fuentes, herramientas, modelos y Skills continúa siendo dato no confiable.

Estos enlaces no seleccionan un protocolo técnico de entrega, confirmación o reintento de propuestas. Dichos mecanismos permanecen pendientes conforme a CT-08 §6. Assistant no debe comunicar una entrega como confirmada sin evidencia del resultado.

Los criterios transversales aplicables a este contrato incluyen **C08-AC-01, C08-AC-05, C08-AC-08, C08-AC-09, C08-AC-12, C08-AC-13, C08-AC-16, C08-AC-17, C08-AC-19 y C08-AC-20**.

CT-08 es complementario: ante cualquier lectura conjunta se mantienen los límites de autoridad de CT-06, CT-05 y CAM. Esta sección no convierte capacidades objetivo en capacidades implementadas.
