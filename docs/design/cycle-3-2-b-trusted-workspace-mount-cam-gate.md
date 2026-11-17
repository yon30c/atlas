# Cycle 3.2-B — Trusted Workspace Mount Resolver y CAM Gate

**Estado:** implementación publicada y validada localmente en Debian por el propietario.
**Base:** rama Cycle 3.2-A, commit `9ce3a4875b09888f6b3e9867df37fadd0875f55d`.
**Rama de trabajo:** `feature/cycle-3-2-b-trusted-workspace-mount-cam-gate`.
**No habilita la consola ni capacidades protegidas.**

## 1. Objetivo

Cerrar la brecha entre el registro canónico introducido en 3.2-A y el acceso físico al workspace. El caller solo puede identificar un `workspace_id` y una ruta relativa dentro de ese workspace. Nunca puede elegir una ruta física, un mount ni el propietario efectivo.

La cadena de confianza requerida es:

1. La frontera confiable entrega un `OperationContext`; esta fase no lo crea ni autentica al actor.
2. Identity Authority confirma que el UserId y la Identity del contexto coinciden con el usuario canónico.
3. El registro canónico devuelve el Workspace.
4. El gate comprueba owner, Project, Environment, estado del Workspace y asociación Project–Environment activa.
5. El resolver interpreta el `root_ref` simbólico usando exclusivamente mounts inyectados por composición confiable del despliegue.
6. CAM evalúa el Grant exacto para actor, owner, Project, Environment, acción y recurso.
7. Solo después de un ALLOW se crea el adaptador de filesystem confinado a la raíz resuelta y se ejecuta la lectura/listado, manteniendo la UoW abierta.

Cualquier ausencia, discrepancia, estado no activo o error de resolución termina en denegación; nunca hay fallback a rutas o workspaces estáticos.

## 2. Contrato de mounts confiables

Introducir un puerto pequeño, independiente del host:

- Entrada: un `root_ref` simbólico del registro canónico.
- Salida: una raíz física absoluta, canónica y existente.
- La implementación concreta recibe un mapa de configuración confiable `mount_id -> absolute_path` en su constructor.
- No lee rutas del request, del plan, de `OperationContext`, de la base de datos aparte de `root_ref`, ni de variables ordinarias controladas por el caller.
- No crea directorios ni modifica permisos.

### Formato v1

`root_ref = mount:<mount_id>`

`mount_id` debe cumplir `[a-z0-9][a-z0-9._-]{0,63}`. Rechazar referencias vacías, mayúsculas, separadores, rutas, URI, espacios, NUL y cualquier formato distinto. No normalizar silenciosamente.

Cada ruta de mount configurada debe:
- ser absoluta;
- existir al construir la composición;
- resolver estrictamente a sí misma (sin symlink en la raíz ni alias no canónico);
- ser un directorio real;
- no ser una ruta aportada por el usuario.

El resolver vuelve a comprobar la raíz al resolver cada referencia para detectar sustitución, desaparición o cambio por symlink después del arranque. Un mount desconocido o inválido produce denegación.

No se permiten aliases implícitos, expansión de variables, `~`, rutas relativas, URI, concatenación de `mount_id` con rutas ni fallback a un workspace anterior.

## 3. Gate CAM: validaciones canónicas

Dentro de la misma `SQLiteLocalAuthorityUnitOfWork`:

1. Validar identidad USER activa y no delegada como hoy.
2. Leer el usuario por `context.user_id`; exigir coincidencia exacta de `user_id` e Identity con `context.actor`.
3. Leer `WorkspaceRecord` por el `workspace_id` de la intención; exigir que exista y esté `ACTIVE`.
4. Exigir que `workspace.owner_user_id == canonical.user_id`.
5. Exigir que `context.project_id` y `context.environment` estén presentes y coincidan exactamente con el Project y Environment del Workspace.
6. Leer Project y Environment canónicos y exigir ambos `active`.
7. Leer la asociación exacta `(workspace.project_id, workspace.environment_id)` y exigir `ACTIVE`.
8. Construir `AuthorizationRequest` con owner y scope obtenidos del registro canónico, no de parámetros del caller.
9. Evaluar CAM contra Grants del owner canónico. Exigir ALLOW y conservar el Grant exacto coincidente.
10. Resolver `workspace.root_ref` mediante el resolver confiable.
11. Construir un adaptador local limitado a esa raíz y ejecutar la operación solicitada.
12. Devolver el resultado con el mismo binding de workspace/recurso y el Grant que autorizó.

El Grant existente mantiene su semántica exacta:
- `workspace.list`: recurso `workspace`, ID = `workspace_id`.
- `workspace.read`: recurso `workspace_file`, ID = serialización canónica `[workspace_id, relative_path]`.

No se amplían scopes, acciones ni capacidades. Un Grant de lectura no autoriza listado ni viceversa.

## 4. UoW y concurrencia

La UoW SQLite compartida permanece abierta durante la validación, CAM y operación filesystem, conservando el fencing actual frente a escritores SQLite de las autoridades canónicas. No se presenta como un lock del filesystem ni como un coordinador genérico de consistencia.

La resolución física ocurre después de CAM para evitar inspeccionar mounts para una operación no autorizada. La raíz se vuelve a validar al acceder. El adaptador local existente sigue siendo responsable de rechazar traversal, symlinks internos, archivos no regulares, binarios y archivos excesivos.

No introducir llamadas de red, Broker, shell, runtime, Skills, escritura ni mutaciones en este ciclo.

## 5. Límites de seguridad explícitos

- No autenticar ni inferir identidad desde UID/GID, `getuser()`, hostname, proceso o entorno.
- No aceptar `owner_user_id`, `project_id`, `environment`, `root_ref` ni ruta física como autoridad desde el plan/request.
- No conceder ni crear Grants.
- No convertir un `OperationContext` local no verificado en identidad autenticada.
- No conectar CLI, consola, runtime, Broker ni capacidades protegidas.
- No cambiar permisos del host, systemd, usuarios, sudoers, Docker ni base de datos productiva.
- No habilitar escritura, shell ni Skills.

## 6. Pruebas de aceptación

### Resolver
- Resuelve mount conocido a raíz canónica.
- Rechaza formato de referencia inválido, mount desconocido y configuración vacía.
- Rechaza rutas relativas, inexistentes, no directorio y symlink/alias.
- Detecta que la raíz configurada fue sustituida o dejó de ser canónica.
- No acepta una ruta física como `root_ref`.

### Gate / registro
- Lista/lee solo un workspace activo propiedad del usuario canónico.
- Rechaza workspace inexistente, suspendido o disabled.
- Rechaza owner distinto aunque exista Grant para el actor.
- Rechaza Project/Environment distintos del Workspace.
- Rechaza Project o Environment inactivos.
- Rechaza asociación inexistente o suspendida.
- Rechaza mount desconocido antes de cualquier acceso.
- Rechaza ausencia de Grant, Grant expirado y Grant de otra acción/recurso.
- Confirma que el adaptador/filesystem no se invoca ante cualquier denegación.
- Mantiene la UoW activa durante la operación autorizada.
- Conserva todas las pruebas existentes de traversal y symlinks del adaptador local.

### Integración
- Pruebas unitarias focalizadas del resolver y del gate.
- Suite completa: `python -m unittest discover -s tests -t tests -v` — **1,218 tests, OK**.
- Compilación: `python -m compileall -q src tests` — **EXIT_CODE=0**.
- Checkout validado: rama `feature/cycle-3-2-b-trusted-workspace-mount-cam-gate`, commit `260043ff16d0eb804691438354bf28491211bc48`, árbol de trabajo limpio.

## 7. Implementación inicial publicada

- `TrustedWorkspaceMountResolver` resuelve exclusivamente `mount:<id>` desde un mapa inyectado por composición confiable. Valida IDs, rutas absolutas, existencia, directorio real y canonicalidad al construir y al resolver.
- `WorkspaceCapabilityExecutionService` ya no usa mapas estáticos de `workspace_id -> path`; carga el Workspace y la asociación desde la UoW canónica, valida owner/scope/estados y Grant exacto, y solo entonces resuelve el mount y construye el adaptador local confinado.
- Se actualizaron pruebas de ejecución para crear asociación y workspace canónicos, y cubrir owner distinto, ámbito distinto, workspace suspendido, asociación suspendida y mount desconocido.
- Se añadieron pruebas unitarias del resolver para configuración inválida, referencias inválidas, symlink de raíz y sustitución posterior.

**Validación local recibida:** el propietario ejecutó la suite completa en Debian (`Ran 1218 tests in 12.409s`, `OK`) y `python -m compileall -q src tests` (`EXIT_CODE=0`). Las pruebas focalizadas no se reportaron por separado; la suite completa sí pasó.

## 8. Criterio de salida

3.2-B se considera validada cuando la suite completa pasa en el checkout local del propietario y `compileall` finaliza sin errores. La validación recibida cumple ambos requisitos.

La implementación de 3.2-B no habilita la consola. La activación de capacidades protegidas sigue bloqueada hasta que la autenticación nativa y la frontera de sesión verificada estén implementadas y probadas en 3.2-C.

## 9. Decisiones aplazadas

- Carga/recarga dinámica de configuración de mounts y su política de permisos.
- Montajes múltiples por workspace, bind mounts y namespaces.
- Resistencia completa a TOCTOU del filesystem mediante operaciones descriptor-relative/openat para cada componente de ruta.
- Coordinador general de invalidación/fencing.
- Sesiones autenticadas y composición de consola (3.2-C).
