# ME-03K — Especificación de conformidad para adaptadores durables de recuperación

**Estado:** especificación de diseño; no selecciona ni implementa tecnología.  
**Rama:** implementation/me-01-to-me-04-memory-engine.  
**Dependencias:** CT-05, ME-03C, ME-03E, ME-03F, ME-03I, ME-03J-A y ME-03J-B.

## 1. Propósito

ME-03J define los coordinadores y puertos para recuperar admisiones, finalizar la recuperación y reabrir el gate. Sus pruebas actuales usan fakes en proceso único. ME-03K define qué debe demostrar cualquier adaptador real antes de considerarlo apto.

La suite debe poder ejecutarse contra implementaciones reales de ConsistencyJournalPort, RecoveryGatePort, ProtectedMemoryConsistencyPort y egress, RecoveryAdmissionFinalizerPort, RecoveryCompletionFinalizerPort, TerminalReceiptVerifierPort, RecoveryCompletionVerifierPort y autenticación de checkpoints/recibos.

Los dobles de prueba sirven para pruebas unitarias, no como evidencia de conformidad.

## 2. Principios no negociables

1. Fail-closed ante pérdida de continuidad, reloj no confiable, resultado ambiguo o evidencia no verificable.
2. Una sola autoridad serializa admisión, cierre, invalidación, egress, fencing y reapertura.
3. Commit de journal con CAS sobre dominio, época y secuencia esperada.
4. El cierre del gate y su persistencia son una única operación atómica.
5. RECOVERY_RECONCILED y la reapertura del gate son una única operación atómica.
6. Ningún proceso antiguo puede emitir después de que la nueva generación haya sido cercada.
7. Recibos y checkpoints deben autenticarse y vincularse a todos los identificadores, generaciones, secuencias e inventarios pertinentes.
8. Un resultado ambiguo se reconcilia consultando autoridad durable; nunca se resuelve suponiendo que la operación falló.
9. Las claves de idempotencia y tombstones sobreviven a reinicios y compactación.
10. La recuperación no restaura capacidades bearer ni reanima emisores antiguos.

## 3. Matriz de pruebas de conformidad

### K01 — Journal y CAS

- Dos escritores con la misma posición esperada: exactamente uno puede avanzar la secuencia.
- Misma clave idempotente y solicitud canónica: devuelve el mismo commit lógico.
- Misma clave con campos distintos: conflicto y ninguna mutación.
- Posición, época o secuencia obsoleta: rechazo.
- Timeout después de commit: consulta posterior descubre el commit exacto sin duplicarlo.
- Escritura parcialmente persistida o corrupción: el dominio queda cerrado.
- Transición inválida, duplicada o fuera de orden: rechazo.

### K02 — Crash points y recuperación

| Punto | Resultado exigido tras reinicio |
|---|---|
| Antes de RECOVERY_CLOSED | No asumir cierre; validar autoridad y posición |
| Después del commit, antes de respuesta | Recuperar cierre exacto y mantener gate cerrado |
| Después de fencing remoto, antes del recibo journal | Reconsultar endpoint y verificar recibo; no repetir ciegamente |
| Después de ENDPOINT_FENCED, antes de ADMISSION_RECONCILED | Reanudar verificación y finalización idempotente |
| Después de finalizador, antes del append | Recuperar el mismo recibo idempotente y verificarlo |
| Después de ADMISSION_RECONCILED | No reactivar la admisión; continuar con el inventario restante |
| Durante RECOVERY_RECONCILED + apertura | Resolver desde autoridad atómica; si no se puede probar, gate cerrado |
| Después de apertura, antes de respuesta | Confirmar apertura exacta desde journal/autoridad |

### K03 — Fencing y egress

- Emisor de generación anterior intenta emitir antes, durante y después del fencing.
- Check-token/send concurrente contra cierre: nunca liberar una unidad no comprometida antes del cierre.
- Commit concurrente con Forget/invalidation: orden total y resultado inequívoco.
- Emisión duplicada o secuencia repetida: rechazar sin doble entrega.
- Resultado de commit ambiguo: mantener admisión UNRESOLVED hasta reconciliar.
- Cada ruta registrada debe confirmar terminalidad; rutas desconocidas o ausentes bloquean.
- Streaming, fragmentos, buffers, exportaciones y salidas derivadas pasan por el mismo fence.

### K04 — Finalización de admisiones

- Recibo endpoint con dominio, época, operación, admisión, endpoint, generación, generación previa o secuencia incorrectos: rechazar.
- Inventario de recibos no coincide exactamente con route_ids: rechazar.
- Recibo duplicado, replayado, expirado o de emisor no confiable: rechazar.
- Finalizador devuelve binding distinto o timeout: mantener UNRESOLVED.
- Resultado ambiguo del append: recargar y aceptar solo si el estado terminal completo coincide exactamente.
- Reintentos producen el mismo recibo y una sola transición terminal.

### K05 — Finalización global y gate

- Falta una admisión afectada o queda alguna no terminal: no reconciliar y no abrir.
- Recibos de admisión no cubren exactamente el inventario: no reconciliar.
- Recibo global con dominio, época, operación, generación, admisiones o rutas diferentes: rechazar.
- Verificador global no disponible o evidencia inválida: gate cerrado.
- Dos coordinadores completan simultáneamente: una única transición y un único resultado terminal.
- Crash entre commit global y respuesta: reconciliar sin duplicar evento.
- Reinicio con evento global pero sin prueba fiable de apertura: gate cerrado hasta restaurar estado atómico.
- Solicitud antigua de apertura no puede abrir un cierre posterior ni una generación distinta.

### K06 — Checkpoints, anti-rollback y continuidad

- Checkpoint sin baseline autenticado: rechazo.
- Checkpoint antiguo reproducido después de una generación nueva: rechazo.
- Truncamiento, huecos de secuencia, época desconocida o hash-chain rota: rechazo.
- Restauración de backup anterior al último cierre: no abre el gate.
- Claves idempotentes/tombstones activas sobreviven compactación.
- Checkpoint y journal deben permitir demostrar continuidad desde un ancla confiable externa al conjunto restaurable.

### K07 — Concurrencia y aislamiento

- Dos procesos y dos nodos ejecutan recuperación sobre el mismo dominio.
- Operaciones sobre dominios distintos no comparten estado ni bloqueos lógicos.
- Cambio de líder/lease no autoriza a un proceso antiguo a emitir.
- Pausa larga y reanudación de un nodo viejo no evita fencing.
- Lecturas y admisiones nuevas permanecen bloqueadas mientras la recuperación no esté reconciliada.

## 4. Requisitos de harness

La suite común debe proporcionar reloj controlable, IDs deterministas solo para pruebas, inyección de fallos antes/después de cada punto durable, pausa/reanudación de procesos y emisores, ejecución concurrente con barreras, reinicio desde solo datos persistidos, restauración de snapshots antiguos, captura de entregas comprometidas y comprobación de que la evidencia no contiene payload, fragmentos, contenido ni hashes del contenido de memoria.

La suite distingue pruebas unitarias, integración con adaptadores reales, concurrencia multiproceso/multinodo, recuperación kill/restart y resiliencia ante corrupción, partición, timeout y resultados ambiguos.

## 5. Criterios de aprobación

Un adaptador solo es conforme si pasa K01–K07 en la configuración y topología objetivo; conserva evidencia y tombstones tras reinicios/compactación; demuestra atomicidad real del gate; no depende de locks locales para garantías entre nodos; demuestra fencing en cada egress; falla cerrado ante pérdida de autoridad, reloj o verificador; y aporta trazas reproducibles sin datos de memoria.

No se admite aprobación parcial de K02, K03, K05 o K06 para activar lecturas protegidas o Forget real.

## 6. Decisiones deliberadamente pendientes

Esta especificación no elige motor de base de datos, mecanismo de consenso/coordinación, broker/transporte, almacén de objetos, sistema criptográfico/proveedor de claves, política de backups/retención ni topología/número de nodos. Esas decisiones requieren primero requisitos operativos y garantías verificables de cada alternativa.

## 7. Estado y siguiente trabajo

La especificación es normativa para la siguiente etapa de adaptadores. Aún no existen adaptadores durables ni pruebas K01–K07 ejecutadas contra infraestructura real. Los tests ME-03J existentes son fakes y no deben presentarse como conformidad distribuida.

Siguiente trabajo: revisar cada puerto contra esta matriz, identificar operaciones faltantes para consultar resultados ambiguos y verificar anclas/checkpoints, y solo entonces diseñar la interfaz de adaptador durable sin escoger tecnología.