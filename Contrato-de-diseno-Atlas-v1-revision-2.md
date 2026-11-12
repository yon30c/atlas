# Atlas v1 — Contrato de diseño (revisión consolidada)

**Estado:** borrador consolidado para revisión y aprobación del propietario.  
**Versión:** revisión 2.  
**Fecha:** 12 de noviembre de 2026.  
**Alcance:** especificación documental y contractual.  
**Implementación:** este documento no autoriza ni declara implementados los componentes descritos.

---

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

#### 1.2.6 Estado global del documento

La revisión 2 es el documento base vigente para esta revisión arquitectónica.

Su utilización como documento base no significa que el contrato completo haya recibido aprobación definitiva.

## El cierre de la revisión arquitectónica requerirá conciliar las decisiones aprobadas, resolver las contradicciones internas, completar las especificaciones pendientes y someter el documento consolidado a aprobación del propietario.

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

Toda solicitud protegida debe contener, como mínimo:

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
  "idempotency_key": "string",
  "correlation_id": "correlation_id"
}
```

Los campos anteriores expresan el contrato lógico. La representación física puede variar.

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
  "concurrency_limit": 1,
  "status": "active|suspended|revoked|expired|exhausted",
  "renewal_requested_at": "instant|null",
  "version": 1
}
```

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
  "idempotency_key": "string",
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
  "deduplication_key": "string",
  "evidence": [],
  "related_event_ids": []
}
```

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

CAM es la autoridad central para conceder, evaluar y aplicar permisos.

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

Resultados lógicos:

- `allow`
- `deny`
- `require_approval`
- `defer`

`defer` no significa permiso temporal. Indica que la operación no puede continuar hasta resolver la condición pendiente.

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
4. Permite continuar partes independientes que sigan autorizadas.
5. Omite dependencias de operaciones bloqueadas.
6. Pausa el flujo afectado cuando no pueda determinarse su independencia o autorización.
7. Conserva los resultados parciales.
8. Informa las operaciones completadas, bloqueadas, omitidas, pendientes y en progreso.
9. No presenta una ejecución parcial como completa.
10. No permite utilizar la ejecución parcial para eludir la revocación.

**PARÁMETROS TÉCNICOS PENDIENTES:**

- Mecanismo de cancelación cooperativa.
- Límites de espera de parada.
- Tratamiento de procesos que no responden.
- Reconciliación de procesos huérfanos.
- Verificación de terminación antes de liberar recursos.

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

### 7.4 Orden de ejecución

**APROBADO:**

- Orden por prioridad y antigüedad.
- Promoción gradual para evitar starvation.
- Una tarea critical bloqueada debe notificarse al propietario.
- Atlas puede explicar el bloqueo y solicitar autorización de ampliación cuando corresponda.
- No puede ampliar permisos o recursos fuera de las reglas aprobadas.

**PARÁMETROS TÉCNICOS PENDIENTES:**

- Valores de concurrencia global, proyecto-entorno y Grant.
- Persistencia de la cola.
- Algoritmo exacto de desempate cuando timestamps coinciden.
- Recuperación de cupos tras una caída.
- Política técnica de cancelación y reintentos.
- Algoritmo exacto de envejecimiento tras interrupciones, respetando la promoción secuencial.

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
- Owner o responsable.
- Clasificación.
- Estado.
- Capacidad y unidad, cuando aplique.
- Atributos no secretos necesarios para identificar el recurso.

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

- Orden canónico exacto.
- Mecanismo de adquisición atómica o compensación segura.
- Backoff.
- Persistencia transaccional.
- Adaptadores para recursos externos.

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

**PARÁMETROS TÉCNICOS PENDIENTES:**

- Límite de reintentos.
- Algoritmo de replanificación.
- Umbrales de recuperación.
- Tiempos de espera concretos.

### 8.8 Lease, heartbeat y fencing

**APROBADO:**

- Cada lock tiene un lease temporal renovable.
- Un supervisor comprueba periódicamente actividad y autorización mediante heartbeat.
- Cada adquisición tiene un fencing token de generación creciente.
- La expiración del lease no significa que el recurso esté libre.
- Antes de una nueva adquisición se verifica que el proceso anterior terminó o se impide técnicamente que siga modificando el recurso.
- El fencing token debe ser validado por el recurso o adaptador que controle todas las escrituras.
- Emitir un token sin hacerlo cumplir no constituye protección.

**PARÁMETROS TÉCNICOS PENDIENTES:**

- Duración del lease.
- Intervalo de heartbeat.
- Tolerancia de reloj.
- Formato y persistencia de tokens.
- Adaptadores y mecanismos de validación.

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

- La memoria se separa por proyecto.
- Un proyecto no puede acceder a la memoria privada de otro por defecto.
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

### 9.4 Olvido y eliminación

**APROBADO:**

- `memory.forget` requiere aprobación.
- La eliminación debe verificarse en todos los almacenes pertinentes.
- Una memoria no puede reaparecer por reindexación o restauración inadvertida.
- No afirmar que un dato se eliminó completamente si solo se retiró de un índice.
- La operación debe conservar evidencia de su ejecución sin volver a exponer el contenido olvidado.

### 9.5 Propuesta técnica de registro

Un registro puede contener:

- ID y versión.
- Scope usuario/proyecto.
- Contenido.
- Procedencia.
- Actor y origen.
- Clasificación.
- Estado.
- Timestamps.
- Referencia a versión anterior.
- Revisión y decisión.

**PARÁMETROS TÉCNICOS PENDIENTES:**

- Tipos de memoria.
- Almacenes e índices.
- Cifrado.
- Resolución de conflictos.
- Estrategia de búsqueda.
- Importación histórica.
- Cobertura de respaldos y eliminación.
- Quién puede proponer cada clase de memoria.

---

## 10. Eventos, incidencias y SecurityAudit

### 10.1 Eventos generales

**APROBADO:**

- Retención indefinida.
- Eventos inmutables.
- Las correcciones crean nuevos eventos relacionados.
- `occurred_at` y `observed_at` son distintos.
- Los tipos de evento y severidades son controlados.
- No se permite asignar arbitrariamente severidad crítica.
- Los eventos y las incidencias son entidades diferentes.
- Los logs se minimizan.
- No almacenar contraseñas, tokens ni secretos.
- No almacenar logs completos sin necesidad y control.

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

**PARÁMETROS TÉCNICOS PENDIENTES:**

- Catálogo de eventos.
- Catálogo de severidades.
- Clasificaciones admitidas.
- Control de acceso y exportación.
- Integridad criptográfica.
- Privacidad y anonimización compatibles con retención indefinida.
- Límites de almacenamiento y alertas.
- Reconciliación de efectos externos inciertos.

La retención indefinida y la inmutabilidad no se reabren.

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

Las operaciones peligrosas o privilegiadas requieren aprobación explícita del propietario y autenticación reforzada, aunque exista un Grant persistente para otras acciones.

### 11.3 Aprobaciones delegadas

**DECISIÓN DEL PROPIETARIO PENDIENTE:**

Definir qué clases de operaciones pueden aprobar personas delegadas y cuáles quedan reservadas exclusivamente al propietario.

Hasta que exista una regla explícita:

- No se presume autoridad de aprobación.
- Las operaciones que requieren aprobación permanecen bloqueadas.
- Un agente nunca puede aprobar su propia solicitud.
- Una notificación no equivale a una aprobación.

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
- Las entregas deben poder reintentarse de forma idempotente.
- Los tokens no se almacenan en repositorios ni logs.
- Debe existir una allowlist de destinatarios.
- No se envía `user_private` ni `system_restricted` por defecto.
- No se envía contenido completo de memorias privadas.

### 11.7 Decisiones pendientes de Telegram

**DECISIÓN DEL PROPIETARIO PENDIENTE:**

1. Hora del resumen diario.
2. Zona horaria.
3. Destinatarios autorizados.
4. Contenido permitido para cada destinatario.
5. Política operativa ante entregas fallidas.

**PROPUESTA TÉCNICA:**

- Conservar las notificaciones pendientes cuando Telegram no entregue.
- Realizar reintentos limitados.
- Registrar el resultado de entrega.
- Evitar duplicados mediante una clave de deduplicación.
- Escalar fallos persistentes por un canal de notificación disponible, si está autorizado.
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

### 12.2 Identidad y aislamiento

**APROBADO:**

- Una skill no hereda permisos de otra.
- Cada skill tiene alcance y permisos explícitos.
- Ninguna skill modifica sus autorizaciones.
- Restaurar una skill no la ejecuta automáticamente.
- Una nueva versión debe pasar revisión.
- Los permisos deben verificarse mediante CAM.

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

**PARÁMETROS TÉCNICOS PENDIENTES:**

- Número máximo de reintentos.
- Backoff.
- Jitter.
- Timeouts por interfaz.
- Retención del ledger.
- Límites de payload.
- Formato de reason codes.

### 13.5 Resultados inciertos

Si una operación pudo producir un efecto externo, pero Atlas no pudo confirmar el resultado:

1. Marcar `outcome_unknown`.
2. Preservar la correlación y evidencia.
3. Consultar el estado externo.
4. Reconciliar el efecto.
5. No repetir ciegamente.
6. Resolver el resultado antes de liberar recursos o iniciar dependencias incompatibles.

### 13.6 Cancelación

La cancelación no equivale a terminación.

Los locks y recursos solo se liberan después de verificar que los procesos asociados terminaron o que el mecanismo de fencing impide que sigan afectando el recurso.

Si no se puede confirmar la terminación, mantener protección y escalar recuperación.

---

## 14. Ciclos de vida y transiciones

### 14.1 Identity

- `active ↔ suspended`
- `active|suspended → revoked`
- `revoked` es terminal.
- Reactivar una identidad revocada requiere una identidad nueva o un proceso explícito del propietario.

El tratamiento de operaciones ya iniciadas por una identidad suspendida queda pendiente de decisión del propietario.

### 14.2 Grant

- `draft → active`
- `active → suspended|revoked|expired|exhausted`
- `suspended → active` solo mediante decisión autorizada del propietario, si sigue siendo válido.
- `revoked` es terminal.
- `expired` no admite nuevas operaciones.
- `indefinite` no requiere fecha de expiración.

La revocación o expiración afecta inmediatamente las nuevas operaciones y tareas dependientes.

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

### 14.4 Approval

- `pending → approved|denied|expired|revoked`
- `approved → consumed`
- Un cambio en el digest requiere una nueva solicitud.
- Una aprobación consumida no puede reutilizarse.

### 14.5 Memory

- `pending_review → approved|rejected`
- `approved → superseded|forgotten`
- Una modificación posterior crea una nueva versión en `pending_review`.

### 14.6 Lock

- `requested → waiting → held → released`
- Alternativas: `expired`, `recovery_required`, `failed`.
- Lease expirado no significa terminación.
- Reconciliar procesos y fencing antes de reutilizar el recurso.

### 14.7 Resource

- `pending_review`
- `active`
- `suspended`
- `retired`

Las transiciones deben conservar la protección mientras existan procesos asociados.

### 14.8 Skill

- `discovered`
- `under_review`
- `approved`
- `installed`
- `active`
- `disabled`
- `revoked`
- `removed`

Un digest nuevo requiere revisión. Una skill restaurada queda inactiva.

### 14.9 Restore

- `normal`
- `recovery_required`
- `verifying`
- `ready_for_owner_activation`
- `active`

No ejecutar proyectos ni skills antes de verificar integridad, permisos y activación deliberada.

---

## 15. Criterios de aceptación

Los siguientes criterios son requisitos de diseño. No se consideran pruebas ejecutadas.

1. Passkey, TOTP y códigos de recuperación funcionan según la política configurada.
2. Identidades suspendidas o revocadas no pueden iniciar nuevas operaciones protegidas.
3. Principal y actor discordantes producen denegación.
4. CAM ausente, política desconocida o error de autorización bloquean operaciones protegidas.
5. Las operaciones cross-project y cross-environment se deniegan sin Grant independiente.
6. Solo el propietario administra Grants.
7. Un agente no puede autoaprobar.
8. Grants temporales requieren expiración.
9. Grants indefinidos requieren selección explícita del propietario.
10. Renovaciones respetan el aviso predeterminado de 24 horas y el silencio no amplía la vigencia.
11. La ampliación automática de recursos se limita a una vez por tarea y a la siguiente configuración disponible.
12. La segunda ampliación requiere autorización.
13. Presupuestos del mismo Grant se comparten entre tareas.
14. Los recursos no se liberan hasta verificar terminación.
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
43. La idempotencia impide duplicar efectos.
44. Un resultado incierto se reconcilia antes de repetir.
45. La cancelación no libera recursos antes de verificar terminación.

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
9. Todas las transiciones y decisiones deberán quedar registradas de acuerdo con el diseño de eventos y auditoría de Atlas.

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

- Límites numéricos de concurrencia global, proyecto-entorno y Grant.
- Unidades y ventanas de presupuesto.
- Contabilidad de uso y reserva.
- Umbral de espera importante.
- Persistencia y recuperación de cola.
- Reconciliación de recursos tras caída.

### 17.2 RLM

- Duraciones de lease.
- Intervalos de heartbeat.
- Tolerancias de reloj.
- Orden canónico exacto de recursos.
- Implementación de fencing.
- Adaptadores para recursos externos.
- Mecanismo de persistencia y reconciliación.
- Backoff.
- Límite de reintentos.
- Algoritmo de desempate cuando persistan empates tras los criterios aprobados.
- Política técnica de locks advisory ante fallos.

### 17.3 Memoria

- Tipos de memoria.
- Almacenes e índices.
- Cifrado.
- Resolución de conflictos.
- Estrategia de búsqueda.
- Importación histórica.
- Verificación de borrado en respaldos e índices.
- Permisos específicos para proponer cada clase de memoria.

### 17.4 Eventos y auditoría

- Catálogo completo de eventos.
- Catálogo de severidades y clasificaciones.
- Acceso y exportación.
- Integridad criptográfica.
- Privacidad y anonimización compatible con retención indefinida.
- Límites de almacenamiento y alertas.
- Reconciliación de efectos externos.

### 17.5 Skills

- Formato del manifiesto.
- Firma y procedencia.
- Herramientas de análisis.
- Criterios de riesgo.
- Sandbox.
- Aislamiento.
- Política de red.
- Procedimiento de actualización y revocación.

### 17.6 Interfaces

- Timeouts por interfaz.
- Límites de payload.
- Backoff y reintentos.
- Retención del ledger de idempotencia.
- Formato de reason codes.
- Política de reconciliación por tipo de operación.

Los valores deben definirse mediante análisis técnico, límites reales del host y pruebas. No se deben inventar valores universales.

---

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
| Memory Engine          | Diseño en desarrollo                                              |
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
7. Cada versión debe conservar un registro de cambios.
8. El contrato aprobado no implica autorización de implementación.
9. La implementación se planifica por fases y requiere autorización independiente.
10. Ninguna fase puede modificar Broker, Registry v2, producción o infraestructura protegida sin autorización explícita.

---

## 20. Estado final de esta revisión

Esta revisión consolida las decisiones aprobadas durante el diseño de Atlas v1 y corrige las contradicciones identificadas en el borrador anterior.

**No constituye todavía aprobación final del propietario.**

Quedan cuatro grupos de decisiones de propietario:

1. Catálogo de aprobaciones y delegación.
2. Continuidad de operaciones cuando una identidad está suspendida.
3. Hora, zona horaria y destinatarios del resumen de Telegram.
4. Política de fallos y contenido permitido en Telegram.

Los parámetros técnicos restantes deben resolverse durante la especificación de cada componente, sin reabrir las políticas aprobadas.

**Fin del documento.**
