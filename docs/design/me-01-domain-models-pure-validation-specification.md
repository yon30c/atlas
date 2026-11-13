# ME-01 — Especificación de modelos de dominio y validaciones puras

**Estado:** especificación documental; pendiente de revisión y de implementación.  
**Base de diseño:** DM-01 y QA-01 en la rama `design/qa-01-memory-acceptance-tests`.  
**Rama de trabajo:** `design/me-01-domain-models-pure-validation`.  
**Alcance de esta fase:** definir los modelos inmutables de Memory Engine, sus tipos cerrados y las validaciones deterministas que no requieren almacenamiento, autorización ni efectos externos.  
**No implica:** código implementado, pruebas ejecutadas, persistencia, MemoryGateway, integración CAM, autenticación, Review, Forget ni infraestructura.

---

## 1. Objetivo

ME-01 convierte el modelo de dominio aprobado en DM-01 en un contrato implementable para:

1. Representar Memory, MemoryScope, MemoryVersion, MemoryProposal y MemoryProvenance.
2. Definir los catálogos cerrados de scope, estado, clasificación, intención de propuesta y procedencia.
3. Validar localmente cada objeto al construirse.
4. Validar relaciones entre objetos cuando se dispone de un conjunto explícito de modelos.
5. Hacer que los modelos sean inmutables también en sus estructuras anidadas.
6. Preparar pruebas unitarias de dominio trazables a QA-01.

ME-01 no decide si una operación está autorizada. Un objeto válido no implica que pueda leerse, crearse, aprobarse, rechazarse o eliminarse.

## 2. Autoridad y precedencia

Orden de autoridad:

1. Contrato principal Atlas v1.
2. CT-01 a CT-08.
3. DM-01, especialmente §§4, 5, 8 y 9.3.
4. QA-01, como especificación de escenarios.
5. ME-01, como contrato de implementación de modelos y validación pura.

Si aparece una discrepancia, se detiene la implementación de la regla afectada y se resuelve contra las fuentes superiores. ME-01 no puede alterar contratos normativos ni relajar una invariante para hacer pasar una prueba.

## 3. Hallazgos de partida

La inspección de la rama QA-01 encontró:

- `src/atlas/memory/models.py` contiene un `Memory` mínimo con `memory_id`, `owner_id`, `content`, `status` y `created_at`; no representa scope ni versiones.
- `MemoryProposal` solo contiene `owner_id`, `content` y `context`; exige igualdad entre owner y `context.user_id`, regla que no sustituye la autorización ni representa la propuesta aprobada en DM-01.
- `src/atlas/core/enums.py` define `MemoryStatus` con `proposed`, `active`, `archived` y `rejected`, incompatible con el conjunto cerrado de estados de MemoryVersion.
- No se encontró en el módulo de memoria un modelo tipado para MemoryScope, MemoryVersion, MemoryProvenance, SourceKind o referencias opacas.
- El repositorio exige Python >=3.10 y no declara dependencias de runtime.

Estos hallazgos son una lectura estática del código de la rama; no representan una ejecución de pruebas ni una evaluación de comportamiento en runtime.

## 4. Alcance exacto

### 4.1 Incluido

- Enumeraciones y tipos de valor del dominio de memoria.
- Modelos inmutables con validación local.
- Validación UUIDv7 de IDs generados por Atlas.
- Validación UTC de instantes.
- Validación de contenido y campos obligatorios.
- Validación de invariantes de MemoryScope.
- Validación de coherencia Memory–MemoryVersion.
- Validación de relaciones MemoryVersion padre/hijo.
- Validación de vínculos MemoryProposal–Memory–MemoryVersion.
- Validación pura de las transiciones permitidas de MemoryVersion.
- Pruebas unitarias puras, sin I/O ni dependencias externas.

### 4.2 Excluido

- MemoryGateway y puertos de aplicación.
- CAM, AuthorizationEvaluator, Grants, ResourceIdentity y resolución de metadatos.
- OwnerDecisionProof, emisión/verificación de pruebas y autenticación.
- Persistencia, repositorios, transacciones, CAS, idempotency store y adaptadores.
- Indexación, embeddings, búsqueda semántica, Cognee y almacenamiento vectorial.
- Review real, aprobación/rechazo por propietario y publicación de versiones.
- Forget, tombstones, purga, backup y reconciliación.
- Assistant, Watchers, Analysis Engine, Proactivity y Skills.
- Eventos, SecurityAudit, despliegue o cambios de Broker/Registry v2.

## 5. Contrato de tipos

Todos los modelos de dominio definidos en ME-01 serán `dataclass(frozen=True, slots=True)` o tipos equivalentes estrictamente inmutables compatibles con Python >=3.10.

Los modelos no contendrán `dict`, `list`, conjuntos mutables, objetos de infraestructura, conexiones, callbacks ni referencias a servicios. Las colecciones se representarán como `tuple` o `frozenset` cuando corresponda. No se aceptará una colección mutable para convertirla silenciosamente durante la construcción: se rechazará para evitar que el llamador conserve un alias mutable.

### 5.1 Catálogos cerrados

| Tipo | Valores exactos |
|---|---|
| `MemoryScopeKind` | `PRIVATE`, `PROJECT` |
| `MemoryVersionStatus` | `pending_review`, `approved`, `rejected`, `superseded`, `forgotten` |
| `MemoryClassification` | `INTERNAL`, `CONFIDENTIAL`, `RESTRICTED` |
| `MemoryProposalIntent` | `CREATE_MEMORY`, `NEW_VERSION` |
| `SourceKind` | `USER_INPUT`, `CONVERSATION`, `FILE`, `CONNECTOR`, `TOOL_RESULT`, `SYSTEM_EVENT`, `DERIVED`, `IMPORT` |
| `ReferenceAvailability` | `AVAILABLE`, `UNAVAILABLE` |

No se permiten alias, valores desconocidos ni estados heredados `proposed`, `active` o `archived` en el nuevo modelo de versiones.

### 5.2 Identificadores

- Los IDs generados por Atlas para Memory, MemoryVersion y MemoryProposal son UUIDv7 canónicos lowercase con guiones.
- El tipo se expresa mediante el campo/tipo del modelo, nunca mediante prefijos usados como autorización.
- Se rechazan UUID inválidos, UUID de otra versión, representación no canónica, uppercase o valores que no sean UUIDv7.
- Los IDs externos de usuario, identidad, proyecto, entorno, origen y evidencia son opacos: se exige valor no vacío donde el campo sea obligatorio, pero no se impone UUID ni se normaliza el texto.
- No se generan IDs dentro de constructores de modelos. La generación pertenece a una futura frontera de aplicación/ID generator y debe ser inyectable y comprobable.
- Python >=3.10 no garantiza un generador UUIDv7 en la biblioteca estándar. ME-01 solo define validación; no incorpora una dependencia ni improvisa un algoritmo generador.

### 5.3 Instantes

Todo campo temporal del dominio debe ser un `datetime` con zona horaria explícita y offset UTC igual a cero.

- Se rechazan valores naive y offsets distintos de UTC.
- No se convierten silenciosamente zonas horarias.
- No se sustituyen fechas ausentes por `now()`.
- Las funciones de validación reciben valores explícitos; no consultan reloj del sistema.

## 6. Modelos normativos

Los campos siguientes son el contrato de dominio. Los nombres pueden mapearse a aliases tipados, pero no se puede omitir ni reinterpretar su semántica.

### 6.1 MemoryScope

| Campo | Tipo | Regla |
|---|---|---|
| `kind` | `MemoryScopeKind` | Obligatorio y cerrado. |
| `project_id` | `ProjectId | None` | Null para PRIVATE; obligatorio para PROJECT. |

Invariantes:

1. PRIVATE exige `project_id is None`.
2. PROJECT exige `project_id` como cadena no vacía.
3. No se infiere el proyecto desde OperationContext, actor, conversación, origen o provenance.
4. No se normaliza el ID externo.
5. La existencia/estado del proyecto no se valida aquí: corresponde a ProjectMetadataPort en una fase posterior.
6. MemoryScope no contiene owner_id.

### 6.2 Memory

| Campo | Tipo | Regla |
|---|---|---|
| `memory_id` | `MemoryId` | UUIDv7 canónico. |
| `owner_id` | `UserId` | ID externo opaco, obligatorio. |
| `scope` | `MemoryScope` | Obligatorio. |
| `current_approved_version_id` | `MemoryVersionId | None` | Nulo mientras no exista versión aprobada. |
| `created_at` | `Instant` | UTC. |
| `updated_at` | `Instant` | UTC y no anterior a created_at. |

Invariantes:

- owner_id tiene una única representación canónica.
- memory_id no se reutiliza.
- scope e identidad lógica no se modifican mediante actualización ordinaria.
- El puntero vigente, si existe, debe apuntar a una MemoryVersion de esta misma memoria con estado approved. La verificación requiere el conjunto de versiones y por ello se realiza mediante validador agregado, no solo en `__post_init__`.

### 6.3 MemoryVersion

| Campo | Tipo | Regla |
|---|---|---|
| `version_id` | `MemoryVersionId` | UUIDv7 canónico. |
| `memory_id` | `MemoryId` | UUIDv7 de la memoria propietaria. |
| `version_number` | entero positivo | Bool no cuenta como entero válido; número único y no reutilizable dentro del historial. |
| `content` | `str` | Obligatorio, no vacío ni whitespace-only; se preserva exactamente, sin trim ni normalización. |
| `classification` | `MemoryClassification` | Obligatoria y cerrada. |
| `status` | `MemoryVersionStatus` | Obligatorio y cerrado. |
| `provenance` | `MemoryProvenance` | Obligatoria e inmutable. |
| `parent_version_id` | `MemoryVersionId | None` | Nulo para la primera versión; relación verificada a nivel agregado. |
| `created_at` | `Instant` | UTC. |
| `submitted_at` | `Instant` | UTC y no anterior a created_at. |
| `reviewed_at` | `Instant | None` | Coherente con estado de revisión. |
| `reviewed_by` | `UserId | None` | ID externo opaco; coherente con reviewed_at. |

Reglas locales:

- version_number debe ser entero, mayor o igual a 1; `True` y `False` se rechazan.
- content se valida sin modificar el texto original.
- classification y provenance no pueden mutar después de la construcción.
- reviewed_at y reviewed_by son ambos nulos para pending_review.
- Para approved, rejected, superseded y forgotten se conserva la evidencia de revisión de la decisión aprobatoria/rechazadora que corresponda; reviewed_at y reviewed_by deben estar presentes. La transición a superseded o forgotten no borra la revisión anterior.
- La coherencia de estado, historial, padre e identidad de memoria requiere validación agregada.

### 6.4 MemoryProposal

| Campo | Tipo | Regla |
|---|---|---|
| `proposal_id` | `ProposalId` | UUIDv7 canónico. |
| `intent` | `MemoryProposalIntent` | CREATE_MEMORY o NEW_VERSION. |
| `memory_id` | `MemoryId` | UUIDv7. |
| `version_id` | `MemoryVersionId` | UUIDv7. |
| `submitted_by` | `IdentityId` | ID externo opaco de la identidad que envía. |
| `submitted_at` | `Instant` | UTC. |

Reglas:

- La propuesta no duplica content, classification, owner ni scope; esos datos viven en Memory y MemoryVersion.
- CREATE_MEMORY identifica Memory nueva, primera versión pending_review y puntero vigente nulo.
- NEW_VERSION identifica Memory existente y versión pending_review cuyo padre es la versión aprobada vigente al momento de la propuesta.
- La igualdad de owner_id con context.user_id no es una regla de validez de la propuesta. El actor que envía no se convierte por ello en propietario ni queda autorizado.
- El vínculo exacto entre propuesta, memoria y versión se valida mediante una función pura de relación.

### 6.5 ProvenanceContext

| Campo | Tipo | Regla |
|---|---|---|
| `origin` | cadena no vacía | Origen declarado; no autentica actor. |
| `actor_identity_id` | `IdentityId` | Identidad declarada en el contexto; debe provenir del contexto confiable de la operación al construir el objeto. |
| `request_id` | cadena no vacía | Correlación de la operación. |
| `correlation_id` | cadena no vacía | Correlación transversal. |
| `project_id` | `ProjectId | None` | Solo cuando corresponda y haya sido resuelto por autoridad confiable. |
| `environment_id` | `EnvironmentId | None` | Solo cuando corresponda y haya sido resuelto por autoridad confiable. |

El modelo puede validar forma y presencia; no puede demostrar que un ID fue resuelto por una autoridad confiable. Esa garantía pertenece a los puertos y servicios de aplicación posteriores.

### 6.6 OpaqueReference

| Campo | Tipo | Regla |
|---|---|---|
| `resource_type` | cadena no vacía | Tipo opaco tipado. |
| `resource_id` | cadena no vacía | ID opaco; sin URL ni credenciales. |
| `availability` | `ReferenceAvailability` | AVAILABLE o UNAVAILABLE. |

La referencia no contiene payload, fragmentos, credenciales, URLs con credenciales ni permisos. Resolverla o leer el recurso referido siempre exige autorización independiente.

### 6.7 MemoryProvenance

| Campo | Tipo | Regla |
|---|---|---|
| `source_kind` | `SourceKind` | Catálogo cerrado. |
| `source_ref` | `OpaqueReference | None` | Referencia opcional según origen. |
| `captured_at` | `Instant` | UTC. |
| `captured_by` | `IdentityId` | Identidad opaca obligatoria. |
| `origin_context` | `ProvenanceContext` | Obligatorio. |
| `transformation` | `str | None` | Resumen breve de transformaciones materiales, nunca razonamiento interno. |
| `evidence_refs` | `tuple[OpaqueReference, ...]` | Tupla inmutable; vacía si no hay evidencia. |

Reglas:

- Provenance es obligatoria por versión e inmutable.
- No se copian fuentes ni payloads completos por defecto.
- Una fuente desaparecida mantiene la referencia con availability UNAVAILABLE.
- Una referencia no concede acceso.
- No se guardan secretos, tokens, credenciales ni URLs con credenciales.
- origin es una declaración de procedencia, no prueba de identidad.
- captured_by identifica quién capturó la fuente; el flujo de aplicación debe vincularlo con identidad autenticada. La dataclass no constituye autenticación.

## 7. Validaciones puras requeridas

Las validaciones serán funciones deterministas sin I/O, sin acceso a reloj, sin lectura de configuración y sin invocar servicios. Reciben todos los valores que necesitan y lanzan ContractError (o el error de dominio definido por CT-03) ante una violación.

### 7.1 Validación local de objetos

Cada modelo debe validar en construcción:

- tipos exactos de campos y enums;
- campos obligatorios no vacíos;
- UUIDv7 canónico donde el ID sea generado por Atlas;
- timestamps UTC;
- consistencia de fechas de revisión;
- invariantes PRIVATE/PROJECT;
- colecciones profundamente inmutables;
- contenido y resúmenes sin valores vacíos;
- ausencia de estructuras arbitrarias/mutables.

### 7.2 validate_memory_aggregate(memory, versions)

Valida un snapshot completo suministrado por el llamador:

1. Todos los elementos son MemoryVersion.
2. Cada version.memory_id coincide exactamente con memory.memory_id.
3. version_id no se repite.
4. version_number no se repite y todos son positivos.
5. La secuencia de números del historial no tiene reutilización; el validador no inventa ni renumera versiones.
6. Una versión con parent_version_id debe referir a una versión existente de la misma Memory.
7. El padre tiene version_number menor que el hijo; no hay ciclos.
8. La primera versión es version_number=1 y no tiene padre.
9. Las versiones posteriores tienen parent_version_id explícito.
10. Si current_approved_version_id es null, no existe versión approved en el snapshot.
11. Si current_approved_version_id no es null, existe exactamente una versión approved y coincide con ese ID.
12. Una versión de otra Memory nunca puede ser el padre ni el puntero vigente.

El validador no consulta almacenamiento ni verifica unicidad global histórica fuera del snapshot; esa garantía requerirá persistencia/transacción en una fase posterior.

### 7.3 validate_proposal_links(memory, version, proposal)

Valida:

- proposal.memory_id == memory.memory_id;
- proposal.version_id == version.version_id;
- version.memory_id == memory.memory_id;
- proposal.submitted_at == version.submitted_at;
- la versión está pending_review al momento de envío;
- CREATE_MEMORY: memory.current_approved_version_id es null, version_number=1 y parent_version_id es null;
- NEW_VERSION: Memory ya tiene versión aprobada vigente; version.parent_version_id coincide exactamente con esa versión vigente y version_number es superior a todos los números existentes.

Esta función valida consistencia de los objetos suministrados. No persiste nada ni demuestra que la operación haya sido atómica.

### 7.4 validate_version_transition(current, target)

Acepta exclusivamente estas aristas:

- pending_review → approved
- pending_review → rejected
- approved → superseded
- approved → forgotten

Rechaza transición al mismo estado, reactivación, transición desde rejected/superseded/forgotten y cualquier estado no catalogado.

Esta función valida únicamente la forma de la transición. No autoriza la decisión, no verifica OwnerDecisionProof y no acredita que Forget haya purgado todos los destinos. Esas condiciones se comprobarán en las fases Review y Forget.

### 7.5 Clasificación entre versiones

ME-01 valida que cada versión tenga una clasificación válida e inmutable. No autoriza cambios de clasificación entre versiones.

DM-01 exige decisión directa del propietario para elevar o reducir clasificación. La verificación de esa decisión corresponde a OwnerDecisionVerifier y al flujo Review posterior. No se implementará un parámetro booleano como `owner_approved=True` ni se aceptará texto de chat como prueba.

## 8. Errores y semántica

- Valores mal tipados, vacíos, enum desconocido, UUID inválido, fecha inválida o estructura mutable: ContractError.
- Relación entre objetos inconsistente o transición no permitida: ContractError o error de dominio específico de CT-03, manteniendo semántica consistente.
- No usar AuthorizationError para errores de forma o de modelo.
- No revelar contenido protegido en mensajes de excepción.
- Los errores no mutan objetos ni intentan reparar valores.

La implementación deberá revisar mensajes existentes y mantener compatibilidad con CT-03. ME-01 no introduce una jerarquía paralela de errores.

## 9. Organización propuesta del código

La organización recomendada, sujeta a la revisión de imports antes de implementar, es:

| Ubicación | Responsabilidad |
|---|---|
| `src/atlas/memory/models.py` | Modelos inmutables y tipos de memoria definidos en ME-01. |
| `src/atlas/memory/validation.py` | Validadores puros entre objetos, historial y transiciones. |
| `src/atlas/memory/identifiers.py` | Validación sintáctica UUIDv7 para IDs de memoria, sin generación ni I/O. |
| `tests/unit/test_memory_models.py` | Validación local y contratos de inmutabilidad. |
| `tests/unit/test_memory_validation.py` | Agregados, relaciones, estados y propuestas. |

Los tipos compartidos de identidad/contexto y errores seguirán en sus módulos existentes. No se moverán módulos compartidos ni se harán refactors ajenos a ME-01.

### Compatibilidad del modelo anterior

El `MemoryStatus` actual no se puede reutilizar como ciclo de vida de MemoryVersion. Antes de retirarlo o cambiar imports, la implementación debe inventariar todos sus usos en `src/` y `tests/`.

La migración debe ser explícita: no convertir silenciosamente `proposed` en `pending_review`, `active` en `approved` o `archived` en `superseded` sin revisar el significado de cada uso. No se conservarán estados legacy en el nuevo catálogo para evitar compatibilidad que contradiga CT-05.

## 10. Plan de pruebas unitarias asociado

Estas pruebas son requisitos de implementación; todavía no están escritas ni ejecutadas.

| Grupo | Cobertura mínima |
|---|---|
| ME01-T01 Scope | PRIVATE válido; PROJECT válido; PRIVATE con proyecto; PROJECT sin proyecto; tipo desconocido; ID externo preservado. |
| ME01-T02 IDs | UUIDv7 canónico válido; UUIDv4; uppercase; formato no canónico; cadena vacía; ID externo no UUID válido. |
| ME01-T03 Timestamps | UTC válido; naive; offset no UTC; tipos incorrectos; updated_at anterior a created_at. |
| ME01-T04 Memory | Campos requeridos; owner único; scope requerido; puntero null; modelo frozen. |
| ME01-T05 Version | número positivo; bool rechazado; content vacío/whitespace; enum inválido; provenance obligatoria; revisión coherente. |
| ME01-T06 Inmutabilidad | mutación de campos; mutación de estructuras anidadas; listas/dicts rechazados; tuplas inmutables. |
| ME01-T07 Provenance | SourceKind completo; kind inválido; referencias opacas; UNAVAILABLE; URL con credenciales/payload rechazado; transformación opcional. |
| ME01-T08 Agregado | mismo memory_id; ID duplicado; número duplicado; padre ausente/cruzado; ciclo; padre con número no menor; puntero vigente válido/inválido; cero o una versión approved coherente. |
| ME01-T09 Propuesta | CREATE_MEMORY correcto/incorrecto; NEW_VERSION correcto/incorrecto; IDs cruzados; versión no pendiente; submitted_at discordante. |
| ME01-T10 Transiciones | cuatro transiciones permitidas; todas las transiciones prohibidas; estados terminales; mismo estado. |
| ME01-T11 Clasificación | catálogo cerrado; cada versión inmutable; ninguna función de ME-01 concede autorización para cambiarla. |
| ME01-T12 Regresión | imports de identidad/contexto/errores; compatibilidad no accidental con MemoryStatus legacy; no modificar módulos fuera de alcance. |

### Criterio de calidad

- Pruebas deterministas, sin red, DB, filesystem, reloj global ni servicios externos.
- Casos positivos y negativos para cada invariante local.
- Pruebas de agregados con fixtures de IDs UUIDv7 válidos.
- Las pruebas no usan nombres alias como `memory-A` en campos que requieren UUIDv7; los alias de QA-01 son etiquetas de lectura, no IDs válidos de producción.
- No se debilitan tests para acomodar el comportamiento legacy.
- La suite completa debe ejecutarse y reportarse por separado de la inspección estática.

## 11. Trazabilidad a QA-01

| ME-01 | Escenarios QA-01 |
|---|---|
| MemoryScope y Memory | QA-DOM-01 a QA-DOM-07 |
| UUIDv7 e IDs externos | QA-DOM-08 a QA-DOM-10 |
| MemoryVersion y estados | QA-VER-01 a QA-VER-10, QA-VER-13, QA-VER-17 |
| Inmutabilidad y clasificación local | QA-VER-05, QA-VER-06, QA-VER-14 a QA-VER-16, QA-PROV-08 a QA-PROV-10 |
| Propuestas y vínculos | QA-PROP-01 a QA-PROP-06 |
| Atomicidad/idempotencia | QA-PROP-05 a QA-PROP-12; los mecanismos reales quedan fuera de ME-01 |
| Provenance y referencias | QA-PROV-01 a QA-PROV-07 |
| Relaciones padre/hijo y puntero vigente | QA-VER-01 a QA-VER-04, QA-CAM-06 a QA-CAM-08 |
| Transiciones | QA-VER-08, QA-VER-09, QA-VER-17 |

ME-01 cubre solo las aserciones que pueden resolverse con datos de dominio puros. Los escenarios de CAM, Gateway, autenticación, atomicidad real y Forget siguen asignados a fases posteriores.

## 12. Criterios de salida de ME-01

ME-01 estará listo para autorizar implementación de código cuando:

1. Los campos y tipos de los seis modelos estén aceptados y no contradigan DM-01.
2. Los catálogos cerrados estén definidos sin estados legacy.
3. Las reglas de UUIDv7 distingan IDs Atlas de IDs externos.
4. Las reglas de UTC y contenido estén explícitas.
5. Las validaciones agregadas no pretendan demostrar persistencia, autorización o atomicidad.
6. La semántica de clasificación no incluya bypass mediante booleanos.
7. Los casos de QA-01 aplicables tengan mapeo a pruebas unitarias.
8. Se haya inventariado el uso actual de MemoryStatus antes de migrar imports.
9. La implementación propuesta no requiera nuevas dependencias ni cambios de infraestructura.
10. El usuario haya revisado el documento y autorizado el inicio de código.

El cierre documental de ME-01 no significa que modelos, validadores o pruebas existan en el repositorio.

## 13. Fases posteriores a ME-01 — plan preliminar

El orden propuesto para la implementación posterior es:

1. **ME-02 — MemoryGateway + CAM:** integración de frontera única, puertos tipados de metadatos, autorización exacta por memoria/versión, aislamiento PRIVATE/PROJECT y fail-closed. No comenzar hasta que ME-01 esté implementado y sus pruebas pasen.
2. **ME-03 — Review y publicación:** propuestas, OwnerDecisionVerifier, prueba directa del propietario, aprobación/rechazo, sustitución atómica de versiones e idempotencia. Si no existe emisor confiable, approve/reject permanecen deshabilitados.
3. **ME-04 — Forget y supresión:** diseñar e implementar solo tras aprobar inventario de destinos, backups, retención física, plazos y verificación de purga. Supresión lógica inmediata y prevención de reaparición son obligatorias.
4. **ME-05 — Persistencia y adaptadores:** seleccionar almacenamiento y adaptadores solo cuando los contratos anteriores estén probados y exista decisión explícita de arquitectura. Implementar transacciones/CAS y pruebas de integración sin usar Broker Registry como autoridad de memoria.
5. **ME-06 — Assistant mínimo:** recuperación exclusivamente por Gateway, presentación de memoria aprobada y envío de propuestas; sin aprobar, rechazar, olvidar ni conceder permisos.
6. **ME-07 — Proactivity:** Watchers de solo lectura, Analysis Engine y propuestas a Assistant; sin mutación de recursos ni autoridad adicional.
7. **ME-08 — Hardening y aceptación integral:** pruebas de seguridad, regresión contractual, concurrencia, filtraciones, recuperación y revisión de amenazas. SecurityAudit solo se incorporará cuando su alcance se apruebe expresamente.

La selección de almacenamiento y adaptadores puede requerirse antes de ME-04/ME-05 según la secuencia de implementación acordada, pero no se anticipa en ME-01. La numeración y el orden final de esas fases se confirmarán antes de cada implementación.

## 14. Registro de cambios

| Versión | Cambio | Estado |
|---|---|---|
| 0.1 | Primera especificación ME-01: modelos, catálogos, validación local/agregada, pruebas requeridas y secuencia posterior. | Borrador documental |

---

**ME-01 define el contrato que deberá implementar el código. No afirma que el código o sus pruebas hayan sido creados, ejecutados o superados.**
