# F0 — Mapa de composición funcional de Atlas

> Inspección de código: 16 de noviembre de 2026.
> Rama: `feature/terminal-commands`.
> Alcance: inspección estática de los archivos indicados; no equivale a una ejecución local nueva.
> Propósito: seleccionar el primer flujo funcional sin duplicar la base conversacional.

## 1. Punto de entrada y composición actual

### Arranque

- `src/atlas/__main__.py` importa y ejecuta `atlas.cli.main`.
- `pyproject.toml` expone el comando `atlas = atlas.cli:main`.
- `src/atlas/cli.py` es el composition root actual.

### Grafo conversacional verificado

```text
python -m atlas
    |
    v
atlas.cli.main
    |
    +--> SQLiteDatabase
    |       |
    |       +--> SQLiteConversationRepository
    |       +--> ConversationBackup
    |       +--> ConversationExport
    |
    +--> ConversationManager
    +--> ConversationConsoleCommands
    +--> LocalConsoleRequestFactory
    |
    +--> OllamaProvider
    |       |
    |       v
    |   OllamaResponseGenerator
    |       |
    |       v
    |   AssistantService
    |       |
    |       v
    |   ConversationContextProcessor <--- SQLiteConversationRepository
    |       |
    |       v
    |   AtlasCore
    |       |
    |       v
    +--> run_console
```

El modo offline sustituye el generador Ollama por `LocalModeResponseGenerator`. El modo normal usa el modelo configurado por `ATLAS_MODEL` o `gemma4:e2b`, y el endpoint configurado por `ATLAS_OLLAMA_URL` o loopback `127.0.0.1:11434`.

## 2. Responsabilidades existentes que se deben reutilizar

| Componente | Responsabilidad actual | Decisión |
|---|---|---|
| `AtlasCore` | Crea solicitud, delega y valida correlación/contexto | Reutilizar como fachada de entrada |
| `AssistantService` | Genera respuesta conversacional | Mantener separado de capacidades |
| `OllamaResponseGenerator` | Traduce solicitud/contexto a mensajes LLM | No convertirlo en ejecutor de herramientas |
| `ConversationContextProcessor` | Proyecta historial durable acotado y guarda turnos exitosos | Reutilizar para continuidad conversacional |
| `ConversationManager` | Ciclo de vida de conversaciones | Reutilizar |
| `SQLiteConversationRepository` | Persistencia de conversaciones y mensajes | Reutilizar para historial; no mezclar estado de tareas sin diseño |
| `ConversationConsoleCommands` | Comandos de administración de conversaciones y backup/export | Extender solo para comandos de producto cuando proceda |
| `run_console` | Bucle de entrada, streaming y despacho de comandos | Mantenerlo como adaptador de presentación |
| `cli.main` | Composición concreta de dependencias | Añadir aquí los nuevos servicios/adaptadores cuando estén probados |

## 3.1 Planificación funcional aislada (F1)

La rama incorpora un flujo independiente del runtime conversacional:

```text
Proveedor LLM inyectado
        |
        v
OllamaIntentInterpreter
        |
        v
parse_intent_interpretation
        |
        v
AssistantRequestPlanner
        |
        v
AssistantPlanningService
        |
        v
RequestPlanningResult
```

- `atlas.bootstrap.build_request_planner(provider, model)` compone el flujo.
- El proveedor se inyecta; la fábrica no crea conexiones ni inicia servicios.
- La configuración del proveedor para Gemma debe incluir `think=False` y `response_format="json"`, según la prueba manual reportada por el propietario.
- Este flujo todavía no se instancia desde `cli.py`, no recibe solicitudes de la consola y no ejecuta capacidades.

## 4. Límites observados

- `AtlasCore` solo expone `respond` y `respond_streaming`; no tiene un caso de uso de planificación ni ejecución.
- `AssistantService` solo genera texto informativo.
- `ATLAS_SYSTEM_PROMPT` indica que el modelo no tiene herramientas y no puede afirmar que ejecutó operaciones.
- El historial de conversación es durable; el estado de tareas aún no está implementado como flujo de usuario.
- `run_console` despacha comandos que empiezan por `/` al handler, y el resto del texto se envía al runtime conversacional.
- Los contratos P3-SR están bajo `tests/evaluation/phase3`; no son herramientas productivas y no deben conectarse al runtime.
- Los módulos de Identity/CAM y Memory Engine no deben considerarse servicios operativos del Assistant por el mero hecho de existir en el repositorio.

## 5. Primer flujo vertical seleccionado

Construir un workspace de prueba dedicado y un flujo de proyecto mínimo, antes de generalizar a agentes, skills o Scheduler.

### Caso de uso inicial

El propietario solicita: "Inspecciona el workspace demo y dime qué archivos contiene".

Flujo previsto:

1. La capa de aplicación reconoce una intención soportada: `workspace.list`.
2. La aplicación valida los parámetros requeridos y el workspace seleccionado.
3. Atlas presenta un plan pequeño y explícito.
4. El usuario confirma la ejecución del flujo de prueba.
5. Un adaptador local enumera archivos únicamente dentro del workspace demo configurado.
6. El adaptador devuelve un resultado estructurado con rutas relativas, tamaños y estado.
7. Atlas presenta el resultado real; si ocurre un error, lo informa sin inventar éxito.
8. La conversación conserva la solicitud y la respuesta; el estado de tarea se persistirá en su propio repositorio en el incremento siguiente.

### Por qué empezar con listado

- Es una operación real, observable y fácil de verificar.
- No requiere modificar archivos.
- Valida el recorrido intención → plan → capacidad → resultado.
- Permite introducir el catálogo de capacidades y el contrato de ejecución sin construir aún un sistema general de herramientas.
- El workspace de prueba puede crearse con datos de fixture y mantenerse fuera de los datos personales.

La siguiente operación será `workspace.read`. Las operaciones de escritura se incorporarán después de demostrar el flujo de lectura y la persistencia de tareas.

## 6. Diseño funcional incremental

### F1 — Interpretación y planificación

Introducir en la capa de aplicación, sin alterar el generador conversacional existente:

- Un catálogo cerrado de intenciones soportadas.
- Un contrato inmutable de intención y parámetros.
- Un resultado de interpretación que pueda pedir aclaraciones o declarar intención no soportada.
- Un plan con pasos tipados, capacidad requerida y resultado esperado.
- Un adaptador de interpretación LLM intercambiable; la validación de aplicación conserva la autoridad sobre el esquema y las capacidades disponibles.

No depender de coincidencias de texto aisladas como clasificador definitivo. El modelo puede proponer una intención, pero la aplicación valida que exista y que sus parámetros cumplan el contrato.

### F2 — Capacidades de workspace

Empezar con:

1. `workspace.list`
2. `workspace.read`
3. `workspace.write` sobre archivos de prueba explícitos, después de validar las dos primeras.

La raíz del workspace se configura en la composición local. Las operaciones reciben rutas relativas y devuelven resultados estructurados. El adaptador no se expone al modelo como acceso general al sistema de archivos.

### F3 — Ejecución y estado

Añadir un modelo de tarea con ID, estado, plan, timestamps y resultado/error; repositorio SQLite separado o tablas dedicadas y migración versionada; servicio de aplicación que ejecuta pasos secuenciales y registra estados. No duplicar el historial conversacional dentro del registro de tarea.

### F4 — Continuidad

Asociar tarea y conversación mediante identificadores. Al iniciar, recuperar tareas no terminales y mostrar su estado; no reejecutar automáticamente operaciones cuyo resultado sea incierto. Para la primera versión, la continuidad puede permitir consultar y reanudar manualmente una tarea de prueba.

### F5 — Experiencia integrada

Añadir comandos de consola como `/capabilities`, `/tasks` y `/task <id>`, más un flujo conversacional de plan/confirmación/resultado. Mantener la administración de conversaciones existente sin cambios regresivos.

## 7. Pruebas mínimas por incremento

- Unitarias: validación de intención, parámetros, plan, transiciones de tarea y resultado del adaptador.
- Integración: repositorio SQLite de tareas con base temporal.
- Workspace: listado y lectura sobre fixtures; ruta inexistente y workspace vacío.
- Consola: plan, confirmación, resultado y error observable.
- Regresión: ejecutar la suite completa vigente y registrar el total validado por el propietario.

No se marcará F1–F5 como completada hasta ejecutar las pruebas en el entorno local del propietario y comprobar el flujo vertical real.

## 8. Estado F0

**Inspección estática realizada:** composition root, fachada AtlasCore, AssistantService, generador Ollama, proyección de contexto, gestor de conversaciones y consola.

**Pendiente para cerrar F0 con evidencia local:** comprobar que el checkout Debian está en el mismo commit/branch y ejecutar la suite de regresión antes de introducir cambios de código.

**Estado actual:** F1.1–F1.5 están implementadas y el propietario validó Gemma real más 886/886 pruebas. F2.1 añade el contrato y adaptador local `workspace.list`; la validación local está pendiente. Ninguna de estas capacidades está conectada todavía a `cli.py` ni al runtime conversacional.


## 9. Frontera de autorización y revisión (F2.3)

Documento de diseño: [F2.3 — Frontera de autorización, revisión y ejecución](design/assistant-workspace-execution-boundary.md).

La inspección de los contratos existentes identificó que:

- `AuthorizationEvaluator` evalúa Grants y produce `AuthorizationEvaluation`, que es interno y no constituye autorización pública.
- `AuthorizationPort` devuelve `AuthorizationResult`, cuyo `ALLOW` exige un `AuthorizationSnapshot` específico de Memory.
- `MemoryAuthorizationService` no es un autorizador de operaciones workspace.
- No existe un Approval Manager general conectado al flujo funcional.
- `OperationContext` permite proyecto y entorno ausentes; una operación protegida debe resolverlos confiablemente y fallar cerrado si son obligatorios.

Por tanto, la composición futura debe separar revisión de intención, autorización CAM y aprobación humana. La confirmación de revisión no concede permisos; una aprobación no convierte DENY en ALLOW; la autorización se revalida antes de ejecutar. El siguiente incremento diseñará el contrato genérico de evidencia CAM sin conectar aún consola ni runtime.

**Estado:** F2.1 validada (893 pruebas en ese punto); F2.2 validada por el propietario con 900/900 pruebas; F2.3 diseño documentado, sin implementación de autorización, aprobación o ejecución.


## 10. Contrato de autorización de operaciones (F2.3.1)

Se añadieron contratos separados del resultado de autorización de Memory:

- `atlas.authorization.operation_models.OperationAuthorizationEvidence`: claims ligados al request, actor/revisión, proyecto, entorno, acción, recurso/owner exactos, Grant/revisión y vigencia.
- `OperationAuthorizationEvidence.matches(request)` valida correspondencia de claims; `is_current_at(now)` valida solo la ventana temporal.
- `OperationAuthorizationResult`: exige evidencia para ALLOW y la prohíbe para DENY/REQUIRE_APPROVAL.
- `atlas.ports.operation_authorization.OperationAuthorizationPort`: puerto de evaluación sin ejecución.
- Pruebas en `tests/unit/test_operation_authorization_contracts.py`.

Estos modelos no autentican al issuer, no prueban revocación actual ni sustituyen un servicio CAM confiable. No existe todavía adaptador productivo ni integración al Assistant/CLI. La validación local de este incremento está pendiente.


## 11. Verificación de evidencia de operación (F2.3.2)

- Puerto `OperationAuthorizationEvidenceVerifierPort`: contrato para validar emisor y decisión CAM, estado/revisión de identidad, Grant, proyecto y entorno.
- Servicio `OperationAuthorizationEvidenceVerificationService`: valida coincidencia exacta y vigencia temporal local; delega la comprobación autoritativa al puerto.
- Estados `VERIFIED`, `DENIED`, `UNAVAILABLE`; cualquier excepción del verificador falla cerrado.
- Pruebas en `tests/unit/test_operation_authorization_verification.py`.

No existe adaptador concreto. El resultado VERIFIED no ejecuta ni concede por sí solo una capacidad. Para operaciones con efectos se necesita una garantía contra carreras de revocación, no una lectura puntual eventual. Validación local pendiente.


## 12. Binding completo de revisiones de autoridad (F2.3.3a)

`OperationAuthorizationEvidence` ahora exige cuatro revisiones positivas: actor, Grant, proyecto y entorno. El verificador confiable deberá contrastarlas con las fuentes canónicas. Se añadieron pruebas para rechazar cero, negativos y booleanos en project_revision/environment_revision.

Este cambio solo completa los claims; no verifica por sí mismo que las revisiones sigan actuales ni cierra carreras de concurrencia. Validación local pendiente.


## 13. Hallazgo F2.3.3b — No hay aún coordinador autoritativo común

La inspección confirma:
- `RevisionValidationPort` es específico de Memory y de `AuthorizationSnapshot`; requiere invalidation-first y comparación de `ConsistencyPosition` dentro de la UoW.
- `GrantRepository` no ofrece coordinación de invalidación.
- `SQLiteIdentityAuthority` aplica CAS a identidad, no coordina cambios de autoridad.
- `AuthorityChangeCoordinatorPort` no tiene adaptador concreto encontrado en esta rama.
- `SQLiteAuthorityChangeStore` solo almacena reservas/idempotencia, no realiza fencing ni reconciliación.

No se debe construir un verificador genérico con lecturas puntuales ni simular consistencia global. El verificador de operaciones sigue siendo un puerto sin adaptador. La implementación de ejecución queda bloqueada hasta que exista una autoridad de consistencia compartida o se apruebe explícitamente un perfil local de prueba sin efectos que no afirme garantías de revocación concurrente.


## 14. F2.3.4 — Decisión sobre consistencia de operaciones

Documento: [Frontera de consistencia para operaciones del Assistant](design/assistant-operation-consistency-boundary.md).

La evidencia CAM, incluso verificada, no es admisión ni permiso de ejecución. Las operaciones requieren una admisión exacta y coordinada con invalidación/fencing. La serialización `BEGIN IMMEDIATE` solo es una garantía válida si todas las fuentes de autoridad, el journal y las admisiones participan en la misma SQLiteDatabase/UoW y cada mutación usa el mismo coordinador.

El primer perfil posible es de solo lectura (`workspace.list`, `workspace.read`). Las escrituras quedan fuera hasta tener un protocolo durable que cubra staging, commit del filesystem y recuperación de resultados inciertos. No se ha creado adaptador ni conectado runtime.

**Siguiente inspección:** matriz de Identity/Grant/Project/Environment → repositorio → base de datos → UoW → caminos de mutación.


## 15. F2.3.5 — Inventario de persistencia CAM

El inventario detallado está en [assistant-operation-consistency-boundary.md](design/assistant-operation-consistency-boundary.md). Hallazgos:

- Identity: `compose_sqlite_identity(path)` crea su propia instancia SQLite; CAS directo de estado, sin invalidación común.
- Grant: solo Protocol y UoW para Grant/renovaciones; no se encontró adaptador SQLite concreto. `issue` escribe directo; revoke depende de un coordinador inyectado no implementado.
- Project/Environment: contratos de metadatos de Memory sin repositorios canónicos de producto encontrados.
- Journal/authority changes: persistencia SQLite separada; no está compuesta con las cuatro autoridades.

No existe UoW compartida ni coordinador concreto. El adaptador de verificación no debe implementarse hasta decidir si se construyen las fuentes canónicas locales y se migran sus mutaciones, o si CAM se aplaza para el perfil de lectura inicial.

## 16. F2.3.6 — Composición Identity sobre base compartida

Se añadió `compose_sqlite_identity_on_database(database)` como seam de composición. Permite que una futura raíz de autoridad local cree una única `SQLiteDatabase` y entregue la misma instancia a Identity. La composición standalone por ruta se mantiene compatible.

Pruebas para reutilización exacta de la instancia y rechazo de tipos inválidos. Pendiente de ejecución local. No implica aún autoridad común ni cambia el runtime.

## 17. F2.3.7 — Persistencia canónica inicial de Grants

Migración SQLite v7 y adaptador `SQLiteGrantRepository`. Grants se almacenan como una unidad de revisión: IDs/scope/acciones inmutables, CAS por revisión, revocación terminal y retención de tombstones. `SQLiteLocalAuthorityFoundation` compone Identity, Grants y el ledger de cambios sobre la misma instancia SQLite.

Validado por el propietario con 943/943 pruebas. Pendiente: fuentes canónicas Project/Environment (en desarrollo), coordinador durable de invalidación/fencing. Sin runtime.

## 18. F2.3.8 — UoW transaccional de Grant + renovaciones

Migración v8 y `SQLiteGrantRenewalRepository`. `SQLiteAuthorizationUnitOfWorkFactory` une repositorios de Grant y renovación en una misma transacción SQLite inmediata; la confirmación es explícita y solo se materializa al salir sin excepción. Se conectan `GrantRenewalService` y el modo configurado de `GrantManagementService.issue` a esta abstracción. El repositorio de renovaciones conserva binding inmutable, CAS de versión, decisión terminal e historial no borrable.

Validado por el propietario con 957/957 pruebas. Pendiente: obligar todo el wiring de emisión a usar la fábrica, incorporar todas las mutaciones al coordinador común, invalidación/fencing y admisión.

## 19. F2.3.9 — Fuentes canónicas Project y Environment

Migración v9: tablas `atlas_projects` y `atlas_environments` con identificador inmutable, estado, revisión CAS y retención de tombstones. `SQLiteProjectEnvironmentRepository` implementa los dos puertos de metadatos existentes y se añade a `SQLiteLocalAuthorityFoundation` usando la misma instancia SQLite compartida con Identity, Grants, renovaciones y authority-change ledger.

Validado por el propietario con 967/967 pruebas. Las mutaciones de Project/Environment aún no están coordinadas por invalidación/fencing y no deben utilizarse como prueba de admisión segura.

## 20. F2.3.10 — Auditoría de mutaciones

La auditoría confirma que la persistencia compartida no equivale a consistencia de autoridad: Identity, emisión y renovación de Grant, y cambios Project/Environment aún tienen rutas sin coordinador de invalidación/fencing. La revocación exige un coordinador por contrato, pero no hay implementación concreta completa. El ledger SQLite es solo reserva/idempotencia. Se documentó el orden para cerrar todos los caminos de mutación antes de admisión. Sin cambios runtime; F2.3 permanece sin integración.

## 21. F2.3.11 — Emisión de Grant fail-closed

`GrantManagementService.issue` exige ahora `unit_of_work_factory` y rechaza emitir si falta, eliminando su fallback de escritura directa. La unicidad y creación siguen dentro de una UoW. Prueba nueva cubre ausencia de UoW. Validado por el propietario con 968/968 pruebas; no equivale a coordinación de invalidación/fencing.

## 22. F2.3.12 — Auditoría de renovaciones

La aprobación de renovación actualiza Grant + solicitud atómicamente en UoW, pero no hace fencing/invalidation de admisiones antiguas. Solicitud, aprobación y rechazo requieren semánticas diferenciadas; aprobación humana del propietario no reemplaza CAM. La futura operación debe vincular revisión Grant y versión de renovación, actor/owner/project/environment y pasar por coordinación durable. Sin cambios runtime.

## 23. F2.3.13 — Cambios multiobjetivo

Diseño publicado para operaciones que modifican varias autoridades. Aprobación de renovación requiere objetivos tipados para Grant y solicitud, una reserva/idempotencia común, CAM vinculado a todos los objetivos, fencing conjunto, CAS atómico y reconciliación completa. El contrato y el store actuales de una autoridad no se han cambiado. Diseño solamente; sin runtime ni pruebas.

## 24. F2.3.14 — Modelos multiobjetivo

Contratos inmutables añadidos para cambios que afectan varias autoridades: targets tipados (incl. Grant y Grant renewal), revisión +1, orden canónico, no duplicados, contexto de actor/owner/action e idempotencia. Pruebas de contrato añadidas. Publicado, pendiente de validación local; sin store/coordinador/runtime.

## 25. F2.3.15 — Persistencia multiobjetivo

SQLite schema v10 incorpora tablas separadas para operaciones multiobjetivo, idempotencia y targets. El store persiste operación + conjunto completo + clave idempotente en una UoW; replays exactos recuperan la reserva, conflictos semánticos se rechazan y triggers sellan los targets. El ledger de una autoridad permanece intacto. Publicado, pendiente de validación local. No hay claims exclusivos, CAM, fencing, invalidación ni coordinación de fuentes.

## 26. F2.3.16 — Claims exclusivos multiobjetivo

Migración v11 y `SQLiteAuthorityChangeStore.acquire_multi_claims` proporcionan exclusión local por recurso: cada `(authority_kind, authority_id)` solo puede pertenecer a una operación multiobjetivo. El conjunto se adquiere completo bajo `BEGIN IMMEDIATE`; reintentos exactos son idempotentes y conflictos no dejan claims parciales. Los claims quedan ligados a targets de operaciones `REQUESTED` y SQL impide su modificación/eliminación.

No existe todavía liberación: sin recibo durable de reconciliación terminal, liberar por estado sería inseguro. Los claims permanecen retenidos hasta un futuro protocolo coordinado de liberación. Sin CAM, fencing, invalidación, escritura de fuentes ni runtime. Pendiente de suite local.
