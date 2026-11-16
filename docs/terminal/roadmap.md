# Hoja de ruta — Atlas Terminal-first

> Prioridad aprobada para la siguiente etapa de desarrollo.
> Registro: 15 de noviembre de 2026.
> Las fases describen objetivos futuros; no implican que estén implementados.

## Orden de trabajo

| Fase | Objetivo | Resultado esperado |
|---|---|---|
| 1 | Experiencia Terminal | Consola conversacional estable y utilizable |
| 2 | Conversaciones | Contexto administrable y persistencia local |
| 3 | Inteligencia | Comportamiento del modelo evaluado de forma reproducible |
| 4 | Capacidades del Assistant | Planificación y herramientas integradas gradualmente |
| 5 | Consolidación | Integración, pruebas y preparación para ampliar el sistema |

Las fases se ejecutan secuencialmente. No se inicia una fase nueva hasta validar los criterios de salida de la anterior, salvo que una corrección necesaria de la fase anterior lo requiera.

## Fase 1 — Experiencia Terminal

**Objetivo:** convertir la consola actual en una interfaz conversacional consistente.

### Trabajo previsto

1. Revisar el ciclo de vida de `run_console` y la composición de `cli.main`.
2. Mejorar el formato de entrada/salida y la legibilidad de respuestas progresivas.
3. Incorporar estados visibles de generación, finalización y error.
4. Implementar `/help`, `/clear` y `/exit`, manteniendo compatibilidad razonable con los comandos de salida actuales.
5. Manejar entrada vacía, EOF, interrupciones y errores de Ollama sin dejar la interfaz en un estado confuso.
6. Mantener el streaming existente y verificar que el texto parcial no se presente como respuesta exitosa si el proveedor falla.
7. Actualizar documentación de uso y ejemplos.

### Criterios de salida

- Inicio y salida funcionan de forma predecible.
- Los tres comandos están documentados y probados.
- Las respuestas se muestran progresivamente cuando el proveedor lo permite.
- Los errores del proveedor se distinguen de las respuestas normales.
- EOF e interrupciones tienen un comportamiento definido.
- Las pruebas focalizadas y la suite completa pasan.
- Se completa una sesión manual real con Ollama local y una sesión en modo offline.

### No incluido

Persistencia durable, gestor de conversaciones, ejecución de herramientas, API remota o interfaz gráfica.

## Fase 2 — Gestión de conversaciones

**Objetivo:** pasar del historial temporal de una sola sesión a conversaciones que el usuario pueda administrar.

### Trabajo previsto

1. Definir operaciones de crear, listar, seleccionar, renombrar y cerrar conversaciones.
2. Definir el comportamiento exacto de limpiar pantalla frente a iniciar una conversación nueva.
3. Diseñar persistencia local y versionado del esquema antes de implementarlos.
4. Sustituir `InMemoryConversationHistory` por un adaptador durable detrás de `ConversationHistoryStore`.
5. Mantener límites explícitos de tamaño, número de turnos y recuperación.
6. Definir política de eliminación, exportación y respaldo antes de almacenar contenido conversacional de forma permanente.
7. Añadir pruebas de reinicio del proceso, aislamiento entre conversaciones e integridad de datos.

### Criterios de salida

- Una conversación puede recuperarse después de cerrar y volver a abrir Atlas.
- El historial de una conversación no aparece en otra.
- Las operaciones de gestión tienen comportamiento y errores definidos.
- Los límites y la política de retención están documentados.
- Migraciones, integridad y recuperación están probadas con bases temporales.

## Fase 3 — Inteligencia y comportamiento

**Objetivo:** evaluar y mejorar la calidad del Assistant sin confundir fluidez con fiabilidad.

### Trabajo previsto

1. Crear un conjunto reproducible de casos de prueba conversacionales.
2. Comparar Gemma 4 E2B y otros modelos candidatos con las mismas entradas y parámetros documentados.
3. Ejecutar pruebas A/B de instrucciones equivalentes en inglés y español.
4. Incluir casos de seguimiento de instrucciones, contexto, ambigüedad, incertidumbre, errores y prompt injection.
5. Evaluar por separado la calidad de respuesta, cumplimiento de límites y honestidad sobre capacidades.
6. Registrar modelo, versión/tag, parámetros, prompt, entradas y resultados para poder repetir las pruebas.
7. Ajustar instrucciones del sistema solo a partir de resultados comparables.

### Criterios de salida

- Existe un conjunto de evaluación versionado.
- Las comparaciones usan condiciones equivalentes.
- Los resultados y fallos son reproducibles y documentados.
- Ningún modelo se considera seguro por una prueba aislada o por responder bien en conversación ordinaria.
- El Assistant conserva la distinción entre sugerir, planificar y ejecutar.

## Fase 4 — Capacidades del Assistant

**Objetivo:** evolucionar de conversación a coordinación controlada, sin otorgar autoridad directa al modelo.

### Trabajo previsto

1. Mejorar la clasificación de intenciones y la identificación de información faltante.
2. Permitir que el Assistant estructure planes y explique sus pasos y supuestos.
3. Definir contratos de herramientas y capacidades antes de conectar adaptadores.
4. Integrar una herramienta de bajo riesgo por vez, con pruebas de autorización y resultados.
5. Enrutar solicitudes protegidas a los componentes responsables y sus fronteras de autorización.
6. Mantener aprobación humana para operaciones sensibles o no delegables.
7. Registrar correlación entre solicitud, plan, decisión, autorización, ejecución y resultado cuando corresponda.

### Criterios de salida

- Cada herramienta tiene contrato, alcance y errores definidos.
- La autorización se decide fuera del modelo y se aplica en el componente responsable.
- Una instrucción del usuario o del modelo no puede ampliar permisos por sí misma.
- Los resultados inciertos no se comunican como éxitos.
- Las pruebas cubren denegaciones, fallos, reintentos y resultados desconocidos.

### No incluido por defecto

Acceso general al shell, ejecución arbitraria de comandos, acceso irrestricto a archivos, SQL o Docker. Cualquier capacidad de ese tipo requiere diseño, autorización y controles específicos; no forma parte automática del prototipo Terminal.

## Fase 5 — Consolidación

**Objetivo:** demostrar que el prototipo y sus integraciones funcionan de manera coherente y están preparados para ampliar su alcance.

### Trabajo previsto

1. Ejecutar pruebas unitarias, de integración y de regresión.
2. Validar persistencia, recuperación, límites de conversación y manejo de fallos.
3. Completar la integración con Identity/CAM y los componentes protegidos que estén realmente listos.
4. Reforzar autenticación, autorización, aislamiento, auditoría y ciclo de vida de credenciales según el alcance aprobado.
5. Revisar dependencias, configuración, registros y manejo de datos sensibles.
6. Documentar instalación, configuración, operación, diagnóstico y recuperación.
7. Revaluar el orden para reanudar Desktop/API y el resto de los subsistemas de Atlas.

### Criterios de salida

- Flujos principales y fallos están cubiertos por pruebas repetibles.
- No hay capacidades declaradas que no estén demostradas.
- Las fronteras de identidad, autorización y ejecución son verificables.
- La recuperación y el comportamiento ante resultados inciertos están documentados y probados.
- Se aprueba explícitamente el siguiente alcance de producto.

## Cadencia obligatoria para cada incremento

1. Inspeccionar el código y las pruebas actuales.
2. Identificar un único cambio pequeño y su criterio de aceptación.
3. Implementar sin reescribir componentes que ya funcionan.
4. Ejecutar pruebas focalizadas.
5. Ejecutar la suite relevante y, cuando corresponda, la suite completa.
6. Probar el comportamiento real desde la terminal.
7. Revisar errores, regresiones y límites.
8. Actualizar README y documentación de fase.
9. Registrar qué quedó implementado, qué sigue pendiente y la evidencia obtenida.

No declarar una fase terminada por haber creado interfaces, contratos, clases o pruebas aisladas: se requiere una composición ejecutable y evidencia del comportamiento real.

## Prioridades en pausa

### Desktop para Windows

Se conserva la dirección previamente aprobada (C#/.NET/WinUI 3, conexión futura mediante API remota, Tailscale y HTTPS/TLS, vinculación explícita de dispositivos y permisos limitados). El desarrollo queda pausado hasta que la prioridad Terminal alcance una versión funcional y se decida reanudarlo.

### API remota

La API remota para Desktop también queda pausada. No se construirá como requisito previo de las fases 1–3; cualquier necesidad de API se evaluará cuando se retome el cliente remoto.

### Seguridad avanzada

Se posterga la expansión de seguridad avanzada para una fase posterior, pero no se eliminan las protecciones mínimas existentes. Se mantienen loopback para Ollama, separación entre conversación y ejecución, ausencia de acceso privilegiado directo y control humano sobre acciones sensibles. No se habilitarán herramientas privilegiadas como atajo para demostrar funcionalidad.

## Relación con la hoja de ruta general de Atlas

Esta hoja de ruta cambia el **orden de prioridad inmediata**, no cancela los dominios de Atlas ni modifica sus contratos. El trabajo de Memory Engine, Identity/CAM, Project/Environment Manager, Skills Manager, agentes, Scheduler, aprobaciones, eventos, notificaciones, Backup/Restore y recuperación continúa como trabajo pendiente o parcialmente implementado según el README raíz.

La integración del Assistant con memoria protegida y herramientas debe respetar CT-06 y esperar a que las fronteras de autorización, persistencia y recuperación correspondientes estén listas. Cuando Terminal esté validado, se revisará la secuencia global y se decidirá qué subsistema retomar.

