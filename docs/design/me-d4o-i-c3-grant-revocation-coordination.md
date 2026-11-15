# ME-D4O-I-C.3 — Coordinación e integración de revocación de Grants

**Estado:** contratos y orquestación implementados; adaptador durable y pruebas diferidos.  
**Rama:** `feature/me-d4o-i-c3-grant-revocation-coordination`

## Objetivo

Eliminar la escritura directa de revocaciones desde `GrantManagementService`. La revocación debe pasar por CAM, el consumo one-shot de I-C.2 y el coordinador neutral de cambios de autoridad aprobado en ME-D4O-F.

## Flujo contractual

1. Validar contexto de acción directa: actor USER activo, identidad coincidente con el propietario y sin delegación.
2. Leer el Grant exacto y comprobar el propietario canónico.
3. Consultar primero la clave idempotente dentro del `consumer_id` configurado. Una clave ya usada para otro recurso se rechaza.
4. Crear o recuperar una reserva REQUESTED. El coordinador asigna `operation_id`; el servicio no lo inventa.
5. Construir la solicitud CAM `grant.revoke` con actor, propietario, Grant, revisión esperada, `request_id` y `requested_at` originales.
6. CAM emite evidencia. El servicio I-C.2 verifica emisor/claims/vigencia y consume `proof_id` con la pareja exacta `operation_id` + `idempotency_key`.
7. El adaptador de autorización entrega al coordinador un sobre neutral vinculado a la operación, autoridad y revisiones exactas.
8. El coordinador ejecuta invalidación/fencing, CAS del Grant, persistencia idempotente y reconciliación según ME-D4O-F/H.
9. Solo se devuelve COMPLETED si el coordinador confirma la revisión propuesta y la lectura autoritativa del Grant confirma el mismo Grant revocado en esa revisión.

## Reserva e idempotencia

`AuthorityChangeIntent` no contiene `operation_id`: ese identificador es asignado y persistido por el coordinador. La intención incluye consumer_id explícito, clave idempotente, autoridad/recurso exacto, revisión esperada/propuesta, tipo de cambio, referencia del contexto y timestamp.

El `consumer_id` es configuración explícita de la composición confiable. No se deriva del nombre del proyecto, del contexto del usuario ni de un identificador suministrado libremente en cada llamada. El puerto `Clock` existente se usa después de la respuesta CAM para validar la vigencia real de emisión y fijar el instante de consumo.

Los reintentos recuperan la intención original y conservan su `request_context_ref` y `requested_at`; no sustituyen el contexto CAM original por uno nuevo. La comparación de idempotencia conserva todos los campos semánticos de la intención; el timestamp de una repetición no reemplaza el timestamp original persistido. Una clave reutilizada para otro recurso no puede obtener ni ejecutar la operación previa.

## Incertidumbre y fail-closed

- Reserva con respuesta perdida: recuperar por la misma clave; si no se puede resolver, pedir reintento con la misma clave.
- CAM sin evidencia: solicitar `abort_unstarted`; ABORTED solo si el coordinador demuestra que la fuente permanece en la revisión anterior y la operación no podrá ejecutarse después.
- Error/timeout de CAM: conservar operación recuperable; no inferir denegación ni autorizar el cambio.
- Verificador no disponible o consumo incierto: conservar REQUESTED/BLOCKED y reintentar con la misma clave; nunca abortar ni usar otra operación.
- Evidencia denegada o conflicto de replay: solicitar aborto verificado de la operación no iniciada.
- Error/timeout durante apply: recuperar el resultado durable. Nunca inferir rollback ni liberar fencing por timeout.
- BLOCKED y estados intermedios no devuelven un Grant revocado.

## Responsabilidades y límites

### GrantManagementService

- Mantiene validaciones de propietario como defensa adicional.
- La composición puede mantener disponible la emisión de Grants sin configurar revocación; en ese caso, `revoke` falla cerrado. Para habilitar revocación deben inyectarse conjuntamente CAM, verificación/consumo, Clock y coordinador.
- No llama `GrantRepository.update` para revocar.
- No genera operation_id ni invalidation_id.
- No decide permisos CAM ni realiza invalidación.
- No declara éxito a partir de una respuesta ambigua.

### AuthorityChangeCoordinatorPort

El coordinador debe imponer idempotencia por (consumer_id, idempotency_key), serialización/CAS por autoridad, cálculo autoritativo de admisiones afectadas, invalidación y fencing antes del cambio de fuente, resultado durable del cambio y reconciliación. Debe validar que la autorización consumida corresponde exactamente a operation_id, Grant y revisiones de la reserva.

### Clock

La hora de solicitud se conserva en la intención. Tras recibir evidencia CAM, el servicio usa el puerto Clock inyectado para obtener el instante de verificación/consumo; así no asume que la evidencia fue emitida antes de la hora capturada al iniciar la llamada.

## Estados

Se utilizan los estados normativos exactos de ME-D4O-F:
`REQUESTED`, `INVALIDATION_PENDING`, `SOURCE_PENDING`, `SOURCE_CONFIRMED`, `RECONCILING`, `COMPLETED`, `ABORTED`, `BLOCKED`.

`COMPLETED` requiere revisión fuente igual a proposed_revision e invalidación reconciliada. `ABORTED` requiere evidencia de revisión fuente igual a previous_revision. Cualquier incertidumbre conserva BLOCKED o un estado no terminal.

## Fuera de alcance de C.3

- Adaptador coordinador SQLite concreto y UoW compartida.
- CAS/idempotencia durable del Grant y del consumo de proof.
- Recuperación tras reinicio entre fases.
- Implementación de invalidación/fencing sobre admisiones/rutas.
- Proveedor/verificador real de CAM.
- Ejecución de pruebas, pospuesta para la validación conjunta solicitada.
- Merge a main, despliegue o activación de runtime.

Estas garantías solo se consideran implementadas cuando exista el adaptador durable de I-C.4/I-C.5 y supere las pruebas de conformidad.
