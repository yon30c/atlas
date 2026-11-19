# Prototipo IPC Unix para operaciones administrativas de autoridad

**Estado:** prototipo experimental, pendiente de validación en Debian y revisión adversarial.  
**Fase:** 2.5.2.  
**No habilitado para producción.**

## Alcance implementado

El módulo `src/atlas/platform_admin_ipc.py` prueba estas propiedades:

1. Un socket conectado debe ser `AF_UNIX/SOCK_SEQPACKET`; el handler comprueba ambas propiedades antes de consultar credenciales.
2. La identidad del peer se obtiene desde el kernel mediante `SO_PEERCRED`; el UID debe pertenecer a una allowlist local.
3. Se acepta exactamente un paquete por conexión.
4. El request usa el envelope exacto `atlas-admin/1`, con UUIDv4 canónico, operación allowlisted y payload vacío para `authority.ping`.
5. El tamaño máximo del request es 16 KiB y el de la respuesta es 64 KiB.
6. Se rechazan claves duplicadas, campos extra, protocolo desconocido, UUID no canónico/no UUIDv4, UTF-8 inválido, JSON inválido, operación desconocida, payload no vacío, paquete truncado y datos ancillary.
7. La única operación disponible es `authority.ping`, sin efectos de dominio.
8. La respuesta usa el envelope común de §10.5: protocolo, request ID, estado, código, resumen, resultado y referencia de auditoría.
9. Cada conexión tiene timeout de lectura/escritura configurable, default 5 s y máximo 60 s; el handler procesa una conexión y un paquete. El listener futuro debe imponer por separado un límite de concurrencia/backpressure.

Los tests unitarios usan pares de sockets Unix reales para validar el transporte `SOCK_SEQPACKET` y las credenciales kernel del peer. Los tests no requieren privilegios.

## Lo que el prototipo deliberadamente no hace

- No crea un socket de filesystem ni define propietario/modo/ACL de un socket persistente.
- No crea listener, daemon, socket activation ni unidad systemd.
- No cambia UID/GID, no usa sudo/setuid y no delega ejecución.
- No abre SQLite ni importa la composición de autoridad.
- No expone diagnóstico, migraciones, bootstrap ni provisioning.
- No registra auditoría administrativa ni identifica al operador humano.
- No valida capabilities, saved IDs, entorno, descriptores heredados o hardening de un proceso desplegado.
- No demuestra aislamiento entre cuentas Linux distintas; el test local inicial permite el UID actual.
- El resultado detallado de ping (versión del servicio y disponibilidad del handler) y la taxonomía completa de errores se completan en etapas posteriores.

## Validación requerida por el propietario en Debian

Desde el checkout de la rama de trabajo:

```bash
python -m unittest -v tests.unit.test_platform_admin_ipc
python -m compileall -q src tests
git diff --check
git status --short --branch
```

Se debe informar el número de tests y el resultado exacto. Si el paquete de tests no puede importarse como módulo en ese checkout, ejecutar el archivo con el mecanismo de test ya usado por el repositorio y reportar el comando.

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
