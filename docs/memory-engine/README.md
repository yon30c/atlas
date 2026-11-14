# Memory Engine — configuración local

> Esta guía documenta la infraestructura SQLite que existe en la rama `feature/atlas-functional-f1`. No significa que el Memory Engine persistente, el Recovery Gate o la autoridad protegida estén listos para producción.

## Estado actual

El perfil SQLite local ofrece:

- Base de datos en archivo (no admite `:memory:`).
- WAL, claves foráneas activadas, `synchronous=FULL` y timeout configurable.
- Migraciones consecutivas con comprobación de checksum.
- Journal de consistencia con append autenticado, idempotencia, resolución de operaciones y checkpoints.
- Separación entre lectura estructural y recuperación verificada.

El esquema reserva campos para el Recovery Gate, pero todavía no existe una implementación SQLite de `ProtectedMemoryRecoveryAuthorityPort`. No abras ni actives el gate manualmente.

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

Esta guía refleja el código y esquema inspeccionados. No se ejecutaron pruebas ni build durante ME-D4I/ME-D4J. Siguen pendientes la autoridad SQLite concreta, las pruebas multiproceso, la atomicidad de admisión/egress y la apertura segura del Recovery Gate.

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

**Límite de esta fase:** `SQLiteConsistencyJournal` todavía utiliza `write_transaction()` por su cuenta. No existe aún un método journal que acepte esta unidad de trabajo, y la autoridad del Recovery Gate no está implementada. Por tanto, no es posible realizar todavía una operación atómica compuesta entre gate y journal. La API nueva no debe utilizarse para simular esa integración.

La implementación se añadió, pero no se ejecutaron pruebas ni build. Los tests unitarios nuevos cubren commit, rollback, ownership, anidamiento y compatibilidad; quedan pendientes de ejecución por el propietario.


## ME-D4L — append del journal dentro de SQLiteUnitOfWork

- `SQLiteConsistencyJournal.append_transition_in(unit_of_work, ...)` reutiliza la conexión activa de una unidad de trabajo propiedad de la misma instancia `SQLiteDatabase`.
- La operación interna no abre, confirma ni revierte transacciones. Conserva la validación de dominio/época, idempotencia, canonicalización, firma del envelope, persistencia de entrada/operación y CAS del head.
- Los fallos inesperados de firma o persistencia se propagan desde la operación interna para que el propietario de la unidad de trabajo revierta todas las mutaciones compuestas.
- `append_transition(...)` conserva su firma y contrato anterior: abre su propia unidad de trabajo y convierte fallos ordinarios en `None`.
- La integración cubre únicamente `append_transition`. `create_local_domain`, `commit_checkpoint` y otras operaciones todavía administran sus propias transacciones; no deben combinarse suponiendo atomicidad con una UoW externa.
- Se añadieron pruebas para reutilización de UoW y rollback de una mutación acompañante ante fallo del signer. **No ejecutadas**.
