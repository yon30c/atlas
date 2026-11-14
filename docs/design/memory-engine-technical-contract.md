# Memory Engine — contrato técnico e invariantes

**Decisión de arquitectura — 13 de noviembre de 2026:** Trust Anchor externo es opcional y su implementación queda postergada hasta la etapa final de Atlas. El perfil local no demuestra anti-rollback frente a una restauración coherente del conjunto local. Por tanto, la garantía MEM-14 de no reaparición sigue siendo normativa, pero una restauración que pueda reintroducir datos anteriores a un Forget no puede habilitarse sin una fuente independiente de supresión/continuidad o reconciliación explícita aprobada.

**Estado:** diseño técnico consolidado; decisiones de dominio detalladas en DM-01 (`docs/design/domain-model-specification-dm-01.md`). Parámetros de infraestructura, autenticación y operación de supresión permanecen pendientes.  
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

## 1.1 Independencia respecto de los proyectos consumidores

**DECISIÓN DE ARQUITECTURA — 14 de noviembre de 2026:** Memory Engine será un componente independiente y reutilizable por Atlas y por otros proyectos. Su dominio, reglas y contratos no dependerán de Wonderful Tours, LeadRD, MisFinanzas ni de ningún consumidor concreto. La integración con cada aplicación se realizará mediante puertos y adaptadores explícitos.

Esta decisión establece independencia lógica y contractual; no declara que el desacoplamiento ya esté implementado.

### 1.1.1 Core independiente

El núcleo de Memory Engine será agnóstico respecto del proyecto consumidor. Le corresponde aplicar las reglas comunes de memoria: identidad y versionado, scope, clasificación, procedencia, propuestas y revisión, autorización en las fronteras definidas, recuperación protegida, consistencia y olvido.

El Core NO debe:
- Importar módulos, modelos de dominio ni servicios propios de AtlasCore, LeadRD, Wonderful Tours, MisFinanzas u otra aplicación consumidora.
- Depender directamente de sus modelos de usuario, sesiones, proyectos, entornos, repositorios o mecanismos de autenticación.
- Inferir permisos a partir del nombre del proyecto, de la aplicación que realiza la llamada o de identificadores proporcionados sin validación.
- Conceder acceso, ampliar permisos ni convertir una integración en una autoridad de aprobación.

El Core conservará las reglas normativas existentes, incluidos los scopes `PRIVATE` y `PROJECT`, la aprobación explícita del propietario, la autorización CAM, Memory Gateway, la procedencia y las garantías de Forget. Esta decisión no cambia esos contratos.

### 1.1.2 Puertos, adaptadores y consumidores

Las dependencias externas se expresarán mediante contratos independientes del consumidor. Según las necesidades de cada integración, podrán existir adaptadores para:
- Identidad y autenticación del actor.
- Autorización y evaluación de decisiones CAM.
- Resolución y validación de proyectos y entornos.
- Persistencia del dominio y de sus versiones.
- Búsqueda léxica, índice semántico y embeddings.
- Reloj, auditoría, almacenamiento de evidencia y operaciones de eliminación.

Los adaptadores traducen los modelos propios de cada aplicación a los contratos de Memory Engine. No trasladan lógica de negocio del consumidor al Core ni pueden relajar sus invariantes. La ausencia, error o respuesta no verificable de una dependencia necesaria debe producir denegación o fallo seguro, según la operación.

AtlasCore y las demás aplicaciones serán clientes de Memory Engine. Ningún cliente accederá directamente a sus almacenes, índices, sesiones internas o credenciales; toda operación protegida seguirá pasando por Memory Gateway y la autorización correspondiente.

### 1.1.3 Aislamiento entre consumidores y proyectos

La reutilización del mismo motor NO significa compartir automáticamente datos:
- Cada operación debe identificar y validar el actor y el contexto del consumidor; cuando corresponda, también el proyecto y el entorno.
- El aislamiento entre proyectos se mantiene incluso cuando el motor se despliegue como servicio centralizado.
- Un consumidor no obtiene acceso a memorias de otro proyecto por conocer sus identificadores, compartir proceso, base de datos, índice, propietario declarado o instancia de servicio.
- Las búsquedas, expansiones de grafo, referencias de evidencia, índices y cachés deben respetar el mismo ámbito y autorización que la lectura final. Los resultados derivados no conceden permisos.
- No habrá búsqueda ni transferencia entre proyectos por defecto. Cualquier capacidad futura de intercambio requerirá una decisión explícita, autorización verificable y reglas de auditoría propias; no se introduce como parte de esta decisión.
- La memoria `PRIVATE` conserva exactamente la semántica normativa de acceso del propietario y CAM. La existencia de varios consumidores para un mismo propietario no concede por sí sola a cada consumidor acceso general a esa memoria. La política de contexto para integraciones multi-consumidor deberá concretarse y probarse antes de habilitar acceso compartido entre aplicaciones.

Los identificadores de consumidor o tenant que sean necesarios para aplicar estas fronteras pertenecen al contexto de integración y a los puertos correspondientes. Esta decisión no añade un nuevo `MemoryScope`, no modifica el modelo normativo ni autoriza a inferir un nuevo campo de dominio sin una revisión específica.

### 1.1.4 Estrategia de despliegue

La estrategia arquitectónica será:
1. **Servicio centralizado como modalidad predeterminada:** varios consumidores podrán utilizar una instancia común, siempre con aislamiento lógico y autorización independiente por operación.
2. **Instancia aislada por proyecto como modalidad opcional:** podrá utilizarse cuando los requisitos de riesgo, cumplimiento, operación o aislamiento físico lo justifiquen.

La modalidad centralizada no implica una base de datos, un índice, una cuenta de servicio o un espacio de almacenamiento compartido sin controles por consumidor. La modalidad aislada tampoco elimina la necesidad de Gateway, CAM, trazabilidad y reglas del dominio.

Quedan fuera de esta decisión la selección de transporte, topología concreta, tecnología de despliegue, proveedor de almacenamiento, motor de búsqueda y mecanismo de embeddings. Se decidirán por separado y no se introducirán mediante dependencias accidentales.

### 1.1.5 Criterios arquitectónicos de conformidad

La independencia se considerará demostrada cuando:
- El paquete Core pueda importarse y probarse sin importar módulos de los proyectos consumidores.
- Los contratos de integración no expongan tipos concretos de AtlasCore, LeadRD, Wonderful Tours o MisFinanzas.
- Dos consumidores puedan utilizar el mismo servicio sin que uno pueda leer o modificar datos del otro.
- Los adaptadores de identidad, autorización, metadatos y persistencia puedan sustituirse sin modificar las reglas del dominio.
- Las pruebas negativas cubran identificadores conocidos, contextos incompletos, confusión de consumidor/proyecto y consultas derivadas o índices.
- El despliegue central y el despliegue aislado respeten las mismas garantías normativas.

Estos criterios son requisitos de diseño y aceptación futuros; no describen capacidades ya implementadas.

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

- `PRIVATE`: `project_id` debe ser `null`; el titular se identifica mediante `Memory.owner_id`.
- `PROJECT`: `project_id` es obligatorio y debe identificar un proyecto válido.
- `Memory.owner_id` es la representación canónica del propietario; no se duplica en `MemoryScope`.
- No se infiere el scope a partir de `OperationContext.project_id`. El scope forma parte explícita de la memoria o propuesta.
- En memoria privada, la ausencia de `project_id` en el contexto de operación es válida solo cuando el scope `PRIVATE` está explícito. No implica acceso global.
- En memoria de proyecto, un `project_id` ausente, ambiguo o diferente del scope produce denegación.
- Un scope ausente, mal formado o ambiguo produce denegación; nunca se interpreta como acceso global.
- Una memoria de proyecto no se convierte en privada ni viceversa mediante una actualización ordinaria. Transferencia de propietario y reclasificación de scope no están soportadas en v1; cualquier migración futura será un flujo separado conforme a DM-01 §9.3.7.
- La autorización de acceso no se deriva de `owner_id` por sí solo; toda operación protegida debe pasar por Memory Gateway y CAM.

**Resuelto en DM-01:** IDs generados por Atlas usan UUIDv7 canónico; IDs externos se mantienen opacos. Transferencia de propietario y reclasificación de scope no están soportadas en v1. Ver DM-01 §§9.3.6–9.3.7.

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

La clasificación de memoria utiliza el catálogo cerrado INTERNAL, CONFIDENTIAL y RESTRICTED, con orden y reglas de herencia definidos en DM-01 §9.3.5. El catálogo de clasificación de eventos no se reutiliza por inferencia.

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

**Resuelto en DM-01:** esquema mínimo de ProvenanceContext, catálogo SourceKind y referencias opacas están definidos en §9.3.10; retención histórica y tratamiento de referencias se definen en §9.3.8. No se copia el contenido de fuentes por defecto.

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

El contrato del puerto OwnerDecisionVerifier y de OwnerDecisionProof está definido en DM-01 §9.3.4. Sigue pendiente seleccionar e integrar el emisor de autenticación confiable capaz de producir esa prueba. No se debe simular mediante un booleano controlado por el propio Assistant.

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
8. Conservar evidencia mínima de cumplimiento y asegurar que restauraciones/reindexaciones consulten el registro de supresión antes de reintroducir datos. En el perfil local sin Trust Anchor externo, el registro restaurado no demuestra por sí solo ser el más reciente; la restauración de datos que puedan preceder a un Forget requiere reconciliación contra una fuente independiente de supresión aprobada o permanece bloqueada.

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
- Proveedor/emisor de autenticación confiable capaz de emitir la prueba definida por OwnerDecisionVerifier en DM-01 §9.3.4; si no existe, approve/reject/forget permanecen deshabilitados.
- Límites de metadatos/contenido expuestos por índices y política operativa de inventario/supresión; la política de dominio de retención histórica sin TTL automático está definida en DM-01 §9.3.8.

Estos parámetros no autorizan a relajar las invariantes confirmadas ni a declarar implementada una capacidad todavía inexistente.

### 13.7 Alcance que permanece aplazado

SecurityAudit continúa postergado. Cognee, Telegram, scheduler, RLM, despliegues, integración con producción y modificaciones de Broker/Registry v2 permanecen fuera del alcance de esta fase. Este documento consolida diseño; no autoriza cambios en esos sistemas ni afirma que las capacidades descritas estén implementadas.

## 14. Resoluciones técnicas complementarias de DM-01

El documento `docs/design/domain-model-specification-dm-01.md`, en su revisión vigente de la rama de diseño, desarrolla y cierra decisiones de dominio que este contrato había dejado como parámetros técnicos. Para evitar duplicar especificaciones, se aplican estas referencias:

- **Autorización de versiones:** Grant sobre la memoria lógica exacta; versión como subrecurso exacto validado contra el padre (DM-01 §9.3.1).
- **Metadatos confiables:** puertos tipados de memoria, proyecto y entorno, sin usar el Registry del Broker como autoridad de memoria (DM-01 §9.3.2).
- **Prueba directa del propietario:** contrato de OwnerDecisionProof y OwnerDecisionVerifier definido; proveedor de autenticación aún por seleccionar (DM-01 §9.3.4).
- **Clasificación:** catálogo INTERNAL, CONFIDENTIAL y RESTRICTED, y reglas de herencia (DM-01 §9.3.5).
- **IDs:** UUIDv7 para IDs generados por Atlas; IDs externos opacos (DM-01 §9.3.6).
- **Transferencias/reclasificación:** no soportadas en v1 (DM-01 §9.3.7).
- **Retención histórica y procedencia:** sin TTL automático durante la vida de la memoria; referencias mínimas y opacas (DM-01 §§9.3.8 y 9.3.10).
- **Propuestas:** transacción lógica atómica e idempotencia por clave de envío (DM-01 §9.3.9).
- **Operaciones colectivas:** deshabilitadas por tipo en v1 (DM-01 §9.3.11).

Estas resoluciones no seleccionan proveedor de autenticación, almacenamiento, adaptadores, retención física de backups ni inventario de destinos. Cuando DM-01 deja esos elementos como pendientes operativos, este contrato no los da por resueltos. El contrato normativo principal y CT-01 a CT-08 mantienen precedencia.



## 15. Decisión de arquitectura — Trust Anchor opcional y postergado

**APROBADO — 13 de noviembre de 2026.** Trust Anchor externo es opcional y su implementación real queda postergada hasta la etapa final de Atlas. Las etapas actuales utilizan el perfil local en un único servidor. El perfil local valida la integridad y continuidad interna disponible, pero no demuestra anti-rollback frente a una restauración coherente del conjunto local ni que el head recuperado sea el último estado existente.

La garantía MEM-14 de no reaparición sigue siendo normativa. Por tanto, una restauración que pueda reintroducir datos anteriores a un Forget no puede habilitarse sin una fuente independiente de supresión/continuidad o reconciliación explícita aprobada. Esta limitación no se resuelve con una comprobación de integridad local. La decisión no implementa ni activa Trust Anchor, Forget físico, lecturas protegidas o restauraciones productivas.


## 16. Estado de implementación — independencia del proyecto consumidor

**ME-D1 — primera extracción implementada en la rama funcional, pendiente de pruebas.** Se incorporaron `MemoryRequestContext`, `MemoryAuthorizationResult`, `MemoryAuthorizationPort` y `AtlasMemoryAuthorizationAdapter`. `MemoryGatewayService` ahora depende del puerto y del contexto neutral, no directamente de `MemoryAuthorizationService` ni de `OperationContext`.

El contexto neutral transporta atributos y **no es una prueba de autenticación**. Solo debe ser emitido por una frontera de identidad confiable del consumidor. El adaptador debe validar contra fuentes autoritativas y fallar cerrado. La extracción no altera las reglas PRIVATE/PROJECT, el orden de autorización ni las garantías de lectura protegida.

El adaptador Atlas conserva temporalmente la integración CAM existente. La independencia completa no está terminada: permanecen acoplamientos en modelos/validadores, metadatos, consistencia/recuperación local y autorización; tampoco existe aún persistencia del contenido de memoria. El alcance y las fases pendientes se registran en `docs/design/memory-engine-project-independence-implementation.md`.

Esta anotación describe código incorporado, no una validación de pruebas. No se ejecutaron pruebas en esta etapa.


### 16.1 ME-D2 — contrato neutral de identidad

**Implementado en la rama funcional; pendiente de pruebas.** Se añadió `atlas.memory.identity.MemoryIdentityBinding`, junto con `MemoryIdentityBindingPort` y `resolve_authenticated_memory_binding`. El contrato expresa una vinculación actor-sujeto verificada, activa y versionada, sin depender de `OperationContext`, `Identity` ni de los tipos de autorización de Atlas.

Atlas conserva su contrato histórico `AuthenticatedUserSubject`/`IdentitySubjectBindingPort`. `AtlasIdentityBindingAdapter` lo traduce al contrato neutral, y `MemoryAuthorizationService` consume el resultado neutral. La política CAM de Atlas, sus Grants y su evaluación PROJECT permanecen en el adaptador/servicio Atlas; esta fase no convierte al consumidor en autoridad de acceso ni altera las reglas PRIVATE/PROJECT.

La vinculación de identidad no es una autorización: solo acredita la relación actor-sujeto desde una fuente confiable. La política debe seguir verificando el propietario canónico y todos los atributos de scope y recurso. Fallos, binding ausente, actor inactivo, identidad discordante o revisión discordante deben denegar.

ME-D2 no termina la independencia. La resolución de metadatos de proyecto/entorno y la política CAM siguen siendo Atlas; aún faltan pruebas de conformidad, persistencia de contenido y un segundo consumidor real. No se ejecutaron pruebas ni builds.


### 16.2 ME-D3 — resolución neutral de metadatos

**Implementado en la rama funcional; pendiente de pruebas.** Los contratos `MemoryMetadataPort`, `ProjectMetadataPort` y `EnvironmentMetadataPort` se encuentran ahora en `atlas.memory.ports.metadata`. Cada consumidor debe implementar estos puertos contra su fuente canónica; los puertos no conceden permisos ni devuelven contenido.

`MemoryMetadataResolver` se trasladó a `atlas.memory.metadata_resolver`. Comprueba identificadores exactos y tipos de respuesta para memoria, versión, proyecto y entorno. Excepciones, ausencia de datos, respuestas de tipo incorrecto o identificadores discordantes producen ausencia; no hay fallback a valores del contexto del solicitante. El resolver no recupera contenido, fragmentos ni embeddings.

Los snapshots de metadatos usan el error de contrato propio de Memory Engine y validan UUIDv7 canónico para IDs de memoria/versiones sin depender del error ni del validador de Atlas. Se conservaron los módulos históricos de puertos y resolver como reexportaciones de compatibilidad. `MemoryAuthorizationService` consume el resolver desde el paquete de memoria.

Esta extracción no mueve CAM, Grants, evaluación PROJECT ni snapshots de autorización fuera de Atlas. Tampoco completa el desacoplamiento de todos los modelos/validadores: permanecen dependencias históricas de `atlas.core` en otros componentes. No se ejecutaron pruebas ni builds.
