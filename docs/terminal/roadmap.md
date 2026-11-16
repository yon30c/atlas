# Hoja de ruta — Atlas Terminal-first

> Prioridad aprobada para la etapa actual de Atlas.
> Última actualización: 16 de noviembre de 2026.
> La hoja de ruta describe la evolución de un Atlas funcional; no reduce el producto a un prototipo ni afirma que todos los subsistemas de la visión estén terminados.

## Orden de trabajo

| Fase | Objetivo | Estado |
|---|---|---|
| 1 | Experiencia Terminal | Implementada y validada en el alcance actual |
| 2 | Conversaciones | Implementada; suite local completa aprobada |
| 3 | Inteligencia y comportamiento seguro | En curso: Gemma 4 E2B ya seleccionado; validación de instrucciones, inyección y salidas estructuradas |
| 4 | Capacidades del Assistant | Planificación y herramientas integradas gradualmente |
| 5 | Consolidación | Integración, pruebas y preparación para ampliar el sistema |

Las fases 1 y 2 entregan una experiencia Terminal utilizable: Atlas inicia, conversa con Ollama cuando está disponible, conserva conversaciones en SQLite, administra su ciclo de vida y ofrece backup/restore/exportación. La aprobación de estas fases no significa que Atlas ya disponga de ejecución autónoma general.

## Fase 1 — Experiencia Terminal

**Estado: implementada y validada en el alcance actual.**

Incluye ciclo de consola, streaming cuando el proveedor lo permite, estados de respuesta, `/help`, `/clear`, `/exit`, alias de salida y manejo de EOF/interrupciones. `/clear` limpia únicamente la pantalla y conserva la conversación.

## Fase 2 — Gestión de conversaciones

**Estado: implementada; validación automatizada local aprobada el 16 de noviembre de 2026.**

### Capacidades incluidas

| Incremento | Alcance | Estado |
|---|---|---|
| 2A | Contratos, modelo de dominio y puertos de conversación | Implementado |
| 2B | Persistencia SQLite aislada, migraciones e historial íntegro | Implementado |
| 2C | Proyección acotada al modelo: 8 turnos y 2.000 caracteres por mensaje | Implementado |
| 2D | Integración SQLite en el arranque y recuperación de conversación activa | Implementado |
| 2E | Crear, listar, seleccionar, renombrar, cerrar y eliminar con confirmación | Implementado |
| 2F | Backup cifrado, verificación y restauración a ruta nueva | Implementado |
| 2G | Exportación JSON versionada, íntegra y sin sobrescritura | Implementado |

### Evidencia automatizada

En Debian, dentro del entorno virtual del proyecto:

- `python -m unittest tests.unit.test_conversation_deletion -v`: **6 pruebas aprobadas**.
- `python -m unittest discover -s tests -v`: **844 pruebas aprobadas**, 0 fallos y 0 errores.
- Las pruebas de eliminación usan bases SQLite temporales.
- No se ejecutaron pruebas en GitHub Actions ni se usó CI como evidencia de aprobación.

La suite completa fue ejecutada localmente por el usuario sobre el commit `610f027f1fe91933278e431d8a9ec29dd291b96e`.

### Evidencia manual ya reportada

Se realizaron comprobaciones locales de persistencia y operaciones de backup, verificación, restauración, exportación y eliminación con bases y rutas temporales. La evidencia no implica borrado forense ni eliminación de copias en respaldos antiguos.

Antes de ampliar el alcance, cualquier nueva integración debe conservar los controles de permisos, rutas, cifrado y no sobrescritura ya establecidos.

### Criterio de avance

La fase 2 queda cerrada para el alcance implementado y probado en esta rama. Las validaciones manuales adicionales de experiencia con Ollama y modo offline pueden repetirse como smoke tests de operación, pero no invalidan la evidencia automatizada ya aprobada.

## Fase 3 — Inteligencia y comportamiento seguro

**Estado: en curso. Modelo principal ya seleccionado: Gemma 4 E2B.** La selección inicial no se repite en esta fase. El trabajo actual consiste en reproducir y corregir fallos de comportamiento, probar instrucciones equivalentes en inglés y español, validar salidas estructuradas en sandbox y reforzar la honestidad operativa.

La evaluación histórica, los resultados observados, la inspección del código y los criterios de salida están registrados en [docs/phase-3-intelligence.md](../phase-3-intelligence.md). La primera tarea es completar el corpus reproducible y repetir el caso de prompt injection que produjo dos propuestas destructivas `delete_file`. No se modificarán todavía el prompt productivo ni el adaptador para habilitar herramientas; no se ejecutarán herramientas reales.

### Criterios de salida

- Corpus versionado y repetible con prompts, resultados esperados y criterios de evaluación.
- Casos críticos de inyección y confusión entre propuesta/ejecución repetidos con resultados aceptables.
- Salidas estructuradas validadas externamente; nunca conceden permisos.
- Resultados registrados con tag del modelo, parámetros, versión de prompt y evidencia completa.
- El Assistant conserva la distinción entre sugerir, planificar, solicitar autorización, ejecutar y verificar.

## Orden general y registro de fases

La hoja de ruta central, los criterios para declarar una fase completada y el registro de cambios están en [docs/roadmap.md](../roadmap.md). La Fase 3 tiene un expediente de trabajo específico en [docs/phase-3-intelligence.md](../phase-3-intelligence.md).

## Fase 4 — Capacidades del Assistant

**Objetivo:** evolucionar de conversación a coordinación controlada, sin otorgar autoridad directa al modelo.

1. Mejorar clasificación de intenciones e identificación de datos faltantes.
2. Permitir planes estructurados con pasos y supuestos.
3. Definir contratos de herramientas y capacidades antes de conectar adaptadores.
4. Integrar una herramienta de bajo riesgo por vez, con pruebas de autorización y resultado.
5. Enrutar solicitudes protegidas a los componentes responsables.
6. Mantener aprobación humana para operaciones sensibles o no delegables.
7. Correlacionar solicitud, plan, autorización, ejecución y resultado.

No se incluye por defecto acceso general al shell, ejecución arbitraria de comandos, acceso irrestricto a archivos, SQL o Docker.

## Fase 5 — Consolidación

**Objetivo:** demostrar que el producto y sus integraciones funcionan coherentemente y están preparados para ampliar su alcance.

- Ejecutar pruebas unitarias, contractuales, de integración, regresión y seguridad.
- Validar persistencia, recuperación, límites y manejo de fallos.
- Integrar Identity/CAM y componentes protegidos únicamente cuando sus fronteras estén completas.
- Reforzar autenticación, autorización, aislamiento, auditoría y credenciales.
- Revisar dependencias, configuración y datos sensibles.
- Documentar instalación, operación, diagnóstico y recuperación.
- Decidir cuándo reanudar Desktop/API y los demás subsistemas.

## Cadencia para cada incremento

1. Inspeccionar código y pruebas existentes.
2. Definir un cambio pequeño y su criterio de aceptación.
3. Implementar sin reescribir componentes funcionales.
4. Ejecutar pruebas focalizadas.
5. Ejecutar suite relevante y completa cuando corresponda.
6. Verificar comportamiento real desde la terminal.
7. Revisar fallos, regresiones y límites.
8. Actualizar documentación y registrar evidencia.

## Prioridades en pausa

### Desktop para Windows

Se conserva la dirección previamente aprobada (C#/.NET/WinUI 3, conexión futura mediante API remota, Tailscale y HTTPS/TLS, vinculación explícita de dispositivos y permisos limitados). El desarrollo queda pausado hasta decidir su reanudación.

### API remota

La API remota para Desktop también queda pausada. No es requisito para la experiencia local actual.

### Seguridad avanzada

Se posterga la expansión de seguridad avanzada, pero no se eliminan las protecciones mínimas existentes: Ollama en loopback, separación entre conversación y ejecución, ausencia de acceso privilegiado directo y control humano sobre acciones sensibles.

## Relación con la visión general de Atlas

Esta hoja de ruta ordena el trabajo inmediato; no cancela los dominios de Atlas ni modifica sus contratos. Memory Engine, Identity/CAM, Broker, Project/Environment Manager, Skills Manager, agentes, Scheduler, aprobaciones, eventos, notificaciones y runtime de herramientas conservan sus propios estados de implementación. La integración de memoria protegida y herramientas debe respetar sus contratos y esperar a que sus fronteras durables y autorizadas estén listas.
