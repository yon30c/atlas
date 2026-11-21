# Probe aislado A-IPC-03 — resolución segura de rutas

**Fecha:** 2026-11-21  
**Estado:** diseño del probe; implementación y ejecución del propietario pendientes. No autoriza listener persistente, cambios del host ni despliegue.  
**Rama:** `experiment/a-ipc-01-private-unix-listener-probe`  
**Dependencias:** A-IPC-02 completo; `local-authority-admin-private-listener-path-resolution.md`; parser fixture `probe_config.py`.

## 1. Objetivo

Convertir los requisitos A-THREAT-06 en evidencia reproducible, limitada al harness, para la resolución de rutas desde un descriptor de `/`. El probe debe demostrar que cada componente se abre como directorio real sin seguir symlinks, que la política de owner/modo se comprueba sobre el descriptor abierto y que las operaciones posteriores pueden permanecer ancladas al descriptor aunque cambie el pathname.

El probe no selecciona la ruta real del endpoint, no crea `/etc/atlas`, no toca configuración del host, no enlaza un socket IPC y no modifica código productivo.

## 2. Perfil y aislamiento

- Runner independiente: `tests/integration/private_unix_listener/run_path_resolution_probe.py`.
- Ejecución directa como EUID 0 únicamente en la VM desechable `Atlas-VM-test`; requiere confirmaciones explícitas `--confirm-disposable-vm` y `--confirm-fixture-ids`.
- Recibe SERVICE UID/GID y OTHER UID/GID numéricos. Deben ser distintos entre sí y de UID 0; no se crean usuarios ni grupos NSS.
- Crea un único sandbox aleatorio bajo `/run`, root:root, modo 0700. Todas las fixtures quedan dentro; ningún path real de Atlas se crea o modifica.
- Los procesos auxiliares, si los hay, usan credenciales numéricas con grupos suplementarios vacíos. No se usa `sudo`, no se cambia la identidad del runner y no se toca systemd, SQLite ni servicios.
- Cleanup solo después de que todos los hijos terminen. La limpieza debe limitarse al inode del sandbox creado por el propio runner y fallar cerrada si su identidad cambió.
- JSON final registra commit, kernel, Python, EUID, IDs fixture, escenarios, duración y resultado global. Un escenario obligatorio sin ejecutar impide `overall=PASS`.

## 3. Contrato del recorrido

El runner implementará una función local de prueba (no una API de producción) que:

1. Acepte únicamente rutas absolutas ASCII y canónicas. Rechace ruta relativa, NUL, doble separador, separador final (salvo `/`), componentes vacíos, `.` y `..`; no normalice ni corrija entradas.
2. Abra `/` con `O_DIRECTORY | O_CLOEXEC` y valide el descriptor con `fstat`.
3. Abra cada componente siguiente con `os.open(component, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC, dir_fd=parent_fd)`.
4. Valide el descriptor recién abierto, no un pathname previo: debe ser directorio; cada ancestro del fixture debe ser root:root y no escribible por grupo/otros.
5. Para el directorio final de endpoint de fixture, exija exactamente el UID/GID SERVICE y modo 0700. Es una política de fixture, no una decisión de deployment.
6. Mantenga el descriptor padre abierto hasta validar el hijo; al avanzar, cierre solo el descriptor anterior que ya no sea necesario. Devuelva el descriptor final y evidencia por componente (tipo, UID/GID, modo, dispositivo e inode).
7. No use `realpath()`, `Path.resolve()`, `stat(path)` seguido de `open(path)`, ni reabra el pathname después de validar el descriptor.

El archivo de configuración fixture se abrirá por nombre simple relativo al descriptor del padre validado y se pasará a `load_probe_config_at()`. El loader ya aplica `O_NOFOLLOW | O_NONBLOCK`, `fstat`, tipo regular, root:root, modo 0644, `st_nlink == 1`, límite de lectura y snapshot inmutable. El probe debe probar que el recorrido seguro llega al padre correcto antes de reutilizar ese loader.

## 4. Escenarios obligatorios

| ID | Escenario | Resultado requerido |
|---|---|---|
| PR-01 | Rutas relativas, `//`, separador final, componentes vacíos, `.`, `..`, NUL y caracteres no permitidos | Rechazo antes de abrir componentes |
| PR-02 | Recorrido válido desde `/` por varios directorios root:root | PASS; descriptor final corresponde al inode esperado y metadata de cada componente registrada |
| PR-03 | Symlink colocado individualmente en cada nivel intermedio | Rechazo; no se abre el destino ni se escapa del sandbox |
| PR-04 | Componente intermedio que es archivo regular | Rechazo como no-directorio |
| PR-05 | Ancestro root-owned con bits group-write u other-write | Rechazo tras `fstat` y antes de abrir el componente siguiente |
| PR-06 | Directorio intermedio propiedad de OTHER UID | Rechazo aunque modo sea 0700 |
| PR-07 | Directorio final endpoint con SERVICE UID/GID y modo 0700 | PASS; owner, group y modo exactos |
| PR-08 | Directorio final endpoint con UID/GID o modo distinto | Rechazo |
| PR-09 | Apertura de configuración desde parent dirfd validado | Snapshot válido; el descriptor leído y su metadata son la autoridad |
| PR-10 | Nombre final de configuración symlink, FIFO y hardlink | Rechazo sin bloquear, seguir symlink ni leer archivo alternativo |
| PR-11 | Reemplazo del pathname del padre después de abrir su descriptor | Operación relativa al descriptor sigue llegando al directorio original; el symlink sustituto y el destino externo permanecen intactos |
| PR-12 | OTHER UID intenta renombrar/sustituir un componente bajo ancestro privado | EACCES/EPERM; árbol original intacto |

PR-11 prueba semántica de descriptor-relative access; no afirma que el recorrido pathname completo sea atómico frente a root o SERVICE UID, ambos dentro de TCB-1. PR-12 demuestra DAC de la fixture, no una defensa frente a root/capabilities.

## 5. Criterios de aceptación

- Todos los PR-01..PR-12 deben quedar PASS para `overall=PASS`.
- Cualquier escape, lectura de destino symlink, modificación del sentinel, bloqueo inesperado, metadata discrepante o cleanup inseguro produce FAIL.
- El runner nunca elimina objetos que no creó ni intenta corregir permisos/ownership.
- La evidencia debe diferenciar explícitamente el recorrido del archivo de configuración y la ruta del directorio endpoint.
- No se probará bind/connect ni se retirará socket alguno: colisiones y stale recovery pertenecen a A-THREAT-05 y se mantienen separados.
- El resultado solo valida el harness y el kernel/VM indicados. No fija rutas/owners productivos, no resuelve el bind pathname no-dirfd-atómico y no aprueba transporte ni lifecycle productivo.

## 6. Fuera de alcance y siguiente gate

Fuera de alcance: configuración real `/etc/atlas/admin-ipc.conf`, creación de `/etc/atlas`, directorios de producción, bind/connect, socket stale cleanup, procfs bind, systemd, listener persistente, cliente administrativo, SQLite y cambios del host.

Después de PR-01..PR-12, revisar el resultado y decidir por separado si hace falta un probe de colisión/stale recovery (A-THREAT-05). La ruta real y la matriz definitiva de ownership/modos siguen pendientes de un plan de instalación aprobado.
