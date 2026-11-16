# Atlas Terminal

> Estado: implementación inicial de comandos en la rama `feature/terminal-commands`; pendiente de validación local y merge.
> Registro: 15 de noviembre de 2026.
> Alcance: prototipo funcional de la experiencia conversacional local de Atlas.

## 1. Objetivo

La prioridad inmediata de Atlas es convertir la consola local existente en una experiencia de terminal utilizable, demostrable y verificable. El objetivo no es construir de inmediato toda la plataforma autónoma: primero se debe poder iniciar Atlas, conversar con él, conservar contexto, comprender sus límites y comprobar su comportamiento en sesiones reales.

El desarrollo será incremental. Cada fase debe entregar una capacidad observable, pruebas automatizadas y una verificación manual reproducible antes de comenzar la siguiente.

## 2. Estado actual comprobado en el código

La revisión de `main` (commit `c2803a931b672cbf5c6843eb77816cb4824dd1c4`) confirma:

- Existe una consola local en `src/atlas/adapters/console.py`.
- La composición de ejecución está en `src/atlas/cli.py` y utiliza `AtlasCore`, `ConversationContextProcessor` y `AssistantService`.
- El adaptador de Ollama admite streaming y limita el endpoint a loopback.
- El modelo predeterminado configurado es `gemma4:e2b`; pueden seleccionarse modelo y URL mediante `ATLAS_MODEL` y `ATLAS_OLLAMA_URL`.
- La consola transmite fragmentos de respuesta cuando el runtime ofrece `respond_streaming`.
- El historial actual es `InMemoryConversationHistory`: conserva hasta 8 turnos por conversación y limita cada mensaje histórico a 2.000 caracteres.
- La conversación actual recibe un identificador nuevo al crear `LocalConsoleRequestFactory`; el historial no sobrevive al cierre del proceso.
- El modo `ATLAS_MODE=offline` informa honestamente que no hay un modelo generativo conectado.

La rama `feature/terminal-commands` incorpora `/help`, `/clear` y `/exit`, además de mantener `salir`, `exit` y `quit` como alias de salida. `/clear` limpia la pantalla mediante secuencias ANSI y **no borra ni reinicia el historial de la conversación**. La rama también maneja `Ctrl+C` durante el ciclo de consola. Estas modificaciones todavía requieren ejecución de pruebas y verificación manual en el entorno local; no deben atribuirse a `main` hasta que se integren.

## 3. Principios de implementación

1. **Progreso visible:** priorizar funciones que puedan probarse directamente desde la terminal.
2. **Un incremento por vez:** no mezclar varias fases ni refactorizaciones amplias con nuevas capacidades.
3. **Reutilizar lo que funciona:** extender la composición y los puertos existentes antes de reemplazarlos.
4. **Evidencia antes de avanzar:** ejecutar pruebas focalizadas, suite relevante y una comprobación manual del flujo real.
5. **Estado honesto:** distinguir generación, respuesta informativa, error, propuesta y operación ejecutada.
6. **Control humano:** el modelo no obtiene autoridad por interpretar una solicitud o generar un plan.

## 4. Alcance de la primera versión funcional

La primera versión utilizable de Atlas Terminal debe cubrir:

- Inicio y salida previsibles.
- Interfaz de conversación legible y entrada robusta.
- Recepción progresiva de respuestas mediante streaming.
- Indicadores comprensibles de generación, finalización y error, sin presentar una respuesta incompleta como éxito.
- Comandos de ayuda, limpieza de pantalla/contexto y salida: `/help`, `/clear` y `/exit`.
- Manejo controlado de entrada vacía, EOF, interrupciones y errores del proveedor.
- Pruebas de los comandos y de los caminos de éxito y error.

En esta primera implementación, `/clear` limpia únicamente la pantalla; no crea una conversación nueva ni elimina el contexto en memoria. La gestión de conversaciones pertenece a la fase 2.

## 5. Límites que permanecen vigentes

La prioridad Terminal no elimina los límites arquitectónicos y de seguridad existentes:

- Ollama continúa limitado a loopback; no exponerlo a la red.
- La consola sigue siendo una interfaz conversacional, no un shell de sistema.
- No conceder acceso directo a archivos, SQL, Docker, contenedores ni operaciones privilegiadas.
- No permitir que prompts, modelos, agentes o Skills amplíen sus propios permisos.
- Las capacidades protegidas deben pasar por sus contratos, identidad, autorización y mediación correspondientes.
- No afirmar que una acción se ejecutó si solo se generó texto o un plan.
- No modificar servicios o infraestructura de producción como parte de las pruebas del prototipo sin autorización explícita.

Estos son límites mínimos del prototipo; el trabajo de seguridad avanzada e integración completa se desarrollará en una fase posterior.

## 6. Trabajo temporalmente pausado

- **Atlas Desktop para Windows:** la dirección y decisiones previamente aprobadas se conservan, pero el desarrollo queda pausado.
- **API remota de Atlas Assistant:** queda pausada; no es requisito para demostrar primero la experiencia local de Terminal.
- La pausa no cancela decisiones anteriores ni autoriza a borrar ramas o documentación existentes.

Las ramas de Desktop ya existentes permanecen separadas de `main`; esta prioridad no las fusiona ni modifica.

## 7. Relación con el resto de Atlas

El trabajo de Identity/CAM, Memory Engine, Broker, Skills, proyectos, agentes y Scheduler no se declara cancelado. Se reordena el trabajo inmediato para validar una experiencia Terminal funcional antes de ampliar la superficie de capacidades.

Los contratos existentes siguen siendo normativos. En particular, el contrato de Atlas Assistant (CT-06) mantiene la separación entre inteligencia/coordinación y autoridad para ejecutar operaciones. La integración de MemoryGateway y de herramientas protegidas no debe adelantarse a la disponibilidad de sus fronteras durables y autorizadas.

## 8. Verificación local

Desde la raíz del repositorio:

```bash
PYTHONPATH=src python -m atlas
```

Modo informativo sin proveedor LLM:

```bash
ATLAS_MODE=offline PYTHONPATH=src python -m atlas
```

Suite completa:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

La ejecución manual con un modelo local debe realizarse con Ollama disponible en loopback. No se debe inferir que el modelo está instalado o activo solo por estar configurado como predeterminado.

## 9. Regla de cierre

Una fase se considera completada únicamente cuando:

- La funcionalidad está implementada y documentada.
- Sus pruebas automatizadas pasan.
- Se ha realizado una verificación manual reproducible.
- Los errores y límites conocidos están documentados.
- El README raíz y esta documentación reflejan el estado real.

