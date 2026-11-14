# Atlas

Atlas es un entorno personal de automatización y gestión de proyectos diseñado alrededor de seguridad por defecto, aislamiento, mínimo privilegio, trazabilidad y recuperabilidad.

## Estado actual: F1 funcional

La rama `feature/atlas-functional-f1` incorpora una primera experiencia conversacional local:

- Modelos inmutables `AssistantRequest` y `AssistantResponse`.
- Mensajes históricos neutrales al proveedor mediante `ConversationMessage`.
- Servicio de aplicación que correlaciona solicitudes y respuestas.
- Adaptador de consola desacoplado de la lógica de aplicación.
- Identidad inicial derivada de la cuenta local del sistema.
- Contexto explícito por solicitud y marcas de tiempo UTC.
- Orquestador `AtlasCore` en `atlas.application`, que coordina la creación de solicitudes, el contexto conversacional, el servicio y el streaming.
- Inicio mediante `python -m atlas` o el comando `atlas` tras instalar el paquete.

`src/atlas/core` conserva los contratos fundamentales del dominio (identidad, contexto, errores y enums). No debe confundirse con `AtlasCore`, que es la fachada de orquestación de aplicación en `src/atlas/application/atlas_core.py`.

La consola solo recoge y presenta texto. AtlasCore recibe ese texto, solicita a la fábrica el contexto local, delega en el procesador de contexto conversacional y valida que la respuesta corresponda a la solicitud original. Esta capa no concede permisos, no ejecuta herramientas ni permite que el modelo acceda directamente a archivos o sistemas.

### Contexto conversacional de sesión

`ConversationContextProcessor` enriquece cada solicitud con los turnos anteriores de la misma conversación. El historial se mantiene en `InMemoryConversationHistory`, separado por `conversation_id`, protegido para accesos concurrentes y limitado por cantidad y tamaño:

- Hasta 8 turnos anteriores (16 mensajes: usuario y asistente).
- Hasta 2000 caracteres por mensaje histórico; el contenido más allá del límite se trunca con una marca explícita.
- Solo se guardan turnos cuya respuesta no sea de tipo `ERROR`.
- Las respuestas y solicitudes conservan sus identificadores y contexto originales.
- El historial desaparece al terminar el proceso. No se escribe en disco ni se comparte entre sesiones.

El mensaje de sistema se mantiene al principio del prompt; después se envían los mensajes históricos en orden y, al final, el mensaje actual del usuario. La gestión del historial pertenece a la capa de aplicación, no a Ollama.

Los contratos neutrales para proveedores de modelos (`LLMProvider`, `LLMRequest`, `LLMResponse` y `LLMMessage`) están definidos en `atlas.ports.llm`. No dependen de un SDK ni de un proveedor concreto y no conceden capacidad para ejecutar herramientas.

El adaptador `OllamaProvider` implementa la API local `/api/chat` mediante la biblioteca estándar. Solo acepta endpoints HTTP loopback (`localhost`, `127.0.0.1` o `::1`); no admite proveedores remotos ni proxies del entorno. Soporta tanto respuestas completas como streaming NDJSON.

El puente `OllamaResponseGenerator` conecta el puerto LLM con `AssistantService`. Convierte cada solicitud en mensajes de sistema, historial y mensaje actual, y traduce fallos conocidos de Ollama en respuestas de tipo `ERROR`, sin propagar detalles internos al usuario. El streaming atraviesa proveedor, generador, servicio, contexto conversacional, AtlasCore y consola: los fragmentos se muestran conforme llegan, sin esperar a que termine la generación. Se rechazan flujos que no entreguen el evento final de Ollama.

### Configuración local de la consola

La consola utiliza por defecto:

- Modelo: `gemma4:e2b`.
- Endpoint: `http://127.0.0.1:11434`.
- Streaming: activado.
- Historial de sesión: hasta 8 turnos, 2000 caracteres por mensaje histórico.

Variables opcionales:

- `ATLAS_MODEL`: cambia el tag del modelo local.
- `ATLAS_OLLAMA_URL`: cambia el endpoint; debe seguir siendo loopback.
- `ATLAS_MODE=offline`: inicia el modo informativo sin proveedor LLM.

No se instala, descarga ni inicia Ollama automáticamente. El modelo debe estar instalado en la instancia local de Ollama. No hay memoria conversacional persistente, herramientas, agentes ni conexión con Atlas Broker en esta fase.

El repositorio también contiene módulos de memoria, autorización y proactividad con contratos y pruebas propios. Su presencia no significa que estén integrados en el flujo conversacional de AtlasCore. Esa integración se abordará en etapas posteriores y con límites de seguridad explícitos.

La integración LLM está cubierta por pruebas unitarias con transportes y proveedores simulados; no requiere un servidor Ollama activo.

## Ejecución local

Desde la raíz del repositorio:

```bash
PYTHONPATH=src python -m atlas
```

Para instalar el comando de consola en el entorno activo:

```bash
python -m pip install -e .
atlas
```

Para ejecutar deliberadamente el modo informativo sin modelo:

```bash
ATLAS_MODE=offline PYTHONPATH=src python -m atlas
```

## Pruebas

```bash
PYTHONPATH=src python -m unittest \
  tests.unit.test_assistant_conversation_models \
  tests.unit.test_assistant_service \
  tests.unit.test_assistant_console \
  tests.unit.test_local_console_composition \
  tests.unit.test_llm_contracts \
  tests.unit.test_ollama_adapter \
  tests.unit.test_ollama_assistant \
  tests.unit.test_ollama_streaming \
  tests.unit.test_atlas_core \
  tests.unit.test_conversation_context -v
```

## Próximas etapas

Validar el contexto de sesión con la suite completa y una conversación local real. Después, diseñar la integración controlada de memoria persistente y las políticas de autorización antes de exponer herramientas. Ninguna capacidad futura debe considerarse implementada hasta contar con código y pruebas verificadas.
