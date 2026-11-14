# ME-03K — Contrato K01 de idempotencia semántica

**Estado:** decisión aprobada; contrato de diseño para la implementación SQLite.  
**Rama objetivo:** `feature/me-03k-local-profile`.  
**Versión de proyección:** `request_projection_version = 1`.

## 1. Decisión

K01 utiliza **idempotencia semántica**. Una repetición con la misma `idempotency_key` dentro del mismo dominio y época, y con la misma solicitud semántica canónica, devuelve el commit original. No crea una segunda entrada de journal.

La identidad técnica regenerada por el caller no convierte una repetición de la misma solicitud de negocio en una operación distinta. En particular, el resultado no depende de que se regeneren `record_id`, `operation_id` o `occurred_at`.

Esta regla no permite cambiar el objeto, sujeto, autoridad, alcance, generación, recibo ni cualquier otro dato que cambie el efecto de negocio.

## 2. Ámbito de unicidad

La clave idempotente se interpreta dentro de:

- `consistency_domain_id`;
- `authority_epoch`;
- `idempotency_key`.

Una clave nunca se comparte entre dominios o épocas. Una transición sin `idempotency_key` solo puede resolverse por su `operation_id` dentro del dominio y época.

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
- `operation_id`: correlación técnica de la invocación; se conserva en el commit original;
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
3. Buscar primero por `idempotency_key`, si existe; también comprobar colisiones por `operation_id`.
4. Si ya existe la clave:
   - mismos bytes canónicos: devolver el commit original con `replayed=True`, sin insertar filas ni avanzar el head;
   - bytes diferentes: `CONFLICT`, sin mutación.
5. Si no existe la clave pero el `operation_id` ya está asociado a otra solicitud: `CONFLICT`, sin mutación.
6. Si no existe operación previa, exigir coincidencia exacta de dominio, época y posición esperada.
7. Crear envelope y compromiso ligados al head anterior; insertar journal y resolución; actualizar head mediante CAS; confirmar todo en la misma transacción.

Una repetición semántica válida puede llegar con otro `operation_id` o `record_id`. La resolución por clave idempotente devuelve siempre la identidad y posición originales; no crea alias ni reemplaza esos identificadores persistidos.

## 6. Resolución de resultado ambiguo

`resolve_operation` debe buscar por la clave idempotente y por el `operation_id` aportados, sin asumir que ambos identifican filas distintas.

- Si la clave encuentra una fila y la proyección esperada coincide byte por byte, devuelve `COMMITTED_EXACT` con el commit original y la transición originalmente persistida.
- Si la clave encuentra una fila con otra proyección, devuelve `CONFLICT`.
- Si el `operation_id` encuentra una fila asociada a otra solicitud o a otra clave, devuelve `CONFLICT`.
- Si ambos localizadores encuentran filas diferentes, devuelve `CONFLICT` y no intenta reconciliarlas automáticamente.
- `NOT_COMMITTED` solo es válido si la transacción de lectura demuestra ausencia por ambos localizadores y una posición actual coherente, dentro del mismo dominio/época.
- Corrupción, indisponibilidad o imposibilidad de demostrar ausencia producen `UNKNOWN`.

La igualdad semántica debe ser una comparación de proyecciones v1, no igualdad de dataclasses completos. El resultado `COMMITTED_EXACT` conserva el commit y la transición originales, aunque sus IDs técnicos y timestamp difieran de los suministrados en el reintento.

## 7. Sin clave idempotente

Para transiciones sin `idempotency_key`:

- `operation_id` es el único localizador de repetición;
- mismo `operation_id` y misma proyección semántica devuelve el commit original;
- mismo `operation_id` y proyección distinta produce `CONFLICT`;
- sin coincidencia previa se aplica CAS de posición normalmente.

No se debe inferir idempotencia a partir de igualdad de contenido sin clave ni identidad de operación.

## 8. Implicaciones para los contratos actuales

Antes de implementar el repositorio SQLite deben alinearse los contratos en memoria:

- `JournalOperationResolution` no puede exigir igualdad completa entre `committed_transition` y `expected_transition`; debe validar igualdad semántica v1.
- `COMMITTED_EXACT` debe permitir que la transición persistida conserve IDs/timestamp originales distintos de los regenerados por el caller, siempre que sus proyecciones semánticas coincidan.
- La consulta debe conservar suficiente información para devolver la transición original y el commit original.
- La migración siguiente debe reforzar la relación entre `journal_operations` y `journal_entries`, incluyendo `operation_id` en la clave foránea compuesta. La migración v1 publicada no se modifica.

## 9. Invariantes de seguridad

- No se utiliza únicamente `request_digest` para decidir igualdad.
- No se acepta una clave reutilizada con contenido semántico diferente.
- No se avanza el head en un replay.
- No se crea una nueva operación para resolver `UNKNOWN` o `CONFLICT`.
- No se considera `NOT_COMMITTED` una excepción SQLite ni una desconexión.
- La firma HMAC y la clave activa siguen siendo una responsabilidad separada; este contrato no crea ni custodia claves.
- El perfil local no obtiene protección anti-rollback externo por esta decisión.
