# Diseño aprobado: guard persistente de intentos de autenticación

**Estado:** diseño aprobado por el propietario el 2026-11-22; implementación inicial publicada en la rama, pendiente de validación local.
**Rama:** `work/atlas-mvp-runtime`.
**Alcance:** contrato de reserva, política de throttling, persistencia SQLite y secuencia de `NativeAuthenticationService`. No habilita login operativo ni composición en consola.

## 1. Decisiones aprobadas

- Almacenamiento: mismo archivo SQLite canónico de autoridad.
- Cada operación del guard usa una transacción `BEGIN IMMEDIATE` breve e independiente.
- Ninguna operación del guard se ejecuta mientras la UoW de autenticación esté abierta.
- Argon2id (verify y hash de rehash) se ejecuta fuera de transacciones SQLite de escritura.
- La cuenta de throttling se delimita por `issuer_id` y `LoginHandle` normalizado.
- El guard es compartido entre procesos que usan el mismo archivo y falla cerrado.

## 2. Política

| Parámetro | Valor |
|---|---:|
| Ventana móvil de fallos | 15 minutos |
| Fallos retenidos para el cálculo | 5 o más, dentro de la ventana |
| Demora tras el 1.er fallo | 1 minuto |
| Demora tras el 2.º fallo | 2 minutos |
| Demora tras el 3.er fallo | 4 minutos |
| Demora tras el 4.º fallo | 7 minutos |
| Demora tras el 5.º y siguientes | 15 minutos |
| Reservas simultáneas máximas por cuenta | 2 |
| TTL de cada reserva | 120 segundos |
| Éxito confirmado | elimina el historial de fallos de esa cuenta |
| Reserva abandonada/expirada | no cuenta como fallo |

La demora se calcula al completar un fallo: se cuenta el fallo recién completado junto con los fallos anteriores aún dentro de la ventana. El bloqueo vigente respeta cualquier `blocked_until` futuro, aunque el fallo que lo originó alcance el límite de antigüedad de la ventana antes de que termine el bloqueo. Los fallos fuera de la ventana dejan de contribuir al cálculo de la siguiente demora. Al llegar exactamente a `blocked_until`, el bloqueo expira; no existe bloqueo permanente. La secuencia 1+2+4+7 permite que el quinto fallo ocurra a los 14 minutos, todavía dentro de la ventana de 15 minutos.

Las reservas activas no son fallos. Una reserva expirada se elimina durante la siguiente operación atómica del guard. Una reserva no puede completarse después de su vencimiento; ese resultado es indisponibilidad y nunca puede producir un proof.

## 3. Contrato de reserva

El puerto sustituye la secuencia ambigua `is_allowed → record_failure/record_success` por operaciones explícitas:

1. `begin_attempt(issuer_id, login_handle, at) → AttemptReservation`: reserva atómicamente un cupo; devuelve reserva opaca con ID y expiración, o deniega si existe demora activa o se alcanzó el máximo de concurrencia.
2. `complete_failure(reservation, at)`: consume una reserva vigente, registra un fallo y calcula su demora.
3. `complete_success(reservation, at)`: consume una reserva vigente y reinicia los fallos de esa cuenta.
4. `abandon_attempt(reservation)`: elimina una reserva sin registrar fallo.

La reserva es opaca, vinculada internamente a la cuenta y no contiene contraseña, PHC, proof ni identificadores de identidad adicionales. Las operaciones de finalización son idempotentes solo si el contrato lo define explícitamente; de lo contrario, una reserva ausente, repetida o expirada falla cerrado.

La clave persistida de cuenta será un digest determinista SHA-256 de una codificación canónica con separación de dominio, issuer y LoginHandle normalizado. El adaptador normaliza el LoginHandle en su propia frontera para que diferencias de mayúsculas no creen buckets de throttling distintos. Es un pseudónimo estable para indexación, no se presentará como secreto ni como protección frente a análisis offline. No se almacenará una copia adicional del handle legible.

## 4. Secuencia de autenticación

1. Validar LoginHandle y contraseña.
2. Abrir una UoW breve, resolver issuer por realm confiable y cerrar la UoW.
3. Reservar intento mediante el guard; denegar antes de Argon2id si no hay cupo.
4. Abrir una UoW breve para leer el autenticador por issuer + handle; cerrarla. La consulta de credenciales ocurre después de reservar el intento.
5. Ejecutar Argon2id fuera de cualquier UoW y transacción SQLite de escritura. Para handle desconocido se conserva la verificación dummy. Un mismatch, handle desconocido o autenticador inactivo completa el fallo en el guard y devuelve error genérico.
6. Preparar fuera de transacción el rehash si corresponde.
7. Abrir una UoW breve; volver a resolver issuer y autenticador y comprobar estado, subject y `credential_revision`. Si cambió cualquier dato, denegar y abandonar la reserva, sin contarlo como contraseña incorrecta.
8. Aplicar rehash con CAS si procede, crear proof y confirmar la UoW.
9. Después del commit, completar éxito en el guard. Solo si esto se confirma se devuelve la referencia raw del proof.
10. Ante excepción interna, indisponibilidad de Argon2id, conflicto de revisión o fallo de persistencia, intentar abandonar la reserva; nunca emitir proof.

Si el commit del proof ocurrió pero completar éxito falla, la referencia raw no se devuelve. El registro proof queda inaccesible para el caller y caduca por su TTL. No se intenta inferir éxito del guard.

## 5. Esquema y transacciones SQLite

La migración añadirá tablas separadas para reservas y fallos, con claves compuestas de issuer/cuenta, IDs opacos, timestamps UTC normalizados y restricciones/índices para consultas por ventana y vencimiento.

Cada operación del guard:
- abre una conexión propia desde la misma `SQLiteDatabase`;
- inicia `BEGIN IMMEDIATE`;
- elimina hasta 256 reservas expiradas y hasta 256 fallos ya vencidos mediante índices de retención;
- calcula bloqueo/concurrencia y aplica la transición;
- confirma o revierte íntegramente;
- nunca se ejecuta anidada dentro de `SQLiteLocalAuthorityUnitOfWork`.

No se introducen tablas de secretos, sesiones, tokens, IPs ni contenido de credenciales. Los fallos fuera de ventana dejan de contribuir al cálculo; la limpieza física es oportunista y acotada a 256 filas por operación de inicio. Las reservas expiradas también se limpian en lotes de hasta 256. Los índices dedicados permiten esa recolección sin recorrer todas las filas. No se añade un daemon de limpieza.

## 6. Pruebas de aceptación que ejecutará el propietario en Debian

- política exacta 1/2/4/7/15, ventana móvil, expiración de demora y bloqueo activo hasta `blocked_until`;
- límite de dos reservas y rechazo de una tercera;
- variantes de mayúsculas del mismo LoginHandle comparten el mismo bucket;
- finalización de reservas correctas, fallidas, repetidas y expiradas;
- abandono no cuenta como fallo;
- éxito reinicia fallos sin borrar otras reservas activas;
- recuperación de reservas expiradas después de reinicio;
- concurrencia multiproceso sobre el mismo archivo SQLite;
- limpieza oportunista acotada de filas vencidas pertenecientes a cuentas inactivas;
- ausencia de bloqueo largo durante Argon2id;
- guard indisponible, commit incierto, error Argon2id y cambio concurrente de credencial nunca producen proof;
- handle desconocido y contraseña incorrecta conservan respuesta genérica;
- migración histórica checksum-safe y base ya migrada;
- regresión de todos los tests existentes del servicio de autenticación.

## 7. Estado de implementación publicado — 2026-11-22

Se publicaron en la rama de trabajo el puerto de reservas, la migración SQLite V28, el adaptador `SQLiteAuthenticationAttemptGuard`, la reestructuración de `NativeAuthenticationService` y pruebas unitarias del servicio y del adaptador. La migración V28 forma parte de `SQLITE_MIGRATIONS`. El servicio resuelve el issuer, reserva, consulta el autenticador, ejecuta Argon2id fuera de UoW y revalida issuer/autenticador/estado/subject/revisión antes de persistir el proof.

**Estado:** implementación publicada y revisada estáticamente en los archivos del incremento; validación local por el propietario pendiente. No se han ejecutado pruebas ni compilaciones desde GitHub. No se habilitó composición operativa, login, Workspace ni CAM.

## 8. Límites

Este incremento no configura la clave HMAC, no provisiona issuer/owner/Grant, no habilita bootstrap, no conecta consola/Workspace/CAM, no crea endpoints ni sesiones y no modifica el host. El guard no ofrece por sí solo límites por IP/origen; cualquier límite de origen futuro deberá usar datos confiables del servidor/proxy, nunca un valor declarado por el cliente.
