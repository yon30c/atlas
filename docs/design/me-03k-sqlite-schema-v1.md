# ME-03K — Alcance de la migración SQLite v1

**Estado:** implementada en la rama `feature/me-03k-local-profile`; pendiente de validación por el propietario en Debian.

La migración `CORE_SCHEMA_V1` crea exclusivamente la base estructural para comenzar el adaptador durable:

- `consistency_domains`: época, posición actual, compromiso, perfil local, política de confianza y estado del Recovery Gate.
- `journal_entries`: posición única, identidad de registro/operación, transición canónica opaca y campos del envelope autenticado.
- `journal_operations`: resolución durable de operación, solicitud canónica/digest y clave idempotente única por dominio/época.
- `checkpoints`: posición y referencias opacas de estado/integridad con sus campos de envelope.
- `checkpoint_projections`: proyección canónica de metadatos de control y referencias de verificación vinculada al checkpoint.

## Límites deliberados de v1

1. La migración no implementa todavía repositorios, puertos de escritura/lectura ni el append K01.
2. No crea tablas para recibos, tombstones, referencias externas ni operaciones pendientes. Esos inventarios requieren fijar primero el contrato de persistencia de cada evidencia y su relación exacta con las proyecciones. No se declarará K04/K05 conforme hasta que exista esa implementación y su verificación de conjunto completo.
3. No almacena claves HMAC ni política de confianza independiente. Esos elementos permanecen fuera de la base restaurable.
4. No guarda contenido de memoria, snippets, embeddings ni hashes de contenido.
5. No activa el Recovery Gate ni habilita lecturas protegidas, Forget físico o egress.

La restricción `profile = 'local'` hace explícito el perfil actualmente aprobado. Una futura etapa anchored requerirá una migración/diseño explícito; no se permite degradación silenciosa.

## Restricciones de integridad incluidas

- Posición de journal única por dominio/época.
- Identidad de registro única dentro del dominio.
- Una operación durable se vincula a un único commit exacto.
- Una clave idempotente no puede vincularse a dos operaciones dentro del mismo dominio/época.
- Proyección de checkpoint sin checkpoint padre es rechazada por FK.
- Las referencias usan `ON DELETE RESTRICT`; no se permite borrar evidencia referenciada mediante cascada.

La migración es inmutable una vez aplicada. Cualquier ajuste posterior debe introducir una nueva versión, nunca modificar `CORE_SCHEMA_V1`.
