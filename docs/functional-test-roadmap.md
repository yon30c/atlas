# Atlas funcional de prueba — plan de trabajo

> Prioridad acordada: 16 de noviembre de 2026.
> Rama de trabajo: `feature/terminal-commands`.
> Objetivo: convertir la base conversacional existente en un asistente local capaz de completar flujos útiles de principio a fin en un entorno de prueba.
> Este plan no declara Atlas listo para producción.

## 1. Dirección del producto

La prioridad inmediata ya no es continuar ampliando el endurecimiento avanzado de seguridad de la Fase 3. Esa evaluación queda pausada, con sus resultados y pendientes preservados en [Fase 3 — Inteligencia y comportamiento seguro](phase-3-intelligence.md).

El objetivo es tener un Atlas que pueda:

1. Entender una solicitud práctica del propietario.
2. Identificar el objetivo y los datos que falten.
3. Proponer un plan comprensible.
4. Usar capacidades concretas disponibles en el entorno de prueba.
5. Ejecutar el flujo de trabajo mediante componentes de aplicación, no fingiendo que lo hizo.
6. Mostrar el resultado real y permitir verificarlo.
7. Conservar el contexto conversacional y el estado necesario para continuar.

"100% funcional de prueba" significa que el conjunto de escenarios de prueba definidos puede completarse de extremo a extremo en el entorno local previsto. No significa que todos los dominios futuros de Atlas estén implementados ni que el sistema esté listo para producción.

## 2. Base existente verificada

### Funcional en la rama actual

- Consola local ejecutable mediante `python -m atlas`.
- Integración conversacional con Ollama; modelo predeterminado `gemma4:e2b`.
- Streaming de respuestas.
- Modo offline informativo.
- AtlasCore y AssistantService conectados en la composición de consola.
- Persistencia SQLite de conversaciones y mensajes.
- Recuperación de la conversación activa al reiniciar.
- Crear, listar, seleccionar, renombrar, cerrar y eliminar conversaciones.
- Exportación JSON versionada.
- Backup cifrado, verificación y restauración a una ruta nueva.
- Contexto enviado al modelo limitado a ocho turnos y 2.000 caracteres por mensaje, sin truncar el historial almacenado.
- Suite local reportada por el propietario: 852/852 pruebas aprobadas tras integrar los contratos F1.1 (16 de noviembre de 2026).

### Infraestructura parcial, no producto integrado

- Identity/CAM: modelos, servicios y persistencia local parcial.
- Memory Engine: dominio, gateway, journal, checkpoints, recuperación local y reducers parciales; no tiene persistencia durable completa del contenido ni composición protegida integral.
- Broker: desarrollo separado; no asumir que está integrado en el runtime de Assistant.
- P3-SR: harness aislado de evaluación, no runtime de herramientas.

### Aún no disponible como flujo funcional de usuario

- Interpretación de intenciones y planes de tareas como capacidad integrada del Assistant.
- Registro operativo y ciclo de vida de proyectos.
- Herramientas de proyecto integradas al Assistant.
- Ejecución y seguimiento de tareas.
- Scheduler y recuperación de trabajos.
- Skills instalables y administrables.
- Agentes especializados coordinados.
- Memoria de producto integrada a la conversación.
- Aprobaciones, eventos y notificaciones integrados.
- Una experiencia funcional de extremo a extremo que conecte estos componentes.

## 3. Alcance de la primera versión funcional de prueba

Construir primero un ciclo completo pequeño y verificable, sin intentar implementar todos los subsistemas de la visión simultáneamente.

### Flujo objetivo

1. El usuario solicita una tarea concreta.
2. Atlas interpreta la intención y solicita aclaraciones solo cuando sean necesarias.
3. Atlas genera un plan estructurado con pasos y parámetros.
4. La aplicación valida que el plan corresponde a una capacidad disponible.
5. El usuario puede revisar el plan antes de continuar cuando el flujo lo requiera.
6. Un adaptador de prueba ejecuta la operación dentro de un workspace local dedicado.
7. Atlas recoge el resultado real del adaptador.
8. Atlas resume qué ocurrió, qué falló y qué quedó pendiente.
9. El resultado y la interacción quedan asociados a la conversación.

### Primeras capacidades candidatas

- Consultar información y estado de proyectos registrados en el entorno de prueba.
- Listar archivos dentro de un workspace de prueba.
- Leer archivos seleccionados dentro de ese workspace.
- Crear o actualizar archivos de prueba con contenido explícito.
- Ejecutar tareas de aplicación previamente definidas y no comandos arbitrarios.
- Consultar el estado y resultado de una tarea.
- Continuar una tarea conversacional usando el historial persistente.

El conjunto exacto de operaciones se define al inspeccionar los módulos existentes y antes de implementar cada adaptador. No se debe asumir que un contrato experimental de P3-SR sea ya una herramienta disponible en el producto.

## 4. Fases de implementación funcional

### F0 — Mapa de composición y contrato de producto

**Estado: inspección estática documentada; cierre pendiente de verificación local del checkout y regresión.** Mapa: [docs/functional-architecture-map.md](functional-architecture-map.md).

- Inspeccionar la estructura real de paquetes, servicios, puertos, adaptadores y pruebas.
- Identificar qué componentes se pueden reutilizar sin duplicación.
- Definir los casos de uso de prueba y sus entradas/salidas.
- Definir una composición local de dependencias clara.
- Registrar las capacidades que estarán disponibles y las que todavía no.

**Criterio de salida:** mapa de módulos y primer conjunto de casos de uso aprobado antes de añadir nuevas capas.

### F1 — Interpretación y planificación

**Estado:** F1.1 (contratos de intención/plan) integrado. F1.2 incluye parser JSON estricto y adaptador `OllamaIntentInterpreter` separado del flujo conversacional. El propietario validó 866/866 pruebas y confirmó con Gemma `gemma4:e2b-it-q4_K_M` los cuatro resultados esperados usando `OllamaProvider(think=False, response_format="json")`. F1.3 añade `AssistantPlanningService`; el propietario validó 875/875 pruebas. F1.4 añade `AssistantRequestPlanner` y `RequestPlanningResult`; el propietario validó 882/882 pruebas. F1.5 añade `build_request_planner` en `atlas.bootstrap`. El propietario validó la composición con Gemma real y 886/886 pruebas. F1 queda completada para el primer catálogo `workspace.list` y `workspace.read`; no hay ejecución de capacidades integrada todavía.

- Clasificar la solicitud en una intención de producto.
- Extraer parámetros y detectar datos faltantes.
- Crear un plan estructurado con pasos, dependencias y resultado esperado.
- Explicar al usuario qué hará Atlas antes de ejecutar el flujo.
- Manejar solicitudes no soportadas sin inventar capacidades.

**Criterio de salida:** casos de prueba de intención, aclaración y planificación pasan con el modelo local y validación de aplicación.

### F2 — Capacidades y herramientas de prueba

**Estado:** F2.1 fue validada con 893/893 pruebas. F2.2 añade `WorkspaceListingService`, que consume `WorkspaceReader`, valida el ID y verifica el tipo y la correspondencia del resultado. El propietario validó F2.2 y la regresión completa con 900/900 pruebas (16 de noviembre de 2026). F2.3 documenta la frontera entre revisión del plan, autorización CAM y aprobación humana en [F2.3 — Frontera de autorización, revisión y ejecución](design/assistant-workspace-execution-boundary.md). Es un diseño, no una implementación: no hay todavía autorización genérica pública, Approval Manager integrado ni ejecución desde consola/runtime.

- Definir un catálogo pequeño de capacidades reales.
- Implementar adaptadores concretos para el workspace de prueba.
- Conectar cada capacidad a un servicio de aplicación.
- Validar entradas y devolver resultados estructurados.
- Distinguir errores, resultados parciales y éxito real.
- Mantener el workspace de prueba separado de datos personales y del sistema.

**Criterio de salida:** Atlas completa operaciones de lectura y escritura de prueba y presenta resultados comprobables.

### F3 — Ejecución y seguimiento de tareas

- Introducir una entidad de tarea con identificador, estado, pasos, fechas y resultados.
- Ejecutar tareas de forma secuencial al principio.
- Registrar inicio, progreso, éxito, error y cancelación.
- Permitir consultar el estado de una tarea.
- Reanudar o cerrar correctamente tareas interrumpidas, según el alcance acordado.

**Criterio de salida:** un flujo de varios pasos puede iniciarse, seguirse y terminar con resultados persistentes.

### F4 — Contexto y continuidad

- Usar conversaciones persistentes ya implementadas.
- Definir qué estado de tarea debe sobrevivir a un reinicio.
- Conectar memoria de producto solo cuando su persistencia real esté disponible.
- Evitar duplicar información entre historial conversacional y estado de tarea.

**Criterio de salida:** Atlas puede continuar una tarea de prueba después de cerrar y volver a iniciar la consola.

### F5 — Experiencia integrada de prueba

- Mejorar comandos y mensajes de estado.
- Añadir ayuda contextual sobre capacidades disponibles.
- Mostrar planes, progreso, resultados y errores de manera consistente.
- Preparar escenarios completos reproducibles.
- Ejecutar pruebas unitarias, de integración y manuales de extremo a extremo.

**Criterio de salida:** todos los escenarios de aceptación definidos para la versión de prueba se completan en un entorno limpio siguiendo la documentación.

## 5. Escenarios de aceptación iniciales

1. Iniciar Atlas y establecer conversación con Ollama.
2. Crear una conversación, cerrarla y recuperar su historial después de reiniciar.
3. Pedir a Atlas que liste los proyectos disponibles en el entorno de prueba.
4. Pedir que inspeccione un workspace de prueba y resuma su contenido.
5. Pedir que cree un archivo de ejemplo con contenido especificado.
6. Pedir que lea el archivo creado y verifique su contenido.
7. Solicitar una tarea de varios pasos y consultar su progreso.
8. Provocar un error controlado y comprobar que Atlas lo comunica sin afirmar éxito.
9. Interrumpir y reiniciar Atlas y comprobar el estado durable que corresponda.
10. Exportar y respaldar la conversación, verificar el respaldo y restaurarlo a una ruta nueva.

Los escenarios se ampliarán conforme existan capacidades implementadas. No se marcará un escenario como aprobado sin evidencia real de ejecución.

## 6. Reglas de desarrollo para esta etapa

- Trabajar sobre la rama `feature/terminal-commands`.
- Inspeccionar el código y las pruebas existentes antes de crear módulos nuevos.
- Reutilizar componentes funcionales y evitar reescrituras amplias.
- Implementar un incremento pequeño por vez.
- Probar primero el caso focalizado y luego ejecutar la suite relevante.
- Verificar el comportamiento desde la terminal con resultados observables.
- No declarar funcional una capacidad por tener únicamente modelos, contratos, prompts o mocks.
- Separar el modelo generativo de los componentes que realizan operaciones.
- Usar un workspace de prueba con datos descartables para validar los flujos.
- Mantener las protecciones mínimas existentes y no convertir la pausa de seguridad en permiso para habilitar shell arbitrario, acceso root o ejecución irrestricta.
- No conectar todavía el harness P3-SR ni sus propuestas experimentales al runtime del producto.

## 7. Seguridad avanzada en pausa

La evaluación avanzada de la Fase 3 queda pausada hasta nueva indicación. No dedicar los siguientes incrementos a mejorar prompts de inyección, reconocimiento semántico, matrices de idioma, criterios adversariales o hardening adicional.

Se preservan:
- Los resultados históricos de P3-PI-001 y P3-PI-002.
- El corpus P3-SR de nueve casos.
- La comparación A/B `default` / `schema_only`.
- La evidencia local de 9/9 en una pasada con `schema_only` y 5/5 en SR-008.
- La revisión pendiente de SR-006 y las limitaciones conocidas.

La pausa no cambia el hecho de que el runtime conversacional actual no tiene herramientas. Tampoco autoriza a desplegar capacidades privilegiadas o a tratar propuestas del harness como autorizaciones.

## 8. Forma de trabajo

Para cada siguiente incremento:

1. Inspeccionar archivos relevantes en GitHub y confirmar el estado de la rama.
2. Explicar el objetivo y el comportamiento esperado.
3. Identificar archivos que se modificarán y posibles regresiones.
4. Realizar un cambio acotado.
5. Proporcionar comandos exactos para que el propietario ejecute las pruebas en Debian.
6. Revisar los resultados antes de continuar.
7. Actualizar esta documentación con evidencia, commit y estado real.

**Siguiente acción:** diseñar el contrato genérico de evidencia de autorización de operación en CAM, con pruebas negativas y sin modificar el runtime. Después definir la interfaz de aprobación humana y el gate de aplicación para `workspace.list`. No integrar consola ni ejecutar capacidades hasta validar esos contratos.
