# Cycle 3.2-A — implementación del registro canónico

**Estado:** implementado en rama de trabajo; pendiente de verificación local por el propietario.

**Rama:** `feature/cycle-3-2-trusted-console-workspaces`

## Alcance implementado

- Contratos de dominio inmutables `ProjectEnvironmentAssociation` y `WorkspaceRecord`.
- Estados explícitos: asociación `active/suspended`; workspace `active/suspended/disabled`.
- Puertos `ProjectEnvironmentAssociationPort` y `WorkspaceRegistryPort`.
- Migración aditiva SQLite v18.
- Repositorio `SQLiteWorkspaceRegistryRepository`.
- Integración en `SQLiteLocalAuthorityUnitOfWork.workspaces`.
- Exportación de `CORE_SCHEMA_V18` y del repositorio desde el paquete SQLite.
- Pruebas unitarias de persistencia, CAS, integridad referencial, inmutabilidad y rollback.

## Modelo físico v18

### `atlas_project_environments`

Clave primaria compuesta `(project_id, environment_id)`; FKs independientes a las autoridades canónicas existentes; estado, revisión y timestamps. La asociación es muchos-a-muchos, se crea explícitamente y se conserva como tombstone. Su identidad no puede modificarse y la revisión debe aumentar exactamente uno.

### `atlas_workspaces`

Contiene `workspace_id`, `owner_user_id`, `project_id`, `environment_id`, `root_ref`, estado, revisión y timestamps.

- `owner_user_id` referencia `atlas_users.user_id`.
- El par Project/Environment referencia la clave compuesta de `atlas_project_environments`.
- Un trigger impide crear un workspace si la asociación no está activa.
- Identidad, owner, ámbito y `root_ref` son inmutables.
- Las revisiones avanzan exactamente uno.
- No hay DELETE: los registros se retienen como tombstones.

La migración no crea asociaciones ni workspaces históricos por inferencia; no realiza backfill.

## Repositorio y transacciones

`SQLiteWorkspaceRegistryRepository` ofrece lectura/alta/actualización CAS de asociaciones y workspaces, y listado por propietario. Acepta una `SQLiteUnitOfWork` existente y se integra en la UoW local compartida como `unit.workspaces`.

El repositorio no resuelve `root_ref` a filesystem. Tampoco concede permisos. La asociación activa se comprueba al crear el workspace en SQL; la validez actual de Project, Environment, asociación, owner y Grant deberá revalidarse por el gate CAM en 3.2-B.

## Seguridad y límites

- No se conecta la CLI.
- No se modifica `LocalConsoleRequestFactory`.
- No se crea autenticación local provisional ni se habilitan sesiones.
- No se modifica `WorkspaceCapabilityExecutionService` en este incremento.
- No se habilitan escritura, shell, Skills, Broker ni runtime.
- No se resuelve ni acepta una ruta física del caller; `root_ref` es simbólico.
- No se modifica la base de datos productiva ni el host.

## Verificación pendiente

El propietario debe ejecutar en Debian desde el checkout actualizado de la rama:

```bash
python -m unittest tests.unit.test_sqlite_workspace_registry_repository -v
python -m unittest discover -s tests -t tests -v
python -m compileall -q src tests
```

No se declara que estas pruebas hayan pasado hasta recibir la salida real. Si la suite completa detecta fallos, se corrigen antes de integrar.

## Siguiente paso

Tras validar 3.2-A, continuar con 3.2-B: resolver `root_ref` mediante configuración de mounts confiable y modificar el gate CAM para que obtenga owner, Project, Environment y asociación desde los registros canónicos dentro de la misma UoW, manteniendo el Grant exacto y el acceso filesystem protegido. La consola seguirá sin capacidades protegidas hasta que exista autenticación verificable operacional.
