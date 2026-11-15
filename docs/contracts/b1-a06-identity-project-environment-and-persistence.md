# Atlas — Enmienda normativa B1-A-06
## Consolidación de decisiones B1-A-01 a B1-A-05

**Estado:** APROBADA POR EL PROPIETARIO  
**Fecha de aprobación:** 15 de noviembre de 2026  
**Versión:** 1.0  
**Contrato principal:** [Contrato de diseño Atlas v1](../../Contrato-de-diseno-Atlas-v1.md)  
**Alcance:** Memory Engine, Identity, Project, Environment, CAM y persistencia local compartida.

---

## 1. Autoridad y alcance

Esta enmienda registra las decisiones aprobadas B1-A-01 a B1-A-05 como ampliaciones posteriores del contrato principal. El contrato raíz continúa siendo el documento normativo principal; esta enmienda forma parte de su baseline vigente y prevalece sobre disposiciones anteriores incompatibles dentro de los ámbitos que modifica.

Las disposiciones no modificadas continúan vigentes. Los contratos técnicos pueden desarrollar estas reglas, pero no reducir sus garantías ni ampliar autoridad.

La aprobación es arquitectónica y documental. No certifica implementación, integración, pruebas, despliegue ni autorización para modificar infraestructura protegida. La autorización de implementación existente conserva su alcance y límites.

## 2. B1-A-01 — Autorización de consumidores sobre memoria PRIVATE

### 2.1 Modelo y alcance

El acceso de un consumidor a una memoria PRIVATE se concede por memoria individual. No existe autorización implícita por propietario, grupo, categoría, conversación o pertenencia a otro consumidor.

Modelo conceptual `PrivateMemoryConsumerAuthorization`:

- `authorization_id`
- `owner_identity_id`
- `consumer_id`
- `memory_id`
- `permissions`
- `revision`
- `status`
- `created_at`
- `expires_at`
- `revoked_at`

La autorización vincula exactamente un propietario, consumidor y memoria. La memoria debe tener scope `PRIVATE` y `project_id = NULL`. `Memory.owner_id` conserva el `UserId` global y canónico de Atlas; `owner_identity_id` identifica el `identity_id` canónico de la Identity(USER) asociada a ese mismo usuario. Identity Authority debe resolver y verificar la relación 1:1 vigente mediante evidencia interna autoritativa. CAM comprueba cada identificador en su propio espacio: no exige ni infiere igualdad textual entre `UserId` e `identity_id`. La correspondencia debe verificarse antes de admitir la autorización PRIVATE.

### 2.2 Permisos

El catálogo de esta autorización es cerrado a:

- `memory.read`
- `memory.propose_update`
- `memory.export`

Los permisos se evalúan individualmente. `memory.propose_update` permite presentar una propuesta de actualización, no modificar directamente una versión aprobada ni aprobar, rechazar, olvidar o cambiar el propietario de una memoria.

No se crean alias automáticos entre `memory.propose_update` y los permisos históricos `memory.propose` o `memory.update`. Cualquier adaptación entre catálogos requerirá un mapeo explícito, verificable y que no amplíe privilegios.

La aprobación, rechazo y Forget permanecen reservados a la acción directa verificable del propietario y no son delegables.

### 2.3 Aislamiento y ciclo de vida

- Un consumidor no hereda autorizaciones de otro.
- Conocer un `memory_id` o `authorization_id` no concede acceso.
- La identidad del consumidor procede de una fuente confiable; un campo enviado por el consumidor no demuestra identidad.
- No existe delegación de estas autorizaciones.
- La revocación es irreversible. Una concesión posterior requiere un nuevo `authorization_id`.
- Desactivar un consumidor bloquea nuevas admisiones inmediatamente, pero conserva las autorizaciones existentes y su historial.
- Reactivar un consumidor no concede permisos nuevos ni revive admisiones anteriores. Las autorizaciones conservadas solo vuelven a ser elegibles si siguen activas, no vencidas ni revocadas y se satisfacen todas las validaciones actuales.

Estados conceptuales: `ACTIVE`, `REVOKING`, `REVOKED`, `EXPIRED`. `REVOKED` y `EXPIRED` no se reactivan.

### 2.4 Admisiones y fallos

Cada admisión registra un snapshot verificable del consumidor, propietario, memoria, autorización exacta, revisiones pertinentes, `admission_id` y generación de invalidación.

Consistency calcula autoritativamente las admisiones y rutas afectadas; el consumidor no suministra una lista autoritativa. La desactivación requiere invalidación y fencing antes de permitir operaciones incompatibles.

La indisponibilidad o inconsistencia de CAM, Identity o Consistency produce denegación (fail-closed). La autorización PRIVATE no depende de un Grant PROJECT ni reutiliza automáticamente uno. La representación interna CAM de esta autorización debe conservar esa separación.

## 3. B1-A-02 — Relación Project–Environment

La relación es 1:N:

- Un Project puede tener cero o varios Environments.
- Cada Environment pertenece exactamente a un Project.
- Un Environment no se comparte entre Projects.
- `Environment.project_id` es obligatorio y canónico.

Project y Environment conservan identidad, estado y revisión independientes.

Estados conceptuales para ambos: `ACTIVE`, `INACTIVE`, `DELETING`, `DELETED`. `DELETED` es tombstone y no admite reactivación ordinaria.

Desactivar Project bloquea nuevas admisiones en todos sus Environments, pero no modifica sus revisiones ni cambia automáticamente sus estados. Desactivar Environment afecta solo a ese Environment. Reactivar Project no reactiva automáticamente Environments ni Grants revocados o vencidos. Reactivar Environment exige que el Project esté activo.

La relación Environment–Project es inmutable en operaciones ordinarias. Una transferencia futura requeriría operación especial, autorización, invalidación, fencing y reconciliación; no está habilitada. El repositorio de Project no modifica directamente tablas, estados o revisiones de Environment.

Los cambios se coordinan conforme a D4O-F y D4O-H.

## 4. B1-A-03 — Identidad canónica y bindings

### 4.1 Separación de autoridades

- **Authentication Authority:** autentica el sujeto externo y verifica la evidencia del proveedor.
- **Identity Authority:** mantiene identidad canónica y bindings.
- **CAM:** decide si una operación concreta está autorizada.
- **Consistency:** coordina invalidaciones, fencing, admisiones y reconciliación.
- **Memory Gateway:** frontera obligatoria de operaciones Memory Engine.

Ninguna de estas responsabilidades se sustituye por otra.

### 4.2 Identidad y binding

`identity_id` es interno, canónico, inmutable, independiente de correo/nombre/proveedor y no reutilizable. `UserId` es un identificador global y canónico de Atlas, distinto de `identity_id`, emitido y administrado por Identity Authority. Existe una relación 1:1 autoritativa entre un `UserId` y exactamente una Identity(USER), y cada Identity(USER) corresponde a exactamente un `UserId`. Identity Authority mantiene y resuelve esta relación mediante evidencia interna verificable y vigente; no se exige igualdad textual entre ambos identificadores.

Binding externo conceptual: `(issuer_id, subject) -> identity_id`.

- `issuer_id` identifica una entrada del registro de issuers confiable de Atlas; no es una cadena arbitraria elegida por el caller.
- `subject` es opaco y se interpreta únicamente dentro del issuer correspondiente.
- Una pareja exacta `(issuer_id, subject)` puede vincularse a como máximo una Identity(USER). La pareja permanece reservada y no reasignable incluso después de revocar el binding.
- Una Identity(USER) puede tener varios bindings externos verificados mediante un proceso explícito.
- Un binding no concede autorización, Grants, permisos PRIVATE, delegación ni propiedad.
- No se crea ni modifica un binding a partir de identificadores enviados por un consumidor.
- Un binding revocado es irreversible y permanece como tombstone no reasignable.
- Un binding nuevo no hereda Grants ni autorizaciones.
- No se fusionan identidades por coincidencia de atributos.
- Cambiar de proveedor requiere añadir un binding nuevo a la misma Identity(USER), con un procedimiento explícito; la revocación del anterior debe preservar un método de acceso o recuperación utilizable.
- La revocación/unlink no puede completarse si no queda al menos un método de acceso o recuperación utilizable conforme a una política aprobada.

La autenticación externa y la resolución del binding son distintas de la autorización. La frontera confiable valida el issuer configurado y el subject exacto y Identity Authority resuelve la Identity(USER) y el `UserId` canónico asociados. Email, nombre, teléfono o ID aislado no son prueba suficiente. Fallos, ambigüedad, expiración, revocación, pérdida de confianza o indisponibilidad producen denegación. CAM conserva la autoridad exclusiva para evaluar cada operación protegida.

### 4.3 Tipos y compatibilidad histórica

La implementación inicial del nuevo modelo Identity se limita a `USER`. `SERVICE` queda reservado para una fase posterior y no recibe capacidades automáticas. Los tipos históricos `AGENT`, `WATCHER` y `SYSTEM` no se eliminan ni adquieren privilegios por esta decisión.

El contrato y el código históricos contienen estados `ACTIVE`, `SUSPENDED` y `REVOKED`; el modelo canónico nuevo define `ACTIVE`, `INACTIVE`, `DELETING` y `DELETED`.

**Decisión de compatibilidad:** no se realiza conversión automática entre ambos vocabularios. Se preservan los valores históricos y su semántica. Los registros históricos no se migran ni se reinterpretan por semejanza nominal. Antes de que un adaptador permita su uso en el nuevo Identity Authority, deberá existir una especificación de migración con reglas por tipo/estado, tratamiento de casos ambiguos, evidencia de origen y pruebas negativas. Mientras no exista, una identidad cuyo estado no pueda interpretarse de forma autoritativa no puede obtener nuevas admisiones protegidas.

En el modelo nuevo, `DELETED` es tombstone y terminal. La reactivación de una identidad no revive bindings revocados.

## 5. B1-A-04 — Integración Identity–CAM

Identity emite un contexto inmutable conceptual `VerifiedIdentityContext`:

- `context_id`
- `identity_id`
- `identity_type`
- `identity_revision`
- `user_id` (UserId canónico Atlas)
- `binding_id`
- `binding_revision`
- `issuer_id`
- `authenticated_at`
- `verified_at`
- `expires_at`
- `verification_ref`

El contexto acredita identidad verificada dentro de su vigencia; no es un Grant ni una autorización permanente. No transporta credenciales ni sustituye la validación CAM.

`VerifiedIdentityContext` se emite exclusivamente para una Identity(USER); `identity_type` debe identificar `USER`. `identity_id` identifica la Identity(USER) autenticada y `user_id` identifica el UserId canónico asociado. Estos campos no identifican necesariamente al actor ejecutor de todas las operaciones realizadas dentro del contexto.

Cuando el actor ejecutor sea una Identity(USER), CAM debe comprobar que su `identity_id` coincide exactamente con el `identity_id` autenticado en el contexto y que el UserId contextual corresponde al mismo usuario canónico. Cuando el actor sea AGENT, SERVICE, WATCHER o SYSTEM, CAM debe verificar separadamente su identidad mediante una fuente confiable y comprobar la delegación explícita aplicable. `VerifiedIdentityContext` no autentica ni acredita por sí mismo esos actores. Esta disposición no define ni habilita mecanismos de autenticación para actores no USER ni les concede capacidades nuevas; requieren especificación independiente.

CAM recibe una solicitud que identifica actor y revisiones, binding y revisión, acción exacta, tipo/ID/revisión esperada del recurso, consumidor cuando aplique y fecha de solicitud. Un `identity_id` aislado no es suficiente.

Antes de admitir una operación, CAM verifica contexto vigente, identidad y binding activos, revisiones actuales, operación y recurso exactos, scope, propietario, Grant/autorización aplicable y ausencia de invalidación/fencing incompatible.

Identity no concede Grants, no aprueba/rechaza memorias, no autoriza Forget, no concede acceso PRIVATE, no cambia propietarios, no revoca Grants ni concede privilegios.

Desactivar Identity o revocar un binding bloquea nuevas admisiones que dependan de ellos. Consistency calcula las admisiones afectadas. Reactivar Identity no reactiva admisiones antiguas ni bindings revocados. Los cambios respetan D4O-F/H y fallan cerrados ante evidencia incompleta.

## 6. B1-A-05 — Persistencia local compartida

### 6.1 Decisión

El perfil LOCAL de Atlas utiliza una única base SQLite compartida. Esta base ofrece una frontera transaccional común para las autoridades que residan realmente en ella y participen en la misma UoW.

La base no es una autoridad de dominio genérica. Cada dominio conserva sus modelos, tablas, repositorios, servicios, invariantes y autoridad canónica.

### 6.2 Dominios lógicos

- **Memory:** memorias, versiones, propuestas y procedencia.
- **Identity:** identidades, bindings, estados y revisiones.
- **Project:** proyectos, estados y revisiones.
- **Environment:** entornos, relación canónica con Project, estados y revisiones.
- **CAM:** Grants, renovaciones, revocaciones, autorizaciones e idempotencia.
- **Consistency:** journal, operaciones de cambio, invalidaciones, fencing, admisiones y recuperación.
- **Infrastructure:** migraciones y metadatos técnicos.

No se introduce una tabla genérica que sustituya los modelos específicos.

### 6.3 Fronteras y transacciones

- Un dominio no escribe directamente en las tablas de otro.
- Un dominio no sustituye la autoridad canónica de otro.
- Los consumidores no acceden directamente a tablas, conexiones, archivos, índices ni credenciales.
- Memory Engine consulta autoridades mediante puertos/adaptadores explícitos.
- Broker Registry no es autoridad de Memory, Identity, Project, Environment o CAM.
- Operaciones coordinadas que requieren atomicidad usan `SQLiteUnitOfWork`.
- Cuando se requiere invalidación/fencing, esta debe ser durable antes de admitir operaciones incompatibles, dentro de la frontera transaccional pertinente.
- No se sustituye una invalidación atómica por actualizar y notificar después.
- Proveedores externos de autenticación permanecen fuera de la transacción SQLite; no se afirma atomicidad con sus APIs.

### 6.4 Migraciones y límites

Se preservan las migraciones existentes y el esquema v4. Las nuevas migraciones deben ser aditivas, verificables y compatibles con los datos existentes. No se reconstruye la base desde cero.

La decisión de SQLite compartida no demuestra que todos los dominios estén ya persistidos ni que exista un coordinador completo. La atomicidad solo puede afirmarse para autoridades que compartan realmente base y frontera UoW.

## 7. Reglas transversales

Las decisiones anteriores respetan D4O-F, D4O-G y D4O-H:

1. Invalidación y fencing preceden a cambios de autoridad efectivos.
2. Revisiones verificadas mediante CAS o mecanismo equivalente.
3. Idempotencia explícita por operación.
4. Timeout o resultado incierto no equivale a ABORTED.
5. Operaciones incompletas conservan fencing.
6. Consistency calcula admisiones afectadas.
7. La recuperación precede a admisiones incompatibles.
8. Fuentes inaccesibles o inconsistentes producen fail-closed.
9. Snapshot de autorización no es permiso permanente.
10. IDs conocidos no conceden acceso.
11. Aislamiento lógico equivalente entre despliegue centralizado y aislado.
12. No hay búsqueda ni transferencia cross-consumer/project por defecto.

## 8. Resoluciones documentales

### 8.1 Revisión del contrato principal

La revisión 3 del contrato raíz es el baseline aprobado anterior a esta enmienda. La revisión 4 incorpora su registro y referencia normativa. La antigua frase de §1.2.6 que declaraba revisión 2 como base vigente queda sustituida por una referencia a revisión 3 como baseline previo y revisión 4 como documento actualizado.

### 8.2 Permisos PRIVATE

`memory.propose_update` es un permiso específico y no un alias de `memory.propose` o `memory.update`. No se amplía la capacidad de aprobar, rechazar, olvidar o modificar directamente una versión aprobada.

### 8.3 Project–Environment

La cardinalidad 1:N y pertenencia obligatoria son reglas normativas posteriores. La falta de persistencia física actual no crea excepciones.

### 8.4 D4O-B — conteo de pruebas

El archivo `tests/unit/test_memory_authority_validation_ports.py` contiene 12 métodos `test_*` en la revisión de rama examinada (blob `aa666d3d4567aab8b953576f17261507181c203e`). La documentación D4O-B se corrige para indicar 12 pruebas añadidas. Este conteo estático no significa que se hayan ejecutado ni que hayan pasado; la ejecución requiere evidencia independiente.

## 9. Condiciones para B1-B-02

El diseño físico debe respetar:

- Una sola SQLite para perfil LOCAL.
- Autoridad canónica separada por dominio.
- Tablas y repositorios específicos por dominio.
- Identificadores exactos y no reutilizables.
- Separación Identity / binding / CAM.
- Relación Project–Environment 1:N.
- Revisiones persistidas.
- Invalidaciones, fencing, admisiones y recuperación durables.
- UoW compartida donde exista atomicidad real.
- Idempotencia explícita.
- Compatibilidad aditiva con migraciones existentes y esquema v4.
- Aislamiento por consumidor y proyecto.
- Recuperación segura ante interrupciones.
- Sin acceso de escritura cruzado entre dominios.

B1-B-02 no puede introducir políticas nuevas ni resolver diferencias mediante equivalencias implícitas.

## 10. Exclusiones y estado de implementación

Esta enmienda no implementa por sí misma:

- Repositorios SQLite canónicos de todos los dominios.
- Coordinador completo de cambios de autoridad.
- Persistencia de identidades/bindings ni migración de estados históricos.
- Autorizaciones PRIVATE operativas.
- `admit_read`, autoridad completa de egress o runtime protegido.
- Forget físico ni verificación de todos los destinos.
- Trust Anchor externo.

La existencia de contratos, tablas de infraestructura o pruebas unitarias parciales no acredita estas capacidades. El Recovery Gate permanece sujeto a sus condiciones de recuperación y bootstrap.

No se modifican Broker, Registry, servicios ni producción. No se autoriza merge, PR ni despliegue.

---

**Fin de B1-A-06.**
