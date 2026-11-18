# I3-2B.7B.3C — Platform Admin bootstrap application service

**Estado:** implementación publicada; validación automatizada del propietario pendiente.

## Propósito

Añadir una capa de aplicación pequeña que prepare el comando inmutable para el bootstrap offline. No sustituye las garantías del adaptador SQLite ni constituye una capacidad de runtime/HTTP.

## Dependencias

`PlatformAdminBootstrapService` recibe explícitamente:
- `IdentityAuthorityPort`, usado para resolver el USER canónico solicitado;
- `PlatformAdminBootstrapPort`, capacidad de escritura offline;
- `Clock`, única fuente de tiempo confiable;
- una fábrica UUIDv4 inyectable para pruebas deterministas (por defecto `uuid4`).

No depende de `SQLiteLocalAuthorityUnitOfWork` y no se incorpora a la composición de runtime.

## Flujo

1. Valida que la intención sea `PlatformAdminBootstrapRequest` y conserve el conjunto exacto de permisos iniciales.
2. Resuelve `request.user_id` mediante Identity Authority.
3. Antes de resolver la identidad o generar nuevos IDs, consulta `get_operation(operation_id)` en el puerto offline. Si ya existe, compara la intención (USER y permisos) y devuelve el grant persistido; si la intención difiere, rechaza el conflicto. Esto recupera un commit exitoso cuya respuesta se perdió sin fabricar una procedencia nueva.
4. Si no existe operación previa, rechaza USER inexistente o no ACTIVE.
5. Obtiene `confirmed_at` exclusivamente de `Clock.now()` y exige UTC consciente de zona.
6. Genera `event_id` y `grant_id` UUIDv4 distintos.
7. Construye procedencia técnica inmutable y grant ACTIVE de revisión 1, con emisión/not-before iguales a la confirmación y expiración exactamente 90 días después.
8. Construye `PlatformAdminBootstrapCommand` (que vuelve a comprobar consistencia entre request, provenance y grant).
9. Delega al puerto offline y devuelve su resultado. Los errores de persistencia se propagan; no hay fallback ni reintento implícito.

## Límite transaccional y concurrencia

La lectura inicial del USER sirve para preparar el comando, no es la decisión final de autoridad. Entre esa lectura y la escritura puede cambiar la identidad. Por eso el adaptador SQLite debe revalidar dentro de su propia transacción `BEGIN IMMEDIATE` que:
- el UserId/Identity(USER) sigue existiendo y ACTIVE;
- identity_id y revisión coinciden con el comando;
- no hay historial previo, salvo replay exacto del mismo operation_id;
- evento y grant se insertan atómicamente.

El servicio no abre otra UoW, no realiza una segunda escritura y no debilita esa frontera.

## Procedencia y seguridad

UID real/efectivo y terminal son datos del proceso local suministrados por la futura CLI después de capturarlos del sistema. Este servicio valida sus contratos a través de `PlatformAdminBootstrapProvenance`, pero no puede probar por sí mismo que esos valores sean auténticos. No se almacenan contraseñas, tokens ni secretos. La confirmación interactiva y la comprobación de TTY pertenecen a la futura fase CLI 7B.3D.

## Pruebas añadidas

`tests/unit/test_platform_admin_bootstrap_service.py` cubre:
- construcción del comando desde USER activo y reloj confiable;
- TTL de 90 días y permisos exactos;
- rechazo de USER inexistente/suspendido;
- rechazo de reloj no UTC;
- propagación de fallo del puerto sin fallback.

Las pruebas de este slice no ejecutan una provisión real ni acceden a una base productiva.


## Recuperación exacta de operaciones

Se amplió el puerto offline con `get_operation(operation_id)`. El adaptador SQLite reconstruye el comando persistido desde el evento y grant canónicos. El servicio consulta este resultado antes de generar IDs/procedencia o releer el USER:
- mismo operation_id + mismo USER/permisos: devuelve el grant previamente persistido;
- mismo operation_id + intención diferente: `ConcurrencyError`;
- no existe operación: sigue el flujo de preparación y la escritura transaccional.

El adaptador conserva además su comparación completa de procedencia al recibir una repetición directa del mismo comando. La recuperación del servicio evita que una repetición secuencial regenere IDs/TTY/timestamp y convierta un commit confirmado con respuesta perdida en un conflicto artificial.

La exclusión global del primer bootstrap sigue protegida por `BEGIN IMMEDIATE` y el guard histórico del adaptador. Dos intentos distintos no pueden crear dos administradores. Para reintentos realmente concurrentes con el mismo operation_id, el adaptador sigue exigiendo que el comando de escritura coincida exactamente; una futura CLI deberá conservar el identificador de operación y no crear una segunda intención independiente.

## Pruebas adicionales

- El servicio recupera el grant existente sin volver a consultar Clock ni emitir nueva procedencia.
- Un operation_id reutilizado para otro USER se rechaza.
- El adaptador reconstruye exactamente el comando persistido mediante `get_operation`.
