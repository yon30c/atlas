# I3-2B.7B.4D — servicio transaccional de lifecycle de asociaciones

**Estado:** implementación publicada; validación del propietario pendiente.  
**PR:** #16 — Draft, abierto y sin merge.  
**Dependencias:** 7B.4A contratos, 7B.4B V26 y 7B.4C adaptador SQLite validados.  
**Alcance:** servicio de aplicación y pruebas iniciales; sin endpoint HTTP, CLI, migración adicional ni activación de bootstrap.

## Servicio

Se añade `ProjectEnvironmentLifecycleService.transition(context, verified_identity, request)`.

Secuencia dentro de una única UoW:

1. Capturar una sola vez `Clock.now()` y exigir datetime UTC.
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

## Validación owner

Pendiente en Debian. Ejecutar:
```bash
cd ~/atlas-dev
git pull --ff-only

PYTHONPATH=tests:tests/unit python -m unittest \
  test_project_environment_lifecycle_service \
  test_sqlite_project_environment_lifecycle_ledger \
  test_sqlite_project_environment_lifecycle_migration -v

PYTHONPATH=tests:tests/unit python -m unittest discover \
  -s tests/unit -p 'test_*.py'

python -m compileall -q src tests
echo "COMPILE_EXIT_CODE=$?"
```

Checkpoint anterior: 1,487 tests. Se esperan seis pruebas nuevas, total **1,493**; `compileall` debe devolver 0. Si la prueba focalizada revela diferencias de nombre de módulo, no cambiar código hasta revisar el traceback exacto.

## Límites y riesgos pendientes para 7B.4E

- La UoW SQLite usa `BEGIN IMMEDIATE`; CAS sigue siendo la defensa explícita de revisión y la transacción serializa escritores SQLite locales.
- El Clock es inyectado y validado; no se usa hora del caller.
- La prueba del servicio usa un verifier doble. Se requieren pruebas adversariales con verifier real/mocks de fallo, grant expirado/revocado, mismatch de identity revision, rollback de commit diferido y concurrencia.
- No se añade cascade sobre Grants/delegaciones/Workspaces ni suspensión automática de Workspaces.
- No hay cambios de schema, host, systemd, Docker, privilegios ni DB productiva.
