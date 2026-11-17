# Cycle 3.2 — consola confiable y registro de workspaces

**Estado:** contrato técnico aprobado por el propietario. Cycle 3.2-A está implementado en rama de trabajo y pendiente de verificación local; ver `cycle-3-2-a-workspace-registry-implementation.md`.

**Base inspeccionada:** `1a0523280d42e14986c370ebb88887ce527a6403`.

## 1. Objetivo y límites

Cycle 3.2 debe preparar una frontera confiable entre la consola local, la identidad canónica, el contexto Project/Environment y los workspaces físicos.

El incremento no habilita todavía ejecución desde la CLI, no implementa autenticación nativa, no cambia privilegios del host y no modifica la política CAM de Cycle 3.1. La autenticación nativa tiene su propio contrato aprobado y debe implementarse en su fase correspondiente.

Se conserva el principio fail-closed: si falta una prueba de identidad confiable, una selección de proyecto/entorno de configuración confiable o un registro de workspace válido, no se ejecuta la capacidad.

## 2. Hechos observados en main

1. La migración v5 está integrada: `identity_records` y `atlas_users` persisten la relación canónica `UserId ↔ Identity(USER)`.
2. Las migraciones posteriores agregaron las autoridades canónicas de Project y Environment. En v9, `atlas_projects` y `atlas_environments` se crean como tablas independientes, con estado y revisión.
3. `SQLiteProjectEnvironmentRepository` consulta y modifica Project y Environment por separado; no existe una asociación persistente entre ambos.
4. `LocalConsoleRequestFactory` usa `getpass.getuser()` por defecto y fabrica `user_id=local:<os-user>` e `identity_id=local-user:<os-user>`. Esos valores no son identificadores canónicos ni evidencia de autenticación.
5. `LocalWorkspaceAdapter` recibe un mapa en memoria `workspace_id → Path`. Valida rutas absolutas, directorios canónicos, traversal y symlinks, pero no conoce propietario, proyecto ni entorno.
6. `WorkspaceCapabilityExecutionService` ya valida Identity canónica, Project y Environment activos, Grant exacto y revisión explícita dentro de `SQLiteLocalAuthorityUnitOfWork`. El acceso filesystem ocurre dentro de esa UoW.
7. Cycle 3.1 está limitado a `workspace.list` y `workspace.read`, no está conectado a `cli.py` y no proporciona fencing para cambios de configuración externos.

## 3. Contrato propuesto para la sesión de consola

### 3.1 Separación de identidad humana y proceso

- El usuario del sistema operativo, UID/GID, hostname y variables de entorno ordinarias pueden servir para diagnóstico o selección de configuración no privilegiada, pero nunca prueban identidad humana Atlas.
- La CLI no debe convertir `getuser()`, un argumento `--user` ni un `UserId` recibido del caller en una identidad autenticada.
- Una sesión autorizable debe recibir un contexto de identidad emitido por la frontera de autenticación/Identity Authority después de verificar la evidencia y validar issuer/binding según el contrato de autenticación aprobado.
- CAM sigue autorizando cada operación. Una sesión autenticada no equivale a un Grant.
- Mientras Authentication Authority y la emisión operacional de `VerifiedIdentityContext` no existan, la consola puede conservar el modo conversacional, pero no debe invocar capacidades protegidas. El contexto conversacional local debe permanecer explícitamente fuera del camino de autorización.

### 3.2 Construcción de contexto

La composición confiable, no el modelo ni los argumentos de una solicitud, debe resolver y construir el contexto de operación autorizado. Como mínimo, debe ligar:

- identidad canónica y revisión;
- UserId canónico;
- referencia de sesión autenticada/verificada con expiración y estado;
- Project seleccionado desde configuración confiable;
- Environment asociado a ese Project;
- origen de consola y propósito de la operación.

No se propone persistir un `OperationContext` caller como prueba. El contexto se construye por operación a partir de evidencia de sesión verificada y fuentes canónicas actuales.

### 3.3 Configuración de Project/Environment

La selección activa debe proceder de configuración administrada por el despliegue o de una interfaz administrativa autenticada futura. No debe proceder de parámetros del prompt ni de valores inventados por el modelo.

La asociación Project–Environment debe persistirse explícitamente. La primera versión puede permitir que un Environment pertenezca a varios Projects si esa es la semántica deseada; la alternativa de pertenencia exclusiva debe aprobarse antes del esquema. No se debe inferir ni backfill automático de asociaciones para registros históricos existentes.

## 4. Registro persistente de workspaces propuesto

Se recomienda introducir una autoridad de Workspace independiente del adaptador filesystem.

### 4.1 Relación canónica

Cada registro inicial de workspace debe contener:

- `workspace_id`: identificador estable e inmutable;
- `owner_user_id`: FK a `atlas_users.user_id`;
- `project_id`: FK a `atlas_projects.project_id`;
- `environment_id`: FK a `atlas_environments.environment_id`;
- asociación válida Project–Environment, protegida por FK compuesta;
- `root_ref`: clave simbólica de mount/configuración confiable, no una ruta suministrada por el modelo;
- `status`: estado explícito, inicialmente `active` o inactivo/suspendido según el vocabulario de dominio aprobado;
- `revision`: revisión positiva con incremento exactamente de uno;
- marcas temporales de creación/actualización.

La primera versión recomienda un propietario canónico por workspace. Compartir workspaces entre usuarios requiere una política explícita de ownership/ACL y no debe simularse con varios propietarios implícitos.

### 4.2 Resolución de raíz física

La base de datos no debe convertir una ruta absoluta recibida de una solicitud en raíz confiable. `root_ref` se resuelve mediante un registro de mounts/configuración del despliegue, administrado fuera del modelo y protegido por el límite operativo del host.

El adaptador debe recibir únicamente la asociación ya validada entre workspace y raíz resuelta. Se conservan las defensas existentes de `LocalWorkspaceAdapter`: ruta absoluta canónica, directorio real, rechazo de symlinks y confinamiento de rutas relativas.

La ruta dentro del contenedor puede diferir de la ruta del host. El registro guarda una referencia lógica; la composición del despliegue resuelve esa referencia al mount disponible en ese nodo.

### 4.3 Autorización de acceso

Antes del filesystem, dentro de la misma `SQLiteLocalAuthorityUnitOfWork`, el servicio debe:

1. validar identidad canónica y sesión confiable;
2. resolver Workspace por `workspace_id`;
3. exigir Workspace activo;
4. exigir que `owner_user_id` coincida con el UserId canónico de la sesión para el perfil inicial;
5. exigir Project activo y Environment activo;
6. exigir asociación Project–Environment activa;
7. evaluar el Grant exacto para acción/recurso y propietario;
8. resolver `root_ref` contra configuración de mounts confiable;
9. ejecutar únicamente la capacidad autorizada.

No se debe aceptar `owner_user_id`, `project_id`, `environment_id` ni ruta física desde el plan como autoridad. Los valores del plan solo pueden identificar el workspace y la ruta relativa solicitada; todos los atributos de propiedad y ubicación se obtienen de fuentes confiables.

La lectura/listado sigue dentro de la UoW SQLite como en Cycle 3.1. Esto no crea fencing para cambios externos de mounts/configuración; la composición debe documentar y limitar esa garantía local.

## 5. Esquema de persistencia: propuesta para revisión

La inspección muestra que el esquema actual llega a v17. Se propone que el primer cambio físico sea una migración aditiva v18, sin editar v1–v17:

- tabla de asociación Project–Environment, con claves foráneas compuestas;
- tabla `atlas_workspaces` con ownership, Project, Environment, `root_ref`, estado y revisión;
- índices para búsquedas por propietario y por Project/Environment;
- restricciones y triggers para identidad inmutable, revisión monotónica y retención de tombstones.

No se debe elegir entre asociación muchos-a-muchos y pertenencia exclusiva de Environment a Project sin aprobación. Si se elige muchos-a-muchos, la tabla de asociación evita reconstruir las tablas históricas y permite que un workspace referencie un par válido mediante FK compuesta.

No se deben insertar workspaces predeterminados ni asociar automáticamente entornos históricos durante la migración. La migración solo establece estructura; el alta de registros debe ser una operación explícita posterior.

## 6. Composición y responsabilidades

- **Authentication Authority:** verifica el método de autenticación y la sesión; no crea Grants.
- **Identity Authority:** valida issuer/binding y resuelve identidad/UserId canónicos; emite el contexto verificado según el contrato aprobado.
- **Project/Environment Authority:** mantiene estados, revisiones y asociaciones válidas.
- **Workspace Authority:** mantiene ownership, ámbito Project/Environment y referencia lógica de mount.
- **Trusted deployment configuration:** resuelve `root_ref` a un mount disponible; no deriva rutas del prompt.
- **CAM:** decide cada acción sobre el recurso exacto.
- **Workspace adapter:** ejecuta operaciones filesystem confinadas; no decide identidad ni autorización.
- **CLI:** presenta la sesión y solicita operaciones; no es una autoridad.

La UoW compartida debe exponer las nuevas lecturas de Workspace y asociación Project–Environment sobre la misma conexión. No se deben abrir conexiones alternativas durante la comprobación y el acceso protegido.

## 7. Secuencia incremental propuesta

### 3.2-A — Contratos y esquema

1. Aprobar cardinalidad Project–Environment y vocabulario de estados.
2. Definir puertos/modelos de Workspace y Project–Environment association.
3. Añadir migración aditiva v18 y pruebas de integridad/compatibilidad.
4. Añadir repositorios SQLite y su integración en la composición/UoW.
5. No conectar CLI ni ejecutar filesystem desde este incremento.

### 3.2-B — Resolución y gate de Workspace

1. Introducir un resolver de `root_ref` basado exclusivamente en configuración confiable.
2. Adaptar `WorkspaceCapabilityExecutionService` para resolver el registro canónico.
3. Rechazar workspace inexistente, inactivo, de otro owner, Project/Environment no asociados o mount no disponible.
4. Mantener Grant exacto y UoW durante la lectura/listado.
5. Añadir pruebas negativas para sustitución de owner, proyecto, entorno, root_ref, symlink y configuración ausente.

### 3.2-C — Frontera de sesión de consola

1. Definir la interfaz de entrada de sesión verificada sin implementar un autenticador paralelo.
2. Mantener la consola conversacional sin privilegios mientras no exista autenticación operacional.
3. Integrar la CLI solo cuando Authentication Authority pueda entregar el contexto verificado aprobado.
4. No mapear automáticamente cuentas Linux a usuarios Atlas.
5. No conectar runtime, Broker, Skills ni capacidades de escritura en esta fase.

## 8. Criterios de aceptación

- Ninguna identidad sintética de consola puede pasar el gate CAM.
- Ningún caller puede elegir su propio UserId, owner, Project, Environment o ruta raíz.
- Un Environment sin asociación explícita con el Project seleccionado no autoriza.
- Un workspace sin registro, suspendido o asociado a otro propietario no autoriza.
- Un `root_ref` ausente, ambiguo o no resuelto falla de forma cerrada.
- La UoW y el evaluador CAM de Cycle 3.1 permanecen obligatorios.
- La migración es aditiva y no altera datos históricos.
- Pruebas de migración desde esquemas anteriores, integridad referencial, concurrencia SQLite, denegaciones y regresión completa.
- Ningún cambio de host, systemd, sudoers, PAM, SSH, usuarios/grupos o privilegios.

## 9. Decisiones que requieren aprobación

1. **Cardinalidad Project–Environment:** recomiendo muchos-a-muchos mediante `atlas_project_environments`, con selección explícita de un par activo por sesión.
2. **Ownership inicial:** recomiendo exactamente un `owner_user_id` por workspace; compartir queda fuera de alcance hasta diseñar ACL.
3. **Raíz física:** recomiendo `root_ref` simbólico en SQLite y resolución a mount por configuración confiable del despliegue; no guardar rutas host como autoridad en registros manipulables por la aplicación.
4. **Autenticación de consola:** recomiendo no habilitar capacidades protegidas hasta que la autenticación nativa aprobada emita un contexto verificable. No crear una identidad local provisional con privilegios.
5. **Orden:** recomiendo completar primero 3.2-A y 3.2-B con pruebas aisladas; 3.2-C queda bloqueado por la implementación de Authentication/Identity Authority.

## 10. Fuera de alcance explícito

- Implementación de login/password, Argon2id, sesiones o bootstrap admin.
- Activación de Recovery Gate.
- Modificaciones de base de datos productiva.
- Cambios de host, Docker, Broker, mounts o systemd.
- Escritura de workspace, shell, ejecución de Skills o runtime conectado.
- Multi-nodo, almacenamiento compartido o fencing distribuido.


## 11. Registro de aprobación e implementación

El propietario aprobó las cinco decisiones de la sección 9:

1. Project–Environment muchos-a-muchos mediante `atlas_project_environments`.
2. Un único `owner_user_id` canónico por workspace en el perfil inicial.
3. `root_ref` simbólico en SQLite, resuelto posteriormente por configuración confiable del despliegue.
4. Capacidades protegidas de consola deshabilitadas hasta disponer de autenticación verificable operacional.
5. Orden de implementación 3.2-A, 3.2-B y 3.2-C.

La primera implementación usa `mount:<id>` como formato de `root_ref`. El detalle del esquema v18, repositorio, UoW y pruebas añadidas está en `cycle-3-2-a-workspace-registry-implementation.md`. La implementación no se considera validada hasta ejecutar las pruebas en Debian.
