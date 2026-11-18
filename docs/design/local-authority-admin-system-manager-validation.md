# Validación de system manager para IPC administrativo de autoridad

**Estado:** protocolo de validación propuesto; pendiente de ejecución en VM desechable.  
**Fase:** 2.5.5.  
**Depende de:** PR #23–#26.  
**No aprobado para producción.**

## Objetivo

Extender la evidencia de la Fase 2.5.4 desde `systemd --user` al **system manager** y comprobar la frontera real entre:

- un frontend administrativo que se ejecuta como root;
- una unidad `.socket` gestionada por PID 1;
- un servicio activado que corre como la identidad dedicada `atlas-runtime`;
- un socket `AF_UNIX/SOCK_SEQPACKET` con credenciales de peer verificadas por el kernel.

La fase valida mecánica de systemd y permisos del host en un laboratorio desechable. No implementa un frontend privilegiado ni operaciones administrativas reales.

## Restricción de seguridad no negociable

Toda prueba de esta fase se ejecutará exclusivamente en una **VM desechable**, con snapshot recuperable, sin datos personales ni servicios Atlas, y con acceso a una consola de recuperación.

No ejecutar el protocolo en el Debian habitual del propietario. No reutilizar `/opt/atlas`, `/opt/atlas-broker`, `/var/lib/atlas`, bases SQLite existentes, usuarios Atlas existentes, sockets existentes ni unidades activas. No utilizar el host de desarrollo como sustituto de la VM.

La VM debe tener red deshabilitada durante las pruebas, salvo que el aprovisionamiento inicial requiera descargar paquetes. Registrar distribución, kernel y versión exacta de systemd.

## Modelo de identidad y rutas candidatas

Los siguientes valores son **solo fixtures de laboratorio**, no configuración aprobada:

| Recurso | Valor de laboratorio |
|---|---|
| Usuario de servicio | `atlas-runtime`, sin login |
| Grupo primario | `atlas-runtime` |
| Directorio de socket | `/run/atlas-authority-admin` |
| Propietario del directorio | `root:root` |
| Modo del directorio | `0700` |
| Socket | `admin.sock`, AF_UNIX/SOCK_SEQPACKET |
| Propietario del socket | `atlas-runtime:atlas-runtime` |
| Modo del socket | `0600` |
| Unidad socket | `atlas-authority-admin.socket` |
| Unidad service | `atlas-authority-admin.service` |
| Peer permitido por el prototipo | UID 0, derivado de `SO_PEERCRED` |

El directorio root-owned evita que el proceso de servicio pueda crear, sustituir o limpiar nombres en el directorio. El proceso recibe el descriptor abierto por systemd y no necesita buscar ni eliminar el pathname. Esta hipótesis debe probarse: no inferirla de la prueba `systemd --user`.

El UID 0 identifica el frontend del sistema operativo, no a un USER de Atlas ni a una persona autenticada. No otorga por sí solo autoridad de dominio.

## Preparación de la VM

1. Crear una VM nueva con Debian estable y systemd.
2. Tomar snapshot antes de instalar o modificar nada.
3. Registrar `uname -a`, `systemd --version`, `id`, `stat` y versión de Python.
4. Confirmar que no existe ninguna unidad, cuenta o ruta con los nombres de laboratorio.
5. Crear únicamente dentro de la VM el usuario/grupo de servicio dedicado, sin shell interactivo.
6. Crear el directorio de socket con propietario root y modo `0700`.
7. Confirmar que el servicio `atlas-runtime` no puede listar, crear ni eliminar entradas en ese directorio.
8. Mantener el laboratorio sin DB, sin migraciones, sin secretos y sin conexión a servicios reales.

Si cualquier nombre ya existe en la VM, detener la prueba y restaurar el snapshot. No adaptar ni reutilizar recursos preexistentes.

## Matriz de pruebas

### A. System manager y descriptor activado

- Instalar unidades temporales con nombres exclusivos del laboratorio.
- Configurar `ListenSequentialPacket=`, `Accept=no`, `SocketUser=atlas-runtime`, `SocketGroup=atlas-runtime` y `SocketMode=0600`. Ejecutar la matriz de lifecycle con `RemoveOnStop=no` y `RemoveOnStop=yes` en fixtures separados.
- El servicio debe usar `User=atlas-runtime`, `Group=atlas-runtime`, `NoNewPrivileges=yes`, `ProtectSystem=strict`, `ProtectHome=yes`, `PrivateTmp=yes`, `UMask=0077` y un conjunto mínimo explícito de descriptores.
- Validar `LISTEN_PID`, `LISTEN_FDS=1`, fd 3, familia AF_UNIX, tipo SOCK_SEQPACKET y nombre esperado.
- Verificar desde el servicio UID/GID efectivos, reales y guardados; capacidades; grupos suplementarios; descriptores abiertos; entorno y límites de recursos.
- Confirmar que el proceso no puede abrir el pathname por filesystem ni modificar el directorio padre, pero puede atender conexiones mediante el descriptor recibido.
- Ejecutar al menos dos activaciones sucesivas y verificar que el listener permanece gestionado por systemd.
- Separar la prueba de autorización del peer de la prueba de permisos del pathname. No se debe esperar que un cliente no privilegiado alcance `SO_PEERCRED` atravesando un directorio `0700` propiedad de root o conectando a un socket `0600` propiedad de atlas-runtime.
- **Fixture de autorización IPC:** crear un socket temporal dentro de un directorio temporal accesible para ambos clientes y con permisos de socket que permitan completar `connect()` (por ejemplo, directorio `0711` y socket `0666`, solo dentro del fixture desechable). Ejecutar un cliente root permitido y un cliente de UID no permitido; confirmar que el servidor obtiene `SO_PEERCRED` y rechaza el segundo antes de leer su paquete.
- **Fixture de permisos de producción:** mantener directorio `root:root 0700` y socket `atlas-runtime:atlas-runtime 0600`; confirmar que el cliente no privilegiado falla en el acceso filesystem antes de establecer la conexión. Registrar este resultado como control de permisos, no como prueba de rechazo por `SO_PEERCRED`.
- No relajar los permisos del fixture candidato de producción para hacer pasar la prueba de autorización. Las dos pruebas responden preguntas distintas y deben permanecer separadas.
- Verificar el timeout de lectura de una conexión que no envía paquete y el timeout de escritura cuando pueda inducirse de forma segura. El handler debe rechazar familias distintas de `AF_UNIX`, tipos distintos de `SOCK_SEQPACKET` y cualquier dato ancillary; el listener llamador debe imponer un límite explícito de conexiones/concurrencia.
- Comprobar que el servicio no hace bind, unlink, chmod ni shutdown sobre el listener heredado.

### B. Ownership y permisos

- Verificar con `stat` el propietario y modo del directorio y socket antes, durante y después de activar el servicio.
- Confirmar que un proceso no privilegiado no puede crear, renombrar, sustituir ni borrar entradas del directorio.
- Confirmar que el socket no queda accesible a otros usuarios.
- Confirmar que el proceso `atlas-runtime` no obtiene permisos adicionales por pertenecer a grupos inesperados.
- Inspeccionar el descriptor heredado y confirmar que el servicio no hereda descriptores no declarados.

### C. Colisiones y pathname

El hallazgo de Debian 13 / systemd 257.13 en la Fase 2.5.4 exige tratar esta sección como prueba de riesgo, no como supuesto aprobado.

- Usar exclusivamente un directorio temporal nuevo dentro de la VM y archivos sentinel descartables.
- Probar pathname ocupado por archivo regular, symlink, socket activo y socket stale.
- Capturar tipo, inode, propietario, modo y hash/contenido del sentinel antes y después de `systemctl start`.
- Registrar si systemd falla, reemplaza, altera o conserva el objeto; no asumir un comportamiento.
- Repetir solo tras restaurar el fixture exacto y verificar que el directorio temporal pertenece al harness.
- Nunca colocar fixtures de colisión en `/run`, `/var/lib`, rutas de producción o rutas de usuario.
- Si systemd modifica cualquier objeto preexistente, documentar la semántica observada y exigir que el diseño operativo elimine la posibilidad de colisión mediante directorio root-owned preaprovisionado, ruta exclusiva y comprobaciones previas. No afirmar que systemd garantiza no-reemplazo.

La prueba no debe borrar ni “limpiar” objetos cuya procedencia no pueda demostrar el harness.

### D. Ciclo de vida y recuperación

- Arrancar socket unit, conectar, comprobar activación y respuesta ping.
- Detener/reiniciar solo el service unit mientras el socket unit permanece activo; verificar nueva activación.
- Detener socket unit y service unit de forma coordinada.
- Comparar `RemoveOnStop=no` y `RemoveOnStop=yes` en dos ejecuciones independientes, cada una con directorio temporal recién creado.
- Para cada variante, registrar si el pathname permanece o desaparece al detener la unidad socket, si el servicio sigue activo y qué ocurre al iniciar de nuevo la unidad.
- Verificar si `RemoveOnStop=yes` elimina exclusivamente el socket que creó systemd y si el resultado cambia ante una ruta preexistente; nunca extrapolar de un solo tipo de fixture.
- Definir la política de cleanup y recuperación de socket stale según la evidencia. No permitir unlink manual o automático del daemon.
- Simular terminación abrupta del servicio, desconexión del cliente y paquete inválido.
- Confirmar que no queda un servicio huérfano ni un descriptor retenido inesperadamente.
- Restaurar snapshot al finalizar; no dejar unidades ni cuentas del laboratorio.

### E. Hardening y límites

- Validar `NoNewPrivileges`, `ProtectSystem`, `ProtectHome`, `PrivateTmp`, `RestrictAddressFamilies=AF_UNIX` si es compatible, `CapabilityBoundingSet=`, `AmbientCapabilities=`, `SystemCallFilter=` solo después de comprobar dependencias reales.
- No añadir reglas de syscall ni restricciones por intuición: registrar fallos y justificar cada excepción.
- Probar límites de memoria, tareas, archivos abiertos, tiempo de arranque y timeout por conexión. El prototipo de handler aplica un timeout por conexión configurable y acotado (default 5 s; máximo 60 s); el listener debe además imponer un máximo explícito de conexiones activas/aceptadas y una política de backpressure. Un timeout por conexión no sustituye un límite de concurrencia.
- Confirmar que el proceso no puede ejecutar comandos, abrir SQLite, escribir fuera de sus rutas permitidas ni acceder a Docker.
- Confirmar que ningún secreto se pasa por argumentos, variables de entorno visibles o logs.

## Criterios de aceptación

La fase solo se considera validada si:

1. La prueba corre en una VM desechable identificada y recuperable.
2. El system manager activa correctamente el servicio como `atlas-runtime`.
3. El descriptor recibido es el socket correcto y permanece bajo lifecycle de systemd.
4. Los permisos y la separación root/runtime son los esperados.
5. La autorización `SO_PEERCRED` se valida en un fixture que permite completar la conexión; por separado, el fixture de permisos de producción demuestra que un UID no privilegiado no atraviesa el directorio/socket privados. No se confunden rechazo filesystem y rechazo IPC.
6. El proceso no conserva privilegios ni descriptores no previstos; el handler verifica AF_UNIX/SOCK_SEQPACKET, rechaza ancillary data y aplica timeout de lectura/escritura; el listener limita concurrencia.
7. Los casos de colisión tienen resultados documentados y no afectan recursos fuera del directorio temporal.
8. Se comparan ambas variantes de `RemoveOnStop` y se define una política explícita para pathname residual/socket stale.
9. Las unidades y fixtures se eliminan/restauran sin tocar recursos ajenos.
10. Se adjuntan comandos, versiones y salidas relevantes, sin incluir secretos.

Un fallo o resultado ambiguo bloquea la adopción de socket activation. No se permite convertir una prueba fallida en una excepción operacional sin revisar el diseño.

## Fuera de alcance

- No implementar el frontend root.
- No crear el protocolo de operaciones administrativas más allá de `authority.ping`.
- No abrir ni crear SQLite.
- No ejecutar migraciones, bootstrap ni provisioning.
- No instalar unidades en el Debian habitual.
- No crear `atlas-runtime` en el host real.
- No modificar `/opt/atlas`, broker, servicios existentes, Docker o bases de datos.
- No declarar socket activation apto para producción.

## Entregable y siguiente decisión

El entregable de esta fase es evidencia reproducible de laboratorio y una decisión explícita: mantener socket activation como candidato, modificar el modelo de permisos/rutas o descartarlo.

Incluso si todas las pruebas pasan, todavía harán falta el diseño del frontend privilegiado, auditoría del canal root → runtime, revisión adversarial del protocolo, autorización de operaciones, idempotencia y reconciliación de resultados ambiguos. La aprobación de esta fase no autoriza despliegue ni cambios en el host.
