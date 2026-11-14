# Atlas

Atlas es un entorno personal de automatización y gestión de proyectos diseñado alrededor de seguridad por defecto, aislamiento, mínimo privilegio, trazabilidad y recuperabilidad.

## Estado actual: F1 funcional

La rama `feature/atlas-functional-f1` incorpora una primera experiencia conversacional local:

- Modelos inmutables `AssistantRequest` y `AssistantResponse`.
- Servicio de aplicación que correlaciona solicitudes y respuestas.
- Adaptador de consola desacoplado de la lógica de aplicación.
- Identidad inicial derivada de la cuenta local del sistema.
- Contexto explícito por solicitud y marcas de tiempo UTC.
- Inicio mediante `python -m atlas` o el comando `atlas` tras instalar el paquete.

Los contratos neutrales para proveedores de modelos (`LLMProvider`, `LLMRequest`, `LLMResponse` y `LLMMessage`) están definidos en `atlas.ports.llm`. No dependen de un SDK ni de un proveedor concreto y no conceden capacidad para ejecutar herramientas.

El adaptador `OllamaProvider` implementa la API local `/api/chat` mediante la biblioteca estándar. Solo acepta endpoints HTTP loopback (`localhost`, `127.0.0.1` o `::1`); no admite proveedores remotos ni proxies del entorno. Soporta tanto respuestas completas como streaming NDJSON.

El puente `OllamaResponseGenerator` conecta el puerto LLM con `AssistantService`. Convierte cada solicitud en mensajes de sistema y usuario y traduce fallos conocidos de Ollama en respuestas de tipo `ERROR`, sin propagar detalles internos al usuario. El streaming atraviesa proveedor, generador, servicio y consola: los fragmentos se muestran conforme llegan, sin esperar a que termine la generación. Se rechazan flujos que no entreguen el evento final de Ollama.

### Configuración local de la consola

La consola utiliza por defecto:

- Modelo: `gemma4:e2b`.
- Endpoint: `http://127.0.0.1:11434`.
- Streaming: activado.

Variables opcionales:

- `ATLAS_MODEL`: cambia el tag del modelo local.
- `ATLAS_OLLAMA_URL`: cambia el endpoint; debe seguir siendo loopback.
- `ATLAS_MODE=offline`: inicia el modo informativo sin proveedor LLM.

No se instala, descarga ni inicia Ollama automáticamente. El modelo debe estar instalado en la instancia local de Ollama. No hay memoria conversacional persistente, herramientas, agentes ni conexión con Atlas Broker en esta fase.

La integración está cubierta por pruebas unitarias con transportes y proveedores simulados; no requiere un servidor Ollama activo.

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
  tests.unit.test_ollama_streaming -v
```

## Próximas etapas

Verificar la integración con una instancia Ollama local y el modelo configurado. Posteriormente, diseñar historial/memoria y herramientas bajo autorización explícita. Ninguna capacidad futura debe considerarse implementada hasta contar con código y pruebas verificadas.
