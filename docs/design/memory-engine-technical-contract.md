# Memory Engine — contrato técnico e invariantes

**Estado:** diseño técnico consolidado; decisiones de diseño confirmadas por el propietario. Parámetros operativos de retención y detalles de implementación permanecen pendientes.  
**Base normativa:** `Contrato-de-diseno-Atlas-v1.md`, revisión 2, especialmente §§ 3, 9, 14.5 y 15.  
**Alcance:** especificación de dominio y fronteras para la Fase 1.  
**Implementación:** no incluida. Este documento no declara capacidades implementadas ni aprueba parámetros que el contrato vigente deja pendientes.

## 1. Objetivo

Definir los contratos mínimos que permitan implementar Memory Engine y Memory Gateway sin debilitar las garantías ya aprobadas:

- Separación entre memoria privada del usuario y memoria asociada a proyectos.
- Aislamiento efectivo entre proyectos.
- Autorización mediante CAM en cada operación protegida.
- Incorporación mediante revisión humana.
- Versiones históricas trazables.
- Procedencia verificable.
- Olvido sujeto a aprobación directa del propietario y verificación de eliminación.
- Prohibición de que Assistant, Memory Engine, Watchers o Skills se auto concedan permisos o aprueben decisiones de memoria.

Este diseño se limita al dominio y a los puertos. No selecciona base de datos, motor semántico, proveedor de modelos, transporte ni despliegue.

## 2. Autoridad y clasificación

Se aplican las categorías del contrato vigente:

- **APROBADO:** invariante que ya figura como decisión aprobada en el contrato.
- **PROPUESTA TÉCNICA:** representación o mecanismo recomendado aquí; requiere revisión cuando concrete una decisión todavía abierta.
- **PENDIENTE:** parámetro que no debe darse por resuelto mediante una implementación accidental.

La especificación técnica no puede cambiar una decisión aprobada. En caso de contradicción prevalece el contrato de diseño.

## 3. Modelo conceptual

Se distinguen cuatro conceptos:

1. **Memory:** unidad lógica de conocimiento, con identidad estable y scope explícito.
2. **MemoryVersion:** versión inmutable de una memoria. Una versión aprobada no se modifica en sitio.
3. **MemoryProposal:** solicitud de incorporación o nueva versión que espera revisión.
4. **MemoryProvenance:** evidencia del origen y del proceso mediante el cual se obtuvo el contenido.

La propuesta separa la identidad lógica de la memoria de sus versiones. Así se conserva el historial sin tratar una propuesta pendiente como conocimiento vigente.

### 3.1 Scope

**APROBADO por el contrato:**

- El scope distingue memoria privada del propietario y memoria asociada a un proyecto.
- El propietario accede a su propia memoria privada mediante una regla explícita evaluada por CAM, sin requerir un Grant de proyecto. Memory Gateway sigue siendo obligatorio.
- Ningún otro actor obtiene acceso a esa memoria privada por defecto.
- El acceso a memoria de proyecto requiere un `project_id` explícito, válido y coincidente, además de autorización CAM.
- La memoria de un proyecto no puede acceder a la memoria privada de otro proyecto por defecto.
- CAM controla el acceso y el alcance.
- Un índice global puede localizar referencias, pero no revelar contenido privado.

**PROPUESTA TÉCNICA de representación:**

```text
MemoryScope
  kind: PRIVATE | PROJECT
  project_id: ProjectId | null
```

Invariantes:

- `PRIVATE`: `project_id` debe ser `null`; el contenido pertenece al usuario propietario.
- `PROJECT`: `project_id` es obligatorio y debe identificar un proyecto válido.
- No se infiere el scope a partir de `OperationContext.project_id`. El scope forma parte explícita de la memoria o propuesta.
- Un scope ausente, mal formado o ambiguo produce denegación; nunca se interpreta como acceso global.
- Una memoria de proyecto no se convierte en privada ni viceversa mediante una actualización ordinaria. Un cambio de scope requiere una operación explícita, revisada y autorizada; el mecanismo concreto queda pendiente.
- `Memory.owner_id` es la representación canónica del propietario; no se duplica en `MemoryScope`.
- Para `PRIVATE`, `project_id` debe ser `null` y el propietario canónico de `Memory` identifica al titular.
- Para `PROJECT`, `project_id` es obligatorio y debe identificar un proyecto válido.
- En memoria privada, la ausencia de `project_id` en el contexto de operación es válida solo cuando el scope `PRIVATE` está explícito. No implica acceso global.
- En memoria de proyecto, un `project_id` ausente, ambiguo o diferente del scope produce denegación.
- El owner identifica al propietario de la memoria. No sustituye la autorización de acceso al proyecto.

**PENDIENTE:** formato definitivo de los identificadores y política para transferir o reclasificar una memoria entre scopes.

### 3.2 Memory y MemoryVersion

**PROPUESTA TÉCNICA:**

```text
Memory
  memory_id: MemoryId
  owner_id: UserId
  scope: MemoryScope
  current_approved_version_id: MemoryVersionId | null
  created_at: Instant
  updated_at: Instant

MemoryVersion
  version_id: MemoryVersionId
  memory_id: MemoryId
  version_number: PositiveInteger
  content: Content
  classification: MemoryClassification
  status: MemoryStatus
  provenance: MemoryProvenance
  parent_version_id: MemoryVersionId | null
  created_at: Instant
  submitted_at: Instant
  reviewed_at: Instant | null
  reviewed_by: UserId | null
```

Reglas:

- `memory_id` identifica la memoria lógica; `version_id` identifica una versión concreta e inmutable.
- `version_number` aumenta dentro de una misma memoria y no se reutiliza.
- `classification` es explícita por versión. Una versión nueva no puede reducir automáticamente la clasificación anterior; cualquier cambio requiere revisión y decisión directa del propietario.
- `parent_version_id` conserva la relación con la versión anterior cuando corresponda.
- El contenido de una versión no se modifica después de su creación. Una corrección crea otra versión y pasa por revisión.
- `current_approved_version_id` solo puede apuntar a una versión `approved`.
- Una versión pendiente o rechazada nunca se publica como versión aprobada vigente.
- El cambio de versión vigente y la transición de la anterior a `superseded` deben ser consistentes: no puede quedar una ventana en la que ambas versiones se presenten como vigentes.
- El historial no autoriza a exponer versiones anteriores a un actor que no pueda leer la memoria correspondiente.

La representación física puede variar, pero debe preservar estas propiedades.

### Propuestas y versiones

Una `MemoryProposal` identifica de forma inequívoca si solicita crear una nueva identidad lógica o una nueva versión de una memoria existente. Debe mantener referencias a la propuesta, la memoria objetivo cuando exista y la versión creada para revisión. La propuesta no altera directamente una versión aprobada. Toda propuesta admitida al proceso de revisión genera una versión `pending_review`; mientras permanezca pendiente, la versión aprobada anterior continúa siendo la vigente. La aprobación y sustitución se realizan atómicamente conforme a §3.3.

La clasificación de memoria tendrá un catálogo propio que deberá definirse antes de implementar las políticas de clasificación. El catálogo de clasificación de eventos del contrato principal no se reutiliza por inferencia.

### 3.3 Estados y transiciones

**APROBADO por el contrato (§§ 9.3 y 14.5):**

- `pending_review → approved | rejected`
- `approved → superseded | forgotten`
- Una modificación posterior crea una nueva versión en `pending_review`.
- `rejected`, `superseded` y `forgotten` no representan conocimiento aprobado vigente.

Reglas adicionales de aplicación:

- La creación de una propuesta no equivale a aprobación.
- Solo el propietario de Atlas puede aprobar o rechazar una propuesta.
- Assistant, Memory Engine, Watchers, Skills y aprobadores delegados no pueden tomar esa decisión en nombre del propietario.
- Una versión aprobada anterior permanece como versión vigente mientras la nueva versión está pendiente. Cuando la nueva versión se aprueba, la sustitución debe realizarse de forma consistente.
- Una propuesta rechazada no se reactiva ni se edita en sitio; una nueva presentación crea una nueva propuesta/versionado trazable.
- `forgotten` solo se asigna cuando el proceso de eliminación aplicable ha sido completado y verificado. No debe utilizarse como etiqueta anticipada de una solicitud de olvido.

No se agregan estados nuevos al ciclo de vida aprobado. Los estados operativos de una solicitud de eliminación, si se necesitan, pertenecen al proceso de eliminación y no sustituyen los estados de MemoryVersion.

## 4. Procedencia

**APROBADO por el contrato:** la procedencia debe conservarse para rastrear el origen de cada registro.

**PROPUESTA TÉCNICA:** cada versión debe conservar una estructura de procedencia inmutable, con campos según el origen:

- `source_kind`: conversación, usuario, proyecto, evento, documento, conector u otro origen tipado.
- `source_ref`: referencia opaca al origen, cuando exista.
- `captured_at`: instante UTC de captura.
- `captured_by`: identidad que originó o registró la propuesta.
- `origin_context`: origen y correlación de la operación.
- `transformation`: resumen de transformaciones relevantes, sin secretos ni payloads innecesarios.
- `evidence_refs`: referencias a evidencia, sujetas al mismo control de acceso que el recurso referenciado.

La procedencia no constituye autorización. Una referencia de origen no permite saltarse CAM ni el scope de la memoria.

**PENDIENTE:** esquema definitivo, retención de referencias y tratamiento de fuentes que desaparecen o dejan de ser accesibles.

## 5. Memory Gateway: frontera obligatoria

**APROBADO por el contrato:** Memory Gateway es la única frontera para consultar y proponer cambios de memoria. Ningún módulo de dominio recibe acceso directo a conexiones, repositorios físicos, archivos de almacenamiento o credenciales.

El Gateway debe ser el punto de aplicación de scope y autorización. No concede permisos: consulta CAM y aplica su resultado.

### 5.1 Operaciones lógicas

**PROPUESTA TÉCNICA:** el puerto debe expresar, como mínimo, operaciones equivalentes a:

- `list_visible(context, query)`: recuperar únicamente memorias aprobadas y autorizadas.
- `get_version(context, memory_id, version_id)`: recuperar una versión solo si la lectura está autorizada.
- `submit_proposal(context, proposal)`: registrar una propuesta en `pending_review`.
- `approve_proposal(context, proposal_id, owner_approval)`: aprobar exclusivamente con decisión directa y verificable del propietario.
- `reject_proposal(context, proposal_id, owner_decision)`: rechazar exclusivamente con decisión directa y verificable del propietario.
- `request_forget(context, memory_id, owner_approval)`: iniciar el proceso autorizado de olvido; no declarar la eliminación completada por el mero registro de la solicitud.

Los nombres y firmas definitivos pueden variar. Las garantías no.

### 5.2 Autorización por operación

Antes de cada operación protegida, el Gateway debe:

1. Validar el contexto y la identidad del actor.
2. Validar el scope y los identificadores de propietario/proyecto.
3. Construir una solicitud de autorización específica para la acción y el recurso.
4. Consultar CAM.
5. Denegar si CAM deniega, no está disponible, devuelve un resultado inválido o no puede evaluar el scope completo.
6. Acceder al almacenamiento solo después de la autorización.
7. Mantener la misma frontera para lectura, propuesta, revisión y olvido.

Acciones lógicas diferenciadas: `memory.read`, `memory.propose`, `memory.approve`, `memory.reject` y `memory.forget`. La aprobación y el olvido requieren además la decisión directa del propietario; un Grant por sí solo no reemplaza esa decisión.

### 5.3 Fallo cerrado y aislamiento

- Scope incompleto o ambiguo: denegar.
- Proyecto inexistente o no validado: denegar.
- CAM no disponible o error de evaluación: denegar.
- Memoria de otro propietario: denegar salvo la regla de acceso explícita aplicable, validada por CAM.
- Proyecto A intentando leer memoria del proyecto B: denegar sin autorización explícita válida.
- El índice global puede devolver referencias mínimas para localización, pero nunca contenido, fragmentos, embeddings recuperables ni metadatos que filtren información privada sin autorización.
- No se permite fallback a una consulta sin filtro de propietario/proyecto.

### 5.4 Observación sobre el CAM existente

El código actual dispone de `AuthorizationPort`, `AuthorizationRequest` y `AuthorizationEvaluator`. El Gateway todavía no integra ese puerto.

Además, el evaluador actual comprueba actor, propietario, proyecto, entorno, tipo de recurso, acción y vigencia del Grant, pero no compara `request.resource_id` con un identificador de recurso autorizado. Por tanto, no debe asumirse que hoy existe autorización granular por memoria concreta.

Antes de habilitar lecturas o mutaciones de memoria, deberá definirse y probarse cómo se restringe el acceso al recurso y a su scope. Esta especificación no modifica ni amplía por sí sola la política general de CAM.

## 6. Revisión y autoridad del propietario

El flujo de incorporación propuesto es:

```text
Origen
  → MemoryProposal
  → pending_review
  → decisión directa del propietario
      ├─ approve → approved
      └─ reject  → rejected
```

Reglas:

- La propuesta conserva actor, origen, contexto, scope y procedencia.
- La identidad autenticada del decisor debe corresponder al propietario de Atlas; no basta con que el payload declare un `owner_id`.
- Una delegación, Grant, skill o servicio no puede sustituir la aprobación directa.
- La aprobación no concede acceso a otros proyectos ni cambia clasificación o permisos.
- La propuesta pendiente no se incluye en recuperación de conocimiento aprobado.
- Las decisiones deben asociarse a la versión exacta revisada; cambios de contenido posteriores invalidan esa revisión y requieren nueva propuesta.

La forma técnica de capturar una aprobación directa y verificable queda pendiente de integrar con el futuro flujo de identidad/autenticación y aprobación. No se debe simular mediante un booleano controlado por el propio Assistant.

## 7. Olvido y eliminación verificable

**APROBADO por el contrato (§ 9.4):**

- `memory.forget` requiere autorización CAM y aprobación específica y directa del propietario.
- La aprobación no es delegable.
- La eliminación comprende almacenes principales, índices derivados, réplicas y respaldos pertinentes.
- Restauración y reindexación no pueden reintroducir memorias olvidadas.
- La evidencia permite verificar la eliminación sin conservar innecesariamente el contenido olvidado.

**PROPUESTA TÉCNICA de flujo:**

1. Identificar la memoria lógica y el conjunto de versiones afectadas.
2. Obtener aprobación directa del propietario para el objetivo exacto.
3. Revalidar CAM para la operación y el recurso.
4. Crear una instrucción de supresión durable que identifique el objetivo sin conservar el contenido.
5. Eliminar o invalidar contenido en almacenes primarios y sistemas derivados.
6. Verificar cada destino pertinente, incluyendo réplicas y respaldos según la política aplicable.
7. Marcar las versiones afectadas como `forgotten` solo cuando se cumpla el criterio de finalización.
8. Conservar evidencia mínima de cumplimiento y asegurar que restauraciones/reindexaciones consulten el registro de supresión antes de reintroducir datos.

Una operación incompleta o con resultado incierto no se reporta como olvido completado. Debe permanecer identificada para reconciliación y no permitir que el contenido vuelva a exponerse.

**PENDIENTE:** política de retención de respaldos, plazo máximo de propagación, criterio verificable por tipo de almacén, formato del registro mínimo de supresión y tratamiento de respaldos inmutables. Estos parámetros no pueden debilitar la garantía de no reaparición.

## 8. Assistant y proactividad: límites de integración

### 8.1 Atlas Assistant

Atlas Assistant podrá:

- Consultar memorias mediante Memory Gateway y el contexto autorizado.
- Presentar información recuperada indicando si es memoria histórica, estado observado o análisis.
- Proponer nuevas memorias o versiones mediante el Gateway.
- Solicitar al propietario una decisión de revisión u olvido.

Atlas Assistant no podrá:

- Leer almacenamiento directamente.
- Tratar propuestas pendientes como conocimiento aprobado.
- Aprobar, rechazar, sustituir o olvidar memorias por iniciativa propia.
- Conceder Grants, ampliar scopes o modificar políticas de CAM.

### 8.2 Watchers y Analysis Engine

- Watchers son observadores de solo lectura: recogen/publican eventos y no ejecutan operaciones protegidas.
- Analysis Engine analiza eventos y genera conclusiones/propuestas; no modifica recursos.
- Un análisis puede originar una propuesta de memoria, pero esta debe entrar en el mismo proceso de revisión.
- Los eventos y conclusiones no se convierten automáticamente en memoria aprobada.
- La proactividad no obtiene acceso adicional por el hecho de ejecutarse en segundo plano.

## 9. Invariantes de aceptación

Estas pruebas deben existir antes de considerar Memory Engine funcional:

| ID | Invariante | Resultado exigido |
|---|---|---|
| MEM-01 | Scope explícito | Una memoria sin scope válido no se almacena ni se consulta. |
| MEM-02 | Aislamiento de proyectos | Un proyecto no lee memoria privada ni memoria de otro proyecto sin autorización explícita válida. |
| MEM-03 | Memoria privada | Solo el propietario puede acceder a su memoria privada, sujeto a identidad válida. |
| MEM-04 | CAM obligatorio | Toda operación protegida consulta CAM; fallo o indisponibilidad produce denegación. |
| MEM-05 | Recurso específico | Una autorización para un recurso no permite acceder a otro recurso por compartir tipo de recurso. |
| MEM-06 | Revisión | Una propuesta nueva queda en `pending_review` y no aparece en recuperación aprobada. |
| MEM-07 | Autoridad | Solo la decisión directa del propietario puede aprobar o rechazar una propuesta. |
| MEM-08 | Versionado | Una edición crea una versión nueva; las versiones son inmutables y trazables. |
| MEM-09 | Sustitución | La versión anterior sigue vigente mientras la nueva está pendiente; al aprobar la nueva, la anterior pasa a `superseded`. |
| MEM-10 | Procedencia | Cada versión conserva su origen y referencias de evidencia sujetas a autorización. |
| MEM-11 | Índice global | La búsqueda global no revela contenido ni metadatos privados no autorizados. |
| MEM-12 | Olvido autorizado | No se inicia `memory.forget` sin aprobación directa del propietario y autorización CAM. |
| MEM-13 | Olvido verificable | No se marca `forgotten` ni se comunica éxito hasta verificar los destinos pertinentes. |
| MEM-14 | No reaparición | Reindexación, importación y restauración respetan el registro de supresión. |
| MEM-15 | Frontera única | Ningún componente consulta o modifica el almacenamiento fuera de Memory Gateway. |
| AST-01 | Assistant limitado | Assistant no aprueba memorias ni concede permisos. |
| PRO-01 | Watchers de solo lectura | Watchers publican observaciones, no mutan recursos. |
| PRO-02 | Analysis sin ejecución | Analysis Engine produce conclusiones/propuestas, no ejecuta cambios. |

Las pruebas deben incluir casos positivos y negativos, especialmente contextos incompletos, actor distinto del propietario, proyecto cruzado, CAM no disponible, recurso distinto, versión modificada después de revisión y eliminación parcialmente completada.

## 10. Correspondencia con el estado actual del repositorio

La inspección de `main` muestra una base de modelos y puertos, no un Memory Engine funcional:

- `MemoryStatus` todavía usa `proposed`, `active`, `archived` y `rejected`, distintos del ciclo de vida aprobado.
- `Memory` solo contiene ID, owner, contenido, estado y fecha; no representa scope, versiones ni procedencia.
- `MemoryProposal` valida que el owner coincida con `context.user_id`, pero no implementa revisión exclusiva del propietario.
- `MemoryGateway` solo declara lectura contextual y recepción de propuestas; no integra CAM ni implementa revisión/olvido.
- `OperationContext` permite que `project_id` y `environment` estén ausentes; por sí solo no resuelve el scope.
- CAM tiene puerto y evaluador, pero no está integrado en Memory Gateway y el evaluador no vincula el Grant a `resource_id`.
- `DomainEvent` es una dataclass congelada, pero su `attributes` puede contener un mapping mutable; la inmutabilidad es superficial.
- Assistant y proactividad tienen modelos iniciales, no flujos de aplicación ni Watchers/Analysis Engine funcionales.

Esta correspondencia es una inspección del código disponible en la revisión de este documento; no equivale a pruebas de comportamiento ni a una certificación de runtime.

## 11. Parámetros técnicos pendientes de especificación

Las siguientes decisiones de diseño ya fueron confirmadas y no deben volver a tratarse como pendientes: scopes `PRIVATE` y `PROJECT`, regla de acceso privado del propietario evaluada por CAM, autorización de proyecto con scope explícito, autorización granular por recurso, separación entre `Memory` y `MemoryVersion`, clasificación por versión, procedencia obligatoria, aprobación exclusiva del propietario, sustitución atómica de versiones y separación del proceso de supresión respecto al ciclo de vida de versiones.

Permanecen pendientes los parámetros y mecanismos de implementación siguientes:

1. Formato definitivo de identificadores y política de transferencia/reclasificación entre scopes.
2. Catálogo de clasificación específico de Memory Engine y sus reglas de propagación.
3. Evidencia técnica verificable de que una decisión fue iniciada directamente por el propietario.
4. Política de retención de versiones históricas.
5. Registro de supresión: formato, almacenamiento, reconciliación y resistencia a restauraciones/importaciones.
6. Inventario de almacenes, índices, cachés, réplicas y respaldos, junto con plazos y criterios de verificación de supresión.
7. Semántica técnica de operaciones colectivas autorizadas por tipo de recurso.
8. Límite de contenido y metadatos que puede devolver el índice global.
9. Permisos específicos para proponer cada clase de memoria.

No se requiere seleccionar todavía base de datos, Cognee, motor de embeddings, scheduler, Telegram ni despliegue. Cognee permanece sin instalar, y SecurityAudit permanece postergado.

## 12. Secuencia de implementación propuesta

Con las decisiones de diseño consolidadas, la implementación solo avanzará después de especificar los parámetros técnicos que bloqueen cada flujo y validar sus criterios de aceptación:

1. **Modelos y contratos:** scopes, estados, versiones, procedencia y validaciones puras.
2. **Pruebas de dominio:** transiciones válidas/ inválidas, inmutabilidad, ownership y scopes.
3. **Memory Gateway + CAM:** frontera única, autorización por operación y aislamiento.
4. **Review:** propuestas, decisiones exclusivas del propietario y publicación de versiones.
5. **Forget:** solo después de definir y probar almacenamiento, derivados, backups y registro de supresión.
6. **Assistant mínimo:** recuperación autorizada y presentación de propuestas, sin autoridad de aprobación.
7. **Proactividad:** eventos observados, análisis y propuestas, sin mutación de recursos.

Cada fase debe quedar cubierta por pruebas antes de continuar. No se introducirán adaptadores de infraestructura ni despliegues como parte de esta especificación.

## 13. Registro de decisiones confirmadas

Las decisiones de esta sección fueron confirmadas por el propietario y complementan —o, cuando se indica expresamente, precisan— las secciones anteriores. En caso de discrepancia, esta sección representa la decisión consolidada más reciente. La confirmación del diseño no significa que estas capacidades estén implementadas.

### 13.1 Autorización y scopes

1. **Memoria privada:** el propietario puede acceder a su propia memoria privada mediante una regla explícita de autorización evaluada por CAM. No necesita un Grant de proyecto. Esto no constituye un bypass: el acceso sigue pasando por CAM y Memory Gateway. Ningún otro actor obtiene acceso por defecto.
2. **Memoria de proyecto:** cada operación exige un `project_id` explícito, válido y coincidente con el scope de la memoria. CAM debe autorizar al actor, proyecto, recurso y acción. No se infiere el proyecto desde la identidad, conversación, origen o procedencia.
3. **Fallos cerrados:** scopes ausentes, incompletos, ambiguos o inconsistentes deniegan la operación.
4. **Autorización por recurso:** cuando la operación se dirige a un recurso concreto, CAM debe comprobar también el `resource_id`. Una autorización por tipo no concede acceso implícito a todos los recursos de ese tipo. Las operaciones genuinamente colectivas solo podrán usar autorización por tipo si esa semántica está expresamente definida y autorizada. No se admiten comodines implícitos.

### 13.2 Identidad lógica, versiones y clasificación

1. `Memory` representa la identidad lógica de una memoria, su propietario, scope y referencia a la versión aprobada vigente.
2. `MemoryVersion` representa una versión inmutable del contenido, con estado, clasificación, procedencia, relación con la versión anterior y metadatos temporales/de revisión.
3. `owner_id` tiene una única representación canónica en `Memory`; no se duplica en `MemoryScope`.
4. Cada versión incluye una `classification` explícita. Una versión nueva no puede rebajar automáticamente la clasificación de la anterior. Los cambios de clasificación requieren revisión y decisión del propietario.
5. Una `MemoryProposal` debe identificar si propone crear una memoria lógica o una nueva versión de una memoria existente. La propuesta se vincula con la memoria y la versión resultante; nunca modifica directamente una versión aprobada.
6. Toda propuesta aceptada para revisión genera una versión en estado `pending_review`. Mientras esa versión está pendiente, la versión aprobada anterior continúa siendo la vigente.
7. La aprobación de una nueva versión y la sustitución de la versión aprobada anterior son atómicas: la anterior pasa a `superseded`, la nueva a `approved` y se actualiza la referencia vigente en una sola transacción. Si la operación falla, no puede quedar un estado parcial.
8. Las versiones son inmutables después de su creación. Una corrección genera otra versión; no reescribe el contenido histórico.

### 13.3 Procedencia y decisiones del propietario

1. La procedencia es obligatoria por versión. Debe registrar, según corresponda, actor/componente de origen, proyecto y contexto, fecha, propuesta originaria, referencias de fuente/evidencia y versión antecesora.
2. Las referencias a fuentes, documentos o evidencias no conceden autorización. Cualquier resolución o lectura de esas referencias debe pasar por sus propios controles de acceso, scope y CAM.
3. Si una fuente desaparece o deja de estar disponible, se conserva su referencia histórica y se marca como no disponible. Esto no elimina automáticamente la memoria ni permite afirmar que la fuente continúa verificándola. Una actualización de contenido requiere una nueva propuesta y versión.
4. La aprobación y el rechazo son decisiones exclusivas y no delegables del propietario. Assistant, Memory Engine, Watchers y Analysis Engine no pueden aprobar, rechazar ni simular una decisión en su nombre.
5. Cada decisión debe poder verificarse y vincularse con la identidad del propietario, la propuesta y versión afectadas, el resultado, la fecha/hora, el contexto de operación y evidencia de que la acción fue iniciada directamente por el propietario. La forma criptográfica o técnica concreta de esa evidencia queda pendiente de especificación, pero no puede sustituirse por una afirmación de un componente interno.

### 13.4 Supresión y olvido

1. Se distinguen el estado de ciclo de vida de cada versión y el estado del proceso de supresión de la memoria lógica. El estado de supresión no introduce nuevos estados al ciclo de vida normativo de las versiones.
2. El proceso de supresión debe representar, como mínimo, que está activo, pendiente/en curso o completado. Los nombres definitivos de esos estados son una decisión de implementación; no deben confundirse con `pending_review`, `approved`, `rejected`, `superseded` o `forgotten`.
3. La solicitud de olvido afecta a la memoria lógica completa y a todas sus versiones históricas, además de índices, réplicas, cachés, almacenes derivados y demás sistemas incluidos en el inventario de retención.
4. El registro de supresión conserva solo los datos mínimos necesarios para impedir la reintroducción. Usa identificadores opacos; no conserva el contenido original ni hashes de contenido que puedan facilitar ataques de diccionario.
5. La supresión se aplica a los almacenes activos y a los índices derivados tan pronto como sea posible. Las copias de respaldo inmutables quedan sujetas a un plazo de retención definido. Mientras una copia física retenida siga existiendo, el proceso no puede declararse completamente finalizado.
6. La supresión lógica debe impedir inmediatamente que la memoria sea consultada, recuperada o expuesta, aunque la purga física de una copia retenida esté pendiente.
7. Toda restauración, reindexación o importación debe consultar y aplicar el registro de supresión antes de hacer datos disponibles. Una memoria suprimida no puede reaparecer por restauración, reindexación, importación ni reconstrucción de índices.
8. Si un almacén, índice, réplica o respaldo no responde, o la eliminación es parcial, no se declara el olvido completado ni se comunica éxito al propietario. La memoria permanece bloqueada para recuperación y el proceso continúa pendiente de reconciliación, reintento y verificación.
9. El estado de versión `forgotten` solo puede reflejarse como resultado completado cuando se cumplan los criterios de verificación definidos para todos los destinos aplicables. La existencia temporal de un respaldo inmutable retenido debe quedar explícita y no puede ocultarse bajo una declaración de eliminación física completa.
10. El plazo exacto de retención de respaldos, la propagación máxima permitida y los criterios operativos detallados de verificación quedan como parámetros técnicos pendientes.

### 13.5 Fronteras de componentes

1. **Memory Gateway** es la frontera obligatoria para todas las operaciones de memoria, incluidas lectura, propuesta, aprobación, rechazo y olvido. Esto se aplica también a procesos internos, tareas programadas y futuras integraciones.
2. Gateway valida scope, solicita la evaluación de CAM y aplica el resultado. No concede permisos, no sustituye a CAM y no aprueba propuestas.
3. Ningún componente accede directamente al almacenamiento de memoria para eludir Gateway.
4. **Atlas Assistant** puede consultar memoria autorizada a través de Gateway, presentar propuestas, solicitar decisiones al propietario y explicar procedencia cuando tenga autorización. No aprueba/rechaza propuestas, no concede Grants ni modifica directamente memorias aprobadas.
5. **Watchers** son observadores de solo lectura: observan fuentes autorizadas y publican eventos. No modifican recursos protegidos ni ejecutan operaciones.
6. **Analysis Engine** analiza eventos y genera conclusiones o propuestas. No modifica recursos, permisos o memorias aprobadas, y no ejecuta acciones en nombre del propietario.

### 13.6 Parámetros que siguen abiertos

La confirmación de las reglas anteriores no cierra los detalles operativos que dependen de la infraestructura futura. Antes de implementar los flujos correspondientes deberán especificarse:

- Plazo de retención de respaldos y copias inmutables.
- Inventario de almacenes, índices, réplicas, cachés y sistemas derivados que participan en supresión.
- Plazos de propagación y criterios verificables para declarar una supresión completada.
- Representación técnica del registro de supresión y su reconciliación durante restauraciones/importaciones.
- Mecanismo verificable para acreditar que una decisión fue iniciada directamente por el propietario.
- Semántica exacta de autorizaciones por tipo para operaciones colectivas, separada de las autorizaciones por recurso concreto.
- Política de retención de versiones históricas y límites de metadatos/contenido expuestos por índices.

Estos parámetros no autorizan a relajar las invariantes confirmadas ni a declarar implementada una capacidad todavía inexistente.

### 13.7 Alcance que permanece aplazado

SecurityAudit continúa postergado. Cognee, Telegram, scheduler, RLM, despliegues, integración con producción y modificaciones de Broker/Registry v2 permanecen fuera del alcance de esta fase. Este documento consolida diseño; no autoriza cambios en esos sistemas ni afirma que las capacidades descritas estén implementadas.

