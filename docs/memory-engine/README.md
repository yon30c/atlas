# Memory Engine — configuración local

> Esta guía documenta la infraestructura SQLite que existe en la rama `feature/atlas-functional-f1`. No significa que el Memory Engine persistente, el Recovery Gate o la autoridad protegida estén listos para producción.

## Estado actual

El perfil SQLite local ofrece:

- Base de datos en archivo (no admite `:memory:`).
- WAL, claves foráneas activadas, `synchronous=FULL` y timeout configurable.
- Migraciones consecutivas con comprobación de checksum.
- Journal de consistencia con append autenticado, idempotencia, resolución de operaciones y checkpoints.
- Separación entre lectura estructural y recuperación verificada.

El esquema reserva campos para el Recovery Gate y ya existe un adaptador SQLite gate-only, pero todavía no existe una implementación completa de `ProtectedMemoryRecoveryAuthorityPort` que comparta autoridad con admisión y egress. No abras ni actives el gate manualmente.

## Requisitos

- Python y dependencias del proyecto instaladas.
- Directorio local persistente, propiedad de la cuenta de servicio de Atlas.
- Ruta absoluta para el archivo SQLite.
- Firmante local que implemente `LocalConsistencySignerPort.sign_envelope()`.
- Para recuperación operativa: `LocalConsistencyRecoveryVerifier` y `LocalConsistencyTrustPolicy` configurados y vinculados.

No guardes la base en directorios temporales, carpetas sincronizadas en la nube ni volúmenes compartidos entre hosts.

## 1. Crear y configurar la base

Desde la raíz del repositorio:

```python
from pathlib import Path
from atlas.adapters.sqlite import SQLiteDatabase, SQLITE_MIGRATIONS

data_dir = Path("/ruta/absoluta/atlas-data/consistency")
data_dir.mkdir(parents=True, exist_ok=True)

database = SQLiteDatabase(
    data_dir / "atlas-consistency.sqlite3",
    busy_timeout_ms=5000,
)

database.apply_migrations(SQLITE_MIGRATIONS)
```

Sustituye la ruta por una ubicación absoluta real. El directorio padre debe existir antes de construir `SQLiteDatabase`.

- `apply_migrations` configura WAL, crea el ledger y aplica el historial completo y consecutivo.
- El esquema actual contiene `CORE_SCHEMA_V1`, `CORE_SCHEMA_V2` y `CORE_SCHEMA_V3`.
- Las migraciones ya publicadas no deben editarse: se agrega una nueva versión.
- `busy_timeout_ms` controla la espera por escritores ocupados; no sustituye una transacción ni un control de concurrencia.

## 2. Configurar el journal

El journal recibe una implementación real del firmante local y metadatos de emisión:

```python
from atlas.adapters.sqlite.consistency_journal import SQLiteConsistencyJournal

journal = SQLiteConsistencyJournal(
    database,
    signer=signer_local_configurado,
    reducer_version="versión-del-reducer",
    issuer_id="identificador-del-emisor",
    issuer_role="rol-del-emisor",
    key_reference="referencia-opaca-de-clave",
    trust_policy_version="versión-de-política",
)
```

Los valores anteriores son marcadores, no credenciales listas para usar. El firmante y la custodia de claves deben proceder de una implementación local aprobada. La clave privada no se almacena en SQLite.

Para recuperación operativa se deben proporcionar ambos argumentos adicionales:

```python
journal = SQLiteConsistencyJournal(
    database,
    signer=signer_local_configurado,
    reducer_version="versión-del-reducer",
    issuer_id="identificador-del-emisor",
    issuer_role="rol-del-emisor",
    key_reference="referencia-opaca-de-clave",
    trust_policy_version=trust_policy.policy_version,
    recovery_verifier=recovery_verifier,
    recovery_trust_policy=trust_policy,
)
```

El verificador debe usar exactamente el mismo objeto `trust_policy` que se inyecta al journal. El constructor rechaza una configuración parcial o versiones discordantes. La configuración concreta del firmante, verificador y política depende de la implementación de custodia y confianza elegida; esta guía no inventa esos componentes.

## 3. Crear el dominio local

Después de aplicar migraciones y construir el journal:

```python
created_or_matches = journal.create_local_domain(
    domain_id="atlas-local",
    authority_epoch=1,
)
if not created_or_matches:
    raise RuntimeError("Dominio existente incompatible o error de creación")
```

El método no modifica un dominio existente. Solo devuelve éxito si coinciden la época, el perfil local y la versión de política. No incrementes la época para resolver un error sin un procedimiento de recuperación aprobado.

## 4. Límites de seguridad

Hasta implementar y validar la autoridad SQLite compartida:

- No actualices `consistency_domains.recovery_gate_state` mediante SQL manual.
- No cambies el gate y luego llames a `append_transition()` en otra transacción.
- No crees autoridades distintas para Gateway y Recovery Coordinator.
- No uses `load_recovery_state` como evidencia autenticada; las decisiones operativas requieren recuperación verificada.
- No habilites egress protegido ni declares Forget terminal solo porque el journal aceptó una transición.
- No compartas la base SQLite entre hosts.

ME-D4H exige una única instancia de autoridad vinculada al mismo journal que usan los puertos de persistencia y recuperación. Esa composición contractual no sustituye la implementación atómica que falta.

## 5. ME-D4J: diseño de la unidad de trabajo

La siguiente frontera transaccional debe:

1. Abrir una conexión configurada bajo `BEGIN IMMEDIATE`.
2. Entregar la misma unidad de trabajo a autoridad y journal; ninguno debe abrir una transacción interna.
3. Confirmar o revertir conjuntamente la transición autenticada, idempotencia, head del journal y mutación del Recovery Gate.
4. Mantener los métodos públicos existentes como wrappers compatibles que abran su propia unidad de trabajo.
5. Verificar que la unidad de trabajo pertenece a la instancia de base de datos correcta y sigue activa.

SQLite no puede incluir la aceptación irrevocable de un endpoint remoto dentro de su transacción. El egress requiere además fencing e idempotencia verificables en el receptor. ME-D4J no habilita todavía la entrega protegida.

## 6. Copias y operación

- Detén el proceso escritor antes de copiar manualmente la base, o usa un procedimiento SQLite que incluya correctamente WAL.
- No asumas que copiar solo el archivo principal mientras hay escritores activos produce un backup completo.
- Restringe permisos del directorio y archivo a la cuenta de servicio.
- Mantén las claves fuera de SQLite.
- El perfil local no tiene una raíz anti-rollback independiente: restaurar un backup antiguo no prueba que el estado sea el más reciente.

## Validación y pendientes

Esta guía refleja el código y esquema inspeccionados. No se ejecutaron pruebas ni build durante ME-D4I/ME-D4J. ME-D4N aporta un adaptador SQLite gate-only con pruebas añadidas pero aún no ejecutadas. Siguen pendientes la autoridad común para admisión/egress, la validación multiproceso y el anti-rollback externo.

Referencias: [contrato de memoria](../contracts/memory.md) · [registro de implementación](../design/memory-engine-project-independence-implementation.md).


## ME-D4K — unidad de trabajo SQLite disponible (sin integración en journal)

La infraestructura ahora expone `SQLiteUnitOfWork` y `SQLiteDatabase.unit_of_work()`:

```python
with database.unit_of_work() as unit:
    connection = unit._connection_for(database)  # uso interno de adaptadores
    connection.execute("INSERT INTO tabla_local(valor) VALUES (?)", ("dato",))
# commit al salir; rollback si se propaga una excepción
```

La unidad está ligada a la instancia exacta de `SQLiteDatabase`, solo permanece activa durante su contexto y rechaza anidamiento en el mismo hilo. La API `write_transaction()` sigue disponible y conserva el acceso legacy a la conexión.

**Límite original de ME-D4K, actualizado por ME-D4L/M/N:** el journal ya dispone de `append_transition_in(...)` y `commit_checkpoint_in(...)`. ME-D4N añade un adaptador gate-only que comparte la UoW con el append. Todavía no existe una autoridad completa que haga compartir esa misma frontera a admisión y egress.

La implementación base se añadió; las pruebas de la UoW y sus integraciones posteriores siguen pendientes de ejecución por el propietario.


## ME-D4L — append del journal dentro de SQLiteUnitOfWork

- `SQLiteConsistencyJournal.append_transition_in(unit_of_work, ...)` reutiliza la conexión activa de una unidad de trabajo propiedad de la misma instancia `SQLiteDatabase`.
- La operación interna no abre, confirma ni revierte transacciones. Conserva la validación de dominio/época, idempotencia, canonicalización, firma del envelope, persistencia de entrada/operación y CAS del head.
- Los fallos inesperados de firma o persistencia se propagan desde la operación interna para que el propietario de la unidad de trabajo revierta todas las mutaciones compuestas.
- `append_transition(...)` conserva su firma y contrato anterior: abre su propia unidad de trabajo y convierte fallos ordinarios en `None`.
- La integración cubre únicamente `append_transition`. `create_local_domain`, `commit_checkpoint` y otras operaciones todavía administran sus propias transacciones; no deben combinarse suponiendo atomicidad con una UoW externa.
- Se añadieron pruebas para reutilización de UoW y rollback de una mutación acompañante ante fallo del signer. **No ejecutadas**.


## ME-D4M — checkpoint y marcador dentro de SQLiteUnitOfWork

- SQLiteConsistencyJournal.commit_checkpoint_in(unit_of_work, ...) ejecuta la persistencia del checkpoint, marcador autenticado, registro idempotente y actualización CAS del head usando la conexión de la UoW externa.
- La operación valida el tipo, propietario y estado activo de la UoW. No abre, confirma ni revierte transacciones.
- Los errores inesperados de SQLite se propagan para que el propietario revierta también las mutaciones acompañantes. Los fallos del signer y los conflictos conservan sus estados de resultado y ocurren antes de las escrituras del checkpoint.
- commit_checkpoint(...) conserva su firma pública y abre una UoW propia; ante errores transaccionales ambiguos devuelve UNKNOWN, manteniendo la reconciliación por identificador estable.
- Se añadieron pruebas para commit dentro de una UoW externa y rollback de mutaciones acompañantes cuando falla la inserción del marcador. **No ejecutadas**.
- Esto no implementa la autoridad Recovery Gate ni demuestra todavía atomicidad de admisión/gate/egress.

## ME-D4N — adaptador SQLite del Recovery Gate

Se implementó LocalSQLiteRecoveryGateAdapter, vinculado a una instancia exacta de SQLiteConsistencyJournal, con las cuatro operaciones de RecoveryGatePort:

- close_recovery_gate: append RECOVERY_CLOSED y cierre materializado dentro de una misma SQLiteUnitOfWork.
- ensure_recovery_gate_closed: restaura únicamente la operación/generación activa demostrada por recuperación local verificada.
- reconcile_and_open_recovery_gate: valida el recibo terminal global, persiste RECOVERY_RECONCILED y abre el gate en el mismo commit.
- ensure_recovery_gate_open: restaura apertura solo para el cierre reconciliado más reciente y su recibo exacto.

La composición compose_local_sqlite_recovery_gate_coordinator(...) conecta este gate con RecoveryJournalCoordinator. Es una composición gate-only, distinta de la autoridad completa que requiere MemoryGateway.

No se añadió migración: los campos de proyección del gate ya existían en consistency_domains desde V1.

Límite crítico: no se implementaron todavía admit_read, Forget/invalidation ni commit_and_emit sobre esta misma UoW. Por eso no se afirma atomicidad global con lecturas o egress. El perfil local tampoco dispone de anti-rollback externo.

Se añadieron pruebas de cierre, reapertura, rollback, recibo exacto, restauración y concurrencia. No ejecutadas; no se ejecutaron build ni CI.

Diseño y límites: [ME-D4N — Recovery Gate SQLite](../design/ME-D4N-sqlite-recovery-gate.md).


## ME-D4O — bootstrap e integración de autoridad SQLite

La inspección confirmó un bloqueo previo a la admisión durable: `consistency_domains.recovery_gate_state` nace `closed`, pero el contrato actual solo permite abrirlo tras un `RECOVERY_RECONCILED` verificado. No existe evento/puerto de bootstrap inicial, y el coordinador de recovery no abre un dominio vacío.

No se debe solucionar con UPDATE manual ni default abierto. El diseño ME-D4O divide el trabajo en: (A) contrato de bootstrap autenticado; (B) admisión durable; (C) egress durable; (D) lifecycle de admisiones/Forget/invalidation; (E) composición completa `ProtectedMemoryRecoveryAuthorityPort`.

**Estado:** ME-D4O-A define el protocolo de bootstrap autenticado, pero sigue sin implementación porque faltan el proveedor independiente de autorización del propietario y el Trust Anchor con inicialización autenticada. No se añadió evento ni apertura del gate. Admisión/egress permanecen bloqueados. Véase [ME-D4O-A](../design/ME-D4O-A-authenticated-domain-bootstrap.md). Pruebas/build/CI siguen pendientes y no se ejecutaron.

Véase [ME-D4O — bootstrap seguro e integración](../design/ME-D4O-sqlite-authority-bootstrap-and-integration.md).
