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

El adaptador `OllamaProvider` implementa el contrato usando la API local `/api/chat`, transporte HTTP de la biblioteca estándar e inyección de transporte para pruebas. Solo acepta endpoints HTTP en `localhost` o direcciones loopback; no admite proveedores remotos.

El adaptador está implementado, pero **todavía no está conectado a la consola ni al servicio conversacional**. Tampoco están conectados memoria, herramientas, agentes ni Atlas Broker. La respuesta actual de la consola sigue siendo deliberadamente informativa y no simula comprensión generativa ni ejecución de tareas.

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

## Pruebas

```bash
PYTHONPATH=src python -m unittest \
  tests.unit.test_assistant_conversation_models \
  tests.unit.test_assistant_service \
  tests.unit.test_assistant_console \
  tests.unit.test_local_console_composition \
  tests.unit.test_llm_contracts \
  tests.unit.test_ollama_adapter \\\n  tests.unit.test_ollama_assistant -v
```

## Próximas etapas

Conectar el adaptador Ollama al servicio conversacional y, posteriormente, integrar memoria y herramientas bajo autorización explícita. Ninguna de estas capacidades futuras debe considerarse implementada hasta contar con código y pruebas verificadas.
