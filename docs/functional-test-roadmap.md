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

**Estado:** F2.1 (`workspace.list`) validada con 893/893 pruebas. F2.2 (`WorkspaceListingService`) implementada y validada por el propietario con 900/900 pruebas. El Ciclo 1 amplía la lectura con `WorkspaceFile`, `WorkspaceFileReader`, `WorkspaceFileReadingService` y `LocalWorkspaceAdapter.read_file`, además del catálogo cerrado `CapabilityCatalog` para `workspace.list` y `workspace.read`. Se añadieron pruebas unitarias para confinamiento de rutas, enlaces simbólicos, archivos UTF-8, límite de tamaño, resultados y catálogo. **Ciclo 1 VALIDADO por el propietario: suite completa de 1,157 tests en 9.853 s, todos OK; `compileall` también finalizó sin errores.** El Ciclo 2 incorpora `WorkspaceFileWritingService` y `LocalWorkspaceWriteAdapter` con staging durable, commit explícito, idempotencia por `operation_id`, comprobación SHA-256 del destino y evaluación de recuperación de solo lectura. Se añadieron pruebas de staging, creación/actualización, colisiones, corrupción y crash después del rename. **Ciclo 2 VALIDADO por el propietario: suite completa de 1,182 tests en 9.769 s, todos OK.** La escritura permanece fuera del catálogo y del runtime; este protocolo de archivos no constituye autorización CAM ni fencing frente a escritores externos. F2.3 documenta la separación entre revisión del plan, autorización CAM y aprobación humana. F2.3.1 añadió los contratos `OperationAuthorizationEvidence`, `OperationAuthorizationResult` y `OperationAuthorizationPort`, validados por el propietario con 913/913 pruebas. F2.3.2 añade el puerto de verificación confiable y `OperationAuthorizationEvidenceVerificationService`, validado por el propietario con 922/922 pruebas. F2.3.3a amplía la evidencia para incluir revisiones explícitas de proyecto y entorno; el propietario validó 925/925 pruebas. F2.3.3b inspeccionó las fuentes de autoridad y documentó por qué todavía no es seguro crear un adaptador de verificación genérico: no existe un coordinador concreto de invalidación/fencing en esta rama. No hay todavía adaptador concreto del verificador, coordinador durable de invalidación/fencing integrado, Approval Manager ni ejecución desde consola/runtime.

- Definir un catálogo pequeño de capacidades reales.
- Implementar adaptadores concretos para el workspace de prueba.
- Conectar cada capacidad a un servicio de aplicación.
- Validar entradas y devolver resultados estructurados.
- Distinguir errores, resultados parciales y éxito real.
- Mantener el workspace de prueba separado de datos personales y del sistema.

**Criterio de salida:** Atlas completa operaciones de lectura y escritura de prueba y presenta resultados comprobables. El Ciclo 1 aporta los adaptadores y contratos de lectura; no cierra F2 hasta integrar autorización/ejecución y completar escritura controlada.

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

**Siguiente acción:** diseñar e implementar el Ciclo 3 (autorización + integración) sin conectar escritura al runtime hasta disponer de un gate de autorización/consistencia adecuado. La suite completa del Ciclo 2 quedó validada por el propietario: 1,182 tests en 9.769 s, todos OK.


### F2.3.3b — Inspección de autoridad y consistencia

La inspección confirmó que los contratos de Memory `RevisionValidationPort` dependen de `AuthorizationSnapshot` y `ConsistencyPosition`, y exigen invalidation-first + revalidación transaccional; no hay adaptador concreto que lo demuestre. `GrantRepository` es persistencia simple; `SQLiteIdentityAuthority` aplica CAS pero no coordina invalidación; `AuthorityChangeCoordinatorPort` no tiene implementación concreta en la rama; `SQLiteAuthorityChangeStore` solo reserva/idempotencia.

Por tanto, no se implementará un verificador que haga lecturas puntuales multi-repositorio ni se declarará que estas cierran carreras de revocación. El siguiente diseño debe decidir entre completar la autoridad durable común (coordinador + fencing + UoW compartida) o restringir expresamente el perfil de prueba sin efectos y sin garantías de revocación concurrente. El runtime permanece desconectado.


### F2.3.4 — Frontera de consistencia de operaciones

Decisión documentada en [assistant-operation-consistency-boundary.md](design/assistant-operation-consistency-boundary.md). Una evidencia CAM verificada no equivale a admisión. Las operaciones con efectos requieren admisión exacta vinculada a operación, actor, recurso, cuatro revisiones y posición de consistencia, coordinada con invalidación/fencing.

Se establece que `BEGIN IMMEDIATE` solo serializa de forma útil si Identity, Grant, Project, Environment, journal, admisiones e invalidaciones comparten la misma `SQLiteDatabase`/UoW y todos los caminos de mutación pasan por el coordinador. No se acepta una composición de lecturas puntuales ni locks de proceso.

El alcance inicial queda limitado a lecturas `workspace.list` y `workspace.read`; las escrituras quedan desconectadas porque SQLite no puede confirmar atómicamente efectos del sistema de archivos. Se definieron ocho criterios previos a implementar un adaptador.

**Estado:** decisión de arquitectura publicada; sin código de ejecución, coordinador durable ni adaptador CAM. Próximo paso F2.3.5: inventario de persistencia/composición de Identity, Grant, Project y Environment (repositorio, base, UoW y caminos de mutación).


### F2.3.5 — Inventario de persistencia y composición

Inspección estática completada y documentada en [assistant-operation-consistency-boundary.md](design/assistant-operation-consistency-boundary.md). La composición actual no tiene una UoW común: Identity crea su propia SQLiteDatabase; Grant solo tiene Protocol/UoW para Grants + renovaciones y no hay adaptador SQLite concreto; Project/Environment solo tienen contratos de metadatos bajo Memory; el journal y authority-change store pueden usar SQLite, pero no están compuestos con esas fuentes. Los cambios de estado de Identity usan CAS directo y Grant issue escribe directo al repositorio; no existe coordinador concreto de invalidación/fencing.

**Conclusión:** no es posible implementar honestamente el adaptador CAM compartido añadiendo solo un verificador. Requiere una composición canónica nueva y migrar los caminos de mutación existentes, o aplazar CAM integrado para el perfil read-only de prueba.

**Estado:** inspección documentada; sin cambios de código. Se requiere decidir el alcance antes de construir las cuatro fuentes canónicas mínimas.

### F2.3.6 — Composición Identity sobre base compartida

Añadido `compose_sqlite_identity_on_database(database)`, que compone la autoridad Identity sobre una instancia SQLite preexistente, sin crear otra base. La función standalone `compose_sqlite_identity(path)` permanece compatible y delega en ella. Se añadieron pruebas de reutilización exacta de instancia y validación de entrada.

**Estado:** código y pruebas publicados; pendiente de ejecución local por el propietario. Este seam no equivale a una autoridad común: Grant, Project, Environment, journal, invalidación y fencing todavía no están integrados. Runtime desconectado.

### F2.3.7 — Persistencia SQLite canónica de Grants

Añadida migración v7 y `SQLiteGrantRepository`, con scope/acciones inmutables, revisión CAS, revocación terminal y tombstones. Nueva composición `SQLiteLocalAuthorityFoundation` reúne Identity, Grants y el ledger durable de cambios de autoridad en la misma instancia SQLite. Se añadieron pruebas de repositorio, integridad y composición; las fixtures históricas v6 se ajustaron para seguir validando la migración v6 desde schema v5.

**Estado:** publicado; pendiente de ejecución local. No existe aún UoW SQLite para Grant + renovaciones, coordinador de invalidación, fuentes Project/Environment ni admisión. No se conecta runtime.

### F2.3.8 — Unidad de trabajo SQLite para Grant y renovaciones

Migración v8 para solicitudes de renovación, repositorio SQLite con CAS y decisión terminal, y `SQLiteAuthorizationUnitOfWorkFactory` que comparte una conexión transaccional entre Grant y renovaciones. `GrantRenewalService` puede usarla directamente; `GrantManagementService.issue` usa la fábrica cuando se inyecta para hacer unicidad + alta atómicas.

Pruebas añadidas para persistencia, CAS, binding/decisión inmutable, rollback, commit explícito, excepción después de solicitar commit, y servicios de emisión/renovación.

**Estado:** validado por el propietario con 957/957 pruebas. La unidad transaccional compartida y los servicios de emisión/renovación están verificados. La composición todavía no obliga a todo el wiring de emisión a usar la fábrica; el coordinador común sigue pendiente.

### F2.3.9 — Fuentes canónicas Project y Environment

Añadida migración v9 con tablas canónicas para Project y Environment, snapshots tipados reutilizando los puertos existentes de metadatos, repositorio SQLite con altas/lecturas/actualizaciones CAS y retención de tombstones. La composición local expone el repositorio usando la misma instancia SQLite que Identity, Grants, renovaciones y el ledger de cambios. Se añadieron pruebas de persistencia, revisión obsoleta, restricciones SQL y composición.

**Estado:** validado por el propietario con 967/967 pruebas. Migración v9, repositorio Project/Environment, restricciones de revisión y composición SQLite compartida verificadas. Las mutaciones todavía no pasan por un coordinador común de invalidación/fencing; no conectar a la admisión ni al runtime.

### F2.3.10 — Auditoría de rutas de mutación y prerrequisitos del coordinador

Inspeccionadas las rutas actuales de Identity, emisión/revocación/renovación de Grants y mutaciones Project/Environment. Se documentó qué rutas escriben directamente, cuáles usan UoW sin invalidación y cuáles requieren CAM/coordinador. La conclusión es que aún no existe un coordinador concreto: `SQLiteAuthorityChangeStore` persiste reservas/idempotencia, pero no ejecuta fencing, invalidación, CAS coordinado ni reconciliación. No se añadieron cambios de runtime ni se habilitó admisión.

**Siguiente orden obligatorio:** migrar las rutas de mutación a una API coordinada; cerrar bypasses; integrar journal, invalidation, route registry y fencing; probar concurrencia/crash/replay; solo después implementar admisión de operaciones.

**Estado:** auditoría documentada. Sin código nuevo ni pruebas adicionales; no habilitar ejecución.

### F2.3.11 — Cierre del bypass de emisión de Grants

`GrantManagementService.issue` ya no permite el fallback de escritura directa cuando falta `unit_of_work_factory`: falla cerrado antes de modificar el repositorio. La comprobación de unicidad y la inserción solo se realizan dentro de la unidad transaccional compartida. Se añadió una prueba que confirma que la ausencia de UoW no crea el Grant, y se adaptó el fixture de servicio a una UoW en memoria.

**Estado:** validado por el propietario con 968/968 pruebas. Esto cierra únicamente el bypass de emisión; no coordina todavía la mutación con invalidación/fencing.

### F2.3.12 — Auditoría detallada de renovaciones

Se verificó que la UoW hace atómica la actualización de Grant + solicitud al aprobar una renovación, pero no coordina invalidación/fencing de admisiones basadas en la revisión anterior. La solicitud y el rechazo tienen semánticas distintas y requieren política explícita de auditoría/autorización. Se documentó la vinculación futura entre operación, Grant, versión de renovación, actor, owner, proyecto y entorno. No se reutilizará el autorizador CAM específico de revocación ni se añadirá un coordinador ficticio.

**Estado:** auditoría documentada; sin cambios de runtime ni pruebas nuevas.

### F2.3.13 — Diseño multiobjetivo para cambios de autoridad

Se documentó un contrato multiobjetivo para operaciones que mutan más de una fuente canónica. Es necesario para aprobación de renovación, que cambia Grant y solicitud en una única decisión lógica: un operation_id, una clave idempotente, todos los objetivos/revisiones tipados, reserva atómica, CAM sobre el conjunto exacto, fencing conjunto, CAS en una UoW y reconciliación completa. Se especificaron también semánticas separadas para solicitar, aprobar y rechazar renovaciones, migración aditiva y pruebas de concurrencia/crash.

**Estado:** diseño publicado; sin código runtime ni pruebas. El contrato actual de una sola autoridad permanece sin cambios. No habilitar aprobación de renovación coordinada ni admisión.

### F2.3.14 — Modelos multiobjetivo inmutables

Añadidos `AuthorityChangeTargetKind`, `AuthorityChangeTarget` y `MultiAuthorityChangeIntent`. Distinguen Grant y Grant renewal, fijan cada transición de revisión en +1, exigen dos o más objetivos, canonicalizan el orden, rechazan duplicados y validan actor/owner/action/idempotency/context/UTC. Se añadieron pruebas unitarias de contratos.

**Estado:** validado por el propietario con 1003/1003 pruebas. Los modelos aún no están conectados al CAM ni a un coordinador de fuentes.

### F2.3.15 — Persistencia SQLite de reservas multiobjetivo

Migración v10 aditiva y tablas separadas para operación, idempotencia y conjunto de objetivos. Se añadieron persistencia atómica de intención completa, canonicalización, replay idempotente, rechazo de clave reutilizada con intención distinta y triggers de inmutabilidad/sellado. Store con reserva y recuperación por operation_id o clave idempotente. Pruebas añadidas.

**Estado:** validado por el propietario con 988/988 pruebas. Es registro durable, no exclusión mutua/claim de objetivos ni coordinador. No hay CAM, fencing, invalidación, mutación de fuentes ni runtime.

### F2.3.17 — Contrato de evidencia terminal multiobjetivo

Añadidos contratos inmutables para resultados terminales `COMPLETED` y `ABORTED`. Cada recibo debe vincular operación, referencia durable, registrador, timestamp UTC y el conjunto completo de objetivos/revisiones. COMPLETED exige observación de todas las revisiones propuestas; ABORTED exige que todas permanezcan en las revisiones esperadas. La coincidencia con la reserva se comprueba por operation_id y conjunto exacto de objetivos.

**Límite:** por ahora solo se valida el contrato en memoria. No autentica la evidencia, no la persiste, no cambia el estado durable ni libera claims. Runtime desconectado.

**Estado:** validado por el propietario con 1003/1003 pruebas.

### F2.3.16 — Claims exclusivos multiobjetivo

Migración v11 añade claims con unicidad global por tipo/ID de autoridad. `SQLiteAuthorityChangeStore.acquire_multi_claims` reclama el conjunto completo dentro de `BEGIN IMMEDIATE`, rechaza operaciones ausentes/no solicitables, permite retry exacto y devuelve conflicto sin adquisición parcial si cualquier target ya está reclamado. Se añade lectura de claims y triggers de binding a targets `REQUESTED`, inmutabilidad y no eliminación. Pruebas cubren adquisición completa, retry, conflicto sin parcialidad, competición entre conexiones y restricciones SQL.

**Límite deliberado:** los claims no se liberan todavía. Permanecen retenidos hasta que exista evidencia durable y un protocolo de liberación verificada. Los estados inciertos/blocked conservan el bloqueo. Esto no equivale a CAM, invalidación/fencing, mutación coordinada de fuentes ni admisión. Validado por el propietario con 993/993 pruebas.


### F2.3.18 — Persistencia atómica de evidencia terminal

Migración SQLite v12 añade tablas inmutables para el recibo terminal y cada objetivo observado. record_multi_terminal_evidence exige operación conocida en RECONCILING, conjunto completo de claims y coincidencia exacta del recibo con la reserva. Inserta recibo + objetivos + transición a COMPLETED/ABORTED dentro de una única UoW. Replay exacto recupera el recibo original; un recibo diferente se rechaza. La recuperación recalcula el digest y la canonicalización para detectar corrupción del contenido persistido. Triggers SQL impiden estado terminal sin evidencia y conjunto de objetivos completo, así como cambiar el estado terminal después. Claims permanecen retenidos.

**Límite:** canonicalización/digest dan binding e idempotencia, no autenticidad ni verificación independiente de la evidencia externa. Sin CAM, fencing, invalidación, mutación de fuentes ni runtime.

**Estado:** validado por el propietario con 1014/1014 pruebas (16 de noviembre de 2026).


### F2.3.19 — Liberación auditable de claims terminales

Migración SQLite v13 incorpora un ledger inmutable de liberaciones. Solo permite registrar una liberación cuando la operación está COMPLETED/ABORTED, el recibo terminal y su digest coinciden, y los conjuntos de targets, observaciones y claims están completos. La eliminación de claims queda protegida por trigger y exige el recibo de liberación.

`release_multi_claims` valida la evidencia persistida, compara los conjuntos exactos y registra el recibo + elimina todos los claims en una misma UoW. Reintentos son idempotentes; operaciones no terminales devuelven False; corrupción, evidencia incompleta o claims parciales fallan cerrados. La auditoría de liberación es inmutable y los recursos pueden reclamarse de nuevo después del commit.

**Límite:** no autentica la referencia externa ni sustituye CAM, fencing, invalidación o un coordinador real. No se conecta al runtime.

**Estado:** validado por el propietario con 1021/1021 pruebas (16 de noviembre de 2026).


### F2.3.20 — Auditoría de recuperación de claims

Se añade una API de auditoría de solo lectura que clasifica una operación como UNCLAIMED, CLAIMED, TERMINAL_CLAIMS_HELD, RELEASED o INCONSISTENT. Compara el conjunto reservado con los claims, valida la evidencia terminal reconstruida y el digest de liberación, y detecta conjuntos parciales, evidencia ausente/corrupta y estados incompatibles. No modifica ni repara datos; las operaciones desconocidas devuelven None.

**Límite:** clasificación local, no prueba de reconciliación externa ni autenticidad. No conecta CAM ni runtime.

**Estado:** validado por el propietario con 1030/1030 pruebas (16 de noviembre de 2026).


### F2.3.21 — Frontera UoW compartida para autoridades canónicas

Se habilita que Identity y Project/Environment acepten una `SQLiteUnitOfWork` externa exacta. Se añade `SQLiteLocalAuthorityUnitOfWork`, que compone sobre la misma transacción Identity, Grants, solicitudes de renovación, Project y Environment. La fábrica exige una única `SQLiteDatabase`; los repositorios verifican propiedad/actividad de la UoW al usarla. La suite nueva prueba commit conjunto, rollback cruzado, rechazo de UoW de otra base y rechazo de uso después de cerrar la transacción.

**Límite:** esto es composición transaccional de persistencia, no coordinador de consistencia. En esta fase el ledger todavía no estaba incluido; se integró en F2.3.22. No se añadieron CAM, invalidación, fencing, admisión ni mutaciones coordinadas. Runtime desconectado.

**Estado:** validado por el propietario con 1040/1040 pruebas (16 de noviembre de 2026).


### F2.3.22 — Ledger de operaciones dentro de la UoW compartida

Se modifica `SQLiteAuthorityChangeStore` para aceptar la misma `SQLiteUnitOfWork` externa usada por Identity, Grants, renovaciones, Project y Environment. Sus operaciones de reserva, claims, evidencia terminal, liberación y consultas pueden participar en esa transacción, sin abrir conexiones o transacciones anidadas. `SQLiteLocalAuthorityUnitOfWork` expone ahora `authority_changes`.

Las pruebas nuevas verifican commit y rollback conjunto entre identidad, proyecto y reserva de operación, además del rechazo de uso después de cerrar la UoW.

**Límite:** esto unifica la persistencia en una transacción, pero todavía no crea un coordinador que decida orden, CAM, admisión, invalidación, fencing, ejecución de mutaciones ni reconciliación. La UoW es infraestructura transaccional, no permiso para ejecutar.

**Estado:** validado por el propietario con 1043/1043 pruebas (16 de noviembre de 2026).


### F2.3.23 — Máquina de estados multiobjetivo con CAS

Migración v14 restringe los cambios de estado del ledger multiobjetivo a la secuencia estricta `REQUESTED → INVALIDATION_PENDING → SOURCE_PENDING → SOURCE_CONFIRMED → RECONCILING → COMPLETED/ABORTED`. Los dos estados terminales siguen requiriendo el recibo de reconciliación completo ya definido por v12. Cualquier salto, retroceso o terminalización directa es rechazado por SQLite incluso si se omite la API.

`SQLiteAuthorityChangeStore.transition_multi_status` aplica compare-and-set con estado esperado, rechazo de reintentos obsoletos cuando el estado ya avanzó y rechazo de llamadas obsoletas. Cada avance intermedio exige el conjunto íntegro de claims exclusivos. La transición registra progreso del ledger únicamente: no acredita que una invalidación externa haya ocurrido, no autoriza mutaciones de fuentes y no ejecuta efectos. No se habilita todavía transición a BLOCKED ni recuperación desde ella; eso requiere un contrato de recuperación separado.

**Estado:** VALIDADA localmente por el propietario; suite completa: 1048 tests en 9.026 s, todos OK.


### F2.3.24 — Diagnóstico de recuperación multiobjetivo

Se añade `MultiAuthorityRecoveryAssessment` y `MultiAuthorityRecoveryDisposition`, junto con `SQLiteAuthorityChangeStore.assess_multi_recovery(operation_id)`. La evaluación es de solo lectura y combina el estado durable del ciclo de vida con la auditoría existente de claims/evidencia.

Distingue solicitudes no iniciadas, claims adquiridos antes de invalidación, invalidación con resultado desconocido, mutación de fuente con resultado desconocido, confirmación de fuente registrada, reconciliación en curso, claims terminales retenidos, operación terminal liberada y estado inconsistente. Una operación desconocida devuelve `None`.

**Límite de seguridad:** `SOURCE_PENDING` se clasifica como resultado desconocido; nunca como no ejecutado. La clasificación no demuestra que un efecto externo haya ocurrido, no autoriza reintentos, no reanuda operaciones, no cambia estados y no libera claims. No se añade transición a `BLOCKED`.

**Estado: VALIDADA.** Suite completa: 1054 tests OK. La evaluación es de solo lectura y no autoriza reintentos ni mutaciones.


### F2.3.25 — Contrato declarativo de decisión de recuperación

Se añaden decisiones tipadas y requisitos de evidencia por disposición del diagnóstico F2.3.24. La recomendación es pura y está ligada al operation_id; distingue revalidación de autoridad, verificación de invalidación, verificación del resultado de fuente, comprobación previa a reconciliación, revisión de evidencia terminal y escalamiento humano ante inconsistencias.

Ninguna decisión permite ejecución automática ni reintentos. El contrato no cambia el ledger, no libera claims, no crea transiciones BLOCKED y no se conecta al runtime. La evidencia requerida es una condición para una futura revisión/coordinación, no autorización.

**Estado: VALIDADA.** Suite completa: 1061 tests en 7.206 s, todos OK.


### F2.3.26 — Contrato de evidencia independiente de recuperación

Se incorpora un modelo inmutable de evidencia no confiable, ligado a operation_id, tipo de evidencia, issuer, ventana temporal, digest y conjunto completo de objetivos/revisiones. Se agrega un puerto verificador de confianza y un servicio que valida binding/ventana antes de delegar autenticidad.

El servicio diferencia VERIFIED, DENIED y UNAVAILABLE. Solo True exacto del verificador produce VERIFIED; excepciones producen UNAVAILABLE. No se confunde digest/referencia con autenticidad. La implementación concreta de criptografía, claves y fuentes autoritativas queda fuera de esta fase.

**Estado: VALIDADA.** Suite completa: 1072 tests en 7.828 s, todos OK.


## F2.3.27 — Política de confianza de emisores

Implementados los contratos `RecoveryEvidenceIssuerTrustPolicy` y `RecoveryEvidenceIssuerTrustPolicyPort`. La política limita por emisor, revisión, habilitación, tipos de evidencia, vigencia y duración máxima. El servicio consulta la política antes de invocar el verificador; rechaza emisores ausentes o políticas incompatibles y devuelve UNAVAILABLE si la fuente de políticas falla.

La política es un filtro de confianza, no una prueba criptográfica. La autenticidad de la atestación, digest/payload, revocación de claves, replay y estado autoritativo permanecen en el verificador. No existe almacenamiento concreto ni conexión al runtime.

**Estado: VALIDADO.** El propietario confirmó la suite completa con 1076 tests, todos OK.

## F2.3.28 — Repositorio durable de políticas de confianza

Implementar snapshots inmutables por emisor y revisión en SQLite, con migración, CAS de revisión, historial consultable, retención sin UPDATE/DELETE y composición en la UoW local compartida. El puerto de lectura debe devolver siempre la última revisión canónica.

**Límites:** no implementar criptografía, gestión de claves, acciones de recuperación ni integración runtime en este incremento.

**Estado: VALIDADO.** El propietario ejecutó la suite completa: 1088 tests, todos OK.


## F2.3.29 — Auditoría de integridad de políticas de confianza

Se implementan diagnósticos de solo lectura para políticas por emisor: continuidad de revisiones, contenido canónico y decodificable, política vigente deshabilitada y ausencia de política para un emisor consultado. `audit_all()` obtiene un snapshot consistente y no muta la base. No se incluyen reparaciones automáticas, autenticación criptográfica ni autoridad de recuperación.

**Estado: VALIDADO.** El propietario ejecutó la suite completa: 1094 tests, todos OK.

## F2.3.30 — Inventario autoritativo de emisores

Implementar un inventario persistente y versionado de emisores esperados, separado de las políticas de confianza. Cada emisor tendrá snapshots append-only y cambios mediante CAS; SQL impedirá reescritura o eliminación de historial. Componer el repositorio en la UoW local compartida y cruzar inventario/políticas en una auditoría consistente de solo lectura.

La auditoría debe detectar registros sin política, políticas huérfanas, emisor deshabilitado, política deshabilitada y corrupción de ambos historiales. Registrar un emisor nunca constituye autenticación ni confianza.

**Estado: VALIDADO.** El propietario ejecutó la suite completa: 1106 tests en 9.086 s, todos OK.

## F2.3.31 — Integración del inventario en la verificación de evidencia

El servicio `MultiAuthorityRecoveryEvidenceVerificationService` exige ahora tres dependencias separadas: registro autoritativo de emisores, política de confianza y verificador independiente. Antes de consultar la política, obtiene el snapshot vigente del emisor. Si no existe, está deshabilitado o no coincide con el issuer_id de la evidencia, devuelve DENIED sin invocar política ni verificador. Si el inventario no está disponible, devuelve UNAVAILABLE y falla cerrado.

Orden: binding/ventana de evidencia → inventario habilitado → política vigente compatible → autenticación independiente. El registro no autentica la firma; la política no autentica el payload; solo el verificador puede devolver VERIFIED.

**Límite:** esta consulta es un gate previo y no cierra por sí sola una carrera de desactivación concurrente entre lectura y efecto. No se declara garantía de revocación/fencing hasta integrar un coordinador con consistencia en el punto de efecto. No se habilitan acciones de recuperación ni runtime.

**Estado: VALIDADO.** El propietario ejecutó 1110 tests en 8.196 s, todos OK.
## F2.3.32 — Binding de revisión del inventario

El servicio realiza una segunda lectura del inventario después de que el verificador criptográfico devuelve True. Solo mantiene VERIFIED si el registro sigue habilitado y conserva exactamente la revisión inicial. El resultado VERIFIED expone `issuer_registry_revision`. Si la revisión cambió durante la verificación, devuelve DENIED; si el inventario falla en la relectura, devuelve UNAVAILABLE. Se añadieron pruebas de desactivación concurrente, cambio de revisión aunque siga habilitado, fallo de la segunda lectura y validación del contrato de resultado.

**Límite:** esto detecta cambios durante el intervalo de verificación, pero no cierra la ventana posterior al retorno. No es fencing ni una garantía de atomicidad en el punto de efecto. No se habilita recuperación ni runtime.

**Estado: VALIDADO por el propietario; suite completa: 1131 tests en 10.314 s, todos OK.**


## F2.3.33 — Contrato de admisión de evidencia verificada

Se incorporan un comando inmutable de admisión y un puerto transaccional. El comando se deriva exclusivamente de un resultado VERIFIED y liga admission_id, operation_id, evidence_id, issuer_id, issuer_registry_revision, evidence_kind y todos los targets/revisiones. Se prueban la procedencia VERIFIED, la identidad exacta de la evidencia, la coincidencia de operación/objetivos, la revisión positiva, UTC y canonicalización.

El contrato del puerto exige que el futuro adaptador haga en una única frontera transaccional/fencing la comprobación de revisión vigente y emisor habilitado, el binding contra la operación/claims durables y la prevención de replay/reutilización. Una lectura puntual seguida de escritura separada no será conforme.

**Fuera de alcance:** no se implementa todavía el adaptador SQLite, no hay registro durable de admisiones y el resultado nunca permite efectos. No se conecta runtime ni recuperación automática.

**Estado: VALIDADO por el propietario; suite completa: 1131 tests en 10.314 s, todos OK.**

## F2.3.34 — Persistencia atómica de admisión de evidencia

Añadida migración SQLite v17 y `SQLiteRecoveryEvidenceAdmissionRepository`, compuesto dentro de `SQLiteLocalAuthorityUnitOfWork`. La admisión usa la misma transacción `BEGIN IMMEDIATE` para comprobar que el emisor sigue habilitado en la revisión exacta, que la operación permanece en un estado recuperable y que los targets/revisiones coinciden exactamente con el conjunto completo de claims. Los recibos guardan el comando canónico y digest SHA-256; admission_id y evidence_id son únicos e inmutables. Un replay exacto devuelve REPLAYED; una evidencia reutilizada o un binding distinto se rechaza.

Pruebas añadidas para persistencia, replay, revisión obsoleta, emisor deshabilitado, discrepancia de objetivos, reutilización de evidencia y trigger de revisión vigente.

**Límite:** la transacción solo hace atómica la admisión local. No protege un efecto posterior ni habilita recuperación/runtime. ADMITTED no es autoridad de ejecución.

**Estado: VALIDADO por el propietario; suite completa: 1131 tests en 10.314 s, todos OK.**

La verificación VERIFIED queda ligada también a un digest canónico SHA-256 de la evidencia completa. El comando de admisión exige coincidencia de ese digest, no solo de evidence_id, evitando reutilizar una verificación con un objeto alterado que conserve el mismo identificador.

### F2.3.35 — Auditoría de integridad de admisiones

Se añaden `audit_admission(admission_id)` y `audit_all()` como consultas de solo lectura sobre recibos de admisión persistidos. Verifican canonicalización y digest SHA-256 del comando, consistencia entre columnas y contenido, conjunto de objetivos frente a la reserva durable y timestamps UTC canónicos. El informe clasifica cada recibo como `HEALTHY` o `CORRUPT` con diagnósticos explícitos; una admisión desconocida devuelve `None`.

**Límite:** no autentica de nuevo la evidencia externa, no repara registros, no demuestra autoridad vigente ni permite ejecutar recuperación/efectos.

**Estado: VALIDADO por el propietario; suite completa: 1131 tests en 10.314 s, todos OK.**

### F2.3.36 — Concurrencia entre admisión y cambio de autoridad

Se añaden dos pruebas de integración con conexiones SQLite independientes sobre el mismo archivo. La primera enfrenta en paralelo una admisión con la desactivación del emisor y exige un resultado equivalente a uno de los dos órdenes seriales válidos: admisión confirmada antes de la desactivación, o rechazo por revisión obsoleta después de la desactivación. La segunda enfrenta dos admisiones exactas y exige un único ADMITTED, un REPLAYED y una sola fila persistida.

**Límite:** la garantía es local a la transacción SQLite de admisión. No protege un efecto externo posterior ni equivale a fencing distribuido. No se habilitan acciones ni runtime.

**Estado: VALIDADO por el propietario; suite completa: 1133 tests en 9.225 s, todos OK.**

### F2.3.37 — Consistencia temporal del emisor en auditoría histórica

Ampliar `audit_admission()` para comprobar que la revisión de emisor enlazada al recibo existía y estaba habilitada en el momento de registro, que su `changed_at` no es posterior a `recorded_at`, y que ninguna revisión posterior del mismo emisor tenía una fecha efectiva igual o anterior a la admisión. Las revisiones posteriores efectivas después de `recorded_at` deben conservar el recibo como históricamente sano.

Pruebas añadidas para cambio posterior válido y revisión posterior retrodatada que debe producir corrupción diagnóstica.

**Límite:** no autentica la fuente del timestamp ni el reloj; no modifica recibos, no autoriza efectos y no habilita recuperación/runtime.

**Estado: VALIDADO por el propietario; suite completa: 1135 tests en 9.444 s, todos OK.**

### F2.3.38 — Auditoría global de relaciones de admisión

Ampliar la auditoría para detectar referencias a operaciones inexistentes, revisiones de emisor ausentes, duplicados de `evidence_id` y discrepancias entre objetivos reservados y claims. La auditoría debe aceptar la liberación histórica de claims únicamente cuando exista recibo de liberación, la operación sea terminal y los objetivos terminales coincidan con los reservados.

El informe global expone códigos diagnósticos consolidados y `is_healthy`. Se añade una prueba que elimina deliberadamente un claim tras retirar el trigger protector y confirma que la auditoría detecta la inconsistencia sin repararla.

**Límite:** solo lectura; sin reparación, autorización, ejecución de efectos ni integración runtime.

**Estado: VALIDADO por el propietario; suite completa: 1136 tests en 9.985 s, todos OK.**
### F2.3.39 — Validación semántica de tipos persistidos

Comprobar que los valores persistidos de `evidence_kind` y `authority_kind` pertenecen a sus enums canónicos, incluso si la columna, el payload y la reserva coinciden entre sí. Añadir pruebas de corrupción controlada para ambos casos y verificar que `audit_admission` y `audit_all` los reportan como corruptos.

**Límite:** auditoría de solo lectura; sin cambios de esquema, reparación, autoridad, ejecución de efectos ni integración runtime.

**Estado: VALIDADO por el propietario; suite completa: 1138 tests en 8.814 s, todos OK.**

### F2.3.40 — Orden temporal del historial de emisores

Comprobar que `changed_at` no retroceda entre revisiones consecutivas del inventario de un emisor. Fechas iguales son válidas; una fecha estrictamente anterior en una revisión posterior produce `REGISTRY_TIMESTAMP_REGRESSION` y clasificación corrupta. Añadir una prueba de corrupción controlada.

**Límite:** solo lectura; no autentica el reloj, no modifica el esquema, no bloquea reactivaciones legítimas ni habilita efectos o runtime.

**Estado: VALIDADO por el propietario; suite completa: 1139 tests en 8.811 s, todos OK.**
