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

Esta etapa **todavía no conecta un LLM, memoria, herramientas, agentes ni Atlas Broker**. La respuesta actual es deliberadamente informativa y declara esa limitación; no simula comprensión generativa ni ejecución de tareas.

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
  tests.unit.test_local_console_composition -v
```

## Próximas etapas

Avanzar incrementalmente: validar la composición local, definir el proveedor de modelo detrás de una interfaz neutral y, posteriormente, integrar memoria y herramientas bajo autorización explícita. Ninguna de estas capacidades futuras debe considerarse implementada hasta contar con código y pruebas verificadas.
