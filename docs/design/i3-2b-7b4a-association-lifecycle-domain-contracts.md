# I3-2B.7B.4A — contratos de dominio para lifecycle de asociaciones

**Estado:** contratos, puerto y pruebas publicados; validación del propietario pendiente.
**PR:** #16 — Draft, abierto y sin merge.
**Alcance:** solo contratos de dominio/puertos y pruebas unitarias; no hay servicio, migración ni escritura runtime.

## Contrato de intención

`ProjectEnvironmentLifecycleRequest` representa exclusivamente intención del caller:

- ProjectId y EnvironmentId exactos;
- estado objetivo `ACTIVE` o `SUSPENDED`;
- `expected_revision` positivo;
- motivo obligatorio normalizado.

El motivo debe tener entre 1 y 500 caracteres, sin caracteres de control, sin espacios iniciales/finales y con secuencias internas de whitespace colapsadas a un espacio. La solicitud no lleva roles, permisos, actor declarado ni claims de autorización.

## Contrato de evento

`ProjectEnvironmentLifecycleEvent` es un hecho inmutable y autoconsistente:

- UUIDv4 del evento;
- asociación exacta;
- estado anterior y nuevo, necesariamente distintos y dentro de ACTIVE/SUSPENDED;
- revisión anterior y nueva, con incremento exactamente +1;
- UserId e Identity(USER) del actor canónico;
- `verified_identity_context_id` como referencia de la evidencia verificada;
- request_id y correlation_id de OperationContext;
- motivo normalizado y timestamp UTC confiable.

La construcción valida forma y consistencia local. No autentica al actor, no comprueba permisos ni sustituye la revalidación dentro de la UoW.

## Puerto de ledger

`ProjectEnvironmentLifecycleLedgerPort` define append y lectura ordenada por asociación. Su implementación futura debe compartir la transacción del cambio de estado y no exponerse como writer fuera del servicio de lifecycle.

## Secuencia posterior

1. 7B.4B: migración V26 para ledger inmutable, unicidad por asociación/revisión y triggers que obliguen a que cada actualización de estado tenga un evento compatible.
2. 7B.4C: adaptador SQLite de ledger y pruebas SQL adversariales.
3. 7B.4D: servicio de aplicación con verificación USER transaccional, Platform Admin exacto, Clock confiable, CAS y persistencia atómica.
4. 7B.4E: pruebas de seguridad, concurrencia, rollback y regresión completa.

La migración debe preservar asociaciones preexistentes sin inventar eventos retrospectivos. El trigger solo exigirá eventos para transiciones posteriores a V26; la semántica de INSERT inicial permanece separada.

## Límites

- No hay bootstrap real ni administrador provisionado.
- No hay runtime composition, HTTP endpoint ni CLI administrativa adicional.
- No se añaden cascadas a Grants, delegaciones o Workspaces.
- No se suspenden Workspaces automáticamente; los consumidores siguen comprobando la asociación ACTIVE en su propia UoW.
- No se cambia V18 ni se reescriben migraciones históricas.
- No se modifica host, systemd, Docker, privilegios ni DB productiva.

## Validación pendiente en Debian

```bash
cd ~/atlas-dev
git pull --ff-only

PYTHONPATH=tests:tests/unit python -m unittest \
  test_project_environment_lifecycle_contracts -v

PYTHONPATH=tests:tests/unit python -m unittest discover \
  -s tests/unit -p 'test_*.py'

python -m compileall -q src tests
echo "COMPILE_EXIT_CODE=$?"
```

Se esperan cinco pruebas nuevas sobre el checkpoint anterior de 1,466 tests: total esperado **1,471** o superior. No ejecutar bootstrap real ni aplicar migraciones manualmente.
