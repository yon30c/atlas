# I3-2B.7B.4D — servicio transaccional de lifecycle de asociaciones

**Estado:** implementación publicada y validada por el propietario en Debian.  
**PR:** #16 — Draft, abierto y sin merge.  
**Dependencias:** 7B.4A contratos, 7B.4B V26 y 7B.4C adaptador SQLite validados.  
**Alcance:** servicio de aplicación y pruebas iniciales; sin endpoint HTTP, CLI, migración adicional ni activación de bootstrap.

## Servicio

Se añade `ProjectEnvironmentLifecycleService.transition(context, verified_identity, request)`.

Secuencia dentro de una única UoW:

1. Adquirir la UoW (`BEGIN IMMEDIATE`) y, ya dentro de la transacción, capturar una sola vez `Clock.now()` y exigir datetime UTC. Así una espera por otro escritor no deja una hora de autorización obsoleta.
2. Revalidar `VerifiedIdentityContext` mediante `require_verified_owner_context_in_unit_of_work`. La evidencia debe resolver a la pareja canónica USER activa; actor y UserId contextual deben coincidir y no se admite delegación.
3. Leer los grants Platform Admin del usuario canónico. Exigir exactamente un grant ACTIVE y aplicar `require_platform_admin_permission` con el permiso exacto según el objetivo: `association.suspend` o `association.reactivate`. El helper comprueba sujeto, identity_id, revisión, estado y ventana temporal.
4. Leer la asociación exacta, exigir que exista y que su revisión coincida con `expected_revision`; rechazar no-op.
5. Construir el evento con actor canónico, `verified_identity_context_id`, request/correlation IDs y timestamp del Clock.
6. Añadir el evento al ledger y hacer CAS de la asociación con `lifecycle_event_id`.
7. Confirmar la UoW. V26 impone que evento y transición se confirmen juntos.

Cualquier fallo antes del commit deja la transacción sin cambios. El servicio no usa `OperationContext.user_id` como evidencia de autenticación.

## Frontera de persistencia

El servicio recibe `ledger_factory(unit)`. La composición confiable enlaza el adapter SQLite a la transacción activa. Así el writer no se expone como capacidad general en `SQLiteLocalAuthorityUnitOfWork`; el servicio tampoco conoce detalles de conexión SQLite.

No se integra el servicio a runtime composition en esta fase y no se crea endpoint ni comando invocable por usuarios. El bootstrap inicial sigue siendo offline-only y no se ejecutó.

## Pruebas añadidas

`tests/unit/test_project_environment_lifecycle_service.py` cubre:
- suspensión con evento y asociación atómicos;
- reactivación con permiso específico;
- ausencia de autoridad administrativa;
- revisión obsoleta sin evento;
- evidencia USER expirada/rechazada;
- fallo del ledger con rollback de la transición.

El test verifier es un doble controlado de la interfaz de verificación transaccional; no pretende probar criptografía, issuer ni attestation. La implementación de verificación real permanece responsabilidad del Identity Authority existente.

## Validación owner — confirmada en Debian

El propietario ejecutó las pruebas en `~/atlas-dev` sobre el HEAD actualizado y confirmó:

- Suite completa: **1,493 tests en 29.527 s — OK**.
- `python -m compileall -q src tests`: **COMPILE_EXIT_CODE=0**.

La validación confirma el servicio, las pruebas focalizadas incorporadas al conjunto completo, el ledger SQLite y las protecciones de migración V26. No implica que se haya ejecutado un bootstrap real ni una migración sobre producción.

## Límites y riesgos pendientes para 7B.4E

- La UoW SQLite usa `BEGIN IMMEDIATE`; CAS sigue siendo la defensa explícita de revisión y la transacción serializa escritores SQLite locales.
- El Clock es inyectado y validado; no se usa hora del caller.
- La prueba del servicio usa un verifier doble. Se requieren pruebas adversariales con verifier real/mocks de fallo, grant expirado/revocado, mismatch de identity revision, rollback de commit diferido y concurrencia.
- No se añade cascade sobre Grants/delegaciones/Workspaces ni suspensión automática de Workspaces.
- No hay cambios de schema, host, systemd, Docker, privilegios ni DB productiva.

## Revisión de integración posterior

La revisión 7B.4A–7B.4E detectó que el `Clock` se capturaba antes de adquirir la UoW. Se corrigió el orden: ahora se captura después de entrar en la UoW, una vez adquirido el bloqueo transaccional. Se añadió una prueba que adelanta el reloj al entrar en la UoW y exige denegación por grant expirado sin escrituras. Validación pendiente del propietario.
