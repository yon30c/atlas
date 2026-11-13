# CT-07 — Contrato de Proactivity


## 1. Propósito

Proactivity es el componente responsable de observar señales autorizadas del ecosistema Atlas, identificar condiciones relevantes, analizar posibles implicaciones y generar propuestas proactivas para Atlas Assistant.

Su objetivo es ayudar a Atlas a detectar situaciones que merecen atención sin esperar necesariamente una solicitud explícita del usuario.

Proactivity no es un agente ejecutor, no es un mecanismo de autorización y no sustituye a Atlas Assistant.

## 2. Principios obligatorios

1. **Solo lectura:** observar y analizar no implica modificar los recursos observados.
2. **Sin autoridad implícita:** detectar una oportunidad no concede permiso para actuar sobre ella.
3. **Separación de responsabilidades:** Proactivity identifica y propone; Assistant gestiona la interacción con el usuario.
4. **Evidencia:** las observaciones y propuestas deben conservar referencias que permitan justificar su origen.
5. **Trazabilidad:** los resultados relevantes deben poder relacionarse con sus fuentes y eventos.
6. **Respeto de permisos:** toda lectura protegida debe pasar por los mecanismos de autorización correspondientes.
7. **No interferencia:** un fallo de Proactivity no debe comprometer la ejecución normal de otros componentes.
8. **Transparencia:** una propuesta no debe presentarse como una acción ejecutada ni como un hecho confirmado cuando exista incertidumbre.

## 3. Responsabilidades

### 3.1 Observación

Proactivity puede observar cambios, eventos y estados de los componentes internos de Atlas cuando su acceso esté permitido por la política aplicable.

El MVP queda limitado a fuentes internas de Atlas. La observación de fuentes externas se considera una capacidad futura y requerirá una política explícita que habilite su incorporación y defina sus permisos.

### 3.2 Análisis

Proactivity puede:

- Correlacionar observaciones relacionadas.
- Detectar patrones y condiciones relevantes.
- Identificar anomalías o cambios significativos.
- Evaluar la persistencia de una condición.
- Estimar relevancia y confianza.
- Identificar información insuficiente o contradictoria.

El análisis no puede convertir una inferencia en un hecho confirmado sin evidencia suficiente.

### 3.3 Generación de propuestas

Cuando una condición lo justifique, Proactivity puede producir una `ProactiveProposal` dirigida exclusivamente a Atlas Assistant.

Atlas Assistant es responsable de decidir si la propuesta debe mostrarse al usuario, conservarse para una interacción posterior o descartarse según su política.

Proactivity no envía notificaciones directamente al usuario ni selecciona canales de comunicación.

### 3.4 Seguimiento

Proactivity puede mantener registros de seguimiento y reevaluar automáticamente condiciones pendientes.

La reevaluación debe permanecer en modo de solo lectura. Puede actualizar el estado analítico de un seguimiento y generar nueva evidencia o una propuesta revisada, pero no ejecutar acciones ni modificar el recurso observado.

Los límites de frecuencia, concurrencia y duración quedan sujetos a decisiones técnicas posteriores.

## 4. Límites de autoridad

Proactivity:

- No ejecuta operaciones de negocio ni operaciones del sistema.
- No modifica archivos, configuraciones, proyectos o recursos observados ni recursos externos.
- No crea, modifica ni revoca Grants.
- No aprueba ni rechaza solicitudes de autorización.
- No realiza operaciones protegidas directamente.
- No accede a almacenamiento protegido evitando MemoryGateway y CAM.
- No invoca operaciones mutables de Atlas Broker.
- No ejecuta herramientas, agentes o Skills como consecuencia de una observación.
- No transforma una propuesta en una tarea admitida o autorizada.
- No interpreta el silencio del usuario como aprobación.

Proactivity puede crear y actualizar sus propios registros internos de observación, análisis y seguimiento. Estas escrituras se limitan a datos bajo su responsabilidad y no pueden modificar los recursos observados, alterar datos protegidos ni ampliar permisos. Esta capacidad no autoriza operaciones sobre recursos externos ni operaciones de negocio.

Una propuesta de Proactivity no equivale a una instrucción del usuario, autorización, Grant, admisión de tarea ni resultado de ejecución.

Cualquier acción posterior debe pasar por Atlas Assistant y por los mecanismos de autorización, admisión y ejecución establecidos en los contratos correspondientes.

## 5. Modelos lógicos

Los siguientes modelos describen responsabilidades conceptuales. No fijan todavía una implementación, tecnología de persistencia ni formato definitivo de identificadores.

### 5.1 Observation

Representa una señal obtenida de una fuente autorizada.

Debe permitir identificar, como mínimo:

- Identidad de la observación.
- Fuente de origen.
- Momento de observación.
- Tipo de señal.
- Referencia al sujeto observado.
- Clasificación aplicable.
- Evidencia disponible.
- Contexto de correlación cuando exista.

### 5.2 Finding

Representa un resultado del análisis de una o varias observaciones.

Debe distinguir entre hechos observados, inferencias y condiciones que requieren verificación adicional.

### 5.3 EvidenceReference

Referencia la evidencia que respalda una observación, hallazgo o propuesta.

Una referencia de evidencia no concede acceso al recurso referenciado.

Si una fuente deja de estar disponible, la referencia histórica puede conservarse indicando que la evidencia ya no está disponible. No debe simularse que el contenido sigue siendo accesible.

### 5.4 ProactiveProposal

Representa una propuesta que Proactivity entrega a Atlas Assistant.

Debe incluir información suficiente para comprender:

- Qué condición fue detectada.
- Por qué podría ser relevante.
- Qué evidencia la respalda.
- Cuál es el nivel de confianza.
- Qué incertidumbres o limitaciones existen.
- Cuándo fue generada.
- Qué observaciones o hallazgos están relacionados.

La propuesta no debe afirmar que una acción ya se realizó cuando solo se está recomendando.

### 5.5 FollowUpRecord

Representa el seguimiento de una condición que puede requerir reevaluación.

Debe conservar la relación con las observaciones, hallazgos y propuestas que originaron el seguimiento, así como sus reevaluaciones y resultados.

## 6. Fuentes y permisos de observación

### 6.1 Fuentes permitidas en el MVP

El MVP puede considerar fuentes internas como:

- Eventos de Atlas.
- Cambios de estado de componentes internos.
- Resultados de tareas y operaciones.
- Estado de proyectos.
- Indicadores operativos internos.
- Resultados de análisis autorizados.
- Información de memoria a través de MemoryGateway y CAM, cuando corresponda.

Esta lista define categorías posibles, no concede acceso automático a todos sus datos.

### 6.2 Fuentes externas futuras

La integración de fuentes externas queda fuera del alcance inicial.

Su incorporación futura requerirá una política explícita que determine:

- Fuentes habilitadas.
- Identidad y permisos de acceso.
- Clasificación de la información.
- Límites de consulta.
- Tratamiento de errores y datos no confiables.
- Retención y trazabilidad.
- Condiciones para suspender o revocar el acceso.

### 6.3 Acceso a memoria

Toda lectura de memoria protegida debe realizarse a través de MemoryGateway y CAM.

Proactivity no puede acceder directamente a los almacenes de memoria, índices protegidos, réplicas o mecanismos internos para evitar los controles de acceso.

La separación entre memoria PRIVATE y PROJECT debe respetarse en todo momento. La evidencia o referencia a una memoria no constituye autorización para leerla.

## 7. Evidencia y calidad

Toda propuesta debe tener una base verificable.

Proactivity debe distinguir:

- **Observación:** señal obtenida directamente de una fuente.
- **Inferencia:** interpretación derivada de una o varias observaciones.
- **Hipótesis:** explicación posible que todavía requiere confirmación.
- **Incertidumbre:** limitación de la evidencia o del análisis.

La confianza representa la solidez estimada de una conclusión; no equivale a severidad ni relevancia.

Cuando la evidencia sea insuficiente, contradictoria o no verificable, Proactivity debe reflejarlo en el hallazgo o abstenerse de generar una propuesta concluyente.

Las referencias de evidencia no deben exponer contenido protegido a destinatarios que no tengan autorización para consultarlo.

## 8. Severidad, relevancia y confianza

Estos conceptos deben permanecer separados.

### 8.1 Severidad

Se utiliza el catálogo definido en CT-04:

- `critical`
- `important`
- `informational`
- `debug`

Cuando Proactivity reutiliza estos valores para expresar la severidad de un hallazgo, esa reutilización es únicamente una convención de clasificación analítica. No convierte el hallazgo en un evento ni lo registra automáticamente como tal. La severidad tampoco sustituye la clasificación de seguridad definida en CT-04.

Proactivity no debe introducir un catálogo incompatible.

### 8.2 Relevancia

Representa cuánto merece atención una condición para el contexto de Atlas y del usuario.

No debe inferirse únicamente de la severidad.

### 8.3 Confianza

Representa la solidez de la evidencia y del análisis que sustentan un hallazgo.

Una condición puede tener severidad alta y confianza baja. Esta distinción debe conservarse y comunicarse correctamente.

Los criterios concretos de cálculo y los umbrales quedan pendientes de definición técnica.

## 9. Ciclo de vida

### 9.1 Observación

Una fuente autorizada produce o expone una señal. Proactivity registra la observación con su procedencia y referencias disponibles.

### 9.2 Análisis

Las observaciones pueden evaluarse individualmente o correlacionarse para producir hallazgos.

### 9.3 Propuesta

Cuando el resultado justifica atención, Proactivity genera una propuesta y la entrega a Atlas Assistant.

### 9.4 Seguimiento y reevaluación

Una condición puede mantenerse bajo seguimiento cuando todavía no se conoce su evolución o requiere observación posterior.

Proactivity puede reevaluarla automáticamente, siempre que:

- La fuente continúe autorizada.
- La reevaluación sea estrictamente de solo lectura.
- Se conserve la trazabilidad con el seguimiento original.
- No se ejecuten operaciones ni se modifiquen recursos.
- Los errores y la falta de evidencia se reflejen correctamente.

Una reevaluación puede confirmar que la condición persiste, que ha cambiado, que ya no se observa o que no puede determinarse.

### 9.5 Cierre

Un seguimiento puede finalizar cuando la condición deja de ser relevante, ya no puede verificarse, expira conforme a una política futura o es cerrado por el mecanismo autorizado.

Los estados definitivos, transiciones y reglas de expiración requieren una decisión técnica explícita. No deben improvisarse durante la implementación.

## 10. Duplicados y correlación

Proactivity puede correlacionar observaciones relacionadas y evitar propuestas redundantes.

La correlación debe preservar las referencias a las observaciones originales.

La detección de duplicados no implica semántica de idempotencia ni garantiza ejecución única.

No debe descartarse información nueva únicamente porque se parezca a una observación anterior.

Los mecanismos definitivos de deduplicación, claves y ventanas temporales quedan pendientes de decisión técnica.

## 11. Presentación y notificaciones

Proactivity entrega propuestas exclusivamente a Atlas Assistant.

Atlas Assistant decide:

- Si la propuesta merece presentarse.
- Cuándo presentarla.
- Si debe agruparse con otras propuestas.
- Si debe solicitar aclaraciones.
- Si debe descartarse o conservarse para una interacción posterior.
- Si corresponde utilizar un canal de notificación autorizado.

Proactivity no contacta directamente al usuario ni decide canales, horarios o preferencias de notificación.

La presentación debe distinguir claramente entre observaciones verificadas, inferencias, incertidumbres y recomendaciones.

## 12. Eventos y trazabilidad

Los acontecimientos relevantes del ciclo de vida deben integrarse con el sistema de eventos de Atlas conforme a CT-04.

La trazabilidad debe permitir relacionar, cuando corresponda:

- Fuente y observación.
- Hallazgo y evidencia.
- Propuesta generada.
- Entrega a Atlas Assistant.
- Reevaluaciones.
- Cambios de estado del seguimiento.
- Errores relevantes.

Los eventos son inmutables y deben respetar el contrato CT-04, incluidos sus campos, clasificación, severidad y reglas de integridad.

La existencia de un evento no implica que una acción se haya ejecutado ni que una propuesta haya sido aceptada.

## 13. Errores y recuperación

Proactivity debe utilizar el modelo de errores definido en CT-03.

Debe manejar, entre otros:

- Fuentes temporalmente no disponibles.
- Lecturas no autorizadas.
- Evidencia incompleta o inaccesible.
- Resultados contradictorios.
- Fallos durante análisis o correlación.
- Fallos al entregar propuestas a Atlas Assistant.
- Interrupciones durante reevaluaciones.
- Conflictos de concurrencia.

Un error de observación no debe interpretarse como evidencia de que la condición desapareció.

Un fallo de entrega no debe convertirse en una notificación directa alternativa ni en una ejecución automática.

Los mecanismos de reintento, recuperación y persistencia quedan sujetos a decisiones técnicas posteriores.

## 14. Correspondencia con otros contratos

- **CT-03 Errors:** define el tratamiento de errores.
- **CT-04 Events:** define la estructura, clasificación, severidad e inmutabilidad de los eventos.
- **CT-05 Memory:** define los límites de acceso y ciclo de vida de la memoria.
- **CT-06 Atlas Assistant:** define la responsabilidad de recibir propuestas, gestionar la interacción y respetar los niveles de autonomía.
- **CAM y MemoryGateway:** mantienen la autoridad sobre las lecturas protegidas.
- **Scheduler y ejecutores:** conservan sus responsabilidades independientes de admisión y ejecución.

Proactivity no sustituye ninguno de estos componentes.

## 15. Criterios de aceptación

### Observación y fuentes

- **PRO-01:** Proactivity puede registrar una observación procedente de una fuente interna habilitada.
- **PRO-02:** Toda observación conserva una referencia a su fuente.
- **PRO-03:** Una fuente no habilitada no puede ser observada.
- **PRO-04:** El MVP no consulta fuentes externas.
- **PRO-05:** La futura habilitación de fuentes externas requiere política explícita.
- **PRO-06:** La indisponibilidad de una fuente no se interpreta como desaparición de la condición.
- **PRO-07:** Las observaciones conservan el momento en que fueron obtenidas.

### Permisos y memoria

- **PRO-08:** Proactivity no puede omitir los controles de autorización de una fuente.
- **PRO-09:** Toda lectura protegida de memoria utiliza MemoryGateway y CAM.
- **PRO-10:** Una referencia de evidencia no concede permiso de lectura.
- **PRO-11:** Una observación no amplía los permisos de Proactivity.
- **PRO-12:** No existe acceso cruzado entre scopes de memoria sin autorización explícita.

### Análisis y evidencia

- **PRO-13:** Un hallazgo puede referenciar una o varias observaciones.
- **PRO-14:** El sistema distingue observaciones de inferencias.
- **PRO-15:** Las hipótesis no se presentan como hechos confirmados.
- **PRO-16:** Una propuesta conserva referencias a la evidencia que la respalda.
- **PRO-17:** Una evidencia inaccesible se identifica como no disponible.
- **PRO-18:** La confianza se mantiene separada de severidad y relevancia.
- **PRO-19:** La severidad utiliza los valores definidos por CT-04.
- **PRO-20:** La falta de evidencia suficiente impide presentar una conclusión como verificada.

### Propuestas y autoridad

- **PRO-21:** Una condición relevante puede producir una ProactiveProposal.
- **PRO-22:** Una propuesta identifica la condición que la originó.
- **PRO-23:** Una propuesta incluye sus referencias de evidencia disponibles.
- **PRO-24:** Una propuesta distingue incertidumbres y limitaciones.
- **PRO-25:** Toda propuesta se entrega a Atlas Assistant.
- **PRO-26:** Proactivity no envía notificaciones directamente al usuario.
- **PRO-27:** Una propuesta no equivale a autorización ni a una tarea admitida.
- **PRO-28:** El silencio del usuario nunca se interpreta como aprobación.

### Seguimiento y correlación

- **PRO-29:** Una condición puede mantener un registro de seguimiento.
- **PRO-30:** Un seguimiento conserva su relación con las observaciones que lo originaron.
- **PRO-31:** Una condición pendiente puede reevaluarse automáticamente.
- **PRO-32:** La reevaluación automática es estrictamente de solo lectura.
- **PRO-33:** Una reevaluación puede registrar persistencia, cambio, ausencia de observación o resultado indeterminado.
- **PRO-34:** Una reevaluación no ejecuta acciones ni modifica el recurso observado.
- **PRO-35:** La correlación conserva referencias a las observaciones originales.
- **PRO-36:** La deduplicación no implica garantías de idempotencia.
- **PRO-37:** Los estados y transiciones de seguimiento no pueden contradecir las reglas que se definan formalmente para su ciclo de vida.

### Trazabilidad, errores y aislamiento

- **PRO-38:** Los eventos relevantes respetan CT-04.
- **PRO-39:** Los errores respetan CT-03.
- **PRO-40:** Un fallo de entrega no provoca una ejecución ni una notificación alternativa no autorizada.
- **PRO-41:** La indisponibilidad de Proactivity no compromete la operación normal de otros componentes.
- **PRO-42:** Las pruebas verifican que Proactivity no realiza operaciones mutables, no modifica recursos observados y no ejecuta acciones como resultado de sus observaciones o reevaluaciones.

## 16. Decisiones técnicas pendientes

La aprobación de este contrato no fija prematuramente decisiones de implementación.

Quedan pendientes:

1. Catálogo definitivo de fuentes internas y sus permisos.
2. Registro y configuración de observadores.
3. Frecuencia, disparadores y límites de reevaluación.
4. Persistencia de observaciones, hallazgos, propuestas y seguimientos.
5. Formatos definitivos de los modelos e identificadores.
6. Cálculo de severidad, relevancia y confianza.
7. Estrategia de correlación y deduplicación.
8. Estados definitivos y transiciones de seguimiento.
9. Reglas de expiración y cierre.
10. Control de concurrencia.
11. Integración técnica con Atlas Assistant.
12. Preferencias y políticas de presentación gestionadas por Assistant.
13. Políticas futuras para fuentes externas.
14. Clasificación y tratamiento de datos observados.
15. Estrategias de recuperación ante fallos.
16. Tratamiento de contenido malicioso o instrucciones no confiables presentes en las fuentes.

Estas decisiones deberán documentarse antes de implementar los mecanismos correspondientes.

## 17. Secuencia propuesta de implementación

La implementación debe avanzar de forma incremental:

1. Definir los modelos de dominio de Proactivity.
2. Definir las interfaces de observación para fuentes internas.
3. Incorporar validación de permisos y clasificación.
4. Implementar registro de observaciones y referencias de evidencia.
5. Implementar análisis y generación de hallazgos.
6. Implementar generación y entrega de propuestas a Atlas Assistant.
7. Incorporar seguimiento y reevaluación automática de solo lectura.
8. Integrar eventos y errores conforme a CT-04 y CT-03.
9. Implementar pruebas de límites de autoridad, aislamiento y ausencia de mutaciones.
10. Revisar la correspondencia entre contratos antes de ampliar las fuentes o capacidades.

Cada etapa debe contar con pruebas verificables antes de avanzar a la siguiente.

---

**Aprobación:** CT-07 aprobado por el usuario para su publicación documental.

**Límite de alcance:** esta aprobación valida el contrato y sus decisiones de diseño. No implica que Proactivity esté implementado ni desplegado.
