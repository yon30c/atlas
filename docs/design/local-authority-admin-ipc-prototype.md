# Prototipo IPC Unix para operaciones administrativas de autoridad

**Estado:** prototipo experimental; suite completa validada por el propietario en Debian 13 (1.583 tests, 1 omitido, cero fallos); pendiente revisión adversarial final.  
**Fase:** 2.5.2.  
**No habilitado para producción.**

## Alcance implementado

El módulo `src/atlas/platform_admin_ipc.py` prueba estas propiedades:

1. Un socket conectado debe ser `AF_UNIX/SOCK_SEQPACKET`; el handler comprueba ambas propiedades antes de consultar credenciales.
2. La identidad del peer se obtiene desde el kernel mediante `SO_PEERCRED`; el UID debe pertenecer a una allowlist local.
3. Se acepta exactamente un paquete por conexión.
4. El request usa el envelope exacto `atlas-admin/1`, con UUIDv4 canónico y operación del catálogo cerrado de siete nombres.
5. Solo `authority.ping` está implementada. Las otras seis operaciones del catálogo se reconocen y se rechazan con `OPERATION_DENIED`; los nombres ajenos al catálogo se rechazan con `UNKNOWN_OPERATION`. Ninguna operación adicional se ejecuta.
6. El payload de `authority.ping` debe ser exactamente el objeto vacío `{}`.
7. El tamaño máximo del request es 16 KiB y el de la respuesta es 64 KiB.
8. La validación rechaza claves duplicadas, campos extra, protocolo desconocido, UUID no canónico/no UUIDv4, UTF-8 inválido, JSON inválido, números no finitos, profundidad superior a 16, payload de ping no vacío, paquete truncado y datos ancillary.
9. Los rechazos de protocolo exponen códigos estables independientes del texto de excepción. Cuando el peer está autorizado y el paquete no está truncado ni contiene ancillary prohibido, el handler envía el envelope `rejected` de §10.5; usa el request ID solo si pudo validarlo de forma canónica, y `null` en caso contrario.
10. Para peer no autorizado, truncamiento, ancillary prohibido o cierre de transporte, el handler no intenta enviar una respuesta.
11. La respuesta de éxito usa el envelope común de §10.5: protocolo, request ID, estado, código, resumen, resultado y referencia de auditoría.
12. El resultado de ping contiene únicamente `protocol_version`, `service_version` y `handler_status: "available"`. La versión se obtiene de los metadatos de la distribución `atlas-assistant`; para ejecución directa desde un checkout sin metadatos instalados se usa el fallback sincronizado con `[project].version` de `pyproject.toml`.
13. Ping no abre SQLite, no inspecciona la ruta ni el filesystem de la DB, no devuelve configuración interna y no crea sesión ni conserva estado entre conexiones.
14. Los timeouts de lectura y escritura son independientes; cada uno tiene default 5 s y máximo 60 s.
15. EOF/recepción vacía se trata como cierre de transporte sin operación ni respuesta, ya que el handler no asume que puede distinguirlo de un paquete de longitud cero. Una desconexión durante envío tampoco se transforma en un resultado de dominio.

Los tests unitarios usan pares de sockets Unix reales para validar el transporte `SOCK_SEQPACKET` y las credenciales kernel del peer. Los tests no requieren privilegios.

## Lo que el prototipo deliberadamente no hace

- No crea un socket de filesystem ni define propietario/modo/ACL de un socket persistente.
- No crea listener, daemon, socket activation ni unidad systemd.
- No cambia UID/GID, no usa sudo/setuid y no delega ejecución.
- No abre SQLite ni importa la composición de autoridad.
- No ejecuta diagnóstico, migraciones, bootstrap ni provisioning.
- No registra auditoría administrativa ni identifica al operador humano.
- No valida capabilities, saved IDs, entorno, descriptores heredados o hardening de un proceso desplegado.
- No demuestra aislamiento entre cuentas Linux distintas; el test local inicial permite el UID actual.

## Validación del propietario en Debian

Desde el checkout de `work/authority-admin-protocol-contract-alignment`:

```bash
python -m unittest -v tests.unit.test_platform_admin_ipc
python -m compileall -q src tests
git diff --check
git status --short --branch
```

**Resultado comunicado:** `Ran 1583 tests in 34.367s` / `OK (skipped=1)`. Se ejecutaron 1.583 tests, con cero fallos y cero errores; uno fue omitido. La suite completa confirma que las pruebas filesystem quedaron alineadas con el envelope `atlas-admin/1` y la semántica `AdminPeerDisconnected`. Esta validación fue ejecutada por el propietario en su servidor Debian local, no desde GitHub. La revisión adversarial final sigue pendiente.

## Siguiente prueba antes de crear un listener

- Abrir sockets AF_UNIX SOCK_SEQPACKET de filesystem dentro de un directorio temporal privado.
- Verificar que un peer de UID no permitido sea rechazado usando procesos con credenciales Linux distintas (no mocks).
- Comprobar permisos del socket/directorio, symlink preexistente, path existente y cleanup seguro.
- Comprobar límites y comportamiento ante desconexión, packet truncado y timeout de lectura/escritura; el listener debe limitar concurrencia.
- Comprobar que no se aceptan descriptores auxiliares SCM_RIGHTS.
- Confirmar si `SO_PEERCRED` del socket conectado sigue el modelo esperado para el futuro cliente privilegiado.
- Solo después decidir si se implementa listener persistente o activación systemd.

No ejecutar estas pruebas contra sockets, servicios, usuarios o directorios de Atlas existentes. Usar exclusivamente recursos temporales creados por la suite.

## Decisión pendiente

El socket Unix permanece como candidato. La aprobación de este prototipo no aprueba todavía el canal de producción, la configuración systemd ni las operaciones administrativas.
