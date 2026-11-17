# Atlas Workstation — entorno operativo aislado

> Estado: decisión arquitectónica aprobada por el propietario; diseño inicial, no implementado.
> Rama: feature/terminal-commands.
> Fecha: 16 de noviembre de 2026.
> Alcance: entorno de trabajo de Atlas en el servidor central, separado del sistema anfitrión y mediado por CAM.

## 1. Propósito

Atlas Workstation es el entorno operativo donde Atlas realiza trabajo sobre proyectos: inspeccionar y modificar archivos, ejecutar tareas de aplicación, utilizar herramientas autorizadas y recoger resultados verificables.

No es una segunda autoridad ni una consola root. Es una capacidad de ejecución confinada que recibe operaciones admitidas por los servicios de Atlas y devuelve resultados observables.

La idea de producto es que el propietario pueda solicitar, por ejemplo, «crea un proyecto y prepara una aplicación», y Atlas pueda organizar un workspace, utilizar herramientas permitidas, ejecutar pruebas y presentar el resultado sin trabajar directamente sobre el sistema anfitrión.

## 2. Decisión arquitectónica

Atlas se desplegará como servicio central en el servidor Debian del propietario. Atlas Workstation será un subsistema del servicio central, con entornos de ejecución separados por proyecto y tarea.

Principios obligatorios:

- **Separación del host:** las tareas de Atlas no se ejecutan directamente en el espacio de usuario del sistema anfitrión.
- **Autoridad central:** identidad, proyecto, entorno, Grants, aprobaciones, estado de tareas y auditoría permanecen bajo control de Atlas/CAM.
- **Mediación obligatoria:** el Assistant propone; los servicios de aplicación validan; CAM autoriza; un adaptador confinado ejecuta.
- **Aislamiento por proyecto:** los archivos, procesos y recursos de un proyecto no quedan disponibles automáticamente para otro.
- **Mínimo privilegio:** cada entorno recibe solo los directorios, capacidades, recursos y conectividad requeridos.
- **Resultados verificables:** Atlas informa el resultado real del adaptador; no confunde una propuesta, un proceso iniciado o un código de salida con la validación completa del trabajo.
- **Persistencia controlada:** los datos de proyecto sobreviven a la destrucción del entorno mediante almacenamiento asignado, no mediante el contenedor como única copia.
- **Trazabilidad:** cada operación se correlaciona con propietario, proyecto, entorno, tarea, plan, autorización y resultado.
- **Control humano:** las acciones que requieran aprobación siguen el flujo de aprobación; Workstation no puede autoaprobarse.

## 3. Modelo conceptual

~~~text
Clientes (terminal / web / móvil / portátil)
                    |
                    v
             Atlas Central
       Assistant / Planner / Scheduler
                    |
                CAM + Approval
                    |
           Application Services
                    |
          Workstation Coordinator
                    |
          Confined Execution Adapter
                    |
        +-----------+-----------+
        |                       |
        v                       v
  Project Workspace       Task Runtime
  persistent data         isolated process/container
        |                       |
        +-----------+-----------+
                    |
             Execution Result
                    |
             Audit / Task State
~~~

### 3.1 Atlas Central

Conserva la autoridad y coordina las operaciones. Los clientes no reciben acceso directo al host ni ejecutan operaciones del servidor por su cuenta.

### 3.2 Workstation Coordinator

Servicio de aplicación responsable de traducir una operación ya validada a una solicitud concreta del adaptador. Comprueba el binding exacto de tarea, proyecto, entorno, workspace y perfil de recursos.

No decide por sí solo permisos ni sustituye CAM. Tampoco acepta argumentos arbitrarios de shell construidos por el modelo.

### 3.3 Project Workspace

Directorio persistente asignado a un proyecto. Contiene únicamente los archivos que ese proyecto necesita. Su propietario canónico, ruta física y política de acceso se resuelven desde configuración/registro confiable, no desde rutas libres proporcionadas por el modelo o el cliente.

Los protocolos existentes de lectura y escritura de workspace se reutilizarán donde sus garantías sean suficientes. La escritura seguirá su protocolo de staging, commit y evaluación de recuperación; no se considerará autorizada por ejecutarse dentro de un contenedor.

### 3.4 Task Runtime

Entorno efímero donde se ejecuta una tarea. La primera implementación preferida será un contenedor Docker confinado, sujeto a la disponibilidad de una frontera de control segura. El entorno puede destruirse al terminar, mientras los datos persistentes autorizados permanecen en el Project Workspace.

## 4. Aislamiento del runtime

El perfil inicial de contenedor deberá aplicar, como mínimo, estas restricciones cuando el adaptador y la plataforma las soporten:

- Ejecutar como usuario no privilegiado y con UID/GID no root dentro del contenedor.
- Sistema de archivos raíz de solo lectura cuando sea viable.
- Eliminar todas las Linux capabilities y añadir únicamente las estrictamente necesarias.
- No usar privileged, host PID, host network ni host IPC.
- No montar el socket Docker, sockets del host, directorios personales ni rutas generales del sistema.
- Montar solo el workspace del proyecto y directorios explícitos de entrada/salida.
- Aplicar límites de CPU, memoria, procesos, almacenamiento y tiempo.
- Aplicar seccomp y controles adicionales disponibles, por ejemplo AppArmor.
- Deshabilitar red por defecto; cualquier excepción debe ser explícita, limitada y autorizada.
- No proporcionar secretos del host ni credenciales de otros proyectos.
- Separar logs y resultados de los archivos de entrada.
- Destruir el runtime al finalizar o vencer su lease, conservando solo los datos persistentes permitidos.

Los perfiles de recursos deben ser versionados y seleccionados por política. Una tarea no puede ampliar sus propios límites ni cambiar su perfil.

## 5. Relación con Docker y Atlas Broker

El acceso al daemon Docker puede equivaler a control privilegiado del host. Por ello:

- Assistant, agentes, Skills y contenedores de tareas nunca reciben acceso directo a docker.sock.
- No se añade el usuario técnico atlas, atlas-sandbox ni otro proceso de Atlas al grupo docker para resolver esta integración.
- El Broker puede evaluarse como frontera de operaciones estrechas y predefinidas, siempre que su API, perfiles, identidad del caller, validación de argumentos, límites y auditoría satisfagan el contrato de Workstation.
- No se presume que el Broker existente ya esté integrado con Atlas ni que su acceso actual autorice operaciones de Workstation.
- Si no existe una frontera de control adecuada, el adaptador de contenedores permanece deshabilitado; no se sustituye por llamadas libres a Docker desde Python.

La decisión de usar Docker como mecanismo de aislamiento no concede autoridad para administrar contenedores al modelo ni a los procesos de ejecución.

## 6. Terminal y herramientas

Atlas podrá disponer de una terminal dentro de cada entorno de tarea. Esa terminal pertenece al runtime confinado, no al host.

La terminal no se expondrá inicialmente como una capacidad genérica equivalente a «ejecuta cualquier comando». La ejecución debe partir de tareas de aplicación definidas y perfiles de herramientas permitidas. Se podrá añadir un intérprete de comandos limitado más adelante solo con una política explícita de comandos, argumentos, directorios, entorno, red, duración y recursos, además de autorización y auditoría por operación.

Las Skills se instalarán y ejecutarán dentro de límites compatibles con su clasificación de riesgo. Una Skill no puede modificar la configuración de seguridad del runtime, concederse permisos, acceder a otros workspaces ni comunicarse directamente con el daemon Docker.

## 7. Ciclo de vida de una tarea

1. Assistant interpreta la solicitud y prepara un plan estructurado.
2. La aplicación valida que cada paso corresponda a una capacidad conocida.
3. Se resuelven identidad, proyecto, entorno y workspace canónicos.
4. CAM evalúa el Grant exacto y las restricciones de contexto.
5. Si la política lo exige, se obtiene aprobación humana ligada a la operación exacta.
6. Scheduler/Task Manager registra la tarea y sus parámetros canónicos.
7. Workstation Coordinator solicita al adaptador un runtime con perfil previamente definido.
8. El adaptador monta únicamente los recursos asignados y ejecuta la tarea.
9. Se recogen salida, código de terminación, artefactos, métricas y errores con límites de tamaño.
10. La aplicación valida los resultados y registra el estado terminal o parcial.
11. El runtime se destruye; el workspace persistente se conserva según la política del proyecto.
12. Atlas comunica qué se hizo, qué se verificó y qué quedó pendiente.

Un timeout, desconexión o pérdida de respuesta no demuestra que la operación no haya ocurrido. Las operaciones con efectos necesitan identificadores idempotentes, estado durable y evaluación de recuperación antes de reintentarse.

## 8. Persistencia y límites entre proyectos

- Cada proyecto tiene un workspace persistente y una política de acceso.
- Cada tarea recibe solo los mounts requeridos; no se montan otros proyectos por comodidad.
- Los directorios temporales y caches se separan del workspace persistente.
- Los artefactos de salida se identifican y vinculan a la tarea que los produjo.
- El borrado de un proyecto debe coordinar tareas activas, runtimes, archivos, backups y auditoría; no equivale a borrar un directorio.
- Los paths físicos no se aceptan directamente del LLM como autoridad. Se derivan de registros y bindings confiables.
- Los cambios de configuración del workspace quedan fuera del alcance de una tarea ordinaria.

## 9. Observabilidad y recuperación

Cada ejecución debe registrar, como mínimo:

- task_id y operation_id;
- identidad canónica y sesión cliente;
- project_id, environment_id y workspace_id;
- capacidad, versión de perfil y versión de imagen;
- aprobación y evidencia de autorización aplicables;
- timestamps de admisión, inicio y finalización;
- estado de runtime y código de salida;
- referencias/digests de artefactos y logs;
- resultado de limpieza del runtime;
- diagnóstico de recuperación si el resultado es incierto.

Los logs deben limitar tamaño y duración, evitar secretos y tratar la salida del proceso como dato no confiable. Un resultado desconocido se clasifica como desconocido; no se transforma en fallo/no ejecución sin evidencia.

## 10. Alcance incremental

### Etapa W0 — Diseño y límites

Documentar el modelo, los perfiles, el límite Docker/Broker, los bindings de proyecto y los estados de tarea. No ejecutar contenedores ni cambiar el host.

### Etapa W1 — Workspace persistente

Completar el registro confiable de proyecto/entorno/owner y la resolución segura de workspace. Reutilizar los adaptadores existentes de lectura/escritura y sus pruebas. Mantener la ejecución de procesos deshabilitada.

### Etapa W2 — Contrato del adaptador de runtime

Definir un puerto de aplicación estrecho para crear, inspeccionar, detener y destruir un runtime de tarea con un perfil nombrado. Definir resultados tipados, idempotencia, límites y recuperación. Evaluar si Atlas Broker puede implementar ese contrato sin ampliar su autoridad.

### Etapa W3 — Runtime confinado de prueba

Implementar un perfil mínimo, sin red por defecto, no root, con recursos limitados y un workspace de prueba descartable. La integración debe tener pruebas de aislamiento, escape de rutas, denegación de mounts, límites y limpieza. No habilitar shell arbitrario.

### Etapa W4 — Tareas y herramientas

Conectar Scheduler/Task Manager a un catálogo cerrado de tareas y herramientas. Ejecutar una tarea reproducible de extremo a extremo, registrar progreso y recoger artefactos verificables.

### Etapa W5 — Terminal interactiva limitada

Solo después de validar W0–W4, considerar una terminal interactiva dentro del runtime. Su política debe limitar comandos, argumentos, entorno, red, duración, recursos y filesystem. No proporciona acceso al host.

### Etapa W6 — Experiencia multiplataforma

Presentar estado, logs filtrados, artefactos y solicitudes de aprobación a través de los clientes autenticados de Atlas. La interfaz es un cliente; no es una frontera de autoridad.

## 11. Fuera de alcance y prohibiciones

Este diseño no autoriza:

- shell arbitrario en el host;
- ejecución como root;
- acceso directo a Docker API/socket desde Assistant, agentes o Skills;
- montaje de /, /home, /var/run u otros directorios generales del host;
- acceso cruzado entre workspaces;
- red abierta por defecto;
- instalación de paquetes en el host para satisfacer una tarea;
- elevación de permisos desde una Skill o un contenedor;
- conexión del runtime a CLI antes de resolver bootstrap, identidad canónica, ownership y CAM;
- abrir Recovery Gate ni modificar autoridad mediante SQL.

La pausa de hardening avanzado de Fase 3 no cambia estas prohibiciones mínimas.

## 12. Relación con la hoja de ruta

Atlas Workstation es una base operativa transversal para la Fase 4 de capacidades del Assistant y los ciclos de ejecución de tareas descritos en functional-test-roadmap.md. No sustituye el trabajo inmediato del Ciclo 3.2: antes de conectar el runtime se debe resolver el contexto canónico de consola, bootstrap confiable, proyecto/entorno y ownership de workspaces.

El primer hito de Workstation es de diseño (W0). No se declara implementado ningún runtime ni se cambia el estado de los adaptadores actuales por publicar este documento.

## 13. Criterios de aceptación de la primera prueba

- Una tarea puede ejecutarse solo dentro de un runtime asignado y un workspace de prueba.
- El contenedor no puede leer directorios del host fuera de sus mounts explícitos.
- Un proyecto no puede leer ni modificar el workspace de otro proyecto.
- El proceso no tiene acceso al socket Docker ni privilegios root del host.
- Red, CPU, memoria, procesos, almacenamiento y duración están limitados.
- El usuario puede consultar estado y resultado real de la tarea.
- Una interrupción produce estado recuperable/indeterminado, no un falso éxito ni un reintento ciego.
- Los logs y artefactos quedan vinculados a la tarea y no filtran secretos.
- La suite de pruebas incluye denegaciones y casos adversariales del aislamiento.

La aprobación de estos criterios requiere evidencia de pruebas locales. La documentación por sí sola no los satisface.
