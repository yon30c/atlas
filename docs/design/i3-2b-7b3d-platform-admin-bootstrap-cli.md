# I3-2B.7B.3D — diseño de CLI offline para bootstrap de Platform Admin

**Estado:** diseño de implementación basado en inspección del branch; no se ha añadido CLI ni ejecutado bootstrap.
**PR:** #16 — Draft, abierto y sin merge.

## 1. Inspección del baseline

Se inspeccionaron los entrypoints y adaptadores actuales:

- `src/atlas/__main__.py` importa `atlas.cli.main`; `pyproject.toml` publica `atlas = atlas.cli:main`.
- `src/atlas/cli.py` es la composición de la consola conversacional y crea su propia base de conversaciones. No es una CLI administrativa ni debe recibir esta responsabilidad.
- `SQLiteDatabase` requiere ruta absoluta y no debe inicializarse ni aplicar migraciones desde el bootstrap.
- `SQLiteIdentityAuthority(database)` puede leer el USER canónico sin abrir una UoW compartida.
- `SQLitePlatformAdminBootstrapAdapter(database)` es el writer offline aislado y abre su propia transacción `BEGIN IMMEDIATE`.
- `PlatformAdminBootstrapService` ya coordina identidad, reloj y writer; el adaptador vuelve a validar identidad/revisión dentro de la transacción.
- `SQLITE_MIGRATIONS` contiene el schema V25. `SQLiteLocalAuthorityUnitOfWork` expone únicamente el reader Platform Admin, no el writer bootstrap.

## 2. Forma de invocación

Publicar un entrypoint separado en `pyproject.toml`, sin modificar `atlas` ni `atlas.cli`:

```text
atlas-platform-admin-bootstrap \
  --database /ruta/absoluta/atlas.sqlite3 \
  --user-id <canonical-user-uuid> \
  --operation-id <uuidv4>
```

Los tres argumentos son obligatorios. `operation_id` se proporciona explícitamente para que el operador pueda repetir exactamente la misma operación tras una respuesta perdida; la CLI no debe generar silenciosamente un ID nuevo en cada invocación. No existe `--yes`, ni parámetros para falsificar UID o terminal.

## 3. Preflight fail-closed

Antes de componer el servicio:

1. Exigir stdin y stdout conectados a TTY real; rechazar pipes, redirecciones y ejecución no interactiva.
2. Capturar `os.getuid()`, `os.geteuid()` y `os.ttyname(sys.stdin.fileno())` desde el proceso. Son procedencia técnica, no autenticación humana.
3. Exigir una ruta absoluta explícita a un archivo SQLite existente y regular. No crear directorios ni archivos.
4. Inspeccionar el ledger de migraciones en modo solo lectura. Exigir historial completo y checksums/nombres válidos hasta V25. No llamar `initialize()`, `apply_migrations()` ni ejecutar SQL de migración.
5. No usar `SQLiteLocalAuthorityUnitOfWork`, entrypoints HTTP, runtime ni composición de consola.

## 4. Confirmación

Para una operación nueva, resolver y mostrar antes de confirmar:

- ruta de DB y versión de schema;
- operation_id;
- UserId, Identity ID, tipo USER, estado y revisión;
- permisos explícitos `association.suspend` y `association.reactivate`;
- vigencia: 90 días desde la confirmación;
- UID real/efectivo y TTY capturados.

Solicitar exactamente:

```text
BOOTSTRAP PLATFORM ADMIN <user_id>
```

La comparación es exacta, sensible a mayúsculas y sin normalización. Cualquier otra entrada aborta sin escribir. El servicio toma `confirmed_at` del `SystemClock` después de la confirmación; la CLI no acepta timestamps del usuario.

## 5. Recuperación idempotente

Consultar `get_operation(operation_id)` antes de exigir que el USER siga activo o generar procedencia nueva:

- Si existe y el UserId/permisos coinciden, mostrar que la operación ya fue confirmada y devolver el grant persistido sin nueva escritura ni nueva confirmación.
- Si existe con intención distinta, abortar como conflicto.
- Si no existe, resolver USER activo, mostrar el resumen y solicitar la frase exacta antes de llamar al servicio.

El operation_id es obligatorio precisamente para evitar que un reintento genere una segunda intención. La escritura y revalidación final siguen siendo responsabilidad del adaptador SQLite transaccional.

## 6. Resultado y límites

La CLI solo informa el resultado persistido (grant_id, UserId, estado, revisión, permisos y ventana temporal). No imprime secretos porque no recibe ni almacena ninguno. Errores de TTY, argumentos, schema, identidad, confirmación, concurrencia o SQLite terminan con código distinto de cero y sin fallback.

No se ejecuta bootstrap automáticamente al importar, instalar, iniciar Atlas, aplicar migraciones o arrancar servicios. No se crea un administrador predeterminado. La fase de pruebas usa exclusivamente bases temporales.

## 7. Pruebas de aceptación previstas

- TTY ausente / stdin redirigido / stdout redirigido: aborta antes de abrir writer.
- DB ausente, ruta relativa, archivo no regular, ledger ausente/incompleto o checksum inválido: aborta sin crear ni migrar.
- USER inexistente/no USER/suspendido: rechazo.
- frase incorrecta: cero eventos/grants.
- confirmación exacta: una única provisión, permisos exactos y TTL de 90 días.
- replay exacto del operation_id: recupera grant sin duplicar ni renovar TTL.
- operation_id asociado a otro USER: conflicto.
- no hay opción `--yes`, override de UID/TTY ni integración runtime.
- suite completa y `compileall` en Debian; no ejecutar provisión real.

