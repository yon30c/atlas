# Decisión arquitectónica: autenticación nativa y portabilidad entre máquinas

> Estado: **ADOPTADA COMO DIRECCIÓN DE PRODUCTO Y REQUISITO ARQUITECTÓNICO**.
> Fecha: 17 de noviembre de 2026.
> Repositorio: `yon30c/atlas`.
> Rama de registro: `feature/terminal-commands`.
> Alcance: define objetivos y restricciones para Cycle 3.2 y el futuro despliegue portable. No habilita autenticación ni constituye una implementación.

## 1. Decisión

Atlas debe poder instalarse y ejecutarse en otra máquina sin depender de la identidad Linux, el nombre de host, las rutas personales, el hardware, los servicios locales implícitos ni los secretos de la máquina de desarrollo original.

La autenticación de personas será una capacidad propia del producto Atlas, separada de las cuentas del sistema operativo. La instalación inicial tendrá un procedimiento de bootstrap controlado para crear el primer usuario canónico. El inicio de sesión no concederá permisos automáticamente: CAM seguirá evaluando cada operación protegida.

Atlas se distribuirá como imagen Linux autónoma compatible con OCI/Docker, conforme a `linux-image-deployment-decision.md`. La imagen será reproducible y separada de los datos persistentes y de la configuración específica de cada instalación.

La portabilidad de una instalación y la migración de sus datos son requisitos explícitos. No se declara todavía soportada la ejecución activa de varias réplicas ni el uso concurrente de SQLite desde múltiples hosts.

## 2. Objetivos de portabilidad

### 2.1 Instalación independiente

Una instalación limpia debe poder realizarse en un host compatible siguiendo documentación versionada y sin requerir:

- un usuario Linux con nombre concreto, como `greed`;
- un UID/GID concreto del host;
- un hostname o dirección IP fija;
- una ruta personal como `/home/greed`;
- un directorio de proyecto preexistente en el host;
- un modelo LLM, proveedor o endpoint codificado en el paquete;
- credenciales, claves o tokens incluidos en la imagen;
- acceso directo al socket Docker del host desde Atlas Runtime;
- datos o configuración residuales de otra instalación.

El host debe satisfacer únicamente los requisitos documentados de runtime, almacenamiento, red y recursos. La distribución base, arquitectura de CPU y versiones compatibles se fijarán en la fase de empaquetado y pruebas.

### 2.2 Migración entre máquinas

Debe existir en una fase posterior un procedimiento soportado para trasladar una instalación a otro host y recuperar, según el alcance aprobado:

- usuarios y sus identidades canónicas;
- configuración durable de Atlas;
- proyectos, entornos y registros de workspace;
- conversaciones y estado de tareas;
- memoria y sus metadatos cuando su persistencia esté implementada;
- registros de auditoría y referencias de procedencia;
- Skills aprobadas y sus manifiestos, sin reactivar automáticamente contenido ejecutable;
- referencias a secretos y configuración externa, sin exportar secretos por accidente.

La migración debe incluir inventario, exportación, manifiesto versionado, integridad, compatibilidad de esquema, restauración a destino, verificación y activación deliberada.

No se debe afirmar que un dominio es portable hasta que su persistencia, exportación, restauración y pruebas estén implementadas. Los datos que hoy no tengan persistencia durable quedan expresamente fuera de cualquier garantía de migración.

### 2.3 Separación de instalaciones

Cada instalación tendrá una identidad técnica de instalación propia, generada mediante un procedimiento confiable. Esta identidad sirve para diagnóstico, correlación y configuración local; **no es la identidad humana de un usuario Atlas** y no concede permisos.

Los IDs canónicos de usuarios e identidades no se derivan de:
- hostname;
- dirección IP o MAC;
- número de serie o hardware;
- UID/GID;
- nombre de usuario del host;
- ruta de instalación;
- identificador del contenedor.

Clonar una imagen no debe clonar secretos ni convertir dos instalaciones en la misma instalación lógica. Los secretos y el identificador de instalación se generan o inyectan por instalación, fuera de la imagen.

## 3. Autenticación nativa de Atlas

### 3.1 Responsabilidades

Se mantienen tres autoridades separadas:

1. **Authentication Authority:** verifica las credenciales nativas de Atlas y administra el ciclo de vida de autenticadores y sesiones.
2. **Identity Authority:** resuelve la cuenta autenticada hacia la relación canónica `UserId`–`Identity(USER)` y emite la evidencia de identidad verificada conforme al contrato vigente.
3. **CAM:** evalúa actor, acción, recurso, scope, revisiones, Grants, proyecto, entorno y delegación. La autenticación no concede permisos.

La consola y cualquier interfaz futura deben consumir estos servicios a través de una frontera confiable. No pueden construir por sí mismas un contexto verificado ni aceptar un `UserId` del caller como prueba de identidad.

### 3.2 Método nativo inicial

El primer método de autenticación será una cuenta local administrada por Atlas, con identificador de inicio de sesión y contraseña.

- El identificador de inicio de sesión es un nombre de acceso, no un UserId ni una prueba de identidad.
- El identificador de acceso no se utilizará para fusionar cuentas ni para inferir propiedad.
- Las contraseñas se almacenarán únicamente mediante un esquema de derivación de contraseña resistente a ataques offline, preferentemente Argon2id con parámetros revisables y versionados.
- Nunca se almacenarán contraseñas en texto plano, logs, journal, eventos, backups legibles ni manifiestos.
- Se aplicarán límites y demoras ante intentos repetidos, respuestas que no revelen si una cuenta existe y controles contra enumeración.
- Los cambios de contraseña, suspensión, revocación y recuperación deben invalidar las sesiones o evidencias afectadas conforme a una política explícita.
- El formato de credenciales incluirá versión y parámetros para permitir actualización controlada del esquema de hash.
- No se implementarán algoritmos criptográficos propios.

Este método nativo deberá integrarse con la semántica de issuer, binding y `VerifiedIdentityContext` de B1-B-03A/B/C/D. No se creará un camino paralelo que emita contextos incompatibles. La definición del issuer nativo, su subject opaco, la verificación de credenciales y la evidencia requerida se documentarán antes de implementar el flujo.

### 3.3 Sesiones

La sesión autenticada será distinta de la identidad persistente:

- token de sesión opaco, aleatorio y de entropía suficiente;
- el token en claro solo se entrega al cliente en el momento necesario;
- persistencia de un digest seguro del token, nunca del token reutilizable;
- expiración explícita, revocación, rotación y política de renovación;
- validación de estado de cuenta, identidad y revisiones relevantes;
- invalidación ante cambio de credenciales, revocación, suspensión o evento de seguridad aplicable;
- protección contra replay y fijación de sesión;
- cookies seguras y protección CSRF si se introduce una interfaz web;
- transporte cifrado cuando la consola se exponga por red.

Los TTL, reautenticación reciente, límites de intentos y política de renovación deben fijarse por tipo de operación antes de producción; no se inventa un TTL universal.

### 3.4 Bootstrap de primera instalación

La primera cuenta no se creará automáticamente a partir de Linux ni de datos de máquina.

El bootstrap deberá:
- ejecutarse solo cuando la instalación se encuentre en estado inicial y sin propietario/admin inicial;
- requerir una prueba de bootstrap de un solo uso, generada fuera de la imagen y entregada al operador por un canal controlado;
- almacenar solo un digest verificable de esa prueba;
- expirar y consumirse atómicamente;
- crear UserId e Identity(USER) en la misma UoW que la cuenta nativa y su vínculo canónico;
- registrar auditoría mínima del alta;
- cerrarse irreversiblemente al completar el alta inicial;
- no exponer una ruta alternativa para recrear el primer administrador.

El bootstrap no será una contraseña universal, valor por defecto, variable de entorno permanente ni secreto embebido en Dockerfile, imagen o repositorio. El mecanismo de recuperación posterior será independiente y requerirá una política aprobada.

### 3.5 Varios usuarios

El diseño soportará múltiples usuarios Atlas desde el primer modelo de autenticación, aunque la primera instalación sea administrada por una sola persona.

No se asumirán roles ni permisos por el orden de creación, por ser el primer usuario o por poseer el host. Los privilegios iniciales se asignarán mediante un procedimiento explícito de bootstrap y una política CAM verificable.

## 4. Configuración y persistencia portable

La imagen OCI contendrá código y dependencias fijadas, no datos de usuario ni secretos.

Cada instalación definirá explícitamente:
- directorio persistente de datos;
- directorio de configuración;
- directorio temporal/cache;
- ubicación de backups/exportaciones;
- endpoint y configuración del proveedor LLM;
- configuración de red y exposición de consola;
- workspaces disponibles y sus mounts;
- referencias a secretos;
- límites de recursos y política de logging.

Las rutas internas del contenedor no se supondrán iguales a las rutas del host. Los paths de host se entregan mediante mounts y configuración confiable; nunca los decide el modelo.

La persistencia de SQLite será local a un único archivo y a una composición compatible con sus garantías transaccionales. No se montará la misma base SQLite para escritura concurrente desde varios hosts ni se afirmará que un filesystem de red o múltiples réplicas mantienen las garantías demostradas.

La elección futura de otra base de datos para escenarios multiinstancia requerirá diseño, migración y pruebas propios; no se presenta como una sustitución transparente de SQLite.

## 5. Secretos y material criptográfico

- Los secretos no forman parte de la imagen ni del repositorio.
- Cada instalación genera o recibe sus propias claves y credenciales mediante un mecanismo documentado.
- Los secretos persistentes deben sobrevivir a recreaciones del contenedor, pero no deben copiarse automáticamente al crear una instalación nueva.
- Las referencias a secretos pueden migrarse; el material secreto exige una decisión explícita de exportación, transferencia, rotación o regeneración.
- Las claves de cifrado y firma no se derivan de hostname, hardware, UID, ruta ni password del usuario.
- La pérdida de una clave debe tener un resultado documentado; no se debe fingir que una restauración de datos cifrados es posible sin ella.
- Las claves de instalación, credenciales de sesión y claves de firma tienen propósitos y ciclos de vida separados.
- Un backup cifrado no reemplaza la gestión independiente de claves necesarias para descifrarlo.

La rotación y recuperación de claves, anti-rollback y perfil de confianza ANCHORED continúan sujetos a sus diseños específicos. El perfil LOCAL no debe presentarse como resistente a restauración de snapshots antiguos.

## 6. LLM y servicios externos

Atlas no debe asumir que Ollama está instalado en el mismo host, en el mismo contenedor o en `127.0.0.1`.

El proveedor LLM y su endpoint se configuran explícitamente. La conectividad, autenticación, TLS, timeouts y política de confianza se validan según el adaptador. La instalación debe poder cambiar de host o proveedor sin cambiar identidad canónica de los usuarios.

Atlas no instalará ni descargará modelos automáticamente salvo que exista un flujo de instalación explícito, aprobado y verificable.

Atlas Broker continúa como servicio independiente. Atlas Runtime no recibe root, modo privileged ni acceso directo a `docker.sock`. La relación con Broker se establece mediante un contrato autenticado y autorizado, no mediante confianza implícita en que ambos procesos estén en la misma máquina.

## 7. Migración y restauración entre hosts

El futuro formato de exportación deberá incluir como mínimo:
- versión de formato y versión de Atlas;
- identificador de origen no secreto;
- inventario de dominios y recursos incluidos/excluidos;
- versiones de esquema y migraciones;
- conteos y digests de integridad;
- referencias a configuración y secretos requeridos;
- advertencias de compatibilidad;
- dependencias externas no incluidas;
- instrucciones de restauración y verificación.

El proceso de destino debe:
1. verificar origen, integridad y compatibilidad;
2. restaurar primero en una ubicación aislada;
3. aplicar migraciones permitidas de forma controlada;
4. verificar relaciones canónicas, referencias, ownership y recursos;
5. reconciliar sesiones, credenciales, claves, revocaciones y estado de seguridad;
6. mantener deshabilitada la ejecución protegida hasta completar las comprobaciones requeridas;
7. requerir activación deliberada por un operador autorizado.

Las sesiones activas no se migrarán como credenciales reutilizables. Por defecto, se revocarán y los usuarios deberán autenticarse de nuevo en el destino.

La restauración no debe reactivar automáticamente Skills ejecutables, agentes, tareas pendientes, credenciales externas, mounts ni integraciones. Cada recurso ejecutable requiere reconciliación y aprobación según su política.

No se fusionarán dos instalaciones ni se combinarán identidades por coincidencia de atributos. La migración conserva los IDs canónicos del origen cuando la operación es una transferencia autorizada de esa instalación; la clonación para crear una instalación independiente requiere un procedimiento separado de identidad, ownership, secretos y recursos.

## 8. Alcance de concurrencia

Primera entrega:
- una instalación lógica;
- una instancia activa de Atlas Runtime para la base SQLite local;
- persistencia explícita y durable;
- despliegue recreable en el mismo host;
- instalación limpia en otro host;
- migración controlada de una instalación a otro host, cuando el ciclo de backup/restore correspondiente esté implementado y validado.

Fuera de alcance hasta diseño independiente:
- active-active o múltiples réplicas escribiendo la misma base;
- SQLite compartida por red;
- coordinación distribuida de sesiones, locks, tareas y autoridad;
- alta disponibilidad y failover automático;
- sincronización bidireccional de instalaciones independientes.

## 9. Impacto sobre Cycle 3.2

Cycle 3.2 debe ser agnóstico al host y al despliegue. Debe resolver:
- identidad autenticada desde Authentication Authority, sin usar `getuser()`, UID/GID ni hostname;
- construcción confiable de `VerifiedIdentityContext` y `OperationContext`;
- selección de proyecto y entorno desde fuentes canónicas;
- workspace registrado con owner, proyecto, entorno y raíz confiable;
- rutas lógicas independientes de los paths físicos del host;
- denegación ante identidad, sesión, proyecto, entorno o workspace no verificables.

El registro de proyectos, entornos y workspaces debe poder persistir y exportarse sin incorporar rutas personales de la máquina original como supuestos universales. El path físico de destino se configura y verifica durante instalación/restauración.

La consola puede ofrecer conversación no protegida antes del login si la política lo permite, pero no ejecutará capacidades protegidas ni consultará datos privados con una identidad sintética.

## 10. Pruebas de aceptación futuras

### Instalación
- instalación limpia en dos hosts distintos;
- usuario Linux y UID/GID diferentes;
- hostname, rutas y direcciones diferentes;
- imagen recreada sin perder datos persistentes;
- ausencia de secretos dentro de imagen, capas, logs y repositorio;
- configuración faltante o inválida produce fallo seguro.

### Autenticación
- bootstrap único, expirable y consumible una sola vez;
- no bootstrap desde identidad Linux;
- credencial inválida, sesión expirada, revocada o manipulada;
- throttling y respuesta resistente a enumeración;
- cambio de contraseña invalida sesiones conforme a política;
- cuenta suspendida/revocada no obtiene contexto;
- no emisión de VerifiedIdentityContext por consola o caller;
- CAM deniega aunque exista sesión válida si falta Grant o scope.

### Portabilidad
- exportación e importación en hosts diferentes;
- IDs canónicos preservados en una transferencia autorizada;
- paths de workspace remapeados explícitamente;
- versiones incompatibles rechazadas o migradas con procedimiento aprobado;
- integridad de archivos, DB y manifiesto;
- secretos ausentes o claves perdidas tratados explícitamente;
- sesiones revocadas al migrar;
- Skills y tareas ejecutables no se reactivan automáticamente;
- recuperación interrumpida y reanudación segura;
- rollback probado antes de migración real.

### Aislamiento y runtime
- Runtime sin root, privileged ni Docker socket;
- mounts limitados a workspaces explícitos;
- proveedor LLM externo configurable;
- Broker independiente y acceso mediado;
- pruebas de reinicio, pérdida de servicio y resultados inciertos.

## 11. Exclusiones y límites

Esta decisión no autoriza:
- cambios en el host Debian actual;
- cambios de usuarios, grupos, sudoers, PAM, systemd, SSH o Docker;
- migrar datos reales;
- instalar paquetes o desplegar una nueva imagen;
- mover Atlas Broker;
- habilitar autenticación o bootstrap en producción;
- abrir Recovery Gate;
- habilitar ejecución protegida desde la consola;
- declarar migración, portabilidad de datos, alta disponibilidad o multiinstancia como implementadas.

Cada intervención de infraestructura o datos requerirá inspección, plan reversible y autorización explícita.

## 12. Criterio de aceptación del objetivo

Atlas cumplirá el objetivo de instalación portable cuando pueda instalarse desde una imagen versionada en un host limpio, completar bootstrap sin identidad Linux, autenticar usuarios propios, configurar explícitamente LLM/workspaces/persistencia, y operar bajo CAM sin depender de la máquina de desarrollo.

La portabilidad de datos se considerará cumplida únicamente cuando una instalación pueda exportarse, verificarse, restaurarse en otro host, reconciliar sus dependencias y reabrir operaciones protegidas tras superar todos los controles.

**Estado final:** dirección de autenticación nativa y portabilidad entre máquinas adoptada; contratos detallados, implementación, empaquetado, migración y pruebas permanecen pendientes.
