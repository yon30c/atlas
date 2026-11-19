# Prototipo IPC Unix para operaciones administrativas de autoridad

**Estado:** prototipo experimental; validación local comunicada por el propietario en Debian: 29 tests focalizados IPC y 1,590 tests de suite completa (`OK (skipped=1)`) sobre el HEAD de código `aae8beda568dee6996ce603fe936085e61fd1165`. La revisión adversarial y la revisión final del diff están completadas. No está habilitado para producción ni se aprueba listener o despliegue.  
**Fase:** 2.5.2.  
**No habilitado para producción.**

## Fuente normativa

El contrato normativo único del protocolo es [Contrato IPC administrativo de autoridad local — atlas-admin/1](../contracts/local-authority-admin-ipc-atlas-admin-1.md). Este archivo describe el prototipo y su estado observado; ante cualquier discrepancia prevalece el contrato normativo.

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
9. Los rechazos de protocolo exponen códigos estables independientes del texto de excepción. Cuando el peer está autorizado y el paquete no está truncado ni contiene ancillary prohibido, el handler envía el envelope `rejected` de §7 del contrato normativo IPC; usa el request ID solo si pudo validarlo de forma canónica, y `null` en caso contrario.
10. Para peer no autorizado, truncamiento, ancillary prohibido o cierre de transporte, el handler no intenta enviar una respuesta.
11. La respuesta de éxito usa el envelope común de §7 del contrato normativo IPC: protocolo, request ID, estado, código, resumen, resultado y referencia de auditoría.
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

**Resultado local comunicado por el propietario (19 de noviembre de 2026):** prueba focalizada `python -m unittest -v tests.unit.test_platform_admin_ipc` — 29 tests, `OK`; suite completa — `Ran 1590 tests in 36.674s` / `OK (skipped=1)`. La ejecución completa tuvo cero fallos, cero errores y una prueba omitida. El checkout probado corresponde al HEAD de código `aae8beda568dee6996ce603fe936085e61fd1165` e incluye la corrección del decoder y la regresión de UID/GID unsigned. Los commits documentales posteriores no alteraron el código ejecutable. No se ejecutaron pruebas desde GitHub.

## Siguiente prueba antes de crear un listener

- Abrir sockets AF_UNIX SOCK_SEQPACKET de filesystem dentro de un directorio temporal privado.
- Verificar que un peer de UID no permitido sea rechazado usando procesos con credenciales Linux distintas (no mocks).
- Comprobar permisos del socket/directorio, symlink preexistente, path existente y cleanup seguro.
- Comprobar límites y comportamiento ante desconexión, packet truncado y timeout de lectura/escritura; el listener debe limitar concurrencia.
- El handler procesa un único paquete; el futuro caller/listener debe cerrar la conexión después de la respuesta y no reutilizarla para una segunda solicitud.
- Comprobar que no se aceptan descriptores auxiliares SCM_RIGHTS.
- Confirmar si `SO_PEERCRED` del socket conectado sigue el modelo esperado para el futuro cliente privilegiado.
- Solo después decidir si se implementa listener persistente o activación systemd.

No ejecutar estas pruebas contra sockets, servicios, usuarios o directorios de Atlas existentes. Usar exclusivamente recursos temporales creados por la suite.

## Decisión pendiente

El socket Unix permanece como candidato experimental. La revisión y la validación de pruebas no aprueban el canal de producción, un listener persistente, la configuración systemd ni las operaciones administrativas.


## Revisión adicional del decoder

Los literales enteros JSON extremos pueden exceder el límite de conversión de Python aunque el paquete respete los 16 KiB. El decoder los marca mediante un sentinel interno durante `parse_int`, completa el parseo para recuperar un `request_id` canónico y luego los rechaza como `INVALID_JSON`. El sentinel nunca puede formar parte de una solicitud aceptada. La primera corrección solo capturaba `ValueError` y perdió el `request_id`; la prueba focalizada detectó esa regresión. La implementación con sentinel fue validada por la prueba focalizada y la suite completa comunicadas arriba.
