# Decisión arquitectónica: imagen Linux autónoma para desplegar Atlas

> Estado: **ADOPTADA**
> Fecha: 17 de noviembre de 2026.
> Repositorio: `yon30c/atlas`.
> Rama de registro: `feature/terminal-commands`.
> Alcance: dirección objetivo de despliegue; no autoriza cambios en el host ni constituye una implementación de despliegue.

## 1. Decisión

Atlas tendrá como objetivo de despliegue una **imagen Linux autónoma distribuida como imagen OCI compatible con Docker**. Debian será la primera base candidata para esa imagen; la selección definitiva de distribución, versión, digest y estrategia de construcción se hará en una fase de implementación y validación.

La imagen contendrá el entorno de ejecución y las dependencias propias de Atlas. No se considera que una imagen de contenedor sea una máquina virtual ni una frontera de seguridad suficiente por sí sola: el aislamiento dependerá también del usuario del proceso, capacidades, namespaces, filesystem, mounts, red, seccomp/AppArmor y configuración del runtime.

Esta decisión define el destino arquitectónico. El desarrollo funcional continúa en el entorno actual hasta que exista un plan de migración probado.

## 2. Principios obligatorios

1. **Independencia del usuario anfitrión.** Atlas no debe necesitar ejecutarse como `greed`, ni inferir identidad humana a partir del UID/GID del host o del contenedor.
2. **Identidad de producto.** `UserId`, Identity Authority, CAM, Projects y Environments conservan la autoridad dentro de Atlas. La autenticación de una persona y la identidad técnica del proceso son conceptos distintos.
3. **Identidad de ejecución separada.** El proceso Atlas Runtime usará una identidad técnica dedicada dentro del contenedor, sin privilegios administrativos innecesarios. Esta identidad no es automáticamente un actor autorizado de Atlas.
4. **Acceso mediado al host.** Los archivos, directorios, servicios y recursos anfitriones solo serán accesibles mediante mounts explícitos y contratos/adaptadores controlados, con propiedad, alcance y permisos verificados.
5. **Broker independiente.** Atlas Core/Runtime no recibe acceso directo al socket Docker ni privilegios root del host. Atlas Broker continúa siendo una frontera independiente de ejecución; CAM decide y el Broker aplica el contrato técnico autorizado.
6. **Persistencia fuera del ciclo de vida de la imagen.** Bases de datos, conversaciones, estado, memoria, configuración durable, backups y artefactos que deban sobrevivir a recreaciones del contenedor residirán en volúmenes/directorios persistentes explícitos o servicios externos. La imagen y la capa efímera del contenedor no serán la fuente durable.
7. **Configuración y secretos externos.** Credenciales, claves, tokens y configuración específica del entorno no se incorporan a la imagen. Se inyectan mediante mecanismos de configuración/secretos con permisos restringidos.
8. **Configuración portable.** Rutas, endpoints, directorios de datos, proveedor LLM y límites de recursos deben configurarse explícitamente; no se asumirán rutas personales ni servicios disponibles en loopback del host.
9. **Mínimo privilegio y aislamiento por defecto.** El contenedor no se ejecutará privilegiado, no montará el filesystem del host de forma amplia y no recibirá `docker.sock`. Los mounts y capacidades se limitarán al mínimo requerido.
10. **Despliegue reproducible.** La imagen deberá construirse desde fuentes versionadas, con dependencias fijadas, identificación por digest, procedencia y proceso verificable de actualización/rollback.

## 3. Topología objetivo

- **Host Linux (primera implementación: Debian):** sistema operativo, Docker Engine/rootless runtime, almacenamiento persistente y servicios anfitriones expresamente aprobados.
- **Atlas Runtime (imagen Linux):** Atlas Core, Assistant, composición de aplicación y los componentes de producto que se integren progresivamente. La composición concreta se definirá por fases; esta decisión no afirma que todos esos dominios estén ya operativos.
- **Atlas Broker (servicio independiente):** frontera controlada para lifecycle y recursos de contenedores. Mantiene su socket/IPC y su identidad técnica actuales salvo una decisión posterior explícita. Runtime no obtiene acceso directo al socket Docker.
- **Workspaces y entornos de ejecución:** recursos separados y montados/entregados bajo contratos explícitos. No se presume que el workspace del host tenga la misma ruta dentro del contenedor.
- **Persistencia:** almacenamiento durable separado de la imagen; cada dominio deberá documentar su ruta, propietario, backup, recuperación y migración.

## 4. Impacto sobre lo ya desarrollado

La decisión **no invalida ni exige reescribir** los contratos de identidad, CAM, Grants, Projects/Environments, los servicios de workspace, el protocolo de escritura ni el gate local read-only de Cycle 3.1. Esas piezas son mayormente independientes del formato de despliegue y deben conservarse.

Sí introduce condiciones de integración que deberán abordarse antes de declarar el despliegue autónomo:

| Área existente | Impacto / acción futura |
|---|---|
| Identity Authority y `UserId` canónico | Reutilizar sin vincular identidad humana al UID Linux. Definir un mecanismo de autenticación confiable para la consola/runtime. |
| `LocalConsoleRequestFactory` | Sigue sin ser fuente de identidad autorizada. Cycle 3.2 debe resolver el contexto canónico sin depender de la identidad del proceso. |
| Projects/Environments y workspace ownership | Cycle 3.2 debe resolver rutas/configuración confiables y ownership; el path dentro del contenedor puede diferir del path anfitrión. |
| `LocalWorkspaceAdapter` | Sus controles de rutas relativas, traversal y symlinks siguen siendo útiles. La raíz física debe proceder de configuración confiable y de un mount explícito, no del modelo ni de una ruta personal implícita. |
| SQLite y UoW de Cycle 3.1 | La garantía demostrada es local a la base/archivo SQLite y a la misma UoW. El primer despliegue debe mantener una composición/proceso compatible; no asumir que SQLite sobre filesystem de red, múltiples réplicas o múltiples contenedores ofrece las mismas garantías. |
| Conversaciones | La ruta predeterminada `~/.local/state/atlas/conversations.sqlite3` cae en el filesystem del contenedor si no se configura persistencia. Debe mapearse a almacenamiento durable explícito antes de recrear contenedores. |
| Backups/exportaciones | Definir destinos persistentes y política de restauración fuera de la capa efímera; no restaurar automáticamente proyectos o Skills. |
| Ollama | `127.0.0.1:11434` dentro del contenedor apunta al propio contenedor. Si Ollama permanece en el host u otro servicio, el endpoint deberá configurarse mediante una ruta de red controlada. No ampliar el binding de Ollama sin revisión. |
| Atlas Broker | Mantenerlo fuera de Atlas Runtime y conservar la mediación. Diseñar un contrato Core–Broker explícito; no compartir `docker.sock` con Atlas. |
| Bootstrap/PAM y privilegios locales | Los diseños existentes no se reinterpretan como autenticación automática del contenedor. La autenticación para el perfil desplegado requiere una decisión específica y no debe depender inadvertidamente del PAM del host. |
| Tests y harnesses locales | Seguirán siendo válidos como evidencia de comportamiento de dominio. Añadir posteriormente pruebas de imagen, mounts, persistencia, aislamiento, red, reinicio y recuperación. |

## 5. Relación con Cycle 3.2

Cycle 3.2 continúa siendo la siguiente acción funcional. Su contrato debe ser agnóstico al despliegue y resolver:

- identidad canónica de consola/usuario, separada de UID/GID del proceso;
- proyecto y entorno activos, resueltos desde fuentes confiables;
- workspace registrado, raíz configurada, propiedad y límites de acceso;
- rechazo de identidad sintética o contexto incompleto;
- comportamiento fail-closed cuando no pueda verificarse identidad, proyecto, entorno o workspace.

La implementación puede seguir ejecutándose en Debian actual. No es necesario construir la imagen Linux para completar Cycle 3.2.

## 6. Alcance excluido y protecciones

Esta decisión no autoriza ni implica:

- quitar `sudo` a `greed`;
- modificar sudoers, PAM, usuarios, grupos, systemd, SSH, Docker Engine/rootless daemon, sockets o permisos del host;
- instalar paquetes o crear/migrar servicios;
- desplegar o reconstruir contenedores en el servidor;
- montar `/home/greed`, el filesystem raíz o `docker.sock` dentro de Atlas;
- ejecutar Atlas como root o en modo privileged;
- mover Atlas Broker dentro de la imagen;
- migrar bases, workspaces o datos existentes;
- declarar aislamiento, portabilidad o recuperación hasta probarlos en la imagen real.

Cualquier cambio de infraestructura requerirá una propuesta y autorización explícitas, con inspección previa y pasos reversibles.

## 7. Etapas futuras de adopción

1. **Inventario de dependencias de despliegue:** rutas, archivos, endpoints, puertos, variables, servicios externos, procesos y permisos realmente usados.
2. **Contrato de configuración/runtime:** definir directorios de estado/configuración/cache, health checks, señales de parada, logging, usuario técnico y endpoints.
3. **Persistencia y workspace:** definir mounts exactos, ownership, permisos, backup, restore y límites de acceso.
4. **Construcción reproducible:** Dockerfile, dependencias fijadas, usuario no root, filesystem mínimo, health check, SBOM/procedencia y digest.
5. **Entorno de prueba aislado:** validar arranque, conversación, SQLite, persistencia tras recreación, Ollama, Broker, mounts y aislamiento sin tocar el despliegue actual.
6. **Pruebas de seguridad y recuperación:** comprobar denegación de mounts no autorizados, acceso a Docker, escalada, red, reinicio, corrupción, backup/restore y resultados inciertos.
7. **Migración controlada:** solo tras superar criterios de aceptación, con rollback probado y autorización expresa.

## 8. Criterio de aceptación del objetivo

La imagen solo se considerará un destino de despliegue validado cuando pueda iniciarse en un host limpio con configuración documentada, operar sin depender de la cuenta personal del host, conservar los datos requeridos tras recreación, acceder exclusivamente a workspaces autorizados, comunicarse con Broker/LLM mediante interfaces explícitas y superar pruebas de aislamiento, recuperación y actualización.

Hasta entonces, el estado es **decisión arquitectónica adoptada; implementación y validación de despliegue pendientes**.
