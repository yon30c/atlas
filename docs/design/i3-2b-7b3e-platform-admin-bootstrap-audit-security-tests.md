# I3-2B.7B.3E — pruebas de auditoría y límites de seguridad del bootstrap

**Estado:** pruebas y documentación publicadas; validación del propietario pendiente.
**PR:** #16 — Draft, abierto y sin merge.
**Restricción:** solo bases SQLite temporales de tests. No ejecutar bootstrap real.

## Objetivo

Endurecer las garantías persistentes y de autorización del primer Platform Admin. Esta slice añade pruebas adversariales sobre los triggers V25 existentes y sobre `require_platform_admin_permission`; no introduce una vía nueva de provisión, revocación o recuperación.

## Cobertura añadida

### Auditoría y persistencia V25

En `tests/unit/test_sqlite_platform_admin_bootstrap.py`:

- un evento de bootstrap no admite UPDATE ni DELETE;
- los claims del grant no admiten modificaciones directas;
- un grant no admite DELETE, conservando el tombstone;
- la revocación válida incrementa revision exactamente una vez y registra instante y actor;
- un grant revocado no puede volver a ACTIVE;
- la revocación no permite iniciar un segundo bootstrap, aunque el grant inicial ya no esté activo.

Las pruebas ejecutan SQL directo contra la base temporal para comprobar que las garantías no dependen únicamente de la disciplina del adaptador de aplicación. Cada operación adversarial debe fallar con `sqlite3.IntegrityError` y conservar el estado persistido.

### Autorización de dominio

En `tests/unit/test_platform_admin_bootstrap_contracts.py`:

- se acepta una acción solo cuando USER, identity ID, revisión, permiso y ventana temporal coinciden;
- se rechaza identidad/sujeto distinto, revisión obsoleta, grant aún no vigente o expirado;
- se rechaza un grant revocado;
- se rechaza un permiso que el grant no contiene.

## Límites

- No se añadió recuperación de administradores revocados.
- No se añadió renovación automática ni extensión de TTL.
- UID y TTY siguen siendo procedencia técnica, no autenticación humana.
- No se añadió writer de bootstrap a runtime/UoW.
- No se modificó el schema V25 ni se ejecutó una migración.
- No se ejecutó bootstrap real ni se tocó una DB productiva.

## Validación requerida por el propietario

Desde `~/atlas-dev`, después de actualizar el branch:

```bash
git pull --ff-only

PYTHONPATH=tests:tests/unit python -m unittest \
  test_platform_admin_bootstrap_contracts \
  test_sqlite_platform_admin_bootstrap -v

PYTHONPATH=tests:tests/unit python -m unittest discover \
  -s tests/unit -p 'test_*.py'

python -m compileall -q src tests
echo "COMPILE_EXIT_CODE=$?"
```

La suite debe incluir seis pruebas nuevas respecto al checkpoint anterior de 1,460 tests. El total esperado es al menos 1,466, sujeto a otros cambios del branch. No se debe ejecutar `atlas-platform-admin-bootstrap` para crear un administrador.
