# ME-03J-A — Finalización terminal de admisiones recuperadas

**Estado:** implementación incremental; validación automatizada pendiente de CI.  
**Rama:** `implementation/me-01-to-me-04-memory-engine`.  
**Dependencias:** CT-05, ME-03G, ME-03H y ME-03I.

## Objetivo

Convertir una admisión `UNRESOLVED` en `CANCELLED` solo después de verificar independientemente todos sus endpoints cercados y obtener/verificar un recibo terminal de la admisión. Esta etapa no completa la recuperación global ni abre el gate.

## Secuencia

1. Cargar y reducir el journal con continuidad verificada.
2. Exigir exactamente una recuperación activa y no reconciliada.
3. Para cada admisión afectada, comprobar que el inventario de endpoints coincide exactamente con `route_ids`.
4. Verificar cada recibo `ENDPOINT_FENCED` contra dominio, época, operación de recuperación, admisión, endpoint, generación, generación anterior y secuencia cercada.
5. Pasar al finalizador de admisión la evidencia verificada completa y el inventario exacto.
6. Recibir un recibo terminal idempotente de la autoridad.
7. Verificar independientemente ese recibo como `ADMISSION_CANCELLED`.
8. Registrar `ADMISSION_RECONCILED` y volver a cargar/reducir el journal para confirmar el estado exacto.

## Fronteras

- `RecoveryAdmissionFinalizerPort` emite/recupera un recibo terminal idempotente para una única admisión. No abre el gate.
- `TerminalReceiptVerifierPort` sigue siendo la autoridad independiente que valida la evidencia.
- `ConsistencyJournalPort` persiste `ADMISSION_RECONCILED`.
- El coordinador no modifica directamente la proyección ni declara éxito por un resultado ambiguo.

## Reanudación

Una admisión ya reconciliada por la misma operación y generación se omite. Si la escritura devuelve un resultado ambiguo, el coordinador vuelve a cargar el journal; solo considera éxito si encuentra el mismo estado terminal, operación, generación y recibo. El finalizador debe devolver el mismo recibo ante reintentos de la misma solicitud canónica.

## Pruebas añadidas

- Verificación de todos los endpoints antes de finalizar.
- Cobertura exacta del inventario de rutas.
- Rechazo de recibo de admisión con binding incorrecto.
- Verificador no disponible y finalizador con timeout.
- Reanudación idempotente sin duplicar `ADMISSION_RECONCILED`.
- El gate sigue cerrado y no se genera `RECOVERY_RECONCILED`.

Las pruebas usan journal, finalizador y verificador falsos. No prueban persistencia durable, autoridad distribuida, firmas criptográficas reales ni transporte de endpoints.

## Límite y siguiente subetapa

Aunque todas las admisiones puedan quedar `CANCELLED`, el dominio debe seguir cerrado. La subetapa ME-03J-B debe obtener/verificar una evidencia terminal global y combinar `RECOVERY_RECONCILED` con la reapertura del gate en una única operación serializada y durable. Un append ordinario seguido de una apertura separada no es aceptable.

## Estado de implementación

Se añadieron `RecoveryAdmissionFinalizationCoordinator`, `RecoveryAdmissionFinalizerPort` y seis pruebas específicas. El estado `ADMISSIONS_TERMINAL` significa únicamente que las admisiones afectadas quedaron CANCELLED con bindings exactos; no significa que la recuperación global esté reconciliada ni que el gate esté abierto.

La validación CI del commit más reciente todavía no está disponible en la evidencia consultada. No se declara la suite aprobada hasta observar el resultado de GitHub Actions.
