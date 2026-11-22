# Auditoría estática: frontera de control de intentos de autenticación

**Fecha:** 2026-11-22  
**Rama inspeccionada:** `work/atlas-mvp-runtime`  
**HEAD de referencia:** `598f461ee5b42b41d3792bc9dbd3fcf8f983ace8`  
**Estado:** auditoría base; las decisiones de implementación y política fueron aprobadas por el propietario el 2026-11-22. La especificación aprobada está en `native-authentication-attempt-guard-approved-design.md`.  
**Alcance:** revisar el contrato `AuthenticationAttemptGuardPort`, su punto de invocación en `NativeAuthenticationService` y la transacción SQLite compartida.

## 1. Resumen

El servicio de autenticación y la emisión/admisión de proofs ya están implementados y tienen validación local histórica. Sin embargo, no existe un adaptador productivo para el guard de intentos. La interfaz actual tampoco define reservas de intentos concurrentes ni identifica cada intento individual.

La inspección detectó además una interacción importante con SQLite: `SQLiteLocalAuthorityUnitOfWork` inicia `BEGIN IMMEDIATE`. `NativeAuthenticationService.authenticate()` abre esa UoW antes de consultar el guard y mantiene la transacción durante la verificación Argon2id. Por tanto, no es seguro implementar el guard como otro writer independiente sobre el mismo archivo SQLite mientras esa UoW permanezca abierta.

No se debe conectar login operativo hasta cerrar este contrato y validar su comportamiento entre procesos.

## 2. Evidencia inspeccionada

- `src/atlas/ports/authentication_attempt_guard.py`: el puerto actual expone `is_allowed(issuer_id, login_handle, at)`, `record_failure(...)` y `record_success(...)`. Exige atomicidad/compartición en su docstring, pero no define un ID de reserva, vencimiento de reserva ni una operación explícita de abandono.
- `src/atlas/authentication/service.py`: `authenticate()` entra primero en `unit_of_work_factory()`, consulta `is_allowed`, ejecuta `verify_password()` y llama `record_failure()` antes de salir de la UoW. En el camino exitoso confirma el proof y llama `record_success()` después de salir de la UoW.
- `src/atlas/adapters/sqlite/authorization_unit_of_work.py`: la UoW comparte una transacción y solo confirma cuando la aplicación llama `commit()`.
- `src/atlas/adapters/sqlite/database.py`: `SQLiteDatabase.unit_of_work()` inicia explícitamente `BEGIN IMMEDIATE`; la base abre una conexión por operación.
- `tests/unit/test_native_authentication_service.py`: los tests inyectan `FakeAttemptGuard`; no hay prueba de persistencia, concurrencia entre procesos ni recuperación de intentos pendientes.
- `src/atlas/adapters/hmac_verified_identity_context_attestor.py`: existe el adaptador HMAC-SHA256 y exige una clave de al menos 256 bits. Su fuente, carga, rotación y ciclo de vida no están conectados a un composition root operativo.
- `docs/implementation/cycle-3-2-c1-progress.md` y `docs/design/native-proof-to-verified-operation-context-integration.md`: confirman que no existe guard productivo ni provisión operativa de la clave.

## 3. Hallazgos técnicos

### H1 — La interfaz no expresa una reserva concurrente

Una secuencia `is_allowed()` → cálculo Argon2id → `record_failure()` deja una ventana en la que varios procesos pueden observar simultáneamente que la cuenta está permitida y comenzar verificaciones paralelas. El puerto no identifica ni limita explícitamente intentos pendientes.

Para un guard compartido entre procesos, el inicio de cada intento debe ser una operación atómica que reserve capacidad antes de ejecutar el hash. La reserva debe tener identificador y expiración para poder finalizarla o recuperarla si el proceso muere.

### H2 — Riesgo de bloqueo SQLite si el guard comparte archivo y conexión independiente

La UoW de autoridad inicia `BEGIN IMMEDIATE` antes de la llamada al guard y mantiene el writer reservation durante Argon2id. Si un adaptador SQLite independiente intenta escribir el estado del guard en el mismo archivo durante esa ventana, compite con la transacción activa y puede bloquearse hasta el timeout o fallar por contención.

Usar la misma conexión/UoW evitaría el segundo writer, pero exige cambiar el contrato del puerto y definir cómo se confirma un fallo de autenticación: actualmente la excepción sale del bloque y provoca rollback, por lo que un registro de fallo escrito en esa UoW también se perdería salvo que el flujo transaccional cambie expresamente.

### H3 — Argon2id se ejecuta dentro de una transacción de escritura

La verificación Argon2id ocurre mientras `BEGIN IMMEDIATE` está activo. El coste deliberado del hash puede mantener bloqueadas otras escrituras de las autoridades locales. Conviene separar la verificación costosa de la transacción breve que vuelve a leer estado/revisión y emite el proof.

La separación debe conservar la relectura de issuer/authenticator y la comparación de `credential_revision` antes de emitir el proof. No se puede confiar en el snapshot previo al hash.

### H4 — Falta política cuantificada

Los documentos exigen ventana, umbral, demoras/backoff, límite de concurrencia, expiración de reservas, retención y política de reset/decay; no se encontró una política numérica aprobada para esos valores. Tampoco debe existir un bloqueo permanente que permita denegar el servicio al propietario.

No fijar estos valores por conveniencia dentro del adaptador. Deben ser configuración explícita revisada y cubierta por pruebas.

## 4. Alternativas de almacenamiento

### A. Guard en el mismo archivo SQLite de autoridad

Es la opción preferida para mantener un único estado durable local, pero solo si cada operación del guard usa una transacción corta y no se ejecuta mientras la UoW de autenticación mantiene `BEGIN IMMEDIATE`.

Requiere:
- reserva atómica en una transacción breve;
- finalizar fallo/éxito/abandono después de cerrar la UoW de autoridad;
- no mantener una transacción SQLite abierta durante Argon2id;
- relectura y comparación de issuer, autenticador, estado y revisión dentro de la UoW breve de emisión del proof;
- pruebas concurrentes multiproceso y de recuperación de reservas expiradas.

### B. Archivo SQLite separado para el guard

Evita contención con la UoW de autoridad y mantiene coordinación local entre procesos que compartan el archivo del guard. Añade, sin embargo, otra base que debe tener política propia de permisos, ubicación, backup, retención, migración y recuperación. También requiere decidir cómo se representa la clave de cuenta sin exponer innecesariamente el login handle.

### C. Contador en memoria

**Rechazado para uso operativo.** No sobrevive reinicios y no coordina procesos independientes.

## 5. Secuencia de aplicación recomendada para revisión

1. Cambiar el contrato a una reserva explícita, por ejemplo `begin_attempt` → `complete_failure` / `complete_success` / `abandon_attempt`, con ID opaco y expiración. Los nombres finales quedan pendientes de diseño.
2. Aprobar una política cuantificada: ventana, umbral, curva y máximo de demora, máximo de intentos pendientes, TTL de reserva, retención y reset/decay.
3. Elegir el almacenamiento. Recomendación: mismo archivo SQLite con transacciones breves del guard, siempre fuera de la UoW que verifica/emite el proof; no mantener `BEGIN IMMEDIATE` durante Argon2id.
4. Reestructurar el servicio para reservar antes del hash, ejecutar Argon2id fuera de la transacción de escritura, revalidar estado/revisión y emitir el proof en una UoW breve, y finalizar la reserva después de cerrar esa UoW.
5. Si el guard no puede finalizar con seguridad, no devolver el proof. Una reserva abandonada por caída debe expirar de forma determinista; no debe transformarse en una autorización.
6. Añadir pruebas de contención, intentos simultáneos, fallo del guard, crash/recovery, expiración, reset, y que nunca se emita proof si no se confirma el resultado requerido.

Esta secuencia es una recomendación de diseño, no una aprobación para cambiar el contrato o los umbrales.

## 6. Dependencias que permanecen separadas

- **Clave HMAC:** el adaptador existe, pero falta un proveedor/configuración secreta confiable para la composición operativa, además de política de rotación. La clave debe permanecer fuera de SQLite, logs y entradas del caller.
- **Bootstrap inicial:** sigue pendiente la decisión explícita del perfil CAM del Grant inicial. No crear un Grant global ni inventar Project, Environment o Workspace para hacer avanzar el login.
- **I-3 / CAM:** la fábrica de `OperationContext` no vuelve seguros automáticamente a los consumidores existentes. La reconciliación de servicios sensibles sigue siendo necesaria antes de conectar Workspace.
- **Consola:** `LocalConsoleRequestFactory` sigue generando identidad sintética basada en la cuenta del sistema operativo. No debe alcanzar capacidades protegidas.

## 7. Estado de validación

Esta auditoría es estática. No se ejecutaron pruebas, compilaciones, migraciones, probes ni operaciones sobre bases reales. No se modificó código ni se habilitó login.

La validación local focalizada de `/plan` (14 tests y `compileall`) es independiente y no cubre autenticación, guard, HMAC, bootstrap ni Workspace.

## 8. Decisión requerida antes del siguiente cambio de código

Aprobar:
1. el contrato de reserva/finalización de intentos;
2. la política numérica de throttling y recuperación;
3. el almacenamiento compartido y su relación transaccional con la UoW de autoridad.

Hasta entonces, mantener `NativeAuthenticationService` sin composición operativa y mantener deshabilitadas las capacidades protegidas de consola.


## 9. Aprobación del propietario — 2026-11-22

El propietario aprobó:
- almacenamiento en el mismo archivo SQLite canónico;
- transacciones breves e independientes del guard, fuera de la UoW de autenticación;
- reservas explícitas por intento con ID opaco y TTL de 120 segundos;
- ventana móvil de 15 minutos y demoras 1/2/4/7/15 minutos;
- máximo de dos intentos simultáneos por cuenta;
- éxito confirmado reinicia fallos; abandono/expiración no cuenta como fallo;
- Argon2id fuera de transacciones SQLite de escritura;
- relectura del issuer/autenticador y comparación de estado/revisión antes de emitir proof.

La interpretación exacta, el algoritmo de reserva/finalización, el pseudónimo de cuenta y los criterios de aceptación están fijados en `docs/design/native-authentication-attempt-guard-approved-design.md`.

**Siguiente paso:** implementar el contrato y adaptador SQLite, reestructurar `NativeAuthenticationService`, añadir pruebas unitarias y multiproceso, y actualizar la composición sin habilitar login operativo.


## 10. Revisión estática de la implementación inicial — 2026-11-22

Esta sección actualiza el estado de §§1–9, que documentan la auditoría base y las decisiones anteriores a la implementación. Se revisó la rama `work/atlas-mvp-runtime` después de publicar el primer incremento.

### Cambios publicados

- Puerto explícito `AuthenticationAttemptGuardPort` con reserva opaca, expiración, finalización de fallo/éxito y abandono.
- Migración `CORE_SCHEMA_V28` con tablas separadas para reservas y fallos, índices por cuenta/expiración/ventana.
- Registro de V28 en `SQLITE_MIGRATIONS` y exportación del símbolo desde el paquete SQLite.
- Adaptador `SQLiteAuthenticationAttemptGuard` con transacciones independientes `BEGIN IMMEDIATE`, digest de cuenta con separación de dominio y normalización defensiva del LoginHandle, TTL de 120 s, máximo de dos reservas y política 1/2/4/7/15. La recolección oportunista elimina en lotes de hasta 256 reservas vencidas y hasta 256 fallos ya vencidos, incluso para cuentas inactivas.
- Servicio reordenado: issuer en UoW breve → reserva → lectura de autenticador en otra UoW → Argon2id fuera de UoW → relectura y validación de estado/revisión → persistencia del proof → confirmación de éxito del guard antes de devolver la referencia.
- Pruebas unitarias del servicio corregidas y nuevo archivo de pruebas para migración, concurrencia entre threads y procesos separados, backoff, ventana, expiración, limpieza de cuentas inactivas, abandono, reset y consumo único.

### Hallazgos corregidos durante la revisión

1. La cuarta demora se cambió a 7 minutos conforme a la aprobación del propietario. Esto sitúa el quinto fallo a los 14 minutos en el caso secuencial límite, dentro de la ventana de 15 minutos.
2. Se corrigió la limpieza de una reserva vencida en `_consume`: la eliminación se confirma antes de informar que la reserva no puede completarse, evitando que el rollback restaure la fila expirada.
3. La limpieza oportunista global, acotada a 256 filas por tabla, se confirma incluso cuando la nueva reserva es denegada por bloqueo o concurrencia. Los fallos con `blocked_until` futuro se conservan hasta que expire el bloqueo.
4. Se corrigió la secuencia del servicio para reservar antes de leer el autenticador. La lectura de issuer ocurre primero porque es necesaria para delimitar la cuenta; el acceso a credenciales y Argon2id ocurren después de reservar.
5. Se corrigió un bloque de importación roto en `test_native_authentication_service.py` que contenía secuencias literales `\\n`.
6. Se incorporó V28 a la tupla ordenada de migraciones y a las exportaciones del paquete SQLite.

### Límites de esta revisión

- Revisión estática de los archivos publicados; no se ejecutaron tests, compileall, migraciones, probes ni workflows.
- Los tests nuevos no constituyen evidencia de que la implementación pase. La suite focalizada y la suite completa deben ejecutarse en Debian por el propietario.
- La implementación no está conectada a una composición de login de producción. No se habilitan endpoints, bootstrap, Workspace, CAM ni consola autenticada.
- La clave HMAC sigue sin proveedor/provisión secreta confiable y el perfil CAM del Grant inicial continúa pendiente.

**Siguiente paso:** terminar la revisión estática de consistencia de imports, contratos y cobertura; después entregar al propietario los comandos focalizados para validar en Debian. Cualquier ajuste posterior se publicará primero en esta rama y requerirá nueva validación local.


## 11. Segunda pasada estática: normalización, retención y multiproceso — 2026-11-22

La revisión adicional del adaptador y sus pruebas produjo estos ajustes:

- El adaptador construye el digest usando `LoginHandle(login_handle).value`, de modo que variantes de mayúsculas no generen buckets de throttling separados aunque un caller omita la normalización previa del servicio.
- La recolección oportunista es global y acotada: cada `begin_attempt` elimina como máximo 256 reservas expiradas y 256 fallos cuyo tiempo de retención terminó. Índices dedicados cubren vencimiento y retención; no se requiere un daemon.
- Una fila de fallo con `blocked_until` futuro no se elimina por salir de la ventana de conteo. El bloqueo se respeta hasta su vencimiento exacto; después, el registro puede limpiarse. Los fallos fuera de ventana no influyen en el cálculo del siguiente backoff.
- Se añadió prueba de concurrencia con procesos separados, además de la prueba entre threads, y prueba de limpieza de registros pertenecientes a cuentas inactivas.
- Se añadieron regresiones del servicio para demostrar que la indisponibilidad al completar fallo no emite proof y que la indisponibilidad al completar éxito nunca devuelve la referencia raw, aunque la metadata del proof ya se haya confirmado.
- El instante de reserva se toma después de resolver el issuer, evitando consumir TTL durante la UoW inicial.

**Revisión:** lectura estática de los archivos de puerto, adaptador, migración, servicio, exportaciones SQLite y pruebas nuevas/actualizadas. La comparación GitHub confirma que la rama de trabajo está 69 commits por delante y 0 por detrás de `main`; los cambios de este incremento permanecen únicamente en `work/atlas-mvp-runtime`.

**Validación local pendiente:** no se ejecutaron tests, compileall, migraciones ni workflows desde GitHub. La prueba multiproceso usa el contexto `spawn` y debe comprobarse en el entorno Debian del propietario. No se debe considerar aprobada la implementación hasta recibir sus resultados.
