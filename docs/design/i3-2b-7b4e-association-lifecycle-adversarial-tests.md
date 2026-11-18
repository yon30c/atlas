# I3-2B.7B.4E — endurecimiento adversarial del servicio lifecycle

**Estado:** pruebas añadidas; validación del propietario pendiente.  
**PR:** #16 — Draft, abierto y sin merge.  
**Base:** 7B.4D validada por el propietario: 1,493 tests OK y compileall exit 0.

## Objetivo

Endurecer el servicio transaccional de suspensión/reactivación de asociaciones Project/Environment sin ampliar su superficie operativa. Este corte añade pruebas adversariales; no cambia el servicio, el esquema, runtime composition ni el procedimiento offline de bootstrap.

## Cobertura añadida

En `tests/unit/test_project_environment_lifecycle_service.py`:

1. **Platform Admin expirado:** adelanta el Clock confiable más allá de la expiración del grant, mantiene evidencia USER de prueba válida para ese instante y exige DENY sin evento ni cambio de asociación.
2. **Identity revision mismatch:** altera la revisión de la evidencia respecto de la identidad USER canónica y exige DENY sin escritura.
3. **Fallo en commit:** sustituye la señal de commit de la UoW por un fallo controlado después de escribir evento y asociación; comprueba rollback de asociación, evento y marcador V26.
4. **Concurrencia same-revision:** dos llamadas compiten con el mismo expected_revision; exactamente una puede confirmar, la otra debe recibir ConcurrencyError, con un solo evento y revisión final 2.

La cobertura existente ya incluye autoridad revocada/ausente, permiso requerido, identidad expirada, revisión obsoleta y fallo del ledger antes del update. Los contratos Platform Admin ya prueban expiración temporal y revocación en el dominio.

## Límites de la prueba

- El verifier del servicio sigue siendo un doble controlado; no se afirma validar criptografía, issuer o attestation real.
- La prueba de fallo de commit inyecta una excepción antes de la confirmación física SQLite; las constraints diferidas V26 siguen cubiertas por sus pruebas de migración.
- La concurrencia se prueba contra SQLite local y el CAS/BEGIN IMMEDIATE existentes; no demuestra coordinación distribuida.
- No se cambia producción ni se ejecuta bootstrap real.

## Validación Debian solicitada

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

Checkpoint anterior: **1,493 tests**. Se añaden cuatro pruebas; se espera **1,497 tests OK** y `COMPILE_EXIT_CODE=0`. No marcar validado hasta recibir el resultado real del propietario.

## Fuera de alcance

Sin cambios en runtime composition, HTTP, CLI, migraciones, DB productiva, host, systemd, Docker, usuarios o privilegios. PR #16 permanece Draft, abierto y sin merge.

## Corrección posterior al primer ensayo

El primer ensayo del propietario detectó un error en el doble `CommitFailingUnit`: el wrapper conserva un `SQLiteLocalAuthorityUnitOfWork` en `unit._unit`, mientras que el ledger exige el `SQLiteUnitOfWork` interno. Se corrigió únicamente el argumento del `ledger_factory` en la prueba para pasar `unit._unit._unit`. No se relajó el contrato del adaptador ni se modificó código productivo. Repetir primero la suite focalizada y luego la suite completa.

## Reejecución focalizada — confirmada por el propietario

Tras la corrección del test double, el propietario confirmó: **26 tests en 1.664 s — OK**. La suite completa y `compileall` aún están pendientes; no marcar la fase como validada hasta recibir ambos resultados.

## Validación completa — confirmada por el propietario

El propietario confirmó la ejecución de la suite completa: **1,497 tests en 30.888 s — OK**. También confirmó `python -m compileall -q src tests` con **`COMPILE_EXIT_CODE=0`**. Junto con las 26 pruebas focalizadas aprobadas, 7B.4E queda validada.

## Prueba adicional de integración — validación pendiente

La revisión integral detectó un posible uso de hora obsoleta si `BEGIN IMMEDIATE` espera por otro escritor. Se movió la captura de `Clock.now()` al interior de la UoW y se añadió `test_clock_is_captured_after_uow_acquisition`, que simula el avance temporal durante la adquisición de la transacción y exige que un grant expirado sea rechazado sin escrituras. Esta prueba nueva y la suite completa deben ejecutarse en Debian antes de cerrar la revisión de integración.
