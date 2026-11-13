# Contrato de eventos

**Estado:** contrato de dominio.  
**Base normativa:** `Contrato-de-diseno-Atlas-v1.md`, especialmente §§ 4.7, 10 y 17.4.  
**Alcance:** definir la naturaleza, estructura lógica, límites y responsabilidades de los eventos de Atlas.  
**Implementación:** este documento no declara implementados Event Collector, Event Store, Analysis Engine ni SecurityAudit.

## 1. Propósito

Un evento representa un hecho que ha ocurrido dentro de Atlas o en una fuente observada por Atlas y que debe conservarse para trazabilidad, correlación o análisis posterior.

Los eventos permiten reconstruir qué ocurrió y bajo qué contexto, sin convertir el registro de un hecho en una autorización o instrucción para ejecutar acciones.

## 2. Modelo lógico

`DomainEvent` representa un hecho inmutable. Su estructura lógica debe contemplar, según corresponda a la naturaleza del evento, los siguientes campos:

| Campo | Significado |
|---|---|
| `event_id` | Identificador único del evento. |
| `event_type` | Tipo de hecho registrado. |
| `schema_version` | Versión del esquema utilizado para representar el evento. |
| `occurred_at` | Instante UTC en que ocurrió el hecho. |
| `observed_at` | Instante UTC en que Atlas detectó u observó el hecho. |
| `project_id` | Proyecto al que pertenece el evento, cuando corresponda. |
| `source` | Identificación de la fuente que produjo u originó el evento. |
| `actor` | Identidad asociada al actor, cuando corresponda. |
| `classification` | Clasificación de seguridad conforme al catálogo aprobado en el contrato principal. |
| `severity` | Severidad del evento conforme al catálogo aprobado. |
| `subject` | Entidad o recurso al que se refiere el evento, cuando corresponda. |
| `data` | Datos estructurados necesarios para describir el hecho. |
| `correlation_id` | Identificador que permite relacionar el evento con un contexto de trabajo. |
| `deduplication_key` | Clave opcional para identificar eventos duplicados o relacionados. |
| `evidence` | Referencias a evidencias asociadas al evento, cuando corresponda. |
| `related_event_ids` | Identificadores de otros eventos relacionados, cuando corresponda. |
| `context`	| OperationContext asociado al evento, que conserva el contexto de la operación. |

Los campos opcionales deben utilizarse según la naturaleza del evento. Su ausencia no invalida un evento cuando el campo no resulte aplicable.

El `OperationContext` asociado conserva el contexto de operación de Atlas. La información de `source` y `actor` describe, respectivamente, el origen del evento y la identidad del actor. Estos conceptos no deben considerarse equivalentes automáticamente a `context.origin` o `context.actor`.

La correlación del evento debe conservarse de manera coherente con `context.correlation_id`.

La representación interna del código podrá utilizar nombres o estructuras diferentes, siempre que preserve la semántica de los campos definidos por el contrato principal y permita su correspondencia inequívoca.

La representación física podrá variar, pero deberá preservar la semántica y las garantías de este contrato.

## 3. Inmutabilidad y conservación

**APROBADO:**

- Los eventos son inmutables una vez registrados.
- El registro es append-only: un evento existente no se modifica ni se sustituye por una versión corregida.
- La retención de eventos es indefinida.
- Un error en un evento registrado se documenta mediante otro evento relacionado; no se reescribe el registro histórico.
- La separación entre eventos e incidencias es obligatoria.

La inmutabilidad comprende tanto los campos del evento como los datos que contiene. No basta con impedir la reasignación de atributos del objeto si las estructuras internas continúan siendo modificables.

La implementación deberá evitar que modificaciones posteriores de un objeto externo alteren los datos de un evento ya construido o registrado.

La retención indefinida es una decisión de diseño aprobada. No determina por sí sola el formato físico, el almacenamiento, la replicación ni la estrategia de respaldo.

## 4. Clasificación y datos

`classification` utilizará exclusivamente los valores definidos en §4.7 del contrato principal:

- `public`
- `internal`
- `sensitive`
- `restricted`

Estos valores constituyen el catálogo aprobado de clasificación general de eventos. No deben introducirse categorías alternativas ni valores adicionales para representar restricciones particulares de un canal de notificación.

La clasificación debe conservarse con el evento y aplicarse conforme a las políticas de acceso y tratamiento correspondientes.

### Severidad

El campo `severity` utilizará exclusivamente los valores definidos en §4.7 del contrato principal:

- `critical`
- `important`
- `informational`
- `debug`

La severidad representa la importancia operativa del evento y no debe confundirse con su clasificación de seguridad.

**APROBADO:**

- Los valores de severidad están controlados.
- No se puede declarar arbitrariamente un evento como `critical`.
- La asignación debe respetar las reglas y criterios aprobados para el tipo de evento.

Permanecen pendientes las definiciones operativas completas y los mecanismos técnicos para aplicar los criterios de severidad.

### Reglas técnicas pendientes de clasificación

Permanecen pendientes las reglas técnicas completas para:

- Asignar una clasificación según el tipo de evento y su contenido.
- Propagar o determinar la clasificación cuando intervengan varias fuentes.
- Aplicar restricciones de lectura, exportación y visualización.
- Tratar datos personales o sensibles sin debilitar la retención indefinida.
- Anonimizar o limitar información cuando corresponda, conservando la integridad del registro.

Los atributos deben limitarse a información necesaria para describir el hecho. No deben incluir secretos, credenciales, tokens ni payloads sensibles innecesarios.

La serialización debe preservar el significado de los datos y permitir su recuperación sin convertir referencias externas en permisos de acceso.

## 5. Contexto y correlación

Todo evento debe conservar el `OperationContext` que permita identificar el contexto en el que se produjo.

La correlación utiliza `context.correlation_id`.

La correlación agrupa eventos relacionados con un mismo contexto de trabajo, pero no demuestra por sí sola:

- Que los eventos hayan ocurrido en un orden causal determinado.
- Que un evento haya causado otro.
- Que todos los eventos de una operación estén necesariamente presentes.
- Que la operación haya terminado correctamente.
- Que el actor tuviera autorización para realizar una acción.

La identidad del actor y la autorización deben interpretarse conforme a los contratos de identidad, contexto y autorización. La presencia de un evento no sustituye la evaluación de CAM.

El orden causal, la relación entre eventos y operaciones y los criterios de completitud de una secuencia quedan pendientes de especificación técnica.

## 6. Eventos, observaciones, conclusiones e incidencias

Estos conceptos no son intercambiables:

- **Evento:** hecho registrado que ocurrió en Atlas o en una fuente observada.
- **Observación:** dato obtenido mediante la observación de una fuente o recurso. Puede originar un evento, pero no equivale automáticamente a una conclusión.
- **Conclusión:** resultado derivado del análisis de uno o varios eventos u observaciones. Debe conservar su relación con la evidencia que la sustenta y no presentarse como un hecho original.
- **Incidencia:** entidad de seguimiento separada que agrupa y gestiona una situación que requiere atención. Puede relacionarse con eventos y conclusiones, pero no reemplaza ni modifica los eventos originales.

El análisis no transforma retroactivamente una conclusión en un evento ocurrido.

La creación, actualización y resolución de incidencias pertenece a su propio contrato. No se define aquí un modelo de incidencias ni se les atribuye autoridad para ejecutar operaciones.

## 7. EventStore

`EventStore` define la frontera lógica de persistencia y consulta de eventos.

El puerto actual declara:

- `append(event)`: registrar un evento.
- `by_correlation(correlation_id)`: recuperar los eventos asociados a una correlación.

Estas operaciones no conceden permisos ni ejecutan acciones sobre los recursos descritos por los eventos.

La implementación deberá respetar:

- La inmutabilidad de los eventos registrados.
- La retención indefinida aprobada.
- La clasificación y los controles de acceso aplicables.
- La conservación del contexto y la correlación.
- La separación entre registro de eventos y gestión de incidencias.

No se presume idempotencia de `append()` ni deduplicación automática por `event_id`. Esas garantías solo podrán establecerse mediante una especificación explícita de la operación.

### Deduplicación e idempotencia

El campo `deduplication_key` es opcional y debe incluirse cuando exista una clave estable que resulte útil para identificar eventos duplicados o relacionados.

La ausencia de `deduplication_key` no invalida un evento que, por lo demás, sea válido.

La deduplicación de eventos y la idempotencia de operaciones son mecanismos independientes.

La presencia de una `deduplication_key` no demuestra que `append()` sea idempotente ni garantiza que un proveedor externo impida la repetición de una operación.

Cualquier garantía de deduplicación deberá establecerse mediante una especificación explícita del comportamiento esperado, sin atribuir a la clave garantías que no hayan sido definidas.

Tampoco se establece todavía un orden global de lectura, entrega garantizada, suscripciones, reintentos o semántica de procesamiento exactamente una vez.

## 8. Límites de autoridad

Los eventos son registros de hechos, no órdenes.

- Event Collector valida y registra eventos; no los convierte en instrucciones de ejecución.
- Watchers observan fuentes autorizadas y publican eventos; no modifican recursos protegidos.
- Analysis Engine analiza eventos y produce conclusiones o propuestas; no ejecuta cambios.
- Atlas Assistant puede explicar eventos y resultados de análisis dentro de sus permisos, pero no obtiene autoridad por consultar el registro.
- EventStore conserva y recupera eventos; no decide autorizaciones.
- SecurityAudit mantiene su diseño aprobado y su implementación postergada. El contrato de eventos no implica que SecurityAudit esté implementado ni que EventStore lo sustituya.

El acceso y la exportación de eventos deberán respetar identidad, autorización, clasificación y alcance del solicitante.

## 9. Parámetros técnicos pendientes

Las siguientes decisiones técnicas permanecen pendientes y no reabren las garantías ni los catálogos aprobados en el contrato principal.

1. Catálogo completo y versionado de tipos de eventos.
2. Definiciones operativas y reglas de asignación de severidades, respetando los valores aprobados.
3. Reglas de aplicación y tratamiento de las clasificaciones de §4.7.
4. Correspondencia entre el modelo lógico del contrato y las estructuras internas utilizadas por la implementación.
5. Formato físico y tecnología de almacenamiento.
6. Mecanismos de integridad criptográfica.
7. Acceso, consulta y exportación.
8. Límites de almacenamiento, alertas y operación.
9. Reconciliación de efectos externos y resultados inciertos.
10. Semántica de orden, causalidad y deduplicación cuando corresponda.
11. Mecanismos de privacidad y anonimización compatibles con la retención indefinida.
12. Reglas técnicas para preservar referencias a evidencias y eventos relacionados.

Los siguientes elementos ya están aprobados y no deben tratarse como decisiones pendientes:

- Clasificaciones: `public`, `internal`, `sensitive` y `restricted`.
- Severidades: `critical`, `important`, `informational` y `debug`.
- `deduplication_key` opcional.
- La ausencia de `deduplication_key` no invalida un evento.
- La deduplicación no sustituye la idempotencia de operaciones.
- Retención indefinida, inmutabilidad y registro append-only.

No se selecciona todavía un broker, base de datos, transporte, mecanismo de entrega ni despliegue.

## 10. Correspondencia con el código actual

La inspección del repositorio `main` muestra:

- `DomainEvent` está definido en `src/atlas/assistant/models.py`.
- El modelo actual contiene `event_id`, `event_type`, `occurred_at`, `context` y `attributes`.
- `event_id` utiliza `UUID`.
- `occurred_at` exige fecha y hora con zona UTC.
- `context` debe ser una instancia de `OperationContext`.
- `attributes` acepta un mapping de cadenas a cadenas.
- La dataclass es congelada, pero el mapping recibido puede seguir siendo mutable.
- El modelo todavía no contiene el campo `classification` exigido por el contrato principal.
- `EventStore` está definido en `src/atlas/ports/event_store.py` y declara únicamente `append()` y `by_correlation()`.
- Las pruebas actuales verifican la creación de un evento y el rechazo de una fecha sin zona horaria, pero no demuestran inmutabilidad profunda, retención, persistencia, clasificación ni comportamiento de un EventStore real.

Esta correspondencia describe el código inspeccionado. No constituye una certificación de funcionamiento ni de integración.

Las diferencias entre el modelo actual y el contrato deberán resolverse durante la implementación correspondiente, sin debilitar las decisiones aprobadas.

## 11. Criterios de aceptación

Antes de considerar implementado el sistema de eventos deberán verificarse, como mínimo:

| ID | Invariante | Resultado exigido |
|---|---|---|
| EVT-01 | Identidad | Cada evento tiene un identificador válido. |
| EVT-02 | Tiempo | Los eventos rechazan instantes que no cumplan el contrato UTC. |
| EVT-03 | Contexto | Todo evento conserva un `OperationContext` válido. |
| EVT-04 | Clasificación | Cada evento conserva una clasificación válida del catálogo aprobado. |
| EVT-05 | Inmutabilidad | No es posible alterar un evento ni sus datos después de construirlo o registrarlo. |
| EVT-06 | Append-only | Un evento registrado no puede modificarse ni sustituirse. |
| EVT-07 | Correlación | La consulta devuelve los eventos asociados a la correlación solicitada, sin mezclar otras correlaciones. |
| EVT-08 | Retención | La implementación respeta la retención indefinida aprobada. |
| EVT-09 | Privacidad | No se exponen eventos sin autorización y tratamiento de clasificación adecuados. |
| EVT-10 | Separación | Las incidencias y conclusiones no sustituyen ni reescriben eventos originales. |
| EVT-11 | Autoridad | La lectura o publicación de un evento no concede permisos ni ejecuta operaciones. |
| EVT-12 | Fallos | Los errores de persistencia o consulta no se presentan como registros completados. |
| EVT-13 | Estructura lógica | El evento conserva los campos aplicables de §4.7 del contrato principal. |
| EVT-14 | Tiempo de observación | Cuando corresponda, `observed_at` conserva el instante UTC en que Atlas detectó el hecho, sin confundirlo con `occurred_at`. |
| EVT-15 | Origen y actor | La fuente y el actor se representan sin confundirlos automáticamente con el origen o actor del `OperationContext`. |
| EVT-16 | Severidad | Cada evento utiliza un valor permitido del catálogo aprobado y respeta las reglas de asignación. |
| EVT-17 | Deduplicación opcional | La ausencia de `deduplication_key` no invalida un evento. |
| EVT-18 | Separación de garantías | La presencia de `deduplication_key` no se interpreta como garantía de idempotencia. |
| EVT-19 | Evidencias y relaciones | Las referencias a evidencias y eventos relacionados se conservan cuando correspondan, sin conceder permisos de acceso. |

Las pruebas deberán cubrir también valores de severidad válidos e inválidos, ausencia de `deduplication_key`, separación entre `occurred_at` y `observed_at`, y correspondencia entre `source`, `actor` y `OperationContext`.

Las pruebas deberán cubrir casos positivos y negativos, incluyendo mappings mutables, clasificaciones inválidas, correlaciones diferentes, acceso no autorizado y fallos de persistencia.

## 12. Referencias a CT-08

CT-08 complementa este contrato como matriz transversal; las resoluciones siguientes precisan su aplicación sin duplicar sus reglas:

- [CT-08 R08-05](consistency-matrix-ct-08.md#r08-05-separacion-de-actor-origen-fuente-y-contexto): Separación entre actor, origen, fuente y contexto conservando la correlación.
- [CT-08 R08-06](consistency-matrix-ct-08.md#r08-06-clasificacion-y-proteccion-de-evidencia-derivada): Protección de la clasificación y de la evidencia derivada.
- [CT-08 R08-07](consistency-matrix-ct-08.md#r08-07-diferencia-entre-finding-followuprecord-e-incidence): Distinción entre Finding, FollowUpRecord e incidencia y sus ciclos de vida.
- [CT-08 R08-11](consistency-matrix-ct-08.md#r08-11-separacion-entre-eventos-y-securityaudit): Los eventos funcionales no sustituyen SecurityAudit.

**Fin del contrato.**
