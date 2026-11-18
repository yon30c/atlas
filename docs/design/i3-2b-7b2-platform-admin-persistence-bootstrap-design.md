# I3-2B.7B.2 — diseño de persistencia y bootstrap offline de Platform Admin

**Estado:** diseño técnico para revisión antes de implementar. No añade migraciones, adaptadores, comandos ni privilegios.
**Rama:** design/verified-agent-delegation-i3-2b.
**Dependencia:** contratos 7B.1; validación Debian confirmada en HEAD 8f65c3646987a2402ecd089f9b426568f60f2ec2.

## 1. Objetivo y límites

Persistir la autoridad administrativa de plataforma como autoridad canónica independiente, inicialmente vacía, y separar estrictamente:
1. lectura/verificación durante operaciones normales;
2. provisión inicial mediante comando offline controlado por el operador;
3. futuras operaciones explícitas de revocación, fuera del bootstrap inicial.

Este slice no implementa el servicio que suspende/reactiva asociaciones. No ejecuta bootstrap, no crea administradores, no cambia asociaciones, no habilita endpoints y no compone la capacidad de bootstrap en runtime. La autoridad ausente debe continuar produciendo DENY.

## 2. Versionado de esquema

La rama tiene como última migración de autoridad conocida CORE_SCHEMA_V24. La siguiente versión aditiva disponible se propone como V25, pero debe confirmarse contra el registro real de migraciones antes de codificar.

No modificar V18 ni V24, ni reescribir datos históricos. La migración debe ser reproducible, transaccional y probada en base vacía y upgrade desde V24. Seguir el migrator existente; no crear uno paralelo.

## 3. Modelo relacional propuesto

### 3.1 platform_admin_grants

Una fila por concesión, incluidos tombstones revocados:
- grant_id UUIDv4 PRIMARY KEY;
- user_id FK a la identidad USER canónica;
- user_identity_id FK a identity_records, con restricción explícita de kind USER;
- user_identity_revision entero positivo;
- provisioning_method restringido a offline_bootstrap en este corte;
- bootstrap_event_id FK al evento offline que originó la concesión;
- issued_at, not_before y expires_at UTC, con issued_at <= not_before < expires_at;
- status ACTIVE/REVOKED y revision positiva;
- revoked_at y revoked_by_user_id nullable, pero obligatorios conjuntamente para REVOKED y ambos NULL para ACTIVE.

No usar rol global, wildcard ni booleano is_admin. No permitir reasignar una concesión a otro UserId/Identity ni cambiar su procedencia.

### 3.2 Permisos exactos

Persistir permisos como filas normalizadas en platform_admin_grant_permissions (grant_id, permission), con PK compuesta y FK al grant. Limitar valores a:
- association.suspend
- association.reactivate

No admitir wildcard, strings arbitrarios ni permisos futuros por aceptación silenciosa. La inserción del grant y todas sus filas de permisos es atómica; una concesión sin permisos no puede confirmarse.

### 3.3 platform_admin_bootstrap_events

Registro inmutable de cada provisión aceptada:
- event_id UUIDv4;
- sujeto USER/Identity y revisión canónica observada;
- método offline_bootstrap;
- conjunto/alcance de permisos concedidos, vinculado a la concesión;
- instante UTC generado por Clock confiable;
- referencia de auditoría del operador/procedimiento local, nunca un secreto ni credencial.

El contrato exacto de esa referencia debe definirse para la interfaz CLI antes de implementar el comando. No fingir que UID del proceso, nombre de usuario del sistema operativo o argumento libre prueban por sí solos la identidad del operador. No almacenar contraseñas, tokens, proofs raw, claves HMAC ni secretos.

El evento y el grant se insertan en la misma transacción. Cada grant apunta a exactamente un evento de bootstrap. Los eventos aceptados no se actualizan ni eliminan.

## 4. Reglas de integridad SQL

- FKs a UserId e Identity(USER), con integridad cruzada que garantice que ambos identificadores pertenecen a la misma identidad canónica activa al provisionar.
- Impedir referencias a identidades AGENT.
- CHECKs para estados, revisiones positivas, orden temporal y revocación coherente.
- Evitar más de una concesión ACTIVE equivalente para la misma identidad USER. Preferir una concesión consolidada con conjunto explícito de permisos.
- Triggers que impidan modificar sujeto, identidad, revisión de identidad de origen, método de provisión y evento bootstrap.
- Revocación solo mediante transición ACTIVE -> REVOKED, CAS de revisión exactamente +1, actor USER canónico y timestamp confiable; REVOKED es terminal. No implementar revocación en el bootstrap slice si falta su servicio.
- No DELETE de grants ni eventos. Permisos inmutables después de la creación para este corte.
- Ningún grant puede confirmarse sin al menos un permiso y un evento bootstrap válido.

Las restricciones no expresables con CHECK/FK deben reforzarse con triggers y validación de dominio. No inventar filas para usuarios existentes.

## 5. Puertos y adaptadores

Mantener la separación de 7B.1:
- PlatformAdminAuthorityReaderPort: solo lectura por grant_id y listado por UserId; devuelve también grants revocados para impedir resurrección/duplicación.
- Un puerto de persistencia interno a la UoW puede exponer inserción/lectura/CAS solo a servicios confiables; no debe incluir provision_first_admin.
- PlatformAdminBootstrapPort: capacidad separada para provisión inicial; su implementación SQLite no debe formar parte de SQLiteLocalAuthorityUnitOfWork ni de repositorios entregados a servicios runtime.

El reader runtime sí se compone dentro de la UoW de autoridad local, compartiendo transacción con Identity Authority. El adaptador bootstrap se crea solo desde una herramienta offline, con acceso explícito a la base local seleccionada y sin exponer esa capacidad a HTTP, workers, consola normal o servicios de aplicación.

## 6. Contrato de bootstrap offline

Interfaz final deliberadamente estrecha. Propuesta conceptual:
- seleccionar una base de datos explícita mediante configuración segura de herramienta, no ruta implícita a producción;
- seleccionar identidad por identificador canónico ya conocido; nunca crear ni modificar la identidad;
- conceder conjunto explícito no vacío de permisos enumerados;
- definir ventana de validez finita;
- requerir confirmación interactiva antes de persistir;
- exigir evidencia/procedencia del operador en formato definido y auditable;
- usar Clock inyectado y una sola UoW;
- imprimir solo resumen no secreto e identificadores del evento/grant.

El comando no debe aceptar un booleano admin, defaults que otorguen permisos, secretos por argv/env genérico ni ejecutarse en startup, migración o instalación. No estará disponible como endpoint ni subcomando de la CLI de usuario.

### Idempotencia y conflictos

- Mismo sujeto + mismo conjunto exacto de permisos + misma intención: devolver resultado existente sin duplicar filas ni ampliar autoridad.
- Mismo sujeto con permisos, ventana o evento diferentes: conflicto explícito; no actualizar ni ampliar el grant silenciosamente.
- Identidad inexistente, inactiva, AGENT, revisión stale, autoridad ausente o DB equivocada: abortar sin escritura.
- El primer administrador no se selecciona por orden de creación, propiedad del sistema o nombre de usuario.

La idempotencia debe basarse en una clave de operación no secreta y persistida, no en comparar timestamps aproximados.

## 7. Composición transaccional y fail-closed

Bootstrap, en una única transacción local:
1. resolver UserId e Identity(USER) desde Identity Authority;
2. exigir ACTIVE y capturar revisión canónica;
3. validar permisos, ventana, operador y alcance;
4. comprobar ausencia de concesión/conflicto;
5. insertar evento, grant y permisos;
6. confirmar todo junto.

Cualquier excepción revierte todo. No hay saga ni atomicidad distribuida: la garantía es únicamente SQLite local compartida.

Para consumidores runtime futuros, identidad USER, revisión de identidad y grant deben releerse dentro de la misma UoW de la operación protegida. El grant persistido no es por sí solo credencial ni contexto verificado.

## 8. Pruebas de aceptación obligatorias

### Migración y SQL
- upgrade V24 -> V25 y creación desde cero;
- migración repetida según convención existente;
- FK inválida, Identity AGENT, UserId/Identity cruzados;
- grant sin evento, evento sin grant, grant sin permisos;
- permiso desconocido/wildcard;
- duplicados y concesiones activas conflictivas;
- inmutabilidad de sujeto/procedencia/permisos y no-delete;
- rollback de evento + grant + permisos.

### Repositorios/UoW
- read-your-writes y rollback en UoW compartida;
- lectura de grants ACTIVE y REVOKED;
- no provisionar mediante reader runtime;
- adaptador bootstrap ausente de composición runtime;
- intentos concurrentes no crean concesiones activas duplicadas ni eventos repetidos.

### Bootstrap
- identidad USER activa existente: provisión explícita;
- identidad inexistente/inactiva/AGENT: DENY;
- mismo request id: idempotencia;
- misma identidad con alcance distinto: conflicto;
- error intermedio: rollback total;
- confirmación ausente o procedencia inválida: no escritura;
- ningún secreto en stdout/stderr/logs/argv ni persistido.

## 9. Secuencia de implementación

1. Confirmar en el árbol actual el registro de migraciones y la siguiente versión libre; no asumir V25 hasta esa inspección.
2. Añadir modelo/persistencia SQLite y pruebas de migración/integridad, sin componer bootstrap runtime.
3. Añadir reader runtime dentro de SQLiteLocalAuthorityUnitOfWork y pruebas read-your-writes/rollback.
4. Implementar adaptador bootstrap aislado y pruebas de idempotencia/conflictos, sin ejecutar el comando contra datos reales.
5. Definir y revisar interfaz operativa/procedencia del operador antes de publicar el comando ejecutable.
6. Ejecutar validación Debian focalizada, compileall y suite completa. No avanzar al servicio lifecycle hasta recibir resultados del propietario.

## 10. Fuera de alcance

- Provisionar el primer administrador real.
- Revocar o editar permisos mediante operación runtime.
- Servicio de suspensión/reactivación de asociaciones.
- Ledger de lifecycle Project/Environment (no acoplarlo automáticamente al grant store).
- Endpoints, login, UI, cambios de host, sudoers, systemd, Docker o DB productiva.
- Merge del PR.

**Gate:** antes de escribir código, confirmar el registro de migraciones y cerrar el contrato exacto de procedencia del operador para el bootstrap offline. Ningún privilegio se concede durante esta etapa.


## 11. Inspección del árbol de implementación — confirmación del siguiente slice

Inspección directa de la rama en GitHub después de publicar este diseño:

- El registro SQLITE_MIGRATIONS en src/atlas/adapters/sqlite/migrations.py termina actualmente en CORE_SCHEMA_V24 y enumera explícitamente V1–V24. Por tanto, **V25 queda confirmado como siguiente número libre en este HEAD**; no era necesario dejarlo como hipótesis.
- SQLiteLocalAuthorityUnitOfWork compone Identity Authority, AGENT/native authorities, delegaciones, Project/Environment, Workspace y stores auxiliares sobre una misma SQLiteUnitOfWork. El reader runtime Platform Admin debe seguir este patrón y compartir la transacción física.
- La composición runtime actual no contiene PlatformAdminAuthorityReaderPort ni PlatformAdminBootstrapPort. La primera se añadirá a la UoW; la segunda debe permanecer fuera de esa composición.
- PlatformAdminBootstrapPort actual solo recibe PlatformAdminGrant. Ese contrato no transporta referencia de operación ni evidencia/procedencia del operador y no basta para el requisito de auditoría definido en este documento. Debe ampliarse antes de implementar el adaptador offline; no implementar el comando con una referencia inventada ni vacía.
- La implementación SQLite de Identity Authority resuelve el par UserId/Identity(USER) mediante JOIN canónico y devuelve status/revision. El bootstrap debe reutilizar esa autoridad dentro de la UoW, no consultar ni escribir tablas de identidad por su cuenta.

### Decisión pendiente acotada: procedencia del operador offline

Recomendación para el primer comando: exigir terminal interactivo local y registrar como procedencia técnica el UID real del proceso, el UID efectivo, el identificador de terminal y un operation_id UUID generado por la herramienta. Estos datos son evidencia del contexto de ejecución local, **no prueba de identidad humana ni de autorización del operador**. La política de confianza seguiría siendo que el operador con acceso local autorizado ejecuta deliberadamente la herramienta y revisa el destino/identidad/permisos antes de confirmar.

No almacenar un nombre de usuario libre como si fuera autenticación, ni usar UID/TTY como sustituto de una identidad USER canónica. El actor de la concesión sigue siendo el USER existente que recibe el permiso; la procedencia del operador es un registro separado.

**Gate operativo:** confirmar si esta procedencia técnica limitada (UID real/efectivo + TTY + operation_id + confirmación interactiva) es aceptable, o si se requiere un mecanismo de autenticación local más fuerte. Hasta esa decisión, se puede implementar V25, el reader runtime y los repositorios, pero no publicar ni ejecutar un comando de bootstrap.


## 12. Implementación inicial de persistencia publicada (pendiente de Debian)

Se añadió en esta rama una primera implementación de persistencia, sin ejecutar ni publicar un comando de bootstrap:

- **V25** crea `platform_admin_bootstrap_events` y `platform_admin_grants`, con FK diferidas circulares para exigir que evento y concesión se confirmen juntos; ambas tablas conservan registros y bloquean UPDATE/DELETE del evento y DELETE de la concesión.
- El evento registra operation_id UUIDv4, UID real/efectivo, terminal y confirmación UTC. El trigger comprueba que el sujeto corresponde exactamente a un par canónico UserId/Identity(USER), activo y en la revisión declarada.
- La concesión persiste permisos JSON no vacío, únicos y limitados a los dos permisos exactos; un índice parcial permite como máximo una concesión activa por USER.
- Se añadió `SQLitePlatformAdminAuthorityReader` de solo lectura y se compuso dentro de `SQLiteLocalAuthorityUnitOfWork`; comparte la conexión y transacción con Identity Authority.
- Se añadieron pruebas focalizadas para migración/reaplicación, lectura vacía, read-your-writes, rollback conjunto, FK diferida, permisos inválidos, identidad suspendida y ausencia de método de provisión en runtime.

**Límites deliberados:** no se implementó todavía el adaptador `PlatformAdminBootstrapPort`, el servicio de provisión ni CLI. El UID/TTY/operation_id quedan registrados como procedencia técnica, pero la interfaz debe exigir terminal interactivo y confirmación humana real antes de cualquier escritura. No se ha provisionado ningún administrador.

**Gate de validación:** ejecutar las pruebas nuevas y la suite completa en Debian. Si aparecen problemas, corregir antes de continuar. No considerar esta persistencia validada hasta recibir resultados del propietario.
