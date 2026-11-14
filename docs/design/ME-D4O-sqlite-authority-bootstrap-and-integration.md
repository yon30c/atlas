# ME-D4O — Bootstrap e integración de la autoridad SQLite por perfiles

**Estado:** inspección completada; ME-D4O-A corregido para admitir perfil LOCAL baseline y perfil ANCHORED opcional futuro.  
**Rama:** `feature/atlas-functional-f1`.  
**Alcance:** implementar incrementalmente la autoridad SQLite sin exigir ahora un proveedor externo ni activar runtime protegido.

## 1. Hallazgo de bootstrap

El esquema `consistency_domains` define:

- `recovery_gate_state TEXT NOT NULL DEFAULT 'closed'`;
- `active_recovery_operation_id`;
- `active_recovery_generation`;
- `recovery_receipt_id`.

`SQLiteConsistencyJournal.create_local_domain(...)` crea el dominio cerrado. `LocalSQLiteRecoveryGateAdapter.ensure_recovery_gate_open(...)` restaura apertura solo con evidencia de recuperación reconciliada; no existe un evento de activación inicial para un dominio vacío.

Un dominio nuevo necesita bootstrap deliberado. No debe tratarse como recuperación vacía ni abrirse mediante UPDATE manual.

## 2. Perfiles normativos

Según ME-03K-B, ME-03K-C y Contrato de diseño Atlas v1 §20.6:

- **LOCAL:** baseline de las etapas actuales, un servidor, sin Trust Anchor externo. Valida autenticidad disponible y continuidad interna, pero no demuestra frescura frente a una restauración coherente del conjunto local.
- **ANCHORED:** perfil opt-in futuro, postergado hasta la etapa final. Añade verificación contra un Trust Anchor externo monotónico. Si se selecciona y no puede verificarse, falla cerrado y nunca degrada a LOCAL.

La opcionalidad del Trust Anchor no elimina autorización directa del propietario, autenticidad local, atomicidad, idempotencia, fencing, reconciliación ni recuperación fail-closed.

## 3. ME-D4O-A — bootstrap por perfil

El contrato detallado está en [ME-D4O-A](ME-D4O-A-authenticated-domain-bootstrap.md).

### Baseline LOCAL

- Requiere descriptor canónico, acción explícita del propietario y evidencia local verificable ligada al dominio/época/perfil.
- La verificación de autorización no puede aceptar un objeto fabricado por el caller ni depender de una fila SQLite que se está activando.
- Requiere evento de génesis explícito, autenticado por los puertos locales y aplicado junto con idempotencia, head y gate en una misma `SQLiteUnitOfWork`.
- No exige proveedor Trust Anchor externo ni afirma anti-rollback.
- El formato de evidencia directa del propietario debe alinearse con identidad/CAM; sigue pendiente conforme a `docs/contracts/memory.md` §8.

### Extensión ANCHORED futura

- Requiere proveedor externo independiente con inicialización create-if-absent, lectura y CAS monotónico.
- Requiere reconciliación de fallos entre proveedor y SQLite.
- La implementación real permanece postergada. No se construye una ancla ficticia local ni se habilita fallback.

## 4. ME-D4O-B — admisión durable

El diseño técnico inicial está documentado en [ME-D4O-B — Diseño de admisión durable de lectura](ME-D4O-B-durable-read-admission.md). La inspección de identidad/CAM confirmó que el binding de sujeto y el snapshot de lectura son evidencia de autenticación/autorización para esa lectura, pero no evidencia de acción directa del propietario. Por ello, D4O-B puede consumir snapshots CAM sin simular aprobación del propietario; el bootstrap LOCAL y Forget mantienen su dependencia separada de OwnerDecisionVerifier/evidencia directa.

Puede desarrollarse para el baseline LOCAL, manteniendo gate cerrado hasta completar bootstrap y validación:

- Implementar `admit_read` sobre la misma `SQLiteUnitOfWork` del journal.
- Verificar snapshot CAM, rutas registradas, revisiones, supresión, invalidaciones pendientes y ausencia de recuperación activa.
- Registrar `READ_ADMITTED` y derivar la admisión desde la proyección verificada.
- Resolver reintentos por snapshot/operación exactos, sin duplicar admisiones.
- No restaurar capacidades bearer ni handles protegidos después de reinicio.

La admisión operativa no puede habilitarse antes de un bootstrap LOCAL autenticado y verificado.

## 5. ME-D4O-C — egress durable

Puede desarrollarse en perfil LOCAL sin proveedor Trust Anchor:

- Implementar `commit_and_emit` con revalidación de admisión, generación, endpoint, secuencia, handle, revisiones y expiración del Grant.
- Persistir `EGRESS_COMMITTED` antes de devolver el recibo.
- Hacer repetición idempotente por emisión y rechazar IDs reutilizados con contenido distinto.
- SQLite puede comprometer el derecho/orden local de emisión, pero no atomiza la aceptación remota. La aceptación remota requiere idempotencia/fencing y evidencia verificable del receptor.

## 6. ME-D4O-D — lifecycle, Forget e invalidación

Puede desarrollarse bajo el baseline LOCAL:

- Implementar `finish`, `fence`, `record_endpoint_ack`, `reconcile` y `get_nonterminal_admissions`.
- Persistir recibos de endpoint en el journal autenticado.
- Implementar Forget e invalidación con captura exacta de admisiones/rutas, fencing y reconciliación.
- Serializar admisión, invalidación, Forget y egress en el mismo orden transaccional SQLite.

**Límite inalterado:** el perfil LOCAL no puede demostrar que un backup restaurado sea posterior a un Forget. Si la restauración puede reintroducir contenido olvidado, la exposición debe permanecer bloqueada hasta reconciliar la supresión contra una fuente independiente aprobada. No declarar Forget completo ni garantía de no reaparición basándose solo en integridad local del backup.

## 7. ME-D4O-E — composición de autoridad completa

- Crear una implementación que satisfaga `ProtectedMemoryRecoveryAuthorityPort`.
- Exigir identidad exacta del `SQLiteConsistencyJournal` y de la `SQLiteDatabase`.
- Inyectar la misma instancia en `MemoryGatewayService` y `RecoveryJournalCoordinator`.
- Mantener las verificaciones del perfil LOCAL explícitas en resultados y composición.
- La futura composición ANCHORED añadirá el proveedor externo; no debe ser requisito para la composición LOCAL.
- No habilitar runtime hasta ejecutar pruebas de rollback, concurrencia multiproceso, reinicio, fallos ambiguos y restricciones de restauración/Forget.

## 8. Reglas transaccionales comunes

Cada mutación local compuesta debe:

1. Obtener recuperación local `VERIFIED` con perfil explícito; nunca usar lectura estructural como autoridad.
2. Abrir `SQLiteUnitOfWork` (`BEGIN IMMEDIATE`).
3. Comparar head y commitment actuales con el snapshot verificado.
4. Comprobar proyección de admisiones, cierres, invalidaciones y recuperaciones.
5. Ejecutar `append_transition_in(...)` en la misma UoW.
6. Actualizar proyecciones materializadas en esa misma transacción.
7. Confirmar todo junto o revertir todo.

La proyección SQLite del gate no se convierte en autoridad paralela. Una discrepancia con el journal autenticado debe fallar cerrada.

## 9. Invariantes que no cambian

- El modelo no autoriza operaciones ni decide permisos.
- Gateway y RecoveryCoordinator comparten una única autoridad.
- Un snapshot CAM no sustituye la revalidación de revisiones en egress.
- Ninguna admisión nueva durante recuperación pendiente, Forget aplicable o invalidación aplicable.
- Un endpoint solo es terminal con recibo correlacionado y validado.
- Timeout o pérdida de conexión no significa fencing.
- Una admisión no terminal tras reinicio es UNRESOLVED; no se restaura el emisor anterior.
- SQLite no proporciona por sí solo anti-rollback externo ni atomicidad con transportes remotos.
- No se afirma entrega remota irreversible a partir de un commit SQLite local.
- El perfil LOCAL no degrada ni se presenta como ANCHORED.
- Las restauraciones que puedan preceder a Forget/fencing/cierres no se exponen sin reconciliación independiente aprobada.

## 10. Estado y criterio para continuar

ME-D4K–D4N proporcionan primitivas parciales (UoW, append/checkpoint en UoW y adaptador gate-only); las pruebas siguen pendientes. El diseño D4O-B ya está especificado, pero su código aún no está implementado. No existe aún implementación concreta completa de `ProtectedMemoryRecoveryAuthorityPort`.

La corrección de ME-D4O-A elimina la dependencia del proveedor externo para el baseline. Se puede continuar con el desarrollo de D4O-B, C y D en LOCAL, manteniendo runtime protegido deshabilitado hasta que el bootstrap local, evidencia de propietario, autoridad compuesta y validación estén completos. La integración ANCHORED queda para la etapa final.

No se declara implementación operativa, no se modifica esquema ni runtime en esta fase, y no se ejecutan pruebas/build/CI sin autorización del propietario.
