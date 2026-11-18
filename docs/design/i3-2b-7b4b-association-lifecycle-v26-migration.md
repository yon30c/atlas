# I3-2B.7B.4B — migración V26 y protección SQL del lifecycle

**Estado:** implementación publicada y validada por el propietario en Debian.  
**PR:** #16 — Draft, abierto y sin merge.  
**Migración:** V26 `audited_project_environment_association_lifecycle`.  
**Alcance:** schema SQLite, constraints/triggers, adaptación mínima del método de persistencia existente y pruebas SQL adversariales. No introduce servicio ni runtime composition.

## Modelo persistido

### Ledger inmutable

`atlas_project_environment_lifecycle_events` guarda un evento por transición:

- UUIDv4 del evento;
- ProjectId y EnvironmentId;
- estado anterior/nuevo (`active` ↔ `suspended`);
- revisión anterior/nueva, exactamente +1;
- UserId y IdentityId canónicos del actor;
- referencia UUIDv4 al contexto de identidad verificada;
- request_id, correlation_id, motivo y timestamp;
- unicidad por asociación y nueva revisión.

El trigger de inserción exige que la asociación todavía esté en el estado/revisión anterior y que actor_user_id resuelva exactamente a una Identity USER activa. Esto es una comprobación de integridad del ledger, no autorización ni prueba suficiente de autenticación; el servicio futuro revalidará VerifiedIdentityContext y Platform Admin dentro de la misma UoW.

Los eventos no admiten UPDATE ni DELETE.

### Enlace con el estado canónico

V26 añade `last_lifecycle_event_id` nullable a `atlas_project_environments`. Las filas existentes conservan estado/revisión y quedan con el puntero NULL; no se fabrican eventos retrospectivos.

Toda actualización posterior a V26 debe:
1. cambiar realmente ACTIVE/SUSPENDED;
2. avanzar exactamente una revisión;
3. apuntar al evento que coincide con asociación, estado anterior/nuevo y revisiones.

El método de persistencia `SQLiteWorkspaceRegistryRepository.update_association` ahora exige `lifecycle_event_id` y escribe ese puntero. El evento debe insertarse antes de la transición dentro de la misma transacción.

### Protección contra eventos huérfanos

La migración añade `atlas_project_environment_lifecycle_commits`, un marcador inmutable de transición completada. Existe una relación FK diferida circular entre evento y marcador:

- insertar un evento sin completar la transición deja pendiente el marcador requerido y falla al commit;
- la actualización válida de la asociación crea el marcador mediante trigger AFTER UPDATE;
- el trigger del marcador comprueba que el estado/revisión/puntero ya corresponden al evento;
- el marcador no puede modificarse ni eliminarse.

Así, un evento y su transición no pueden confirmarse por separado, incluso si se omite el servicio de aplicación.

## Límites de autoridad

- Los triggers verifican integridad y asociación canónica USER; no conceden permisos.
- No se confía en UID/TTY ni en un actor declarado por el caller como evidencia de autenticación.
- La verificación de VerifiedIdentityContext, identidad USER y permiso exacto Platform Admin permanece en 7B.4D.
- No se añaden cascadas ni actualizaciones automáticas a Workspaces, Grants o delegaciones.
- No se cambia V18 ni se reescribe ninguna migración histórica.
- No se ejecuta bootstrap real ni se aplica V26 manualmente a una base de datos productiva.
- V26 se aplica únicamente por el mecanismo normal de migraciones en entornos de prueba/desarrollo; el usuario decide cuándo desplegarla.

## Pruebas añadidas

`tests/unit/test_sqlite_project_environment_lifecycle_migration.py` cubre:
- preservación de asociaciones preexistentes sin historial sintético;
- rechazo de transiciones sin evento coincidente;
- transición válida y puntero al evento;
- rechazo de evento obsoleto o actor que no corresponde a la Identity USER;
- imposibilidad de confirmar eventos huérfanos;
- inmutabilidad/retención de eventos y marcadores;
- rechazo de incrementos de revisión sin transición real.

Las pruebas existentes de `SQLiteWorkspaceRegistryRepository` ahora generan el evento y la transición en una misma UoW, conservando los casos de CAS, Workspace y rollback. La prueba focal añade **9 casos** adversariales, incluido rollback conjunto de evento, asociación y marcador.

## Siguiente fase

7B.4C implementará `SQLiteProjectEnvironmentLifecycleLedger` para `append_event` y `list_events`, compartiendo UoW y sin exponer el writer en runtime composition. Después 7B.4D coordinará el ledger con autorización y CAS.

## Validación del propietario

El propietario sincronizó la rama en `~/atlas-dev` y ejecutó la suite completa y `compileall`. Resultado reportado:

```text
Ran 1480 tests in 30.943s

OK
COMPILE_EXIT_CODE=0
```

**Resultado:** 1,480/1,480 tests OK; compilación estática sin errores. La validación focal y la suite completa quedaron cubiertas por la ejecución completa. No se ejecutó migración productiva ni bootstrap real. PR #16 permanece Draft, abierto y sin merge.
