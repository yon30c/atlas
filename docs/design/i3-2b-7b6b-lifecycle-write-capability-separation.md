# I3-2B.7B.6B — separación de capacidades de asociación lifecycle

**Estado:** implementación publicada; validación Debian pendiente.
**Base:** auditoría 7B.6A.
**PR:** #16 — debe permanecer Draft, abierto y sin merge.
**Alcance:** separar puertos y adaptadores para que la UoW general no entregue la capacidad de transición lifecycle. No se habilita runtime.

## 1. Cambios realizados

### 1.1 Workspace registry limitado a Workspace

`SQLiteWorkspaceRegistryRepository` ya no implementa `get_association`, `create_association` ni `update_association`. Conserva únicamente operaciones de Workspace: lectura, creación, actualización CAS de metadatos y listado por owner.

`WorkspaceRegistryPort` refleja ahora ese límite y solo declara operaciones de Workspace.

### 1.2 Repositorio separado para asociaciones

Nuevo `SQLiteProjectEnvironmentAssociationRepository`:
- `get_association`
- `create_association`
- No implementa `update_association`.

La UoW local expone este adaptador como `unit.project_environment_associations`, ligado al mismo `SQLiteUnitOfWork` que el resto de repositorios canónicos. El puerto `ProjectEnvironmentAssociationPort` declara lectura y creación; el puerto reader-only permanece disponible para consumidores que solo necesitan lectura.

### 1.3 Writer lifecycle estrecho

Nuevo adaptador interno `SQLiteProjectEnvironmentLifecycleAssociationWriter`:
- solo acepta `SQLiteLocalAuthorityUnitOfWork`;
- exige UoW activa, misma instancia de `SQLiteDatabase`, conexión presente y transacción abierta;
- realiza CAS por `expected_revision`;
- exige `lifecycle_event_id`;
- no autentica ni autoriza.

El writer no se agrega a `SQLiteLocalAuthorityUnitOfWork`, no se exporta desde el paquete SQLite y no se entrega a consumidores generales.

### 1.4 Servicio y composición confiable

`ProjectEnvironmentLifecycleService` ahora recibe dos factories internas:
- `ledger_factory(unit)`
- `association_writer_factory(unit)`

El servicio obtiene la asociación por `unit.project_environment_associations`, revalida USER y Platform Admin en esa misma UoW y usa ambos writers antes del commit. La composición confiable crea ambos adaptadores con el mismo objeto `SQLiteLocalAuthorityUnitOfWork`. No hay factory pública ni atributo writer en la UoW general.

### 1.5 Consumidor Workspace read-only

`WorkspaceCapabilityExecutionService` ahora lee el estado de asociación a través de `unit.project_environment_associations`. Conserva la comprobación ACTIVE antes de resolver el mount y ejecutar lectura/listado.

## 2. Pruebas actualizadas o añadidas

- La UoW expone repositorio de asociaciones y repositorio Workspace separados.
- El repositorio Workspace no ofrece métodos de asociación.
- El repositorio de asociaciones no ofrece transición lifecycle.
- El writer se liga a la conexión de la UoW local activa y rechaza uso después de salir de la UoW o con una base de datos distinta.
- Las pruebas de servicio lifecycle pasan el writer mediante factory separada.
- Las pruebas de composición confiable y Workspace usan los nuevos puertos.
- Se mantiene la cobertura de CAS, rollback, concurrencia y denegación de asociaciones suspendidas.

## 3. Límites que permanecen

- El writer es un módulo Python interno, no un sandbox. Código arbitrario dentro del mismo proceso puede importar módulos internos.
- Un proceso con acceso directo de escritura a SQLite puede intentar operaciones SQL directas; V26 garantiza integridad/atomicidad de la estructura, no autorización Platform Admin.
- La creación de asociaciones permanece como operación separada de lectura/creación; no es una transición ACTIVE/SUSPENDED.
- No se realizó todavía un barrido exhaustivo de todos los imports/call-sites. Esa comprobación forma parte de 7B.6C.
- No hay runtime registration, HTTP, CLI, plugins, endpoint, bootstrap real ni migración nueva.
- No se modificaron host, systemd, Docker, usuarios, privilegios, secretos o DB productiva.

## 4. Validación pendiente

El propietario debe ejecutar en Debian:

```bash
cd ~/atlas-dev
git pull --ff-only
git log -1 --oneline

PYTHONPATH=tests:tests/unit python -m unittest \
  test_sqlite_workspace_registry_repository \
  test_sqlite_local_authority_unit_of_work \
  test_project_environment_lifecycle_service \
  test_trusted_project_environment_lifecycle_composition \
  test_workspace_capability_execution -v

python -m compileall -q src tests
echo "COMPILE_EXIT_CODE=$?"

python -m unittest discover -s tests -v
```

No se afirma que compileall o los tests hayan pasado hasta recibir los resultados del propietario.

## 5. Próxima fase

7B.6C debe completar el inventario de imports/call-sites de las antiguas operaciones de asociación, confirmar que no existe consumidor de aplicación alternativo, revisar exports y ejecutar pruebas adversariales adicionales. La fase no habilitará runtime.

PR #16 permanece Draft, abierto y sin merge.


## 6. Corrección posterior a validación — 7B.6B

La primera ejecución del propietario en Debian detectó un error sintáctico en `tests/unit/test_project_environment_lifecycle_service.py`: el constructor principal del servicio declaraba dos veces el argumento `association_writer_factory`.

Se eliminó la segunda declaración redundante, conservando una sola factory para esa instancia. Commit correctivo: `c2422d5a1e4824a3190e1d8491f2a184715f313d`.

Se revisaron los cinco archivos de pruebas de la fase: no se encontraron llamadas antiguas a `unit.workspaces.get_association/create_association/update_association` ni a `self.repository.get_association/create_association/update_association`. En el archivo del servicio hay cinco asignaciones de factory correspondientes a distintas instancias de prueba; no equivalen a argumentos duplicados dentro de una misma llamada.

**Estado:** corrección publicada; compileall y pruebas siguen pendientes de repetición en Debian. No avanzar a 7B.6C hasta recibir validación limpia.
