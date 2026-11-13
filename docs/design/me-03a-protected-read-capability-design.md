# ME-03A — Protección de capacidades de lectura

**Estado:** diseño aprobado para implementación incremental  
**Ámbito:** Memory Gateway y contrato de lectura protegida  
**No incluido:** persistencia del journal, autoridad distribuida, egress real, selección de almacenamiento ni aislamiento entre procesos.

## 1. Objetivo

Evitar que un consumidor de Memory Gateway obtenga referencias internas al snapshot CAM, a la admisión o al handle de contenido. El consumidor recibe únicamente una capacidad opaca que le permite solicitar operaciones limitadas al Gateway.

La capacidad no es una autorización autónoma ni sustituye CAM, la autoridad de consistencia o el fencing del egress.

## 2. Decisión ME-03A-01 — Capacidad opaca de lectura

`ProtectedMemoryRead` expone únicamente un identificador aleatorio de capacidad. No contiene `AuthorizationSnapshot`, `ReadAdmission`, `ProtectedContentHandle` ni datos de contenido.

El identificador se trata como secreto bearer:
- se genera con un generador criptográficamente seguro;
- no se deriva de IDs de usuario, memoria, versión, admisión ni request;
- no se incluye en logs ni representaciones;
- se valida contra una sesión activa mantenida por el Gateway;
- una capacidad inventada, alterada, expirada o desconocida falla cerrado.

La capacidad queda ligada en el estado privado del Gateway a la operación, snapshot, admisión, handle y rutas autorizadas exactas.

## 3. Decisión ME-03A-02 — Estado interno bajo control del Gateway

El Gateway mantiene un registro privado de sesiones de lectura. Solo los métodos del Gateway pueden resolver una capacidad a su sesión interna.

El registro no es almacenamiento durable y no pretende sobrevivir al reinicio del proceso. Después de reiniciar:
- las capacidades anteriores dejan de ser utilizables;
- ninguna sesión puede reconstruirse a partir de un token del consumidor;
- admisiones durables no reconciliadas permanecen bajo la autoridad de consistencia como unresolved;
- la autoridad y el egress siguen obligados a rechazar generaciones antiguas.

La pérdida de una sesión no demuestra que el endpoint haya dejado de emitir; la recuperación y el fencing siguen siendo responsabilidades de ME-03B/ME-03C.

## 4. Decisión ME-03A-03 — Resolución y ciclo de vida

`emit_version`, `finish_version` y `reconcile_version` reciben la capacidad pública y resuelven la sesión internamente.

La sesión se elimina del registro local únicamente cuando la reconciliación informa que la admisión exacta está resuelta. Un resultado ausente, ambiguo, con error o que deje la admisión unresolved no permite liberar la sesión.

La eliminación local de la sesión no equivale a Forget, supresión física ni borrado de contenido.

## 5. Decisión ME-03A-04 — Concurrencia local

Las operaciones de alta, resolución y retirada del registro de sesiones se protegen con sincronización local. Esa sincronización evita corrupción del registro dentro del proceso; **no** sustituye la autoridad lógica compartida ni establece orden global entre admisión, invalidación y egress.

El compromiso de emisión y el fencing continúan siendo atómicos en el contrato de `ProtectedEgressPort` y deberán compartir la frontera autoritativa definida en ME-03B.

## 6. Límites y amenazas

Esta etapa protege contra acceso accidental por la API pública del Gateway y contra consumidores que intenten inspeccionar el objeto devuelto mediante sus campos documentados.

No constituye una frontera contra código Python arbitrario ejecutándose dentro del mismo proceso con capacidad de inspeccionar memoria, monkey-patching o introspección del runtime. Para consumidores mutuamente no confiables se requerirá aislamiento de proceso y una interfaz IPC autenticada, fuera del alcance de ME-03A.

La capacidad es bearer: quien la posea puede solicitar operaciones que la sesión permita, sujetas a endpoint registrado, vigencia temporal, autoridad y egress. No se debe persistir, compartir ni registrar.

## 7. Criterios de aceptación

- `ProtectedMemoryRead` no expone snapshot, admisión ni handle.
- Una capacidad no emitida por el Gateway no permite emitir, finalizar ni reconciliar.
- El Gateway resuelve internamente la capacidad y pasa el handle exacto al egress.
- Las rutas siguen limitadas al conjunto configurado y a la admisión exacta.
- La expiración del Grant y la validación de tiempo siguen aplicándose en cada emisión.
- Una reconciliación unresolved o ambigua no libera la sesión.
- Una reconciliación que resuelve la admisión retira la capacidad local.
- Ningún cambio afirma que existe persistencia durable, aislamiento de procesos o egress real.

## 8. Secuencia de implementación

1. Sustituir el objeto público rico por capacidad opaca.
2. Añadir registro privado de sesiones en Gateway y resolución controlada.
3. Adaptar pruebas unitarias e integración para demostrar ausencia de exposición y rechazo de capacidades falsificadas.
4. Actualizar el contrato ME-03 y registrar limitaciones.
5. Revisar el diff y estado de CI; no abrir PR ni hacer merge.
