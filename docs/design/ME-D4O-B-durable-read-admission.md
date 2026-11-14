# ME-D4O-B — Diseño de admisión durable de lectura

**Estado:** diseño técnico de implementación; código y pruebas pendientes.  
**Rama objetivo:** `feature/atlas-functional-f1`.  
**Perfil:** LOCAL. No requiere Trust Anchor externo.  
**Dependencias:** ME-D4K, ME-D4L, ME-D4M y ME-D4N.

## 1. Propósito y límite

Implementar `ReadConsistencyAuthorityPort.admit_read(...)` como primera operación de la autoridad durable de memoria protegida.

La admisión ordena una lectura autorizada por CAM frente a Forget, invalidaciones y recuperación. No recupera contenido, no crea handles, no emite datos y no abre el Recovery Gate.

El trabajo de D4O-B puede desarrollarse antes del bootstrap LOCAL, pero no habilita admisiones operativas mientras el dominio no tenga génesis autenticada y recuperación verificada. El gate permanece cerrado por defecto.

## 2. Hallazgos de identidad y CAM

La inspección de la rama confirma:

- `Identity` y `OperationContext` son datos inmutables de atribución/contexto; no prueban autenticación ni conceden permisos.
- `IdentitySubjectBindingPort.resolve_user_subject(actor_identity_id)` consulta una fuente declarada autoritativa y `resolve_authenticated_user_binding(...)` comprueba actor USER/ACTIVE, coincidencia de identidad y revisión.
- `MemoryAuthorizationService.authorize_read(...)` emite el snapshot CAM después de resolver la memoria/versión, comprobar binding del sujeto PRIVATE o Grant/revisiones PROJECT y evaluar la autorización.
- `AuthorizationSnapshot` compromete recurso, versión, owner, scope, actor, decisión, solicitud y revisiones. No es un permiso autónomo ni sustituye revalidación durable.
- El contrato de memoria §8 mantiene pendiente el mecanismo técnico de evidencia de acción directa del propietario. El binding de identidad y un snapshot de lectura no constituyen esa evidencia.

Consecuencia: `admit_read` consume exclusivamente un `AuthorizationSnapshot` CAM válido para la lectura. No simula una decisión directa del propietario. El futuro bootstrap LOCAL y las operaciones no delegables de aprobación/Forget requieren un mecanismo separado de acción del propietario, ligado a descriptor/objetivo exactos y validado fuera de la fila SQLite que se modifica.

## 3. Entrada y validación

La operación recibe:

- `AuthorizationSnapshot` emitido por CAM;
- `DeliveryRouteSet` con conjunto no vacío de rutas registradas;
- instante UTC confiable.

Antes de abrir la UoW se rechazan entradas mal tipadas, timestamps no UTC, snapshot no correspondiente a `memory.read`, versiones no APPROVED, clasificación RESTRICTED, IDs inconsistentes, scope inválido o rutas vacías. Estas comprobaciones estructurales no sustituyen las revalidaciones transaccionales.

La autoridad debe validar que el snapshot incluya las revisiones obligatorias y que:
- memory/version/identity revision IDs correspondan exactamente al recurso, versión y actor;
- PRIVATE tenga sujeto autenticado igual al owner y no incluya revisiones PROJECT/Grant;
- PROJECT incluya project, environment y Grant, con IDs exactos y expiración;
- las rutas solicitadas estén cubiertas por el registro confiable de rutas del dominio. No se acepta que el caller amplíe la cobertura declarada.

## 4. Fuente de verdad y secuencia atómica

La implementación debe usar la misma instancia de `SQLiteDatabase` y `SQLiteConsistencyJournal` que utilizarán las demás operaciones de la autoridad.

Secuencia dentro de una única `SQLiteUnitOfWork`:

1. Obtener estado de recuperación LOCAL verificado mediante el puerto configurado. La lectura estructural del journal no es evidencia operativa.
2. Exigir resultado VERIFIED del dominio/época/política exactos y perfil LOCAL explícito.
3. Comparar head sequence y commitment del estado verificado con el head actual dentro de la UoW. Si difieren, abortar y requerir nueva verificación.
4. Reconstruir/reducir la proyección verificada hasta el head exacto.
5. Exigir gate abierto en la proyección autenticada y proyección materializada coincidente. Cualquier discrepancia falla cerrado.
6. Rechazar recuperación activa, Forget no reconciliado/supresión aplicable, invalidación aplicable o admisión previa no terminal incompatible.
7. Revalidar revisiones del snapshot y su vigencia contra resolvers autoritativos actuales. Un snapshot CAM antiguo no congela identidad, memoria, versión, proyecto, entorno ni Grant.
8. Resolver idempotencia exacta. Repetición idéntica del mismo snapshot y conjunto de rutas devuelve la admisión original; misma clave con contenido distinto es conflicto. No se duplican READ_ADMITTED.
9. Calcular generación desde la proyección verificada; no aceptar generación del caller.
10. Construir `ConsistencyTransition(READ_ADMITTED, schema_version=2)` con campos del snapshot exacto, owner, actor, request, scope, revisiones, admission_id, generación y rutas.
11. Ejecutar `append_transition_in(unit_of_work, ...)`.
12. Actualizar cualquier proyección materializada de admisión en la misma UoW, si el diseño de almacenamiento la requiere. El journal autenticado sigue siendo fuente de verdad.
13. Confirmar una sola vez. Cualquier fallo inesperado revierte append y proyección.

No se permite hacer el append y luego actualizar el estado de admisiones en otra transacción.

## 5. Idempotencia y resultados ambiguos

- La clave idempotente debe derivarse de una identidad estable de la solicitud de admisión, ligada al snapshot CAM y al conjunto exacto de rutas.
- El registro debe comprometer la solicitud canónica completa. La misma clave con snapshot, recurso, revisiones, generación o rutas distintas debe producir conflicto.
- Un reintento tras resultado ambiguo debe reconciliarse consultando la clave y comparando el request canónico completo; no debe generar otra admisión.
- No se debe devolver una admisión reconstruida desde una fila auxiliar sin comprobarla contra el journal autenticado.

La forma final de la clave y el ID estable de admisión se fijarán en implementación para respetar el formato de IDs ya vigente, sin introducir un nuevo esquema de persistencia.

## 6. Reinicio y capacidades

Una admisión durable no restaura una capacidad bearer ni un `ProtectedContentHandle`.

Después de reinicio:
- las admisiones no terminales se consideran UNRESOLVED hasta reconciliación;
- no se recrean handles ni sesiones de Gateway;
- el contenido no se expone por el mero hecho de que exista un READ_ADMITTED;
- la recuperación debe cerrar/fencear las rutas pendientes y producir recibos verificables antes de terminalizar.

El estado durable describe el orden y la obligación de reconciliación, no una autorización reutilizable.

## 7. Pruebas requeridas para la fase de validación posterior

- gate cerrado o dominio no bootstrappeado => no admite;
- recuperación UNAVAILABLE/REJECTED o head divergente => no admite;
- snapshot mal ligado a IDs/revisiones/scope => no admite;
- snapshot PRIVATE y PROJECT válido con rutas exactas;
- Grant expirado/revocado o revisión cambiada => no admite;
- Forget/supresión o invalidación pendiente => no admite;
- recuperación activa => no admite;
- admisión y append comparten UoW y rollback conjunto;
- reintento idéntico devuelve la misma admisión;
- reutilización de idempotency key con contenido distinto => conflicto;
- concurrencia multiproceso entre admit_read y cierre/invalidación;
- reinicio no restaura handles ni bearer capabilities;
- fallo de signer/persistencia => rollback completo.

Las pruebas no se ejecutan en esta etapa; se reservarán para la validación acordada en el servidor.

## 8. Fuera de alcance

- Bootstrap `DOMAIN_BOOTSTRAPPED` y evidencia directa del propietario.
- Implementación del `OwnerDecisionVerifier` o mecanismo de acción directa.
- `commit_and_emit`, endpoint acknowledgements, fencing y finalización.
- Forget físico, inventario de destinos y eliminación verificable.
- Trust Anchor ANCHORED.
- Composición completa `ProtectedMemoryRecoveryAuthorityPort`.
- Activación de runtime protegido, despliegue, migraciones o cambios de servicio.

## 10. Inspección de implementación y dependencias faltantes

La inspección de código en la rama confirmó:

- `SQLiteConsistencyJournal.append_transition_in(...)` ya permite insertar `READ_ADMITTED v2` dentro de una UoW externa.
- `SQLiteUnitOfWork` ya proporciona `BEGIN IMMEDIATE`, ownership exacto y rollback compuesto.
- `LocalConsistencyRecoveryVerifier` produce `VerifiedLocalConsistencyRecoveryState` con proyección semántica, pero el dominio vacío sin evento de génesis no puede producir una proyección VERIFIED operativa.
- `ConsistencyJournalReducer` rechaza READ_ADMITTED durante recuperación activa, después de Forget aplicable y antes de reconciliar invalidaciones aplicables.
- `MemoryMetadataResolver` resuelve memoria, versión, proyecto y entorno exactos; `IdentitySubjectBindingPort` resuelve binding autenticado; CAM obtiene Grants desde `GrantRepository`.
- No existe todavía un puerto de registro confiable de rutas de entrega ni una frontera común que permita a la autoridad comprobar que todos los IDs de ruta están registrados.
- No existe un contrato de lectura/revalidación de revisiones que garantice orden coherente entre los cambios de metadatos/identidad/Grant y sus eventos de invalidación en el journal.
- `LocalSQLiteRecoveryGateAdapter` es gate-only; no hay autoridad SQLite que implemente actualmente `admit_read`.

### Consecuencia de diseño

No se debe añadir una implementación que acepte como confiables las rutas del caller, que compare revisiones solo con el snapshot CAM original o que lea el estado del journal sin verificación independiente.

Antes del adaptador SQLite de admisión se deben definir e implementar dos fronteras confiables:

1. **Route Registry Port:** resolución/validación de todos los route IDs contra configuración confiable, con rechazo total ante IDs desconocidos o registro no disponible.
2. **Revision Validation Port:** validación actual y coherente de las revisiones MEMORY, MEMORY_VERSION, IDENTITY y, para PROJECT, PROJECT, ENVIRONMENT y GRANT. Debe definir cómo se serializa el cambio de revisión con la invalidación durable; una consulta puntual no basta para eliminar la carrera entre validación y append.

La validación de revisiones no debe asumir que una lectura de varios repositorios independientes es atómica. Si los authorities no pueden compartir transacción, el contrato debe especificar una secuencia monotónica de invalidación/fencing que haga imposible emitir con una revisión obsoleta.

### Orden actualizado de implementación

1. Definir contratos neutrales y resultados fail-closed para Route Registry y Revision Validation.
2. Implementar adaptadores Atlas sobre las fuentes autoritativas existentes y documentar sus garantías de orden.
3. Implementar el coordinador SQLite de admisión: verified projection → BEGIN IMMEDIATE → head/CAS exactos → validaciones → idempotencia → append en UoW.
4. Componerlo con la autoridad única y el Recovery Gate sin declarar aún completa la autoridad de egress/Forget.
5. Mantener runtime protegido deshabilitado hasta bootstrap LOCAL, composición total y pruebas de servidor.

No se ejecutan pruebas/build/CI en esta etapa, según lo acordado.

## 11. Criterio de salida

D4O-B solo se considera implementado cuando la admisión durable está ligada al snapshot CAM exacto, se serializa con cierres e invalidaciones en la misma autoridad SQLite, es idempotente, se recupera sin restaurar capacidades y falla cerrado ante cualquier evidencia incompleta.

Su implementación no habilita runtime protegido. Esa habilitación requiere además bootstrap LOCAL autenticado, autoridad compuesta completa, pruebas y revisión de seguridad.
