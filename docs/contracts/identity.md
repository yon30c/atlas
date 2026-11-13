# Contrato de identidad

## 1. Propósito y alcance

Este contrato define el modelo de identidad del núcleo de Atlas. `Identity` es la representación de un actor para atribuir operaciones. La identidad no representa por sí sola autenticación, autorización, propiedad, delegación ni pertenencia a un proyecto.

El contrato describe el modelo presente en `src/atlas/core/identity.py` y sus validaciones cubiertas por `tests/unit/test_identity.py`. La autorización se evalúa en la frontera de autorización; la identidad y el contexto no conceden permisos.

## 2. Modelo

`Identity` es un valor inmutable con estos campos:

| Campo | Tipo | Regla |
|---|---|---|
| `identity_id` | `str` | Obligatorio; no puede ser vacío ni consistir únicamente en caracteres que `str.strip()` elimina. |
| `kind` | `IdentityKind` | Obligatorio; debe ser un miembro válido de la enumeración. |
| `status` | `IdentityStatus` | Obligatorio; debe ser un miembro válido de la enumeración. |

La instancia es inmutable (`frozen`) y usa slots. La validación del identificador comprueba que sea una cadena y que `value.strip()` no sea vacía, pero conserva el valor original: no normaliza ni elimina espacios iniciales o finales. Una cadena no vacía con espacios alrededor se acepta tal cual.

Los valores de tipo y estado deben ser instancias de sus enumeraciones respectivas. Cadenas como `"agent"` o `"active"` no se convierten automáticamente y son inválidas.

## 3. Tipos de identidad

`IdentityKind` admite exactamente estos valores:

| Miembro | Valor serializado |
|---|---|
| `USER` | `user` |
| `AGENT` | `agent` |
| `SERVICE` | `service` |
| `WATCHER` | `watcher` |
| `SYSTEM` | `system` |

El tipo clasifica al actor. La enumeración, por sí misma, no le otorga capacidades o permisos.

## 4. Ciclo de vida y estados de identidad

Los estados de una identidad determinan si esta puede participar en nuevas operaciones y cómo deben tratarse las operaciones que ya están en curso.

Los estados definidos son:

- `ACTIVE`: identidad habilitada para participar en operaciones, siempre que las autorizaciones correspondientes sean válidas.
- `SUSPENDED`: identidad suspendida temporalmente. No puede iniciar nuevas operaciones mientras permanezca en este estado.
- `REVOKED`: identidad revocada definitivamente. No puede iniciar nuevas operaciones ni continuar participando en operaciones que dependan de esa identidad.

### 4.1. Suspensión

La suspensión es una medida temporal.

Cuando una identidad pasa a `SUSPENDED`:

1. Se bloquea inmediatamente el inicio de nuevas operaciones.
2. Se identifican las tareas activas que dependan de esa identidad.
3. Se inicia la detención cooperativa de dichas tareas.
4. Si una interrupción inmediata pudiera comprometer la integridad de datos o recursos, se permite que la tarea alcance un punto seguro de consistencia.
5. Durante ese intervalo no se permiten nuevas operaciones ni la ampliación del alcance de las operaciones existentes.
6. Se preservan los resultados parciales y el estado de ejecución.
7. Las tareas independientes ejecutadas por otras identidades pueden continuar si sus propias autorizaciones siguen siendo válidas.

La identidad suspendida puede ser reactivada por su propietario mediante un procedimiento autorizado.

### 4.2. Revocación

La revocación es definitiva para la identidad afectada.

Cuando una identidad pasa a `REVOKED`:

1. Se bloquea el inicio de nuevas operaciones.
2. Se impide que las operaciones dependientes continúen utilizando la identidad revocada.
3. Se detienen de forma segura las operaciones activas, permitiendo alcanzar un punto seguro de consistencia cuando sea necesario para proteger la integridad.
4. Se preservan y registran los resultados parciales y el estado de ejecución.
5. La misma identidad no puede reactivarse como si la revocación no hubiera ocurrido.

Si en el futuro se necesita una identidad equivalente, deberá crearse una identidad independiente y concedérsele las autorizaciones correspondientes.

### 4.3. Relación entre identidad y autorización

El estado `ACTIVE` es una condición necesaria para que una identidad pueda participar en nuevas operaciones, pero no concede permisos por sí mismo.

Toda operación protegida debe seguir pasando por el mecanismo de autorización correspondiente (CAM). Una identidad activa no puede ejecutar una acción si no dispone de una autorización válida para el recurso y la operación solicitados.

### 4.4. Decisiones técnicas pendientes

Las políticas operativas de suspensión y revocación descritas anteriormente están aprobadas en el contrato principal de arquitectura, sección 16.2.

Quedan pendientes de definición los detalles técnicos de implementación, entre ellos:

- El mecanismo mediante el cual se solicitan y ejecutan las transiciones de estado.
- La persistencia del estado y del historial de cambios.
- El registro y la trazabilidad de las operaciones administrativas.
- Los procedimientos técnicos para ejecutar la suspensión, reactivación y revocación.
- La representación y gestión de las identidades revocadas para impedir su reutilización accidental.

Estas decisiones de implementación no modifican las políticas operativas ya aprobadas.

## 5. Uso con el contexto de operación

Cada operación utiliza un `OperationContext` explícito e inmutable. Su campo `actor` es una instancia válida de `Identity`; el contexto aporta atribución y correlación, pero no concede permisos. La ausencia de proyecto o entorno tampoco implica autorización.

Identidad, autenticación y autorización son conceptos separados. La forma de autenticar o probar una identidad, vincular `identity_id` con una cuenta externa, y administrar el ciclo de vida del registro queda fuera de lo especificado aquí y requiere decisiones técnicas explícitas.

## 6. Errores de validación

Una identidad inválida, un tipo que no sea `IdentityKind`, o un estado que no sea `IdentityStatus` produce `ContractError` al construir `Identity`. No se describe una conversión automática ni recuperación implícita.

## 7. Decisiones técnicas abiertas

Los documentos arquitectónicos aprobados no fijan los siguientes detalles. Deben decidirse antes de depender de ellos:

- Formato, longitud, sensibilidad a mayúsculas, espacio de nombres, unicidad y generación de `identity_id`.
- Si se permiten espacios iniciales o finales en identificadores y, de ser así, cómo se comparan. El código actual los conserva.
- Si existe normalización o una representación canónica de identificadores entre sistemas.
- Significado operacional detallado de cada `IdentityKind`, más allá de clasificar el actor.
- Semántica de cada estado fuera del efecto CAM documentado para estados distintos de `ACTIVE`.
- Transiciones permitidas, iniciadores autorizados, revisión, persistencia e historial de cambios de estado.
- Mecanismo de autenticación y vínculo entre una identidad del dominio y una credencial o cuenta.
- Si las identidades eliminadas pueden reutilizar sus identificadores y cómo se conserva la atribución histórica.

Hasta que se resuelvan, no deben suponerse formatos, políticas de autenticación, poderes asociados a tipos ni transiciones del ciclo de vida.
