# ME-03B — Autoridad única de consistencia

**Estado:** decisión de diseño e integración de contrato  
**Rama:** `implementation/me-01-to-me-04-memory-engine`  
**Dependencias:** CT-01, CT-03, CT-05, CT-08; DM-01; ME-03; ME-03A; contratos de puertos de lectura protegida y journal durable.  
**Fuera de alcance:** selección de almacenamiento, broker, transporte, topología, despliegue, implementación durable/distribuida, inventarios operativos completos y eliminación física.

## 1. Problema

El Gateway recibe hoy dos dependencias:

- `ReadConsistencyAuthorityPort`, que administra admisiones, Forget, invalidaciones, acknowledgements y reconciliación;
- `ProtectedEgressPort`, que compromete emisiones, finaliza endpoints, aplica fencing y consulta el estado del endpoint.

Aunque el fake actual delega el egress a la misma instancia de autoridad y usa su mismo lock, la construcción del Gateway no exige esa identidad. Un adaptador podría recibir dos objetos independientes y dejar una carrera entre `commit_and_emit` y `begin_forget`/`begin_invalidation`.

La documentación exige orden lógico compartido, pero la firma del Gateway permite una configuración que no puede demostrarlo. ME-03B corrige esa brecha contractual sin elegir el mecanismo físico.

## 2. Decisión ME-03B-01 — Una sola frontera inyectada

El Gateway dependerá de un único `ProtectedMemoryConsistencyPort`. Este protocolo compuesto reúne las capacidades de autoridad y egress:

- admisión;
- cierre y reconciliación de Forget;
- invalidación;
- compromiso y aceptación irrevocable de emisiones;
- finalización y fencing de endpoints;
- registro de acknowledgements;
- consulta/reconciliación de estado.

Los contratos de autoridad y egress pueden conservarse como facetas tipadas para organizar responsabilidades internas, pero el Gateway no recibirá instancias independientes de esas facetas. La misma instancia de la frontera compuesta será responsable de todas las operaciones que deban compartir orden.

El puerto de contenido permanece separado: solo recibe snapshot y admisión exactos y devuelve un handle protegido. No se introduce una ruta de lectura por IDs ni se devuelve contenido al consumidor.

## 3. Invariantes

| ID | Invariante |
|---|---|
| ME-03B-01 | Un Gateway tiene exactamente una dependencia de consistencia para admisión, Forget, invalidación y egress. |
| ME-03B-02 | `admit_read`, `begin_forget`, `begin_invalidation` y `commit_and_emit` pertenecen a la misma frontera lógica de orden. |
| ME-03B-03 | El compromiso de emisión y su aceptación irrevocable son una operación indivisible ordenada con cierres e invalidaciones. |
| ME-03B-04 | La finalización, fencing, acknowledgements y reconciliación se registran/consultan en esa misma frontera. |
| ME-03B-05 | Un wrapper o proxy no satisface la garantía por el mero hecho de exponer los métodos: la implementación debe demostrar que todos operan sobre el mismo estado autoritativo y orden. |
| ME-03B-06 | Si la frontera no puede probar la continuidad u orden requerido, falla cerrado; no delega la decisión a una caché local ni a un segundo puerto independiente. |
| ME-03B-07 | El Gateway no expone snapshot, admisión, handle ni contenido fuera de sus operaciones protegidas. |
| ME-03B-08 | La sincronización local del Gateway no se considera orden global, durabilidad ni fencing entre procesos. |

## 4. Contrato compuesto

Se define `ProtectedMemoryConsistencyPort` como protocolo compuesto de las facetas `ReadConsistencyAuthorityPort` y `ProtectedEgressPort`. El Gateway acepta únicamente esa interfaz compuesta y utiliza la misma instancia para todas las llamadas.

La composición es una restricción de la frontera de inyección, no una prueba automática de linealizabilidad. Cada implementación concreta deberá garantizar que las operaciones que se solapan usan una única relación de orden autoritativa. La implementación puede delegar internamente a componentes físicos diferentes solo si conserva esa propiedad de extremo a extremo; no puede usar un permiso o token temporal que luego se compruebe y libere en una operación separada.

La interfaz de egress conserva los parámetros explícitos de operación, admisión, endpoint, generación, secuencia y tiempo. Ningún endpoint infiere el cierre al que responde a partir de estado ambiental.

## 5. Semántica de orden

Para cualquier admisión afectada:

1. Si `commit_and_emit` se compromete antes de `begin_forget` o `begin_invalidation`, esa unidad cuenta como emitida antes del cierre.
2. Si el cierre/invalidation se ordena primero, toda emisión posterior de la admisión antigua se rechaza.
3. La operación de emisión no puede dividirse en comprobar generación y liberar bytes después.
4. Un resultado ambiguo conserva la admisión como `UNRESOLVED`; no se infiere que la unidad no fue emitida.
5. Las unidades comprometidas previamente no se consideran revocables retroactivamente; las que sigan bajo control de Atlas no pueden liberarse después del cierre.
6. La revocación/expiración de autorización y el tiempo confiable se revalidan en el punto de compromiso.

El orden de operaciones no relacionadas puede progresar independientemente si la implementación demuestra que sus alcances no se solapan. Una operación de invalidación cuyo alcance incluya varias memorias debe conservar atomicidad lógica para el conjunto afectado.

## 6. Responsabilidades

### Gateway
- Ejecuta CAM antes de solicitar admisión.
- Pasa snapshot y rutas exactos a la frontera compuesta.
- Lee contenido únicamente después de una admisión válida.
- Conserva snapshot/admisión/handle en sesión privada.
- Solicita emisión/finalización/reconciliación a la misma frontera.
- No declara terminalidad ni supresión por cuenta propia.

### ProtectedMemoryConsistencyPort
- Es el punto de coordinación lógica para las operaciones anteriores.
- Comprueba revisiones, generación, supresión, rutas y vigencia temporal.
- Ordena atómicamente admisión, cierre, invalidación y compromiso de emisión.
- Registra recibos correlacionados e idempotentes.
- Recupera y reconcilia estado sin inferencias optimistas.
- Mantiene las rutas cerradas cuando la evidencia es incompleta.

### ProtectedMemoryContentPort
- Recupera un handle solo para snapshot y admisión exactos.
- No expone payload al Gateway consumidor ni ofrece fallback por IDs.
- No declara admisiones completadas ni aplica decisiones de Forget.

### Endpoint de entrega
- Acepta unidades únicamente mediante el compromiso protegido.
- Aplica fencing a todas las salidas, buffers, fragmentos e intermediarios.
- Emite recibos correlacionados y consultables tras fallos.
- No convierte timeout o pérdida de proceso en confirmación de cancelación.

## 7. Fallos y respuesta obligatoria

| Fallo | Respuesta |
|---|---|
| La frontera compuesta no está configurada o no implementa una operación | No se admite ni se emite; fallo cerrado. |
| Dos adaptadores independientes se configuran para autoridad y egress | Configuración inválida: el Gateway ya no acepta dos dependencias separadas. |
| El journal no confirma admisión | No se lee contenido. |
| El cierre gana el orden frente a una emisión | La emisión se rechaza. |
| La emisión gana el orden antes del cierre | Se conserva como emisión anterior; el cierre espera reconciliar lo pendiente. |
| Respuesta de egress ambigua | Admisión `UNRESOLVED`; mantener gate cerrado cuando corresponda. |
| Falta ack de endpoint | No se confirma `SUPPRESSED` ni `CANCELLED`. |
| Recuperación con registro o endpoint contradictorio | Cuarentena/fail-closed hasta reconciliación. |
| Caída del proceso Gateway | La capacidad local deja de resolverse; la autoridad durable conserva admisiones y cierres pendientes. |

## 8. Pruebas de aceptación

- El constructor del Gateway recibe una sola frontera de consistencia.
- La misma instancia recibe `admit_read`, `commit_and_emit`, `finish`, `record_endpoint_ack` y `reconcile`.
- La frontera ofrece además `begin_forget`, `reconcile_forget` y `begin_invalidation`.
- No existe un parámetro de egress separado en el Gateway.
- Un fake integrado implementa las operaciones sobre el mismo estado/lock.
- Prueba concurrente determinista entre emisión e invalidación: el resultado corresponde a un único orden; nunca se acepta una emisión posterior al cierre.
- La prueba de concurrencia no usa sleeps ni temporizadores.
- Las rutas de contenido crudo siguen inaccesibles.
- La documentación distingue contrato compuesto de garantía real de runtime.

## 9. Límites y no objetivos

Esta etapa no implementa ni demuestra:
- journal durable ni transacciones distribuidas;
- linealizabilidad entre procesos o nodos;
- atomicidad real entre registro y transporte;
- fencing de un proveedor de red real;
- continuidad criptográfica, recuperación o alta disponibilidad;
- inventario completo de rutas y destinos;
- eliminación física ni Forget completado.

El fake de pruebas puede demostrar un orden determinista dentro de un proceso y compartir un lock, pero no demuestra una garantía distribuida. No se selecciona base de datos, broker, caché, proveedor ni topología.

## 10. Secuencia de implementación

1. Añadir el protocolo compuesto y documentar la frontera única.
2. Cambiar MemoryGatewayService para aceptar y utilizar una sola instancia.
3. Adaptar fakes/pruebas de Gateway para que la misma autoridad implemente las operaciones de egress.
4. Mantener pruebas de concurrencia de la autoridad y dejar claro que son fakes de proceso único.
5. Actualizar el contrato ME-03 y registrar las limitaciones reales.
6. Revisar referencias, diff, estado de commit y CI sin abrir PR ni hacer merge.


## 11. Estado de implementación parcial

Se incorporó `ProtectedMemoryConsistencyPort` como protocolo compuesto por las facetas de autoridad y egress. `MemoryGatewayService` ahora recibe una sola instancia de ese contrato; admisión, compromiso de emisión, finalización, acknowledgements y reconciliación pasan por la misma dependencia. El constructor ya no acepta un `ProtectedEgressPort` independiente.

Se renombró la consulta de estado de un endpoint a `reconcile_endpoint(admission, endpoint_id)` para evitar colisión con `reconcile(operation_id)`, que consulta la operación completa.

Los fakes de Gateway fueron adaptados para implementar ambas facetas sobre la misma instancia. El fake de autoridad de consistencia ya serializa admisión, invalidación y compromiso de egress bajo su lock de proceso único; la prueba concurrente existente cubre ese orden local mediante barrera determinista.

**Limitaciones:** el fake no demuestra linealizabilidad distribuida, persistencia durable, atomicidad real con transporte, recuperación tras reinicio ni fencing de endpoints reales. Las pruebas fueron modificadas, pero no se han ejecutado en esta etapa. No se declara validación automatizada ni CI exitoso.
