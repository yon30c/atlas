# Atlas

Atlas es un asistente modular en Python. Esta etapa establece contratos y modelos del núcleo; todavía no conecta servicios ni infraestructura.

## Etapa 0

- La identidad y el contexto de operación son explícitos.
- Todo acceso a memoria pasa por `MemoryGateway`; los módulos Assistant y Proactivity solo dependen de su puerto.
- Autorización, persistencia de eventos y reloj son puertos, sin adaptadores concretos.
- Los modelos son inmutables cuando representan datos de dominio.
- No se incluyen base de datos, API, framework web, LLM, Cognee, Telegram ni Broker.

La versión mínima declarada (`Python >=3.10`) es provisional mientras el proyecto confirma su política de runtimes. No se usa una librería externa de validación en esta etapa; los contratos aplican comprobaciones básicas de la biblioteca estándar.

## Desarrollo

Instala el proyecto en modo editable con `python -m pip install -e .` y ejecuta las pruebas con `python -m unittest discover -s tests -v`.