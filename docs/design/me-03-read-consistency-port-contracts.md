# ME-03 — Contratos tipados de consistencia y entrega protegida

**Estado:** diseño aceptado; integración parcial del Gateway protegida en curso.  
**Rama:** `implementation/me-01-to-me-04-memory-engine`  
**Dependencias:** ME-01, ME-02, ME-03 §§4.8–4.11, DM-01, CT-01 y CT-05.  
**Alcance:** contratos lógicos de snapshots CAM, revisiones, admisiones, supresión, invalidaciones y entrega protegida.  
**Fuera de alcance:** adaptadores reales, almacenamiento físico, transporte, colas, locks, proveedor criptográfico, topología, despliegue y eliminación física/verificación final de Forget.

Este documento traduce las garantías aceptadas en contratos tipados y responsabilidades de puertos. El estado real de las interfaces y de la integración Python se registra en §§12–14; las propuestas y firmas conceptuales no deben confundirse con adaptadores de runtime.

---

## 1. Hallazgos iniciales de compatibilidad con ME-01/ME-02 (línea base)

Esta tabla conserva la línea base inspeccionada antes de implementar snapshots, revisiones y el Gateway protegido. No representa el estado actual; consultar §§12–14.

| Elemento | Estado actual | Cambio requerido |
|---|---|---|
| `AuthorizationResult` | Solo contiene `decision` | ALLOW debe incluir un snapshot CAM confiable y exacto |
| `MemoryVersionMetadata` | IDs, estado, clasificación y padre; sin revisión | Incorporar revisión canónica monotónica |
| `ProjectMetadata` / `EnvironmentMetadata` | ID y estado; sin revisión | Incorporar revisión canónica monotónica |
| `AuthenticatedUserSubject` | Actor, sujeto y `is_active`; sin revisión | Exponer revisión/época de identidad |
| `Grant` | Alcance, acciones, fechas y revocación; sin revisión | Exponer revisión/época exacta del Grant |
| `MemoryVersionContentPort` | Lee por IDs | Exigir snapshot y admisión válidos; no permitir fallback por IDs |
| `MemoryGatewayService.get_version()` | Devuelve `MemoryVersion` al llamador | No debe liberar contenido crudo fuera de la sesión de entrega protegida |
| Supresión/admisión | No existe puerto | Definir autoridad lógica y contratos de ciclo de vida |
| Entrega protegida | No existe puerto | Definir compromiso de emisión y fencing por endpoint |

La implementación actual es correcta como etapa inicial de autorización seguida de lectura, pero no satisface la garantía ME-03 de consistencia concurrente y fencing de extremo a extremo.

## 2. Reglas de diseño de los contratos

1. CAM sigue siendo la única autoridad que decide si la acción está autorizada.
2. La autoridad de consistencia no concede permisos ni interpreta políticas CAM; coordina admisiones, revisiones, cierres y fencing.
3. Memory Gateway sigue siendo la única frontera pública de memoria.
4. Ningún puerto de contenido puede ser invocado por Assistant, Skills, Watchers, endpoints o consumidores externos directamente.
5. El contenido solo puede cruzar un punto de entrega registrado y capaz de aplicar fencing.
6. Las operaciones deben fallar cerradas ante ausencia, discrepancia, timeout, estado ambiguo o revisión no verificable.
7. PRIVATE y PROJECT conservan las reglas actuales de CAM. La ausencia de Grant en PRIVATE debe representarse como una condición explícita de la ruta de propietario, nunca como un dato faltante.
8. Los contratos no fijan formato criptográfico, base de datos, mecanismo de concurrencia ni transporte.

## 3. Contratos de revisión y autorización

### 3.1 AuthorityRevision

Cada autoridad canónica mutable expone una revisión monotónica propia:

- Memory.
- MemoryVersion.
- Project, cuando aplique.
- Environment, cuando aplique.
- Identity del actor.
- Grant exacto, cuando aplique.
- Supresión/admisión para el conjunto de recursos afectado.

La revisión es comparable únicamente dentro de su misma autoridad/agregado. No se comparan revisiones de autoridades distintas. No puede faltar una revisión requerida, retroceder, reutilizarse ni cambiar sin que el cambio lógico correspondiente la incremente.

Cada transición que pueda alterar autorización o visibilidad debe ordenar su nueva revisión respecto de los compromisos de emisión. No se acepta actualizar el dato canónico y propagar su revisión posteriormente mediante una notificación eventual.

### 3.2 AuthorizationRevisionSet

Objeto inmutable que vincula las revisiones exactas evaluadas por CAM:

| Campo | Obligatorio | Condición |
|---|---|---|
| `memory_revision` | Sí | Siempre |
| `version_revision` | Sí | Siempre |
| `identity_revision` | Sí | Siempre |
| `project_revision` | Según scope | Obligatorio para PROJECT |
| `environment_revision` | Según scope | Obligatorio para PROJECT |
| `grant_id` | Según scope | Grant exacto para PROJECT |
| `grant_revision` | Según scope | Obligatorio junto con `grant_id` |
| `admission_generation` | Al admitir | Generación de fencing asignada por la autoridad |

Un campo requerido ausente o marcado como no aplicable sin que corresponda al scope produce DENY. PRIVATE usa la regla explícita del propietario y la revisión de identidad; no inventa un Grant. PROJECT requiere proyecto, entorno y Grant exactos.

### 3.3 AuthorizationSnapshot

CAM emite un snapshot inmutable únicamente después de evaluar la solicitud y obtener ALLOW. Debe vincular:

- `snapshot_id` y `decision_id` opacos;
- `request_id`;
- acción exacta (`memory.read`);
- `actor_identity_id` y sujeto autenticado cuando corresponda;
- `memory_id`, `version_id` y `owner_id` exactos;
- scope, `project_id` y entorno cuando apliquen;
- estado y clasificación de la versión evaluada;
- `AuthorizationRevisionSet`;
- instante de emisión confiable;
- `grant_expires_at` cuando la decisión dependa de un Grant.

El snapshot no contiene contenido y no es un permiso autónomo. Es evidencia de qué hechos evaluó CAM. No puede ser creado, modificado ni ampliado por Gateway, Assistant, un consumidor o el solicitante.

**Contrato de resultado CAM propuesto:**

- ALLOW: incluye exactamente un `AuthorizationSnapshot`.
- DENY o REQUIRE_APPROVAL: no incluye snapshot de lectura.
- Resultado inválido, incompleto o contradictorio: se trata como DENY.

Una nueva autorización produce un snapshot nuevo. No se renueva ni muta un snapshot antiguo.

## 4. Contratos de admisión y supresión

### 4.1 ReadTarget y DeliveryRouteSet

`ReadTarget` identifica una memoria y versión exactas. La admisión debe incluir el conjunto de recursos cuya visibilidad puede verse afectada por el cierre correspondiente.

`DeliveryRouteSet` contiene IDs opacos de todos los puntos de entrega que participarán en esa lectura. Debe derivarse del inventario de rutas vigente. Una ruta desconocida, no registrada o incapaz de fencing no puede aceptar la admisión.

El inventario de rutas no sustituye al inventario de persistencia/derivados. Son contratos separados.

### 4.2 ReadAdmission

La autoridad emite una admisión solo si puede comprobar atómicamente:

1. El snapshot procede de CAM y corresponde al objetivo exacto.
2. Todas las revisiones requeridas siguen vigentes.
3. No existe cierre ni invalidación pendiente para el objetivo o alguno de sus ancestros.
4. No existe supresión lógica activa.
5. Las rutas de entrega están registradas y habilitadas.
6. La autoridad puede registrar durablemente la admisión antes de permitir recuperar contenido.

La admisión contiene, como mínimo:

- `admission_id` opaco y único;
- `snapshot_id`;
- `memory_id` y `version_id`;
- alcance exacto de recursos;
- generación de fencing;
- IDs de rutas de entrega;
- estado lógico;
- instante de admisión.

La admisión no sustituye CAM. No puede utilizarse con otro actor, memoria, versión, acción, generación o endpoint.

### 4.3 ReadConsistencyAuthorityPort

Contrato lógico propuesto:

```python
class ReadConsistencyAuthorityPort(Protocol):
    def admit_read(
        self,
        snapshot: AuthorizationSnapshot,
        routes: DeliveryRouteSet,
        now: datetime,
    ) -> ReadAdmission | None: ...

    def begin_forget(
        self,
        target: ForgetTarget,
        authorization: ForgetAuthorizationReceipt,
        idempotency_key: str,
    ) -> ForgetClosure | None: ...

    def begin_invalidation(
        self,
        invalidation: AuthorizationInvalidation,
    ) -> InvalidationReceipt | None: ...

    def record_endpoint_ack(
        self,
        receipt: EndpointFenceReceipt,
    ) -> bool: ...

    def get_nonterminal_admissions(
        self,
        operation_id: str,
    ) -> tuple[ReadAdmission, ...]: ...

    def reconcile(
        self,
        operation_id: str,
    ) -> ReconciliationResult: ...
```

Semántica:

- `admit_read` es indivisible respecto de cierres e invalidaciones. No puede haber admisión entre el cierre y el inventario de admisiones previas.
- `begin_forget` recibe una autorización ya validada por Gateway/CAM y OwnerDecisionVerifier, vinculada al objetivo exacto. La autoridad no acepta un booleano ni una afirmación del Assistant como prueba.
- `begin_invalidation` registra la nueva época y bloquea emisiones antiguas antes de que el cambio de autoridad pueda considerarse efectivo para contenido protegido.
- Los acknowledgements deben identificar operación, admisión, generación y endpoint.
- `reconcile` nunca convierte timeout o ausencia de heartbeat en cancelación.
- Si la autoridad no está disponible, no se admiten lecturas ni se confirma supresión.

Los nombres y firmas definen contratos tipados. El estado de las implementaciones Python parciales y sus límites se registra en §§12–14.

## 5. Contrato de lectura condicional de contenido

El puerto anterior `MemoryVersionContentPort.get_version_content(memory_id, version_id)` fue retirado: solo identificaba por IDs y no probaba que la lectura perteneciera a una admisión vigente.

**Interfaz implementada:**

```python
class ProtectedMemoryContentPort(Protocol):
    def read_version_if_admitted(
        self,
        snapshot: AuthorizationSnapshot,
        admission: ReadAdmission,
    ) -> ProtectedContentHandle | None: ...
```

Condiciones:

- IDs y revisiones exactos del snapshot.
- Admisión vigente, objetivo coincidente y generación actual.
- Estado APPROVED y clasificación autorizada.
- Ausencia de supresión lógica.
- Ningún fallback por IDs si snapshot o admisión faltan.
- El resultado es interno a Gateway y a la sesión protegida. No puede devolverse como contenido crudo a un llamador arbitrario.
- La lectura interna no marca la admisión como completada: la entrega sigue activa hasta que los endpoints terminen o sean cercados.
- Cualquier buffer creado por esta lectura queda bajo el alcance de la admisión y debe descartarse o quedar inaccesible tras su invalidación.

El adaptador de contenido no decide autorización. Solo verifica las condiciones técnicas que le corresponden y devuelve ausencia genérica ante cualquier discrepancia.

## 6. Contrato de entrega protegida

### 6.1 ProtectedEgressPort

El punto final de entrega debe ofrecer una operación indivisible de compromiso y liberación:

```python
class ProtectedEgressPort(Protocol):
    def commit_and_emit(
        self,
        admission: ReadAdmission,
        handle: ProtectedContentHandle,
        endpoint_id: str,
        emission_id: str,
        sequence: int,
        now: datetime,
    ) -> EgressReceipt | None: ...

    def finish(
        self,
        admission: ReadAdmission,
        operation_id: str,
        endpoint_id: str,
        final_sequence: int,
        now: datetime,
    ) -> EndpointCompletionReceipt | None: ...

    def fence(
        self,
        admission: ReadAdmission,
        operation_id: str,
        endpoint_id: str,
        new_generation: int,
        now: datetime,
    ) -> EndpointFenceReceipt | None: ...

    def reconcile(
        self,
        admission: ReadAdmission,
        endpoint_id: str,
    ) -> EndpointDeliveryStatus: ...
```

`commit_and_emit` no puede implementarse como «consultar autorización y luego enviar» si existe una ventana entre ambas operaciones. El compromiso y la aceptación irrevocable por el último punto controlado deben compartir el mismo orden lógico que Forget y las invalidaciones.

Cada endpoint debe:

- comprobar la admisión, generación, revisiones y vigencia temporal en cada unidad;
- rechazar unidades posteriores al cierre o invalidación;
- preservar IDs de admisión y secuencias a través de buffers/intermediarios;
- descartar unidades no comprometidas al aplicar fencing;
- emitir acknowledgements correlacionados e idempotentes;
- no declarar finalización si quedan bytes, buffers, fragmentos o trabajo pendiente;
- permanecer fuera de servicio para contenido protegido si no puede demostrar fencing.

Una unidad comprometida antes del cierre cuenta como emitida antes del cierre, aunque la latencia del transporte haga que llegue al consumidor después. Ninguna unidad todavía bajo control de Atlas puede cruzar el último punto de entrega después del cierre.

### 6.2 ReadAdmission lifecycle

Se conservan los estados lógicos ME-03:

- ADMITTED
- ACTIVE
- COMPLETED
- CANCELLED
- UNRESOLVED

COMPLETED y CANCELLED son terminales incompatibles. UNRESOLVED no es terminal y bloquea la confirmación de Forget o invalidación que dependa de demostrar que no habrá más emisiones.

### 6.3 Consumidores internos y Assistant

Un consumidor interno que recibe contenido protegido también es una ruta de entrega inventariable. No puede conservar una copia independiente que luego emita contenido sin controles.

Si un consumidor puede producir una respuesta derivada a partir de la memoria, su trabajo debe permanecer vinculado a la admisión hasta completar la entrega derivada o confirmar su cancelación. Los puntos de salida de esa respuesta deben aplicar el fencing correspondiente. No basta con proteger la transferencia inicial desde Memory Gateway y dejar sin control la respuesta posterior.

Este requisito no concede a Assistant autoridad sobre memoria ni modifica CT-06; define cómo debe integrarse como consumidor de contenido protegido.

## 7. Invalidación de autorizaciones

### 7.1 AuthorizationInvalidation

Representa una transición que puede invalidar admisiones existentes:

- tipo de autoridad (Identity, Grant, Memory, MemoryVersion, Project o Environment);
- ID exacto de la autoridad/agregado;
- revisión anterior y nueva revisión;
- alcance de recursos y admisiones afectadas;
- ID de invalidación;
- motivo tipado, sin contenido privado.

El cambio canónico y el avance de fencing deben quedar ordenados. Si no puede probarse ese orden, la ruta afectada se bloquea.

### 7.2 Grant expiry

El compromiso de cada unidad comprueba el instante confiable. Para el Grant actual, se preserva la semántica del evaluador:

- `issued_at <= now < expires_at`;
- `revoked_at is None or revoked_at > now`.

No hay periodo de gracia. Una admisión previa no extiende el Grant. Si el reloj confiable falla o resulta ambiguo, no se emite.

### 7.3 Identidad

La revisión de Identity debe reflejar ACTIVE, SUSPENDED o REVOKED. SUSPENDED bloquea nuevas operaciones y respeta el punto seguro de CT-01; REVOKED impide continuar operaciones dependientes. La invalidación y el fencing deben aplicarse a las rutas afectadas sin depender de propagación eventual.

## 8. Operación durable e idempotencia

Todo cierre, invalidación y admisión debe tener:

- identificador único;
- clave de idempotencia cuando sea una solicitud repetible;
- objetivo y alcance exactos;
- estado monotónico;
- generación;
- secuencia de transición;
- correlación de endpoints;
- acknowledgements verificables.

La misma clave con el mismo objetivo devuelve la operación existente. La misma clave con otro objetivo se rechaza. Un acknowledgement duplicado, tardío o de otra generación no puede cambiar estados terminales.

Tras reinicio:

1. Restaurar cierres y generaciones.
2. Mantener bloqueadas las rutas afectadas.
3. Recuperar admisiones no terminales como UNRESOLVED.
4. Reconciliar cada endpoint.
5. Reabrir solo las rutas cuya seguridad haya quedado demostrada; las rutas no verificables permanecen deshabilitadas.

Los registros no contienen payloads, fragmentos, contenido olvidado ni hashes de contenido.

## 9. Cambios requeridos en las interfaces actuales

| Interfaz actual | Evolución requerida |
|---|---|
| `AuthorizationResult` | Resultado de autorización con snapshot tipado obligatorio en ALLOW |
| `MemoryVersionMetadata` | Añadir revisión monotónica |
| `ProjectMetadata` / `EnvironmentMetadata` | Añadir revisión monotónica |
| `AuthenticatedUserSubject` | Añadir revisión/época de identidad y estado canónico |
| `Grant` y `GrantRepository` | Exponer revisión del Grant exacto y mantener semántica temporal actual |
| `MemoryVersionContentPort` | Sustituir lectura por IDs por lectura condicional con snapshot y admisión |
| `MemoryGateway.get_version` | Sustituir retorno crudo por sesión/entrega protegida |
| Nuevos puertos | ReadConsistencyAuthorityPort y ProtectedEgressPort |

No se debe hacer una migración parcial que deje coexistir una ruta nueva segura con un fallback antiguo que devuelva contenido crudo. La ruta antigua debe quedar retirada o estrictamente interna y no alcanzable por consumidores.

## 10. Orden de implementación recomendado

1. Definir modelos inmutables de revisiones, snapshot CAM, admisión, invalidación y recibos.
2. Añadir revisiones a los snapshots de metadatos y a las autoridades Identity/Grant.
3. Implementar puertos y fakes deterministas para admisión, cierre, invalidación y egress.
4. Modificar MemoryAuthorizationService para emitir snapshot solo con ALLOW.
5. Modificar MemoryGateway para orquestar snapshot → admisión → lectura condicional → entrega protegida.
6. Implementar estados terminales, fencing y recuperación con pruebas C01–C44.
7. Revisar todos los puntos de entrega y consumidores antes de afirmar cobertura global.
8. No integrar almacenamiento real ni declarar Forget completo hasta completar inventarios y criterios de verificación CT-05.

Cada paso debe conservar fail-closed y pruebas unitarias. Los fakes demuestran el contrato lógico, no integración real ni garantías de runtime.

## 11. Decisiones y pendientes

**Direcciones técnicas adoptadas en esta especificación:** snapshot CAM ligado a revisiones; admisión durable; autoridad lógica única; lectura condicional; compromiso de emisión ordenado; fencing por unidad; invalidación coordinada; estados terminales; idempotencia; recuperación fail-closed; consumidores internos inventariados.

**Pendientes antes de implementar los puertos:**

1. Revisión de nombres, tipos e imports exactos con el paquete actual.
2. Definir cómo cada fuente canónica participa en el protocolo de invalidación sin seleccionar proveedor.
3. Completar inventarios reales de persistencia y entrega.
4. Definir evidencia verificable para cada tipo de destino físico y backup.
5. Convertir estos contratos en pruebas unitarias deterministas antes de escribir adaptadores.

**Estado:** especificación documental. No modifica código, contratos normativos, infraestructura ni producción.


## 12. Estado de implementación — revisiones canónicas y snapshot CAM

La primera parte de la implementación de los contratos de revisión quedó incorporada en la rama de trabajo:

- `Memory` y `MemoryVersion` exponen revisión positiva, con revisión inicial 1 para agregados recién creados.
- `MemoryVersionMetadata`, `ProjectMetadata` y `EnvironmentMetadata` requieren revisión positiva explícita desde sus puertos.
- `Identity` expone su revisión; la vinculación confiable `AuthenticatedUserSubject` también expone revisión y se rechaza si no coincide con la revisión del actor autenticado.
- `Grant` expone revisión; revocación y aprobación de renovación avanzan la revisión.
- `AuthorizationEvaluator` devuelve una evaluación interna que conserva el Grant exacto que coincidió. Esa evaluación interna no constituye por sí sola una autorización pública.
- `AuthorizationResult` exige un `AuthorizationSnapshot` para ALLOW y prohíbe snapshots para DENY o REQUIRE_APPROVAL.
- `MemoryAuthorizationService` genera snapshots privados y de proyecto con las revisiones de memoria, versión e identidad; PROJECT incluye además las revisiones exactas de proyecto, entorno y Grant.

### Límites pendientes

1. La revisión inicial 1 es válida para creación de un agregado nuevo. Los adaptadores futuros deben persistirla y recuperarla explícitamente; no deben reconstruir revisiones a partir de valores predeterminados al hidratar datos antiguos.
2. Todavía no existe una autoridad persistente que garantice incrementos monotónicos y compare-and-swap para Memory, MemoryVersion, Identity, Project, Environment y Grant.
3. Las transiciones de estado de Identity, Memory y MemoryVersion aún no están integradas con invalidación/fencing.
4. El Gateway todavía no consume el snapshot para admisión y egress protegidos; su ruta antigua de lectura sigue pendiente de migración y no debe considerarse compatible con la garantía ME-03 completa.
5. No hay adaptadores reales ni almacenamiento implementado en esta etapa.

**Verificación:** se añadieron y actualizaron pruebas unitarias para revisiones y snapshots, pero no se ha ejecutado la suite ni existe un workflow/status check asociado al commit de esta implementación. No se declara validación de runtime.


## 13. Estado de implementación — fakes de autoridad y egress

Se añadió `tests/unit/test_memory_consistency_authority.py` con un fake determinista de proceso único que implementa los comportamientos principales de `ReadConsistencyAuthorityPort` y `ProtectedEgressPort` para pruebas:

- Admisión únicamente cuando las revisiones Memory, MemoryVersion e Identity coinciden con el snapshot y todas las rutas están registradas.
- Inventario exacto de admisiones afectadas por una invalidación; se rechazan inventarios incompletos o con IDs ajenos.
- Incremento de generación al iniciar invalidación.
- Rechazo de nuevas emisiones de admisiones con generación anterior.
- Acknowledgements correlacionados por operación, admisión, endpoint y generación.
- Reconciliación no terminal hasta que cada endpoint afectado confirma finalización o fencing.
- Transición a COMPLETED solo cuando todos los endpoints confirman finalización; si hay una combinación de finalización y fencing, la admisión queda CANCELLED.
- Emisiones con secuencia estricta y handle vinculado a la admisión y objetivo exactos.
- Una emisión comprometida antes del cierre puede completar su acknowledgement después del cierre; no puede comprometer una unidad adicional.

### Límites explícitos del fake

El fake es una herramienta de prueba, no un adaptador de producción. Usa memoria local y un lock de proceso único. No prueba persistencia durable, compare-and-swap distribuido, fencing entre procesos, transporte de red, recuperación tras reinicio ni cobertura real de todos los endpoints. Tampoco implementa persistencia durable, recuperación tras reinicio, supresión global ni eliminación física. La extensión del fake para Forget en §14.3 solo prueba el contrato lógico en memoria y proceso único.

La interfaz de `ReadConsistencyAuthorityPort` ya declara el inicio y la reconciliación del cierre lógico Forget. La autoridad concreta todavía debe implementar el ciclo completo con autorización verificable y evidencia CT-05 antes de que pueda considerarse completa. No se selecciona todavía almacenamiento ni transporte.

**Verificación:** se incorporaron pruebas adicionales para admisión, inventario de invalidación, fencing, finalización y egress. No se ha ejecutado la suite ni existe status check/workflow asociado a estos commits. No se afirma validación de runtime.


### 13.1 Aclaración de correlación de acknowledgements

Las firmas tipadas de `ProtectedEgressPort.finish()` y `fence()` requieren `operation_id` y `endpoint_id` explícitos. El egress no debe inferir qué invalidación o ciclo de lectura intenta completar a partir de estado ambiental. Cada recibo debe quedar vinculado a una operación y endpoint concretos; la autoridad valida esa correlación antes de aceptarlo.

El fake de pruebas implementa la correlación explícita, acknowledgements idempotentes y serialización conservadora de invalidaciones que afectan una misma admisión. Una invalidación nueva que se solape con una operación aún pendiente se rechaza hasta reconciliar la anterior.

El conjunto de pruebas de autoridad/egress contiene actualmente 20 métodos de prueba, incluidos los escenarios de cierre lógico Forget descritos en §14.3. Este número describe pruebas escritas, no pruebas ejecutadas.


## 14. Estado de integración del Gateway protegido

Se sustituyó la ruta anterior de lectura cruda por el siguiente flujo de frontera:

1. `MemoryGatewayService.get_version()` obtiene un resultado CAM. Solo continúa si es `AuthorizationResult(ALLOW, snapshot)` y el snapshot identifica exactamente la memoria, versión y acción solicitadas.
2. Después de CAM, el Gateway obtiene una segunda lectura de tiempo UTC confiable y solicita `admit_read(snapshot, routes, now)`. Si el Grant expiró entre CAM y admisión, rechaza la lectura. La autoridad debe validar revisiones actuales, supresión, generación, expiración de Grant y el conjunto completo de rutas registradas.
3. El Gateway valida que la admisión devuelta coincida exactamente con snapshot, objetivo, propietario, scope y rutas configuradas.
4. Solo entonces llama a `ProtectedMemoryContentPort.read_version_if_admitted(snapshot, admission)`.
5. El puerto de contenido devuelve un `ProtectedContentHandle` opaco. El Gateway valida IDs, admisión y clasificación y construye `ProtectedMemoryRead`; nunca devuelve `MemoryVersion` ni su contenido.
6. Cada unidad pasa por `emit_version()`, que llama a `ProtectedEgressPort.commit_and_emit()`. La expiración del Grant se comprueba en el Gateway y debe volver a comprobarse atómicamente en el último punto de egress.
7. Cada endpoint confirma su finalización mediante `finish_version()`; el recibo queda vinculado a la operación `read:{admission_id}`, admisión, endpoint, generación y secuencia final. `reconcile_version()` consulta el resultado sin forzar terminalidad.

Si la lectura condicional falla después de admitir, el Gateway intenta cerrar la admisión vacía con secuencia final cero para todos los endpoints. Si falta cualquier acknowledgement, la admisión permanece pendiente/no resuelta; no se presupone finalización.

### 14.1 Retirada de la ruta cruda

- Se retiró `src/atlas/ports/memory_content.py` y el puerto `MemoryVersionContentPort.get_version_content(memory_id, version_id)`.
- El contrato público `MemoryGateway.get_version()` ahora devuelve `ProtectedMemoryRead | None`, no `MemoryVersion | None`.
- La emisión y finalización están expuestas como operaciones explícitas del Gateway.

### 14.2 Límites y pendientes

Esta integración define el camino protegido, pero no acredita la garantía completa:

- `ProtectedMemoryRead` es un lease opaco a nivel de API Python; la seguridad final depende de que el handle real no exponga payload ni permita serialización o lectura fuera de egress.
- La configuración de `DeliveryRouteSet` debe provenir de composición confiable y representar todas las rutas que puedan emitir contenido. No debe aceptar rutas elegidas libremente por el solicitante.
- La autoridad concreta debe crear atómicamente la operación `read:{admission_id}` junto con la admisión y comprobar supresión, revisiones, generación y cobertura.
- El egress concreto debe ordenar cada compromiso respecto de invalidaciones/Forget y validar revisiones y expiración de Grant por unidad.
- `begin_forget` y `reconcile_forget` están definidos en el puerto y cubiertos por un fake de proceso único; no existe autoridad durable ni emisor/verificador confiable de OwnerDecisionProof. El inventario verificable de destinos de persistencia/derivados sigue pendiente.
- No hay adaptadores reales, persistencia durable, transporte ni recuperación distribuida.

Los tests escritos para esta integración incluyen 16 casos unitarios del Gateway, 9 casos CAM/Gateway y 3 casos de seguridad de frontera. Usan fakes donde corresponde. No se han ejecutado en esta etapa y no prueban comportamiento de runtime. Esta implementación no habilita todavía lectura protegida en producción.

### 14.3 Contrato inicial de cierre lógico Forget

Se añadieron `src/atlas/memory/forget.py` y los siguientes modelos puros:

- `ForgetTarget`: identifica la Memory lógica exacta. Forget v1 cubre esa memoria y todas sus versiones; no admite seleccionar una versión aislada.
- `ForgetClosure`: conserva el ID de cierre, operación, clave de idempotencia, objetivo, generación de fencing, conjunto de admisiones previas, conjunto aún no resuelto, rutas de entrega y estado operativo.
- `ForgetClosureStatus`: distingue `CLOSING` de `SUPPRESSED`. El segundo solo es válido cuando el conjunto no resuelto está vacío. Los IDs de admisiones afectadas se conservan como evidencia mínima incluso después de reconciliarse.

El modelo no contiene payload, fragmentos, hashes ni contenido derivado. `SUPPRESSED` describe exclusivamente el cierre lógico de exposición; no representa eliminación física, no cambia MemoryVersion a `forgotten` y no permite comunicar que el olvido completo terminó.

Se amplió `ReadConsistencyAuthorityPort` con:

- `begin_forget(target, authorization, idempotency_key, now)`: exige una autorización ya verificada y consumida por CAM/OwnerDecisionVerifier; debe serializarse atómicamente con `admit_read`, cerrar nuevas admisiones, avanzar generación y capturar todas las admisiones/rutas anteriores.
- `reconcile_forget(operation_id)`: mantiene `CLOSING` mientras cualquier admisión previa esté no resuelta y solo devuelve `SUPPRESSED` tras evidencia correlacionada de finalización o fencing de todos los endpoints.

El protocolo `VerifiedForgetAuthorization` representa la frontera tipada para la evidencia ya verificada. No implementa un emisor ni un verificador: el repositorio aún no dispone de un emisor confiable de OwnerDecisionProof. Por tanto, este contrato **no habilita una operación Forget invocable** ni admite sustituir la prueba por un booleano, texto de chat o afirmación del Assistant.

Se añadieron siete pruebas de modelo en `tests/unit/test_memory_forget.py` y cinco escenarios adicionales de autoridad/egress en `tests/unit/test_memory_consistency_authority.py`; son pruebas escritas y no ejecutadas. El fake cubre idempotencia, rechazo de reutilización de clave, vínculo propietario/actor, carrera con admisión, bloqueo de nuevas lecturas y acknowledgements parciales/fencing. Aún falta recuperación tras reinicio y revisar todos los canales de entrega. No hay persistencia durable, supresión global ni eliminación física implementadas.