# I3-2B.7B.4C — adaptador SQLite del ledger lifecycle

**Estado:** implementación publicada; validación del propietario pendiente.  
**PR:** #16 — Draft, abierto y sin merge.  
**Dependencia:** V26 validada en Debian en 7B.4B.  
**Alcance:** adaptador de persistencia y pruebas; no servicio, autorización, runtime composition ni cambios de schema.

## Adaptador

Se añade `SQLiteProjectEnvironmentLifecycleLedger`, que implementa estructuralmente `ProjectEnvironmentLifecycleLedgerPort`:

- `append_event(event)` persiste todos los campos del contrato, incluidos los estados/revisiones, actor USER/Identity, referencia de contexto verificado, request/correlation IDs, motivo y timestamp UTC.
- `list_events(project_id, environment_id)` devuelve una tupla inmutable ordenada por `new_revision ASC`.
- La reconstrucción desde SQLite vuelve a pasar por `ProjectEnvironmentLifecycleEvent`; registros corruptos o inválidos se rechazan como `ContractError`.
- Los IDs de asociación se validan como texto no vacío y normalizado.
- Se admiten conexiones independientes de lectura y un `SQLiteUnitOfWork` explícito compartido.

## Atomicidad y frontera de runtime

El adapter puede compartir la UoW que coordina el evento y la actualización de asociación. V26 impide confirmar un evento sin su transición correspondiente: el FK diferido requiere el commit marker que genera el trigger de la actualización válida.

Un `append_event` aislado no puede confirmarse. El adapter convierte conflictos de integridad inmediatos o de commit en `ContractError` cuando opera con su propia UoW. En una UoW externa, los errores diferidos emergen al commit de esa UoW y provocan rollback conjunto.

El writer **no se agrega** a `SQLiteLocalAuthorityUnitOfWork` ni a la composición runtime. Se exporta la clase de infraestructura para que el futuro servicio lifecycle la construya explícitamente con la UoW de la operación. No hay endpoint, CLI ni servicio en esta fase.

## Pruebas

`tests/unit/test_sqlite_project_environment_lifecycle_ledger.py` cubre:

1. append y lectura dentro de la misma UoW que la transición;
2. orden de historial por revisión;
3. rechazo de commit de evento sin transición;
4. rollback conjunto de evento y asociación;
5. validación de tipo de evento y scope;
6. historial vacío;
7. ausencia del writer en la UoW runtime.

La suite SQL V26 de 7B.4B sigue siendo la autoridad para inmutabilidad, constraints, actor canónico y protección contra eventos huérfanos.

## Validación owner

Pendiente de ejecución en Debian. No declarar 7B.4C validada hasta recibir:
```bash
cd ~/atlas-dev
git pull --ff-only

PYTHONPATH=tests:tests/unit python -m unittest \
  test_sqlite_project_environment_lifecycle_ledger -v

PYTHONPATH=tests:tests/unit python -m unittest discover \
  -s tests/unit -p 'test_*.py'

python -m compileall -q src tests
echo "COMPILE_EXIT_CODE=$?"
```

Checkpoint previo: 1,480 tests. Se esperan 7 pruebas nuevas, total esperado 1,487; `compileall` debe devolver 0. No aplicar migraciones manualmente ni ejecutar bootstrap real.
