# QA-01 — Especificación de pruebas de aceptación de Memory Engine

**Estado:** especificación documental; pendiente de implementación y ejecución.  
**Rama base:** `design/dm-01-domain-model-specification`  
**Alcance:** aceptación funcional, de dominio y seguridad de Memory Engine / Memory Gateway, con pruebas de frontera para CAM, Atlas Assistant, Proactivity y contratos transversales.  
**Autoridad:** contrato principal de Atlas v1 y CT-01 a CT-08. DM-01 concreta las decisiones técnicas de dominio sin sustituir los contratos normativos.  
**No implica:** implementación, certificación de runtime, selección de infraestructura ni autorización para modificar Broker, Registry v2, producción o sistemas protegidos.

---

## 1. Propósito

QA-01 convierte los invariantes DM-01-01 a DM-01-20, las decisiones DM-P01 a DM-P12 y los criterios de aceptación de CT-01 a CT-08 en escenarios verificables.

La especificación debe servir como baseline para:

1. Construir pruebas unitarias de modelos y validaciones puras.
2. Construir pruebas de servicio para Memory Engine y Memory Gateway.
3. Verificar la integración de Gateway con CAM y las autoridades de metadatos.
4. Verificar límites de autoridad entre memoria, Assistant y Proactivity.
5. Identificar pruebas bloqueadas por decisiones operativas que todavía no se han aprobado.

Una prueba solo se considera superada cuando el resultado observable coincide con el criterio indicado y no existe una ruta alternativa que exponga datos, mutile recursos o conceda permisos.

## 2. Autoridad, precedencia y vocabulario

### 2.1 Fuentes normativas

Orden de precedencia:

1. Contrato principal de Atlas v1.
2. Contratos CT-01 a CT-08 y sus resoluciones armonizadas.
3. DM-01, como especificación técnica de dominio compatible con los anteriores.
4. QA-01, como traducción de esas reglas a escenarios de aceptación.

Si QA-01 parece contradecir una fuente de mayor autoridad, la prueba debe detenerse y registrarse como discrepancia documental; QA-01 no puede modificar la regla normativa.

### 2.2 Resultado de los escenarios

- **PASS:** se observa el resultado exigido y no se observa efecto prohibido.
- **FAIL:** se incumple el resultado exigido, se filtra información o se produce un efecto prohibido.
- **BLOCKED:** no puede evaluarse sin un parámetro o mecanismo pendiente expresamente identificado.
- **NOT RUN:** el escenario está especificado, pero no existe evidencia de ejecución.

No se permite convertir BLOCKED o NOT RUN en PASS por inferencia, revisión estática o aprobación documental.

### 2.3 Tipos de pruebas

- **Dominio:** construcción, invariantes, estados y transiciones.
- **Autorización:** identidad, CAM, Grants, scope, metadatos y no delegabilidad.
- **Integración:** frontera Gateway, puertos tipados y componentes consumidores.
- **Atomicidad/concurrencia:** todo-o-nada, idempotencia y conflictos.
- **Seguridad negativa:** denegación, ausencia de filtraciones y comportamiento fail-closed.
- **Regresión contractual:** compatibilidad con CT-01 a CT-08.

## 3. Límites y dependencias

### 3.1 Incluido

- Modelo Memory, MemoryScope, MemoryVersion, MemoryProposal y MemoryProvenance.
- Ciclo de vida y versionado.
- Clasificación por versión.
- PRIVATE y PROJECT.
- Autorización CAM por recurso exacto.
- Grants con IDs explícitos.
- Vinculación MemoryVersion–Memory.
- Fuentes confiables de metadatos.
- OwnerDecisionProof y OwnerDecisionVerifier como contrato.
- Atomicidad e idempotencia de propuestas.
- MemoryGateway como frontera obligatoria.
- Supresión lógica y garantías de no reaparición que ya están definidas.
- Límites de autoridad de Assistant, Watchers, Analysis Engine, Proactivity y Skills.
- Semántica de errores y trazabilidad de eventos en lo aplicable.

### 3.2 Fuera de alcance

- Implementación de código o cambios en los tests existentes.
- Selección de base de datos, vector store, embeddings, Cognee o adaptadores concretos.
- Proveedor de autenticación, firma criptográfica o emisor real de OwnerDecisionProof.
- Retención física de backups, inventario definitivo de destinos, plazos de propagación y criterios operativos de purga.
- Controles técnicos completos de RESTRICTED todavía no definidos.
- SecurityAudit, despliegue, Telegram, Scheduler y RLM como implementaciones.
- Modificaciones de Atlas Broker, Registry v2, producción o infraestructura protegida.

### 3.3 Dependencias que bloquean pruebas positivas

1. **OwnerDecisionProof:** las pruebas del contrato del verificador pueden usar un emisor/verificador de prueba controlado. La aceptación de integración real de approve/reject/forget permanece bloqueada hasta que exista un emisor confiable aprobado. Sin él, esas acciones deben permanecer deshabilitadas y fallar cerradas.
2. **Forget físico:** se pueden probar supresión lógica, bloqueo de recuperación y manejo de fallos. No se puede aprobar el olvido completo ni el estado final `forgotten` hasta definir el inventario de destinos, la retención de backups y los criterios verificables de purga.
3. **RESTRICTED:** se puede verificar que la clasificación no amplía permisos y que la falta de controles requeridos deniega. La aceptación positiva de operaciones que requieran controles adicionales queda bloqueada hasta definirlos.
4. **Adaptadores:** las pruebas de contrato de puertos pueden usar dobles deterministas. La integración con adaptadores reales no forma parte de QA-01.

## 4. Convenciones de datos de prueba

Los datos siguientes son fixtures abstractos; no representan usuarios, proyectos ni recursos reales.

### 4.1 Identidades

- `owner-A`: identidad USER activa, propietaria de `memory-A`.
- `user-B`: identidad USER activa, distinta del propietario.
- `agent-A`: identidad de agente que actúa bajo el contexto permitido, sin autoridad propia de propietario.
- `watcher-A`: identidad de Watcher de solo lectura.
- `skill-A`: identidad de Skill no confiable por defecto.
- `owner-suspended`: identidad suspendida.
- `owner-revoked`: identidad revocada.

### 4.2 Recursos y ámbitos

- `project-A` y `project-B`: proyectos distintos, existentes y activos en los escenarios que así lo indiquen.
- `memory-A`: PRIVATE, owner `owner-A`.
- `memory-B`: PROJECT, owner `owner-A`, project `project-A`.
- `memory-C`: PROJECT, owner `owner-A`, project `project-B`.
- `memory-D`: PRIVATE, owner `user-B`.
- `version-A1`: versión aprobada vigente de `memory-A`.
- `version-A2`: versión pendiente de `memory-A`, cuyo padre es `version-A1`.
- `version-X1`: versión perteneciente a otra memoria, no a `memory-A`.

Los identificadores de Atlas generados durante pruebas deben respetar UUIDv7 canónico lowercase con guiones. Los nombres anteriores son alias legibles de fixtures, no valores válidos de producción.

### 4.3 Grants

- `grant-A`: Grant válido con recurso explícito `memory-A`, acciones y contexto compatibles.
- `grant-project-A`: Grant válido para el ID exacto `project-A` y la acción de propuesta PROJECT.
- `grant-expired`: Grant expirado.
- `grant-revoked`: Grant revocado.
- `grant-type-only`: Grant sin IDs concretos, únicamente con tipo de recurso.
- `grant-other-memory`: Grant para `memory-B`, no para `memory-A`.

No se utilizarán comodines, IDs inferidos ni permisos implícitos en los fixtures.

### 4.4 Control de contenido y filtraciones

Cada recurso protegido tendrá un marcador de contenido único y sintético. Los tests negativos comprobarán no solo el tipo de error, sino también que el marcador, fragmentos, embeddings, metadatos protegidos y conteos no autorizados no aparecen en respuesta, excepción, log expuesto o resultado de búsqueda.

## 5. Matriz de trazabilidad de invariantes DM-01

| Invariante | Escenarios QA-01 principales |
|---|---|
| DM-01-01 — propietario canónico y scope explícito | QA-DOM-01, QA-DOM-02 |
| DM-01-02 — PRIVATE sin project_id; PROJECT con project_id | QA-DOM-03, QA-DOM-04 |
| DM-01-03 — owner_id no duplicado en MemoryScope | QA-DOM-05 |
| DM-01-04 — versión pertenece a una Memory | QA-VER-01, QA-VER-02 |
| DM-01-05 — versión vigente pertenece a Memory y está approved | QA-VER-03, QA-VER-04 |
| DM-01-06 — contenido, clasificación y procedencia inmutables | QA-VER-05, QA-VER-06 |
| DM-01-07 — estados/transiciones cerrados | QA-VER-07 a QA-VER-10 |
| DM-01-08 — intención CREATE_MEMORY o NEW_VERSION | QA-PROP-01, QA-PROP-02 |
| DM-01-09 — pendiente no es conocimiento aprobado | QA-PROP-03, QA-PROP-04 |
| DM-01-10 — provenance no concede acceso | QA-PROV-01, QA-PROV-02 |
| DM-01-11 — recurso concreto exige resource_id exacto | QA-CAM-01, QA-CAM-02 |
| DM-01-12 — Grant por tipo sin IDs no autoriza instancia | QA-CAM-03 |
| DM-01-13 — Grant solo autoriza IDs enumerados | QA-CAM-04, QA-CAM-05 |
| DM-01-14 — metadatos autoritativos no proceden del solicitante | QA-META-01 a QA-META-04 |
| DM-01-15 — PROJECT exige coincidencia explícita | QA-AUTH-04 a QA-AUTH-07 |
| DM-01-16 — PRIVATE del propietario no omite Gateway/CAM | QA-AUTH-01 a QA-AUTH-03 |
| DM-01-17 — approve/reject/forget directos y no delegables | QA-OWNER-01 a QA-OWNER-08 |
| DM-01-18 — versión vinculada a Memory padre | QA-VER-01, QA-CAM-06 a QA-CAM-08 |
| DM-01-19 — fallos e incertidumbre deniegan | QA-FAIL-01 a QA-FAIL-07 |
| DM-01-20 — sin fallback por tipo ni consulta sin scope | QA-CAM-03, QA-LIST-01 a QA-LIST-04 |

## 6. Escenarios de aceptación

### 6.1 Modelo y construcción de dominio

| ID | Escenario | Resultado exigido |
|---|---|---|
| QA-DOM-01 | Construir Memory con owner canónico y scope válido | La construcción se acepta y conserva exactamente ambos valores. |
| QA-DOM-02 | Construir Memory sin owner o sin scope | Se rechaza como incumplimiento contractual; no se crea recurso parcial. |
| QA-DOM-03 | Construir scope PRIVATE con project_id nulo | Se acepta. |
| QA-DOM-04 | Construir scope PROJECT sin project_id, vacío o inválido | Se rechaza; no se infiere proyecto desde contexto, actor u origen. |
| QA-DOM-05 | Intentar incluir owner_id dentro de MemoryScope | El modelo no duplica el propietario; la forma incompatible se rechaza. |
| QA-DOM-06 | Usar un scope desconocido o una combinación PRIVATE/project_id | Se rechaza sin normalización ni corrección silenciosa. |
| QA-DOM-07 | Transferir owner_id o cambiar PRIVATE a PROJECT mediante actualización ordinaria | La operación se rechaza con error de dominio explícito. |
| QA-DOM-08 | Generar IDs de Memory, MemoryVersion, MemoryProposal o supresión | Cada ID generado por Atlas cumple UUIDv7 canónico lowercase con guiones, es único y no contiene datos personales ni contenido. |
| QA-DOM-09 | Proporcionar ID externo de usuario/proyecto/fuente | Se conserva opaco, sin reescritura ni normalización silenciosa. |
| QA-DOM-10 | Provocar colisión o ID generado inválido | La operación falla; no se corrige, reutiliza ni sustituye silenciosamente el ID. |

### 6.2 Versiones y ciclo de vida

| ID | Escenario | Resultado exigido |
|---|---|---|
| QA-VER-01 | Crear MemoryVersion con memory_id existente | La versión queda vinculada a esa Memory. |
| QA-VER-02 | Crear versión con parent_version_id de otra Memory | Se rechaza; no se acepta una relación padre/hijo cruzada. |
| QA-VER-03 | Establecer current_approved_version_id a una versión de otra Memory | Se rechaza. |
| QA-VER-04 | Establecer puntero vigente a versión pending_review, rejected, superseded o forgotten | Se rechaza; el puntero solo puede referir a versión de esa Memory en approved. |
| QA-VER-05 | Modificar content, classification o provenance de una versión existente | La mutación se rechaza; una corrección requiere nueva versión. |
| QA-VER-06 | Crear versión con clasificación ausente o fuera del catálogo | Se rechaza. Los valores válidos son INTERNAL, CONFIDENTIAL y RESTRICTED. |
| QA-VER-07 | Intentar estados distintos del conjunto aprobado | Se rechazan estados como proposed, active o archived. |
| QA-VER-08 | Ejecutar cada transición permitida | Se aceptan únicamente pending_review→approved, pending_review→rejected, approved→superseded y approved→forgotten, sujetos a sus condiciones adicionales. |
| QA-VER-09 | Reactivar versión rejected, superseded o forgotten | Se rechaza; no hay transición de reactivación. |
| QA-VER-10 | Crear nueva versión mientras existe versión aprobada vigente | La nueva queda pending_review; la anterior sigue siendo la vigente. |
| QA-VER-11 | Aprobar nueva versión | En una única operación lógica, la nueva pasa a approved, la anterior a superseded y se actualiza el puntero vigente. |
| QA-VER-12 | Fallo durante la sustitución de versión | No queda estado parcial: o se confirman todos los cambios o ninguno. |
| QA-VER-13 | Intentar reutilizar version_number o version_id | Se rechaza; el número es monotónico y no reutilizable dentro de la memoria y el ID es único. |
| QA-VER-14 | Crear nueva versión con clasificación heredada | Hereda la clasificación aprobada vigente, salvo una decisión directa del propietario registrada para el cambio exacto. |
| QA-VER-15 | Intentar downgrade automático por resumen, importación, transformación u origen distinto | Se rechaza; no se reduce clasificación por inferencia. |
| QA-VER-16 | Operar con clasificación RESTRICTED sin controles adicionales definidos/disponibles | La operación que dependa de esos controles deniega. No se interpreta RESTRICTED como permiso adicional. |
| QA-VER-17 | Intentar una transición no listada, incluida una transición desde estado terminal | Se rechaza sin mutar la versión ni el puntero vigente. |

### 6.3 Propuestas, atomicidad e idempotencia

| ID | Escenario | Resultado exigido |
|---|---|---|
| QA-PROP-01 | Enviar propuesta CREATE_MEMORY con scope explícito | Se crean Memory, primera MemoryVersion pending_review y MemoryProposal como unidad lógica atómica; puntero vigente nulo. |
| QA-PROP-02 | Enviar propuesta NEW_VERSION para Memory existente | Se crea MemoryVersion pending_review y MemoryProposal atómicamente; owner y scope se heredan de Memory y no pueden ser sustituidos por el solicitante. |
| QA-PROP-03 | Intentar propuesta sin intent válido o sin vínculo Memory/version | Se rechaza. |
| QA-PROP-04 | Consultar recuperación aprobada mientras una propuesta está pending_review | La propuesta y su contenido no aparecen como conocimiento aprobado; la versión aprobada anterior permanece disponible si la autorización lo permite. |
| QA-PROP-05 | Fallar una parte de CREATE_MEMORY | No queda Memory huérfana, versión sin propuesta ni propuesta sin versión. |
| QA-PROP-06 | Fallar una parte de NEW_VERSION | No queda versión o propuesta parcial. |
| QA-PROP-07 | Enviar dos propuestas concurrentes sobre la misma versión vigente | La asignación de número y parent se protege con CAS/revisión optimista o equivalente; un conflicto no sobrescribe ni reutiliza números. |
| QA-PROP-08 | Repetir actor, operación, idempotency_key y payload canónico | Se devuelve el mismo resultado lógico, sin crear una segunda propuesta/versión. |
| QA-PROP-09 | Repetir idempotency_key con payload canónico diferente | Se devuelve conflicto; no se modifica el resultado anterior. |
| QA-PROP-10 | Usar la misma idempotency_key desde otro actor u operación | No se confunden ámbitos de idempotencia; la clave se evalúa en el ámbito actor/operación establecido. |
| QA-PROP-11 | Omitir idempotency_key en un envío que la requiere | Se rechaza; request_id no se usa como sustituto implícito. |
| QA-PROP-12 | Conflicto de concurrencia durante revisión/aprobación | Se devuelve el error de concurrencia correspondiente; no se sobrescribe silenciosamente el estado y no se reintenta sin reevaluar autorización y estado. |

### 6.4 Autorización, scope y Grants

| ID | Escenario | Resultado exigido |
|---|---|---|
| QA-AUTH-01 | owner-A lee memory-A PRIVATE mediante MemoryGateway | Se permite únicamente tras identidad activa, metadatos confiables y evaluación CAM por la ruta PRIVATE explícita. |
| QA-AUTH-02 | owner-A intenta leer memory-D PRIVATE de user-B | Se deniega; no hay acceso por ser una identidad USER activa. |
| QA-AUTH-03 | owner-A accede a memory-A PRIVATE a través de ruta que evita Gateway o CAM | La ruta no existe o se deniega; la propiedad no es bypass. |
| QA-AUTH-04 | Leer memory-B PROJECT con project_id=project-A explícito y autorización válida | Se permite únicamente si actor, proyecto, scope, recurso, acción y Grant coinciden. |
| QA-AUTH-05 | Leer memory-B omitiendo project_id | Se deniega. |
| QA-AUTH-06 | Leer memory-B indicando project-B | Se deniega por discrepancia de proyecto. |
| QA-AUTH-07 | Intentar leer memory-C desde contexto project-A | Se deniega; no hay herencia ni cruce de proyectos. |
| QA-AUTH-08 | actor_identity y context.user_id son distintos | No se equiparan automáticamente; la autorización utiliza identidad autenticada y reglas CT-02. user_id contextual por sí solo no demuestra propiedad ni autoridad. |
| QA-AUTH-09 | Operación delegada con Grant limitado a otro recurso | Se deniega; delegación no amplía el alcance ni convierte al delegado en propietario. |
| QA-AUTH-10 | Recurso requiere environment_id y el contexto omite o declara otro entorno | Se deniega; no hay herencia implícita entre entornos. |
| QA-CAM-01 | Solicitar operación sobre recurso concreto sin resource_id | Se deniega. |
| QA-CAM-02 | Solicitar un resource_id distinto al recurso resuelto | Se deniega; no se sustituye por un recurso parecido ni por tipo. |
| QA-CAM-03 | Usar grant-type-only sin resource_ids explícitos para leer una instancia | Se deniega. |
| QA-CAM-04 | Usar grant-A para memory-A | Se permite solo si todos los demás controles y condiciones coinciden. |
| QA-CAM-05 | Usar grant-A para memory-B o cualquier ID no enumerado | Se deniega. |
| QA-CAM-06 | Operar sobre version-A2 con memory-A exacta y relación padre/hijo verificada | Se evalúa Grant contra memory-A y CAM verifica el version_id exacto como subrecurso. |
| QA-CAM-07 | Solicitar version-X1 declarando memory-A como padre | Se deniega por relación padre/hijo no coincidente. |
| QA-CAM-08 | Solicitar versión concreta inexistente, inválida o no verificable | Se deniega; nunca se sustituye silenciosamente por la versión vigente. |
| QA-CAM-09 | Leer sin especificar versión en lectura ordinaria | Gateway resuelve la versión aprobada vigente y autoriza la Memory antes de recuperar contenido. |
| QA-CAM-10 | Usar Grant para memory-A sobre una nueva versión perteneciente a memory-A | Puede cubrirla conforme al contrato, pero solo después de verificar que esa versión pertenece a memory-A y satisface estado/acción. |
| QA-CAM-11 | Intentar operación colectiva por tipo o wildcard | Se deniega en v1. |
| QA-CAM-12 | Crear memoria PROJECT en project-A | CAM evalúa la propuesta contra el ID exacto project-A y la acción memory.propose; no autoriza por tipo project. |
| QA-CAM-13 | Crear memoria PROJECT con proyecto inexistente, suspendido o no verificable | Se deniega. |
| QA-CAM-14 | Usar Grant expirado, revocado o fuera de alcance | Se deniega. |
| QA-CAM-15 | Intentar ampliar resource_ids por delegación o por creación automática de versión | Se deniega; la ampliación requiere decisión del propietario. |
| QA-CAM-16 | resource_id coincide, pero owner, project o environment no coincide con el Grant/metadatos | Se deniega; la coincidencia de ID no omite las demás dimensiones de ResourceIdentity. |

### 6.5 Autoridad de metadatos y fail-closed

| ID | Escenario | Resultado exigido |
|---|---|---|
| QA-META-01 | Solicitante declara owner_id distinto del owner canónico | CAM ignora el dato no autoritativo y resuelve el propietario desde MemoryMetadataPort; la discrepancia no concede acceso. |
| QA-META-02 | Solicitante declara project_id o scope que contradice el recurso | Se deniega. |
| QA-META-03 | MemoryMetadataPort o ProjectMetadataPort no está disponible, expira o devuelve datos inconsistentes | Se deniega; no se utiliza caché no validada ni dato del solicitante como fallback. |
| QA-META-04 | No existe ResourceMetadataResolver para el tipo requerido | Se deniega. |
| QA-META-05 | Intentar usar Registry del Broker como autoridad de metadatos de memoria | La integración se rechaza; Registry no sustituye MemoryMetadataPort. |
| QA-META-06 | Enumerar IDs candidatos para list_visible | Los IDs candidatos no exponen contenido ni metadatos protegidos antes de autorización individual. |
| QA-FAIL-01 | CAM no disponible o produce error | La operación protegida deniega; no continúa en modo permisivo. |
| QA-FAIL-02 | Scope, owner, project o environment requerido está ausente/ambiguo | Se deniega. |
| QA-FAIL-03 | Identidad suspendida | No inicia nuevas operaciones protegidas; se respeta CT-01. |
| QA-FAIL-04 | Identidad revocada | No puede participar en operaciones protegidas ni reactivarse como la misma identidad. |
| QA-FAIL-05 | Resolver devuelve relación padre/hijo no verificable | Se deniega. |
| QA-FAIL-06 | Error de autorización o not-found para recurso protegido | No revela si el recurso existe ni expone contenido o metadatos protegidos. |
| QA-FAIL-07 | Cualquier fallo de autorización | No activa fallback por tipo, acceso directo, consulta sin filtro de scope ni uso de contenido previo. |
| QA-FAIL-08 | Identidad se suspende/revoca durante una operación dependiente | Se detienen nuevas operaciones y se aplica el tratamiento cooperativo definido en CT-01; la identidad revocada no continúa como si siguiera activa. |

### 6.6 Decisiones directas del propietario

| ID | Escenario | Resultado exigido |
|---|---|---|
| QA-OWNER-01 | Aprobar propuesta con prueba válida del propietario | Se permite solo si sujeto autenticado, actor USER y propietario canónico coinciden; acción y recursos exactos coinciden. |
| QA-OWNER-02 | Rechazar propuesta con prueba válida del propietario | Se permite bajo las mismas condiciones y solo para proposal_id/version_id exactos. |
| QA-OWNER-03 | Aprobar/rechazar con actor distinto del propietario | Se deniega aunque exista Grant. |
| QA-OWNER-04 | Presentar texto de chat, booleano, afirmación del Assistant o context.delegation=None como prueba | Se deniega; esos datos no constituyen OwnerDecisionProof. |
| QA-OWNER-05 | Reutilizar proof_id/nonce ya consumido | Se deniega; prueba de un solo uso. |
| QA-OWNER-06 | Prueba expirada, emisor desconocido, acción o recurso distinto | Se deniega. |
| QA-OWNER-07 | OwnerDecisionVerifier no disponible o error al verificar/consumir | Se deniega y no se cambia el estado de la propuesta/memoria. |
| QA-OWNER-08 | Delegación activa o prueba con delegation distinta de NONE | Se deniega para approve/reject/forget. |
| QA-OWNER-09 | Assistant, Memory Engine, Watcher, Analysis Engine o Skill intenta aprobar/rechazar | Se deniega; ninguno posee esa autoridad. |
| QA-OWNER-10 | No existe emisor de autenticación confiable en integración | approve/reject/forget permanecen deshabilitados; no se introduce bypass provisional. |
| QA-OWNER-11 | Proof contiene request_id distinto, action distinta, recurso/propuesta/version distinta o nonce no válido | Se deniega; la prueba está ligada a la solicitud y recursos exactos y no puede reutilizarse en otra operación. |

Las pruebas QA-OWNER-01 y QA-OWNER-02 pueden ejecutarse contra un emisor/verificador de prueba aislado para verificar el contrato. Esto no equivale a aceptar el proveedor real de autenticación.

### 6.7 Procedencia, evidencia y clasificación

| ID | Escenario | Resultado exigido |
|---|---|---|
| QA-PROV-01 | Crear versión sin provenance | Se rechaza. |
| QA-PROV-02 | Usar SourceKind fuera del catálogo cerrado | Se rechaza. Valores admitidos: USER_INPUT, CONVERSATION, FILE, CONNECTOR, TOOL_RESULT, SYSTEM_EVENT, DERIVED e IMPORT. |
| QA-PROV-03 | origin declara un actor diferente al autenticado | origin no autentica ni sustituye actor; CAM usa identidad y metadatos confiables. |
| QA-PROV-04 | Incluir credenciales, URLs con credenciales o payloads completos en referencias | Se rechaza o sanea conforme al contrato sin conservar secretos en provenance. |
| QA-PROV-05 | Fuente desaparece | Se conserva referencia opaca y estado UNAVAILABLE; no se presenta como fuente verificable vigente. |
| QA-PROV-06 | Intentar leer evidencia referenciada sin permiso sobre el recurso de evidencia | Se deniega; la referencia no concede permiso. |
| QA-PROV-07 | Consultar una versión histórica autorizada | Se conserva provenance de esa versión; el historial no concede acceso por sí mismo. |
| QA-PROV-08 | Intentar reducir clasificación durante transformación/importación | Se deniega el downgrade implícito. |
| QA-PROV-09 | Elevar o reducir clasificación sin decisión directa del propietario ligada a propuesta/versión exacta | Se deniega. |
| QA-PROV-10 | Usar clasificación como sustituto de CAM o scope | Se deniega; clasificación no es permiso. |

### 6.8 MemoryGateway y frontera de componentes

| ID | Escenario | Resultado exigido |
|---|---|---|
| QA-GW-01 | Assistant lee memoria protegida | La lectura ocurre exclusivamente a través de MemoryGateway y CAM. |
| QA-GW-02 | Watcher o Proactivity lee memoria protegida | Usa Gateway y CAM con identidad, fuente y alcance válidos. |
| QA-GW-03 | Skill o servicio intenta acceder directamente al almacén | Acceso bloqueado por frontera; no existe ruta lateral. |
| QA-GW-04 | Llamar operaciones de lectura, propuesta, aprobación, rechazo u olvido | Todas pasan por Gateway; ninguna operación protegida omite CAM. |
| QA-GW-05 | Llamar list_visible(context) | Se conserva la interfaz contractual vigente; no se presupone filtros o paginación no aprobados. |
| QA-GW-06 | list_visible obtiene varios IDs candidatos | Cada recurso se autoriza individualmente antes de devolver metadatos protegidos o contenido. |
| QA-GW-07 | Algunos candidatos no están autorizados | Se excluyen sin exponer contenido, metadatos, embeddings ni conteos que permitan inferir recursos no autorizados. |
| QA-GW-08 | Gateway recibe una respuesta de CAM incompleta o incierta | Deniega; no interpreta ausencia de respuesta como ALLOW. |

### 6.9 Olvido y supresión

| ID | Escenario | Resultado exigido |
|---|---|---|
| QA-FORGET-01 | Solicitar forget sin decisión directa verificable del propietario | Se deniega; no se inicia una mutación autorizada. |
| QA-FORGET-02 | Solicitar forget con decisión válida y CAM válido | Puede iniciarse el proceso de supresión según el contrato; iniciar no significa completar. |
| QA-FORGET-03 | Supresión lógica iniciada | La memoria deja inmediatamente de ser recuperable/exponible por las rutas ordinarias. |
| QA-FORGET-04 | Proceso físico pendiente o destino no disponible | No se comunica éxito ni se asigna estado final forgotten. El recurso permanece bloqueado para recuperación. |
| QA-FORGET-05 | Inventario de destinos incompleto o desconocido | El olvido completo permanece BLOCKED; no se declara verificado. |
| QA-FORGET-06 | Un destino activo o derivado no confirma eliminación | El proceso permanece incompleto y requiere reconciliación/reintento. |
| QA-FORGET-07 | Restaurar backup, reindexar o importar una copia que contiene una memoria suprimida | El registro de supresión se aplica antes de exponer datos; la memoria no reaparece. |
| QA-FORGET-08 | Consultar registro mínimo de supresión | No contiene contenido original, fragmentos ni hashes de contenido vulnerables a ataques de diccionario. |
| QA-FORGET-09 | Un backup inmutable retenido aún contiene contenido | No se declara purga física completa; se respeta la política de retención que se apruebe. |
| QA-FORGET-10 | Todos los destinos aplicables han sido verificados conforme a política aprobada | Solo entonces puede completarse el olvido y reflejarse forgotten según CT-05/DM-01. |

**Bloqueo explícito:** QA-FORGET-05 a QA-FORGET-10 no pueden recibir aceptación integral de producción hasta aprobar inventario de destinos, retención física, plazos y criterios verificables. QA-01 no inventa esos valores ni declara completado el flujo.

### 6.10 Atlas Assistant y Proactivity

| ID | Escenario | Resultado exigido |
|---|---|---|
| QA-AST-01 | Assistant recupera memoria aprobada | Solo presenta datos obtenidos mediante Gateway y autorizados para el actor/contexto. |
| QA-AST-02 | Assistant recibe propuesta pending_review | No la presenta como conocimiento aprobado. |
| QA-AST-03 | Assistant propone nueva memoria/versión | La envía a Gateway como propuesta; no modifica Memory directamente. |
| QA-AST-04 | Assistant intenta aprobar, rechazar, olvidar o conceder Grants | La operación se deniega; requiere decisión directa del propietario y controles definidos. |
| QA-PRO-01 | Watcher observa fuente interna habilitada | Registra observación con referencia y tiempo, sin mutar la fuente. |
| QA-PRO-02 | Watcher intenta observar fuente no habilitada | Se deniega. |
| QA-PRO-03 | Proactivity accede a memoria o evidencia | Usa Gateway/CAM y los controles del recurso referenciado. |
| QA-PRO-04 | Analysis Engine produce hallazgo o propuesta | Distingue observación de inferencia, conserva evidencia y no modifica recursos. |
| QA-PRO-05 | Reevaluación automática | Es estrictamente de solo lectura; vuelve a comprobar autorización vigente. |
| QA-PRO-06 | Proactivity genera ProactiveProposal | Se entrega a Assistant; no notifica directamente ni crea permiso/tarea admitida. |
| QA-PRO-07 | Usuario guarda silencio ante una propuesta | El silencio no se interpreta como aprobación. |
| QA-PRO-08 | Fuente inaccesible o reevaluación interrumpida | Se informa estado indeterminado/no disponible; no se concluye que la condición desapareció. |
| QA-PRO-09 | Skill intenta elevar permisos o saltar Gateway/CAM | Se deniega y se conserva el aislamiento. |
| QA-PRO-10 | Finding, FollowUpRecord o Observation se convierte en evento/incidencia automáticamente | Se rechaza cualquier confusión de tipos o reescritura de eventos originales. |

### 6.11 Errores, eventos y consistencia transversal

| ID | Escenario | Resultado exigido |
|---|---|---|
| QA-ERR-01 | Entrada o estado viola invariantes de dominio | Se utiliza ContractError o el error contractual específico; no se etiqueta como autorización si no lo es. |
| QA-ERR-02 | Operación fuera de permisos/scope/Grant | Se utiliza AuthorizationError o la respuesta externa equivalente sin filtrar datos. |
| QA-ERR-03 | Recurso inexistente o no visible | La respuesta no permite distinguir existencia real de existencia protegida. |
| QA-ERR-04 | Estado cambió concurrentemente | Se utiliza ConcurrencyError; no se sobrescribe el cambio. |
| QA-ERR-05 | Conflicto concurrente | Antes de cualquier reintento se obtiene estado actual, se reevalúan permisos y seguridad y se confirma idempotencia. |
| QA-EVT-01 | Evento de memoria o proactividad se construye | Cumple identidad, tiempo UTC, OperationContext y clasificación contractual. |
| QA-EVT-02 | Modificar evento o mapping anidado tras construirlo/registrarlo | No altera el evento; inmutabilidad profunda verificable. |
| QA-EVT-03 | Consultar eventos por correlation_id | No mezcla otras correlaciones ni expone eventos sin autorización. |
| QA-EVT-04 | Registrar fallo de persistencia/consulta | No se informa como evento completado. |
| QA-EVT-05 | Deduplication key presente o ausente | No se confunde deduplicación con idempotencia. |
| QA-X-01 | Aplicar C08-AC-05 | Cada nueva lectura y reevaluación vuelve a verificar identidad, CAM, fuente, recurso y alcance. |
| QA-X-02 | Aplicar C08-AC-12/C08-AC-13 | Proactivity entrega propuestas solo a Assistant; propuesta no crea permiso ni tarea admitida. |
| QA-X-03 | Aplicar C08-AC-17 | Assistant, Watchers y Proactivity no aprueban, rechazan ni olvidan por el propietario. |
| QA-X-04 | Informar estado del producto a partir de pruebas documentales | No se afirma implementación, integración, despliegue o SecurityAudit verificados sin evidencia de ejecución. |

## 7. Reglas de ejecución y evidencia

### 7.1 Evidencia mínima por escenario

Cada ejecución deberá conservar:

- ID del escenario QA-01.
- Commit exacto probado.
- Versión de los contratos/fixtures utilizados.
- Tipo de prueba y entorno aislado.
- Resultado PASS/FAIL/BLOCKED/NOT RUN.
- Resultado observable y aserciones relevantes.
- Identificadores opacos de correlación cuando correspondan.
- Evidencia de que no hubo efecto prohibido en pruebas negativas.
- Causa y dependencia concreta cuando esté BLOCKED.

No se incluirán contenidos de memoria reales, credenciales, tokens ni datos personales en artefactos de prueba.

### 7.2 Reglas para pruebas negativas

Una denegación solo es PASS si además se verifica:

1. No se leyó contenido antes de autorizar.
2. No se devolvieron fragmentos, embeddings ni metadatos protegidos.
3. No se modificó el recurso, versión, Grant o estado.
4. No se expuso la existencia de recursos protegidos.
5. No se activó fallback por tipo, scope inferido o acceso directo.
6. No se emitió una respuesta de éxito engañosa.
7. La correlación/evento no contiene secretos ni contenido protegido.

### 7.3 Pruebas de integración

Las pruebas de integración deben demostrar la ruta real:

`Caller → MemoryGateway → CAM → ResourceMetadataResolver → dominio/almacén`

El orden de autorización es obligatorio: identidad y contexto; metadatos autoritativos; comparación exacta de recurso/owner/scope/project/environment; regla PRIVATE o Grant; no delegabilidad y OwnerDecisionProof cuando corresponda; solo entonces lectura o mutación.

Un doble de prueba puede verificar el contrato de un puerto, pero no acredita que un adaptador real, proveedor de autenticación o almacenamiento esté implementado.

### 7.4 No regresión

- Los contratos CT-01 a CT-08 y el contrato principal permanecen como autoridad.
- No se cambian firmas públicas por conveniencia de los tests.
- En particular, no se presupone que `list_visible(context)` incorpore filtros o paginación.
- No se relajan garantías de aislamiento, autorización, atomicidad, no delegabilidad o supresión.
- Ninguna prueba debe depender de Atlas Broker/Registry como autoridad de memoria.

## 8. Criterios de salida de QA-01

QA-01 estará listo para pasar a implementación de pruebas cuando:

1. Todos los escenarios no bloqueados tengan fixtures y resultados esperados inequívocos.
2. La matriz de trazabilidad cubra DM-01-01 a DM-01-20 y los criterios aplicables de CT-05, CT-06, CT-07 y CT-08.
3. Las pruebas de denegación comprueben ausencia de filtraciones y efectos laterales, no solo el tipo de excepción.
4. Se identifiquen expresamente los escenarios BLOCKED por dependencias pendientes.
5. Ningún escenario introduzca una decisión de infraestructura o política no aprobada.
6. El plan de ejecución distinga pruebas de dominio, integración, seguridad y regresión.
7. La revisión del código de pruebas confirme que los tests no aceptan accidentalmente el comportamiento actual contrario al contrato, especialmente Grant por tipo sin resource_id exacto.

El cierre de QA-01 como documento no significa que la suite se haya implementado ni ejecutado.

## 9. Dependencias pendientes y gates de aceptación

| Dependencia | Qué puede probarse ahora | Qué permanece bloqueado |
|---|---|---|
| Emisor real de OwnerDecisionProof | Contrato del verificador con fixtures aislados; denegación ante ausencia/error | Aceptación de integración real de approve/reject/forget |
| Inventario y retención de backups | Supresión lógica, bloqueo de lectura, tratamiento de destino no disponible | Declarar olvido físico completo y estado final forgotten |
| Adaptadores de metadatos/almacenamiento | Contratos de puertos con dobles deterministas | Integración real y certificación de disponibilidad/consistencia |
| Controles de RESTRICTED | Denegación si los controles requeridos faltan; clasificación no concede permiso | Casos positivos que dependan de controles aún no definidos |
| SecurityAudit | Verificar que la trazabilidad funcional no se presenta como SecurityAudit | Aceptación de SecurityAudit, cuya implementación sigue postergada |

Estos gates no suspenden ni debilitan las pruebas negativas y las garantías ya aprobadas.

## 10. Relación con los documentos fuente

- `Contrato-de-diseno-Atlas-v1.md`: contrato principal, especialmente límites de autoridad, aprobación del propietario y alcance autorizado.
- `docs/contracts/identity.md` (CT-01): identidad, suspensión, revocación y estado.
- `docs/contracts/operation-context.md` (CT-02): actor, usuario contextual, delegación, proyecto, entorno, origen y correlación.
- `docs/contracts/errors.md` (CT-03): ContractError, AuthorizationError, NotFoundError, ConcurrencyError y no exposición.
- `docs/contracts/events.md` (CT-04): estructura, inmutabilidad, correlación, clasificación y fallos.
- `docs/contracts/memory.md` (CT-05): scopes, lifecycle, versiones, Gateway, review, forget y criterios MEM-01 a MEM-40.
- `docs/contracts/assistant.md` (CT-06): autoridad y límites de Atlas Assistant.
- `docs/contracts/proactivity.md` (CT-07): observación, análisis, propuestas, seguimiento y criterios PRO-01 a PRO-42.
- `docs/contracts/consistency-matrix-ct-08.md` (CT-08): criterios transversales C08-AC-01 a C08-AC-20.
- `docs/design/domain-model-specification-dm-01.md`: invariantes DM-01-01 a DM-01-20 y decisiones DM-P01 a DM-P12.
- `docs/design/memory-engine-technical-contract.md`: contrato técnico de Memory Engine y su relación con DM-01.

## 11. Registro de cambios

| Versión | Cambio | Estado |
|---|---|---|
| 0.1 | Primera especificación QA-01: escenarios de dominio, autorización, versionado, revisión, supresión y fronteras transversales. | Borrador documental para revisión |

---

**QA-01 especifica qué debe demostrarse. No afirma que ninguna prueba haya sido implementada, ejecutada o superada.**
