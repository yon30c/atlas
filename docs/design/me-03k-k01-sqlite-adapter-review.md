# ME-03K K01 — Revisión del adaptador SQLite

**Estado:** revisión estática completada; correcciones publicadas; validación Debian pendiente.  
**Rama:** `feature/me-03k-local-profile`.  
**Base revisada:** implementación K01 de SQLite y contrato del puerto en la rama de trabajo.

## 1. Alcance revisado

Se inspeccionaron directamente en GitHub:

- `ConsistencyJournalPort`;
- `SQLiteConsistencyJournal`;
- migraciones SQLite v1, v2 y v3;
- proyección semántica K01;
- resolución tipada `JournalOperationResolution`;
- pruebas del fake en memoria y pruebas del adaptador SQLite.

La revisión no ejecutó pruebas ni modificó Debian, systemd, Docker, Broker o producción.

## 2. Resultado

La implementación mantiene correctamente los límites principales de K01:

- `BEGIN IMMEDIATE` serializa lectura de autoridad y escritura dentro del proceso SQLite.
- El head se actualiza con CAS dentro de la misma transacción que inserta journal y resolución.
- Un replay semántico devuelve el commit original sin avanzar el head.
- La igualdad compara bytes canónicos exactos, no solo SHA-256.
- `append_id` identifica el intento; `idempotency_key` identifica la solicitud semántica; `operation_id` conserva correlación no única.
- El adaptador declara expresamente que todavía no implementa carga de recuperación autenticada, checkpoints ni recibos.

## 3. Correcciones publicadas durante la revisión

### 3.1 Proyección semántica v1 congelada

La lista de campos de proyección se derivaba de la lista de validación de transiciones. Una ampliación futura de esta última podía alterar accidentalmente la semántica de v1.

Se añadió `REQUEST_PROJECTION_FIELDS_V1` como snapshot inmutable independiente. Cambiar el conjunto semántico exige modificar explícitamente la versión de proyección y sus pruebas.

### 3.2 Frontera de firma endurecida

El adaptador ahora exige que el firmante preserve exactamente el `issued_at` del envelope recibido. El firmante puede completar el compromiso del objeto y la evidencia de autenticación, pero no cambiar los demás metadatos esperados.

También se convierte cualquier excepción ordinaria del firmante en fallo cerrado; la transacción se revierte y no se devuelve un commit.

### 3.3 Pruebas añadidas

- Inmutabilidad del allowlist de proyección v1.
- Rechazo de un firmante que altera `issued_at`.
- Fallo cerrado ante una excepción no prevista del firmante.

Commits de esta revisión:

- `bdae629b29fd40ba97238060a585e90c58980fa5`
- `dfc3f565c19d6ac62d6de5395ff0f2c1ad489cce`
- `99df952c132fea6cc9a4d3fde5f86020c87f5d99`
- `27832211552d928006fc33004048cd303bed04d4`

## 4. Deuda y límites que permanecen

Esta revisión no convierte K01 en conformidad completa K01–K07.

1. Las pruebas actuales del adaptador son pruebas de integración SQLite dentro de un proceso; todavía falta probar escritores multiproceso, interrupciones/crash y reconciliación tras reinicio.
2. El adaptador todavía recibe un `LocalConsistencySignerPort` inyectado; no hay firmante productivo ni proveedor de credenciales implementado.
3. La lectura durable y verificada del journal todavía no está implementada por este adaptador.
4. No se ha integrado la recuperación de checkpoints, inventarios, tombstones ni recibos con SQLite.
5. No se ha configurado ni provisionado ningún systemd credential.
6. El perfil local no ofrece protección contra restauración coherente de un backup antiguo.

## 5. Criterio para cerrar esta revisión

La revisión está completada a nivel estático. La validación de los cambios añadidos queda pendiente de la ejecución de la suite completa en Debian por el propietario. No afirmar conformidad K01 hasta añadir y ejecutar las pruebas de concurrencia y crash/restart contra el adaptador real.
