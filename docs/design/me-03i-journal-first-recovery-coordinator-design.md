# ME-03I — Coordinador de recuperación con cierre durable previo

Estado: diseño e implementación incremental en la rama de memoria.  
Relación: CT-05, ME-03C, ME-03F, ME-03G y ME-03H.  
Alcance: coordinación journal-first y reanudación segura de fencing. No activa runtime ni declara recuperación distribuida.

## 1. Objetivo

Eliminar la ventana peligrosa en la que Atlas contactaría endpoints antes de cerrar de forma durable y autoritativa el dominio. La recuperación debe seguir este orden:

1. cargar una proyección cuyo journal y continuidad hayan sido verificados por el adaptador;
2. cerrar atómicamente el gate de admisiones/egress y persistir `RECOVERY_CLOSED`;
3. solo después contactar endpoints;
4. verificar independientemente cada recibo;
5. persistir inmediatamente cada `ENDPOINT_FENCED`;
6. conservar el gate cerrado y las admisiones UNRESOLVED hasta una etapa posterior de reconciliación terminal.

## 2. Nueva frontera de autoridad

`RecoveryGatePort` define dos operaciones:

- `close_recovery_gate(expected_position, transition)`: serializa con admisión y egress, cierra el gate y confirma `RECOVERY_CLOSED` en el journal como una sola operación lógica.
- `ensure_recovery_gate_closed(operation_id, generation)`: después de reinicio, restaura y confirma el cierre exacto antes de permitir que el coordinador contacte endpoints.

Un append ordinario al journal no sustituye esta frontera. Un registro `RECOVERY_CLOSED` sin restauración efectiva del gate no autoriza continuar el fencing.

## 3. Secuencia del coordinador

`RecoveryJournalCoordinator.run()`:

- exige estado del journal disponible y reducible; ausencia, corrupción o error bloquean;
- si no existe recuperación pendiente, calcula una generación superior a todas las admisiones, Forget, invalidaciones y recuperaciones previas, y solicita cierre atómico;
- si ya existe una recuperación pendiente, exige que `ensure_recovery_gate_closed` confirme el gate exacto;
- construye el plan desde la proyección;
- omite endpoints ya registrados como FENCED;
- procesa los endpoints restantes uno por uno;
- valida el recibo del fencer y solicita su verificación independiente ME-03G;
- persiste `ENDPOINT_FENCED` después de verificar cada endpoint;
- vuelve a cargar y reducir el journal para confirmar cada append.

## 4. Reanudación e idempotencia

El coordinador no depende de memoria local para el progreso:
- el cierre y los fences ya confirmados se leen desde la proyección;
- un endpoint ya FENCED no se contacta de nuevo;
- si el endpoint se cercó pero el proceso cayó antes de registrar el evento, el adaptador de endpoint debe aceptar la repetición idempotente de la misma operación/generación y devolver evidencia verificable;
- append ambiguo, estado no verificable o discrepancia de secuencia mantiene el dominio cerrado.

Los adaptadores reales deberán proporcionar idempotencia durable y resolución de resultados ambiguos; los fakes solo prueban el contrato de coordinación.

## 5. Estados y resultados

- `FENCING_RECORDED`: todos los fences están registrados en el journal; no significa que las admisiones estén CANCELLED ni que el gate pueda abrirse.
- `PENDING`: algún endpoint, verificación, append o recarga no pudo completarse.
- `BLOCKED`: journal, proyección, gate o plan no verificable.

Incluso en `FENCING_RECORDED`, el coordinador deja las admisiones en `UNRESOLVED`. No emite `ADMISSION_RECONCILED` ni `RECOVERY_RECONCILED`. No se reabren admisiones ni egress.

## 6. Pruebas

`tests/unit/test_memory_unresolved_admission_recovery.py` añade pruebas para:
- demostrar que el cierre se persiste antes del primer contacto de endpoint;
- registrar progreso parcial y reanudar sin duplicar el cierre ni repetir endpoints ya confirmados;
- restaurar el gate desde journal tras reinicio antes de continuar;
- bloquear cuando el journal no es verificable.

Las pruebas usan journal, gate, fencer y verifier falsos de proceso único. No prueban atomicidad distribuida ni persistencia real.

## 7. Límites explícitos

No se implementa:
- adaptador durable del journal;
- implementación real del gate que serialice con el egress del runtime;
- transporte/endpoints reales o fencing de procesos;
- recibo terminal de admisión independiente;
- `ADMISSION_RECONCILED` o `RECOVERY_RECONCILED` desde el coordinador;
- apertura del gate;
- anti-rollback, replicación o recuperación multi-nodo.

La siguiente etapa debe definir y probar la finalización terminal de cada admisión con evidencia independiente, y solo después el cierre de recuperación que pueda reabrir el gate mediante una operación atómica. Ninguna implementación de producción debe interpretar `FENCING_RECORDED` como recuperación terminada.
