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

## 6. Servicio de aplicación para workspace.list (F2.2)

El caso de uso se mantiene separado del adaptador:

```text
Solicitud de aplicación
        |
        v
WorkspaceListingService
        |
        v
WorkspaceReader (puerto)
        |
        v
LocalWorkspaceAdapter
        |
        v
WorkspaceListing
```

- El servicio recibe un lector inyectado; no recibe rutas del modelo ni conoce el sistema de archivos.
- Valida que `workspace_id` sea texto no vacío.
- Comprueba que el adaptador devuelva `WorkspaceListing` y que el ID del resultado coincida con el solicitado.
- Propaga errores de dominio, como `NotFoundError`, sin transformarlos en éxitos.
- Incluye prueba de integración unitaria del servicio con el adaptador local y fixtures temporales.
- No se integra todavía en `bootstrap.py`, `cli.py` ni el runtime conversacional.

## 7. Diseño funcional incremental

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

## 8. Pruebas mínimas por incremento

- Unitarias: validación de intención, parámetros, plan, transiciones de tarea y resultado del adaptador.
- Integración: repositorio SQLite de tareas con base temporal.
- Workspace: listado y lectura sobre fixtures; ruta inexistente y workspace vacío.
- Consola: plan, confirmación, resultado y error observable.
- Regresión: ejecutar la suite completa vigente y registrar el total validado por el propietario.

No se marcará F1–F5 como completada hasta ejecutar las pruebas en el entorno local del propietario y comprobar el flujo vertical real.

## 9. Estado F0

**Inspección estática realizada:** composition root, fachada AtlasCore, AssistantService, generador Ollama, proyección de contexto, gestor de conversaciones y consola.

**Pendiente para cerrar F0 con evidencia local:** comprobar que el checkout Debian está en el mismo commit/branch y ejecutar la suite de regresión antes de introducir cambios de código.

**Estado actual:** F1.1–F1.5 están implementadas y el propietario validó Gemma real más 886/886 pruebas. F2.1 (contrato y adaptador local) fue validada con 893/893 pruebas. F2.2 añade `WorkspaceListingService`; su validación local está pendiente. Ninguna de estas capacidades está conectada todavía a `cli.py` ni al runtime conversacional.
