# Frontera de consistencia para operaciones del Assistant

> Estado: decisión de arquitectura F2.3.4.
> Rama: `feature/terminal-commands`.
> Alcance: definir las garantías necesarias antes de conectar capacidades del Assistant con CAM.
> Este documento no implementa autorización, admisión ni ejecución.

## 1. Problema

`OperationAuthorizationEvidence` enlaza una decisión CAM con actor, Grant, proyecto, entorno, acción, recurso y revisiones. La comparación local de esos claims y su ventana temporal no demuestra que las revisiones sigan vigentes ni impide que una revocación compita con la operación.

Un verificador que consulte cada repositorio por separado tiene una ventana TOCTOU: una fuente puede cambiar después de su lectura y antes del efecto. Una secuencia de lecturas exitosas no es una barrera de concurrencia.

## 2. Decisión

La autorización de una operación con efectos requiere una **admisión de operación** emitida por una autoridad de consistencia común. La admisión debe vincular, como mínimo:

- identidad inmutable de la operación y su idempotency key;
- decisión/evidencia CAM exacta y request ID;
- actor y revisión de identidad;
- Grant y revisión, cuando aplique;
- proyecto y revisión;
- entorno y revisión;
- acción, tipo e ID de recurso;
- dominio, época y secuencia de consistencia;
- instante UTC y estado de admisión.

Una admisión no es un permiso transferible ni una autorización general. Es válida solo para esa operación, parámetros, actor, proyecto, entorno y recurso exactos. No puede reutilizarse para otra operación ni para un retry semánticamente distinto.

## 3. Orden obligatorio

Toda mutación de una fuente de autoridad debe pasar por el mismo coordinador de consistencia que controla las admisiones:

1. Registrar/reservar el cambio de autoridad con identidad durable e idempotencia.
2. Marcar la autoridad afectada como invalidación pendiente y cerrar nuevas admisiones incompatibles.
3. Aplicar fencing a las operaciones/admisiones afectadas.
4. Mutar la fuente de autoridad con compare-and-swap de la revisión esperada.
5. Reconciliar las operaciones afectadas y cerrar la invalidación.
6. Permitir nuevas admisiones solo después de que el estado reconciliado sea demostrable.

Si cualquier fase queda incierta, la autoridad afectada permanece bloqueada/fenced. Un timeout, excepción o reinicio no equivale a abortar ni a completar.

La admisión sigue el orden inverso de forma coordinada: comprobar que no existe invalidación aplicable, validar las fuentes exactas, releer el head de consistencia y registrar la admisión dentro de la misma unidad de serialización. Si la posición cambió, abortar y volver a validar desde el principio.

## 4. Perfil local SQLite: garantía y condiciones

`SQLiteUnitOfWork` abre `BEGIN IMMEDIATE`. Esto puede proporcionar serialización local entre admisiones y mutaciones **solo si se cumplen todas** estas condiciones:

- existe una única instancia lógica de autoridad de consistencia y una única base SQLite para las fuentes que participan;
- identidad, Grant, proyecto, entorno, revisiones, invalidaciones, admisiones y journal se leen/escriben mediante la misma `SQLiteDatabase` y la misma `SQLiteUnitOfWork`;
- todos los caminos de mutación usan el coordinador; ningún servicio escribe directamente a los repositorios;
- la admisión lee las fuentes y registra su decisión dentro de la transacción `BEGIN IMMEDIATE`;
- una mutación de autoridad no puede confirmar su cambio sin registrar y reconciliar su invalidación en el protocolo;
- la autoridad no se compone de lecturas cacheadas ni de snapshots externos sin validación.

Si alguna fuente no participa en esa transacción, no se declara consistencia atómica. Un lock de proceso, una notificación eventual o una segunda lectura fuera de la transacción no sustituyen estas condiciones.

La serialización SQLite es local a la base/archivo compartido; no constituye un protocolo distribuido ni una garantía entre bases independientes.

## 5. Operaciones de workspace y límite de efectos

### Lecturas

Para `workspace.list` y `workspace.read`, la ruta de prueba podrá considerarse protegida únicamente cuando la admisión y la lectura estén dentro de una sección de consistencia que impida confirmar una revocación concurrente hasta que termine la lectura, y todas las autoridades participen en esa misma barrera.

La lectura debe limitarse al workspace registrado y a rutas canónicas permitidas. No se permite seguir symlinks ni escapar de la raíz. El resultado se publica solo después de completar la operación admitida.

### Escrituras

No se habilitan en esta fase. Una transacción SQLite no puede hacer commit atómico de una modificación del sistema de archivos. Antes de permitir `workspace.write` se requiere un protocolo durable específico: staging, identidad/idempotencia de operación, commit/rename controlado, reconciliación tras crash y tratamiento explícito de resultados inciertos. La aprobación humana tampoco resuelve esa atomicidad.

## 6. Reutilización de componentes existentes

- `OperationAuthorizationEvidence` conserva los claims exactos y las cuatro revisiones.
- `OperationAuthorizationEvidenceVerificationService` conserva la validación local y delega la verificación confiable; su estado VERIFIED no se convierte por sí solo en admisión ni permiso de ejecución.
- `RevisionValidationPort` es una referencia de diseño útil para el patrón invalidation-first + posición de consistencia, pero sigue siendo específico de Memory y de `AuthorizationSnapshot`. No se reutiliza como puerto genérico del Assistant.
- `ConsistencyPosition` expresa dominio/época/secuencia; no proporciona por sí mismo almacenamiento ni exclusión mutua.
- `AuthorityChangeCoordinatorPort` expresa fases de coordinación, pero no hay adaptador concreto en esta rama.
- `SQLiteAuthorityChangeStore` conserva reservas e idempotencia, pero no ejecuta fencing, mutación de fuentes ni reconciliación.
- `SQLiteIdentityAuthority` ofrece CAS para identidad, pero no prueba que las demás autoridades compartan la misma transacción.
- `GrantRepository` es un contrato CRUD y no impone por sí mismo el protocolo de invalidación.

No se debe combinar estas piezas en un falso coordinador mediante composición superficial.

## 7. Criterios de aceptación antes de implementar el adaptador

1. Identificar los repositorios canónicos de Identity, Grant, Project y Environment y sus bases de datos reales.
2. Demostrar que todos comparten una instancia de `SQLiteDatabase` y aceptan la misma `SQLiteUnitOfWork`, o diseñar un fencing equivalente que cubra explícitamente las fuentes externas.
3. Implementar el coordinador durable completo, no solo su store: reserva, invalidación, fencing, CAS de fuente, reconciliación y recuperación.
4. Probar concurrencia real entre admisión y revocación con conexiones independientes/procesos: nunca puede confirmarse una lectura admitida después de que una revocación incompatible haya cerrado su admisión.
5. Probar crash/restart en cada fase; la incertidumbre debe quedar bloqueada, nunca convertirse en ALLOW.
6. Probar cambio de cada una de las cuatro revisiones, cambio de proyecto/entorno, Grant expirado/revocado, actor suspendido/revocado, replay e idempotency key con parámetros alterados.
7. Solo entonces crear un adaptador de verificación/admisión para el perfil de solo lectura.
8. Mantener `workspace.write` y la integración CLI/runtime desconectadas hasta que tengan su propio protocolo probado.

## 8. Estado actual

- F2.3.1: contratos de evidencia y resultado, validados por el propietario.
- F2.3.2: servicio y puerto de verificación, validados por el propietario.
- F2.3.3a: revisiones de proyecto y entorno añadidas; el propietario reportó 925/925 pruebas aprobadas.
- F2.3.3b: inspección de autoridad y consistencia documentada.
- F2.3.4: esta decisión define la admisión común y las condiciones de consistencia; todavía no hay coordinador durable ni adaptador.
- No se ha conectado el verificador al runtime ni se ejecutan capacidades reales.

## 9. Próximo incremento

F2.3.5 debe ser una inspección de persistencia/composición: localizar exactamente dónde viven hoy Identity, Grant, Project y Environment, qué repositorios los modifican y qué instancias de base de datos usan. El resultado será una matriz fuente → repositorio → base de datos → UoW → caminos de mutación. No crear código de coordinador hasta que esa matriz confirme una estrategia implementable.
