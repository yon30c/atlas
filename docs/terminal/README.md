# Atlas Terminal

> Estado consolidado del proyecto: [Estado vigente de Atlas](../status-current.md).

> Estado: **la base conversacional está integrada en `main`**. La rama `work/atlas-mvp-runtime` añade `/plan` como vista previa; este incremento está pendiente de validación local.
> Última validación automatizada de la base Terminal: 16 de noviembre de 2026, commit `610f027f1fe91933278e431d8a9ec29dd291b96e`. Esta evidencia no cubre los cambios nuevos de `/plan`.
> Alcance: experiencia conversacional local, persistencia y administración de conversaciones, más vista previa de planes en la rama de MVP. No equivale todavía al runtime autónomo completo.

## 1. Objetivo

Atlas Terminal es la primera superficie funcional de Atlas. Permite iniciar el Assistant local, conversar con un modelo local cuando Ollama está disponible, conservar conversaciones entre ejecuciones y administrar su ciclo de vida. Esta implementación es software funcional en evolución, no una demostración estática ni la totalidad de la visión de Atlas.

El desarrollo sigue siendo incremental: cada capacidad se inspecciona, implementa, prueba y documenta antes de ampliar el alcance.

## 2. Estado funcional comprobado

La rama `feature/terminal-commands` contiene:

- Consola local y composición ejecutable desde `src/atlas/cli.py`.
- AssistantService, AtlasCore y ConversationContextProcessor conectados en el arranque.
- Adaptador Ollama para `/api/chat`, streaming y validación del endpoint para loopback.
- Modo `ATLAS_MODE=offline`, que permite iniciar la consola sin proveedor generativo y comunica esa limitación.
- Comandos de terminal `/help`, `/clear` y `/exit`; `salir`, `exit` y `quit` siguen siendo alias de salida.
- En `work/atlas-mvp-runtime`, comando `/plan <solicitud>` conectado al planificador F1; solo genera una vista previa y permanece pendiente de validación local.
- Manejo de EOF e interrupciones de consola.
- Persistencia SQLite durable de conversaciones, metadatos, mensajes y referencia a la conversación activa.
- Recuperación de la conversación activa al iniciar Atlas.
- Gestión de conversaciones: crear, listar, seleccionar, renombrar, cerrar y eliminar con confirmación.
- Proyección acotada al modelo: últimos 8 turnos y máximo 2.000 caracteres por mensaje histórico. El almacenamiento conserva el historial íntegro.
- Exportación JSON versionada de conversaciones.
- Respaldo cifrado, verificación de autenticidad e integridad y restauración a una ruta nueva.
- Pruebas de repositorio y gestor, incluidos rollback transaccional y reemplazo de conversación activa después de eliminarla.

## 3. Persistencia y seguridad local

La base de conversaciones está separada de la base de autoridad:

`~/.local/state/atlas/conversations.sqlite3`

- Directorio dedicado con permisos `0700`.
- Archivo SQLite con permisos `0600`.
- La base puede seleccionarse mediante `ATLAS_CONVERSATION_DB` o el argumento `conversation_db_path` de `main()`.
- El historial íntegro permanece almacenado; los límites de 8 turnos y 2.000 caracteres se aplican únicamente al contexto enviado al modelo.
- Si el almacenamiento no puede prepararse o abrirse, Atlas falla al iniciar; no degrada silenciosamente a memoria.
- No hay sincronización externa ni respaldos automáticos.

El modelo no recibe herramientas ni autoridad para ejecutar acciones. La consola no es un shell y no ofrece acceso directo a archivos, SQL, Docker, contenedores o capacidades privilegiadas.

## 4. Comandos

Los comandos de conversaciones y sus políticas están documentados en [Conversaciones locales](../conversations.md).

| Comando | Función |
|---|---|
| `/help` | Muestra ayuda |
| `/plan <solicitud>` | En `work/atlas-mvp-runtime`: prepara y muestra un plan; no ejecuta operaciones ni accede a archivos |
| `/clear` | Limpia la pantalla; no borra el historial |
| `/exit` | Sale de Atlas |
| `/new [título]` | Crea y selecciona una conversación |
| `/conversations [--all]` | Lista conversaciones |
| `/use ID` | Selecciona una conversación |
| `/rename título` | Renombra la activa |
| `/close` | Cierra la activa y crea otra |
| `/delete ID CONFIRM` | Elimina conversación y mensajes |
| `/export [ID] "ruta"` | Exporta el historial a JSON |
| `/backup "ruta"` | Crea respaldo cifrado |
| `/verify-backup "ruta"` | Verifica un respaldo |
| `/restore-backup "respaldo" "nueva-db"` | Restaura a una ruta nueva |

## 5. Evidencia de validación local

El 16 de noviembre de 2026, en Debian, con el entorno virtual del proyecto activado, el usuario ejecutó:

```text
python -m unittest tests.unit.test_conversation_deletion -v
Ran 6 tests ... OK

python -m unittest discover -s tests -v
Ran 844 tests ... OK
```

Resultado: **6/6 pruebas focalizadas y 844/844 pruebas de la suite completa aprobadas**. Las pruebas de eliminación usan almacenamiento temporal; no modifican la base personal de conversaciones.

También se habían realizado comprobaciones manuales locales de persistencia, backup, verificación, restauración, exportación y eliminación usando bases/rutas temporales. Estas evidencias no deben confundirse con una validación de despliegue productivo ni con CI de GitHub Actions.

## 6. Límites actuales

- La experiencia conversacional local funciona, pero no es todavía un agente con ejecución general de tareas.
- `/plan` está disponible únicamente en la rama `work/atlas-mvp-runtime` hasta que se integre; es una vista previa, no una autorización ni una ejecución.
- El Assistant no tiene acceso directo al shell, archivos, SQL, Docker ni herramientas privilegiadas.
- La integración con Ollama requiere que el servicio y el modelo estén instalados y disponibles localmente; Atlas no los instala ni inicia automáticamente.
- El modo offline es informativo y no genera respuestas mediante un LLM.
- Las conversaciones se almacenan localmente; no existe sincronización multi-dispositivo.
- La exportación JSON no está cifrada.
- La eliminación de una conversación no garantiza borrado forense de bloques liberados ni elimina copias dentro de respaldos previos.
- La persistencia conversacional no equivale a persistencia del Memory Engine.
- Las capacidades de Identity/CAM y Memory Engine no se consideran integradas de extremo a extremo en el flujo de conversación.

## 7. Relación con la visión general de Atlas

Atlas Terminal es una parte funcional de una plataforma mayor. Identity/CAM, Memory Engine, Broker, Skills, gestión de proyectos, agentes, Scheduler, aprobaciones, eventos, notificaciones y ejecución mediada continúan desarrollándose según sus propios contratos y estados. No se debe presentar un contrato, modelo o prueba aislada como un subsistema operativo completo.

La prioridad Terminal ordena el trabajo inmediato; no cancela la visión ni los demás dominios. La integración de memoria protegida y herramientas debe esperar a que sus fronteras durables y autorizadas estén listas.

## 8. Ejecución local

Desde la raíz del repositorio, con el entorno virtual activado:

```bash
source .venv/bin/activate
python -m atlas
```

Modo offline:

```bash
ATLAS_MODE=offline python -m atlas
```

Instalación editable si el entorno todavía no tiene el paquete instalado:

```bash
python -m pip install -e .
```

Configuración principal:

- `ATLAS_MODEL`: tag del modelo local; predeterminado `gemma4:e2b`.
- `ATLAS_OLLAMA_URL`: endpoint Ollama; predeterminado `http://127.0.0.1:11434`.
- `ATLAS_MODE=offline`: inicia el modo informativo sin LLM.
- `ATLAS_CONVERSATION_DB`: selecciona una base de conversaciones alternativa.

## 9. Próximo trabajo

La prioridad actual es construir un Atlas funcional de prueba, evolucionando desde la conversación hacia flujos locales completos: interpretación, planificación, capacidades concretas, ejecución de tareas y resultados verificables. El plan y sus criterios de aceptación están en [Atlas funcional de prueba](../functional-test-roadmap.md). El endurecimiento avanzado de seguridad de la Fase 3 queda pausado por decisión del propietario y se retomará más adelante. Se conservan las protecciones mínimas existentes; no se habilita shell arbitrario ni se conectan propuestas experimentales del harness al runtime.
