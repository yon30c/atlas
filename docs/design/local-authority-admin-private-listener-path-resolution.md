# Resolución segura de rutas y ownership — listener privado

**Fecha:** 2026-11-21  
**Estado:** diseño candidato para alternativa A; pendiente de revisión y probes aislados. No autoriza implementación persistente ni cambios del host.  
**Rama:** `experiment/a-ipc-01-private-unix-listener-probe`  
**Relacionado:** `local-authority-admin-private-listener-identity-config.md`, `local-authority-admin-listener-lifecycle.md`, `local-authority-admin-private-listener-threat-model-review.md`.

## 1. Objetivo y alcance

Cerrar a nivel de diseño el requisito A-THREAT-06: la seguridad de una ruta absoluta no puede depender de aplicar `O_NOFOLLOW` únicamente al último componente. Deben resolverse y validarse todos los directorios desde una raíz confiable, conservar descriptores y hacer operaciones relativas cuando la API lo permita.

Se distinguen dos superficies con propiedades diferentes:

1. **Archivo de configuración confiable**, candidato `/etc/atlas/admin-ipc.conf`, administrado por root y de solo lectura para los procesos.
2. **Directorio del endpoint**, ruta aún no fijada, preaprovisionada para `atlas-runtime`, con modo candidato `0700`; el socket tendría modo candidato `0600`.

Este documento no confirma que esas rutas existan en Debian. No deben crearse durante esta fase. Tampoco define todavía el mecanismo final de bind/connect para el socket.

## 2. Política común de rutas

- Aceptar únicamente rutas absolutas, constantes y procedentes de la configuración confiable. Nunca desde JSON, argumentos libres, entorno del usuario, nombre de proyecto o datos de operador.
- Rechazar rutas relativas, componentes vacíos, `.`, `..`, NUL, separadores alternativos, expansión `~`, variables, globbing y normalizaciones ambiguas. No “arreglar” una ruta inválida: fallar cerrado.
- Comenzar la resolución desde un descriptor abierto de la raíz `/`; no volver a resolver la ruta completa desde el cwd.
- Recorrer cada componente directorio mediante `openat` (en Python, `os.open(..., dir_fd=...)`) con `O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC`. Validar cada descriptor con `fstat` antes de continuar.
- Mantener abierto el descriptor del directorio padre validado mientras se usa. Las operaciones de inspección/eliminación deben ser relativas a ese descriptor (`fstatat`/equivalente con no-follow y `unlinkat`/equivalente).
- No asumir que `O_NOFOLLOW` en el último componente protege los ancestros. No usar `realpath()`, `Path.resolve()` o una secuencia pathname-stat-then-open como control de seguridad.
- `openat2(RESOLVE_BENEATH | RESOLVE_NO_SYMLINKS | RESOLVE_NO_MAGICLINKS)` podría evaluarse como alternativa Linux, pero no es requisito de la primera especificación. No introducir una llamada syscall propia hasta definir compatibilidad, manejo de ENOSYS/EINVAL y pruebas. El recorrido componente a componente con descriptores es la base candidata.
- Registrar para cada directorio validado tipo, UID/GID, modo, dispositivo e inode. Los valores esperados deben proceder de la política de instalación aprobada, no inferirse de lo que se encuentre.

Los directorios intermedios deben ser directorios reales, no symlinks, y no ser escribibles por identidades fuera de la TCB. La política de propietario/modo debe definirse por componente; no imponer que todos los componentes tengan el mismo UID.

## 3. Lectura del archivo de configuración

Para el archivo candidato `/etc/atlas/admin-ipc.conf`:

1. Abrir y validar `/`, luego `/etc`, luego `/etc/atlas`, manteniendo cada descriptor y aplicando la política root-owned/no-writable-by-untrusted a cada componente.
2. Abrir el nombre final relativo al descriptor de `/etc/atlas` con `O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK`. `O_NONBLOCK` evita quedar bloqueado si una sustitución inesperada apunta a FIFO antes de validar el tipo.
3. Ejecutar `fstat` sobre el descriptor ya abierto. Exigir archivo regular, propietario root:root, no escribible por grupo/otros, tamaño máximo pequeño y, como política inicial, `st_nlink == 1` para rechazar hardlinks.
4. Leer desde ese descriptor, con límite estricto de bytes (máximo + 1 para detectar exceso). Nunca validar un pathname y luego reabrirlo.
5. Parsear con gramática cerrada; rechazar duplicados, claves desconocidas, tipos incorrectos, números fuera de rango y valores ambiguos.
6. Convertir a estructura inmutable. El servicio y el cliente no recargan configuración durante una conexión ni durante la vida del proceso; cambios requieren reinicio controlado y preflight completo.

El modo candidato del archivo es `0644`: contiene únicamente IDs, rutas y límites no secretos; root es el único escritor. Si el esquema incorpora secretos, esta decisión deja de ser válida y debe rediseñarse la distribución de configuración. No incluir secretos compartidos como sustituto de `SO_PEERCRED`.

## 4. Directorio del endpoint y socket

La ruta del socket sigue pendiente de fijarse. Cuando se seleccione:

- Todos los componentes de directorio deben validarse desde `/`; el directorio final será preaprovisionado, propiedad de `atlas-runtime:atlas-runtime`, modo candidato `0700`, sin ACL/grupos adicionales.
- El servicio conservará un descriptor del directorio final y lo usará para inspección y cleanup relativo.
- La cuenta `atlas-runtime` es TCB-1 aceptada: procesos de ese UID se consideran confiables entre sí. Los usuarios ordinarios externos no pueden modificar el directorio; root también pertenece a la autoridad superior confiable del host.
- El nombre del socket será fijo, no derivado de parámetros del cliente. `bind()` de AF_UNIX pathname recibe una ruta, no un `dir_fd` en la API Python estándar. Por ello, la validación del directorio por descriptor no debe presentarse falsamente como un bind atómico relativo al descriptor.
- El diseño inicial puede usar el pathname absoluto solo después de verificar la cadena y establecer que ningún actor fuera de la TCB puede modificar los directorios. Debe evaluarse si una técnica basada en `/proc/self/fd/<n>/...` realmente conserva la semántica/identidad esperada antes de adoptarla; no asumirlo.
- Antes de `bind()`, no hacer unlink, rename ni truncamiento. Si el nombre ya existe, fallar cerrado.
- Después de bind, inspeccionar la entrada relativa al descriptor, sin seguir symlinks, y comprobar socket, UID, modo, `st_dev` y `st_ino`. Mantener descriptor listener y descriptor de directorio.
- El cliente usa la ruta fija de configuración, conecta y valida `SO_PEERCRED` del servidor antes de enviar bytes. Una comprobación pathname previa puede servir para diagnóstico, pero no autentica al servidor y no elimina carreras; la autenticación de servidor se basa en UID kernel.

El uso de descriptores y ownership impide la sustitución por UIDs ordinarios que no pueden escribir en los directorios. Bajo TCB-1, no se pretende defender frente a root ni frente a procesos maliciosos del propio UID `atlas-runtime`.

## 5. Limpieza y TOCTOU

Linux no ofrece en la API habitual una operación pathname de “unlink únicamente si el inode aún es X”. Por tanto, comprobar `st_dev/st_ino` y después llamar `unlinkat` conserva una ventana TOCTOU; el uso de `dir_fd` evita escapes de ruta, pero no vuelve atómica la comparación y eliminación.

Bajo TCB-1, la estrategia candidata es:

1. Mantener el descriptor del directorio privado abierto durante todo el lifecycle.
2. Antes de cleanup, consultar la entrada relativa a ese descriptor con no-follow.
3. Exigir que sea socket y que coincida con `st_dev/st_ino` registrado después del bind, además de UID esperado.
4. Ejecutar `unlinkat` relativo al mismo descriptor solo si la identidad coincide.
5. Si algo no coincide o la consulta falla, no eliminar; registrar y dejar el objeto para diagnóstico administrativo separado.
6. No hacer stale cleanup automático en un arranque posterior.

La carrera residual no se declara resuelta por una primitiva atómica: se considera no explotable por UIDs externos porque no pueden modificar el directorio; root y los procesos del mismo UID pertenecen a la TCB. Si esa exclusividad no puede demostrarse en el entorno de instalación, alternativa A no satisface el modelo y debe detenerse antes de implementar.

## 6. Identidad del cliente privilegiado

El propietario confirmó como requisito que el frontend administrativo debe conectar con **EUID 0**. La allowlist del servicio queda fijada como requisito de diseño `client_uids = {0}`, no como valor operativo ya probado.

- El frontend comprueba su EUID antes de conectar y falla si no es 0.
- El servidor obtiene `SO_PEERCRED` antes de `recv` y solo acepta UID kernel 0.
- El frontend consulta `SO_PEERCRED` después de `connect` y antes de `send`; solo continúa si el UID kernel del servidor coincide con el UID numérico configurado para `atlas-runtime`.
- No se aceptan consumidores adicionales sin una nueva decisión explícita del propietario.
- La comprobación UID identifica el dominio de confianza, no el ejecutable ni la identidad humana del operador. Root es parte de la autoridad confiable del host.

El entrypoint ejecutable del frontend y su modo real de lanzamiento aún no existen/revisados. Por ello, EUID 0 es requisito aceptado, pero no hay evidencia de runtime para el par cliente UID 0 ↔ servicio `atlas-runtime`.

## 7. Fallos y comportamiento cerrado

Fallar antes de crear/aceptar conexiones ante ruta no absoluta/canónica, symlink en cualquier componente, directorio no regular, propietario/modo inesperado, archivo de configuración no regular, hardlink no permitido, tamaño excesivo, configuración inválida, descriptor perdido o discrepancia de identidad.

No corregir permisos automáticamente, no crear directorios, no cambiar ownership, no borrar rutas existentes, no reintentar con defaults y no intentar recuperación stale en startup.

## 8. Matriz de escenarios para un probe futuro

| Escenario | Resultado requerido |
|---|---|
| Symlink en cualquier componente intermedio | Rechazo sin abrir fuera de la raíz confiable |
| Componente `..`, ruta relativa o ruta ambigua | Rechazo de configuración |
| Directorio padre escribible por UID no confiable | Rechazo antes de abrir el siguiente componente |
| Archivo final symlink/FIFO/socket/dispositivo | Rechazo sin bloqueo ni lectura |
| Configuración con hardlink (si se mantiene `st_nlink == 1`) | Rechazo |
| Reemplazo del nombre final después de abrir | Lectura desde el descriptor original, nunca reabrir pathname |
| Directorio del endpoint sustituible por UID externo | Preflight debe demostrar que ownership/modos lo impiden |
| Nombre de socket preexistente | Bind falla; objeto y contenido permanecen intactos |
| Socket sustituido antes de cleanup | Sustituto permanece intacto |
| UID cliente distinto de 0 | Rechazo antes de `recv`, sin respuesta de protocolo |
| Cliente con EUID distinto de 0 | No intenta conectar |
| Servidor con UID distinto del `service_uid` esperado | Cliente cierra antes de enviar bytes |
| Configuración cambia tras cargar | La instancia conserva snapshot inmutable; cambio requiere reinicio |

Los escenarios son requisitos de diseño; no se han implementado ni ejecutado.

## 9. Decisiones pendientes

1. Fijar la ruta real del socket y los owners/modos exactos de cada componente según el plan de instalación.
2. Revisar una técnica segura para que el pathname usado por `bind()` corresponda al directorio validado; no asumir que `dir_fd` se propaga a `bind()`.
3. Definir el procedimiento manual y auditado para retirar un socket residual.
4. Definir límites de tamaño/formatos y política definitiva de hardlinks para el archivo de configuración.
5. Identificar el entrypoint cliente y revisar el lanzamiento real con EUID 0.
6. Diseñar un probe aislado para el recorrido de ruta, autenticación mutua y cleanup; no usar la cuenta temporal A09 ni modificar el host sin autorización independiente.

## 10. Límites

- Diseño estático/documentación desde GitHub.
- No se modificó código, contrato normativo ni configuración del host.
- No se ejecutaron pruebas, compilaciones ni workflows.
- No se crearon rutas, archivos `/etc`, usuarios, grupos, permisos, servicios ni sockets.
- No se aprobó listener persistente, systemd, acceso SQLite ni despliegue.
