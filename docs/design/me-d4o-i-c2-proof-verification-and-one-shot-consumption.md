# ME-D4O-I-C.2 — Verificación y consumo de evidencia CAM

Estado: implementación contractual en rama de trabajo; pruebas diferidas por decisión del usuario.

## Objetivo

Garantizar que una revocación no avance solo porque el consumidor recibió una instancia de
`VerifiedGrantRevocationAuthorization`. La evidencia debe corresponder exactamente a la
solicitud, ser auténtica según una autoridad CAM confiable, estar vigente y consumirse de
forma one-shot con recuperación idempotente.

## Responsabilidades

### GrantRevocationProofAuthorizationService

El servicio de aplicación:

1. Exige tipos y contexto completos.
2. Compara exactamente `request_id`, actor, propietario, Grant y revisión esperada.
3. Comprueba que la emisión no precede a la solicitud y que `issued_at <= now < expires_at`.
4. Invoca el verificador confiable antes de consumir.
5. Si el verificador deniega o no está disponible, no inicia el consumo.
6. Consume la prueba con el `operation_id` y `idempotency_key` estables que entrega el coordinador.
7. Solo devuelve AUTHORIZED ante consumo nuevo confirmado o repetición exacta de la misma operación y clave.
8. Un conflicto de reutilización deniega. Una excepción, respuesta inválida o resultado indeterminado se trata como incertidumbre, nunca como prueba libre.

### GrantRevocationProofVerifierPort

La implementación futura debe validar contra la autoridad CAM confiable que:

- `proof_id` identifica una decisión auténtica.
- El emisor está permitido.
- La decisión fue para la acción exacta `grant.revoke`.
- El actor era un USER activo, actuó directamente y corresponde al propietario canónico.
- Los claims de actor, propietario, Grant y revisión coinciden con la solicitud.
- La evidencia estaba vigente al momento de verificación.

La verificación de autenticidad no consume la prueba. No debe rechazar una prueba únicamente porque ya fue consumida: los reintentos exactos se resuelven por el puerto de consumo.

### GrantRevocationProofConsumptionPort

La implementación futura debe serializar por `proof_id` y persistir atómicamente:

- `proof_id`
- `operation_id`
- `idempotency_key`
- instante de consumo y resultado durable

La misma pareja `operation_id` + `idempotency_key` puede recuperar el mismo resultado sin un segundo efecto. Cualquier operación o clave distinta para el mismo `proof_id` produce conflicto. Si se pierde la respuesta o no se puede determinar el commit, el resultado es indeterminado y no se puede tratar la prueba como disponible.

## Estados de resultado

- `AUTHORIZED`: verificación válida y consumo confirmado, nuevo o replay exacto.
- `DENIED`: claims no coincidentes, evidencia fuera de vigencia o verificación negativa.
- `VERIFIER_UNAVAILABLE`: el verificador falla; no se llama al consumidor.
- `PROOF_REPLAY_CONFLICT`: el proof fue consumido para otra operación/clave o la respuesta no coincide.
- `CONSUMPTION_UNCERTAIN`: el consumo pudo confirmarse, pero no hay resultado confiable; se conserva incertidumbre y se requiere recuperación con los mismos identificadores.

## Límites de esta etapa

Esta entrega contiene modelos de resultado, puertos y orquestación por puertos. No incluye:

- proveedor criptográfico ni consulta real a CAM;
- implementación durable de consumo;
- SQLite, CAS o tablas de idempotencia;
- coordinador de cambios de autoridad;
- cambios a `GrantManagementService.revoke`;
- pruebas ejecutadas (se posponen para la validación conjunta solicitada).

El `operation_id` no lo genera este servicio: debe entregarlo el coordinador de I-C.3. Esta separación evita que la verificación de evidencia se convierta en autoridad para crear o ejecutar por sí sola una revocación.
