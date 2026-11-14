# ME-03K-B — Contrato de persistencia, continuidad y autenticidad

**Estado:** contrato técnico de diseño propuesto para cerrar ME-03K antes de elegir tecnología.  
**Ámbito:** journal de consistencia, checkpoints, recibos operativos y recuperación.  
**No autoriza:** activar almacenamiento protegido, Forget físico ni cambios de producción.

## 1. Objetivo y límites

Este documento fija las garantías observables que debe ofrecer cualquier adaptador durable. Es independiente de motor de base de datos, protocolo de consenso, formato físico, algoritmo criptográfico y proveedor de claves. La implementación deberá seleccionar mecanismos concretos que satisfagan los requisitos y demostrarlo mediante ME-03K K01–K07.

El journal contiene metadatos operativos mínimos. Está PROHIBIDO incluir contenido de memoria, fragmentos, payloads, embeddings, snippets, hashes de contenido o datos derivados que permitan reconstruirlo. La integridad del journal protege registros de control, nunca sustituye la eliminación de contenido.

## 2. Identidad del dominio y posición durable

Cada registro durable pertenece exactamente a un `consistency_domain_id` y `authority_epoch`. Su posición es la tupla `(consistency_domain_id, authority_epoch, sequence)`.

- `sequence` es estrictamente creciente y sin huecos dentro de una época.
- Una escritura solo puede confirmar contra la posición esperada exacta (CAS).
- La autoridad no puede aceptar escrituras de una época anterior ni cambiar de época sin una transición de autoridad autenticada.
- `record_id` es único dentro del dominio y no puede reutilizarse.
- El orden de confirmación durable define el orden de admisión, cierre, invalidación, egress, fencing y reconciliación.
- El tiempo de pared no determina el orden. Los timestamps sirven para semántica temporal/auditoría; la secuencia durable determina precedencia.

Una respuesta exitosa de escritura significa que la transición y su posición son durables conforme a la política de confirmación declarada por el adaptador. Una respuesta ambigua no significa éxito ni fracaso.

## 3. Canonicalización e idempotencia

### 3.1 Solicitud canónica

Cada operación idempotente debe tener una representación canónica versionada, independiente del orden de propiedades, formato JSON incidental, espacios, codificación de transporte o serialización específica del proveedor.

La representación canónica incluye como mínimo:

- versión del esquema canónico;
- dominio y época;
- tipo de operación/transición;
- `operation_id` e `idempotency_key` cuando correspondan;
- identificadores de recurso, admisión, endpoint y rutas aplicables;
- generación y revisiones aplicables;
- inventarios exactos y campos semánticos de la solicitud.

No incluye timestamps de reintento, valores aleatorios regenerados por el cliente ni datos de contenido. Los identificadores asignados por la autoridad deben asignarse una sola vez y recuperarse en reintentos, no regenerarse para disfrazar la misma operación como nueva.

### 3.2 Clave e identidad de solicitud

- La clave idempotente es única en el ámbito de dominio definido por el adaptador y se conserva mientras pueda existir replay o recuperación de la operación.
- El adaptador vincula la clave a una identidad de solicitud canónica autenticada.
- Misma clave + misma solicitud canónica: devuelve el mismo resultado durable original, identificado como replay, sin crear otra transición.
- Misma clave + solicitud diferente: conflicto explícito, sin mutación.
- La misma operación no puede crear dos cierres, recibos terminales ni aperturas por cambiar `record_id`.
- Las tombstones de claves y operaciones no se eliminan durante compactación mientras un replay pueda afectar seguridad o semántica.

### 3.3 Consulta de resultado ambiguo

Tras timeout, desconexión o pérdida de respuesta, el caller debe consultar por `(domain_id, authority_epoch, operation_id, idempotency_key)` y aportar o recuperar la identidad canónica esperada.

El resultado de consulta debe distinguir:

- `COMMITTED_EXACT`: existe exactamente una transición durable que coincide en todos los campos canónicos; devuelve posición y `record_id` originales.
- `NOT_COMMITTED`: la autoridad demuestra que no existe commit para esa clave/operación y que la posición/época permiten un reintento seguro.
- `CONFLICT`: existe la clave u operación con solicitud distinta, o hay más de un resultado incompatible.
- `UNKNOWN`: no puede demostrarse ninguno de los estados anteriores por indisponibilidad, corrupción, pérdida de continuidad o ambigüedad.

`UNKNOWN` y `CONFLICT` fallan cerrado. Nunca se reintenta como operación nueva ni se abre un gate a partir de esos resultados. `NOT_COMMITTED` solo permite reintentar la misma solicitud canónica con CAS actualizado y bajo la misma autoridad.

## 4. Autenticidad e integridad del journal

El adaptador debe ofrecer evidencia verificable de que los registros fueron emitidos por la autoridad autorizada, no fueron modificados, reordenados, insertados, eliminados ni sustituidos.

Cada unidad autenticada debe vincular como mínimo:

- dominio y época;
- secuencia y `record_id`;
- versión de esquema y tipo de transición;
- representación canónica completa de los campos permitidos;
- referencia autenticada al registro anterior o al checkpoint base;
- identidad/rol del emisor autorizado y material de confianza aplicable;
- versión del formato de autenticación.

El mecanismo puede ser firma, MAC, hash-chain autenticada u otro mecanismo equivalente, pero debe resistir falsificación, sustitución, truncamiento y reordenamiento dentro del modelo de amenazas declarado. Un hash sin autenticación no prueba quién emitió el registro.

El verificador debe validar la cadena completa desde un ancla confiable; validar solo el último registro o una referencia declarada por el mismo conjunto restaurable no basta.

## 5. Ancla externa y anti-rollback

### 5.1 Ancla confiable

El estado más reciente confirmado debe quedar vinculado a un ancla de continuidad almacenada o atestiguada fuera del mismo dominio de rollback que el journal/checkpoint restaurable. El respaldo de datos no puede ser la única fuente de verdad sobre cuál era el estado más reciente.

El ancla identifica al menos dominio, época, secuencia máxima confirmada y compromiso autenticado del estado correspondiente. Su actualización debe tener semántica monotónica y autenticada.

### 5.2 Restauración

- Un checkpoint anterior al ancla externa vigente se rechaza.
- Una época desconocida, inferior o no autorizada se rechaza.
- Un journal truncado, con huecos, forks o cadena rota se rechaza.
- Si el ancla externa no está disponible, no puede verificarse o discrepa, el dominio permanece cerrado.
- Restaurar datos desde backup nunca restaura automáticamente la autoridad para admitir lecturas o emitir contenido.
- La recuperación debe reconstruir cierres, generaciones, tombstones, invalidaciones y admisiones no terminales antes de aceptar tráfico.

### 5.3 Cambio de autoridad/época

El cambio de autoridad requiere una transición de handoff autenticada que identifique autoridad anterior/nueva, época anterior/nueva, posición final anterior, posición inicial nueva y evidencia de que los emisores antiguos quedan cercados. Un lease expirado por sí solo no demuestra fencing ni autoriza a una autoridad nueva a emitir.

## 6. Checkpoints y compactación

Un checkpoint es una proyección autenticada de una posición exacta del journal, no una fuente autónoma de autoridad.

Debe vincular:

- checkpoint ID;
- dominio, época y secuencia exacta;
- referencia inmutable de la proyección base;
- compromiso autenticado de esa proyección;
- referencia/posición del ancla externa;
- versión de esquema/reducer;
- tombstones e idempotency records aún vigentes;
- inventario de operaciones, admisiones, endpoints, cierres e invalidaciones no terminales.

La compactación solo puede descartar entradas cuyo efecto esté representado íntegramente en un checkpoint verificado y cuya eliminación no destruya evidencia necesaria para idempotencia, replay, auditoría, recuperación o Forget.

Un checkpoint sin baseline autenticado, sin ancla vigente o sin proyección verificable produce `UNKNOWN` y mantiene el gate cerrado. El reducer puro no autentica checkpoints; esta responsabilidad pertenece al adaptador/verificador antes de entregar `ConsistencyRecoveryState` al reducer.

## 7. Recibos autenticados

### 7.1 Claims comunes

Todo recibo usado para fencing, finalización de endpoint, admisión terminal o finalización global debe autenticarse y vincular:

- `receipt_id` único;
- tipo exacto de recibo y resultado terminal;
- dominio y época;
- `operation_id`;
- `admission_id` cuando aplique;
- endpoint/route exacto cuando aplique;
- generación vigente y, si corresponde, generación anterior cercada;
- secuencia final o posición de egress cuando aplique;
- inventario exacto de rutas/admisiones cubiertas;
- emisor, identidad de autoridad y versión de clave/material de confianza;
- tiempo de emisión y límites de validez si existen;
- referencia a la solicitud canónica a la que responde.

Los recibos globales deben incluir el conjunto exacto de recibos terminales de admisión verificados o compromisos verificables de ese conjunto. No basta con declarar un contador o una lista incompleta.

### 7.2 Verificación independiente

El verificador es una frontera separada del finalizador. Debe comprobar autenticidad, autorización del emisor, validez temporal con reloj confiable, binding exacto, estado de clave, revocación, replay y correspondencia con el journal.

El finalizador no puede autoaprobar su propio recibo. Un identificador de recibo o un objeto tipado no es evidencia criptográfica por sí mismo.

### 7.3 Rotación y revocación de claves

El sistema de confianza debe definir identificación de claves, vigencia, rotación, revocación, compromiso, recuperación y retención de material público/histórico para verificar recibos antiguos. Una clave comprometida debe poder invalidar recibos según una política explícita; si no se puede determinar la validez, se falla cerrado.

No se prescribe proveedor ni algoritmo en este contrato. La selección debe documentar propiedades de seguridad, gestión de claves, recuperación y pruebas.

### 7.4 Replay

Un recibo solo puede cerrar la operación, admisión, endpoint, generación, secuencia e inventario exactos para los que fue emitido. Un recibo ya consumido no puede cerrar otra operación, generación o dominio. La deduplicación y el consumo deben ser durables y atómicos con el cambio de estado correspondiente.

## 8. Atomicidad y frontera de autoridad

La implementación de `ProtectedMemoryRecoveryAuthorityPort` debe compartir una sola autoridad serializable para:

- `admit_read`;
- `begin_forget` y supresión lógica;
- invalidaciones de Identity/Grant/Memory/Project/Environment;
- `commit_and_emit` y `finish`;
- fencing y acknowledgements de endpoints;
- cierre de recuperación;
- reconciliación global y apertura del gate.

Cada operación que cambie el orden lógico debe compartir una posición/época o una primitiva equivalente demostrable. Una transacción local seguida de una llamada remota no es atómica. Un lock de proceso, un cache o un lease sin fencing verificable no satisface el requisito.

El egress debe aplicar la generación y autorización vigentes en el mismo punto irrevocable de aceptación de la unidad para transporte/consumidor. No se admite check-token-then-send con una ventana de carrera.

`RECOVERY_RECONCILED` y apertura del gate deben ser un único resultado atómico. Si el resultado de la llamada es ambiguo, la autoridad consulta el estado durable exacto. Hasta poder demostrar el resultado, ninguna admisión nueva ni emisión se permite.

## 9. Contrato de consultas del journal

Además de append y recuperación, el adaptador debe permitir resolver resultados inciertos sin exponer acceso a consumidores de memoria. Las consultas mínimas son:

1. Buscar operación por dominio/época/operation_id.
2. Resolver idempotency key contra solicitud canónica esperada.
3. Obtener posición/época/ancla actuales autenticadas.
4. Cargar proyección y entradas/recibos correlacionados de una admisión.
5. Obtener estado exacto del cierre de recuperación y su recibo global.
6. Distinguir ausencia demostrada de indisponibilidad/estado desconocido.

Las consultas no deben devolver contenido de memoria. Sus respuestas deben ser consistentes con la autoridad que realiza escrituras; lecturas eventualmente consistentes no pueden decidir si abrir un gate o permitir egress.

## 10. Fallos y resultados

| Condición | Resultado obligatorio |
|---|---|
| Journal/ancla/verificador no disponible | UNKNOWN; gate cerrado |
| Conflicto de idempotencia | CONFLICT; sin mutación |
| CAS obsoleto | Rechazo; recargar y reevaluar bajo autoridad |
| Timeout con commit posiblemente aplicado | Resolver por clave/operación; no duplicar |
| Checkpoint antiguo o no autenticado | Rechazo; gate cerrado |
| Recibo inválido, revocado o replayado | Rechazo; no avanzar estado |
| Inventario incompleto | PENDING/BLOCKED; no suprimir/reabrir prematuramente |
| Resultado ambiguo de cierre/apertura | Gate cerrado hasta prueba exacta |
| Pérdida de ancla o continuidad | Dominio bloqueado; recuperación manual/procedimiento explícito |

## 11. Requisitos de prueba obligatorios

El adaptador deberá demostrar con pruebas K01–K07 y fallos inyectados:

- escritura concurrente CAS y ausencia de forks;
- replay de clave idempotente con misma solicitud y conflicto con solicitud distinta;
- timeout después de commit y consulta exacta del resultado;
- autenticidad de cadena, detección de alteración/truncamiento/reordenamiento;
- restauración de checkpoint antiguo frente a ancla externa más nueva;
- revocación/rotación de claves y validación de recibos históricos;
- duplicación/replay de recibos y binding incorrecto;
- caída en cada frontera de cierre, fencing, finalización y apertura;
- recuperación multiproceso/multinodo sin reactivar emisores antiguos;
- compactación conservando tombstones y operaciones no terminales.

Los resultados de fakes son evidencia unitaria únicamente. La aprobación requiere adaptadores reales y la topología objetivo.

## 12. Decisiones pendientes expresas

Siguen pendientes y no se infieren aquí:

- algoritmo de autenticación, formato de envelope y proveedor/gestor de claves;
- tecnología de journal y transacciones/CAS;
- mecanismo de ancla externa y su disponibilidad operativa;
- protocolo de consenso/elección de autoridad y handoff;
- política de retención, backup, restore y custodia de anclas;
- objetivos de disponibilidad, RPO/RTO y procedimiento de recuperación manual;
- topología, límites de dominio y despliegue.

Estas decisiones se evaluarán después de cerrar el contrato y comparar alternativas contra cada requisito verificable.

## 13. Criterio de cierre de ME-03K-B

ME-03K-B se considera contractualmente cerrado cuando:

1. Los puertos de journal y autoridad representan todas las operaciones de consulta/ambigüedad descritas.
2. El adaptador valida autenticidad y anti-rollback antes de entregar estado al reducer.
3. El gate no puede abrirse por una consulta eventual ni por un recibo no verificado.
4. Checkpoints, claves idempotentes, tombstones y recibos tienen ciclo de vida durable definido.
5. La misma autoridad serializa lecturas, Forget, invalidación, egress y recuperación.
6. K01–K07 pueden ejecutarse sin cambiar las expectativas por proveedor.

Este cierre de diseño no equivale a implementación ni conformidad operativa. No autoriza activar lecturas protegidas o Forget físico.

## 14. Contrato tipado complementario

Los tipos y puertos que hacen exigibles las garantías de ancla externa, verificación de checkpoint/estado, contexto de confianza, autenticidad de recibos y resolución de operaciones ambiguas se especifican en `me-03k-c-trust-anchor-and-verification-port-contracts.md`.

ME-03K-B y ME-03K-C deben leerse conjuntamente. El journal no entrega un estado desnudo al reducer: la recuperación debe demostrar autenticidad y continuidad desde un ancla externa vigente. Los recibos tipados no son por sí mismos evidencia autenticada. El finalizador y el verificador permanecen separados.

El cierre de ambos contratos sigue siendo diseño; los puertos y modelos existentes aún requieren alineación de tipos antes de iniciar adaptadores durables.
