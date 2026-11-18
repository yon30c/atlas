# I3-2B.7B.3A — contratos de dominio para bootstrap offline

**Estado:** implementado en la rama de trabajo; validación automatizada en Debian pendiente.  
**Alcance:** contratos de dominio y puerto. No implementa persistencia de bootstrap, servicio, CLI ni provisión real.  
**PR:** #16 — permanece Draft, abierto y sin merge.

## 1. Objetivo

Definir una intención inmutable para conceder la primera autoridad Platform Admin, una procedencia técnica inmutable de la ejecución local y un comando de dominio que vincule solicitud, procedencia y concesión. El adaptador offline futuro recibirá ese comando en lugar de aceptar un `PlatformAdminGrant` arbitrario.

## 2. Contratos

### `PlatformAdminBootstrapRequest`

- `operation_id`: UUIDv4 canónico que identifica la intención y permite idempotencia.
- `user_id`: UUIDv4 del usuario Atlas existente que recibirá la autoridad.
- `permissions`: `frozenset` que debe contener exactamente:
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
