# Memory Engine — configuración local y estado de implementación

> Esta guía describe la infraestructura existente en el repositorio. No significa que el Memory Engine persistente, la autoridad protegida o el runtime de lecturas/egress estén habilitados para producción.

## Estado funcional

El repositorio incluye:

- Journal de consistencia con append autenticado, idempotencia y resolución de operaciones.
- Checkpoints y proyecciones verificables.
- \`SQLiteDatabase\` con WAL, claves foráneas, \`synchronous=FULL\`, timeout configurable y migraciones consecutivas con checksum.
- \`SQLiteUnitOfWork\` para compartir una transacción entre adaptadores vinculados a la misma instancia de base de datos.
- \`LocalSQLiteRecoveryGateAdapter\`, que coordina operaciones del Recovery Gate con el journal dentro de una misma UoW.
- \`SQLiteAuthorityChangeStore\` para reservas durables e idempotencia semántica de cambios de autoridad.
- Coordinación de revocación de Grants en la capa de aplicación, con contratos de autorización y pruebas.
- Persistencia local de identidad canónica mediante \`SQLiteIdentityAuthority\`.

La conversación de Atlas Assistant todavía utiliza \`InMemoryConversationHistory\`. No existe una conexión operativa que convierta el historial de Assistant en memoria conversacional persistente.

## Esquema SQLite v1–v6

Las migraciones son consecutivas e inmutables:

| Versión | Alcance |
|---|---|
| v1 | Dominio local, journal y checkpoints |
| v2 | Referencia exacta de operación al commit del journal |
| v3 | Identidad de append separada de la correlación de operación |
| v4 | Ledger durable de cambios de autoridad, invalidaciones y evidencia de recuperación |
| v5 | Identidad canónica interna y relación UserId–Identity(USER) |
| v6 | Integridad bidireccional de la relación USER mediante claves foráneas diferidas |

La migración v6 exige que una identidad de tipo USER tenga su registro canónico de usuario correspondiente y viceversa al confirmar la transacción. Los registros USER huérfanos heredados hacen fallar la migración de forma atómica; la versión anterior debe permanecer intacta.

El esquema almacena metadatos de control, journal, checkpoints y relaciones de identidad. **No almacena contenido de memorias, embeddings ni snippets**. La persistencia de identidad no equivale a autenticación externa, issuer adapters, bindings externos ni VerifiedIdentityContext completo.

## Preparación de una base local

Requisitos:

- Python y dependencias del proyecto instaladas.
- SQLite 3.26.0 o superior en la biblioteca enlazada al módulo `sqlite3` de Python.
- Directorio persistente y ruta absoluta.
- Directorio propiedad de la cuenta que ejecuta Atlas.
- Firmante local aprobado que implemente \`LocalConsistencySignerPort.sign_envelope()\`.

No guardes la base en directorios temporales, carpetas sincronizadas en la nube ni volúmenes compartidos entre hosts.

Desde la raíz del repositorio:

\`\`\`python
from pathlib import Path
from atlas.adapters.sqlite import SQLiteDatabase, SQLITE_MIGRATIONS

data_dir = Path("/ruta/absoluta/atlas-data/consistency")
data_dir.mkdir(parents=True, exist_ok=True)

database = SQLiteDatabase(
    data_dir / "atlas-consistency.sqlite3",
    busy_timeout_ms=5000,
)
database.apply_migrations(SQLITE_MIGRATIONS)
\`\`\`

El directorio padre debe existir antes de construir \`SQLiteDatabase\`. Las migraciones publicadas no se editan: cualquier evolución requiere una nueva versión consecutiva.

## Configuración del journal

El journal necesita un firmante local y metadatos de emisión:

\`\`\`python
from atlas.adapters.sqlite.consistency_journal import SQLiteConsistencyJournal

journal = SQLiteConsistencyJournal(
    database,
    signer=signer_local_configurado,
    reducer_version="version-del-reducer",
    issuer_id="identificador-del-emisor",
    issuer_role="rol-del-emisor",
    key_reference="referencia-opaca-de-clave",
    trust_policy_version="version-de-politica",
)
\`\`\`

Los valores son marcadores, no credenciales listas para usar. La clave privada no se almacena en SQLite. La custodia de claves y el firmante deben proceder de una implementación local aprobada.

Para recuperación operativa se requieren también \`recovery_verifier\` y \`recovery_trust_policy\` compatibles y vinculados. No se debe utilizar una lectura estructural del journal como evidencia autenticada de recuperación.

## Identidad canónica local

La implementación \`SQLiteIdentityAuthority\` gestiona el par interno \`UserId\`–\`Identity(USER)\`, con identificadores UUID canónicos, revisión y control compare-and-swap para cambios de estado.

La migración v6 impone integridad recíproca entre ambas tablas. Las identidades revocadas son terminales y los registros canónicos se conservan como tombstones. Este alcance no crea cuentas externas ni demuestra la autenticación del propietario.

## Recovery Gate y autoridad protegida

\`LocalSQLiteRecoveryGateAdapter\` cubre el cierre, restauración y reapertura reconciliada del Recovery Gate dentro de una UoW compartida con el journal. Es una composición gate-only.

No equivale a una implementación completa de \`ProtectedMemoryRecoveryAuthorityPort\`. Siguen pendientes:

- Admisión durable de lecturas protegidas (\`admit_read\`).
- Autoridad común que coordine admisión, gate, invalidación y egress.
- Egress protegido con fencing e idempotencia verificable en el receptor.
- Integración atómica completa de Forget/invalidation con admisiones y egress.
- Bootstrap operativo completo con evidencia directa del propietario.
- Anti-rollback externo para un perfil ANCHORED.

El perfil LOCAL no demuestra anti-rollback independiente. No existe fallback automático de ANCHORED a LOCAL.

**No abras el Recovery Gate manualmente ni modifiques \`consistency_domains.recovery_gate_state\` mediante SQL.** Mantén el runtime protegido deshabilitado hasta completar bootstrap, autoridad, recuperación y validación.

## Backups y operación

- Detén el proceso escritor antes de copiar manualmente la base, o usa un procedimiento SQLite que incluya correctamente WAL.
- Copiar solo el archivo principal mientras hay escritores activos puede producir un backup incompleto.
- Restringe los permisos del directorio y del archivo a la cuenta de servicio.
- Mantén las claves fuera de SQLite.
- Una restauración de un backup antiguo no demuestra que el estado sea el más reciente.

## Validación

Ejecuta desde la raíz del proyecto:

\`\`\`bash
PYTHONPATH=src python -m unittest discover -s tests -v
\`\`\`

La línea C.4.1 registró previamente 787 pruebas locales reportadas como correctas. Esa evidencia antecede a las migraciones de identidad v5–v6. La línea integrada actual necesita una nueva ejecución completa; las pruebas añadidas para identidad, migración v6, concurrencia y composición no deben considerarse aprobadas hasta obtener su resultado en el entorno controlado.

No se debe inferir que GitHub Actions/CI pasó a partir de pruebas locales.