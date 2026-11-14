# ME-03K — Decisión: identidad de operación e identidad de append

**Estado:** aprobada por el propietario.  
**Aplicación:** perfil local SQLite, K01.

## Problema

El esquema anterior imponía unicidad a `operation_id` en `journal_entries` y `journal_operations`. Eso confundía la operación de negocio con cada transición durable. Una misma admisión necesita registrar varios eventos, por lo que una identidad de operación repetida no debe impedir nuevos commits.

## Decisión aprobada

Se separan tres identidades:

1. `operation_id`: correlación de negocio. Puede repetirse en múltiples entradas y no es un localizador de append.
2. `append_id`: identidad única y estable de un intento concreto de append dentro de dominio/época. Se entrega como argumento del repositorio, no como campo de `ConsistencyTransition`.
3. `idempotency_key`: identidad semántica de la solicitud. Permite reproducir el commit original aun cuando el reintento use otro `append_id` o IDs técnicos regenerados.

### Resolución

- Con clave idempotente: consultar por clave y comprobar también el `append_id` de la invocación.
- Sin clave idempotente: `append_id` es el único localizador.
- `operation_id` no se utiliza para inferir repetición ni colisión.
- Si los localizadores aportados apuntan a commits diferentes, resultado `CONFLICT`.
- El replay conserva siempre el commit, `record_id`, `operation_id` y transición originales.

## Persistencia

La migración v3:

- elimina la unicidad de `operation_id` en `journal_entries`;
- convierte `append_id` en clave primaria de `journal_operations` junto con dominio y época;
- mantiene `operation_id` como correlación no única en ambas tablas;
- mantiene la relación foránea exacta entre resolución y entrada;
- mantiene la unicidad de `idempotency_key` por dominio/época;
- asigna identificadores heredados deterministas `legacy-v2:` a las filas de resolución existentes;
- conserva v1 y v2 sin modificaciones.

## Consecuencias para la API

El contrato del repositorio cambia de una resolución por operación a una resolución por append:

- `append_transition(expected_position, append_id, transition)`;
- `resolve_append(domain_id, authority_epoch, append_id, idempotency_key, expected_transition, expected_position)`.

La identidad `append_id` no se añade a la transición ni a la proyección semántica v1. El caller debe conservarla durante el reintento de una misma escritura incierta.

## Límites

Esta decisión no convierte `operation_id` en una identidad global ni modifica el significado de los eventos de dominio. Tampoco implementa por sí sola la firma, la verificación histórica, el anti-rollback o la recuperación autenticada.
