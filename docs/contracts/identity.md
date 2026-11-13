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

## 4. Estados de identidad

`IdentityStatus` admite exactamente estos valores:

| Miembro | Valor serializado |
|---|---|
| `ACTIVE` | `active` |
| `SUSPENDED` | `suspended` |
| `REVOKED` | `revoked` |

El evaluador CAM actual deniega solicitudes cuyo actor no está en estado `ACTIVE`. Esto describe el efecto comprobado en esa frontera; el estado no sustituye la evaluación de Grants ni concede acceso cuando es `ACTIVE`.

Este contrato no define cambios de estado ni autoriza transiciones entre ellos. La creación, suspensión, reactivación o revocación de identidades y quién puede iniciarlas son **decisiones técnicas abiertas**. Ninguna transición debe inferirse de la enumeración.

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
