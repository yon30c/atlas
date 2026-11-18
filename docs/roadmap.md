# Hoja de ruta general de Atlas

> Fuente central del orden de implementación y del estado de las fases.
> Rama de seguimiento: `design/verified-agent-delegation-i3-2b`.
> Actualizado: 18 de noviembre de 2026.

Este documento registra el orden acordado para completar Atlas. Se actualiza al cerrar cada fase con evidencia verificable. El 16 de noviembre de 2026 el propietario cambió la prioridad: pausar el endurecimiento avanzado de seguridad y concentrar el trabajo inmediato en un Atlas funcional de prueba. Los estados describen el trabajo real implementado, no solamente diseños, contratos o planes.

## Reglas de seguimiento

Una fase solo puede marcarse **Completada** cuando:
1. El alcance y los criterios de aceptación están definidos.
2. La implementación correspondiente está integrada en la rama.
3. Las pruebas automatizadas pertinentes pasan localmente.
4. Las comprobaciones manuales requeridas se ejecutan y documentan.
5. No quedan defectos bloqueantes conocidos para el alcance de la fase.
6. La documentación refleja el resultado y referencia commit/evidencia.
7. Se actualizan este roadmap, el estado vigente y el README cuando corresponda.

Estados permitidos:
- **Completada:** todos los criterios de salida se han demostrado.
- **En curso:** existe trabajo activo y se conoce el siguiente incremento.
- **Pendiente:** no se ha iniciado o depende de fases anteriores.
- **Bloqueada:** existe una dependencia o riesgo que impide avanzar.

No se marcará una fase como completada por tener sus contratos escritos, por pasar únicamente pruebas unitarias aisladas ni por una respuesta convincente del modelo. Las pruebas locales reportadas por el usuario se etiquetan como tales; no se presentan como CI o producción.

## Orden de fases

| Orden | Fase | Objetivo | Estado |
|---:|---|---|---|
| 1 | Experiencia Terminal | Disponer de una superficie local utilizable para conversar con Atlas | **Completada** |
| 2 | Conversaciones persistentes | Conservar, administrar, exportar y respaldar conversaciones | **Completada** |
| 3 | Inteligencia y comportamiento seguro | Validar comportamiento, inyección, salidas estructuradas y honestidad | **Pausada** |
| 4 | Atlas funcional de prueba / capacidades del Assistant | Evolucionar de conversación a tareas completas en entorno local de prueba | **Prioridad actual** |
| 5 | Integración y consolidación | Integración entre dominios, seguridad, recuperación, auditoría y preparación operativa | **Pendiente** |

## Fase 1 — Experiencia Terminal

**Estado: Completada.**

Alcance demostrado:
- Consola conversacional local.
- Integración con Ollama y streaming.
- Modo offline informativo.
- Manejo de entrada, salida, EOF e interrupciones.
- Separación entre generación conversacional y ejecución de acciones.

Evidencia y detalles: [Atlas Terminal](terminal/README.md).

## Fase 2 — Conversaciones persistentes

**Estado: Completada.**

Alcance demostrado:
- Persistencia SQLite independiente de la base de autoridad.
- Recuperación de la conversación activa.
- Crear, listar, seleccionar, renombrar, cerrar y eliminar.
- Exportación JSON.
- Backup cifrado, verificación y restauración a ruta nueva.
- Pruebas de rollback y eliminación.

Evidencia local reportada el 16 de noviembre de 2026:
- Pruebas específicas de eliminación: 6/6.
- Suite completa: 844/844.
- Commit de código probado: `610f027f1fe91933278e431d8a9ec29dd291b96e`.
- Ejecutadas por el usuario en Debian con `.venv`; no son resultados de GitHub Actions.

## Fase 3 — Inteligencia y comportamiento seguro

**Estado: Pausada por decisión del propietario el 16 de noviembre de 2026.** Modelo principal ya seleccionado: **Gemma 4 E2B**. La selección inicial de modelo no se repetirá como objetivo de esta fase.

Objetivo: convertir los aprendizajes de la evaluación inicial en un comportamiento evaluable, consistente y seguro. Esta fase no habilita herramientas reales ni concede autoridad al modelo.

Subfases:
1. **3.1 — Consolidar baseline y protocolo reproducible.** Completada para el baseline/harness inicial: corpus, esquema, registro JSONL y runner aislado implementados; P3-PI-002 documentado en 40 corridas; pruebas unitarias locales del harness aprobadas 6/6 el 16 de noviembre de 2026.
2. **3.2 — Instrucciones y resistencia a prompt injection.** En curso: P3-PI-001 tiene un fallo exploratorio histórico y una repetición controlada posterior con 4/4 respuestas seguras. P3-PI-002 está completado como escenario: 40/40 contención y 22/40 reconocimiento estricto. Faltan otros casos de inyección directa, suplantación de roles privilegiados, revelación de razonamiento y conflictos de autoridad.
3. **3.3 — Salidas estructuradas en entorno de evaluación.** En curso: schema cerrado, validador puro y pruebas unitarias adversariales añadidos al harness. Pendiente ejecutar pruebas localmente y completar separación de autorización externa. No conectar esas salidas a ejecutores.
4. **3.4 — Límites y honestidad operativa.** Probar que Gemma no afirme ejecución, no transforme planes en acciones realizadas, respete denegaciones y comunique errores/resultados inciertos.
5. **3.5 — Robustez y regresión.** Añadir corpus versionado, pruebas repetibles, criterios de aceptación y regresión de los casos que fallen.

Criterios de salida:
- Gemma 4 E2B sigue siendo el modelo seleccionado salvo decisión explícita basada en evidencia nueva.
- Corpus versionado con entradas, variantes de idioma, resultados esperados y severidad.
- Resultados reproducibles con tag exacto del modelo, parámetros y versión de prompt.
- Los casos críticos de inyección y de confusión entre propuesta/ejecución tienen resultados aceptables y repetibles.
- Las salidas estructuradas se validan fuera del modelo y nunca conceden permisos.
- Ninguna herramienta real ni operación destructiva se ejecuta durante la evaluación.
- Los fallos conocidos quedan documentados; no se ocultan con promedios de calidad.

El corpus, harness y protocolo están en `tests/evaluation/phase3/`. P3-PI-002 se fijó a `gemma4:e2b-it-q4_K_M` y completó 40 corridas (10 por combinación); resultados: 40/40 contención y 22/40 reconocimiento estricto. Informe: [matriz P3-PI-002 de Gemma 4](evaluations/p3-pi-002-gemma4-language-matrix.md). Las pruebas unitarias locales del harness pasaron 6/6 el 16 de noviembre de 2026. Documento de trabajo: [Fase 3 — Inteligencia y comportamiento](phase-3-intelligence.md).

## Fase 4 — Atlas funcional de prueba / capacidades del Assistant

**Estado: En curso — base de autoridad e identidad en desarrollo; integración funcional del Assistant pendiente.** El objetivo sigue siendo disponer de un asistente local que complete flujos de trabajo de prueba de principio a fin. La rama actual ha avanzado en autenticación nativa, identidad verificada USER/AGENT, delegación AGENT, renovación CAM y lifecycle de asociaciones Project–Environment. Estos componentes son prerrequisitos de confianza y todavía no están conectados a la consola ni a un runtime protegido. El incremento 7B.6B quedó validado y cerrado el 18 de noviembre de 2026 en Debian: 37 pruebas focalizadas OK, `compileall` con código 0 y `main` sincronizada con `origin/main`. El siguiente incremento propuesto es la auditoría read-only 7B.6C de imports, call-sites y exports. El alcance funcional y sus criterios de aceptación están en [docs/functional-test-roadmap.md](functional-test-roadmap.md).

Objetivo: permitir que Atlas comprenda solicitudes, elabore planes y solicite capacidades de forma controlada, manteniendo al modelo fuera de la frontera de autoridad.

Alcance previsto:
- Interpretación de intención y detección de información faltante.
- Planes estructurados con pasos, dependencias y supuestos.
- Contratos de herramientas y validación de argumentos.
- Integración con Identity/CAM y políticas de autorización.
- Aprobaciones humanas para acciones sensibles o no delegables.
- Ejecución exclusivamente mediante componentes mediadores autorizados.
- Correlación entre solicitud, plan, autorización, ejecución y resultado.

No implica acceso arbitrario a shell, archivos, SQL, Docker ni permisos directos para el modelo.

## Fase 5 — Integración y consolidación

**Estado: Pendiente.**

Objetivo: demostrar coherencia y seguridad en la composición real de los dominios.

Alcance previsto:
- Integración de Assistant con Identity/CAM, Memory Engine y Broker cuando sus fronteras estén listas.
- Integración progresiva de Project/Environment Manager, Skills Manager, agentes y Scheduler.
- Aprobaciones, eventos y notificaciones.
- Pruebas unitarias, contractuales, de integración, regresión y seguridad.
- Recuperación integral, auditoría, observabilidad y documentación operativa.
- Evaluación de preparación para producción y reanudación de Desktop/API remotos.

El Recovery Gate seguirá cerrado hasta demostrar autoridad, bootstrap y recuperación completos.

## Registro de cambios de estado

| Fecha | Fase | Cambio | Evidencia |
|---|---|---|---|
| 2026-11-16 | 1 | Confirmada como completada | Implementación y validación documentadas en `docs/terminal/README.md` |
| 2026-11-16 | 2 | Confirmada como completada | 6/6 pruebas focalizadas y 844/844 suite local en commit `610f027...` |
| 2026-11-16 | 3 | Pausada por decisión del propietario | P3-SR con `schema_only`: 9/9 PASS determinísticos en una pasada; SR-008: 5/5. SR-006 conserva revisión semántica pendiente. No es aprobación de seguridad. |
| 2026-11-16 | 4 | Convertida en prioridad actual: Atlas funcional de prueba | Acuerdo de construir capacidades end-to-end en entorno local de prueba; plan en `docs/functional-test-roadmap.md`. |
| 2026-11-18 | 4 / Cycle 3.2 | Avance de identidad, delegación AGENT y lifecycle Project–Environment; 7B.6B validada y cerrada | Suite completa: 1,513 tests OK; validación focalizada: 37 tests OK; `compileall` exit 0; `main`/`origin/main` sincronizadas. Runtime protegido sigue desconectado. |

## Trabajo transversal fuera de estas fases

Las fases organizan el camino de entrega; no sustituyen el estado de cada dominio. Identity/CAM, Memory Engine, Broker, Project/Environment Manager, Skills Manager, agentes, Scheduler, Approval, eventos, notificaciones y runtime de herramientas conservan sus propios criterios y estados. Consulta [estado vigente](status-current.md).

## Referencias

- [Estado vigente de Atlas](status-current.md)
- [Plan de Atlas funcional de prueba](functional-test-roadmap.md)
- [Fase 3 — Inteligencia y comportamiento](phase-3-intelligence.md)
- [Atlas Terminal](terminal/README.md)
- [Roadmap detallado Terminal-first](terminal/roadmap.md)


## Actualización de seguimiento — 18 de noviembre de 2026

La rama de trabajo actual incorpora Authentication/Identity Authority nativa, servicios de contexto verificado USER/AGENT, delegación AGENT con consentimiento del propietario, renovación delegada bajo CAM y lifecycle auditable de asociaciones Project–Environment. La separación de capacidades de escritura lifecycle (7B.6B) está implementada y validada en Debian: 37 pruebas focalizadas OK y `compileall` exit 0 sobre `main` (`f0070dd`). Queda cerrada en el alcance validado. 7B.6C se plantea como auditoría read-only de imports/call-sites/exports antes de cualquier cambio adicional.

El propietario reportó la suite completa: **1,513 tests — OK**. Esta evidencia no equivale a validación E2E ni a habilitación de login, endpoints, runtime AGENT o herramientas. La Fase 4 continúa en curso; F3–F5 siguen pendientes como flujos funcionales integrados. La Fase 3 de evaluación avanzada permanece pausada.
