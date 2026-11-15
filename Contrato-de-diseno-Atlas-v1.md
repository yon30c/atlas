# Atlas v1 — Contrato de diseño (revisión consolidada)

**Estado:** baseline arquitectónico aprobado por el propietario.
**Implementación:** autorizada únicamente para la Fase 1, conforme al alcance registrado en §20.5.
**Versión:** revisión 4.
**Fecha:** 15 de noviembre de 2026.
**Alcance:** especificación documental y contractual.
**Implementación:** este documento no autoriza ni declara implementados los componentes descritos.

---

## 0. Regla de coherencia entre secciones

Las declaraciones específicas de cada operación prevalecen sobre cualquier supuesto general de idempotencia.

Ningún esquema común, definición de Task, criterio de aceptación o mecanismo de reintentos podrá exigir o presumir soporte de idempotencia que no haya sido declarado explícitamente para la operación correspondiente.

Las reglas de autoridad exclusiva del propietario sobre decisiones de memoria prevalecen sobre las reglas generales de delegación de aprobaciones.

Cualquier sección, criterio de aceptación o flujo operativo que contradiga estas restricciones deberá interpretarse y corregirse para mantener la coherencia del contrato.

## 1. Convenciones de lectura y autoridad de las decisiones

Este documento utiliza las siguientes etiquetas:

- **APROBADO:** decisión explícitamente aceptada por el propietario. Es normativa para el diseño, pero no implica implementación.
- **PROPUESTA TÉCNICA:** formalización recomendada para convertir una decisión aprobada en un contrato implementable. Requiere revisión cuando implique una política nueva.
- **PARÁMETRO TÉCNICO PENDIENTE:** valor, algoritmo o mecanismo de implementación que todavía debe especificarse.
- **DECISIÓN DEL PROPIETARIO PENDIENTE:** política que requiere una elección explícita del propietario.
- **HISTÓRICO CONFIRMADO:** evidencia de un estado observado en una fecha determinada.
- **NO IMPLEMENTADO / NO VERIFICADO:** capacidad diseñada cuya implementación o estado actual no está acreditado.

### 1.1 Reglas de interpretación

1. Una decisión aprobada no vuelve a considerarse pendiente por el hecho de que falte definir su implementación.
2. Un parámetro técnico pendiente no permite omitir una garantía o invariante ya aprobada.
3. Una propuesta técnica no se convierte automáticamente en política aprobada.
4. Una capacidad descrita en este contrato no se considera implementada sin evidencia verificable.
5. La ausencia de identidad, autorización, clasificación, alcance o evidencia suficiente debe producir denegación o cuarentena cuando corresponda.
6. Ningún componente puede ampliar sus propios permisos.
7. La autorización se verifica en cada operación protegida, no solamente al iniciar una sesión o tarea.

### 1.2 Registro consolidado de decisiones y autoridad documental

Esta subsección establece cómo deben interpretarse las decisiones aprobadas, los parámetros técnicos y los estados de implementación descritos en el contrato.

#### 1.2.1 Autoridad de las decisiones

Las decisiones expresamente aprobadas por el propietario constituyen la referencia normativa para el diseño de Atlas.

Una decisión aprobada no vuelve a considerarse pendiente simplemente porque su implementación, mecanismo técnico o validación todavía no estén completos.

Las decisiones aprobadas deben mantenerse coherentes en todas las secciones del contrato.

Cuando una sección antigua contradiga una decisión aprobada posteriormente, prevalece la decisión aprobada más reciente y debe corregirse la sección contradictoria.

#### 1.2.2 Estados documentales

Se utilizarán las siguientes clasificaciones:

- **APROBADO:** decisión aceptada expresamente por el propietario. Es normativa para el diseño, pero no implica implementación.
- **BASELINE DE DESARROLLO APROBADO:** parámetro inicial aceptado para orientar desarrollo y pruebas. No constituye automáticamente una configuración de producción.
- **PROPUESTA TÉCNICA:** solución recomendada que todavía requiere aceptación cuando introduce una decisión nueva.
- **PARÁMETRO TÉCNICO PENDIENTE:** detalle de implementación todavía no definido.
- **DECISIÓN DEL PROPIETARIO PENDIENTE:** política que requiere una decisión expresa del propietario.
- **HISTÓRICO CONFIRMADO:** evidencia de un estado observado en una fecha determinada.
- **IMPLEMENTADO:** comportamiento cuya existencia está respaldada por evidencia verificable.
- **VERIFICADO:** comportamiento que ha superado las comprobaciones o pruebas correspondientes.
- **NO IMPLEMENTADO / NO VERIFICADO:** capacidad diseñada cuya implementación o funcionamiento no está acreditado.
- **POSTERGADO:** capacidad cuya implementación se ha aplazado expresamente.

#### 1.2.3 Separación entre aprobación e implementación

La aprobación de una decisión arquitectónica no autoriza a afirmar que su implementación existe.

La existencia de código tampoco demuestra por sí sola que una garantía de seguridad esté correctamente aplicada.

Para considerar una capacidad verificada se requiere evidencia apropiada, como inspección de código, pruebas, comprobaciones de integración o evidencia operativa, según corresponda.

La evidencia histórica debe conservar su fecha y alcance. No debe presentarse como una comprobación del estado actual.

#### 1.2.4 Baselines de desarrollo

Los parámetros expresamente aprobados como baseline de desarrollo se consideran decisiones aceptadas para orientar la implementación y las pruebas iniciales.

No deben volver a clasificarse como decisiones pendientes del propietario.

Su validación, ajuste y eventual configuración de producción siguen sujetos a pruebas y evidencia técnica.

Los parámetros no incluidos en el baseline aprobado continúan sujetos a sus respectivas decisiones o especificaciones pendientes.

#### 1.2.5 Mantenimiento y cambios

Toda modificación de una decisión aprobada debe contar con aceptación expresa del propietario.

Cuando se modifique una decisión, deberán actualizarse:

- Su registro documental.
- Las secciones técnicas afectadas.
- Los contratos entre componentes.
- Los criterios de aceptación y pruebas relacionados.

No deben conservarse clasificaciones pendientes que contradigan decisiones aprobadas posteriormente.

Tampoco deben elevarse propuestas técnicas o requisitos documentados a la categoría de aprobados sin aceptación expresa.

### 1.2.6 Estado global y revisión vigente

La revisión 3 constituyó el baseline arquitectónico aprobado el 13 de noviembre de 2026.

La revisión 4 incorpora la enmienda normativa B1-A-06, aprobada por el propietario el 15 de noviembre de 2026. La enmienda adopta las decisiones B1-A-01 a B1-A-05 como ampliaciones posteriores relativas a autorización PRIVATE, relación Project–Environment, Identity/bindings, integración Identity–CAM y persistencia SQLite local compartida.

La enmienda se conserva como documento separado en `docs/contracts/b1-a06-identity-project-environment-and-persistence.md` para mantener trazabilidad, historial y detalle. Forma parte del baseline normativo vigente y prevalece sobre disposiciones anteriores incompatibles dentro de su alcance. El contrato raíz continúa siendo el documento normativo principal.

La aprobación de la revisión 4 y de B1-A-06 es arquitectónica y documental. No declara que las capacidades estén implementadas, integradas, verificadas o desplegadas, ni amplía por sí misma la autorización de implementación registrada en §20.5.

Los parámetros técnicos pendientes pueden desarrollarse en fases posteriores siempre que respeten las decisiones, invariantes y garantías aprobadas. Toda modificación que debilite o posponga una garantía aprobada requiere nueva revisión y aprobación expresa del propietario.

## 2. Propósito y principios de Atlas

Atlas es un sistema personal de asistencia, coordinación y automatización de proyectos. Su objetivo es permitir que el propietario interactúe con sus proyectos, consulte su estado, reciba información relevante, investigue problemas y delegue tareas dentro de límites explícitos.

Atlas debe poder trabajar de forma autónoma cuando el propietario le haya concedido permisos adecuados, sin convertir esa autonomía en autoridad ilimitada.

### 2.1 Principios aprobados

- Mínimo privilegio.
- Separación entre identidad, autenticación y autorización.
- Aislamiento entre proyectos y entornos.
- Autoridad centralizada mediante Central Authorization Manager (CAM).
- Verificación de permisos antes de cada operación.
- Aprobación humana para operaciones sensibles y privilegiadas.
- Autonomía limitada por Grants explícitos.
- Recursos y concurrencia sujetos a límites compartidos.
- Coordinación obligatoria mediante Scheduler y Resource Lock Manager.
- Auditoría y trazabilidad de las operaciones.
- Recuperación segura ante fallos e interrupciones.
- Separación entre estado deseado y estado observado.
- No ejecutar automáticamente proyectos o skills restaurados.
- No presentar resultados parciales como trabajos completos.

### 2.2 Restauración y recuperación

**APROBADO:**

- Las restauraciones deben utilizar manifiestos, respaldos e integridad verificable.
- Una restauración comienza en modo de recuperación.
- No ejecutar automáticamente proyectos ni skills restaurados.
- Verificar respaldo, integridad y permisos antes de migraciones o cambios de estado.
- La activación posterior requiere una decisión deliberada y autorizada.

### 2.3 Alcance de implementación

El cierre de este contrato no certifica que estén construidos o desplegados:

- AtlasCore / Atlas Assistant.
- Central Authorization Manager.
- Authentication Service.
- Memory Engine.
- Event Collector.
- Analysis Engine.
- Scheduler.
- Resource Lock Manager.
- Resource Registry.
- Approval Manager.
- Notification Manager.
- Project Connectors y Watchers.
- Telegram Integration.
- Skill Manager.
- SecurityAudit.

Cada componente debe verificarse por separado antes de considerarlo operativo.

---

## 3. Arquitectura y límites de autoridad

### 3.1 Arquitectura conceptual

```text
Propietario
    |
    v
Authentication / Identity
    |
    v
Atlas Assistant / AtlasCore
    |
    +----------------------+
    |                      |
    v                      v
Central Authorization   Memory Gateway
Manager (CAM)               |
    |                       v
    |                  Memory Engine
    |
    v
Scheduler
    |
    v
Resource Lock Manager (RLM)
    |
    v
Resource Registry
    |
    +-----------------------------+
    |                             |
    v                             v
Project Connectors             Broker
Watchers                       |
    |                          v
    v                      Runtime aislado
Event Collector
    |
    v
Analysis Engine
    |
    v
Notification Manager
    |
    v
Telegram (solo salida en v1)

Approval Manager: gestiona solicitudes y decisiones humanas.
SecurityAudit / Event Store: registra eventos y resultados.
```

### 3.2 Responsabilidades

| Componente           | Responsabilidad                                                      | Autoridad que no posee                            |
| -------------------- | -------------------------------------------------------------------- | ------------------------------------------------- |
| Atlas Assistant      | Conversación, interpretación, planificación y solicitudes de trabajo | No concede permisos                               |
| Authentication       | Verificar identidad y autenticación                                  | No decide permisos de recursos                    |
| CAM                  | Evaluar y aplicar autorizaciones                                     | No ejecuta por sí mismo el trabajo                |
| Memory Gateway       | Aplicar scope y autorización sobre memoria                           | No concede permisos                               |
| Memory Engine        | Proponer, recuperar y gestionar registros de memoria                 | No aprueba sus propias propuestas                 |
| Scheduler            | Admitir, ordenar y coordinar tareas                                  | No concede permisos ni recursos                   |
| RLM                  | Coordinar exclusión y protección de recursos                         | Un lock no concede autorización                   |
| Resource Registry    | Catalogar recursos y sus políticas                                   | No concede acceso por sí solo                     |
| Approval Manager     | Registrar decisiones humanas                                         | Una solicitud no autoriza ejecución               |
| Event Collector      | Validar y registrar eventos                                          | No convierte eventos en órdenes                   |
| Analysis Engine      | Analizar eventos y generar conclusiones                              | No modifica recursos por analizar                 |
| Notification Manager | Preparar y entregar notificaciones                                   | No ejecuta comandos                               |
| Watchers             | Observar y publicar eventos                                          | No ejecutan operaciones de modificación           |
| Broker               | Aplicar operaciones permitidas en la frontera de ejecución           | No amplía permisos ni acepta comandos arbitrarios |

### 3.3 Arquitectura de confianza

**APROBADO:**

- Ningún componente obtiene autoridad simplemente por estar conectado.
- Cada petición conserva identidad, actor, origen, propósito y alcance.
- La identidad del principal autenticado se valida contra el actor declarado.
- La delegación debe ser explícita, verificable y limitada.
- CAM es la autoridad central de autorización.
- Las operaciones protegidas fallan de forma cerrada si CAM no está disponible.
- Los permisos se verifican antes de cada operación.
- Watchers observan y publican; no ejecutan operaciones protegidas.
- Notification Manager comunica; no ejecuta acciones.
- Un mensaje enviado, recibido o leído nunca equivale a una aprobación.

### 3.4 Evidencia histórica del Broker

**HISTÓRICO CONFIRMADO — 11 de noviembre de 2026:**

Se reportó:

- `atlas-broker.service`.
- Socket Unix `/run/atlas-broker/broker.sock`.
- UID 997, GID 985 y modo 0660.
- Registry SQLite v2 con `integrity_check=ok`.
- Proyecto `leadrd` con perfil `medium`.
- Estado deseado `stopped`, observado `registered` y `container_id=NULL`.
- UID 999 con acceso de solo lectura en las pruebas reportadas.
- Operaciones mutadoras denegadas.
- 84 pruebas correctas en el baseline reportado.
- Denegaciones visibles en journal, pero no en el `audit_log` persistente.

Estos datos son evidencia histórica. No certifican el estado actual del host ni la implementación del contrato completo.

---

## 4. Convenciones y esquemas lógicos

### 4.1 Convenciones generales

**PROPUESTA TÉCNICA:**

- JSON UTF-8.
- Nombres de campos en `snake_case`.
- Identificadores opacos e inmutables.
- Instantes en RFC 3339 UTC.
- Duraciones con unidad explícita.
- Registros persistentes con `schema_version`.
- Rechazar campos desconocidos en solicitudes de control.
- No almacenar secretos ni payloads sensibles en auditoría.
- Las mutaciones externas con resultado incierto deben reconciliarse antes de repetirse.
- Los IDs de proyecto y entorno deben validarse contra el registro autorizado.
- Los cambios de esquema deben ser versionados y compatibles con recuperación.

### 4.2 Solicitud común

idempotency_key es un campo opcional del esquema común de solicitudes.

Su presencia y obligatoriedad dependen de la operación solicitada:

Si una operación declara explícitamente soporte de idempotencia, la solicitud deberá incluir un idempotency_key válido.

Si una operación no declara soporte de idempotencia, el campo podrá omitirse.

La ausencia de idempotency_key en una operación que no declara soporte no constituye un error de validación.

La inclusión de una clave en una operación que no declara soporte no implica que el sistema garantice un comportamiento idempotente.

El contrato de cada operación deberá especificar expresamente si admite idempotencia y, cuando corresponda, las condiciones de uso y el alcance de la garantía.

```json
{
  "request_id": "req_id",
  "principal": {
    "identity_id": "identity_id",
    "authentication_context": "verified_context"
  },
  "actor": {
    "identity_id": "identity_id"
  },
  "origin": {
    "kind": "client|agent|watcher|service|system",
    "id": "origin_id"
  },
  "delegation": {
    "mode": "delegated|independent",
    "on_behalf_of": "identity_id|null",
    "grant_reference": "grant_id|null"
  },
  "purpose": "string",
  "project_id": "project_id",
  "environment_id": "environment_id",
  "operation": "catalogued_operation",
  "resource_ids": [],
  "classification": "classification",
  "arguments": {},
  "deadline": "instant|null",
  "correlation_id": "correlation_id",
  "skill_provenance": [
    {
      "skill_id": "skill_id",
      "skill_version": "version",
      "skill_digest": "digest"
    }
  ]
}
```

Los campos anteriores expresan el contrato lógico. La representación física puede variar.

Los campos `project_id` y `environment_id` son condicionales según la operación. Para operaciones sobre memoria privada, pueden ser `null` o estar ausentes cuando el scope explícito sea `PRIVATE`; su ausencia no convierte la operación en global ni elimina la obligación de identificar y validar el scope. Para memoria de proyecto, `project_id` es obligatorio, explícito y debe coincidir con el proyecto de la memoria. Los requisitos de entorno se determinan por la política de la operación correspondiente.

### Procedencia de ejecución de Skills

Cuando una operación involucre una o varias Skills, el contexto de la operación MUST conservar la procedencia de cada Skill que participe directamente en su ejecución.

Se utilizará el campo opcional `skill_provenance`, definido como un arreglo de registros de procedencia.

Cada registro MUST contener:

- `skill_id`: Identificador estable de la Skill.
- `skill_version`: Versión exacta de la Skill ejecutada.
- `skill_digest`: Resumen criptográfico del paquete o artefacto exacto aprobado e instalado.

El campo podrá omitirse cuando la operación no involucre Skills.

Cuando una operación involucre una o varias Skills, el arreglo MUST registrar todas las Skills que participen directamente en su ejecución, conservando la versión y el digest exactos de cada una.

No se deben registrar dos veces como entidades diferentes versiones idénticas de una misma participación de ejecución.

Esta información MUST permanecer asociada a la solicitud, la decisión de autorización, la ejecución y los eventos de auditoría correspondientes.

**APROBADO:**

- El principal autenticado no se acepta únicamente porque aparezca declarado en el payload.
- El canal de autenticación debe proporcionar evidencia verificable de identidad.
- El actor, el origen y la delegación son conceptos diferentes.
- La operación, el proyecto y el entorno deben estar definidos.
- Una solicitud no obtiene permisos por declarar un Grant.

### 4.3 Identity

```json
{
  "id": "identity_id",
  "kind": "user|agent|service|watcher|system",
  "issuer_id": "identity_id",
  "subject": "string",
  "status": "active|suspended|revoked",
  "authn_methods": ["passkey", "totp", "recovery_code", "service_credential"],
  "created_at": "instant",
  "expires_at": "instant|null",
  "revoked_at": "instant|null",
  "version": 1
}
```

La modalidad de delegación se registra en el contexto de autorización de la solicitud. No debe confundirse con la identidad misma.

### 4.4 Grant

```json
{
  "id": "grant_id",
  "owner_id": "owner_identity_id",
  "holder_id": "identity_id",
  "project_id": "project_id",
  "environment_id": "environment_id",
  "duration": "temporary|indefinite",
  "issued_at": "instant",
  "expires_at": "instant|null",
  "operations": ["permission_name"],
  "resource_limits": {},
  "shared_budget": {},
  "concurrency_limit": null,
  "status": "draft|active|suspended|revoked|expired|exhausted",
  "renewal_requested_at": "instant|null",
  "version": 1
}
```

### Límite de concurrencia del Grant

`concurrency_limit` representa el número máximo de tareas simultáneas que pueden ejecutarse utilizando el mismo Grant.

Su tipo lógico es un entero positivo o `null`.

- Un entero positivo representa el límite configurado.
- `null` representa que el límite todavía no ha sido configurado.
- `null` no significa concurrencia ilimitada.
- `null` no autoriza a omitir los controles de concurrencia.

La configuración de este campo corresponde exclusivamente al propietario, conforme a las reglas de §7.3.

Un Grant cuyo `concurrency_limit` sea `null` no podrá utilizarse para iniciar tareas hasta que el propietario configure un límite válido.

El estado `active` de un Grant no sustituye esta validación. Scheduler deberá comprobar el límite antes de admitir una tarea, incluso cuando el Grant esté activo.

Un valor ilustrativo de un esquema o ejemplo no constituye un límite operativo aprobado.

No se establece un valor predeterminado para `concurrency_limit` en este contrato.
El estado `draft` representa un Grant creado que todavía no ha sido activado.

Un Grant en estado `draft` MUST NOT autorizar ninguna operación.

La transición `draft → active` solo podrá realizarse después de completar la autorización del propietario y las verificaciones de activación correspondientes.

Un Grant revocado es terminal y MUST NOT reactivarse. Cualquier autorización nueva requiere la creación de otro Grant.

**APROBADO:**

- Cada Grant pertenece exactamente a un proyecto y un entorno.
- No existe herencia automática entre proyectos o entornos.
- Un Grant reutilizable puede ser utilizado por varias tareas dentro de su alcance.
- Las tareas comparten el presupuesto y los límites del Grant.
- El Grant no se amplía por delegación.
- La duración es `temporary` o `indefinite`.
- `temporary` es el valor predeterminado.
- Un Grant temporal exige `expires_at`.
- Un Grant indefinido solo se concede cuando el propietario lo selecciona expresamente.

Los valores concretos de recursos, concurrencia y límites se especifican en las secciones correspondientes.

### 4.5 Task

idempotency_key es un campo opcional de Task.

Solo deberá incluirse cuando la operación asociada declare soporte de idempotencia y requiera esta clave para controlar la repetición segura de solicitudes.

Una Task que corresponda a una operación sin soporte de idempotencia podrá existir sin este campo.

La presencia de idempotency_key no convierte por sí misma una operación en idempotente ni autoriza su reintento automático.

```json
{
  "id": "task_id",
  "requester_id": "identity_id",
  "actor_id": "identity_id",
  "origin": {
    "kind": "client|agent|watcher|service|system",
    "id": "origin_id"
  },
  "delegation_mode": "delegated|independent",
  "project_id": "project_id",
  "environment_id": "environment_id",
  "grant_id": "grant_id",
  "operation": "catalogued_operation",
  "priority": "critical|high|normal|low",
  "priority_history": [],
  "state": "submitted|queued|awaiting_approval|blocked_authorization|blocked_dependency|running|completed|partially_completed|skipped|failed|cancelled|outcome_unknown",
  "resource_request": {},
  "resource_expansion_count": 0,
  "created_at": "instant",
  "started_at": "instant|null",
  "completed_at": "instant|null",
  "deadline": "instant|null",
  "attempt": 0,
  "correlation_id": "correlation_id",
  "partial_results": []
}
```

El contador `resource_expansion_count` pertenece a cada tarea, no al proyecto ni al Grant.

### 4.6 Approval

```json
{
  "id": "approval_id",
  "request_id": "request_id",
  "task_id": "task_id",
  "requester_id": "identity_id",
  "approver_id": "identity_id|null",
  "authentication_evidence": null,
  "delegation_reference": "delegation_id|null",
  "action_digest": "digest",
  "scope": {
    "project_id": "project_id",
    "environment_id": "environment_id",
    "resource_ids": []
  },
  "risk": "catalogued_risk",
  "status": "pending|approved|denied|expired|revoked|consumed",
  "created_at": "instant",
  "expires_at": "instant",
  "decided_at": "instant|null",
  "reason": "string|null",
  "version": 1
}
```

El campo authentication_evidence será null cuando todavía no exista una decisión de aprobación o cuando la operación no requiera autenticación reforzada.

Cuando se requiera step-up authentication y esta haya sido completada correctamente, deberá contener un objeto con:

method: Método de autenticación utilizado.

verified_at: Fecha y hora de verificación.

evidence_reference: Referencia a la evidencia verificable.

La evidencia deberá corresponder a la identidad autenticada de quien aprueba y a la decisión específica.

Cuando la aprobación sea directa, delegation_reference será null. Cuando se utilice una delegación autorizada, deberá contener su referencia verificable.

La ausencia de evidencia obligatoria, cuando la política exija autenticación reforzada, MUST impedir la aprobación o ejecución correspondiente.

### Evidencia de autenticación y delegación

Cuando una aprobación requiera autenticación reforzada (`step-up authentication`), el registro de `Approval` MUST conservar una referencia verificable que permita comprobar que el desafío de autenticación se completó correctamente.

La evidencia deberá identificar:

- El método de autenticación utilizado.
- La fecha y hora de verificación.
- La referencia al registro verificable de autenticación.
- La identidad autenticada de quien aprobó.
- La referencia de delegación, cuando la aprobación se haya realizado mediante una delegación autorizada.

Cuando la aprobación sea directa, `delegation_reference` será `null`.

Cuando la aprobación todavía esté pendiente, los campos de evidencia de decisión permanecerán sin completar.

La evidencia de autenticación MUST NOT almacenar contraseñas, secretos, códigos de recuperación ni credenciales reutilizables.

La evidencia MUST permanecer vinculada a la aprobación, su operación y su alcance exactos.

### 4.7 Event

```json
{
  "event_id": "event_id",
  "event_type": "catalogued_event",
  "schema_version": 1,
  "occurred_at": "instant",
  "observed_at": "instant",
  "project_id": "project_id|null",
  "source": {
    "kind": "service|watcher|agent|system",
    "id": "source_id"
  },
  "actor": {
    "identity_id": "identity_id|null"
  },
  "classification": "public|internal|sensitive|restricted",
  "severity": "critical|important|informational|debug",
  "subject": {},
  "data": {},
  "correlation_id": "correlation_id",
  "evidence": [],
  "related_event_ids": []
}
```

### Clasificación de eventos

El campo `classification` utiliza exclusivamente los siguientes valores:

- `public`
- `internal`
- `sensitive`
- `restricted`

Estos valores constituyen el catálogo de clasificación general del evento. No deben crearse valores alternativos de clasificación para representar restricciones particulares de un canal de notificación.

Las etiquetas descriptivas utilizadas por otros componentes deberán interpretarse mediante este catálogo y no constituyen valores adicionales de `Event.classification`.

Para mantener la compatibilidad entre la clasificación general y las restricciones históricas de Telegram, se establece el siguiente mapeo:

| Etiqueta descriptiva | Clasificación general |
| -------------------- | --------------------- |
| `user_private`       | `sensitive`           |
| `system_restricted`  | `restricted`          |

Este mapeo permite interpretar las restricciones existentes sin ampliar el enum ni crear una segunda taxonomía de clasificación.

La clasificación del evento representa el nivel de protección de la información. No constituye por sí misma una autorización de acceso, procesamiento, exportación o divulgación.

Las políticas específicas de cada canal de notificación deberán respetar la clasificación general y aplicar adicionalmente las restricciones correspondientes al destinatario, propósito y contenido.

### Carácter opcional de `deduplication_key`

El campo `deduplication_key` es opcional y SHOULD incluirse cuando exista una clave estable que resulte útil para identificar eventos duplicados o relacionados.

Su ausencia MUST NOT invalidar un evento que, por lo demás, sea válido.

La presencia de `deduplication_key` MUST NOT interpretarse como prueba de idempotencia ni como garantía de que un proveedor externo impedirá la repetición de una operación.

**APROBADO:**

- `occurred_at` indica cuándo ocurrió el hecho.
- `observed_at` indica cuándo Atlas lo detectó.
- Los eventos son inmutables.
- Las correcciones generan nuevos eventos relacionados.
- La retención de eventos es indefinida.
- Los tipos de evento y severidades son controlados.
- No se puede declarar arbitrariamente un evento como crítico.
- Se minimizan secretos y contenido de logs.

### 4.8 Lock

```json
{
  "id": "lock_id",
  "resource_id": "resource_id",
  "scope": "project|atlas_global|external_shared",
  "project_id": "project_id|null",
  "owner_task_id": "task_id",
  "owner_actor_id": "identity_id",
  "mode": "shared|exclusive",
  "policy": "mandatory|advisory",
  "parent_resource_id": "resource_id|null",
  "state": "requested|waiting|held|released|expired|recovery_required|failed",
  "lease_expires_at": "instant|null",
  "heartbeat_at": "instant|null",
  "fencing_token": 0,
  "request_id": "request_id",
  "version": 1
}
```

La representación de locks y tokens debe conservar su relación con el recurso y la generación de adquisición.

---

## 5. Identidad, autenticación, delegación y CAM

### 5.1 Identidades aprobadas

Tipos:

- `user`
- `agent`
- `service`
- `watcher`
- `system`

Estados:

- `active`
- `suspended`
- `revoked`

Identidad y autorización son controles separados.

Una identidad activa no significa que tenga permisos para todos los recursos u operaciones.

### 5.2 Autenticación aprobada

El sistema de autenticación deberá contemplar:

- Passkey como método principal.
- TOTP como alternativa o segundo factor.
- Códigos de recuperación.
- Reautenticación para cambios sensibles.

La implementación de autenticación se realizará en una fase posterior.

La biometría local puede desbloquear una credencial o dispositivo, pero no constituye por sí sola una identidad universal de Atlas.

### 5.3 Delegación

Modos aprobados:

- `delegated`: Assistant actúa en nombre del usuario dentro de permisos concedidos.
- `independent`: Assistant actúa únicamente con su identidad propia.

**APROBADO:**

- La delegación debe ser explícita, verificable y limitada.
- Se deben conservar actor, origen y principal.
- La delegación no amplía operaciones, proyecto, entorno, duración ni recursos del Grant.
- Ningún agente puede concederse permisos.
- Ningún agente puede aprobar su propia solicitud.

**DECISIÓN PENDIENTE:** modalidad inicial de delegación. Se propuso `delegated`, pero no consta una aprobación explícita del valor inicial.

### 5.4 Central Authorization Manager

CAM es la autoridad central encargada de evaluar y aplicar las decisiones de autorización de Atlas.

La concesión, modificación, renovación y revocación de Grants corresponde exclusivamente al propietario. CAM aplica esas decisiones y verifica que cada operación se encuentre dentro del alcance autorizado.

**APROBADO:**

- Solo el propietario de Atlas puede conceder, modificar, renovar y revocar Grants.
- Los agentes y skills pueden solicitar permisos, pero nunca concedérselos.
- Las operaciones protegidas consultan CAM.
- CAM verifica el alcance exacto de cada operación.
- CAM falla de forma cerrada cuando no puede evaluar una operación protegida.
- Ningún componente puede cambiar sus propios permisos.
- La revocación afecta las operaciones nuevas inmediatamente.
- Las decisiones de autorización deben quedar registradas.

### 5.5 Evaluación de autorización

La evaluación debe considerar:

1. Identidad autenticada.
2. Actor efectivo.
3. Origen.
4. Delegación.
5. Operación.
6. Recurso.
7. Proyecto.
8. Entorno.
9. Clasificación.
10. Propósito.
11. Grant.
12. Aprobación, si corresponde.
13. Presupuesto y concurrencia.
14. Estado y vigencia de las políticas.

Cuando la operación identifica un recurso concreto, CAM MUST comprobar que el `resource_id` autorizado coincide con el recurso solicitado. Una autorización limitada únicamente al tipo de recurso no concede acceso implícito a todas sus instancias. Las operaciones colectivas podrán autorizarse por tipo solo cuando su semántica, alcance y permiso estén definidos expresamente. Si el identificador es obligatorio y falta, no coincide o no puede verificarse, la decisión será `deny`. CAM MUST comprobar también que el recurso pertenece al propietario y proyecto compatibles con el scope y la autorización evaluada.

Para operaciones de memoria privada, CAM evaluará una regla explícita de acceso del propietario a su propia memoria. Esta regla no requiere un Grant de proyecto, pero no omite CAM ni Memory Gateway y no concede acceso a otros actores. Para memoria de proyecto, se requiere un `project_id` explícito y coincidente, además de la autorización CAM correspondiente.

Resultados lógicos:

- `allow`
- `deny`
- `require_approval`

**PROPUESTA TÉCNICA — `defer`:**

Indica que la operación no puede continuar hasta resolver una condición pendiente. No representa un permiso temporal ni autoriza la ejecución.

### 5.6 Permisos granulares

Catálogo de permisos acordado:

**Memoria**

- `memory.read`
- `memory.propose`
- `memory.review`
- `memory.approve`
- `memory.reject`
- `memory.update`
- `memory.forget`
- `memory.export`

**Proyectos**

- `project.read`
- `project.manage`

**Eventos**

- `events.read`
- `events.publish`
- `events.acknowledge`

**Permisos**

- `permissions.read`
- `permissions.grant`
- `permissions.revoke`

**Aprobaciones**

- `approvals.request`
- `approvals.decide`

**Notificaciones**

- `notifications.read`
- `notifications.manage`

Los permisos operativos de ejecución, recursos, skills y Broker deben estar definidos mediante operaciones específicas del catálogo, no mediante un permiso genérico ilimitado.

`memory.approve` no se concede a Atlas Assistant, Watchers ni Memory Service como autoridad automática.

### 5.7 Alcance de los Grants

Cada Grant está limitado a:

- Un `project_id`.
- Un `environment_id`.
- Operaciones concretas.
- Recursos y límites autorizados.
- Una duración.
- Un propietario que lo concede.

Entornos iniciales:

- `development`
- `testing`
- `staging`
- `production`

Un Grant de desarrollo no autoriza operaciones en producción.

La ausencia o incertidumbre de proyecto o entorno produce denegación.

---

## 6. Grants, autonomía, recursos y presupuestos

### 6.1 Duración y vigencia

**APROBADO:**

- Duración `temporary` o `indefinite`.
- `temporary` es el valor predeterminado.
- `indefinite` exige selección explícita del propietario.
- Los Grants temporales tienen fecha y hora de expiración obligatorias.
- Expirar bloquea nuevas operaciones.
- La expiración no borra el historial.
- Cambiar de temporal a indefinido requiere autenticación y confirmación explícita.
- Los Grants indefinidos pueden revocarse en cualquier momento.

### 6.2 Renovación de Grants temporales

**APROBADO:**

- Atlas puede solicitar automáticamente una renovación.
- Atlas nunca puede aprobar su propia renovación.
- La anticipación predeterminada es de 24 horas.
- El propietario puede configurar globalmente o por Grant la anticipación.
- Atlas evalúa si el Grant sigue siendo necesario antes de solicitar renovación.
- No se generan solicitudes innecesarias si la tarea terminó.
- La solicitud queda pendiente hasta que el propietario responda o expire el Grant.
- No existe una extensión automática por silencio.
- El silencio significa que el Grant expira en su fecha original.
- El rechazo cierra la solicitud.
- Ampliar el alcance requiere una solicitud nueva.

### 6.3 Revocación y expiración durante tareas activas

**APROBADO:**

La revocación o expiración de un Grant:

1. Bloquea nuevas operaciones que dependan de ese Grant.
2. Afecta inmediatamente las tareas dependientes.
3. Detiene de forma segura las operaciones en curso cuando sea técnicamente posible.
4. Si una interrupción inmediata compromete la integridad de los datos o recursos, se permite alcanzar un punto seguro de consistencia antes de detener la operación.
5. Durante ese intervalo no se pueden iniciar nuevas operaciones ni ampliar el alcance de las operaciones existentes.
6. Pausa el flujo afectado cuando no pueda determinarse su independencia o autorización.
7. Conserva los resultados parciales.
8. Informa las operaciones completadas, bloqueadas, omitidas, pendientes y en progreso.
9. No presenta una ejecución parcial como completa.
10. No permite utilizar la ejecución parcial para eludir la revocación.

**BASELINE DE DESARROLLO APROBADO:**

- Tiempo de cancelación cooperativa: 30 segundos.
- Espera adicional de terminación: 15 segundos.
- Verificación obligatoria de terminación antes de liberar recursos.

**PARÁMETROS TÉCNICOS PENDIENTES:**

- Tratamiento específico de procesos que no responden.
- Reconciliación de procesos huérfanos.
- Mecanismos técnicos de verificación de terminación.

La política de ejecución parcial no está pendiente.

### 6.4 Autonomía

Capacidades independientes aprobadas:

| Capacidad | Alcance                                                     |
| --------- | ----------------------------------------------------------- |
| `monitor` | Vigilar proyectos, servicios y repositorios                 |
| `analyze` | Investigar errores, consultar logs y analizar evidencias    |
| `propose` | Preparar soluciones y cambios sin aplicarlos                |
| `execute` | Aplicar cambios u operaciones dentro de permisos concedidos |

**APROBADO:**

- Observar no autoriza modificar.
- Analizar no autoriza ejecutar.
- Proponer no autoriza aplicar.
- Ejecutar exige Grant y permisos específicos.
- Atlas puede iniciar tareas por sí mismo si tiene los permisos correspondientes.
- Ninguna tarea puede ampliar sus propios permisos.
- Las tareas autónomas pueden ejecutarse en segundo plano dentro de las autorizaciones vigentes.
- Operaciones no autorizadas se bloquean.
- Las partes independientes autorizadas pueden continuar.

### 6.5 Estados de ejecución

Estados lógicos aprobados:

- `completed`
- `blocked_authorization`
- `blocked_dependency`
- `skipped`
- `failed`
- `partially_completed`
- `awaiting_approval`

También pueden existir estados operativos como `submitted`, `queued`, `running`, `cancelled` y `outcome_unknown`.

### 6.6 Presupuesto compartido

**APROBADO:**

- Cada Grant tiene límites de recursos.
- Los límites son compartidos por todas las tareas que utilizan ese Grant.
- No se crean presupuestos independientes por tarea.
- No se consumen recursos asignados a otros proyectos sin autorización.
- Antes de iniciar una tarea se verifica disponibilidad.
- La concurrencia y el presupuesto son controles independientes.
- Ampliar recursos no amplía permisos ni límites de concurrencia.

### 6.7 Ampliación automática de recursos

**APROBADO:**

Atlas puede efectuar una única ampliación automática por tarea a la siguiente configuración disponible, siempre que:

1. Sea suficiente para continuar la tarea.
2. Exista capacidad disponible.
3. Se respeten los límites globales.
4. No se consuman recursos de otros proyectos sin autorización.
5. No se salten configuraciones arbitrariamente.
6. No se consuman todos los recursos del host.

Si la siguiente configuración no es suficiente, Atlas solicita autorización al propietario.

Una segunda ampliación en la misma tarea requiere autorización.

La ampliación automática:

- Modifica el presupuesto compartido del Grant.
- Queda registrada.
- No crea un presupuesto paralelo.
- No reinicia el contador de otra tarea.
- No amplía permisos.
- Puede beneficiar a otras tareas que utilicen el mismo Grant, si existe capacidad adicional disponible y cumplen sus límites.

Cada tarea tiene su propio contador de ampliación automática.

### 6.8 Liberación de recursos

**APROBADO:**

- Liberar recursos reservados cuando la tarea termina, falla o se cancela.
- Actualizar el presupuesto compartido.
- Registrar recursos utilizados y liberados.
- No liberar recursos solo porque cambió el estado lógico de una tarea.
- Verificar que los procesos y contenedores asociados terminaron realmente.
- Si el estado es incierto, mantener la protección y reconciliar.

---

## 7. Scheduler: prioridad, envejecimiento y concurrencia

### 7.1 Prioridades

Prioridades aprobadas:

`critical > high > normal > low`

Atlas debe recomendar una prioridad inicial considerando:

- Urgencia temporal.
- Impacto.
- Consecuencias del retraso.
- Dependencias.
- Riesgos.
- Deadlines.

Importancia y urgencia son conceptos diferentes.

La prioridad nunca concede permisos ni recursos adicionales.

### 7.2 Envejecimiento

Política aprobada:

| Prioridad actual | Tiempo para promover un nivel | Prioridad máxima |
| ---------------- | ----------------------------: | ---------------- |
| `low`            |                      24 horas | `high`           |
| `normal`         |                       8 horas | `high`           |
| `high`           |                       2 horas | `critical`       |
| `critical`       |                     No aplica | `critical`       |

**APROBADO:**

- Los intervalos son configurables por el propietario.
- La promoción es gradual, un nivel cada vez.
- `low` también puede ascender por envejecimiento.
- No se permiten saltos de varios niveles por una interrupción.
- La promoción automática no reinicia el contador de espera.
- Un cambio manual de prioridad reinicia el contador de envejecimiento.
- El cambio manual establece nueva prioridad inicial y nuevo máximo.
- Se conserva el historial anterior y el actor que cambió la prioridad.
- La prioridad inicial, actual, máxima y el motivo deben conservarse.
- Al recuperar una tarea interrumpida se recalcula su envejecimiento sin saltos múltiples.

### 7.3 Límites de concurrencia

Hay tres límites independientes y obligatorios:

1. **Global:** máximo de tareas simultáneas en Atlas.
2. **Proyecto + entorno:** máximo de tareas simultáneas para cada combinación.
3. **Grant:** máximo de tareas simultáneas que utilizan el mismo Grant.

**APROBADO:**

- Los tres límites deben disponer de capacidad antes de iniciar.
- Si cualquiera está lleno, la tarea permanece en cola.
- Los límites son configurables exclusivamente por el propietario.
- Ampliar recursos no amplía automáticamente concurrencia.
- Una tarea en cola no consume un cupo de ejecución.
- Una tarea en cola no reserva recursos adicionales.
- Antes de iniciar se vuelven a validar CAM, Grant, entorno, capacidad y RLM.

### Configuración y validación

Los tres límites deben estar configurados con valores enteros positivos y verificables antes de admitir una tarea.

Para el límite asociado al Grant, el valor se representa mediante `concurrency_limit`, definido en §4.4.

La ausencia de configuración, un valor inválido o la imposibilidad de verificar cualquiera de los tres límites impedirá iniciar la tarea.

La falta de configuración no equivale a disponibilidad ilimitada ni permite utilizar un límite alternativo.

Scheduler deberá verificar simultáneamente la capacidad de los tres ámbitos. Disponer de capacidad en uno o dos ámbitos no compensa la falta de capacidad o configuración en el tercero.

Los valores numéricos de los límites permanecen pendientes de configuración por el propietario. No se establece en este contrato un valor predeterminado global, por proyecto, entorno o Grant.

La expansión automática de recursos no podrá modificar estos límites ni incrementar la concurrencia permitida.

### 7.4 Orden de ejecución

**APROBADO:**

- Ordenar las tareas por prioridad efectiva y antigüedad.
- Aplicar promoción gradual para evitar starvation.
- Una tarea `critical` bloqueada debe notificarse al propietario.
- Atlas puede explicar el bloqueo y solicitar autorización de ampliación cuando corresponda.
- No puede ampliar permisos o recursos fuera de las reglas aprobadas.
- El desempate seguirá este orden determinista:
  1. Mayor prioridad efectiva.
  2. Mayor antigüedad dentro de la prioridad.
  3. Fecha y hora de entrada a la cola más antigua.
  4. `task_id` en orden lexicográfico ascendente como desempate final.

**PARÁMETROS TÉCNICOS PENDIENTES:**

- Valores de concurrencia global, proyecto-entorno y Grant.
- Persistencia de la cola.
- Recuperación de cupos tras una caída.
- Algoritmo técnico exacto de envejecimiento después de interrupciones, respetando la promoción secuencial.

---

## 8. Resource Registry y Resource Lock Manager

### 8.1 Resource Registry

**APROBADO:**

El Resource Registry es centralizado y obligatorio.

Ningún recurso protegido puede utilizarse sin estar registrado y clasificado.

Ámbitos:

- `project`: recursos propios de un proyecto.
- `atlas_global`: recursos centrales compartidos por Atlas.
- `external_shared`: recursos externos o compartidos entre proyectos.

Ejemplos:

- Archivos y directorios.
- Bases de datos.
- Servicios.
- Repositorios.
- Configuración central.
- Scheduler.
- CAM.
- Infraestructura compartida.

El registro debe incluir:

- `resource_id` único.
- `scope`.
- `project_id`, cuando corresponda.
- `resource_type`.
- Jerarquía padre/hijo.
- `lock_policy`.
- `owner`: Identidad del propietario de Atlas responsable de la gobernanza y autorización del recurso.
- `technical_custodian`: Identidad de la persona o servicio responsable de la custodia o administración técnica del recurso, cuando corresponda.
- Clasificación.
- Estado.
- Capacidad y unidad, cuando aplique.
- Atributos no secretos necesarios para identificar el recurso.

El campo `owner` no debe confundirse con la persona o servicio que administra técnicamente el recurso.

La custodia técnica no concede autoridad para aprobar, modificar, suspender o retirar recursos ni sus políticas.

La aprobación, modificación, suspensión y retirada de recursos protegidos continúan siendo facultades exclusivas del propietario de Atlas, conforme a las políticas de autorización y aprobación aplicables.

Estados aprobados:

- `pending_review`
- `active`
- `suspended`
- `retired`

**APROBADO:**

- Los agentes y skills pueden solicitar registro.
- Solo el propietario puede aprobar, modificar, suspender o retirar recursos y políticas.
- Un recurso desconocido o no clasificado se bloquea.
- Suspender o retirar un recurso no libera locks mientras haya procesos utilizándolo.
- La transición debe realizarse de forma segura.

### 8.2 Ámbitos y aislamiento

Los tres ámbitos no se cruzan implícitamente.

Un recurso `project` no autoriza acceder a otro proyecto.

Un recurso `atlas_global` tiene controles reforzados.

Un recurso `external_shared` requiere identidad, alcance y autorización explícitos.

### 8.3 RLM obligatorio

El Resource Lock Manager es obligatorio para agentes, skills y tareas que accedan a recursos compartidos protegidos.

**APROBADO:**

- Ninguna tarea puede omitir RLM.
- Tener un lock no concede permisos.
- CAM continúa autorizando cada operación.
- Si RLM no está disponible, las operaciones protegidas esperan o se bloquean.
- No se permite utilizar rutas alternativas para evitar el bloqueo.
- No se libera un lock mientras un proceso siga utilizando el recurso.
- Ante incertidumbre, se mantiene la protección.

### 8.4 Bloqueos jerárquicos

**APROBADO:**

- Los locks pueden tener relación padre-hijo.
- Un lock exclusivo de directorio protege el directorio y sus descendientes.
- Un lock de archivo protege ese archivo, no los archivos vecinos.
- RLM detecta conflictos padre-hijo.
- Los modos shared y exclusive respetan la jerarquía.
- La jerarquía no permite cruzar límites de proyecto, globales o externos sin autorización explícita.

### 8.5 Modos y políticas

Modos fundamentales aprobados:

- `shared`
- `exclusive`

Políticas aprobadas:

- `mandatory`
- `advisory`

Un lock mandatory es obligatorio y su ausencia bloquea el efecto protegido.

Un lock advisory sirve para coordinación voluntaria, pero nunca sustituye:

- CAM.
- Scheduler.
- Un lock mandatory.
- Una aprobación humana.
- Una autorización de acceso.

No se asigna semántica adicional a otros modos sin especificación explícita.

### 8.6 Adquisición de múltiples locks

**APROBADO:**

- Orden global determinista de adquisición.
- Detección de conflictos jerárquicos.
- Si una tarea necesita varios locks, no debe conservar locks parciales mientras espera por los restantes.
- Debe adquirir el conjunto necesario de forma coordinada o esperar sin retener bloqueos parciales.
- La liberación y recuperación deben ser verificables.

**PARÁMETROS TÉCNICOS PENDIENTES:**

- Orden canónico exacto de adquisición.
- Mecanismo de adquisición atómica o compensación segura.
- Persistencia transaccional.
- Adaptadores para recursos externos.

**BASELINE DE DESARROLLO APROBADO:**

- Backoff exponencial con jitter completo.
- Secuencia de espera máxima: 1, 2, 4, 8, 16 y 30 segundos; posteriormente, máximo de 30 segundos.

### 8.7 Deadlocks

**APROBADO:**

- Detección de ciclos en el grafo de espera.
- Tiempo máximo de espera configurable por el propietario.
- Recuperación mediante cancelación segura o replanificación.
- Selección determinista de víctima según este orden:
  1. Menor prioridad actual.
  2. Menor cantidad de trabajo completado que habría que recuperar.
  3. Menor impacto sobre tareas dependientes.
  4. Si persiste el empate, antigüedad e ID de tarea como desempate determinista.

La tarea víctima:

- Se detiene de forma segura.
- Conserva resultados parciales.
- Se devuelve a la cola si sigue autorizada y puede reintentarse.
- No se reintenta si la autorización ha sido revocada o la operación ya no es válida.
- Debe quedar registrada junto con la incidencia y la decisión de recuperación.

**BASELINE DE DESARROLLO APROBADO:**

- Frecuencia de detección de deadlocks: 5 segundos.
- Escalamiento de la incidencia: 30 segundos.
- Tiempo máximo de espera por lock: 300 segundos.
- Máximo de 3 recuperaciones automáticas.
- Máximo de 8 reintentos automáticos por operación recuperable.
- Backoff exponencial con jitter completo: 1, 2, 4, 8, 16 y 30 segundos; posteriormente, máximo de 30 segundos.

**PARÁMETROS TÉCNICOS PENDIENTES:**

- Algoritmo exacto de replanificación.
- Umbrales adicionales de recuperación.

### 8.8 Lease, heartbeat y fencing

**APROBADO:**

- Cada lock tiene un lease temporal renovable.
- Un supervisor comprueba periódicamente actividad y autorización mediante heartbeat.
- Cada adquisición tiene un fencing token de generación creciente.
- La expiración del lease no significa que el recurso esté libre.
- Antes de una nueva adquisición se verifica que el proceso anterior terminó o se impide técnicamente que siga modificando el recurso.
- El fencing token debe ser validado por el recurso o adaptador que controle todas las escrituras.
- Emitir un token sin hacerlo cumplir no constituye protección.

**BASELINE DE DESARROLLO APROBADO:**

- Duración del lease: 30 segundos.
- Intervalo de heartbeat: 10 segundos.
- Tolerancia: 3 heartbeats fallidos.
- Margen de renovación: 5 segundos.
- Timeout de adquisición de lock: 300 segundos.
- Fencing token monotónico y persistente.
- Validación del fencing token en cada escritura.
- La validación debe realizarla el recurso o un adaptador que controle todas las escrituras.
- Si un recurso no admite fencing verificable, se requiere un adaptador que controle todas las escrituras o se bloquea el acceso concurrente peligroso.

**PARÁMETROS TÉCNICOS PENDIENTES:**

- Tolerancia de reloj.
- Formato técnico del fencing token.
- Adaptadores concretos y sus mecanismos de validación.

### 8.9 Persistencia y recuperación

**APROBADO:**

La persistencia debe conservar:

- ID del lock.
- Recurso y ámbito.
- Tarea y actor propietarios.
- Modalidad.
- Lease.
- Último heartbeat.
- Fencing token.
- Estado.
- Historial.

Al iniciar Atlas:

1. RLM entra en recuperación.
2. Se bloquean nuevas adquisiciones de recursos protegidos.
3. Se leen los locks persistidos.
4. Se verifican procesos, supervisores, leases y uso real.
5. Se recuperan locks válidos.
6. Se retiran locks obsoletos solo después de verificar seguridad.
7. Se mantienen protegidos los recursos inciertos.
8. Se reanudan tareas solo después de revalidar CAM y Grants.

Nunca se considera libre un lock únicamente porque su lease expiró.

### 8.10 Integración Scheduler–CAM–RLM

**APROBADO:**

El flujo obligatorio es:

1. Scheduler identifica proyecto, entorno, Grant, prioridad y recursos.
2. CAM valida identidad y autorización.
3. Scheduler valida concurrencia global, por proyecto-entorno y por Grant.
4. Scheduler valida presupuesto compartido.
5. RLM adquiere los locks necesarios en orden determinista.
6. Si no puede adquirirlos todos, la tarea espera sin retener locks parciales.
7. Antes de iniciar se revalidan autorización, capacidad y locks.
8. Durante la ejecución se mantienen heartbeat, leases y fencing.
9. Al finalizar se verifica terminación.
10. Se liberan recursos y se registran resultados.

Ninguna prioridad permite saltarse este flujo.

---

## 9. Memory Engine

### 9.1 Propósito

Memory Engine gestiona memoria histórica, decisiones, contexto de proyectos y conocimiento aprobado.

Debe distinguir:

- Memoria histórica.
- Estado observado en vivo.
- Análisis y conclusiones.

La memoria histórica no debe presentarse como evidencia del estado actual.

### 9.2 Aislamiento

**APROBADO:**

- La memoria se separa por scope: memoria privada del propietario y memoria asociada a un proyecto.
- El propietario puede acceder a su propia memoria privada mediante una regla explícita de autorización evaluada por CAM; no necesita un Grant de proyecto. Esta regla no constituye un bypass de CAM ni de Memory Gateway.
- Ningún otro actor obtiene acceso a la memoria privada del propietario por defecto.
- Un proyecto no puede acceder a la memoria privada de otro ni a la memoria privada del propietario por defecto.
- El acceso a memoria de proyecto exige un `project_id` explícito, válido y coincidente con el scope de la memoria, y la autorización correspondiente de CAM.
- Scopes ausentes, incompletos, ambiguos o inconsistentes producen denegación.
- CAM controla acceso y alcance.
- Un índice global puede localizar referencias, pero no revelar contenido privado.
- Cognee es candidato para almacenamiento o recuperación semántica.
- Cognee no es autoridad de identidad ni autorización.
- No instalar Cognee todavía.

### 9.3 Incorporación de memoria

**APROBADO:**

El proceso es `review`.

Atlas propone y el propietario revisa/aprueba.

Estados:

- `pending_review`
- `approved`
- `rejected`
- `superseded`
- `forgotten`

Las propuestas pendientes no entran en el índice de memorias aprobadas.

Una modificación posterior a una memoria aprobada crea una nueva versión y requiere revisión.

**APROBADO:**

- Las propuestas en estado `pending_review` no pueden utilizarse como conocimiento aprobado ni incorporarse al índice de memorias aprobadas.
- La aprobación corresponde al propietario y no puede ser realizada automáticamente por Atlas Assistant, Memory Engine o una skill.
- La aprobación de una memoria no concede permisos de acceso a otros proyectos ni modifica las reglas de clasificación.
- Cada versión conserva una clasificación explícita. Una nueva versión no puede rebajar automáticamente la clasificación de la anterior; cualquier cambio de clasificación requiere revisión y decisión directa del propietario.
- La versión aprobada anterior permanece vigente mientras una nueva versión está pendiente.
- La aprobación de una nueva versión, la transición de la anterior a `superseded` y la actualización de la referencia a la versión vigente deben realizarse atómicamente. Una operación fallida no puede dejar dos versiones vigentes ni una referencia inconsistente.

### 9.4 Olvido y eliminación

Las decisiones de aprobación, rechazo, sustitución y eliminación de información de memoria son facultad exclusiva del propietario de Atlas.

Esta exclusividad comprende, como mínimo:

- Aprobar o rechazar propuestas de memoria.
- Aprobar nuevas versiones de memorias existentes.
- Autorizar operaciones memory.forget.
- Autorizar la eliminación definitiva de información de memoria en los almacenes correspondientes.

Estas decisiones no podrán delegarse a agentes, servicios, Watchers, Skills ni a otros usuarios autorizados como aprobadores.

La delegación de aprobaciones para otras operaciones no implica ni concede autoridad sobre decisiones de memoria.

Atlas podrá analizar, proponer y solicitar estas decisiones, pero no podrá aprobarlas ni ejecutarlas por iniciativa propia cuando requieran autorización del propietario.

**APROBADO:**

- `memory.forget` requiere autorización mediante CAM y aprobación específica y directa del propietario de Atlas. La aprobación no puede delegarse. CAM deberá validar por separado que el actor tiene autorización vigente para ejecutar la operación.
- La eliminación debe contemplar los almacenes principales, índices derivados, réplicas y respaldos pertinentes.
- La restauración o reindexación no puede reintroducir una memoria cuyo olvido haya sido aprobado y ejecutado. Esta garantía requiere una fuente de supresión/continuidad que no pueda retroceder junto con el backup. En el perfil local sin Trust Anchor externo, Atlas no puede demostrar por sí solo que el backup sea posterior al Forget; la restauración de datos de memoria afectados por un Forget posterior al backup debe permanecer bloqueada hasta reconciliarse con una fuente independiente aprobada. No se declarará satisfecha esta garantía mediante una comprobación de integridad local solamente.
- La evidencia de eliminación debe permitir verificar la operación sin conservar innecesariamente el contenido olvidado.

**APROBADO:**

- Mantener un registro mínimo de supresión que permita reconocer memorias olvidadas durante reindexaciones, importaciones y restauraciones, sin conservar su contenido original ni hashes de contenido susceptibles a ataques de diccionario.
- La supresión lógica debe impedir inmediatamente la consulta, recuperación o exposición, aunque una copia de respaldo inmutable permanezca retenida temporalmente.
- La eliminación no se considera completada mientras existan destinos aplicables sin verificar o copias físicas retenidas dentro del plazo de retención.
- Si un almacén, índice, réplica o respaldo no responde, o la eliminación es parcial, la memoria permanece bloqueada para recuperación; el proceso queda pendiente de reconciliación y no se comunica éxito.
- Restauraciones, reindexaciones e importaciones deben aplicar el registro de supresión antes de exponer datos.
- El estado de supresión de la memoria lógica se distingue del ciclo de vida de sus versiones y no introduce estados adicionales a los definidos en §9.3.

**PARÁMETROS TÉCNICOS PENDIENTES:**

- Plazo de retención de respaldos inmutables y propagación máxima.
- Inventario de almacenes, índices, réplicas, cachés y sistemas derivados.
- Criterios verificables y mecanismo de reconciliación para declarar completada la supresión.

### 9.5 Propuesta técnica de registro

La identidad lógica de memoria y sus versiones se representan por separado:

- `Memory`: identificador lógico, propietario canónico, scope explícito, referencia a la versión aprobada vigente y timestamps de creación/actualización.
- `MemoryVersion`: identificador de versión, memoria asociada, número monotónico, contenido inmutable, clasificación explícita, estado, procedencia, referencia a versión antecesora y metadatos temporales/de revisión.
- `MemoryScope`: tipo `PRIVATE` o `PROJECT`; `project_id` es obligatorio solo para `PROJECT`. El propietario se mantiene de forma canónica en `Memory.owner_id` y no se duplica en el scope.
- `MemoryProposal`: identifica si propone crear una memoria lógica o una nueva versión de una memoria existente y mantiene referencias a la propuesta, memoria y versión resultante.
- La procedencia es obligatoria por versión. Incluye actor/componente de origen, contexto y proyecto cuando correspondan, fecha, propuesta originaria, referencias de fuente/evidencia y versión antecesora.
- Las referencias a fuentes y evidencias no conceden acceso; su lectura requiere autorización y scope propios.
- Una fuente que desaparece conserva su referencia histórica y se marca como no disponible. Esto no elimina automáticamente la memoria ni prueba que la fuente siga verificándola.
- La aprobación o rechazo registra identidad del propietario, propuesta y versión afectadas, decisión, fecha/hora, contexto y evidencia verificable de inicio directo por el propietario.

**APROBADO:**

- El scope debe distinguir memoria privada del usuario y memoria asociada a un proyecto.
- El acceso a memoria de proyecto se determina mediante CAM y las autorizaciones correspondientes.
- La procedencia debe conservarse para permitir rastrear el origen de cada registro.
- Las versiones anteriores deben conservar su relación histórica con la versión vigente, sin sustituir automáticamente el conocimiento aprobado actual.

**PARÁMETROS TÉCNICOS PENDIENTES:**

- Formato definitivo de los identificadores de scope y política de transferencia/reclasificación entre scopes.
- Política de retención de versiones históricas.
- Representación técnica del registro de supresión, su reconciliación y protección contra reintroducción.
- Mecanismo técnico verificable de evidencia de decisión directa del propietario.
- Catálogo y reglas de clasificación específicas de Memory Engine.
- Inventario de almacenes/índices/réplicas/cachés y criterios/plazos de verificación de supresión.

---

## 10. Eventos, incidencias y SecurityAudit

### 10.1 Eventos generales

**APROBADO:**

Cada evento debe contemplar, según corresponda:

- `event_id`
- `event_type`
- `occurred_at`
- `observed_at`
- `project_id`
- `source`
- `actor`
- `classification`
- `severity`
- `subject`
- `data`
- `correlation_id`
- `deduplication_key`
- `evidence`
- Identificadores de entidades relacionadas.

Los campos de la estructura del evento se incluyen según corresponda a la naturaleza del evento. En particular, `deduplication_key` es opcional y su ausencia no invalida el registro.

La deduplicación de eventos y la idempotencia de operaciones son mecanismos independientes. Una clave de deduplicación MUST NOT sustituir las garantías explícitas de idempotencia de una operación.

Los campos opcionales deben utilizarse según la naturaleza del evento. Su presencia no autoriza almacenar secretos ni información sensible innecesaria.

### 10.2 Incidencias

Estados:

- `open`
- `acknowledged`
- `resolved`
- `reopened`

Una incidencia puede relacionar múltiples eventos.

La actualización de una incidencia no modifica retroactivamente los eventos originales.

### 10.3 SecurityAudit

**DISEÑO APROBADO; IMPLEMENTACIÓN POSTERGADA.**

SecurityAudit se mantiene separado del Registry y del logging operativo.

Diseño acordado:

- Módulo `security_audit.py`.
- Base `/var/lib/atlas-broker/security-audit.db`.
- Registry `projects.db` separado.
- Registro append-only.
- Actor, operación, decisión, resultado y correlación.
- Sin payloads sensibles.
- Logging operativo independiente.
- Registrar `intent` antes del efecto y `outcome` después.
- Los almacenes separados no garantizan atomicidad; debe existir reconciliación.
- Una falla de auditoría nunca convierte una denegación en permiso.
- Lecturas pueden responder únicamente cuando sea seguro, con señalización de error crítico.
- Mutaciones y operaciones Docker se bloquean si no se puede garantizar su registro.

El usuario decidió postergar su implementación para centrarse primero en Atlas Assistant, Memory Engine y proactividad.

### 10.4 Integridad y privacidad

**APROBADO:**

- La retención indefinida de eventos no justifica almacenar secretos, credenciales ni payloads sensibles innecesarios.
- La minimización de datos debe aplicarse desde la generación del evento.
- Las correcciones y actualizaciones se registran mediante nuevos eventos relacionados, sin modificar los originales.

**PARÁMETROS TÉCNICOS PENDIENTES:**

- Mecanismos concretos de integridad y verificación.
- Política de anonimización y tratamiento de datos personales compatible con la retención indefinida.
- Procedimiento para reconciliar efectos externos cuyo resultado no pueda determinarse inmediatamente.

---

## 11. Aprobaciones, notificaciones y Telegram

### 11.1 Principios de aprobación

**APROBADO:**

- Una solicitud de aprobación no autoriza ejecución.
- Las operaciones sensibles requieren aprobación humana específica.
- Las operaciones peligrosas o privilegiadas requieren aprobación explícita del propietario y autenticación reforzada.
- Una aprobación se vincula a una operación, recurso, alcance y versión exactos.
- Una aprobación no puede reutilizarse para una operación diferente.
- Cambiar argumentos invalida la aprobación anterior.
- La aprobación no concede permisos ni amplía un Grant.
- La identidad, autorización, Grant y aprobación se vuelven a validar antes del efecto.
- El solicitante no puede aprobar su propia solicitud.
- Un agente no puede aprobar su propia operación.

### 11.2 Operaciones que requieren aprobación

Como mínimo, requieren aprobación:

- `memory.forget`
- `memory.export`
- `permissions.grant`
- Cambios de políticas de seguridad.
- Ejecución privilegiada.
- Operaciones peligrosas sobre proyectos.
- Determinadas operaciones `project.manage`.

Todas las operaciones clasificadas como sensibles requieren aprobación humana específica.

Las operaciones relacionadas con decisiones de memoria están sujetas a una excepción de autoridad exclusiva.

Aunque una operación de memoria requiera aprobación humana, dicha aprobación deberá proceder directamente del propietario de Atlas.

Esta regla se aplica especialmente a:

- memory.approve
- memory.reject
- La aprobación de nuevas versiones de memoria.
- memory.forget

Ninguna delegación general o específica de aprobación podrá utilizarse para transferir estas facultades.

La existencia de un Grant que permita ejecutar una operación de memoria tampoco concede autoridad para aprobar decisiones de memoria.

Las operaciones peligrosas o privilegiadas requieren aprobación explícita del propietario y autenticación reforzada, aunque exista un Grant persistente para otras acciones.

### 11.3 Aprobaciones delegadas

**APROBADO:**

La autoridad de aprobación se distribuye según la clasificación y el riesgo de la operación.

- **Operaciones sensibles de riesgo limitado:** pueden ser aprobadas por el propietario o por una persona a quien el propietario haya delegado explícitamente esa autoridad.
- **Operaciones peligrosas o privilegiadas:** requieren aprobación exclusiva del propietario y autenticación reforzada.
- **Grants, permisos y políticas de seguridad:** su concesión, modificación, renovación y revocación corresponden exclusivamente al propietario.

La delegación debe estar limitada explícitamente por:

- Proyecto.
- Entorno.
- Tipo de operación.

Excepción obligatoria: decisiones de memoria

Las decisiones relacionadas con la memoria quedan excluidas de toda delegación y permanecen bajo autoridad exclusiva del propietario, conforme a las reglas establecidas en §§9.4 y 11.2.

Los aprobadores delegados, agentes, Watchers y servicios podrán presentar solicitudes y aportar información para facilitar la decisión, pero MUST NOT aprobar, rechazar ni autorizar estas decisiones en nombre del propietario.

Esta restricción no puede modificarse mediante delegación, Grant, configuración de agente ni política de una Skill.

Reglas obligatorias:

- Una persona delegada no puede subdelegar su autoridad.
- La delegación no concede permisos de ejecución.
- La autorización de ejecución continúa dependiendo de CAM y del Grant correspondiente.
- La persona delegada solo puede decidir sobre aprobaciones comprendidas dentro del alcance delegado.
- No se permite autoaprobación.
- La ausencia de una delegación explícita implica ausencia de autoridad de aprobación.

### 11.4 Ciclo de aprobación

Estados:

- `pending`
- `approved`
- `denied`
- `expired`
- `revoked`
- `consumed`

La aprobación debe vincularse a:

- Solicitante.
- Aprobador.
- Operación.
- Recurso.
- Proyecto.
- Entorno.
- Argumentos y digest.
- Clasificación/riesgo.
- Fecha de expiración.
- Decisión.

No se retienen locks mientras una tarea espera aprobación.

**APROBADO:**

- La aprobación debe identificar de forma inequívoca la versión de la operación y su digest criptográfico.
- Antes de ejecutar, debe comprobarse que la aprobación continúa vigente, no ha sido revocada ni consumida y que los argumentos siguen coincidiendo exactamente con los aprobados.
- Una aprobación consumida no puede reutilizarse.

### 11.5 Notificaciones aprobadas

| Severidad       | Política                 |
| --------------- | ------------------------ |
| `critical`      | Inmediata                |
| `important`     | Inmediata                |
| `informational` | Resumen diario           |
| `debug`         | No notificar normalmente |

Las notificaciones críticas e importantes deben priorizarse.

Las tareas críticas que no puedan ejecutarse deben notificarse al propietario, explicando el bloqueo y la necesidad de recursos o autorización cuando corresponda.

### 11.6 Telegram v1

**APROBADO:**

- Telegram es un canal exclusivamente saliente.
- Solo envía notificaciones.
- No acepta comandos de acción.
- No permite consultas bidireccionales.
- No sustituye autenticación ni autorización.
- No aprueba operaciones.
- Los fallos de Telegram no bloquean el registro de eventos.
- Los reintentos de entrega solo podrán realizarse cuando la repetición sea segura según las garantías verificables del mecanismo de envío. Cuando no exista garantía de idempotencia, deberá aplicarse la política de recuperación correspondiente, considerando la posibilidad de duplicados y los resultados inciertos.
- Los tokens no se almacenan en repositorios ni logs.
- Debe existir una allowlist de destinatarios.
- Los eventos clasificados como `sensitive` o `restricted` no se envían por defecto mediante Telegram.
- Las etiquetas descriptivas `user_private` y `system_restricted` se interpretan conforme al mapeo establecido en §4.7 y no constituyen clasificaciones independientes.
- No se envía contenido completo de memorias privadas.

La clasificación del evento no concede por sí misma autorización para divulgar su contenido.

La posibilidad de enviar información `public` o `internal` deberá respetar la allowlist de destinatarios y las restricciones de contenido aplicables. La clasificación, el destinatario y el propósito deben evaluarse conjuntamente.

La política concreta de contenido permitido por destinatario continúa sujeta a la decisión del propietario pendiente registrada en §20.2.

Las condiciones de idempotencia, reintento, deduplicación y tratamiento de resultados inciertos de las entregas se desarrollan en §11.7 y deben cumplir las garantías generales de §§13.3, 13.4 y 13.5.

La utilización de una clave de deduplicación no constituye por sí misma una garantía de idempotencia del proveedor externo ni permite afirmar que una notificación no se duplicará.

### 11.7 Decisiones pendientes de Telegram

**DECISIONES DEL PROPIETARIO PENDIENTES:**

1. Hora del resumen diario.
2. Zona horaria del resumen.
3. Destinatarios autorizados.
4. Contenido permitido para cada destinatario.
5. Política operativa ante entregas fallidas y fallos persistentes.

La clave de deduplicación de notificaciones permite identificar eventos o intentos de notificación relacionados y reducir el riesgo de envíos duplicados.

Su utilización no constituye por sí sola una garantía de idempotencia en el proveedor externo.

La garantía efectiva dependerá de las capacidades verificables del mecanismo de envío utilizado.

Cuando Telegram o el adaptador correspondiente no proporcionen una garantía verificable de idempotencia, Atlas deberá conservar el estado del intento, registrar los resultados conocidos y tratar los resultados ambiguos de acuerdo con una política explícita de recuperación.

No se deberá afirmar que una notificación fue enviada correctamente cuando el resultado del intento sea desconocido.

Los reintentos deberán preservar la relación con el evento original y utilizar mecanismos de deduplicación cuando estén disponibles.

**PROPUESTA TÉCNICA:**

- Conservar las notificaciones pendientes cuando Telegram no entregue.
- Realizar reintentos limitados, únicamente cuando la repetición sea segura y respete las garantías de idempotencia disponibles.
- Registrar el resultado de cada entrega.
- Utilizar claves de deduplicación para identificar y relacionar eventos e intentos de entrega, y reducir repeticiones internas cuando el mecanismo lo permita. Esta medida MUST NOT interpretarse como garantía de que el proveedor externo impedirá notificaciones duplicadas.
- Escalar fallos persistentes por un canal alternativo, únicamente si está autorizado.
- No descartar silenciosamente notificaciones críticas.

---

## 12. Skills externas

### 12.1 Modelo híbrido aprobado

Atlas gestionará:

1. Un catálogo de skills previamente aprobadas.
2. La posibilidad de recibir o descubrir paquetes externos.

Las skills externas deben pasar por:

- Registro de procedencia.
- Análisis de código.
- Análisis de dependencias.
- Declaración de capacidades y permisos.
- Revisión de permisos solicitados.
- Aprobación explícita.
- Instalación controlada.
- Aislamiento según riesgo.
- Auditoría.
- Actualizaciones controladas.
- Desactivación o eliminación.

Ninguna skill puede elevar sus propios permisos.

**APROBADO:**

- La recepción, descarga o descubrimiento de un paquete externo no autoriza su instalación ni ejecución.
- La instalación requiere completar el proceso de revisión y obtener aprobación explícita.
- La aprobación se limita al paquete, versión, digest, capacidades y permisos revisados.
- Una modificación del paquete o una nueva versión requiere una revisión y aprobación nuevas.
- Una skill desactivada o restaurada no puede reactivarse ni ejecutarse automáticamente.

### 12.2 Identidad y aislamiento

**APROBADO:**

- Los permisos de cada skill deben estar delimitados por proyecto y entorno, conforme al modelo de Grants de Atlas.
- Una skill no puede utilizar permisos de otra skill, aunque ambas formen parte de una misma tarea.
- La delegación de una tarea a una skill no amplía los permisos del actor ni del Grant correspondiente.
- CAM debe verificar la autorización de cada operación protegida realizada por la skill.

### Identidad de ejecución y autoridad de las Skills

Una Skill MUST NOT recibir automáticamente una identidad independiente ni un contexto de autorización propio por el hecho de estar instalada, aprobada o ser invocada.

Una Skill MUST ejecutarse bajo una identidad autenticada de tipo `agent` o `service`. Esa identidad conserva la responsabilidad de la operación y MUST ser evaluada por CAM.

La procedencia de la Skill se registra mediante `skill_provenance`, sin incorporarla como una identidad adicional al catálogo de `Identity.kind` ni como un nuevo tipo de actor.

La identidad del agente o servicio ejecutor, el origen, la delegación y la procedencia de la Skill son datos distintos y MUST conservarse por separado.

Una Skill MUST NOT heredar permisos de otra Skill, concederse permisos a sí misma o a otra Skill ni ampliar los permisos del agente o servicio bajo cuya identidad se ejecuta.

CAM MUST evaluar cada operación protegida teniendo en cuenta la identidad ejecutora, el contexto de procedencia de la Skill, el Grant, el proyecto, el entorno, el recurso y la operación solicitada.

La instalación, restauración, actualización o habilitación de una Skill MUST NOT autorizar automáticamente su ejecución.

Una nueva versión o un nuevo `skill_digest` requiere la revisión y aprobación correspondientes antes de su ejecución.

### 12.3 Propuesta técnica

Cada paquete puede identificarse mediante:

- Nombre.
- Versión.
- Digest.
- Procedencia.
- Dependencias.
- Manifiesto de capacidades.
- Recursos solicitados.
- Permisos solicitados.
- Clasificación de riesgo.

Los outputs de una skill se tratan como datos no confiables.

No debe exponerse por defecto:

- Socket del host.
- Daemon Docker.
- Secretos.
- Credenciales.
- Recursos de otros proyectos.

**APROBADO:**

- Los outputs de una skill son datos no confiables, independientemente de que la skill esté aprobada.
- Los outputs no pueden modificar instrucciones de sistema, políticas de seguridad, Grants ni permisos.
- Una skill no puede concederse capacidades adicionales mediante sus outputs, manifiestos o dependencias.
- Los accesos a recursos protegidos deben pasar por los mecanismos de autorización y aislamiento de Atlas.
- La declaración de permisos de una skill no sustituye la verificación de CAM.

**PROPUESTA TÉCNICA:**

- La instalación debe verificar que el digest del paquete coincide con el aprobado.
- El entorno de ejecución debe aplicar los límites declarados y autorizados, sin depender exclusivamente del manifiesto.
- Las dependencias deben quedar identificadas y vinculadas a la versión revisada de la skill.

**PARÁMETROS TÉCNICOS PENDIENTES:**

- Formato y firma del manifiesto.
- Herramientas de análisis.
- Criterios de riesgo.
- Niveles de aislamiento.
- Sandbox.
- Política de red.
- Proceso técnico de actualización y revocación.

El flujo de revisión y aprobación explícita ya está aprobado.

---

## 13. Interfaces, errores, idempotencia y timeouts

### 13.1 Interfaces contractuales

| Interfaz                               | Entrada / salida                                        | Invariante                               |
| -------------------------------------- | ------------------------------------------------------- | ---------------------------------------- |
| Cliente → AtlasCore                    | Solicitud autenticada → resultado y correlación         | Principal y actor verificables           |
| AtlasCore → CAM                        | Identidad, operación, scope, recurso y Grant → decisión | Fail-closed                              |
| AtlasCore → Approval Manager           | Digest, scope y riesgo → estado de aprobación           | Solicitante distinto del aprobador       |
| AtlasCore → Memory Gateway             | Lectura/propuesta/revisión/olvido → resultado           | Aislamiento y CAM                        |
| AtlasCore → Scheduler                  | Admitir/consultar/cancelar → estado de tarea            | Encolar no autoriza ni reserva           |
| Scheduler → CAM                        | Revalidar → decisión vigente                            | Verificar antes de iniciar               |
| Scheduler → RLM                        | Solicitar conjunto de locks → locks y fencing           | Sin locks parciales retenidos al esperar |
| RLM → Resource Registry                | Consultar recurso y política                            | Recurso desconocido bloqueado            |
| Watcher → Event Collector              | Evento observado → aceptación/rechazo                   | No ejecutar efectos protegidos           |
| Event Collector → Analysis Engine      | Eventos validados → análisis                            | Evidencia trazable                       |
| Analysis Engine → Notification Manager | Resultado y severidad → notificación                    | No ejecutar acciones                     |
| Broker → SecurityAudit                 | Intent/outcome → registro                               | Fallo audit bloquea mutaciones           |
| Broker → Runtime                       | Operación allowlisted y argumentos tipados              | No aceptar comandos arbitrarios          |
| Notification Manager → Telegram        | Notificación saliente                                   | Sin comandos entrantes                   |

### 13.2 Errores lógicos

Catálogo inicial:

- `IDENTITY_INVALID`
- `IDENTITY_INACTIVE`
- `AUTHENTICATION_FAILED`
- `AUTHORIZATION_DENIED`
- `PERMISSION_MISSING`
- `PROJECT_SCOPE_MISMATCH`
- `CLASSIFICATION_DENIED`
- `GRANT_EXPIRED`
- `GRANT_REVOKED`
- `APPROVAL_REQUIRED`
- `APPROVAL_EXPIRED`
- `APPROVAL_SCOPE_MISMATCH`
- `RESOURCE_UNKNOWN`
- `RESOURCE_BUSY`
- `LOCK_TIMEOUT`
- `DEADLOCK_VICTIM`
- `FENCING_REJECTED`
- `AUDIT_UNAVAILABLE`
- `DEPENDENCY_UNAVAILABLE`
- `DEADLINE_EXCEEDED`
- `IDEMPOTENCY_CONFLICT`
- `INVALID_REQUEST`
- `OUTCOME_UNKNOWN`
- `POLICY_UNAVAILABLE`
- `INTERNAL_ERROR`

La respuesta de error debe incluir un código estable, contexto de correlación y explicación segura, sin exponer secretos.

### 13.3 Idempotencia

La idempotencia es una capacidad declarada individualmente
por cada operación. Solo las operaciones que declaren
soporte de idempotencia requieren idempotency_key y
garantizan el comportamiento definido para dicha capacidad.

Las operaciones que no declaren este soporte no deben
considerarse seguras para repetición automática.

El soporte de idempotencia se declara individualmente por operación. No se presume que todas las operaciones del sistema sean idempotentes.

Cuando una operación declare soporte de idempotencia:

- La solicitud deberá proporcionar un idempotency_key.
- El sistema deberá garantizar el comportamiento idempotente definido para esa operación.
- La reutilización de una clave deberá respetar el alcance y las reglas de retención establecidos por dicha operación.
- Las solicitudes repetidas con la misma clave no deberán producir efectos adicionales fuera de las garantías declaradas.

Cuando una operación no declare soporte de idempotencia:

- No se exigirá idempotency_key.
- No se presumirá que repetir la solicitud sea seguro.
- No se permitirá el reintento automático basándose únicamente en la existencia de una clave.
- Los reintentos deberán seguir las condiciones específicas de seguridad y recuperación de esa operación.

La política general de reintentos no podrá asumir idempotencia donde no exista una declaración explícita y verificable.

**PROPUESTA TÉCNICA:**

- Misma idempotency key y misma carga: devolver el resultado original.
- Misma key con operación o argumentos diferentes: conflicto.
- No repetir efectos externos sin comprobar el resultado anterior.
- Mantener un ledger de idempotencia.
- Los reintentos deben respetar el deadline original.

### 13.4 Reintentos

**APROBADO COMO INVARIANTE:**

- Reintentar únicamente operaciones cuya repetición sea segura.
- No reintentar una denegación de autorización.
- No reintentar una aprobación pendiente.
- No reintentar ciegamente un rechazo de fencing.
- No repetir una operación cuyo resultado sea incierto sin reconciliar primero.
- No usar reintentos para eludir revocaciones.

**BASELINE TÉCNICO APROBADO PARA DESARROLLO:**

- Backoff exponencial con _full jitter_.
- Esperas máximas: 1, 2, 4, 8, 16 y 30 segundos; posteriormente, 30 segundos.
- Máximo de 8 reintentos automáticos por operación recuperable.
- Hasta 3 recuperaciones automáticas en los mecanismos de recuperación de deadlocks.
- Detector de deadlocks cada 5 segundos.
- Escalamiento de deadlock a los 30 segundos.
- Tiempo máximo de espera por lock: 300 segundos.

Los reintentos deben respetar siempre la autorización vigente, el deadline original, los límites de recursos y las condiciones de idempotencia.

**PARÁMETROS TÉCNICOS TODAVÍA PENDIENTES:**

- Timeouts específicos por interfaz.
- Retención del ledger de idempotencia.
- Límites de payload.
- Formato definitivo de reason codes.
- Tratamiento técnico de operaciones no idempotentes cuyo resultado externo sea incierto.

### 13.5 Resultados inciertos

Si una operación pudo producir un efecto externo, pero Atlas no pudo confirmar el resultado:

1. Marcar `outcome_unknown`.
2. Preservar la correlación y evidencia.
3. Consultar el estado externo.
4. Reconciliar el efecto.
5. No repetir ciegamente.
6. Resolver el resultado antes de liberar recursos o iniciar dependencias incompatibles.

La reconciliación debe utilizar el identificador de operación o correlación y consultar, cuando sea posible, la fuente externa que produjo el efecto.

Mientras el resultado permanezca incierto:

- No repetir la operación.
- No iniciar tareas dependientes que requieran conocer el resultado.
- No liberar locks ni reservas mientras exista riesgo de que el proceso anterior siga afectando el recurso.
- Registrar la incertidumbre y mantener el estado protegido hasta su resolución.

Si no existe un mecanismo confiable para verificar el resultado, la operación debe permanecer en estado de recuperación y requerir intervención o resolución autorizada.

### 13.6 Cancelación

La cancelación no equivale a terminación.

Los locks y recursos solo se liberan después de verificar que los procesos asociados terminaron o que el mecanismo de fencing impide que sigan afectando el recurso.

Si no se puede confirmar la terminación, mantener protección y escalar recuperación.

**BASELINE TÉCNICO APROBADO PARA DESARROLLO:**

- Solicitar cancelación cooperativa y esperar hasta 30 segundos.
- Si no termina, conceder un período adicional de hasta 15 segundos para verificar la terminación.
- Antes de liberar locks, leases o reservas, verificar obligatoriamente que los procesos asociados terminaron o que existe un mecanismo de fencing efectivo que impide nuevas escrituras.
- Si no puede verificarse la terminación ni garantizarse el aislamiento mediante fencing, mantener la protección del recurso y escalar la recuperación.

## Estos valores son un baseline inicial de desarrollo, no parámetros definitivos de producción.

## 14. Ciclos de vida y transiciones

### 14.1 Identity

- `active ↔ suspended`
- `active|suspended → revoked`
- `revoked` es terminal.
- Una identidad revocada es terminal y no puede reactivarse. Cualquier nueva identidad requiere un proceso independiente de creación, autenticación y autorización.

La suspensión o revocación de una identidad afecta inmediatamente las nuevas operaciones y las tareas activas que dependan de ella.

- `suspended`: bloquear nuevas operaciones. Detener cooperativamente las tareas dependientes. Si la interrupción inmediata compromete la integridad, permitir alcanzar un punto seguro de consistencia, sin iniciar operaciones nuevas ni ampliar el alcance.
- `revoked`: bloquear nuevas operaciones y detener de forma segura las tareas dependientes, aplicando el mismo criterio de punto seguro.
- Las tareas independientes pueden continuar únicamente si disponen de autorización propia y vigente.
- Conservar los resultados parciales y registrar las operaciones completadas, detenidas y pendientes.
- Una identidad revocada no puede reactivarse. Cualquier nueva identidad requiere un proceso independiente.

### 14.2 Grant

- `draft → active`
- `active → suspended|revoked|expired|exhausted`
- `suspended → active` solo mediante decisión autorizada del propietario, si sigue siendo válido.
- `revoked` es terminal.
- `expired` no admite nuevas operaciones.
- `indefinite` no requiere fecha de expiración.

La revocación o expiración afecta inmediatamente las nuevas operaciones y tareas dependientes.

`exhausted` indica que el presupuesto disponible del Grant se ha consumido y que no puede admitirse nuevo consumo que exceda sus límites.

- No equivale a `revoked` ni a `expired`.
- No permite iniciar operaciones que requieran presupuesto adicional.
- Solo puede volver a `active` mediante una ampliación autorizada del presupuesto, validada por CAM.
- La ampliación no concede permisos nuevos ni aumenta automáticamente los límites de concurrencia.
- El historial de consumo y las operaciones anteriores se conserva.

### 14.3 Task

Estados operativos:

- `submitted`
- `queued`
- `awaiting_approval`
- `blocked_authorization`
- `blocked_dependency`
- `running`
- `completed`
- `partially_completed`
- `skipped`
- `failed`
- `cancelled`
- `outcome_unknown`

Una tarea pasa de `queued` a `running` únicamente después de revalidar CAM, Grant, entorno, presupuesto, concurrencia y locks.

La ejecución parcial conserva resultados y dependencias. Nunca debe presentarse como ejecución completa.

Los estados representan condiciones diferentes:

- `blocked_authorization`: la tarea no puede continuar por falta, expiración, suspensión o revocación de autorización.
- `blocked_dependency`: una dependencia necesaria no está disponible o no ha alcanzado un estado válido.
- `partially_completed`: una parte de la tarea terminó correctamente, pero otra parte no pudo completarse.
- `outcome_unknown`: existe incertidumbre sobre el efecto de una operación y se requiere reconciliación antes de repetirla o continuar dependencias incompatibles.

Una tarea parcialmente completada no debe considerarse automáticamente fallida ni completada. Su resultado debe conservar el detalle de las operaciones completadas, bloqueadas, omitidas y pendientes.

### 14.4 Approval

- `pending → approved|denied|expired|revoked`
- `approved → consumed|revoked`

consumed, denied, expired y revoked son estados terminales
y no admiten transiciones posteriores.

Una aprobación revocada no puede reutilizarse.
Revocar una aprobación impide ejecutar la operación
si todavía no fue consumida.
Una aprobación en estado `approved` solo puede utilizarse para la operación, el recurso, el proyecto, el entorno, los argumentos y la versión exactos que fueron revisados.

Antes de ejecutar:

- Verificar que la aprobación no haya expirado, sido revocada o consumida.
- Comprobar que el digest de la operación coincide.
- Revalidar identidad, autenticación, Grant y autorización mediante CAM.
- Consumir la aprobación de forma que no pueda reutilizarse.

Una aprobación no concede permisos ni sustituye la autorización de CAM.

### 14.5 Memory

- `pending_review → approved|rejected`
- `approved → superseded|forgotten`
- Una modificación posterior crea una nueva versión en `pending_review`.
- `rejected`, `superseded` y `forgotten` no representan conocimiento aprobado vigente.
- `forgotten` requiere aprobación y verificación del proceso de eliminación en los almacenes y sistemas derivados correspondientes.
- Una memoria olvidada no debe reaparecer por reindexación o restauración.

### 14.6 Lock

- `requested → waiting → held → released`
- Alternativas: `expired`, `recovery_required`, `failed`.
- Lease expirado no significa terminación.
- Reconciliar procesos y fencing antes de reutilizar el recurso.

Un lock en estado `expired` no puede considerarse `released` automáticamente. Debe pasar por reconciliación para verificar la terminación del proceso anterior o garantizar mediante fencing efectivo que no pueda continuar afectando el recurso.

`recovery_required` mantiene el recurso protegido hasta completar la reconciliación.

### 14.7 Resource

- `pending_review`
- `active`
- `suspended`
- `retired`

Las transiciones deben conservar la protección mientras existan procesos asociados.

### 14.8 Skill

Estados:

- `discovered`
- `under_review`
- `approved`
- `rejected`
- `installed`
- `active`
- `disabled`
- `revoked`
- `removed`

Reglas:

- `discovered` no autoriza instalación ni ejecución.
- `approved` se refiere exclusivamente al paquete, versión, digest, capacidades y permisos revisados.
- Un digest o versión diferente requiere nueva revisión y aprobación.
- `installed` no implica que la skill esté autorizada para ejecutarse.
- `active` requiere instalación válida, autorización vigente y activación deliberada.
- `disabled`, `revoked` y `removed` no pueden ejecutar operaciones.
- Una skill restaurada queda inactiva y requiere verificar integridad, versión y autorización antes de una nueva activación.
- Los resultados de una skill se consideran datos no confiables y nunca pueden modificar instrucciones, políticas, Grants o permisos.

### 14.9 Restore

- `normal`
- `recovery_required`
- `verifying`
- `ready_for_owner_activation`
- `active`

No ejecutar proyectos ni skills antes de verificar integridad, permisos y activación deliberada.

`ready_for_owner_activation` indica que las verificaciones técnicas finalizaron satisfactoriamente, pero no autoriza la ejecución ni la reactivación automática de proyectos, servicios o skills.

La transición a `active` requiere una decisión deliberada del propietario y la validación de los permisos y condiciones vigentes mediante CAM.

La restauración no recupera automáticamente autorizaciones, Grants, aprobaciones o permisos que hayan expirado, sido revocados o dejado de ser válidos.

---

## 15. Criterios de aceptación

Los siguientes criterios son requisitos de diseño. No se consideran pruebas ejecutadas.

1. Passkey, TOTP y códigos de recuperación funcionan según la política configurada.
2. Identidades suspendidas o revocadas no pueden iniciar nuevas operaciones protegidas.
3. Principal y actor discordantes producen denegación.
4. CAM ausente, política desconocida o error de autorización bloquean operaciones protegidas.
5. Las operaciones cross-project y cross-environment se deniegan sin Grant independiente.
6. Solo el propietario administra Grants.
7. Autoridad y delegación de aprobaciones
   El sistema permite delegar aprobaciones únicamente dentro de los límites expresamente autorizados.
   Las decisiones relacionadas con la memoria permanecen bajo autoridad exclusiva del propietario de Atlas, incluyendo la aprobación o rechazo de propuestas, la aprobación de nuevas versiones y la autorización de memory.forget.
   Las pruebas deberán verificar que ningún agente, servicio, Watcher, Skill o aprobador delegado pueda realizar estas decisiones en nombre del propietario.
8. Grants temporales requieren expiración.
9. Grants indefinidos requieren selección explícita del propietario.
10. Renovaciones respetan el aviso predeterminado de 24 horas y el silencio no amplía la vigencia.
11. La ampliación automática de recursos se limita a una vez por tarea, utiliza únicamente la siguiente configuración disponible que sea suficiente y respeta la capacidad disponible y los límites globales de recursos. No puede ampliar permisos ni concurrencia ni consumir recursos reservados o protegidos de otros proyectos.
12. La segunda ampliación requiere autorización.
13. Presupuestos del mismo Grant se comparten entre tareas.
14. Los locks, leases y reservas no se liberan hasta verificar la terminación de los procesos asociados o garantizar mediante fencing efectivo que no puedan seguir afectando el recurso. La expiración de un lease por sí sola no demuestra terminación.
15. La ejecución parcial conserva resultados y no elude autorización.
16. La promoción de prioridad respeta 24 h, 8 h y 2 h, con promoción gradual.
17. Los cambios manuales reinician el envejecimiento y las promociones automáticas no.
18. Los tres límites de concurrencia son independientes y obligatorios.
19. Las tareas en cola no reservan recursos ni cupos de ejecución.
20. Resource Registry bloquea recursos desconocidos o no clasificados.
21. Solo el propietario administra políticas y recursos.
22. RLM prueba jerarquía, modos shared/exclusive y políticas mandatory/advisory.
23. RLM prueba orden global y detección de ciclos.
24. La víctima de deadlock se selecciona según los criterios aprobados.
25. La víctima conserva resultados parciales y vuelve a cola únicamente si sigue autorizada.
26. Fencing impide que un propietario obsoleto afecte el recurso.
27. Recuperación tras reinicio verifica procesos y locks persistidos.
28. RLM caído no permite rutas alternativas para operaciones protegidas.
29. Memory Engine mantiene aislamiento entre proyectos.
30. Propuestas de memoria no entran al índice aprobado.
31. Memorias aprobadas requieren revisión para cambios posteriores.
32. `memory.forget` verifica todos los almacenes pertinentes.
33. Los eventos son inmutables y tienen retención indefinida.
34. Las incidencias se separan de los eventos.
35. SecurityAudit bloquea mutaciones cuando no puede garantizar registro.
36. Una aprobación queda vinculada a digest y alcance exactos.
37. Una modificación invalida la aprobación anterior.
38. Telegram no acepta comandos de acción.
39. Las notificaciones no autorizan operaciones.
40. Las skills externas pasan por revisión y aprobación antes de instalarse.
41. Las skills no pueden elevar sus permisos.
42. Una skill restaurada queda inactiva.
43. Idempotencia por operación
    El sistema exige idempotency_key únicamente en las operaciones que declaran explícitamente soporte de idempotencia.
    Las operaciones que no declaran dicho soporte pueden ejecutarse sin este campo y no se consideran seguras para reintentos automáticos por defecto.
    Las pruebas deberán verificar ambos escenarios: operaciones con soporte de idempotencia y operaciones sin dicho soporte.
44. Un resultado incierto se reconcilia consultando la fuente externa y preservando la correlación y evidencia antes de repetir la operación o iniciar tareas dependientes incompatibles. Si no puede verificarse, permanece en recuperación y requiere resolución autorizada.
45. La cancelación solicita terminación cooperativa durante un máximo de 30 segundos y permite hasta 15 segundos adicionales para verificarla. No libera locks, leases ni reservas antes de verificar la terminación o garantizar un fencing efectivo.
46. La suspensión o revocación de una identidad bloquea nuevas operaciones y afecta las tareas dependientes. Las tareas independientes solo continúan con autorización propia y vigente.

47. Una aprobación solo puede utilizarse para la operación, recurso, proyecto, entorno, argumentos y versión exactos que fueron revisados. Antes de ejecutar se revalidan CAM, identidad, Grant y estado de la aprobación.

48. Las memorias `pending_review` no se utilizan como conocimiento aprobado. Las memorias olvidadas no reaparecen mediante reindexación o restauración de almacenes.

49. La recepción, descarga o descubrimiento de una skill externa no autoriza su instalación ni ejecución. La aprobación corresponde al paquete, versión, digest, capacidades y permisos revisados.

50. Los resultados de skills y otras fuentes externas no pueden modificar instrucciones del sistema, políticas, Grants o permisos, ni elevar las capacidades del actor.

51. La expiración o revocación de un Grant bloquea nuevas operaciones dependientes y provoca la reevaluación y detención segura de las tareas afectadas.
52. Un Grant en estado `draft` no puede autorizar operaciones. La transición a `active` requiere completar la autorización del propietario y las verificaciones de activación correspondientes.
53. Las operaciones que involucren Skills conservan la identidad autenticada del agente o servicio ejecutor y registran la procedencia de cada Skill participante mediante `skill_id`, `skill_version` y `skill_digest`. La Skill no obtiene identidad ni permisos independientes por su instalación o ejecución.
54. Los eventos sin `deduplication_key` son válidos. La presencia de esta clave no se interpreta como garantía de idempotencia ni como protección automática contra duplicados externos.
55. Las aprobaciones que requieren autenticación reforzada conservan evidencia verificable del método, fecha y referencia de autenticación, sin almacenar secretos ni credenciales reutilizables.
56. El campo `owner` de un recurso identifica la autoridad de gobernanza correspondiente y no se confunde con la custodia técnica. La custodia técnica no concede permisos de administración o modificación del Resource Registry.

---

# 16. Decisiones del propietario

Esta sección consolida las decisiones de diseño que requieren autorización explícita del propietario de Atlas.

Las decisiones marcadas como **APROBADO** representan políticas aceptadas para el diseño del sistema. Su aprobación no significa que estén implementadas ni que exista todavía un mecanismo técnico que garantice su cumplimiento.

## 16.1. Política de aprobaciones delegadas

**Estado: APROBADO**

Atlas podrá admitir aprobadores delegados para determinadas operaciones sensibles, bajo las siguientes condiciones:

1. Las operaciones sensibles de riesgo limitado podrán ser aprobadas por el propietario o por un aprobador delegado expresamente autorizado.
2. Las operaciones peligrosas o privilegiadas requerirán aprobación exclusiva del propietario.
3. La administración de Grants, permisos y políticas de seguridad será facultad exclusiva del propietario.
4. Todo aprobador delegado tendrá una autorización específica y limitada por:
   - Proyecto.
   - Entorno.
   - Tipo de operación.
5. Un aprobador delegado no podrá delegar sus facultades a otra identidad.
6. La delegación no concederá permisos adicionales para ejecutar operaciones; únicamente permitirá decidir sobre las aprobaciones expresamente asignadas.
7. Ningún agente o skill podrá aprobar una solicitud propia ni concederse facultades de aprobación.

La autorización del aprobador deberá verificarse en el momento de decidir la solicitud. Una delegación inexistente, expirada, revocada o fuera de alcance no será válida.

La autorización delegada deberá mantener una vigencia verificable y un alcance definido. Cualquier modificación, reducción, suspensión, revocación o expiración de dicha autorización deberá aplicarse a las nuevas decisiones de aprobación y reevaluar las solicitudes pendientes que dependan de ella.

## 16.2. Suspensión y revocación de identidades

**Estado: APROBADO**

Cuando una identidad cambie de estado, Atlas deberá aplicar las siguientes reglas:

### Identidad `suspended`

1. Bloquear inmediatamente las nuevas operaciones de la identidad.
2. Identificar las tareas activas que dependan de esa identidad.
3. Iniciar la detención cooperativa de las operaciones afectadas.
4. Si una interrupción inmediata compromete la integridad de los datos o recursos, permitir que la operación alcance un punto seguro de consistencia.
5. Durante ese intervalo no se podrán iniciar nuevas operaciones ni ampliar el alcance de las operaciones existentes.
6. Conservar los resultados parciales y el estado de ejecución.
7. Las tareas independientes, ejecutadas por otras identidades, podrán continuar si conservan sus propias autorizaciones.
8. Registrar la suspensión, las tareas afectadas y sus resultados.

La suspensión es temporal. El propietario podrá reactivar la identidad mediante el procedimiento autorizado correspondiente.

### Identidad `revoked`

1. Bloquear nuevas operaciones.
2. Impedir que las operaciones dependientes continúen utilizando la identidad revocada.
3. Detener de forma segura las operaciones activas, permitiendo alcanzar un punto seguro de consistencia cuando sea necesario para proteger la integridad.
4. Conservar y registrar los resultados parciales.
5. No permitir la reactivación de la misma identidad como si su revocación no hubiera ocurrido.

La revocación representa la retirada definitiva de esa identidad. Si en el futuro se necesita una identidad equivalente, deberá seguirse un proceso de creación y autorización independiente.

### Regla de integridad

El punto seguro de consistencia no constituye una excepción para continuar trabajando. Es únicamente una transición controlada para dejar los recursos en un estado consistente.

No autoriza nuevas operaciones, ampliaciones de alcance ni elusión de la suspensión o revocación.

## 16.3. Modificación y revocación de Grants durante tareas activas

**Estado: APROBADO**

Los cambios en un Grant deberán aplicarse de acuerdo con su naturaleza y su impacto sobre las operaciones activas.

### Revocación de un Grant

1. Bloquear inmediatamente nuevas operaciones que dependan del Grant.
2. Identificar las tareas activas que utilizan ese Grant.
3. Detener de forma segura las operaciones afectadas.
4. Permitir alcanzar un punto seguro de consistencia cuando una interrupción inmediata comprometa la integridad.
5. Conservar los resultados parciales y registrar las tareas afectadas.

### Reducción de permisos

1. Aplicar inmediatamente el nuevo alcance a las operaciones nuevas.
2. Reevaluar las tareas activas que dependan del Grant.
3. Detener de forma segura las operaciones que excedan el nuevo alcance.
4. No permitir que una autorización anterior se utilice para eludir la reducción de permisos.

### Reducción de presupuesto

1. Aplicar el nuevo límite a los consumos posteriores.
2. Impedir nuevos consumos que excedan el presupuesto actualizado.
3. No cancelar automáticamente el trabajo ya realizado.
4. Si la tarea no puede continuar dentro del presupuesto disponible, deberá quedar bloqueada o detenerse de forma segura.

### Ampliación de permisos o presupuesto

1. Las ampliaciones no modificarán retroactivamente las autorizaciones de las tareas activas.
2. Las nuevas operaciones podrán utilizar el alcance actualizado después de la validación correspondiente del CAM.
3. Ninguna ampliación podrá eludir las reglas de aprobación, concurrencia, límites de recursos o aislamiento.

### Registro de cambios

Cada modificación deberá registrar, como mínimo:

- Identidad que realizó el cambio.
- Grant afectado.
- Tipo de modificación.
- Alcance anterior y nuevo.
- Fecha y hora.
- Tareas afectadas.
- Resultado de las acciones tomadas.

## 16.4. Cambios de configuración y políticas durante la ejecución

**Estado: APROBADO**

Los cambios de configuración y políticas deberán considerar su impacto sobre las tareas activas y las operaciones futuras.

La modificación, aprobación, suspensión o sustitución de políticas de seguridad corresponde exclusivamente al propietario. Ningún agente, servicio, watcher o skill podrá modificar estas políticas ni ampliar sus propias facultades mediante cambios de configuración.

### Políticas más restrictivas

1. Aplicar inmediatamente las nuevas restricciones a las operaciones nuevas.
2. Reevaluar las tareas activas afectadas.
3. Detener de forma segura las operaciones que ya no cumplan las nuevas políticas.
4. Permitir alcanzar un punto seguro de consistencia cuando sea necesario para proteger la integridad.

### Políticas menos restrictivas

1. Aplicar los cambios únicamente a operaciones nuevas.
2. Exigir la validación correspondiente antes de utilizar el nuevo alcance.
3. No ampliar retroactivamente las autorizaciones de tareas activas.
4. Mantener las condiciones de autorización bajo las cuales fueron iniciadas las tareas existentes, salvo que otra política más restrictiva obligue a reevaluarlas.

### Cambios incompatibles con tareas activas

1. Identificar las tareas y recursos afectados.
2. Determinar si pueden continuar de forma segura bajo la nueva configuración.
3. Si existe incompatibilidad, detenerlas de forma controlada.
4. Permitir alcanzar un punto seguro de consistencia cuando sea necesario.
5. Conservar los resultados parciales y registrar el motivo de la interrupción.

### Cambios que afectan recursos compartidos

1. Coordinar la transición mediante el Resource Lock Manager (RLM).
2. Respetar la jerarquía y modalidad de los locks existentes.
3. No liberar locks mientras existan procesos que utilicen los recursos protegidos.
4. Si no puede verificarse que el recurso está libre, mantener la protección y realizar la reconciliación correspondiente.

### Cambios sin impacto de seguridad

Los cambios que no alteren permisos, aislamiento, integridad o condiciones de seguridad podrán aplicarse según su ámbito y versión, evitando interrupciones innecesarias de tareas activas.

### Registro de cambios

Registrar como mínimo:

- Propietario que autorizó o realizó el cambio.
- Política o configuración afectada.
- Versión anterior.
- Nueva versión.
- Fecha y hora.
- Ámbito del cambio.
- Tareas y recursos afectados.
- Resultado de la transición.

## 16.5. Reglas comunes de aplicación

**Estado: APROBADO**

Las cuatro políticas anteriores comparten las siguientes reglas:

1. La seguridad y la integridad de los recursos prevalecen sobre la continuidad de una tarea.
2. Un punto seguro de consistencia permite finalizar una transición controlada, pero no autoriza trabajo adicional.
3. Ninguna tarea conserva una autorización que haya sido revocada o que haya dejado de ser válida.
4. Los cambios de permisos y políticas no podrán utilizarse para ampliar automáticamente el alcance de tareas existentes.
5. La detención de una tarea deberá preservar, cuando sea posible, los resultados parciales y el estado necesario para su recuperación.
6. Una tarea parcialmente ejecutada nunca podrá presentarse como completada.
7. Los recursos compartidos permanecerán protegidos mientras exista incertidumbre sobre su utilización.
8. Las operaciones posteriores a un cambio deberán pasar nuevamente por las validaciones de autorización que correspondan.
9. Todas las transiciones y decisiones deberán generar los registros correspondientes de acuerdo con el diseño de eventos y auditoría de Atlas. La ausencia de un mecanismo de auditoría implementado no podrá interpretarse como cumplimiento del requisito. SecurityAudit mantiene su estado de diseño aprobado e implementación postergada.

## 16.6. Estado consolidado de decisiones

| Decisión                               | Estado   |
| -------------------------------------- | -------- |
| Aprobaciones delegadas                 | APROBADO |
| Suspensión y revocación de identidades | APROBADO |
| Modificación y revocación de Grants    | APROBADO |
| Cambios de configuración y políticas   | APROBADO |

Las cuatro decisiones de esta sección han sido aprobadas por el propietario durante la revisión del diseño.

Su implementación requiere contratos técnicos, mecanismos de autorización, coordinación con Scheduler y RLM, procedimientos de detención segura y registro de auditoría.

## **Aprobación de diseño no equivale a implementación.**

## 17. Parámetros técnicos pendientes

Estos puntos no reabren decisiones de política ya aprobadas.

### 17.1 Scheduler y recursos

- Configuración de los valores numéricos de concurrencia global, proyecto-entorno y Grant, pendiente de decisión y configuración explícita del propietario.
- Implementación técnica de la persistencia, contabilización, reserva y liberación de cupos de concurrencia.
- Unidades y ventanas de presupuesto.
- Implementación de la contabilidad acumulada, concurrente y de reservas.
- Umbral de espera importante.
- Persistencia y recuperación de cola.
- Mecanismo técnico de reconciliación de recursos tras una caída.

El modelo de presupuesto compartido por Grant, los tres límites independientes de concurrencia y las reglas de reserva y liberación ya están aprobados.

La definición de los valores numéricos de concurrencia corresponde al propietario y permanece pendiente de su configuración explícita.

La persistencia, contabilización, coordinación y recuperación técnica de estos límites podrán especificarse durante la implementación, respetando los tres ámbitos independientes y sin introducir valores predeterminados no aprobados.

### 17.2 RLM

- Tolerancias de reloj.
- Orden canónico exacto de adquisición de recursos.
- Implementación técnica de fencing y mecanismos de enforcement.
- Adaptadores para recursos externos.
- Mecanismo de persistencia y reconciliación.
- Política técnica de locks advisory ante fallos.

**BASELINE TÉCNICO APROBADO PARA DESARROLLO:**

- Lease: 30 segundos.
- Heartbeat: 10 segundos.
- Tolerancia: 3 heartbeats fallidos.
- Margen de renovación: 5 segundos.
- Timeout de adquisición de lock: 300 segundos.
- Detector de deadlocks: cada 5 segundos.
- Escalamiento de deadlock: a los 30 segundos.
- Recuperaciones automáticas de deadlock: máximo 3.
- Backoff exponencial con full jitter: esperas máximas de 1, 2, 4, 8, 16 y 30 segundos; posteriormente, 30 segundos.
- Máximo de 8 reintentos automáticos por operación recuperable.

**REGLAS DE DESEMPATE YA APROBADAS:**

La selección de tareas respeta el siguiente orden:

1. Mayor prioridad efectiva.
2. Mayor antigüedad dentro de la prioridad.
3. Fecha y hora de entrada a la cola más antigua.
4. `task_id` lexicográfico ascendente.

Estos valores y reglas constituyen un baseline inicial de desarrollo, no parámetros definitivos de producción.

### 17.3 Memoria

El aislamiento entre proyectos, el control de acceso mediante CAM y el proceso de incorporación mediante revisión humana son decisiones de diseño aprobadas. Los puntos pendientes corresponden a su implementación técnica y validación.

- Tipos de memoria.
- Almacenes e índices.
- Cifrado.
- Resolución de conflictos.
- Estrategia de búsqueda.
- Importación histórica.
- Verificación de borrado en respaldos e índices.
- Permisos específicos para proponer cada clase de memoria.
- Catálogo definitivo de clasificación de memoria y reglas de propagación de clasificación entre versiones.
- Formato técnico de los scopes e identificadores.
- Evidencia técnica de aprobación directa del propietario.
- Plazos de retención y propagación de supresión en respaldos, réplicas e índices.
- Implementación y validación de autorización granular por recurso en CAM.
- Estrategia de reconciliación de supresión durante restauraciones e importaciones.
- Trust Anchor externo: capacidad opcional aprobada y postergada hasta la etapa final de Atlas; su proveedor, custodia, autenticación y pruebas anti-rollback quedan para esa etapa. El perfil local no demuestra que un backup restaurado sea el último estado confirmado.

### 17.4 Eventos y auditoría

- Catálogo completo de tipos de eventos.
- Definiciones operativas y reglas de asignación de severidades.
- Reglas de aplicación, compatibilidad y tratamiento de las clasificaciones definidas en §4.7.
- Acceso y exportación.
- Integridad criptográfica.
- Privacidad y anonimización compatible con retención indefinida.
- Límites de almacenamiento y alertas.
- Reconciliación de efectos externos.

Los valores admitidos para `Event.classification` ya están definidos en §4.7. La especificación pendiente corresponde a sus reglas completas de aplicación, asignación y tratamiento en los distintos componentes y canales.

La inmutabilidad, la retención indefinida y la separación entre eventos e incidencias son decisiones aprobadas. SecurityAudit mantiene su diseño aprobado e implementación postergada. Los puntos pendientes corresponden a mecanismos técnicos, controles de privacidad, integridad y operación.

### 17.5 Skills

El modelo híbrido de catálogo aprobado y recepción o descubrimiento de paquetes externos, así como la revisión y aprobación obligatorias antes de instalar, son decisiones aprobadas. Los puntos pendientes corresponden a los formatos, herramientas y mecanismos técnicos necesarios para aplicarlas.

- Formato del manifiesto.
- Firma y procedencia.
- Herramientas de análisis.
- Criterios de riesgo.
- Sandbox.
- Aislamiento.
- Política de red.
- Procedimiento de actualización y revocación.

### 17.6 Interfaces

- Timeouts específicos por interfaz.
- Límites de payload.
- Retención del ledger de idempotencia.
- Formato de reason codes.
- Política y mecanismo de reconciliación por tipo de operación.

Los reintentos deben respetar el baseline aprobado en 13.4 y 17.2: únicamente operaciones recuperables y seguras, backoff exponencial con full jitter y máximo de 8 reintentos automáticos por operación recuperable.

## La configuración de timeouts específicos por interfaz deberá respetar los deadlines originales y no podrá eludir los límites de cancelación, recuperación o autorización.

## 18. Estado de implementación

| Componente / capacidad | Estado conocido                                                   |
| ---------------------- | ----------------------------------------------------------------- |
| Broker                 | Implementación histórica reportada; verificar estado actual       |
| Registry v2            | Implementación histórica reportada; no modificar sin autorización |
| Atlas Assistant        | Diseño / foco de trabajo                                          |
| CAM                    | Diseño; no verificado como implementado                           |
| Authentication         | Requisitos definidos; implementación posterior                    |
| Grants                 | Diseño contractual                                                |
| Scheduler              | Diseño contractual                                                |
| Resource Registry      | Diseño contractual                                                |
| RLM                    | Diseño aprobado; implementación no acreditada                     |
| Memory Engine          | Diseño contractual en desarrollo; implementación no acreditada.   |
| Cognee                 | Candidato; no instalar todavía                                    |
| Event Collector        | Diseño                                                            |
| Analysis Engine        | Diseño                                                            |
| SecurityAudit          | Diseño aprobado; implementación postergada                        |
| Approval Manager       | Diseño                                                            |
| Notification Manager   | Diseño                                                            |
| Telegram               | Política v1 definida; integración no implementada/verificada      |
| Watchers               | Diseño; no verificados como implementados                         |
| Skill Manager          | Modelo de seguridad aprobado; implementación no acreditada        |

No se debe afirmar que un componente está operativo sin evidencia actual.

---

## 19. Control de cambios del contrato

1. Las decisiones aprobadas se conservan como baseline.
2. Una modificación de una decisión aprobada requiere aprobación explícita del propietario.
3. Una propuesta técnica nueva debe identificarse como tal.
4. Los cambios de esquema deben versionarse.
5. Una modificación de alcance de autorización no se considera una simple actualización técnica.
6. Las decisiones pendientes no se resuelven por inferencia.
7. Cada versión debe conservar un registro de cambios que identifique, como mínimo, la versión anterior y nueva, los apartados modificados, la naturaleza del cambio, su justificación, el autor y la aprobación correspondiente cuando aplique.
8. El contrato aprobado no implica autorización de implementación.
9. La implementación se planifica por fases y requiere autorización independiente.
10. Ninguna fase puede modificar Broker, Registry v2, producción o infraestructura protegida sin autorización explícita.
11. La armonización documental de Memory Engine debe reflejar las decisiones confirmadas por el propietario, sin convertir parámetros técnicos pendientes en decisiones aprobadas ni declarar implementadas capacidades aún no verificadas.

---

## 20. Estado final de esta revisión

Esta revisión consolida las decisiones aprobadas durante el diseño de Atlas v1 y corrige las contradicciones identificadas en el borrador anterior.

Esta revisión cuenta con la aprobación expresa del propietario respecto al baseline arquitectónico de Atlas v1, conforme a §20.4.

La autorización de implementación se concede de forma independiente y limitada a la Fase 1, conforme a §20.5.

La aprobación del baseline y la autorización de implementación no certifican que los componentes estén implementados, integrados o verificados.

### 20.1. Decisiones aprobadas

Las siguientes decisiones ya fueron aprobadas y se encuentran consolidadas en la sección 16:

1. Política de aprobaciones delegadas.
2. Suspensión y revocación de identidades.
3. Modificación y revocación de Grants durante tareas activas.
4. Cambios de configuración y políticas durante la ejecución.

Estas decisiones no deben volver a presentarse como pendientes, salvo que el propietario decida modificarlas expresamente.

### 20.2. Decisiones de propietario pendientes

Quedan pendientes:

1. Hora y zona horaria del resumen diario de Telegram.
2. Destinatarios autorizados para recibir notificaciones.
3. Política de fallos persistentes de entrega.
4. Contenido permitido por destinatario y clasificación de información.
5. Modalidad inicial de delegación de Atlas: delegated o independent.

### 20.3. Trabajo técnico pendiente

Los parámetros técnicos restantes deberán resolverse durante la especificación e implementación de cada componente, de acuerdo con su clasificación y las decisiones de autoridad establecidas en este contrato.

Los parámetros técnicos pendientes no reabren las políticas aprobadas ni autorizan por sí mismos la implementación.

Su resolución deberá respetar las siguientes condiciones:

1. No modificar ni debilitar las garantías arquitectónicas y de seguridad aprobadas.
2. No ampliar permisos, delegaciones, Grants ni facultades de aprobación.
3. No eliminar controles de autorización, aislamiento, concurrencia, auditoría o recuperación.
4. No convertir valores ilustrativos o placeholders de esquemas en valores operativos aprobados.
5. No resolver por inferencia las decisiones expresamente reservadas al propietario.
6. Documentar los parámetros definidos, su justificación, los componentes afectados y la evidencia de validación correspondiente.

Los parámetros cuya configuración corresponde exclusivamente al propietario deberán permanecer pendientes hasta que este determine sus valores.

Los detalles de implementación que no alteren decisiones ni garantías aprobadas podrán especificarse durante las fases técnicas correspondientes.

Si una decisión técnica requiere modificar, debilitar o posponer una garantía aprobada, no podrá adoptarse como un simple ajuste de implementación. Deberá someterse nuevamente a revisión y aprobación explícita del propietario.

El cierre y aprobación del baseline arquitectónico no certifican la implementación ni la verificación de sus componentes.

### 20.4. Aprobación del baseline arquitectónico

**Estado: APROBADO POR EL PROPIETARIO**

El propietario ha aprobado expresamente el baseline arquitectónico de Atlas v1 y las decisiones de diseño y seguridad consolidadas en este documento.

La aprobación comprende las reglas, invariantes, límites de autoridad, controles de seguridad y decisiones arquitectónicas identificadas como aprobadas.

Esta aprobación no significa que todos los componentes estén implementados, integrados o verificados.

Las decisiones del propietario y los parámetros técnicos que permanecen pendientes en §20.2 y §17 conservan su estado correspondiente. Su existencia no invalida la aprobación del baseline, siempre que se respeten las restricciones establecidas en este contrato.

La autorización para implementar se registra por separado y queda limitada al alcance expresamente indicado en §20.5.


### 20.5 — Aprobación del propietario e inicio de la Fase 1

**Fecha:** 12 de noviembre de 2026.

El propietario aprueba el baseline arquitectónico establecido en este contrato y autoriza el inicio de la primera fase de implementación de Atlas.

**Repositorio principal:** `yon30c/atlas`.

**Rama de trabajo:** `main`.

El repositorio `yon30c/atlas-broker` permanece como proyecto independiente y fuera del alcance de modificación de esta autorización.

**Alcance autorizado de la Fase 1:**

- Atlas Assistant.
- Memory Engine y Memory Gateway.
- Sistema de proactividad.
- Análisis, diseño técnico, planificación, desarrollo y pruebas correspondientes a estos componentes.

**Exclusiones:**

Esta autorización no permite modificar Broker, Registry v2, infraestructura protegida ni servicios de producción; tampoco autoriza despliegues, instalación de Cognee, implementación de Telegram ni cambios de políticas de seguridad o permisos que requieran aprobación adicional.

**Control de cambios y publicación:**

El trabajo se realizará directamente en el servidor de desarrollo. La revisión del propietario se efectuará sobre los cambios publicados y verificables en GitHub.

La autorización para desarrollar no implica autorización automática para realizar commits, push, merges o publicar cambios. Estas acciones seguirán sujetas a la aprobación correspondiente del propietario.

Las decisiones pendientes identificadas en §20.2 permanecen pendientes y no se consideran resueltas por esta aprobación.


### 20.6 — Decisión del propietario: Trust Anchor opcional y postergado

**Fecha:** 13 de noviembre de 2026.  
**Estado:** APROBADO.

El propietario decide que el Trust Anchor externo será una capacidad **opcional** de Atlas y que su implementación real se postergará hasta la etapa final del proyecto.

#### Decisiones aprobadas

1. Las etapas actuales de Atlas trabajarán con un único servidor y el perfil local de continuidad/verificación.
2. No se desarrollará ni desplegará ahora un proveedor externo de Trust Anchor, una VM que actúe como autoridad independiente ni una integración con servicios externos de custodia.
3. La arquitectura conservará interfaces y separación de responsabilidades que permitan incorporar el perfil anclado en la etapa final, sin convertirlo en dependencia de las etapas actuales.
4. La ausencia de Trust Anchor debe declararse explícitamente. El perfil local puede verificar integridad disponible, estructura, secuencias, continuidad interna, inventarios y recibos conforme a sus mecanismos implementados, pero **no demuestra que el estado recuperado sea el último que existió antes de una restauración coherente del conjunto local** y no ofrece protección anti-rollback externa.
5. El perfil anclado será opt-in y deberá seleccionarse explícitamente. Si se selecciona y el proveedor no está disponible o no puede verificarse, fallará cerrado; nunca degradará automáticamente al perfil local.
6. La autenticidad de recibos, el control de autoridad, la idempotencia, la atomicidad, el fencing y la recuperación local siguen siendo requisitos independientes. Hacer Trust Anchor opcional no elimina esos controles.
7. La garantía de que una memoria olvidada no reaparezca tras restaurar un backup anterior al Forget requiere una fuente de supresión/continuidad independiente del conjunto restaurable. Sin ella, la restauración afectada permanecerá bloqueada o requerirá reconciliación explícita; no se afirmará que la garantía está satisfecha.
8. Esta decisión es documental y arquitectónica. No modifica código, no declara implementado el perfil local sin ancla y no autoriza lecturas protegidas, Forget físico, migraciones, despliegues ni cambios de infraestructura.

#### Consecuencias para los contratos ME-03K

- ME-03K-B y ME-03K-C definen dos perfiles: local (baseline actual) y anclado (opcional, etapa final).
- ME-03K-A y la especificación de conformidad separan la validación local de la prueba anti-rollback externa.
- Las pruebas con fakes solo acreditan contratos de coordinación; no prueban criptografía, custodia externa ni anti-rollback.
- El código actual contiene modelos y coordinadores cuyo flujo verificado requiere un Trust Anchor. La compatibilidad de código con el perfil local opcional queda pendiente para su fase de adaptación; no se desarrollará ahora el proveedor Trust Anchor.

#### Registro de cambio

Revisión 3: incorpora la decisión aprobada sobre Trust Anchor opcional, aplaza su implementación real a la etapa final y documenta las limitaciones de anti-rollback y restauración en el perfil local. También actualiza la regla de no reintroducción de memorias olvidadas para evitar afirmar una garantía que no pueda demostrarse sin una fuente independiente de supresión/continuidad.

**Fin del documento.**


## 21. Enmienda normativa B1-A-06 — 15 de noviembre de 2026

**Estado: APROBADA POR EL PROPIETARIO.**

La enmienda `docs/contracts/b1-a06-identity-project-environment-and-persistence.md` adopta y consolida las decisiones B1-A-01 a B1-A-05 como ampliaciones normativas posteriores de este contrato.

Su alcance comprende: autorización individual de consumidores sobre memorias PRIVATE; relación Project–Environment 1:N; identidad canónica y bindings; separación Authentication Authority / Identity Authority / CAM / Consistency; contexto de identidad verificada; y persistencia local compartida mediante una única base SQLite con autoridades de dominio separadas y UoW común donde exista atomicidad real.

Las reglas de compatibilidad histórica, ausencia de alias implícitos de permisos, conservación de migraciones, aislamiento, invalidación, fencing y recuperación se detallan en la enmienda. En particular, no se migran automáticamente estados históricos de Identity y no se declara completa la persistencia de dominios ni el coordinador de cambios de autoridad.

La aprobación es de diseño y no certifica implementación, pruebas ni despliegue. B1-B-02 (diseño físico de persistencia) permanece como siguiente fase documental.
