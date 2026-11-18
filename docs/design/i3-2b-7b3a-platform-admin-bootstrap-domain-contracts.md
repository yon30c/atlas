# I3-2B.7B.3A — contratos de dominio para bootstrap offline

**Estado:** contratos 7B.3A y adaptador offline 7B.3B implementados y validados por el propietario en Debian.  
**Alcance:** contratos de dominio y puerto. No implementa persistencia de bootstrap, servicio, CLI ni provisión real.  
**PR:** #16 — permanece Draft, abierto y sin merge.

## 1. Objetivo

Definir una intención inmutable para conceder la primera autoridad Platform Admin, una procedencia técnica inmutable de la ejecución local y un comando de dominio que vincule solicitud, procedencia y concesión. El adaptador offline futuro recibirá ese comando en lugar de aceptar un `PlatformAdminGrant` arbitrario.

## 2. Contratos

### `PlatformAdminBootstrapRequest`

- `operation_id`: UUIDv4 canónico que identifica la intención y permite idempotencia.
- `user_id`: UUIDv4 del usuario Atlas existente que recibirá la autoridad.
- `permissions`: `frozenset` tipado con valores `PlatformAdminPermission` (no strings libres) que debe contener exactamente:
  - `association.suspend`
  - `association.reactivate`

No se admiten permisos parciales, wildcard, strings libres ni ampliación implícita.

### `PlatformAdminBootstrapProvenance`

- `event_id` y `grant_id`: UUIDv4 canónicos y distintos.
- UID real y efectivo: enteros no negativos, excluyendo booleanos.
- `terminal_id`: identificador de terminal no vacío, limitado y sin caracteres de control.
- `confirmed_at`: instante consciente de zona horaria UTC.

**Límite de confianza:** UID y terminal describen el contexto técnico del proceso local. No demuestran identidad humana, autenticación ni autorización del operador. La confirmación interactiva deliberada deberá implementarse y verificarse en la fase CLI; estos contratos no simulan esa interacción.

### `PlatformAdminBootstrapCommand`

Vincula solicitud, procedencia y grant y rechaza inconsistencias:
- grant y solicitud deben referirse al mismo UserId y conjunto exacto de permisos;
- grant_id y bootstrap_event_id deben coincidir con la procedencia;
- el método debe ser `offline_bootstrap`;
- la concesión inicial debe estar ACTIVE en revisión 1;
- `issued_at` y `not_before` deben coincidir con `confirmed_at`;
- `expires_at` debe ser exactamente `confirmed_at + 90 días`.

El comando no reemplaza la verificación de la identidad USER canónica dentro de la transacción SQLite del adaptador futuro.

## 3. Puerto actualizado

`PlatformAdminBootstrapPort.provision_first_admin(command)` recibe el comando validado y devuelve la concesión persistida. La implementación futura tendrá que:
1. buscar primero `operation_id`;
2. devolver el resultado existente solo si la intención y procedencia coinciden exactamente;
3. rechazar replay conflictivo;
4. para una operación nueva, exigir ausencia de cualquier evento/grant histórico;
5. serializar comprobación e inserción dentro de una transacción;
6. persistir evento y grant atómicamente y revalidar la identidad canónica USER activa en esa misma transacción.

El puerto permanece separado del reader runtime y no debe añadirse a `SQLiteLocalAuthorityUnitOfWork`.

## 4. Pruebas añadidas

`tests/unit/test_platform_admin_bootstrap_contracts.py` cubre:
- permisos exactos obligatorios;
- UUIDv4 canónicos;
- UIDs, terminal y timestamp UTC;
- consistencia entre solicitud, procedencia y grant;
- vigencia exacta de 90 días;
- estado inicial ACTIVE/revisión 1;
- inmutabilidad de solicitud y procedencia.

## 5. Fuera de alcance y siguiente fase

No se añadió servicio, adaptador writer, CLI, integración runtime ni operación de recuperación de administradores revocados. No se ejecutó bootstrap ni se modificó ninguna base de datos.

**Siguiente slice:** I3-2B.7B.3B, adaptador SQLite offline, idempotencia transaccional, concurrencia, rollback e integridad; usar exclusivamente bases temporales en pruebas.


## 6. I3-2B.7B.3B — adaptador SQLite offline

Se implementó `SQLitePlatformAdminBootstrapAdapter` en `src/atlas/adapters/sqlite/platform_admin_bootstrap.py`. El adaptador recibe únicamente `SQLiteDatabase` y no se compone en `SQLiteLocalAuthorityUnitOfWork`, factory runtime, HTTP ni workers.

### Orden transaccional

Cada intento abre la transacción existente `SQLiteDatabase.unit_of_work()`, que utiliza `BEGIN IMMEDIATE`. Bajo ese lock:

1. Busca primero `operation_id` mediante JOIN de evento y grant.
2. Si existe, compara IDs de evento/grant, sujeto, identidad/revisión, UIDs, terminal, confirmación UTC, permisos, método y ventana de emisión. Coincidencia exacta devuelve la concesión ya persistida; diferencias producen `ConcurrencyError`.
3. Si no existe, exige que no haya ningún evento ni grant histórico.
4. Resuelve el USER mediante `SQLiteIdentityAuthority` enlazada a la misma unidad de trabajo; exige identidad canónica ACTIVE y coincidencia exacta de identity_id/revision.
5. Inserta evento y grant dentro de la misma transacción. V25 mantiene las FKs diferidas circulares y triggers de identidad/permisos.
6. Relee el grant mediante el decoder del reader canónico y compara el resultado con el comando antes de permitir el commit.

Un fallo, incluida una excepción durante la verificación posterior a las inserciones, provoca rollback conjunto. `BEGIN IMMEDIATE` serializa intentos concurrentes: un único bootstrap nuevo puede superar el guard histórico.

### Recuperación e idempotencia

El lookup por `operation_id` precede deliberadamente al guard de historial. Así, el replay exacto continúa recuperable después de la primera provisión. Un replay con identidad, permisos o procedencia distinta se rechaza. Una operación diferente, incluso si el grant histórico está revocado, no puede reutilizar el bootstrap inicial; recuperación/reemplazo exige un flujo administrativo futuro separado.

### Pruebas añadidas

`tests/unit/test_sqlite_platform_admin_bootstrap.py` cubre:
- provisión y lectura posterior del grant/evento;
- replay exacto sin duplicados;
- conflicto por replay alterado;
- rechazo de otro sujeto y de otra operación tras historial;
- rechazo de USER suspendido y revisión obsoleta;
- rollback forzado después de insertar evento y grant;
- aislamiento respecto de la UoW runtime;
- dos intentos concurrentes, con exactamente un resultado creado.

Estas pruebas están publicadas, pero **requieren ejecución en Debian**. No se ha ejecutado el bootstrap real ni se ha tocado una base de datos del usuario.


## 7. Validación del propietario — I3-2B.7B.3A y 7B.3B

El propietario ejecutó dos checkpoints consecutivos de la suite completa en Debian:

| Checkpoint | Suite completa | Resultado de compilación |
|---|---:|---|
| Inicial | 1,433 pruebas en 26.282 s | `COMPILE_EXIT_CODE=0` |
| Más reciente | **1,443 pruebas en 25.743 s — OK** | **`COMPILE_EXIT_CODE=0`** |

La segunda ejecución es el checkpoint vigente y confirma diez pruebas adicionales respecto al primero. Ambos resultados fueron comunicados por el propietario; no se atribuyen a CI ni a una ejecución local del asistente.

Con este resultado quedan validados por el propietario:
- los contratos de dominio y el puerto de bootstrap de 7B.3A;
- la persistencia V25, el reader runtime y el adaptador SQLite offline de 7B.3B;
- los casos automatizados publicados para idempotencia, conflicto, USER activo/revisión, rollback, aislamiento runtime y concurrencia.

**Límite importante:** la validación usa bases SQLite temporales de pruebas. No se ejecutó el bootstrap real, no se creó ningún Platform Admin y no se modificó ninguna base productiva.

**Siguiente slice:** I3-2B.7B.3C — servicio de aplicación de bootstrap. Antes de implementarlo se inspeccionarán las convenciones de servicios, Clock, composición y errores del repositorio. El servicio coordinará identidad canónica, tiempo confiable y adaptador offline; todavía no añadirá CLI ni ejecutará provisión real.


## 8. I3-2B.7B.3C — servicio de aplicación

Se publicó el siguiente incremento de aplicación:
- `src/atlas/application/platform_admin_bootstrap.py`
- `tests/unit/test_platform_admin_bootstrap_service.py`
- `docs/design/i3-2b-7b3c-platform-admin-bootstrap-application-service.md`

El servicio resuelve el USER canónico, exige estado ACTIVE, toma el instante UTC del puerto `Clock`, genera los identificadores UUIDv4 de evento y grant, construye el grant inicial exacto de 90 días y delega la escritura al puerto offline. No incorpora el writer a runtime ni abre una transacción paralela.

La lectura de identidad del servicio es preparatoria: el adaptador SQLite conserva la revalidación autoritativa de USER/identity_id/revisión dentro de `BEGIN IMMEDIATE`, junto con idempotencia, exclusividad histórica y escritura atómica.

Se añadieron siete pruebas unitarias de servicio y una prueba de recuperación en el adaptador SQLite. **Aún no se han ejecutado en Debian**; la validación del propietario queda pendiente. No se debe considerar 7B.3C cerrada hasta recibir el resultado de las pruebas focalizadas, suite completa y compileall.

La implementación inicial reveló que regenerar IDs/procedencia en cada llamada impediría recuperar un commit exitoso cuya respuesta se perdió. Para cerrar ese hueco, el puerto offline ahora expone `get_operation(operation_id)`; el adaptador reconstruye el comando persistido y el servicio recupera el grant antes de generar nueva procedencia. El mismo operation_id con otro USER/permisos se rechaza. La comparación completa de procedencia en la escritura del adaptador se conserva.

La futura fase 7B.3D seguirá siendo responsable de TTY real, captura de UID/terminal y confirmación interactiva. No se ha creado ni ejecutado CLI y no se ha realizado ningún bootstrap real.


## 9. Validación del propietario — I3-2B.7B.3C

El propietario validó en Debian la suite completa: **1,451 tests en 25.087 s — OK**; `python -m compileall -q src tests` terminó con **`COMPILE_EXIT_CODE=0`**. Quedan validados el servicio de aplicación y la recuperación idempotente mediante `get_operation(operation_id)` en el puerto/adaptador SQLite. No se ejecutó el bootstrap real, no se creó un Platform Admin y no se modificó ninguna base productiva.

**Siguiente slice:** I3-2B.7B.3D — diseño e implementación de la CLI offline, separada del entrypoint de consola habitual y sin integración HTTP/runtime.
