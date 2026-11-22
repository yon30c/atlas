# Auditoría de brecha: composición de autenticación nativa

**Fecha:** 2026-11-22  
**Rama revisada:** `work/atlas-mvp-runtime`  
**HEAD de código validado por el propietario:** `29e900a1129efbb83c8e4b867c99d37d66473c55`  
**Estado:** revisión estática completada; no implementa ni autoriza login operativo.  
**Alcance:** identificar qué piezas existen, qué puntos de composición las conectan (o no) y qué decisiones faltan antes de exponer autenticación al runtime.

## 1. Conclusión

El guard de intentos y el servicio de autenticación nativa están implementados y la suite completa de la rama fue validada localmente por el propietario. Sin embargo, **no existe una composición operativa de login**.

La implementación actual es una capacidad de aplicación/persistencia aislada. No se debe conectar a la consola cotidiana ni a Workspace hasta cerrar la cadena de bootstrap, consumo del proof, identidad USER verificada y autorización CAM. La identidad sintética que produce la consola no puede sustituir esa cadena.

## 2. Piezas verificadas en GitHub

| Componente | Evidencia revisada | Alcance actual |
|---|---|---|
| Servicio de autenticación | `src/atlas/authentication/service.py` | `NativeAuthenticationService` verifica credenciales, reserva intentos, revalida autoridad y persiste un proof de un solo uso. No es un endpoint ni un entrypoint de login. |
| Guard SQLite | `src/atlas/adapters/sqlite/authentication_attempt_guard.py` | `SQLiteAuthenticationAttemptGuard` ejecuta transacciones `BEGIN IMMEDIATE` independientes sobre una instancia `SQLiteDatabase`. |
| Migración | `src/atlas/adapters/sqlite/authentication_attempt_migration.py`, `migrations.py` | V28 crea tablas e índices de reservas/fallos y está registrada en `SQLITE_MIGRATIONS`. |
| UoW de autoridad | `src/atlas/adapters/sqlite/local_authority_unit_of_work.py` | Expone repositorios `native_identity` y `native_authentication` sobre una UoW compartida. |
| Composición de almacenamiento | `src/atlas/adapters/sqlite/authority_storage_composition.py` | Vincula una instancia `SQLiteDatabase` con `SQLiteLocalAuthorityUnitOfWorkFactory`; no crea directorios, no inicializa ni migra la base y no compone el servicio de autenticación. |
| Consola | `src/atlas/cli.py` | Compone conversación, proveedor Ollama y planificación F1. No instancia `NativeAuthenticationService` ni el guard. |
| Bootstrap de aplicación | `src/atlas/bootstrap.py` | Construye el planificador; no compone autenticación. |

La revisión cubrió los puntos de composición de consola, bootstrap y almacenamiento de autoridad mencionados arriba. No se encontró una ruta de login conectada a la consola en esos puntos.

## 3. Frontera transaccional que debe preservar una futura composición

La composición futura debe construir **una sola instancia canónica** de `SQLiteDatabase` y derivar de ella tanto:

- `SQLiteLocalAuthorityUnitOfWorkFactory(database)`, para que el servicio lea issuer/autenticador y persista proofs mediante los repositorios nativos;
- `SQLiteAuthenticationAttemptGuard(database)`, para que cada reserva/finalización use el mismo archivo SQLite canónico en una transacción corta e independiente.

No se debe crear accidentalmente un segundo archivo para el guard ni pasar una base distinta a cada dependencia. La identidad del objeto de base de datos debe comprobarse en el composition root, además de verificar la ruta canónica.

La composición de almacenamiento no aplica migraciones. La inicialización y aplicación de `SQLITE_MIGRATIONS` deben permanecer en un procedimiento explícito de provisión/administración; no deben introducirse como efecto lateral del arranque cotidiano de la consola.

Se mantienen las reglas aprobadas:

1. Resolver issuer en una UoW breve.
2. Reservar el intento antes de consultar el autenticador.
3. Ejecutar Argon2id fuera de UoW y de transacciones SQLite de escritura.
4. Releer issuer, autenticador, estado, subject y `credential_revision` antes de persistir el proof.
5. No devolver la referencia raw si no se confirma la finalización exitosa del guard.
6. Abandono/expiración no suma un fallo; la reserva conserva su TTL acotado.

## 4. La autenticación no termina al emitir un proof

El proof emitido por `NativeAuthenticationService` es una evidencia intermedia, opaca, de un solo uso y ligada a una audience. No es por sí solo un `VerifiedIdentityContext`, un `OperationContext` ni un Grant CAM.

La cadena posterior documentada debe mantenerse separada:

1. Admitir/consumir el proof exactamente una vez y para la audience esperada.
2. Resolver el binding nativo issuer/subject hacia la identidad canónica USER.
3. Revalidar estado y revisiones de identidad.
4. Construir un `VerifiedIdentityContext` efímero mediante la frontera de identidad verificada.
5. Derivar un `OperationContext` para una operación concreta.
6. Evaluar un Grant CAM exacto para el recurso, acción y scope solicitados.
7. Reconciliar los consumidores protegidos (I-3) antes de permitir que usen ese contexto.

El diseño `docs/design/native-proof-to-verified-operation-context-integration.md` sigue siendo una propuesta de integración; no autoriza a omitir etapas ni a conectar consumidores legacy.

## 5. Decisiones y dependencias pendientes

### 5.1 Bootstrap y Grant CAM inicial del propietario

El bootstrap de propietario no debe crear un Grant global ni inventar Project, Environment o Workspace. Antes de implementarlo hay que decidir expresamente el perfil CAM inicial: sujeto, recursos, acciones, scope, duración, renovación/revocación y límites de uso. No se deducen permisos a partir de que el actor sea el propietario ni de que el bootstrap sea local.

El contrato de Memory mantiene pendiente la evidencia técnica de acción directa del propietario para decisiones no delegables. El diseño de bootstrap LOCAL propone autenticación interactiva reciente mediante PAM y confirmación vinculada al descriptor, pero el protocolo de desafío/prueba todavía contiene decisiones técnicas pendientes y no está implementado.

### 5.2 Clave HMAC para identidad verificada

`HmacVerifiedIdentityContextAttestor` recibe una clave de al menos 256 bits por constructor. El código exige que la composición entregue esa clave; no define su procedencia, carga, permisos, rotación ni recuperación. Esas responsabilidades pertenecen a una fuente/proveedor confiable fuera de SQLite y fuera de entradas del caller.

No reutilizar por inferencia la clave del firmante de consistencia local: son usos y contratos distintos. Antes de componer el attestor deben fijarse la fuente de secreto, la referencia de clave, el propietario/permisos, la rotación y el comportamiento fail-closed cuando no esté disponible.

### 5.3 Otras dependencias

- La admisión/consumo del proof debe seguir siendo one-shot y audience-bound.
- La construcción de contexto USER debe revalidar autoridad; un proof válido no concede permisos CAM.
- La consola sintética actual permanece fuera de toda capacidad protegida.
- No habilitar Workspace read-only hasta completar identidad, bootstrap, Grant CAM e I-3.

## 6. Próximo incremento recomendado

**No implementar todavía un login de producción.** El siguiente trabajo debe ser una revisión/decisión explícita de:

1. perfil CAM mínimo del Grant inicial del propietario;
2. fuente y ciclo de vida de la clave HMAC del attestor de identidad verificada;
3. contrato final del desafío y prueba de acción directa del propietario para bootstrap LOCAL.

Una vez resueltas esas decisiones, se puede diseñar una composición autenticada aislada, sin conectarla inicialmente a la consola ni a Workspace. La implementación debe incluir pruebas de que UoW y guard usan la misma base canónica, que las migraciones se ejecutan solo mediante provisión explícita, que un proof no consumido no crea contexto USER y que cualquier fallo de guard/attestor/identidad deniega.

## 7. Validación y límites

El propietario confirmó en Debian 13 / `Atlas-VM-test`:

```text
Ran 1611 tests in 40.322s

OK (skipped=1)
```

También confirmó `.venv/bin/python -m compileall -q src tests` sin errores reportados. Esta evidencia valida la suite unitaria de la rama, no una migración sobre una base persistente real, un login desplegado, el bootstrap de propietario, el consumo E2E del proof ni Workspace/CAM.

No se ejecutaron pruebas, compilaciones, migraciones ni workflows desde GitHub. No se modificó código ejecutable, `main`, el host ni una base real.
