# ME-03 — Diseño de consistencia para lecturas y supresión de memoria

**Estado:** propuesta técnica para revisión; no normativa ni implementada.  
**Rama de trabajo:** `implementation/me-01-to-me-04-memory-engine`  
**Alcance:** lectura versionada a través de MemoryGateway y su interacción con cambios de estado y Forget.  
**Fuera de alcance:** selección de base de datos, motor de índices, caché, proveedor de almacenamiento, despliegue, adapters reales y ejecución de Forget.

## 1. Problema observado

La ruta actual ejecuta esta secuencia:

1. `MemoryGatewayService.get_version()` obtiene la hora.
2. `MemoryAuthorizationService.authorize_read()` resuelve metadatos y autoriza.
3. Si CAM devuelve `ALLOW`, el Gateway llama a `MemoryVersionContentPort.get_version_content()`.
4. El Gateway valida IDs, estado `approved` y clasificación distinta de `RESTRICTED`.

La secuencia impide que una denegación ordinaria consulte el puerto de contenido, pero no constituye una operación atómica. Entre los pasos 2 y 3, o durante la lectura, la versión podría pasar a `superseded` o `forgotten`, cambiar su clasificación/metadatos, o quedar bajo supresión lógica. La comprobación final del objeto devuelto reduce algunos riesgos, pero no prueba que la comprobación y la entrega observen el mismo estado autoritativo.

## 2. Requisitos normativos que debe preservar

Esta propuesta se deriva de los contratos existentes; no los modifica:

- Toda lectura protegida atraviesa MemoryGateway y CAM.
- CAM autoriza el recurso concreto y falla cerrado ante ausencia, inconsistencia o error.
- Solo una versión `approved` puede ser leída; `pending_review`, `rejected`, `superseded` y `forgotten` no son conocimiento aprobado vigente.
- La aprobación de una versión nueva, el supersede de la anterior y el cambio del puntero vigente son atómicos.
- Una vez validada una solicitud de olvido, la supresión lógica debe impedir inmediatamente la exposición por rutas ordinarias, incluidas consultas, índices, cachés, exportaciones y recuperación.
- La supresión lógica debe mantenerse mientras la eliminación física y su verificación estén incompletas.
- Restauración, reindexación, replicación e importación deben aplicar la supresión antes de volver a exponer contenido.
- No puede declararse `forgotten` hasta completar la verificación de todos los destinos aplicables.

Referencias principales: `docs/contracts/memory.md` §§5.2–5.4, 7 y 9; DM-01 §§4.3–4.4 y 9.3.8–9.3.9; CT-05 y CT-08.

## 3. Objetivo de consistencia

Definir un punto de linealización para una lectura protegida y otro para la activación de supresión lógica, de forma que exista un orden observable entre ambos.

**Garantía mínima propuesta:** una lectura no puede comenzar a entregar contenido si, en su punto de validación atómica, la memoria o versión está suprimida, no está aprobada, tiene clasificación no permitida o sus metadatos ya no coinciden con los que CAM autorizó.

**Garantía para Forget propuesta:** después de confirmar la activación de la supresión lógica, no se admiten nuevas lecturas de la memoria/versión afectada. Las lecturas ya admitidas deben quedar sujetas a una barrera de finalización/cancelación antes de que Forget comunique que la supresión inmediata está aplicada. El contrato actual no define todavía cómo se drenan lecturas en curso; este detalle requiere aceptación explícita antes de implementarlo.

Esta garantía es más fuerte que consultar un tombstone antes de leer y luego recuperar contenido por separado: esa secuencia también tiene una carrera entre la consulta del tombstone y la entrega.

## 4. Diseño recomendado: autorización vinculada a una lectura condicional atómica

### 4.1 Snapshot de autorización

CAM debe producir, además de la decisión, un snapshot opaco e inmutable de los hechos que justificaron el permiso. Conceptualmente debe vincular como mínimo:

- `memory_id` y `version_id` exactos;
- `owner_id` y scope canónicos de Memory;
- `project_id` y entorno cuando apliquen;
- estado y clasificación de la versión;
- relación de la versión con su memoria;
- revisión/epoch de los metadatos usados para autorizar;
- identidad del actor y contexto de la operación;
- identificador/revisión de la decisión de autorización, si el repositorio de Grants permite obtenerlo.

El snapshot no contiene contenido ni concede permisos por sí mismo. Debe ser emitido por la ruta confiable CAM, no aceptado desde el solicitante. Su formato criptográfico, almacenamiento y caducidad quedan pendientes; no se debe inventar un token firmado sin seleccionar y aprobar antes el mecanismo de confianza.

### 4.2 Lectura condicional

El puerto de contenido debe evolucionar conceptualmente de una lectura incondicional por IDs a una operación equivalente a:

`read_version_if_visible(authorization_snapshot) -> MemoryVersion | None`

La operación debe comprobar en un mismo límite de consistencia:

1. IDs exactos de memoria y versión.
2. Que la versión siga perteneciendo a esa memoria.
3. Que la revisión/epoch de metadatos coincida con el snapshot autorizado.
4. Que la versión siga en estado `approved` y mantenga la clasificación autorizada.
5. Que no exista supresión lógica activa para la memoria ni para la versión.
6. Que el mecanismo de lectura/supresión otorgue una admisión válida que cubra la entrega, no solo la consulta inicial.

Si una condición falla, devuelve ausencia genérica y no entrega contenido. No debe degradarse a una lectura sin snapshot ni a un fallback de ID solamente.

### 4.3 Autoridad de supresión

La supresión lógica debe ser una autoridad consultada obligatoriamente por todas las rutas capaces de volver a exponer contenido. No basta con marcar una fila en el almacén primario si índices, cachés, réplicas, exportaciones o restauraciones pueden responder sin comprobarla.

El diseño debe permitir suprimir por identificadores opacos de memoria/versión y conservar solo los metadatos mínimos exigidos por CT-05. No almacenar contenido olvidado, fragmentos ni hashes de contenido como sustituto del tombstone.

El estado operativo de supresión no debe introducir un nuevo estado normativo de `MemoryVersion`. `forgotten` continúa significando olvido físico verificado y completado, no solicitud recibida ni supresión provisional.

### 4.4 Coordinación con lecturas en curso

Una lectura admitida debe tener una duración/lease acotada o una forma equivalente de coordinación. Forget debe impedir nuevas admisiones y esperar la finalización o cancelación verificable de las admisiones previas antes de considerar aplicada la barrera de supresión inmediata.

La semántica exacta de cancelación, expiración, bloqueo y recuperación tras caída queda pendiente. No se debe elegir un mecanismo de locks distribuidos, leases, transacciones o mensajería hasta definir los requisitos operativos y el proveedor.

## 5. Reglas de fallo cerrado

- Snapshot ausente, inválido, caducado o con IDs distintos: no leer.
- Revisión de metadatos cambiada: no leer; solicitar nueva autorización en una operación nueva.
- Estado distinto de `approved`: no leer.
- Clasificación distinta de la autorizada o `RESTRICTED`: no leer.
- Supresión no disponible, timeout o respuesta inconsistente: no leer.
- No se puede confirmar el límite atómico entre validación y lectura: no leer.
- Cache, índice, réplica o destino derivado no puede verificar supresión: no exponer contenido.
- Un proceso de restauración/reindexación no puede comprobar supresión: bloquear publicación/visibilidad.
- No se puede drenar o cancelar una lectura en curso: Forget no puede declarar aplicada la barrera.

La respuesta pública debe seguir evitando distinguir denegación, inexistencia y no disponibilidad cuando esa distinción pueda revelar la existencia de una memoria protegida.

## 6. Consecuencias para la implementación actual

La implementación actual no ofrece todavía esta garantía:

- `AuthorizationResult` contiene solo la decisión, no un snapshot de autorización.
- `MemoryVersionMetadata` no contiene revisión/epoch.
- `MemoryVersionContentPort.get_version_content()` es una lectura por IDs y no declara atomicidad, supresión ni coordinación de lecturas en curso.
- No existe aún un puerto ni servicio de supresión/Forget.
- No existe inventario de destinos, cachés, índices, réplicas, exportaciones o backups.

Por tanto, las pruebas existentes demuestran orden de llamadas y fail-closed básico, pero no consistencia concurrente ni supresión global.

## 7. Plan de verificación propuesto

Antes de integrar un proveedor real, construir pruebas deterministas con puertos falsos coordinados por barreras:

| Caso | Intercalado | Resultado exigido |
|---|---|---|
| C01 | La versión cambia a `superseded` después de CAM y antes de lectura condicional | No se entrega contenido |
| C02 | La versión cambia a `forgotten` después de CAM | No se entrega contenido |
| C03 | Se activa supresión de memoria entre CAM y lectura | No se entrega contenido |
| C04 | Se activa supresión de versión entre CAM y lectura | No se entrega contenido |
| C05 | Cambia la revisión de metadatos | Snapshot rechazado |
| C06 | El servicio de supresión no responde | Fail closed |
| C07 | La lectura se admite primero y Forget empieza después | Forget bloquea nuevas lecturas y coordina la lectura en curso |
| C08 | Forget activa la barrera primero y llega una lectura después | Lectura rechazada |
| C09 | Se intenta restaurar/reindexar contenido suprimido | No se publica ni expone |
| C10 | El destino derivado no puede consultar la supresión | No expone contenido |

Las pruebas de concurrencia deben usar eventos/barreras explícitas, no sleeps ni temporizadores, para que los intercalados sean reproducibles.

## 8. Decisiones pendientes antes de implementar

1. Aceptar o ajustar la garantía propuesta para lecturas ya admitidas cuando comienza Forget.
2. Definir la autoridad única de supresión y cómo la consultan todos los destinos.
3. Definir cómo se versionan los metadatos canónicos y cómo se detecta un cambio desde el snapshot CAM.
4. Definir la semántica de lease/admisión y su recuperación ante caída del proceso.
5. Definir cómo una revocación de Grant o expiración durante el intervalo se refleja en la admisión de lectura.
6. Inventariar destinos reales antes de afirmar que la supresión es global.
7. Definir evidencia verificable para que Forget avance de supresión lógica a eliminación física y finalmente a `forgotten`.

Ninguno de estos puntos autoriza a seleccionar una base de datos, caché, índice, proveedor, scheduler o plataforma.

## 9. Criterio de salida

ME-03 de diseño estará listo para implementación cuando se hayan aceptado las garantías de §3–4 y cerrado los bloqueos de §8 que afecten al límite de lectura. La implementación posterior deberá:

- cambiar el contrato del puerto para exigir lectura condicional;
- vincular el resultado CAM con el snapshot exacto;
- comprobar la supresión en el mismo límite de admisión/lectura;
- coordinar lecturas en curso con Forget;
- añadir pruebas deterministas de carreras;
- mantener los adaptadores de prueba separados de cualquier afirmación de integración real.

**Estado actual:** este documento registra una propuesta de diseño. No implementa snapshots, leases, supresión, Forget, persistencia ni garantías de runtime.
