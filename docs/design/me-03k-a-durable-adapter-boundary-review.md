# ME-03K-A — Revisión de fronteras para adaptadores durables

**Estado:** revisión de contratos y refinamiento de tipos; sin adaptadores ni persistencia.  
**Dependencias:** ME-03J-B y ME-03K.

## Hallazgo principal: una sola autoridad debe ser una sola implementación

ME-03B y ME-03J exigen que admisión, egress, cierres, fencing y reapertura compartan el mismo orden serializable. Sin embargo, las interfaces estaban separadas entre ProtectedMemoryConsistencyPort y RecoveryGatePort. Una composición incorrecta podía conectar el Gateway a una autoridad y el coordinador de recuperación a otra.

Se añadió ProtectedMemoryRecoveryAuthorityPort, que compone ambas facetas. La raíz de composición deberá inyectar la misma instancia concreta al Gateway y a los coordinadores de recuperación. Dos adaptadores separados que implementen cada faceta no cumplen el contrato.

## Capacidades que debe ofrecer el adaptador durable

### Journal

- Append condicional por dominio/época/secuencia.
- Idempotencia durable para solicitud canónica.
- Recuperación con integridad y continuidad local en el baseline; anti-rollback externo como capacidad opcional futura.
- Lectura completa de recibos de endpoint y estado de operaciones.
- Checkpoint con referencia a baseline confiable.
- Resolución de resultados ambiguos mediante lectura de estado durable.

### Autoridad compuesta

- Serialización compartida entre admit_read, begin_forget, invalidación y commit_and_emit.
- Cierre y reapertura del gate en la misma autoridad que controla egress.
- Fencing de generaciones antiguas en cada ruta.
- Recuperación durable de admisiones, endpoints, cierres y recibos.
- No aceptar nuevas admisiones hasta demostrar RECOVERY_RECONCILED y gate abierto.

### Emisores y verificadores

- Finalizadores idempotentes ligados al conjunto exacto de recursos.
- Recibos autenticados con dominio, época, operación, admisión, endpoint, generación y secuencia.
- Verificación independiente del emisor y del material de confianza.
- Rechazo de replay, sustitución de inventario y recibos expirados.

## Gaps que siguen abiertos

1. No existe una implementación durable de ConsistencyJournalPort.
2. No existe una implementación concreta de ProtectedMemoryRecoveryAuthorityPort.
3. Los puertos no especifican todavía el formato ni el protocolo de autenticación de checkpoints/recibos; deben permanecer agnósticos a proveedor, pero exigir claims y validación criptográfica concreta en el adaptador.
4. La recuperación de un resultado ambiguo debe poder identificar la transición por operation_id e idempotency_key y comparar la solicitud canónica. El adaptador debe exponer esa consulta de forma inequívoca, directamente o mediante load_recovery_state.
5. No hay pruebas multiproceso/multinodo, caída real ni restauración de backup.
6. No se ha inventariado el sistema de backup/retención ni las fuentes de restauración.

## Restricciones para la siguiente etapa

- No escoger tecnología hasta comparar las garantías operativas y de recuperación requeridas.
- No declarar conformidad con fakes.
- No activar Forget físico ni lecturas protegidas en producción.
- No aceptar que un lock local, lease expirado o timeout pruebe la muerte de un emisor.
- No abrir el gate si la autoridad no puede demostrar el cierre y la reconciliación exactos.

## Siguiente subetapa

ME-03K-B debe definir el contrato de persistencia y autenticidad mínimo para journal/checkpoints/recibos, consulta de resultados ambiguos e invariantes de atomicidad. El Trust Anchor externo es opcional y su implementación queda postergada hasta la etapa final de Atlas. El baseline local debe declarar que no demuestra anti-rollback externo; la comparación de tecnologías del proveedor anclado se reserva para esa etapa.

## Decisión posterior — Trust Anchor opcional

**APROBADO — 13 de noviembre de 2026.** El Trust Anchor externo no es requisito para las etapas actuales. Se utilizará un perfil local en un único servidor y se desarrollará el proveedor anclado únicamente en la etapa final. Esta decisión no elimina la verificación local ni permite afirmar anti-rollback. Las garantías que dependan de conocer el último estado fuera del conjunto restaurable permanecen bloqueadas o requieren reconciliación independiente aprobada.
