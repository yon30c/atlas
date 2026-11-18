# I3-2B.7B.6A — auditoría de frontera de escritura del lifecycle

**Estado:** auditoría de arquitectura publicada; diseño de implementación pendiente de revisión.
**PR:** #16 — Draft, abierto y sin merge.
**Base:** 7B.5C validada por el propietario con 1,517 tests en 30.234 s — OK.
**Alcance:** inspección estática de contratos, UoW, adaptadores y composición. Sin cambios de código, schema, runtime, HTTP, CLI o infraestructura.

## 1. Objetivo

Antes de exponer cualquier operación de suspensión/reactivación, verificar que la capacidad de escribir el estado de una asociación Project/Environment solo esté disponible a través de `ProjectEnvironmentLifecycleService`, después de revalidar identidad USER y Platform Admin dentro de la misma UoW.

La meta no es fingir que Python proporciona aislamiento entre módulos. Es reducir las capacidades de escritura entregadas accidentalmente a consumidores generales y hacer explícita la diferencia entre lectura de asociaciones, administración de Workspaces y transición lifecycle autorizada.

## 2. Hallazgos confirmados

### 2.1 La UoW general expone un adaptador con capacidad de escritura lifecycle

`SQLiteLocalAuthorityUnitOfWork.__enter__` construye `SQLiteWorkspaceRegistryRepository` y lo publica como `unit.workspaces`.

Ese repositorio combina operaciones distintas:
- lectura de Workspace y asociación;
- creación de Workspace y asociación;
- actualización CAS de Workspace;
- actualización de estado de asociación mediante `update_association(..., lifecycle_event_id=...)`.

Por tanto, aunque la UoW no tiene un atributo llamado `lifecycle_ledger` ni expone el ledger writer, sí entrega a cualquier consumidor interno con acceso a `unit.workspaces` el método de actualización de asociación. La composición de 7B.5B limita la closure del ledger, pero no retira esta capacidad del repositorio mixto.

### 2.2 El contrato de puerto no coincide con el adapter

Hay tres contratos/superficies relevantes:
- `ProjectEnvironmentAssociationReaderPort` en `src/atlas/ports/project_environment_associations.py` define lectura de la asociación.
- `ProjectEnvironmentAssociationPort` en `src/atlas/ports/workspace_registry.py` declara `update_association(association, expected_revision)`, sin `lifecycle_event_id`.
- `SQLiteWorkspaceRegistryRepository.update_association` exige `lifecycle_event_id`.

El puerto de escritura está desactualizado frente al contrato SQL V26. Además, la separación entre el puerto de lectura y el repositorio mixto no se refleja todavía en la composición de UoW.

### 2.3 El servicio lifecycle es el punto correcto de política

`ProjectEnvironmentLifecycleService.transition`:
1. adquiere la UoW;
2. captura Clock UTC después de adquirir el bloqueo;
3. revalida evidencia USER mediante el verifier real dentro de esa UoW;
4. exige un único grant Platform Admin activo y el permiso exacto;
5. comprueba asociación, estado y revisión;
6. escribe evento y transición con el mismo contexto transaccional;
7. confirma la UoW.

La composición confiable de 7B.5B construye el verifier real y enlaza el ledger a la UoW local. Esta ruta debe seguir siendo la única ruta de aplicación soportada para cambiar ACTIVE/SUSPENDED.

### 2.4 V26 protege integridad, no autorización

Los triggers V26 obligan a que evento, transición, revisión y marcador sean coherentes y atómicos, y comprueban que el actor corresponde a un USER canónico activo. No verifican el grant Platform Admin ni el permiso lifecycle.

Un proceso con acceso directo de escritura a SQLite puede intentar reproducir la estructura SQL. Por ello, V26 no debe describirse como frontera de autorización frente a código con acceso arbitrario a la DB.

### 2.5 Lectura de asociaciones por consumidores

`WorkspaceCapabilityExecutionService` consulta la asociación canónica desde `unit.workspaces` y exige que esté ACTIVE antes de resolver el Workspace. Esa lectura debe continuar disponible sin entregar al servicio de lectura la capacidad de transición lifecycle.

Los tests de infraestructura pueden seguir probando el adapter y SQL directamente sobre bases temporales. Esas pruebas no constituyen una ruta operativa de producto.

## 3. Riesgo y clasificación

**Riesgo arquitectónico confirmado:** la UoW de autoridad local entrega un repositorio mixto que contiene una operación lifecycle de escritura. La autorización está implementada en el servicio, no en el repositorio ni en SQL.

**No se ha demostrado:** una ruta HTTP, CLI, agente o plugin que actualmente invoque directamente `update_association`. La revisión de este corte no constituye un inventario exhaustivo de todos los imports/call-sites del repositorio.

**Límite de confianza:** separar objetos y puertos reduce exposición accidental y errores de composición, pero no detiene código Python deliberadamente malicioso dentro del mismo proceso. Skills/plugins no confiables requieren aislamiento de proceso y una frontera IPC/broker; no deben recibir el objeto UoW, el repositorio SQLite ni la conexión DB.

## 4. Diseño recomendado para 7B.6B

### 4.1 Separar lectura y escritura

- Mantener un puerto de lectura de asociación para consumidores que solo necesitan comprobar existencia/estado/revisión.
- Mantener `WorkspaceRegistryPort` para operaciones de Workspace, sin métodos de transición de asociación.
- Definir un puerto estrecho de transición lifecycle cuyo contrato incluya explícitamente `expected_revision` y `lifecycle_event_id`.
- Evitar que `SQLiteLocalAuthorityUnitOfWork.workspaces` exponga el writer lifecycle.

### 4.2 Entregar la capacidad writer solo al servicio lifecycle

La composición confiable debe construir el writer lifecycle sobre la UoW activa y pasarlo al servicio mediante una closure/factory interna. La closure debe validar el tipo exacto de UoW, base de datos y transacción activa, siguiendo el patrón de 7B.5B.

Los consumidores de Workspace y los servicios generales reciben solo lectores. El writer no se agrega como atributo general a `SQLiteLocalAuthorityUnitOfWork`, ni se exporta desde paquetes públicos.

### 4.3 Mantener la política en aplicación

El repositorio writer no autentica ni decide permisos. La única operación de aplicación soportada para transición continúa siendo `ProjectEnvironmentLifecycleService.transition`, que revalida USER y Platform Admin en la misma UoW.

No duplicar el verificador, no mover permisos a un boolean caller-controlled y no interpretar el trigger V26 como autorización.

### 4.4 Pruebas obligatorias

1. La UoW general expone lectura de asociaciones, pero no una operación de transición lifecycle.
2. La UoW conserva las capacidades de Workspace necesarias para los consumidores actuales.
3. La composición lifecycle crea un writer ligado a la misma UoW/transacción que el verifier.
4. Writer rechaza UoW inactiva, de otra base o de otro tipo.
5. La transición autorizada mantiene atomicidad evento + asociación + marcador.
6. El servicio Workspace read-only sigue denegando asociaciones suspendidas.
7. No hay cambios de asociación por rutas alternativas de aplicación soportadas.
8. El contrato del puerto coincide con la firma real del adapter.
9. Los rechazos de autorización/revisión no producen escrituras.
10. Los tests de exportación verifican que writer y composition no se convierten en API pública.

### 4.5 Fuera de alcance

- No endpoint, CLI, runtime registration, agente o plugin.
- No bootstrap real, migración productiva ni cambios de V26.
- No cascadas a Grants, delegaciones o Workspaces.
- No cambios en systemd, Docker, usuarios, privilegios, secretos o permisos del host.
- No afirmar sandboxing Python ni protección frente a un proceso con acceso de escritura a la DB.

## 5. Decisión de secuencia

- **7B.6A:** auditoría de frontera completada; este documento registra el hallazgo y la propuesta.
- **7B.6B:** separar puertos/adaptadores de lectura y escritura lifecycle; corregir la firma del contrato y restringir la capacidad writer a la composición interna.
- **7B.6C:** pruebas adversariales de composición y barrido de call-sites/imports antes de considerar cualquier exposición.
- **Después:** una revisión de seguridad independiente deberá decidir si existe una frontera de proceso adecuada para skills/plugins. Ninguna de estas fases habilita por sí sola el lifecycle en runtime.

## 6. Estado de seguridad

7B.5C permanece validada por el propietario con **1,517 tests en 30.234 s — OK**. No se reportó compileall para ese checkpoint.

Este corte es documental y no altera el comportamiento ejecutable. PR #16 permanece Draft, abierto y sin merge.


## 7. Seguimiento 7B.6B — implementación publicada, validación pendiente

Se implementó la separación descrita en esta auditoría. `SQLiteWorkspaceRegistryRepository` ya no contiene métodos de asociación; `SQLiteProjectEnvironmentAssociationRepository` gestiona lectura/creación; y `SQLiteProjectEnvironmentLifecycleAssociationWriter` es un adaptador interno separado, ligado a una UoW local activa y a la misma base de datos.

La UoW general expone `project_environment_associations` y `workspaces`, pero no expone el writer lifecycle. El servicio lifecycle recibe ledger y association writer por factories internas y la composición confiable crea ambos sobre la misma UoW. Workspace read-only consulta el nuevo repositorio de asociaciones.

La firma de `WorkspaceRegistryPort` quedó limitada a operaciones Workspace. `ProjectEnvironmentAssociationPort` declara lectura/creación, mientras `ProjectEnvironmentLifecycleAssociationWriterPort` declara el CAS lifecycle con `expected_revision` y `lifecycle_event_id`.

Las pruebas y fixtures correspondientes fueron actualizadas, incluyendo límites de capacidades y rechazo de writer fuera de una UoW activa o con otra base de datos. **No se han ejecutado localmente en este entorno ni han sido validadas por el propietario**. Ver `docs/design/i3-2b-7b6b-lifecycle-write-capability-separation.md` para los comandos.

No se realizó aún el inventario exhaustivo de todos los imports/call-sites; queda para 7B.6C. No hay runtime registration, endpoint, CLI, plugin ni cambio de infraestructura. PR #16 permanece Draft, abierto y sin merge.
