# Atlas funcional de prueba — plan de trabajo

> Prioridad acordada: 16 de noviembre de 2026.
> Corte de estado: 22 de noviembre de 2026.
 > Rama de trabajo actual: `work/atlas-mvp-runtime` (derivada de `main`).
> Objetivo: convertir la base conversacional existente en un asistente local capaz de completar flujos útiles de principio a fin en un entorno de prueba.
> Este plan no declara Atlas listo para producción.


## Avance y reordenamiento del MVP — 22 de noviembre de 2026

El objetivo inmediato se reduce a una primera versión local que sea útil sin esperar a que todos los subsistemas estén completos.

### Incremento actual: vista previa de planes

En `work/atlas-mvp-runtime` se conectó el planificador F1 a la consola mediante `/plan <solicitud>`. El comando:

- usa el intérprete de intenciones Ollama con salida JSON;
- reconoce únicamente las capacidades declaradas actualmente (`workspace.list` y `workspace.read`);
- muestra objetivo, parámetros y resultado esperado;
- pide aclaración o rechaza solicitudes fuera del catálogo;
- no ejecuta capacidades ni toca archivos;
- informa que el runtime protegido aún no está habilitado.

Pruebas focalizadas añadidas, todavía **pendientes de ejecución local**:
`python -m unittest tests.unit.test_console_planning tests.unit.test_local_console_composition -v`

No se ejecutaron pruebas ni compilaciones desde GitHub.

### Secuencia acelerada para llegar al primer uso con archivos

1. **F1 — Planificación en consola:** completar revisión y validación local de `/plan`.
2. **3.2-C — Autenticación local confiable:** completar bootstrap del propietario, control de intentos, clave de attestation y admisión de proof. No usar `getuser()`, UID/GID ni contexto sintético como identidad Atlas.
3. **3.2-C4 — Frontera de consola:** construir contexto de operación desde evidencia USER verificada; revalidar dentro de la misma UoW.
4. **F2 — Workspace read-only:** conectar exclusivamente `workspace.list` y `workspace.read` mediante el gate CAM ya existente, con Project/Environment/association activos, mount confiable y Grant exacto.
5. **MVP 0.1:** conversación persistente, planes visibles y lectura controlada de un Workspace de prueba. Escritura, shell, Docker, Skills, Broker, agentes y tareas autónomas quedan fuera.

**Dependencia crítica:** el servicio de Workspace no se conectará directamente a la consola actual porque `LocalConsoleRequestFactory` fabrica una identidad sintética. La infraestructura CAM/Workspace ya existe, pero no sustituye la autenticación de la frontera.


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

**Estado:** F2.1 (`workspace.list`) validada con 893/893 pruebas. F2.2 (`WorkspaceListingService`) implementada y validada por el propietario con 900/900 pruebas. El Ciclo 1 amplía la lectura con `WorkspaceFile`, `WorkspaceFileReader`, `WorkspaceFileReadingService` y `LocalWorkspaceAdapter.read_file`, además del catálogo cerrado `CapabilityCatalog` para `workspace.list` y `workspace.read`. Se añadieron pruebas unitarias para confinamiento de rutas, enlaces simbólicos, archivos UTF-8, límite de tamaño, resultados y catálogo. **Ciclo 1 VALIDADO por el propietario: suite completa de 1,157 tests en 9.853 s, todos OK; `compileall` también finalizó sin errores.** El Ciclo 2 incorpora `WorkspaceFileWritingService` y `LocalWorkspaceWriteAdapter` con staging durable, commit explícito, idempotencia por `operation_id`, comprobación SHA-256 del destino y evaluación de recuperación de solo lectura. Se añadieron pruebas de staging, creación/actualización, colisiones, corrupción y crash después del rename. **Ciclo 2 VALIDADO por el propietario: suite completa de 1,182 tests en 9.769 s, todos OK.** La escritura permanece fuera del catálogo y del runtime; este protocolo de archivos no constituye autorización CAM ni fencing frente a escritores externos. F2.3 documenta la separación entre revisión del plan, autorización CAM y aprobación humana. F2.3.1 añadió los contratos `OperationAuthorizationEvidence`, `OperationAuthorizationResult` y `OperationAuthorizationPort`, validados por el propietario con 913/913 pruebas. F2.3.2 añade el puerto de verificación confiable y `OperationAuthorizationEvidenceVerificationService`, validado por el propietario con 922/922 pruebas. F2.3.3a amplía la evidencia para incluir revisiones explícitas de proyecto y entorno; el propietario validó 925/925 pruebas. F2.3.3b inspeccionó las fuentes de autoridad y documentó por qué todavía no es seguro crear un adaptador de verificación genérico: no existe un coordinador concreto de invalidación/fencing en esta rama. El incremento Ciclo 3.1 añade `WorkspaceCapabilityExecutionService`: valida identidad canónica, proyecto/entorno activos, Grant exacto y revisión explícita; ejecuta `workspace.list`/`workspace.read` dentro de la UoW SQLite compartida. Se corrigió además `get_environment()` para respetar esa UoW. **Ciclo 3.1 VALIDADO por el propietario: suite completa de 1,194 tests en 9.318 s, todos OK.** Este gate es local y read-only; no implementa un coordinador genérico, verificación de evidencia externa ni Approval Manager. No está conectado a consola/runtime.

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

- Trabajar sobre la rama de incremento vigente, actualmente `design/verified-agent-delegation-i3-2b`; integrar a `main` solo después de validación y revisión documental.
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

**Estado actualizado (18 de noviembre de 2026):** 7B.6B queda cerrada tras la validación en Debian sobre `main` (`f0070dd`): 37 pruebas focalizadas OK en 2.342 s, `compileall` con código 0 y `main...origin/main` sincronizado (0/0). La suite completa de 1,513 pruebas también había sido reportada como OK. **Siguiente incremento propuesto: 7B.6C**, cuyo alcance es un inventario exhaustivo de imports/call-sites y la verificación de que no queda una ruta alternativa de transición lifecycle. Antes de cualquier cambio de código, debe hacerse una auditoría read-only de esos puntos y sus exports. La consola continúa sin identidad autorizada: `LocalConsoleRequestFactory` no debe convertirse en autoridad. Después de cerrar el lifecycle y la frontera de identidad, continuar la integración funcional F3–F5. No conectar runtime privilegiado, Broker ni herramientas de consola por la sola presencia de contratos o adaptadores.


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

### F2 — Ciclo 3.1: gate CAM local para lectura de workspace

`WorkspaceCapabilityExecutionService` acepta un `AssistantPlan` de un solo paso y requiere `review_confirmed=True` como confirmación de intención (no como permiso). Revalida que el actor coincida exactamente con el par canónico UserId/Identity de SQLite, exige proyecto y entorno existentes y activos, y consulta Grants por propietario canónico. `workspace.list` requiere un Grant para el workspace exacto; `workspace.read` requiere un Grant `workspace_file` para el ID JSON canónico `[workspace_id, path]`. Solo después de `AuthorizationEvaluator.ALLOW` ejecuta el lector/listador.

La UoW usa `BEGIN IMMEDIATE` y se mantiene abierta durante la lectura del filesystem, de modo que las mutaciones de autoridad SQLite sobre esa misma base no puedan intercalarse entre la comprobación y la lectura. `get_environment()` ahora usa la conexión de la UoW, igual que Project, Identity y Grants. Esto es una garantía local de la composición SQLite, no fencing distribuido ni protección contra cambios de configuración externos.

**Límites:** solo capacidades READ_ONLY; sin `workspace.write`, shell, aprobación `REQUIRE_APPROVAL`, ejecución multi-paso, verificación criptográfica de evidencia, coordinador genérico ni integración en `cli.py`. La política inicial considera que los workspaces configurados pertenecen al UserId canónico de la sesión. **VALIDADO por el propietario: suite completa de 1,194 tests en 9.318 s, todos OK.**


## 9. Fundamento operativo transversal — Atlas Workstation

**Diseño aprobado; implementación pendiente.** La especificación se encuentra en [Atlas Workstation](design/atlas-workstation.md).

Atlas Workstation será el entorno aislado donde Atlas realizará trabajo de proyecto y ejecutará tareas. Separa el workspace persistente de cada proyecto del runtime efímero de cada tarea. La implementación objetivo usa contenedores confinados, no acceso directo al host.

El trabajo se organiza en W0–W6:
- W0: diseño y límites (documentado).
- W1: workspace persistente y ownership canónico.
- W2: contrato del adaptador de runtime y evaluación de Atlas Broker.
- W3: runtime confinado mínimo, sin red por defecto.
- W4: catálogo cerrado de tareas y seguimiento durable.
- W5: terminal interactiva limitada, solo tras validar el aislamiento.
- W6: experiencia multiplataforma.

Workstation no es una autorización independiente. CAM y las aprobaciones siguen siendo obligatorias; Assistant, agentes y Skills no reciben Docker socket, root ni shell irrestricta. El siguiente paso inmediato continúa siendo el Ciclo 3.2 (bootstrap confiable, contexto canónico y ownership de workspaces). La documentación W0 no implica ejecución habilitada ni cambios en el servidor.


## 10. Subsistema transversal — Memory Engine

**Estado: infraestructura de dominio y autoridad parcialmente implementada; ciclo de memoria de producto e integración con Assistant pendientes.** Memory Engine es un subsistema propio de Atlas, no un sinónimo del historial conversacional ni una tabla adicional de conversaciones.

### 10.1 Base implementada conocida

- Modelos y contratos de memoria, versiones, propuestas, scopes, clasificación, estado y procedencia.
- Ámbitos PRIVATE y PROJECT y reglas de acceso asociadas.
- Memory Gateway y servicios/adaptadores de autorización de memoria.
- Journal de consistencia, posiciones, checkpoints y mecanismos/reducers de recuperación parcialmente implementados.
- Persistencia SQLite para parte de la autoridad, identidad, Grants, cambios de autoridad y estructuras de consistencia.
- UoW SQLite compartida para Identity, Grants, renovaciones, Project, Environment y ledger de cambios de autoridad, con operaciones transaccionales y pruebas de commit/rollback.
- Contratos y persistencia para inventario/política de emisores, verificación y admisión de evidencia de recuperación, con auditorías de integridad.
- El trabajo F2.3.40 y Cycle 3.1 valida un gate CAM local para lectura de workspace; no equivale a cerrar el Recovery Gate ni a completar Memory Engine.

### 10.2 Límites y trabajo pendiente

- No declarar durable y completo el contenido de memoria: la persistencia integral del contenido/versiones y sus adaptadores de producto aún debe verificarse y completarse.
- Completar los flujos de crear/proponer, revisar, almacenar, recuperar, actualizar, invalidar y olvidar recuerdos.
- Completar autorización de lectura y control de salida (egress) en el flujo real, no solo en contratos o servicios aislados.
- Completar composición protegida, autoridad confiable y condiciones de recuperación; el Recovery Gate permanece cerrado.
- Definir e implementar el ciclo de vida, retención, procedencia, aislamiento PRIVATE/PROJECT y auditoría de cada operación.
- Integrar Memory Engine con Assistant y el contexto de tareas sin duplicar el historial conversacional.
- Demostrar pruebas de reinicio, recuperación, revocación, aislamiento entre proyectos y resultados verificables.
- Evaluar y demostrar su desacoplamiento ejecutable de Atlas Core; no afirmar independencia de despliegue hasta probarla.

### 10.3 Relación con el contexto conversacional

El historial SQLite de conversaciones sigue siendo la fuente de continuidad de chat. La proyección actual al modelo está limitada a ocho turnos y 2.000 caracteres por mensaje. Memory Engine tendrá una función diferente: conservar conocimiento seleccionado y durable con autorización, scope, procedencia y políticas de ciclo de vida. No se sustituirá el historial por Memory Engine ni se copiarán todos los mensajes automáticamente.

**Criterio de salida:** Memory Engine puede completar operaciones reales de memoria, con persistencia y recuperación comprobables, autorización y aislamiento, auditoría y una integración explícita con Assistant. Contratos, reducers o pruebas unitarias aisladas no bastan para marcarlo como producto funcional.

## 11. Subsistema transversal — Atlas Broker

**Estado conocido al último reporte operativo del propietario: servicio separado desplegado en Debian para acceso controlado a Docker rootless; integración end-to-end con Atlas Core/Assistant no demostrada.** Broker es una frontera de ejecución acotada, no el planificador, la autoridad central ni una API para que el modelo ejecute comandos arbitrarios.

### 11.1 Despliegue y base operativa reportada

- Repositorio independiente `yon30c/atlas-broker`, separado del repositorio Atlas.
- Servicio systemd `atlas-broker.service`.
- Proceso de ejecución separado bajo la identidad técnica `atlas-sandbox`.
- Acceso al daemon Docker rootless mediante el socket de ese usuario técnico.
- Socket IPC Unix del Broker en `/run/atlas-broker/broker.sock`.
- Registry SQLite, perfiles de recursos y auditoría de operaciones.
- Controles de identidad del proceso cliente mediante credenciales del socket (SO_PEERCRED).
- Endurecimiento del servicio mediante restricciones systemd y separación del proceso de servicio.
- El propietario reportó pruebas automatizadas del Broker en distintos incrementos; los recuentos históricos pertenecen al repositorio Broker y no deben sumarse a la suite de Atlas Core.
- Este estado es una referencia documental del último reporte operativo conocido, no una verificación en vivo del servicio en este cambio documental.

### 11.2 Responsabilidades y límites

- Broker valida al caller y la forma/perfil de la operación según su política local.
- Ejecuta únicamente operaciones Docker predefinidas y limitadas; no debe convertirse en un proxy de shell ni aceptar argumentos arbitrarios del LLM.
- El modelo, Assistant, agentes, Skills y contenedores de tareas nunca reciben directamente docker.sock ni privilegios del host.
- Broker no sustituye CAM: Atlas Core conserva identidad canónica, proyecto, entorno, Grants, aprobaciones, tareas y decisión de autoridad.
- SO_PEERCRED identifica credenciales del proceso conectado, pero por sí solo no prueba que la operación esté autorizada en CAM ni que el proceso represente una sesión humana válida.
- El despliegue separado no demuestra que exista integración con `cli.py`, Assistant, Task Manager o Workstation Coordinator.
- Una operación con resultado incierto requiere estado durable, idempotencia y reconciliación; no se reintenta por asumir que no ocurrió.

### 11.3 Integración pendiente con Atlas Core y Workstation

1. Definir un contrato tipado y versionado Core–Broker: operación, caller, proyecto, entorno, workspace, tarea, perfil, límites, idempotency key y correlación.
2. Definir cómo la decisión CAM y la aprobación humana se vinculan a la solicitud exacta y cómo Broker verifica el binding sin convertirse en autoridad paralela.
3. Definir autenticación IPC, autorización por operación, protección contra replay, timeouts, cancelación y semántica de resultado desconocido.
4. Definir lifecycle de runtime: crear, inspeccionar, detener, destruir, expiración/lease, limpieza y recuperación.
5. Vincular auditoría de Core y Broker mediante IDs y digests correlacionables.
6. Implementar un adaptador de Workstation que invoque solo operaciones Broker permitidas.
7. Ejecutar pruebas E2E en entorno descartable: denegación, permisos mínimos, aislamiento entre proyectos, límites de recursos, red deshabilitada por defecto, crash, timeout, replay, reconciliación y limpieza.
8. Verificar el servicio y su configuración en Debian antes de modificar el despliegue. No cambiar systemd, usuarios, grupos, socket, Docker ni privilegios sin autorización explícita del propietario.

**Criterio de salida:** una tarea autorizada en Atlas Core llega al runtime confinado a través de un adaptador Broker; la operación y el resultado quedan correlacionados y auditados; los casos de denegación, fallo, incertidumbre, recuperación y aislamiento pasan E2E. El despliegue independiente del Broker no basta.

## 12. Orden de integración y dependencias

La secuencia de trabajo queda actualizada así:

1. **Cycle 3.2 — contexto canónico y workspace confiable:** cerrar la identidad canónica de la consola, la selección de proyecto/entorno y el ownership/ruta confiable del workspace. No convertir la identidad sintética actual en autoridad.
2. **F3 — Task Manager mínimo:** entidad durable, pasos secuenciales, estados, progreso, resultados, cancelación y recuperación conservadora de tareas interrumpidas.
3. **F4 — continuidad + Memory Engine:** mantener el historial conversacional como historial; integrar memoria de producto mediante sus APIs autorizadas y persistencia real. Priorizar un flujo vertical pequeño de guardar/recuperar/invalidar con aislamiento y auditoría.
4. **F5 — experiencia E2E del Assistant:** conectar interpretación, revisión, autorización, ejecución de capacidades locales, Task Manager, continuidad y presentación de resultados verificables. No marcar escritura como disponible hasta cerrar su frontera transaccional y de efectos.
5. **Workstation W1/W2 — workspace persistente y contrato del runtime:** formalizar bindings y contrato de adaptador; evaluar Broker contra ese contrato sin habilitar aún operaciones Docker desde Assistant.
6. **Broker integration — Core–Broker–runtime:** implementar el adaptador solo después de cerrar identidad/contexto, autorización exacta, contratos y política de ejecución; comenzar con perfiles de prueba estrechos y recursos descartables.
7. **Bootstrap/privilege separation — B0–B7:** retomar la evaluación de separación de privilegios y bootstrap antes de conceder al servicio/helper nuevas capacidades privilegiadas. Candidate A no está aprobado; Candidate B sigue siendo alternativa de diseño. Recovery Gate permanece cerrado.
8. **Consolidación de producto:** Project/Environment Manager completos, Skills Manager, Agents, Scheduler, Approval Manager, Event Collector, Notification Manager y Atlas Workstation multiplataforma, siguiendo sus dependencias.

### Reglas de secuenciación

- Se puede continuar desarrollo aislado, documentación y pruebas no privilegiadas de Memory Engine y Broker mientras avanza Fase 4.
- No conectar Broker al runtime del Assistant solo porque el servicio esté activo.
- No abrir Recovery Gate para acelerar F4 ni tratar la persistencia parcial como autoridad protegida.
- No entregar Docker socket, root, shell irrestricta o permisos de host a modelos, Skills, agentes o contenedores.
- Cada estado se etiqueta separadamente como **implementado**, **desplegado**, **validado localmente**, **integrado** o **E2E verificado**.
- La prueba de un subsistema no se suma automáticamente a la suite de otro repositorio.

## 13. Decisión de despliegue: imagen Linux autónoma

**Estado: DECISIÓN ARQUITECTÓNICA ADOPTADA el 17 de noviembre de 2026.** Documento normativo: [Imagen Linux autónoma para desplegar Atlas](design/linux-image-deployment-decision.md).

Atlas tendrá como objetivo de despliegue una imagen Linux autónoma distribuida como imagen OCI compatible con Docker. Debian es la primera base candidata, pendiente de selección/versionado y validación durante la implementación. La decisión no cambia el entorno de desarrollo actual ni autoriza cambios en el host.

Principios:
- Atlas Runtime no dependerá del usuario Linux anfitrión ni se ejecutará como `greed` por necesidad.
- Identidad humana canónica de Atlas (`UserId`), identidad técnica del proceso y permisos del host permanecen separados.
- Atlas Broker continúa independiente; Atlas Runtime no recibe `docker.sock`, root ni modo privileged.
- Workspaces se entregan mediante mounts explícitos y configuración confiable; las rutas internas no se presumen iguales a las del host.
- SQLite, conversaciones, estado, memoria y demás datos durables deben residir en almacenamiento persistente explícito, no en la capa efímera del contenedor.
- Configuración, secretos, endpoints LLM y rutas se inyectan explícitamente; loopback dentro del contenedor no equivale al loopback del host.
- La imagen deberá construirse de forma reproducible, con dependencias fijadas, usuario no root y pruebas de aislamiento/recuperación.

### Impacto en trabajo existente

La decisión no invalida ni exige reescribir contratos Identity/CAM, Grants, Projects/Environments, Workspace adapters, el protocolo de escritura ni el gate read-only de Cycle 3.1. Introduce requisitos para su futura composición/despliegue:
- Cycle 3.2 debe resolver identidad canónica sin inferirla del UID/GID del proceso, y workspace confiable/ownership con rutas configuradas.
- Los límites de rutas y symlinks del adaptador local siguen siendo válidos; la raíz debe venir de configuración confiable y mounts explícitos.
- La garantía SQLite/UoW de Cycle 3.1 es local a la misma base/archivo y UoW; no se extiende automáticamente a réplicas, múltiples contenedores o filesystem de red.
- La ruta de conversaciones `~/.local/state/atlas/conversations.sqlite3` requiere volumen persistente explícito.
- Ollama configurado en `127.0.0.1:11434` dentro de un contenedor apunta al contenedor, no al host; el endpoint deberá configurarse según la topología.
- Los diseños de bootstrap/PAM no se convierten automáticamente en autenticación del contenedor.

**Cycle 3.2 sigue siendo la siguiente acción funcional y debe permanecer agnóstico al despliegue.** No es necesario construir la imagen para completarlo. No se modifica el estado de F2, F3–F5 ni se declara integración de runtime.

### Fuera de alcance

No se autoriza quitar `sudo` a `greed`, modificar sudoers/PAM/systemd/usuarios/grupos/SSH/Docker del host, cambiar sockets/permisos, instalar paquetes, mover Broker, montar directorios personales o migrar datos. Cualquier cambio de infraestructura requiere propuesta y autorización explícitas.

**Estado de implementación:** decisión documental adoptada; inventario de dependencias, contrato de runtime, Dockerfile, persistencia, pruebas de aislamiento y migración controlada siguen pendientes.


## 14. Autenticación nativa y portabilidad entre máquinas

**Estado: DIRECCIÓN DE PRODUCTO Y REQUISITO ARQUITECTÓNICO ADOPTADOS el 17 de noviembre de 2026.** Documento: [Autenticación nativa y portabilidad entre máquinas](design/native-authentication-and-machine-portability-decision.md).

Atlas debe poder instalarse en un host diferente sin depender de la cuenta Linux, UID/GID, hostname, hardware, rutas personales, servicios locales implícitos ni secretos de la máquina de desarrollo.

Principios:
- Atlas tendrá autenticación propia, separada de las cuentas del sistema operativo.
- Authentication Authority verifica credenciales; Identity Authority resuelve el UserId/Identity(USER) canónico y la evidencia; CAM continúa autorizando cada operación.
- El primer usuario se crea mediante bootstrap de un solo uso, generado fuera de la imagen. No se crea desde `getuser()`, UID/GID ni hostname.
- El diseño soporta múltiples usuarios; el primer despliegue puede ser administrado por una sola persona.
- Contraseñas con Argon2id y sesiones opacas, revocables y expirables; no almacenar secretos reutilizables en claro.
- Imagen, configuración, datos persistentes y secretos son artefactos separados por instalación.
- Los endpoints LLM, workspaces, rutas, persistencia y mounts son configurables; no se asume que Ollama o cualquier servicio esté en loopback.
- La portabilidad de datos exige exportación, manifiesto, integridad, restauración, reconciliación de secretos/identidades y activación deliberada.
- Las sesiones no se trasladan como credenciales reutilizables; se revocan al migrar por defecto.
- La primera entrega no promete active-active, múltiples réplicas ni SQLite compartida entre hosts.

### Impacto en Cycle 3.2

Cycle 3.2 debe implementar contexto canónico sin depender de la máquina:
- identidad autenticada desde Authentication Authority;
- VerifiedIdentityContext emitido por Identity Authority;
- proyecto y entorno resueltos desde fuentes canónicas;
- workspace registrado con owner, proyecto, entorno y raíz lógica confiable;
- mapeo explícito entre ruta lógica y mount físico de cada instalación;
- denegación ante sesión, identidad, proyecto, entorno o workspace no verificables.

La consola no puede fabricar identidad ni contexto verificado. La conversación sin login, si se permite, no habilita capacidades protegidas.

**Estado de implementación:** decisión adoptada; contratos detallados, autenticación, bootstrap, portabilidad de datos, empaquetado, migración y pruebas siguen pendientes. No se autoriza cambiar el host ni migrar datos existentes.


### F2 — Cycle 3.2-A: registro canónico de Workspaces

**Estado:** implementación en rama de trabajo; pendiente de verificación del propietario. La migración aditiva v18 añade asociaciones explícitas muchos-a-muchos Project–Environment y registros de workspace con owner canónico, ámbito compuesto y `root_ref` simbólico `mount:<id>`. No se infieren asociaciones históricas ni se crean workspaces por defecto. Los registros conservan tombstones; identidad, owner, ámbito y root_ref del workspace son inmutables; las actualizaciones de estado usan revisión CAS. La creación requiere un owner existente y una asociación Project–Environment activa. `SQLiteWorkspaceRegistryRepository` queda expuesto como `unit.workspaces` dentro de `SQLiteLocalAuthorityUnitOfWork`. Se añadieron pruebas unitarias para integridad referencial, ownership, asociación activa, CAS, inmutabilidad, validación de root_ref y rollback. **No declarar validado hasta recibir la salida de la suite en Debian.**

Cycle 3.2-A no conecta CLI/runtime, no modifica `WorkspaceCapabilityExecutionService`, no resuelve mounts a rutas físicas y no habilita autenticación ni capacidades protegidas. El siguiente incremento es 3.2-B: resolver `root_ref` desde configuración confiable y revalidar owner, Project, Environment, asociación activa y Grant exacto dentro de la misma UoW antes de filesystem.


## 15. Estado de Cycle 3.2 / I3-2B y lifecycle Project–Environment (18-11-2026)

La rama `design/verified-agent-delegation-i3-2b` contiene incrementos de identidad nativa, identidad verificada, delegación AGENT, renovación delegada y lifecycle de asociaciones. Este trabajo amplía las precondiciones de autoridad necesarias para el futuro flujo funcional, pero **no equivale a conectar esas capacidades al Assistant ni a habilitar un runtime AGENT**.

### Implementado en la rama

- Autenticación nativa con credenciales Argon2id, autenticadores y proofs de un solo uso; persistencia separada de Authentication Authority e Identity Authority.
- Identidad canónica USER/AGENT y bindings nativos separados.
- Emisión y revocación de delegaciones por el propietario verificado; scopes explícitos y evidencia AGENT de corta duración.
- Renovación delegada de Grants con acción CAM explícita, cobertura exacta de recursos y revalidación de identidad, Grant, delegación y asociación Project–Environment.
- Bootstrap local de Platform Admin y lifecycle de asociaciones con eventos inmutables, CAS, ledger y servicio de aplicación.
- 7B.6A auditó la frontera de escritura lifecycle; 7B.6B separó los repositorios de lectura/Workspace del writer lifecycle y limitó ese writer a la composición confiable.

### Validación conocida

El propietario reportó en Debian la suite completa: **1,513 tests — OK** (30.071 s). Posteriormente, sobre `main` en HEAD `f0070dd`, ejecutó los cuatro módulos focalizados: **37 tests — OK** (2.342 s), y `python -m compileall -q src tests` terminó con `COMPILE_EXIT_CODE=0`. `main...origin/main` devolvió `0 0`. Con esta evidencia, 7B.6B queda cerrada en el alcance validado. La evidencia es local y no representa GitHub Actions, E2E ni despliegue productivo.

### Secuencia de 7B.6C (propuesta; auditoría read-only)

1. Inventariar todos los imports del writer lifecycle, su implementación concreta y los módulos que pueden obtener una referencia.
2. Localizar todos los call-sites de transición Project–Environment, incluyendo factories, composición, repositorios, servicios y tests.
3. Revisar exports públicos (`__init__`, módulos de paquete y puntos de composición) para detectar exposición accidental del writer.
4. Buscar rutas alternativas de escritura que evadan el servicio lifecycle o la UoW autorizada.
5. Clasificar cada hallazgo como permitido, interno, obsoleto o exposición que requiere corrección; adjuntar rutas y líneas.
6. No modificar código durante el inventario. Presentar hallazgos y propuesta de corrección antes de implementar cambios.

No habilitar runtime ni cambiar las fronteras de autoridad como parte de esta auditoría.

Documentos de diseño: [auditoría 7B.6A](design/i3-2b-7b6a-lifecycle-write-boundary-audit.md), [separación 7B.6B](design/i3-2b-7b6b-lifecycle-write-capability-separation.md) y [auditoría CAM de renovación AGENT](design/i3-2b-cam-renewal-integration-audit.md).
