# ME-03K — Contrato K01 de idempotencia semántica

**Estado:** decisión aprobada; contrato actualizado para identidad de append separada.  
**Rama objetivo:** `feature/me-03k-local-profile`.  
**Versión de proyección:** `request_projection_version = 1`.

## 1. Decisión

K01 utiliza **idempotencia semántica**. Una repetición con la misma `idempotency_key` dentro del mismo dominio y época, y con la misma solicitud semántica canónica, devuelve el commit original. No crea una segunda entrada de journal.

Se distinguen tres identidades que no deben confundirse:

- `operation_id`: correlaciona una operación de negocio. Puede aparecer en múltiples transiciones del journal.
- `append_id`: identifica un intento concreto de append. Es estable durante los reintentos de ese append y único dentro del dominio/época.
- `idempotency_key`: reconoce una misma solicitud semántica aunque un reintento llegue con otro `append_id`, `record_id` u otros metadatos técnicos regenerados.

Una operación de negocio puede producir múltiples transiciones, por ejemplo `READ_ADMITTED`, `READ_ACTIVATED` y `EGRESS_COMMITTED`, todas con el mismo `operation_id`, cada una con su propio `append_id`.

## 2. Ámbito de unicidad y localizadores

La clave idempotente se interpreta dentro de:

- `consistency_domain_id`;
- `authority_epoch`;
- `idempotency_key`.

`append_id` también se limita al dominio y época. No se exige unicidad global.

La API del repositorio recibe `append_id` como argumento separado de `ConsistencyTransition`. No se agrega al DTO de dominio ni a la proyección semántica.

- Con `idempotency_key`: buscar por la clave y comprobar también el `append_id` suministrado.
- Sin `idempotency_key`: `append_id` es el único localizador de repetición.
- `operation_id` nunca es un localizador único de append y no se utiliza para decidir si una escritura ya existe.

El mismo `append_id` no puede identificar dos filas dentro del mismo dominio/época. Un `append_id` diferente con la misma clave y semántica devuelve el commit original.

## 3. Proyección canónica v1

La proyección es una estructura explícita y versionada, no la serialización incidental del DTO ni los bytes de transporte.

Forma lógica:

```json
{
  "request_projection_version": 1,
  "consistency_domain_id": "...",
  "authority_epoch": 1,
  "record_kind": "...",
  "schema_version": 1,
  "semantic_fields": {}
}
```

`semantic_fields` contiene todos los campos de negocio permitidos para el `record_kind`, según el contrato de `ConsistencyTransition`, incluidos sus valores nulos y colecciones vacías cuando formen parte de la forma permitida. La lista se define explícitamente por tipo de transición y por versión; no se debe derivar automáticamente de todos los campos futuros del dataclass.

### 3.1 Campos excluidos de la proyección semántica

Estos campos se conservan en el registro original cuando corresponda, pero no cambian la identidad semántica del reintento:

- `record_id`: identidad técnica de la fila del journal;
- `operation_id`: correlación de la operación de negocio, no identidad del append;
- `append_id`: identidad técnica del intento de append, suministrada fuera del DTO;
- `occurred_at`: instante declarado por el caller, susceptible de regenerarse;
- `request_id`: identificador de transporte/solicitud;
- `correlation_id`: identificador de trazabilidad;
- `idempotency_key`: clave de búsqueda/unicidad, almacenada y comparada separadamente de los bytes de la proyección.

No se excluyen identificadores de entidades o recursos que cambien el efecto de negocio. Por ejemplo: `memory_id`, `version_id`, `snapshot_id`, `admission_id`, `endpoint_id`, `emission_id`, `receipt_id`, `authority_id`, `owner_id`, `subject_user_id`, `actor_identity_id`, `checkpoint_reference`, `proof_reference` y los IDs de rutas/admisiones afectadas permanecen semánticos cuando el tipo de transición los admite.

También permanecen semánticos las revisiones de autorización, el alcance, las generaciones, secuencias, estados terminales, versiones de esquema y el tipo de transición.

## 4. Canonicalización y digest

1. Construir la proyección v1 validada para el tipo exacto de transición.
2. Canonicalizarla usando el canonicalizador JSON versionado existente (UTF-8, claves ordenadas, separadores compactos, enums normalizados, UTC normalizado, sets ordenados y sin floats).
3. Persistir los bytes canónicos exactos en `journal_operations.request_canonical`.
4. Persistir SHA-256 de esos bytes en `request_digest` como índice/diagnóstico; la decisión de igualdad compara los bytes canónicos, no solo el digest.
5. La versión de proyección debe estar incluida en los bytes canónicos. Un cambio futuro de reglas requiere una nueva versión explícita y pruebas de compatibilidad.

El dominio y la época están incluidos en la proyección para evitar que el mismo material semántico se interprete fuera de su ámbito de autoridad.

## 5. Resolución de append

Bajo una única transacción `BEGIN IMMEDIATE`:

1. Validar dominio, época, estado de continuidad y posición esperada.
2. Construir la proyección semántica y sus bytes canónicos.
3. Buscar por `idempotency_key`, si existe, y por `append_id`.
4. Si ambos localizadores encuentran filas diferentes, devolver `CONFLICT`.
5. Si la clave ya existe:
   - mismos bytes canónicos y mismo ámbito: devolver el commit original con `replayed=True`, sin insertar filas ni avanzar el head;
   - bytes diferentes: `CONFLICT`, sin mutación.
6. Si no existe clave, pero el `append_id` ya existe:
   - mismos bytes canónicos y misma clave nula: devolver el commit original;
   - proyección o clave diferente: `CONFLICT`.
7. Si no existe append previo, exigir coincidencia exacta de dominio, época y posición esperada.
8. Crear envelope y compromiso ligados al head anterior; insertar journal y resolución; actualizar head mediante CAS; confirmar todo en la misma transacción.

Una repetición semántica válida puede llegar con otro `append_id`, `record_id` u `operation_id`. La resolución por clave idempotente devuelve siempre la identidad y posición originales; no crea alias ni reemplaza esos identificadores persistidos.

## 6. Resolución de resultado ambiguo

La operación se denomina `resolve_append` y recibe `append_id`, `idempotency_key`, transición esperada y posición esperada. No utiliza `operation_id` como localizador.

- Si la clave encuentra una fila y la proyección esperada coincide byte por byte, devuelve `COMMITTED_EXACT` con el commit original y la transición originalmente persistida.
- Si la clave encuentra una fila con otra proyección, devuelve `CONFLICT`.
- Si `append_id` encuentra una fila asociada a otra proyección o clave, devuelve `CONFLICT`.
- Si ambos localizadores encuentran filas diferentes, devuelve `CONFLICT` y no intenta reconciliarlas automáticamente.
- `NOT_COMMITTED` solo es válido si la transacción de lectura demuestra ausencia por ambos localizadores y una posición actual coherente, dentro del mismo dominio/época.
- Corrupción, indisponibilidad o imposibilidad de demostrar ausencia producen `UNKNOWN`.

La igualdad semántica debe ser una comparación de proyecciones v1, no igualdad de dataclasses completos. El resultado `COMMITTED_EXACT` conserva el commit y la transición originales, aunque sus IDs técnicos y timestamp difieran de los suministrados en el reintento.

## 7. Transiciones sin clave idempotente

Para transiciones sin `idempotency_key`:

- `append_id` es el único localizador de repetición;
- mismo `append_id` y misma proyección semántica devuelve el commit original;
- mismo `append_id` y proyección distinta produce `CONFLICT`;
- sin coincidencia previa se aplica CAS de posición normalmente.

No se infiere idempotencia a partir de igualdad de contenido ni de `operation_id`.

## 8. Implicaciones de persistencia

- `journal_entries.operation_id` deja de ser único dentro del dominio/época.
- `journal_operations` utiliza `append_id` como clave primaria compuesta por dominio/época.
- `journal_operations.operation_id` conserva la correlación con la operación de negocio, sin restricción de unicidad.
- La relación exacta entre resolución y commit incluye dominio, época, secuencia, `record_id` y `operation_id`.
- La unicidad de `idempotency_key` se mantiene por dominio/época cuando no es NULL.
- La migración v3 reconstruye las tablas afectadas, preserva los registros existentes y asigna a las resoluciones heredadas un `append_id` determinista con prefijo `legacy-v2:`.
- Las migraciones v1 y v2 publicadas son inmutables.

## 9. Invariantes de seguridad

- No se utiliza únicamente `request_digest` para decidir igualdad.
- No se acepta una clave reutilizada con contenido semántico diferente.
- No se avanza el head en un replay.
- No se crea una nueva operación para resolver `UNKNOWN` o `CONFLICT`.
- No se considera `NOT_COMMITTED` una excepción SQLite ni una desconexión.
- La firma HMAC y la clave activa siguen siendo una responsabilidad separada; este contrato no crea ni custodia claves.
- El perfil local no obtiene protección anti-rollback externo por esta decisión.
