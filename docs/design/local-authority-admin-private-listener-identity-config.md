# Configuración confiable de identidad — alternativa A

**Fecha:** 2026-11-21  
**Estado:** diseño candidato posterior a aceptación de TCB-1 y a la decisión explícita de EUID 0; faltan entrypoint ejecutable, valores operativos y validación aislada.  
**Rama:** experiment/a-ipc-01-private-unix-listener-probe  
**Relacionado:** trust-boundary, lifecycle, threat-model review y [resolución segura de rutas](local-authority-admin-private-listener-path-resolution.md).

## 1. Decisión aceptada y alcance

El propietario aceptó TCB-1: todos los procesos ejecutados bajo la cuenta dedicada atlas-runtime forman parte del mismo dominio confiable. Por tanto, el diseño no intenta distinguir procesos del mismo UID. Esta aceptación no autoriza todavía crear la cuenta, cambiar grupos/permisos, instalar servicios, abrir un listener persistente ni desplegar.

Bajo TCB-1, el objetivo inmediato es una fuente única, protegida y no controlable por el cliente para fijar las identidades numéricas, el endpoint y la política de autenticación.

## 2. Fuente de configuración recomendada

**Recomendación:** archivo de configuración local administrado por root, separado del repositorio y de los datos mutables de la aplicación. Ubicación candidata: /etc/atlas/admin-ipc.conf.

La ruta es una propuesta, no una ruta existente confirmada ni una instrucción para crearla.

Propiedades candidatas:

- Propietario root:root.
- Modo candidato 0644, propietario root:root. El archivo contiene solo identificadores y rutas no secretas; ambos procesos pueden leerlo, pero solo root puede modificarlo. Evitar añadir un grupo lector al servicio si no es necesario.
- Directorio padre root:root y no escribible por atlas-runtime ni por el cliente no privilegiado.
- Archivo regular, no symlink, con resolución segura de todos los componentes de ruta.
- Parseo estricto: claves conocidas, sin duplicados, sin interpolación, sin includes, sin expansión de variables, sin valores por defecto permisivos.
- Configuración cargada una vez durante preflight y convertida en estructura inmutable.
- Cualquier ausencia, clave desconocida, duplicado, tipo incorrecto, ID inválido o contradicción con identidad efectiva provoca fallo cerrado antes de crear/aceptar conexiones.

No almacenar secretos: SO_PEERCRED no usa secreto compartido. Los valores de UID/GID y la ruta del socket no son credenciales secretas; su integridad sí es crítica.

## 3. Esquema lógico propuesto

Los nombres son ilustrativos; el formato definitivo (TOML, JSON o ini estricto) se seleccionará al implementar el parser. No crear este archivo en el host durante esta fase.

| Campo | Significado | Estado |
|---|---|---|
| schema_version | Versión exacta del esquema de configuración | Requerido |
| service_uid | UID numérico esperado de atlas-runtime | Requerido, valor pendiente |
| service_gid | GID primario esperado de atlas-runtime | Requerido, valor pendiente |
| client_uids | Lista cerrada de UID autorizados | Requerido, identidad por confirmar |
| socket_path | Ruta absoluta fija del endpoint AF_UNIX | Requerido, valor pendiente |
| socket_type | Literal SOCK_SEQPACKET | Fijo |
| socket_mode | Modo esperado del socket | Candidato 0600 |
| socket_dir_mode | Modo esperado del directorio | Candidato 0700 |

No aceptar UID/GID simbólicos en runtime como autoridad. El provisionamiento podrá usar nombres, pero el preflight debe resolver y verificar IDs numéricos efectivos y mantener esos números durante la vida del proceso. No aceptar comodines, rangos, UID negativos ni allowlists vacías.

## 4. Separación de responsabilidades

### 4.1 Proceso de servicio atlas-runtime

- Lee la configuración de solo lectura durante startup.
- Verifica que UID/GID real, efectivo y saved coincidan con la política acordada para el servicio.
- Verifica que no haya capabilities efectivas/permitted/inheritable/ambient inesperadas. La política de capabilities debe ser explícita; valor inicial recomendado: ninguna capability adicional.
- Verifica que la configuración declara el mismo UID/GID que el proceso y que la ruta está bajo el directorio privado esperado.
- Congela service identity, client_uids, endpoint y límites en un objeto de configuración inmutable.
- Rechaza startup ante discrepancias; no reintenta con defaults ni modifica credenciales para corregirlas.

### 4.2 Cliente administrativo

- Lee la misma fuente protegida o una fuente equivalente con integridad garantizada.
- No acepta UID esperado, socket_path ni política de autenticación desde argumentos, variables de entorno no confiables, solicitud IPC ni configuración de usuario.
- Conecta a socket_path y consulta SO_PEERCRED antes de enviar cualquier byte.
- Compara UID del peer con service_uid. Si no coincide, cierra inmediatamente sin enviar solicitud.
- No necesita leer la allowlist client_uids para autenticar al servidor; esa lista es política del servicio.

### 4.3 Servicio autenticando al cliente

- Usa client_uids como frozenset cargado en preflight.
- Obtiene SO_PEERCRED del socket aceptado antes de recv.
- Rechaza y cierra sin respuesta de protocolo cuando el UID no está en la lista.
- Nunca usa PID/GID para ampliar autorización ni toma identidad del JSON.

## 5. Política de UID/GID y privilegios

La propuesta inicial respaldada por el diseño de operaciones existente es:

- Servicio: UID dedicado atlas-runtime, GID primario dedicado atlas-runtime.
- Cliente requerido: frontend administrativo con EUID 0, decisión explícita del propietario.
- Allowlist requerida del servicio: exactamente {0}; no se admiten consumidores adicionales sin nueva decisión explícita.
- Servicio sin capabilities adicionales.
- Sin grupos suplementarios con autoridad sobre el directorio/socket salvo los estrictamente necesarios y documentados.

El diseño de operaciones administrativas y la decisión posterior del propietario fijan EUID 0 como requisito del frontend. La inspección no encontró un cliente IPC ejecutable/entrypoint que realice connect: por ello, la política de diseño queda fijada como client_uids={0}, pero su cumplimiento operativo exige implementar y revisar el entrypoint y comprobar su EUID real. No se declara validado el par UID 0 ↔ atlas-runtime.

La comprobación de UID/GID real, efectivo y saved debe ser consistente con el modo de lanzamiento elegido. No se debe imponer todavía una política de NoNewPrivileges, bounding set, seccomp o systemd sandbox sin revisar primero cómo se inicia el proceso y qué capacidades necesita. La decisión provisional es no conceder capabilities adicionales al servicio; los mecanismos concretos de hardening se diseñarán después.

## 6. Integridad y carga segura de la configuración

Requisitos para futura implementación:

1. Resolver todos los componentes desde el descriptor de /, recorriendo directorios con openat/dir_fd, O_DIRECTORY y O_NOFOLLOW, y validando cada uno con fstat; seguir [la especificación de resolución de rutas](local-authority-admin-private-listener-path-resolution.md). No basta con O_NOFOLLOW en el último componente.
2. Verificar mediante fstat que el descriptor apunta a archivo regular, propietario esperado, modo no escribible por grupo/otros y tamaño máximo pequeño.
3. Leer desde el descriptor validado; no hacer stat y luego volver a abrir por pathname.
4. Rechazar hardlinks si el modelo operativo los considera un vector no aceptable; documentar la política concreta.
5. Parsear con gramática cerrada y límites estrictos; rechazar claves duplicadas, desconocidas o valores fuera de rango.
6. Resolver el usuario/grupo solo en provisioning confiable; comparar contra IDs numéricos y credenciales reales/efectivas/saved del proceso.
7. Mantener configuración inmutable en memoria; no recargar automáticamente mientras el listener esté activo.
8. Si cambia la configuración, exigir reinicio controlado y nueva validación completa.

El uso de descriptor y resolución segura protege contra sustituciones de ruta durante lectura; no protege frente a root, que administra la fuente confiable y pertenece a la autoridad del host.

## 7. Errores y observabilidad

- Configuración ausente, inválida, inesperada o no legible: servicio no inicia.
- UID/GID/capabilities efectivos inesperados: servicio no inicia.
- UID de servidor no esperado en cliente: cliente cierra antes de enviar solicitud.
- UID de cliente no permitido en servidor: cierre antes de leer solicitud y sin respuesta protocolaria.
- Logs incluyen código de error, etapa y PID/UID/GID kernel cuando sea apropiado; no registran payload sensible, variables de entorno ni contenido completo de configuración.
- No registrar la lista de UID autorizados como mecanismo de autorización ni permitir que logs alteren decisiones.

## 8. Decisiones aún abiertas

1. Implementar e identificar el entrypoint concreto del frontend y verificar que su EUID al conectar sea 0; el requisito está aceptado, pero no existe cliente IPC ejecutable revisado.
2. Confirmar que ambos procesos pueden leer el mismo archivo root:root 0644 sin exponer secretos (el esquema no debe contenerlos); si no, diseñar configuración duplicada desde fuente canónica.
3. Confirmar formato de archivo y ruta definitiva tras revisar convenciones/configuración existentes del repositorio y el modelo de instalación.
4. Definir valores definitivos de UID/GID, socket path y límites de modo.
5. Definir política precisa de capabilities y hardening según el entrypoint real.
6. Mantener EUID 0 como requisito del frontend; si se propone un helper, demostrar que el proceso que realmente conecta conserva EUID 0 y someter el diseño a revisión separada.

## 9. Próximo incremento técnico

Después de resolver los puntos 1–3, diseñar un probe aislado, sin listener persistente ni host changes, que cubra:

- carga de configuración confiable y fallos de integridad;
- cliente que acepta UID de servidor esperado y rechaza UID incorrecto antes de enviar bytes;
- servidor que acepta UID cliente permitido y rechaza UID no permitido antes de recv;
- discrepancias de UID/GID reales, efectivos y saved;
- configuración inmutable durante la vida del servicio;
- ausencia de capabilities adicionales bajo el modelo aprobado.

No reutilizar ni modificar la identidad temporal atlas-a09-test sin autorización y plan independiente.

## 10. Límites

- Diseño estático/documentación en GitHub.
- No se modificó código, contrato normativo ni configuración del host.
- No se ejecutaron pruebas, compilaciones ni workflows.
- No se crearon usuarios/grupos, archivos /etc, permisos, servicios ni sockets.
- No se aprobó listener persistente, systemd, acceso SQLite ni despliegue.


## 11. Decisión del propietario — identidad cliente EUID 0 (2026-11-21)

El propietario confirmó que el frontend administrativo debe ejecutarse con EUID 0. La política de diseño del servicio queda fijada en `client_uids={0}`. El cliente debe verificar su propio EUID antes de conectar; el servidor debe verificar UID kernel 0 mediante `SO_PEERCRED` antes de leer; el cliente debe verificar el UID configurado de `atlas-runtime` antes de enviar bytes. Esto identifica dominios UID, no un ejecutable específico.

La decisión no prueba un entrypoint inexistente ni valida el par operativo UID 0 ↔ `atlas-runtime`. No autoriza cambios de host, cuentas, permisos, servicios, listener persistente ni despliegue.
