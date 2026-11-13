# DM-01 — Especificación del modelo de dominio de Atlas Core

**Estado:** recomendaciones técnicas y decisiones de detalle cerradas para la especificación de dominio; parámetros de infraestructura fuera de alcance.  
**Rama base:** `main`  
**Commit base:** `8832e59c8d6895750bfc7053a26bf4f4f3932437`  
**Alcance:** modelo de dominio, identidad de recursos y contrato lógico de autorización requerido para Memory Engine / Memory Gateway.  
**Implementación:** no incluida. Este documento no modifica ni sustituye los contratos normativos.  
**Autoridad:** el contrato principal de Atlas v1 prevalece sobre este documento. Las decisiones técnicas de dominio se registran como adoptadas en §9. Los parámetros operativos y de infraestructura expresamente aplazados no se consideran resueltos por inferencia.

---

## 1. Objetivo

Convertir las decisiones ya aprobadas para Memory Engine y CAM en una especificación de dominio verificable, sin introducir decisiones de persistencia, infraestructura o despliegue.

DM-01 debe permitir que QA-01 derive pruebas de aceptación y que ME-01 implemente modelos sin inferir reglas de seguridad.

Objetivos concretos:

1. Definir los conceptos y relaciones del dominio de memoria.
2. Separar la identidad lógica de una memoria de sus versiones.
3. Representar explícitamente los scopes `PRIVATE` y `PROJECT`.
4. Precisar la identidad de un recurso protegido y el significado de `resource_id`.
5. Especificar un alcance de Grant que no permita autorizar instancias por compartir solamente el tipo.
6. Definir cómo se aplican las reglas especiales de memoria privada del propietario.
7. Identificar las decisiones técnicas que todavía bloquean una implementación completa.

## 2. Autoridad y vocabulario

Se utilizan estas etiquetas:

- **APROBADO:** regla que ya está establecida en el contrato principal o en los contratos CT.
- **PROPUESTA TÉCNICA:** representación o mecanismo recomendado en DM-01. No se considera aprobado hasta que el propietario lo confirme.
- **PENDIENTE:** dato o mecanismo que debe decidirse explícitamente antes de implementar el flujo afectado.
- **FUERA DE ALCANCE:** cuestión que DM-01 no debe resolver.

En caso de contradicción, prevalecen el contrato principal y los contratos CT-01 a CT-08.

DM-01 no autoriza cambios en Atlas Broker, Registry v2, infraestructura protegida ni producción. Tampoco selecciona base de datos, motor semántico, embeddings, proveedor de modelos, scheduler, RLM o despliegue.

## 3. Hallazgos de la implementación actual

La inspección estática de `main` en el commit base identificó:

| Elemento | Implementación actual | Brecha respecto al diseño aprobado |
|---|---|---|
| `Memory` | `memory_id`, `owner_id`, `content`, `status`, `created_at` | No separa versiones ni representa scope o puntero vigente. |
| `MemoryProposal` | `owner_id`, `content`, `context` | No identifica crear memoria frente a crear versión. |
| `MemoryStatus` | `proposed`, `active`, `archived`, `rejected` | No coincide con el ciclo normativo de CT-05. |
| `MemoryGateway` | `list_visible`, `submit_proposal` | No integra CAM ni representa revisión, versión u olvido. |
| `AuthorizationRequest` | acción, tipo, ID y propietario del recurso | No incorpora un scope tipado ni una relación explícita con el recurso padre. |
| `Grant` | tipo de recurso y acciones | No contiene un conjunto de identificadores concretos autorizados. |
| `AuthorizationEvaluator` | valida tipo, acción, actor, owner, proyecto, entorno y vigencia | No compara el `resource_id` solicitado con el alcance autorizado. |

La prueba actual `tests/unit/test_evaluator.py::test_matching_grant_allows_resource_type_not_specific_id` confirma que un Grant permite actualmente otro ID del mismo tipo. Ese comportamiento contradice el requisito aprobado y debe sustituirse por una prueba negativa.

Esta tabla describe código observado; no certifica comportamiento de runtime ni ejecución de la suite.

## 4. Modelo de memoria

### 4.1 MemoryScope

**APROBADO**

- El scope solo puede ser `PRIVATE` o `PROJECT`.
- `PRIVATE` no lleva `project_id`.
- `PROJECT` requiere un `project_id` explícito, válido y coincidente.
- El propietario se representa una sola vez, en `Memory.owner_id`.
- Un scope ausente, inválido, ambiguo o inconsistente produce denegación.
- El scope no se infiere del contexto, la conversación, el origen o la procedencia.
- No hay transferencia ni reclasificación implícita entre scopes.

**DIRECCIÓN TÉCNICA ADOPTADA**

Representación lógica:

```text
MemoryScope
  kind: PRIVATE | PROJECT
  project_id: ProjectId | null
```

Invariantes de construcción:

- `PRIVATE` exige `project_id = null`.
- `PROJECT` exige `project_id` no vacío.
- No se normaliza ni transforma el identificador silenciosamente.
- La validación sintáctica del identificador no demuestra que el proyecto exista; su validación semántica corresponde a una autoridad de proyectos que deberá definirse.

### 4.2 Memory

**APROBADO**

`Memory` representa la identidad lógica estable de una memoria, su propietario canónico, su scope y la referencia a la versión aprobada vigente.

**PROPUESTA TÉCNICA**

```text
Memory
  memory_id: MemoryId
  owner_id: UserId
  scope: MemoryScope
  current_approved_version_id: MemoryVersionId | null
  created_at: Instant
  updated_at: Instant
```

Invariantes:

1. `memory_id` identifica una memoria lógica y no se reutiliza.
2. `owner_id` es la única representación canónica del propietario.
3. `scope` es obligatorio.
4. `current_approved_version_id` puede ser nulo mientras la memoria no tenga una versión aprobada.
5. Si no es nulo, debe apuntar a una versión perteneciente a esa misma memoria y cuyo estado sea `approved`.
6. Una memoria no puede apuntar a una versión de otra memoria.
7. La identidad lógica y su scope no se modifican mediante una actualización ordinaria.
8. Los timestamps son instantes UTC con zona horaria explícita.

La consistencia entre la memoria y las versiones relacionadas requiere validación de dominio/servicio; no puede garantizarse únicamente con la validación aislada de una dataclass.

### 4.3 MemoryVersion

**APROBADO**

- Cada versión es inmutable después de su creación.
- Cada versión tiene clasificación y procedencia propias.
- Una versión nueva no reduce automáticamente la clasificación anterior.
- Una versión pendiente no sustituye a la aprobada vigente.
- La aprobación de una versión nueva, la transición de la anterior a `superseded` y el cambio del puntero vigente son atómicos.
- El historial no concede acceso por sí mismo.

**PROPUESTA TÉCNICA**

```text
MemoryVersion
  version_id: MemoryVersionId
  memory_id: MemoryId
  version_number: PositiveInteger
  content: Content
  classification: MemoryClassification
  status: MemoryVersionStatus
  provenance: MemoryProvenance
  parent_version_id: MemoryVersionId | null
  created_at: Instant
  submitted_at: Instant
  reviewed_at: Instant | null
  reviewed_by: UserId | null
```

Invariantes:

1. `version_id` es único y no se reutiliza.
2. `version_number` es positivo, monotónico dentro de una memoria y no se reutiliza.
3. `memory_id` debe referir a la memoria propietaria de la versión.
4. `parent_version_id`, cuando exista, debe referir a una versión de la misma memoria.
5. `content`, `classification` y `provenance` no se modifican en sitio.
6. Una corrección crea otra versión.
7. La clasificación es obligatoria y utiliza el catálogo ordenado INTERNAL < CONFIDENTIAL < RESTRICTED, definido en §9.3.5. La clasificación no concede permisos ni sustituye CAM.
9. Los campos de revisión son nulos mientras la versión no haya sido decidida y deben ser coherentes con el resultado de revisión.

### 4.4 Estados de MemoryVersion

**APROBADO — conjunto cerrado**

- `pending_review`
- `approved`
- `rejected`
- `superseded`
- `forgotten`

Transiciones permitidas:

```text
pending_review -> approved
pending_review -> rejected
approved       -> superseded
approved       -> forgotten
```

No se agregan estados alternativos como `proposed`, `active` o `archived`.

Reglas:

- `rejected`, `superseded` y `forgotten` no son conocimiento aprobado vigente.
- Una versión rechazada no se reactiva.
- Una versión `forgotten` solo refleja una eliminación completada y verificada.
- El estado del proceso de supresión pertenece a otro modelo y no amplía este conjunto.

### 4.5 MemoryProposal

**APROBADO**

Una propuesta debe identificar si pretende crear una memoria lógica nueva o una versión nueva de una memoria existente. Debe vincularse con la memoria y la versión sometida a revisión, sin modificar una versión aprobada.

**PROPUESTA TÉCNICA**

```text
MemoryProposal
  proposal_id: ProposalId
  intent: CREATE_MEMORY | NEW_VERSION
  memory_id: MemoryId
  version_id: MemoryVersionId
  submitted_by: IdentityId
  submitted_at: Instant
```

Semántica propuesta:

- `CREATE_MEMORY`: identifica una nueva memoria lógica con scope explícito y una primera versión en `pending_review`. Su puntero aprobado permanece nulo hasta la aprobación.
- `NEW_VERSION`: identifica una memoria existente y una nueva versión pendiente; hereda propietario y scope de la memoria objetivo. La propuesta no puede cambiar propietario ni scope.
- El contenido y la clasificación propuestos pertenecen a la versión, no a una copia mutable dentro de la propuesta.
- La propuesta no es por sí misma una memoria aprobada ni un permiso de lectura.
- La creación de Memory, MemoryVersion y MemoryProposal para CREATE_MEMORY constituye una única unidad lógica atómica. Para NEW_VERSION, la creación de MemoryVersion y MemoryProposal también es atómica. La semántica se detalla en §9.3.9; no selecciona almacenamiento físico.

### 4.6 MemoryProvenance

**APROBADO**

La procedencia es obligatoria por versión. Las referencias a fuentes y evidencias no conceden autorización. Si una fuente desaparece, se conserva la referencia histórica y se identifica como no disponible.

**PROPUESTA TÉCNICA**

```text
MemoryProvenance
  source_kind: SourceKind
  source_ref: OpaqueReference | null
  captured_at: Instant
  captured_by: IdentityId
  origin_context: ProvenanceContext
  transformation: TransformationSummary | null
  evidence_refs: tuple[OpaqueReference, ...]
```

Reglas:

- La estructura es inmutable.
- No se copian secretos ni payloads innecesarios.
- Una referencia de evidencia se resuelve bajo sus propios controles de acceso.
- La procedencia no sustituye identidad, autenticación, scope ni CAM.
- El catálogo de SourceKind y la estructura de ProvenanceContext se fijan en §9.3.10.
- Las referencias se conservan como identificadores opacos y metadatos mínimos; no se copia el contenido de la fuente salvo que sea el propio contenido de memoria autorizado.

## 5. Identidad de recursos protegidos

### 5.1 Identidad compuesta

**APROBADO**

Cuando una operación identifica un recurso concreto, CAM debe verificar el `resource_id` exacto. Un permiso sobre el tipo no autoriza todas sus instancias. Un ID ausente, distinto o no verificable produce denegación.

**DIRECCIÓN TÉCNICA ADOPTADA**

Un recurso se identifica dentro de un contexto de autorización por la tupla:

```text
ResourceIdentity
  resource_type
  resource_id
  owner_id
  project_id
  environment_id
```

La comparación de autorización no debe depender de `resource_id` aislado. Debe validar conjuntamente:

- Identidad autenticada y actor efectivo.
- Acción solicitada.
- Tipo e ID exactos del recurso.
- Propietario canónico del recurso.
- Proyecto y entorno aplicables.
- Scope del recurso.
- Vigencia y estado del Grant, cuando la operación dependa de uno.
- Restricciones especiales de la operación, incluidas las decisiones no delegables del propietario.

Los IDs generados por Atlas siguen UUIDv7 canónico conforme a §9.3.6. Los IDs externos se conservan opacos y sin normalización.

### 5.2 Vinculación de versiones con la memoria

**DIRECCIÓN TÉCNICA ADOPTADA**

Toda operación dirigida a una `MemoryVersion` debe incluir o resolver también su `memory_id` padre. El sistema debe comprobar que la versión pertenece a esa memoria y hereda su propietario y scope.

No se acepta como autoridad un `owner_id`, `project_id` o scope declarado libremente por el solicitante. Esos datos deben proceder de una fuente de metadatos confiable.

**DECISIÓN CERRADA — §9.3.1**

El Grant de lectura/propuesta se limita al ID exacto de la memoria lógica (memory_id). La versión solicitada se expresa como subrecurso exacto (version_id) junto con parent_resource_id=memory_id. CAM debe resolver ambos IDs desde metadatos confiables y comprobar que la versión pertenece a esa memoria. Un Grant sobre una memoria no autoriza otra memoria; sí cubre las versiones que pertenecen a esa memoria, sin necesidad de emitir un Grant nuevo por cada versión. Una operación que no especifique versión solo puede utilizar la versión aprobada vigente resuelta por Gateway.

## 6. Alcance de Grants y corrección de CAM

### 6.1 Regla normativa

**APROBADO**

- Un Grant está limitado a un proyecto, entorno, operaciones, recursos y límites autorizados.
- CAM verifica el alcance exacto.
- No existe herencia automática entre proyectos o entornos.
- La delegación no amplía el Grant.
- Ningún componente puede concederse permisos.
- Un tipo de recurso no sustituye la identidad de una instancia concreta.
- Una operación colectiva solo puede autorizarse por tipo cuando su semántica y alcance estén expresamente definidos y autorizados.

### 6.2 Alcance exacto de recurso

**APROBADO POR EL PROPIETARIO**

El modelo lógico de Grant con un conjunto explícito de IDs:

```text
GrantResourceScope
  resource_type: ResourceType
  resource_ids: frozenset[ResourceId]
```

Reglas propuestas:

1. `resource_ids` debe ser no vacío para un Grant que autorice operaciones sobre recursos concretos.
2. Cada ID es explícito; no se admiten `*`, prefijos, rangos implícitos ni coincidencia por tipo.
3. Todos los IDs del conjunto pertenecen al mismo `resource_type`, proyecto, entorno y propietario del Grant.
4. Una solicitud solo coincide si su `resource_id` aparece exactamente en el conjunto.
5. Un Grant puede autorizar varios recursos, pero cada uno debe estar enumerado explícitamente.
6. Un Grant que no tenga alcance de recurso verificable no autoriza una operación sobre una instancia.
7. La ampliación del conjunto de recursos es una modificación de alcance y requiere decisión del propietario; no se produce por delegación ni por creación automática de una nueva versión.

**APROBADO POR EL PROPIETARIO:** adoptar este diseño como dirección técnica para el alcance de recursos de Grant. La implementación deberá conservar las reglas normativas y los criterios de aceptación de QA-01.

### 6.3 Operaciones colectivas

**APROBADO POR EL PROPIETARIO — dirección técnica para la primera implementación**

No habilitar Grants genéricos por tipo ni comodines.

- `list_visible` debe filtrar candidatos por scope y después autorizar cada memoria por su identidad concreta antes de devolver contenido o metadatos protegidos.
- No debe devolver conteos, fragmentos, embeddings, contenido ni metadatos de elementos no autorizados.
- Una creación de memoria PROJECT puede evaluarse contra el recurso contenedor explícito del proyecto (`resource_type=project`, `resource_id=project_id`) y la acción `memory.propose`. La memoria creada obtiene después su propio ID y scope. Esta convención queda aprobada como dirección técnica: la creación PROJECT se autoriza sobre el ID exacto del proyecto contenedor, mediante CAM.
- Las operaciones colectivas por tipo quedan deshabilitadas hasta que tengan semántica, permiso y criterios de aceptación propios.

La enumeración de candidatos utiliza los puertos de metadatos definidos en §9.3.2 y nunca expone contenido ni metadatos protegidos antes de la autorización individual.

### 6.4 Memoria PRIVATE del propietario

**APROBADO**

El propietario puede acceder a su propia memoria PRIVATE mediante una regla explícita evaluada por CAM. No necesita un Grant de proyecto. MemoryGateway y CAM siguen siendo obligatorios. Ningún otro actor obtiene acceso por defecto.

**APROBADO POR EL PROPIETARIO — dirección técnica**

La regla de propietario privado se evalúa como una ruta explícita y limitada, separada de la coincidencia de Grants:

- actor de tipo `USER`;
- identidad activa;
- `actor.identity_id == context.user_id == Memory.owner_id`;
- scope de la memoria explícitamente `PRIVATE`;
- acción dentro del conjunto permitido para la operación;
- recurso exacto y metadatos confiables.

Esta regla no autoriza memoria PROJECT, memoria de otro propietario, ni operaciones administrativas de otros dominios.

Para `memory.approve`, `memory.reject` y `memory.forget`, la coincidencia de propietario no es suficiente: también se exige evidencia verificable de una decisión iniciada directamente por el propietario. Un Grant no sustituye esa evidencia.

La ruta PRIVATE del propietario se limita a memory.read y memory.propose, más memory.export si se habilita expresamente. memory.approve, memory.reject y memory.forget requieren además prueba directa de propietario según §9.3.4. Ninguna otra acción queda autorizada por el mero hecho de ser propietario; cada acción sigue sujeta a CAM.

### 6.5 Solicitud de autorización tipada

**APROBADO POR EL PROPIETARIO — dirección técnica**

La solicitud de CAM transportará una referencia tipada al recurso, en lugar de confiar en campos sueltos que no expresen el scope:

```text
AuthorizationRequest
  context: OperationContext
  action: Permission
  target:
    resource_type: ResourceType
    resource_id: ResourceId
    subresource_type: ResourceType | null
    subresource_id: ResourceId | null
    owner_id: UserId
    scope:
      kind: PRIVATE | PROJECT
      project_id: ProjectId | null
    parent_resource_id: ResourceId | null
```

La estructura es conceptual. No obliga a cambiar inmediatamente la API pública existente.

Invariantes:

- `target.resource_id` es obligatorio para operaciones sobre una instancia concreta; cuando la operación apunta a una versión, `subresource_type=memory_version` y `subresource_id=version_id` son también obligatorios.
- CAM compara el Grant contra el recurso lógico exacto y valida el ID exacto del subrecurso y su relación padre/hijo mediante metadatos confiables.
- `target.owner_id` y `target.scope` deben provenir de metadatos confiables, no del payload no verificado del solicitante.
- `PRIVATE` exige `project_id = null`.
- `PROJECT` exige `project_id` explícito, válido y coincidente con `context.project_id`.
- `parent_resource_id` permite vincular una versión u otro subrecurso con su contenedor lógico.
- Una referencia padre/hijo inconsistente deniega.
- CAM debe fallar cerrado si no puede verificar cualquiera de estas condiciones.

### 6.6 Fuente confiable de metadatos

**DECISIÓN CERRADA — ver §9.3.2**

La autoridad de metadatos y sus puertos se definen en §9.3.2. La implementación debe respetar esa frontera y no usar los datos del solicitante como autoridad.

- recurso e ID;
- propietario;
- scope;
- proyecto;
- entorno;
- recurso padre, cuando corresponda.

El solicitante no puede ser esa fuente. Tampoco se debe asumir que el Registry del Broker es la fuente de metadatos de memoria: su alcance es independiente y está protegido.

**DECISIÓN CERRADA — §9.3.2**

La autoridad de metadatos se implementa mediante puertos de lectura tipados, separados de CAM y del solicitante: MemoryMetadataPort resuelve memoria, versiones, propietario, scope, proyecto, estado, versión vigente y relación padre/hijo; ProjectMetadataPort verifica existencia/estado del proyecto; EnvironmentMetadataPort verifica el entorno cuando aplique; ResourceMetadataResolver enruta por tipo de recurso al resolver registrado.

Los adaptadores consultan la fuente canónica del dominio correspondiente. Para memoria, la fuente canónica es el agregado de memoria; para proyectos, la autoridad de proyectos definida por Atlas. El Registry del Broker no es fuente de metadatos de memoria ni se reutiliza como sustituto. El solicitante nunca aporta metadatos autoritativos. Los puertos devuelven metadatos mínimos, no contenido. Si falta un resolver, hay duplicidad, inconsistencia, timeout o no se puede verificar el vínculo padre/hijo, CAM deniega. La enumeración puede obtener IDs candidatos, pero Gateway debe resolver y autorizar cada uno antes de exponer incluso metadatos protegidos. No se selecciona base de datos ni adaptador.

## 7. Flujos de dominio

Los siguientes flujos describen orden lógico, no implementación física.

### 7.1 Lectura de una memoria

1. El consumidor solicita lectura mediante MemoryGateway.
2. Gateway valida contexto e identidad.
3. Gateway obtiene metadatos autoritativos del recurso sin exponer contenido.
4. CAM evalúa acción, ID exacto, propietario, scope, proyecto, entorno y autorización aplicable.
5. Si CAM no devuelve `ALLOW`, no se recupera ni expone contenido.
6. Solo después de la autorización se recupera el contenido.
7. La respuesta no incluye referencias o versiones fuera del alcance autorizado.

### 7.2 Enumeración de memorias visibles

1. Gateway recibe el contexto.
2. Se determina el scope explícito permitido; no se infiere uno global.
3. Se obtienen candidatos mediante una fuente que no revele contenido.
4. Cada candidato se autoriza por su identidad concreta.
5. Solo se devuelven los autorizados.
6. Errores de evaluación, metadatos incompletos o CAM no disponible excluyen el candidato y no producen fallback abierto.

La paginación, filtros, búsqueda y garantías de rendimiento quedan fuera de DM-01.

### 7.3 Propuesta de memoria nueva

1. Se define un scope explícito.
2. Se genera una identidad lógica y una versión pendiente, conforme a UUIDv7 canónico según §9.3.6.
3. En PRIVATE, CAM evalúa la regla explícita del propietario.
4. En PROJECT, la operación debe estar autorizada sobre el recurso contenedor del proyecto o bajo otra semántica explícita aprobada.
5. Se conserva la procedencia.
6. La versión queda en `pending_review`; no se expone como memoria aprobada.

### 7.4 Propuesta de nueva versión

1. La propuesta identifica la memoria existente.
2. El propietario y scope se heredan de la memoria; no se aceptan cambios declarados por el solicitante.
3. CAM evalúa `memory.propose` sobre el recurso concreto.
4. Se crea una versión inmutable en `pending_review`.
5. La versión aprobada vigente no cambia.

### 7.5 Aprobación y rechazo

1. Se identifica la propuesta y la versión exacta.
2. Se verifica la identidad del propietario.
3. Se verifica evidencia de que la acción fue iniciada directamente por el propietario.
4. Se valida que la versión no haya cambiado desde la revisión.
5. Se ejecuta la transición permitida.
6. En aprobación de nueva versión, aprobación, supersession y puntero vigente se actualizan atómicamente.
7. Assistant, agentes, servicios, Watchers y Skills no pueden decidir en nombre del propietario.

La representación técnica de la evidencia directa sigue pendiente.

### 7.6 Olvido

El olvido requiere CAM y decisión directa no delegable del propietario. La supresión lógica, inventario de destinos, reconciliación y verificación física siguen el contrato CT-05 y no se detallan como implementación en DM-01.

No se marca `forgotten` ni se comunica éxito antes de la verificación completa. Los estados operativos del proceso de supresión permanecen separados de los estados de MemoryVersion.

## 8. Invariantes de dominio y seguridad

Estas invariantes deben traducirse en QA-01:

| ID | Invariante |
|---|---|
| DM-01-01 | Todo objeto Memory tiene un propietario canónico y un scope explícito. |
| DM-01-02 | PRIVATE no contiene project_id; PROJECT requiere project_id explícito. |
| DM-01-03 | MemoryScope no contiene owner_id. |
| DM-01-04 | Una MemoryVersion pertenece a una única Memory. |
| DM-01-05 | La versión vigente pertenece a la Memory y está en approved. |
| DM-01-06 | El contenido, clasificación y procedencia de una versión son inmutables. |
| DM-01-07 | Los estados y transiciones de MemoryVersion son exactamente los aprobados. |
| DM-01-08 | Una propuesta distingue CREATE_MEMORY de NEW_VERSION. |
| DM-01-09 | Una propuesta pendiente nunca se expone como conocimiento aprobado. |
| DM-01-10 | La procedencia no concede acceso. |
| DM-01-11 | Una operación concreta exige resource_id no vacío y exacto. |
| DM-01-12 | Un Grant por tipo sin IDs explícitos no autoriza una instancia concreta. |
| DM-01-13 | Un Grant solo autoriza IDs incluidos explícitamente en su alcance. |
| DM-01-14 | Propietario, scope y proyecto se obtienen de metadatos confiables, no del solicitante. |
| DM-01-15 | PROJECT exige coincidencia explícita entre scope y contexto. |
| DM-01-16 | PRIVATE solo habilita la regla explícita del propietario y nunca omite CAM/Gateway. |
| DM-01-17 | Las decisiones approve/reject/forget requieren acción directa y no delegable del propietario. |
| DM-01-18 | La versión solicitada debe estar vinculada a su Memory padre. |
| DM-01-19 | CAM no disponible, error, scope incompleto o metadatos no verificables producen denegación. |
| DM-01-20 | No existe fallback a autorización por tipo ni a consulta sin filtro de scope. |

## 9. Registro de decisiones técnicas

Las recomendaciones y decisiones de detalle de DM-01 quedan cerradas conforme a las decisiones siguientes. Estas precisan cómo implementar los contratos; no modifican las reglas normativas de CT-01 a CT-08 ni seleccionan infraestructura.

### 9.1 Direcciones técnicas aprobadas

| Referencia | Dirección aprobada |
|---|---|
| §5.2 | Grant sobre la memoria lógica exacta; versión como subrecurso exacto validado contra su padre, conforme a §9.3.1. |
| §6.2 | GrantResourceScope utiliza IDs explícitos e inmutables por tipo de recurso; no hay wildcard ni autorización por tipo solamente. |
| §6.3 | `list_visible` autoriza individualmente cada recurso antes de devolver contenido o metadatos protegidos; las operaciones colectivas permanecen deshabilitadas salvo alcance explícito. |
| §6.3 | La creación de memoria PROJECT se autoriza mediante CAM sobre el ID exacto del proyecto contenedor. |
| §6.4 | La memoria PRIVATE del propietario usa una ruta explícita y limitada de CAM, sin Grant de proyecto y sin omitir Gateway/CAM. |
| §6.5 | AuthorizationRequest adopta una referencia tipada al recurso, con scope y relación padre cuando corresponda. |

### 9.2 Estado de las decisiones originales

| ID | Decisión | Recomendación inicial | Estado |
|---|---|---|---|
| DM-P01 | Representación del alcance de recursos en Grant | Conjunto explícito e inmutable de IDs; sin wildcard | **Aprobado** |
| DM-P02 | Semántica de acceso a versiones | Grant sobre memory_id exacto; version_id como subrecurso exacto validado contra su padre | Cerrado — §9.3.1 |
| DM-P03 | Autorización de creación PROJECT | Autorizar la acción sobre el ID exacto del proyecto contenedor | **Aprobado** |
| DM-P04 | Fuente autoritativa de metadatos | Puertos tipados por dominio y resolver de recursos; fuente canónica de cada dominio | Cerrado — §9.3.2 |
| DM-P05 | Catálogo de clasificación | INTERNAL < CONFIDENTIAL < RESTRICTED; herencia por defecto y cambio sujeto a decisión directa | Cerrado — §9.3.5 |
| DM-P06 | Evidencia directa del propietario | Prueba de emisor confiable, ligada a acción y recursos exactos, de un solo uso | Cerrado como contrato de puerto — §9.3.4 |
| DM-P07 | Formato y generación de IDs | UUIDv7 canónico para IDs generados por Atlas; IDs externos preservados como opacos | Cerrado — §9.3.6 |
| DM-P08 | Transferencia/reclasificación de scope | No soportado en v1; cualquier migración futura será flujo explícito separado | Cerrado — §9.3.7 |
| DM-P09 | Semántica de propuestas | Creación atómica del agregado/propuesta; idempotencia por clave de envío | Cerrado — §9.3.9 |
| DM-P10 | Retención histórica y referencias de procedencia | Historial ligado a vida de memoria; sin TTL automático; olvido elimina todo destino verificable | Cerrado para política de dominio — §9.3.8 |
| DM-P11 | Catálogo SourceKind y estructura ProvenanceContext | Catálogo cerrado y contexto mínimo tipado | Cerrado — §9.3.10 |
| DM-P12 | Operaciones colectivas | Deshabilitadas salvo autorización explícita de un contenedor concreto | **Aprobado** |

No se deben introducir nuevas rutas de autorización por inferencia. Los detalles de autenticación, persistencia, adaptadores, retención física de backups e inventario de destinos se mantienen como decisiones de infraestructura/operación, sin reabrir las decisiones de dominio aquí cerradas.

### 9.3 Resoluciones técnicas adoptadas

#### 9.3.1 DM-P02 — Autorización de versiones

El recurso de autorización estable es la memoria lógica. El Grant se limita al ID exacto de Memory. Una operación sobre una versión incluye además el version_id exacto y parent_resource_id igual al memory_id. CAM comprueba el Grant contra el memory_id y resuelve version_id desde MemoryMetadataPort, verificando pertenencia, estado y parent. Un Grant para una memoria cubre sus versiones presentes y futuras únicamente dentro de esa memoria; nunca cubre otra memoria por tipo o similitud. Si se pide una versión concreta, no se sustituye silenciosamente por la vigente. Si no se especifica versión en una lectura ordinaria, Gateway resuelve la versión aprobada vigente y autoriza la memoria antes de recuperar contenido.

#### 9.3.2 DM-P04 — Autoridad de metadatos

Se adoptan puertos lógicos de lectura, sin fijar adaptadores ni almacenamiento:

- MemoryMetadataPort: resuelve memoria/versiones, propietario, scope, proyecto, estado, versión vigente y relación padre/hijo.
- ProjectMetadataPort: verifica existencia y estado del proyecto.
- EnvironmentMetadataPort: verifica el entorno cuando la política lo requiera.
- ResourceMetadataResolver: enruta por resource_type al resolver registrado.

Los adaptadores consultan la fuente canónica del dominio correspondiente. MemoryMetadataPort es autoridad para los metadatos de memoria; ProjectMetadataPort es autoridad para proyecto. El Registry del Broker no es fuente de metadatos de memoria ni se reutiliza como sustituto. El solicitante nunca aporta metadatos autoritativos. Los puertos devuelven metadatos mínimos, nunca contenido, fragmentos o embeddings. Si falta un resolver, hay duplicidad, inconsistencia, timeout o no se puede verificar el vínculo padre/hijo, CAM deniega. La enumeración puede obtener IDs candidatos, pero Gateway debe resolver y autorizar cada uno antes de exponer metadatos protegidos.

#### 9.3.3 Orden obligatorio de autorización

1. Validar identidad autenticada y estado.
2. Validar contexto y acción.
3. Resolver metadatos autoritativos del recurso y, cuando aplique, del padre y proyecto.
4. Comparar exactamente IDs, owner, scope, project y environment con contexto y Grant.
5. Aplicar la regla PRIVATE del propietario o el Grant explícito.
6. Aplicar no delegabilidad y verificar prueba directa cuando la acción sea approve/reject/forget.
7. Emitir ALLOW solo si todas las condiciones son verificables; en cualquier otro caso DENY.

La autorización precede a la lectura de contenido. No se usa el contenido para decidir si se autoriza su propia lectura.

#### 9.3.4 DM-P06 — Evidencia directa del propietario

Se define el puerto OwnerDecisionVerifier; no se selecciona proveedor de autenticación ni mecanismo criptográfico:

OwnerDecisionProof:
- proof_id opaco e issuer confiable.
- subject_user_id y actor_identity_id.
- action exacta: memory.approve, memory.reject o memory.forget.
- memory_id y, según la operación, proposal_id/version_id exactos.
- request_id, issued_at, expires_at, nonce y delegation=NONE.

OwnerDecisionVerifier.verify_and_consume valida y consume la prueba contra la acción, recursos, sujeto autenticado y request_id esperados.

Invariantes:
- La prueba procede de un emisor de autenticación confiable, independiente de Assistant, Memory Engine, Skills y servicios de dominio.
- El sujeto autenticado, actor USER y propietario canónico deben coincidir.
- La prueba vincula acción y recursos exactos; es de corta duración y de un solo uso.
- Repetición, expiración, discrepancia, emisor desconocido o verificador no disponible producen DENY.
- Gateway nunca crea ni firma la prueba. Un booleano, texto de chat, afirmación del Assistant, ausencia de delegación en OperationContext o Grant no son prueba válida.
- Si el flujo de autenticación futuro no puede producirla, approve/reject/forget permanecen deshabilitados; no se implementa bypass provisional.

#### 9.3.5 DM-P05 — Catálogo de clasificación

Catálogo cerrado y ordenado:

| Valor | Orden | Uso |
|---|---:|---|
| INTERNAL | 1 | Contexto no especialmente sensible. |
| CONFIDENTIAL | 2 | Información personal, privada o de negocio que no debe exponerse por defecto. |
| RESTRICTED | 3 | Información de impacto elevado que requiere controles adicionales definidos por política. |

La clasificación es metadato de sensibilidad, no permiso ni sustituto de scope/CAM. Una nueva memoria comienza en CONFIDENTIAL salvo elección explícita más restrictiva del propietario. Una nueva versión hereda la clasificación aprobada vigente. Elevar o reducir clasificación exige decisión directa del propietario vinculada a la propuesta/versión exacta. No hay downgrade automático por inferencia, resumen, importación o cambio de origen. RESTRICTED nunca amplía permisos; si exige controles no implementados, la operación correspondiente deniega. El catálogo no autoriza almacenar credenciales, secretos de autenticación ni datos prohibidos por otros contratos.

#### 9.3.6 DM-P07 — Identificadores

Los identificadores generados por Atlas para Memory, MemoryVersion, MemoryProposal y operaciones de supresión utilizan UUIDv7 en representación canónica lowercase con guiones. El tipo se conserva en el tipo/campo de dominio, no mediante prefijos usados para autorización. Los IDs externos (usuario, proyecto, entorno y fuentes) se conservan opacos según su autoridad; no se reescriben ni normalizan. Los IDs no incluyen nombre, correo, contenido, scope ni datos derivados del usuario. Nunca se reutilizan; colisión o formato inválido produce error, sin corrección silenciosa.

#### 9.3.7 DM-P08 — Transferencia y reclasificación de scope

Transferencia de propietario, conversión PRIVATE/PROJECT y movimiento entre proyectos no están soportados en v1. owner_id y scope son inmutables durante la vida de una memoria. Una petición de cambio se rechaza con error de dominio explícito. Una futura migración deberá ser un flujo separado: lectura autorizada del origen, propuesta de una memoria destino independiente, revisión directa del propietario, procedencia que enlace ambos IDs opacos y decisión explícita sobre el olvido del origen. La migración no copia Grants, aprobaciones ni historial de autorización; no puede ser automática, implícita ni delegada.

#### 9.3.8 DM-P10 — Retención de historial y procedencia

No hay TTL automático para versiones aprobadas ni superseded mientras la memoria lógica siga existiendo. Las versiones rechazadas se conservan como historial, pero no se incluyen en recuperación aprobada. Las referencias de procedencia conservan solo tipo, ID opaco, instante de captura, actor y disponibilidad; no se copia la fuente original por defecto. El olvido abarca todas las versiones, propuestas, referencias y destinos derivados del inventario. No se declara forgotten mientras exista un destino aplicable sin verificar. El plazo físico de retención de backups sigue siendo parámetro operativo obligatorio antes de implementar Forget; mientras un backup retenido contenga el contenido, el proceso no está completado y la supresión lógica bloquea su reintroducción. La evidencia mínima de supresión no conserva contenido, fragmentos ni hashes de contenido.

#### 9.3.9 DM-P09 — Atomicidad e idempotencia de propuestas

CREATE_MEMORY crea Memory con puntero vigente nulo, primera MemoryVersion pending_review (version_number=1) y MemoryProposal en una única transacción lógica. NEW_VERSION valida Memory y revisión esperada, asigna el siguiente version_number no reutilizado, crea MemoryVersion pending_review con parent_version_id de la versión aprobada vigente y crea MemoryProposal en una única transacción lógica. Se confirma todo o nada. La asignación de versión y parent usa revisión optimista/CAS o equivalente; ante conflicto se aborta y reintenta como nueva operación. Cada envío requiere idempotency_key opaca, única por actor y operación: misma clave y mismo payload canónico devuelve el mismo resultado; misma clave con payload distinto produce conflicto. No se deriva idempotencia de request_id sin contrato explícito. La tecnología transaccional queda fuera de alcance.

#### 9.3.10 DM-P11 — Procedencia tipada

SourceKind es un catálogo cerrado: USER_INPUT, CONVERSATION, FILE, CONNECTOR, TOOL_RESULT, SYSTEM_EVENT, DERIVED e IMPORT.

ProvenanceContext mínimo:
- origin declarado;
- actor_identity_id;
- request_id y correlation_id;
- project_id y environment_id cuando correspondan y hayan sido resueltos por autoridad confiable.

origin no autentica al actor. source_ref y evidence_refs son referencias opacas tipadas; nunca incluyen secretos, URLs con credenciales ni payloads completos. transformation conserva un resumen breve de transformaciones materiales, no razonamiento interno ni datos innecesarios. Una fuente desaparecida conserva su referencia con estado UNAVAILABLE. Toda lectura de evidencia vuelve a pasar por autorización del recurso referenciado.

#### 9.3.11 DM-P12 — Operaciones colectivas

Las operaciones colectivas por tipo permanecen deshabilitadas en v1. list_visible obtiene IDs candidatos bajo filtros de scope y autoriza cada memoria individualmente antes de devolver metadatos protegidos. No existe Grant wildcard, autorización masiva por tipo ni conteo de recursos no autorizados. La creación PROJECT se evalúa contra el ID exacto del proyecto contenedor conforme a §6.3.

## 10. Exclusiones

DM-01 no define:

- Base de datos, ORM, esquema SQL o migraciones.
- Motor de búsqueda, vector store, embeddings o Cognee.
- Persistencia, réplicas, cachés o estrategia de backup.
- Scheduler, RLM, Broker, Registry v2 o runtime.
- SecurityAudit (su implementación sigue postergada).
- API HTTP, transporte, interfaz de usuario o integración con Telegram.
- Adaptadores de clasificación o controles adicionales para RESTRICTED; el catálogo de dominio está definido en §9.3.5.
- Retención y purga física del proceso de olvido.

## 11. Secuencia posterior

1. Preparar QA-01 con pruebas positivas, negativas, aislamiento, idempotencia y concurrencia a partir de las decisiones cerradas.
2. Implementar ME-01: modelos y validaciones puras, sin adaptadores de infraestructura.
3. Implementar ME-02: MemoryGateway y CAM, únicamente después de que la autorización exacta por recurso esté probada.
4. Implementar Review usando el puerto de verificación de decisión directa del propietario; si no existe emisor confiable, denegar.
5. Implementar Forget solo después de definir el inventario real de destinos, la retención de backups y criterios verificables de purga.

## 12. Fuentes normativas

- `Contrato-de-diseno-Atlas-v1.md`: §§ 4.3–4.4, 5.4–5.7, 9 y 20.5.
- `docs/contracts/identity.md`: modelo y lifecycle de Identity.
- `docs/contracts/operation-context.md`: contexto como atribución/correlación, no autorización.
- `docs/contracts/memory.md`: §§ 3–13, especialmente scopes, recurso concreto, Gateway, autoridad del propietario y olvido.
- `docs/contracts/consistency-matrix-ct-08.md`: resoluciones R08-01 a R08-12 y criterios C08-AC.
- `docs/design/memory-engine-technical-contract.md`: modelo conceptual, Gateway, CAM, criterios MEM-01 a MEM-15 y decisiones consolidadas §13.

**Nota final:** DM-01 registra recomendaciones técnicas aprobadas por el propietario y decisiones de detalle todavía pendientes. La aprobación documental no significa que las capacidades estén implementadas, probadas o desplegadas.
