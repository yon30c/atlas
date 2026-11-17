# Cycle 3.2 — diseño técnico del contexto confiable y registro de workspaces

**Estado:** propuesta técnica para revisión; todavía no autoriza migración de datos reales ni conexión de la consola al runtime protegido.  
**Baseline:** `main` en `1a0523280d42e14986c370ebb88887ce527a6403`.  
**Rama de trabajo:** `feature/cycle-3-2-workspace-registry`.  
**Fecha:** 2026-11-17.

## 1. Resultado de la inspección de GitHub

La revisión del código de `main` confirma:

- `SQLITE_MIGRATIONS` contiene las migraciones v1–v17. La v5 (`canonical_user_identity`) y la v6 (integridad recíproca) están integradas.
- `SQLiteIdentityAuthority` crea y resuelve la relación canónica `UserId ↔ Identity(USER)`. No implementa autenticación, issuers, bindings externos ni `VerifiedIdentityContext`.
- `atlas_projects` y `atlas_environments` se crean en v9 como registros separados. El repositorio no persiste una relación Environment→Project.
- El modelo lógico aprobado B1-B-02 establece que cada Environment pertenece a exactamente un Project y que esa pertenencia no se transfiere ordinariamente.
- `LocalWorkspaceAdapter` recibe un mapa en memoria `workspace_id → Path`. Valida raíces absolutas/canónicas, directorios reales, rutas relativas y symlinks; no mantiene ownership ni relación canónica con Project/Environment.
- `WorkspaceCapabilityExecutionService` exige un contexto con actor USER activo, compara actor y UserId con Identity Authority, valida Project/Environment activos y evalúa el Grant exacto dentro de la misma UoW. Sin embargo, el contexto llega como argumento y no se demuestra que provenga de autenticación verificada. El workspace se resuelve por el adaptador configurado, no por un registro durable.
- `LocalConsoleRequestFactory` sigue generando una identidad sintética basada en `getuser()`, un `user_id` no canónico, `project_id=None` y entorno `local`. No debe convertirse en fuente de identidad autorizada.
- No se encontró una clase Python operativa `VerifiedIdentityContext`, Authentication Authority ni flujo de sesión/login en la ruta revisada.

## 2. Invariantes que no se modifican

1. Identity Authority es la única autoridad de `UserId ↔ Identity(USER)`.
2. La identidad del proceso Linux no autentica a una persona Atlas.
3. La autenticación no concede permisos; CAM evalúa cada operación.
4. El servicio de Cycle 3.1 conserva su gate exacto, la misma UoW y su perfil exclusivamente read-only.
5. Los valores de actor, UserId, proyecto, entorno, owner o workspace suministrados por el modelo/caller no son evidencia de autoridad.
6. No se infieren relaciones para registros históricos ni se asignan propietarios por conveniencia.
7. La ruta física es configuración de instalación/mount confiable; no es una ruta universal almacenada como supuesto portable en la base.
8. Las migraciones históricas v1–v17 permanecen inmutables.

## 3. Propuesta de incrementos

### 3.2A — Relación canónica Environment→Project

Añadir una migración aditiva (candidata v18) con una relación durable e inmutable entre Environment y Project.

Propuesta de tabla `atlas_environment_projects`:

- `environment_id`: clave primaria y FK a `atlas_environments`.
- `project_id`: FK a `atlas_projects`.
- `created_at`: timestamp UTC.

La clave primaria en `environment_id` impide que un Environment pertenezca a más de un Project. La FK compuesta que use posteriormente el registro de workspaces permitirá comprobar que el Project del workspace coincide con el Project propietario del Environment.

**Compatibilidad legacy:** no se asignará automáticamente un Project a ningún Environment existente. Los registros sin relación explícita se considerarán no resueltos y no podrán participar en operaciones protegidas. La migración debe conservarlos sin inventar asociaciones. Toda reconciliación será una operación explícita y revisable.

Las nuevas creaciones de Environment deberán registrar Environment y relación Environment→Project en la misma UoW. El repositorio no expondrá una ruta nueva que permita crear un Environment utilizable sin pertenencia canónica.

### 3.2B — Registro durable de workspaces

Añadir una tabla `atlas_workspaces` con, como mínimo:

- `workspace_id`: ID lógico estable, único e inmutable.
- `owner_user_id`: FK a `atlas_users(user_id)`.
- `project_id`: FK a Project.
- `environment_id`: referencia a Environment y a su relación exacta con Project.
- `mount_ref`: identificador opaco de una raíz montada/configurada; no un path arbitrario enviado por el modelo.
- `status`: estado explícito.
- `revision`: revisión positiva y monotónica.
- `created_at`, `updated_at`.

Las restricciones deberán impedir:
- cambiar la identidad del workspace;
- transferir owner, Project, Environment o mount mediante una actualización ordinaria;
- asociar el workspace a un par Environment/Project que no corresponda;
- borrar físicamente registros de autoridad;
- saltar revisiones.

Los cambios de ownership o de asociación no se implementarán como un simple UPDATE; requieren una operación coordinada y una política específica.

### 3.2C — Resolución confiable de raíz física

El registro SQLite almacenará `mount_ref`, no la ruta absoluta del host. Una configuración confiable de instalación resolverá `mount_ref → Path` y se inyectará al adaptador.

El adaptador conservará sus comprobaciones actuales de:
- raíz absoluta y existente;
- directorio real, no symlink;
- ruta canónica;
- confinamiento de rutas relativas;
- rechazo de traversal y symlinks;
- límites de tamaño y tipo de archivo.

Un `mount_ref` ausente, duplicado, inválido o no disponible produce denegación. El modelo nunca podrá crear ni cambiar mounts.

### 3.2D — Integración con el gate CAM

Antes de cualquier lectura protegida, el servicio resolverá el workspace desde el registro durable dentro de la misma `SQLiteLocalAuthorityUnitOfWork` que lee Identity, Project, Environment y Grants.

Debe comprobar:
- identidad canónica y UserId coincidentes;
- Project activo;
- Environment activo y perteneciente exactamente al Project del contexto;
- workspace activo;
- owner del workspace igual al UserId canónico del perfil inicial;
- Project/Environment del workspace iguales al contexto confiable;
- `mount_ref` resuelto por configuración confiable;
- Grant exacto para acción y recurso.

La lectura/listado permanecerá dentro de la UoW, después de `AuthorizationDecision.ALLOW`. El recurso de `workspace.read` conservará el ID canónico actual `[workspace_id, path]`.

No se añade escritura de workspace ni se permite que la confirmación humana sustituya CAM.

### 3.2E — Identidad autenticada de consola (bloqueada por dependencias)

La consola solo podrá construir un contexto para operaciones protegidas cuando exista el flujo aprobado:

`Authentication Authority → evidencia nativa → Identity Authority → VerifiedIdentityContext → frontera confiable → OperationContext → CAM`.

El contrato de compatibilidad ya aprobado define esa secuencia, pero la implementación de Authentication Authority, issuer nativo, prueba anti-replay y sesiones continúa pendiente. Por tanto:

- no se creará una clase de contexto verificado improvisada;
- no se aceptará un `OperationContext` del caller como autenticación;
- no se mapeará `getuser()` a un UserId canónico;
- la conversación no protegida puede continuar bajo política explícita, pero las capacidades protegidas permanecerán inaccesibles desde la consola hasta cerrar esta dependencia.

## 4. Orden de implementación recomendado

1. Añadir pruebas de migración/upgrade para Environment legacy sin relación y para nuevas relaciones.
2. Implementar v18 y repositorio Environment→Project con inmutabilidad, unicidad y UoW.
3. Implementar registro de workspaces y pruebas de ownership, Project/Environment exactos, revisiones y tombstones.
4. Implementar resolver confiable `mount_ref → Path` y probar configuración faltante/ambigua.
5. Adaptar `WorkspaceCapabilityExecutionService` para resolver el workspace desde el registro, sin debilitar CAM ni la UoW.
6. Ejecutar pruebas focalizadas y suite completa en el entorno del propietario.
7. Mantener la consola sin ejecución protegida hasta que la ruta de autenticación verificada esté implementada y validada.

## 5. Pruebas de aceptación obligatorias

- Upgrade desde schema v17 conserva todos los registros existentes.
- Environment legacy sin relación explícita no puede usarse para operaciones protegidas.
- Environment no puede asociarse a dos Projects.
- Workspace no puede apuntar a un Environment perteneciente a otro Project.
- Workspace no puede tener owner inexistente.
- Cambios de owner/Project/Environment/mount y borrado son rechazados por restricciones.
- Revisión obsoleta o salto de revisión es rechazado.
- Workspace inactivo, Environment inactivo o Project inactivo deniegan.
- `mount_ref` ausente o sin configuración confiable deniega antes del filesystem.
- Grant ausente, vencido, revocado o con acción/recurso/scope distinto deniega antes del filesystem.
- La UoW sigue abierta durante la operación protegida.
- La identidad sintética de consola no puede acceder al servicio protegido.
- No se modifica la semántica ni se habilita escritura de Cycle 3.1.

## 6. Límites

Este documento no activa autenticación, bootstrap, sesiones ni Recovery Gate. No ejecuta migraciones sobre la base real, no reconcilia datos legacy, no cambia host/usuarios/PAM/sudoers/systemd/SSH/Docker, no despliega servicios y no integra la consola con capacidades protegidas.

**Decisión solicitada:** revisar y aprobar el diseño de 3.2A–3.2D antes de escribir migración v18 y código de repositorios. La parte 3.2E permanece bloqueada por las decisiones físicas y la implementación de autenticación nativa.
