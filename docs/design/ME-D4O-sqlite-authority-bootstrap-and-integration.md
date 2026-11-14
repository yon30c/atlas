# ME-D4O — Bootstrap seguro e integración de la autoridad SQLite

**Estado:** ME-D4O-A definido a nivel contractual; implementación bloqueada por dependencias externas de autorización y Trust Anchor.  
**Rama:** `feature/atlas-functional-f1`.  
**Alcance:** preparar la implementación de `ProtectedMemoryRecoveryAuthorityPort` sin activar el runtime.

## 1. Hallazgo bloqueante confirmado

El esquema `consistency_domains` define:

- `recovery_gate_state TEXT NOT NULL DEFAULT 'closed'`;
- `active_recovery_operation_id`;
- `active_recovery_generation`;
- `recovery_receipt_id`.

`SQLiteConsistencyJournal.create_local_domain(...)` no establece un estado abierto: inserta el dominio y deja actuar el valor predeterminado `closed`.

El adaptador `LocalSQLiteRecoveryGateAdapter.ensure_recovery_gate_open(...)` solo restaura apertura cuando la proyección autenticada contiene el cierre reconciliado más reciente, con operación, generación y recibo terminal exactos. No existe un evento de activación inicial del dominio ni un método de bootstrap en `RecoveryGatePort`.

El coordinador de recuperación tampoco resuelve el caso vacío: `RecoveryJournalCoordinator._ensure_closed(...)` exige un plan con admisiones pendientes y no crea un evento terminal de recuperación para abrir un dominio nuevo sin admisiones.

**Consecuencia:** un dominio recién creado comienza cerrado y no dispone de un camino contractual para llegar a abierto. La admisión SQLite no debe implementarse suponiendo que el gate está abierto ni debe corregirse con un UPDATE manual.

## 2. No confundir bootstrap con recuperación

Son operaciones distintas:

- **Bootstrap:** primera activación deliberada de un dominio recién creado, antes de que existan admisiones.
- **Recovery:** cierre de un dominio que ya tuvo operaciones y debe cercar capacidades/emisores anteriores después de una interrupción o inconsistencia.

Un recibo de recuperación no debe reutilizarse como prueba de bootstrap. Tampoco debe aceptarse la ausencia de eventos como prueba suficiente de que el dominio está íntegro o es el más reciente: una base restaurada puede ser una versión antigua.

## 3. Decisión de diseño pendiente

Antes de implementar el bootstrap debe elegirse y documentarse una autoridad de activación que cumpla todos estos puntos:

1. Aprobación explícita del propietario/operador autorizado para activar ese dominio concreto.
2. Evidencia verificable, ligada al ID del dominio, época, política de confianza y compromiso de estado inicial.
3. Identidad y custodia de la clave verificadora independientes del contenido SQLite que se está activando.
4. Idempotencia: repetir la misma activación produce el mismo resultado; una activación distinta o contradictoria falla cerrada.
5. No permitir que un proceso de restauración de backup convierta por sí mismo un dominio antiguo en el dominio activo.
6. Auditoría persistente de quién/qué autorizó la activación, cuándo y bajo qué política.
7. Sin bypass administrativo silencioso ni actualización directa de `recovery_gate_state`.

La protección anti-rollback externa sigue siendo una limitación del perfil local actual. Mientras no exista un ancla independiente adecuada, no se debe afirmar que una restauración de SQLite prueba frescura.

## 4. Secuencia propuesta para ME-D4O

La integración se dividirá para evitar una implementación monolítica y no verificable.

### ME-D4O-A — contrato de bootstrap

- **Diseño completado, sin implementación.** El protocolo exige autorización explícita del propietario y ancla externa independiente.
- El TrustAnchorPort actual solo lee/avanza anclas existentes; falta inicialización autenticada create-if-absent y no hay proveedor concreto.
- No se añade todavía evento de génesis ni apertura del gate: hacerlo sin esas dependencias sería una falsa garantía de anti-rollback.
- Criterios, secuencia de dos fronteras y recuperación de fallos: [ME-D4O-A](ME-D4O-A-authenticated-domain-bootstrap.md).

### ME-D4O-B — admisión durable

Una vez resuelto el bootstrap:

- Implementar `admit_read` sobre la misma `SQLiteUnitOfWork` del journal.
- Verificar el snapshot CAM, rutas registradas, revisiones, supresión, invalidaciones pendientes y ausencia de recuperación activa.
- Registrar `READ_ADMITTED` v2 y derivar la admisión desde la proyección verificada.
- Resolver reintentos por snapshot/operación exactos, sin duplicar admisiones.
- No restaurar capacidades bearer ni handles protegidos después de reinicio.

### ME-D4O-C — egress durable

- Implementar `commit_and_emit` con revalidación de admisión, generación, endpoint, secuencia, handle, revisiones y expiración del Grant.
- Persistir `EGRESS_COMMITTED` antes de devolver el recibo.
- Hacer la repetición idempotente por emisión y rechazar IDs reutilizados con contenido distinto.
- Mantener explícita la frontera: SQLite puede comprometer el derecho/orden de emisión, pero no puede atomizar por sí sola el transporte remoto. Cualquier aceptación remota requiere su propio protocolo de idempotencia/fencing y evidencia verificable.

### ME-D4O-D — lifecycle de admisiones

- Implementar `finish`, `fence`, `record_endpoint_ack`, `reconcile` y `get_nonterminal_admissions`.
- Persistir cada recibo de endpoint en el journal autenticado.
- Implementar Forget e invalidación con captura exacta de admisiones/rutas, fencing y reconciliación.
- Garantizar que admisión, invalidación, Forget y egress compiten por el mismo orden transaccional SQLite.

### ME-D4O-E — composición de autoridad completa

- Crear una implementación que satisfaga `ProtectedMemoryRecoveryAuthorityPort`.
- Exigir identidad exacta del `SQLiteConsistencyJournal` y de la `SQLiteDatabase`.
- Inyectar la misma instancia en `MemoryGatewayService` y `RecoveryJournalCoordinator`.
- Eliminar la composición gate-only como ruta de runtime; conservarla solo si sigue siendo útil para pruebas aisladas.
- No habilitar runtime hasta ejecutar pruebas de rollback, concurrencia multiproceso, reinicio y fallos ambiguos.

## 5. Reglas transaccionales comunes

Cada mutación local compuesta debe:

1. Obtener una recuperación local `VERIFIED`; nunca usar lectura estructural como autoridad.
2. Abrir `SQLiteUnitOfWork` (`BEGIN IMMEDIATE`).
3. Comparar el head y commitment actuales con el snapshot verificado.
4. Comprobar la proyección de admisiones, cierres, invalidaciones y recuperaciones.
5. Ejecutar `append_transition_in(...)` en la misma UoW.
6. Actualizar cualquier proyección materializada en esa misma transacción.
7. Confirmar todo junto o revertir todo.

La proyección SQLite del gate no se convierte en una autoridad paralela. Una discrepancia con el journal autenticado debe fallar cerrada.

## 6. Invariantes de seguridad que no deben debilitarse

- El modelo no autoriza operaciones ni decide permisos.
- MemoryGateway y RecoveryCoordinator deben compartir una única instancia de autoridad.
- Un snapshot CAM no sustituye la revalidación de revisiones en el punto de egress.
- Ninguna admisión nueva durante recuperación pendiente, Forget aplicable o invalidación aplicable.
- Un endpoint solo se considera terminal con recibo correlacionado y validado.
- Timeout o pérdida de conexión no significa fencing.
- Una admisión no terminal tras reinicio debe tratarse como UNRESOLVED; no se restaura el emisor anterior.
- SQLite no proporciona por sí solo anti-rollback externo ni atomicidad con transportes remotos.
- No se afirma entrega remota irreversible a partir de un commit SQLite local.

## 7. Estado de implementación

- ME-D4K: `SQLiteUnitOfWork` implementada.
- ME-D4L: `append_transition_in` implementado.
- ME-D4M: `commit_checkpoint_in` implementado.
- ME-D4N: adaptador gate-only implementado; sus pruebas siguen pendientes de ejecución.
- ME-D4O: inspección y diseño general completados.
- ME-D4O-A: contrato de bootstrap autenticado documentado; sin código ni proveedor. La admisión/egress siguen bloqueados.

No se ejecutaron pruebas, build ni CI. No se modificó el esquema, el runtime, Broker, Registry, Docker, systemd ni producción.

## 8. Criterio para continuar

El siguiente trabajo no es implementar `admit_read`: primero deben satisfacerse los criterios externos de ME-D4O-A (autorización de propietario verificable y proveedor de ancla independiente). No conectar MemoryGateway ni habilitar egress mientras falte cualquiera de ellos.
