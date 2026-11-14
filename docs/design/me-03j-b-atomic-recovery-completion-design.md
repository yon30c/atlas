# ME-03J-B — Finalización global y reapertura atómica

**Estado:** implementación incremental; CI no confirmado todavía.  
**Rama:** `implementation/me-01-to-me-04-memory-engine`.  
**Dependencias:** ME-03J-A, ME-03G, ME-03I y CT-05.

## Objetivo

Cerrar el ciclo de recuperación solo cuando todas las admisiones afectadas estén `CANCELLED` con recibos terminales verificados y el gate pueda persistir `RECOVERY_RECONCILED` y abrirse en un único punto linealizable.

## Secuencia

1. Cargar y reducir el journal; exigir una recuperación activa exacta.
2. Verificar que el conjunto de admisiones terminales coincide con `affected_admission_ids`.
3. Revalidar cada recibo `ADMISSION_CANCELLED` con el verificador independiente.
4. Construir `RecoveryCompletionRequest` con dominio, época, operación, generación, inventario de admisiones/rutas y todos los recibos verificados.
5. Obtener recibo global idempotente mediante `RecoveryCompletionFinalizerPort`.
6. Verificar el recibo global con `RecoveryCompletionVerifierPort`.
7. Construir `RECOVERY_RECONCILED` con los inventarios exactos.
8. Invocar `RecoveryGatePort.reconcile_and_open_recovery_gate`: el adaptador debe confirmar el evento y abrir el gate atómicamente.
9. Recargar el journal y confirmar la proyección reconciliada; confirmar/restaurar el gate abierto con el recibo exacto.

## Contratos nuevos

- `RecoveryCompletionFinalizerPort`: produce un recibo global idempotente para el conjunto exacto.
- `RecoveryCompletionVerifierPort`: verifica independientemente el recibo global.
- `RecoveryGatePort.reconcile_and_open_recovery_gate`: serializa la transición final con admisiones y egress, y realiza commit + apertura como una única operación.
- `RecoveryGatePort.ensure_recovery_gate_open`: después de reinicio, confirma el estado abierto únicamente si journal, operación, generación y recibo coinciden exactamente.

Un append ordinario seguido de una apertura independiente no satisface el contrato. Ante timeout o resultado ambiguo, el gate permanece cerrado hasta que la autoridad pueda demostrar el resultado exacto.

## Pruebas añadidas

- Reconciliación global con recibo verificado y apertura atómica.
- Inventario global incorrecto.
- Timeout del verificador global.
- Resultado atómico ambiguo reconciliado desde journal y autoridad.
- Reinicio/idempotencia sin duplicar `RECOVERY_RECONCILED`.

Las pruebas utilizan fakes en proceso único. No demuestran almacenamiento durable, serialización distribuida, fencing real, anti-rollback, firma criptográfica ni tolerancia a fallos de múltiples nodos.

## Límite

La implementación define y prueba el contrato de coordinación; no existe todavía un adaptador real de `RecoveryGatePort`, finalizador global ni verificador criptográfico. Por tanto, no hay recuperación distribuida activada ni garantía de producción. La próxima etapa debe diseñar los adaptadores durables y demostrar la atomicidad con pruebas de concurrencia y caída/recuperación contra esos adaptadores.
