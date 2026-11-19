# Auditoría y cierre de alineación IPC administrativo con atlas-admin/1

**Estado:** etapas 1–5 del prototipo implementadas; cierre documental del contrato de resultados, canonicalización e invariantes de códigos publicado en revisión 1.1. La corrección posterior del decoder para enteros JSON extremos sigue pendiente de validación local Debian; pendiente revisión final antes de integrar.  
**Base de trabajo:** `test/authority-admin-systemd-activation`.  
**Rama de trabajo:** `work/authority-admin-protocol-contract-alignment`.  
**Fuente normativa IPC:** `docs/contracts/local-authority-admin-ipc-atlas-admin-1.md`. Este documento de auditoría es descriptivo y no sustituye el contrato.  
**Alcance:** transporte IPC, validación del protocolo, ping, pruebas y documentación.  
**Advertencia:** el contrato mantiene estado de propuesta de diseño y no autoriza despliegue, operaciones privilegiadas ni acceso a una base real.

## 1. Resumen ejecutivo

La auditoría inicial encontró que el prototipo demostraba `AF_UNIX/SOCK_SEQPACKET`, `SO_PEERCRED`, allowlist de UID y un ping experimental, pero no implementaba el sobre `atlas-admin/1`, los límites, la respuesta ni los errores normativos.

Las etapas 1–5 alinearon el envelope, los límites, la validación estricta, los errores de transporte y el resultado de ping. La revisión también corrigió una brecha: los errores de protocolo recuperables producen una respuesta `rejected` segura, no una excepción sin envelope.

La implementación sigue siendo deliberadamente estrecha: solo acepta `authority.ping`. Las otras seis operaciones ya tienen especificaciones individuales consolidadas en el contrato normativo, pero siguen sin implementarse y se rechazan con `OPERATION_DENIED`.

## 2. Hallazgos iniciales y resolución

| ID | Hallazgo inicial | Resolución |
|---|---|---|
| A-01 | Request usaba `version: 1` entero | `protocol: "atlas-admin/1"` exacto |
| A-02 | Request máximo 64 KiB | 16 KiB |
| A-03 | Response máximo 4 KiB | 64 KiB |
| A-04 | Response experimental | Envelope normativo §7 |
| A-05 | Ping sin versión de servicio/estado | Resultado mínimo del contrato normativo §9.1 |
| A-06 | Errores sin códigos estables | Códigos estables para transporte/protocolo |
| A-07 | Sin límite de profundidad | Máximo 16 niveles |
| A-08 | Timeout compartido | Lectura/escritura independientes, default 5 s, máximo 60 s |
| A-09 | Desconexión durante envío no manejada | Se clasifica como desconexión de transporte |
| A-10 | Paquete vacío y EOF no diferenciados | Cierre conservador sin operación ni respuesta |
| A-11 | Truncamiento/ancillary genéricos | Rechazo diferenciado, sin respuesta |
| A-12 | UTF-8/JSON genéricos | `INVALID_UTF8` / `INVALID_JSON` |
| A-13 | Versión/operación/payload genéricos | Códigos diferenciados |
| A-14 | Modelo conservaba versión entera | `AdminRequest.protocol` string |

## 3. Contrato implementado

### Request

```json
{
  "protocol": "atlas-admin/1",
  "request_id": "UUIDv4",
  "operation": "authority.ping",
  "payload": {}
}
```

No se admite compatibilidad con el sobre experimental `version: 1`. El código reconoce exactamente los siete nombres del catálogo cerrado. Solo `authority.ping` está implementada; las otras seis se rechazan con `OPERATION_DENIED`, y los nombres ajenos al catálogo reciben `UNKNOWN_OPERATION`.

### Response de éxito

```json
{
  "protocol": "atlas-admin/1",
  "request_id": "UUIDv4",
  "status": "completed",
  "code": "OK",
  "summary": "Operation completed",
  "result": {
    "protocol_version": "atlas-admin/1",
    "service_version": "0.1.0",
    "handler_status": "available"
  },
  "audit_ref": null
}
```

La versión de servicio se obtiene de los metadatos de la distribución `atlas-assistant`; en checkout sin metadatos se usa el fallback `0.1.0`, que debe mantenerse sincronizado con `[project].version`.

### Rechazos

Los errores recuperables de protocolo de un peer autorizado producen un envelope `rejected` con código estable. El request ID se incluye solo si puede validarse canónicamente; en otro caso es `null`. Para peer no autorizado, truncamiento, ancillary prohibido o cierre de transporte se cierra sin respuesta.

### Ping

Devuelve únicamente versión de protocolo, versión de servicio y `handler_status: "available"`. No abre SQLite, no inspecciona el filesystem de la DB y no demuestra su salud o integridad.

## 4. Transporte y validación

- `AF_UNIX/SOCK_SEQPACKET`, un request por conexión.
- `SO_PEERCRED` antes de leer el paquete.
- Request 16 KiB; response 64 KiB.
- UTF-8 y JSON estrictos; claves duplicadas, campos extra y constantes no estándar rechazadas.
- Rechazo de números no finitos, UUID no canónico/no UUIDv4 y profundidad superior a 16.
- Códigos estables de transporte/protocolo.
- Timeouts de lectura/escritura independientes, default 5 s y máximo 60 s.
- Truncamiento, ancillary prohibido, peer no autorizado y desconexión no reciben respuesta.
- No hay listener, loop servidor, socket activation ni unidad systemd en este cambio.

## 5. Cinco etapas ejecutadas

1. Auditoría del contrato las referencias normativas heredadas del contrato raíz frente a código, tests y documentación.
2. Alineación del envelope y límites 16/64 KiB.
3. Validación estricta, profundidad, errores estables, timeouts y cierre seguro.
4. Ping completo sin acceso a DB.
5. Revisión del diff, respuesta `rejected` para errores recuperables y alineación de pruebas filesystem con el contrato vigente.

## 6. Validación del propietario en Debian

El propietario ejecutó la suite completa desde su servidor local Debian 13:

```text
Ran 1583 tests in 34.367s

OK (skipped=1)
```

**Resultado:** 1.583 tests ejecutados, 0 fallos, 0 errores y 1 omitido. La suite completa confirma que desaparecieron los dos errores previos de `test_platform_admin_ipc_filesystem.py` relacionados con el envelope experimental antiguo y la expectativa incorrecta de desconexión.

La validación fue ejecutada por el propietario en Debian; no se ejecutaron pruebas desde GitHub ni durante la edición remota. Este resultado acredita únicamente el checkout probado antes de la corrección adicional del decoder. No debe presentarse como validación de HEAD actual. La corrección posterior descrita en §9 queda pendiente de nueva ejecución local.

## 7. Límites y riesgos pendientes

- Las seis operaciones restantes tienen payloads, precondiciones, resultados, efectos y restricciones documentados en §§9.3–9.8 del contrato normativo, pero no están implementadas ni habilitadas.
- El cierre documental de representación quedó completado en contrato §§9.11.1–9.11.6; los resultados exactos están en §9.12 y el mapeo de códigos/estados en §10.4. Esto no equivale a implementación ni validación de las operaciones.
- No hay listener persistente, daemon ni activación systemd en este PR.
- La concurrencia/backpressure corresponde al futuro listener y debe probarse antes de implementarlo.
- La conducta de EOF/paquete vacío se mantiene conservadora.
- No se habilitan operaciones sobre la DB real, cambios de host ni despliegue.
- La revisión final debe verificar diff completo, contratos, límites de confianza, pruebas adversariales y que ningún cambio amplíe la allowlist.

## 8. Criterio de cierre

Las cinco etapas están implementadas. La validación de 1.583 tests es histórica respecto de la corrección posterior del decoder; no declarar el HEAD actual validado hasta recibir el nuevo resultado local. El siguiente paso es completar la validación y revisión final de seguridad. Mantener PR #28 en Draft hasta concluir esa revisión y obtener aprobación explícita para integrarlo.


## 9. Hallazgo de revisión final: literales enteros extremos

La revisión del decoder identificó que Python puede lanzar `ValueError` al convertir un literal entero JSON que excede el límite de dígitos configurado por el intérprete. El decoder ya convertía errores JSON y recursión excesiva en `INVALID_JSON`, pero no capturaba ese `ValueError`; una solicitud de menos de 16 KiB podía escapar del flujo de rechazo controlado.

**Primera corrección incompleta:** capturar `ValueError` alrededor de `json.loads` evitaba la excepción no controlada, pero el parseo abortaba antes de recuperar `request_id`. La prueba de regresión detectó que el rechazo devolvía `request_id: null` aunque el UUIDv4 estaba presente y era válido.

**Corrección revisada:** el decoder usa `parse_int` para convertir los enteros normales y, si Python rechaza un literal por su límite de conversión, conserva un sentinel interno. Así puede terminar de parsear la estructura, validar/extraer el UUIDv4 y después rechazar el sentinel como `INVALID_JSON`, adjuntando el `request_id` validado. El sentinel nunca llega al payload aceptado. Se conserva el rechazo de JSON inválido y no se eleva el límite global del intérprete.

**Validación:** la prueba focalizada reportada por el propietario falló antes de esta segunda corrección (`request_id=None`, esperado UUIDv4). La corrección revisada está publicada; prueba focalizada y suite completa quedan pendientes de nueva ejecución en Debian.


## 10. Cierre documental de canonicalización, resultados y códigos — 2026-11-19

La revisión 1.1 del contrato normativo `atlas-admin/1` cerró en una sola fuente:

1. **Plan/digest:** §9.11.5 reutiliza `atlas.memory.local_auth.canonical_json_bytes` (canonical JSON v1) y define la proyección exacta `atlas-admin-migration-plan`, sus campos, orden de migraciones, exclusiones, serialización UTF-8 y SHA-256 lowercase. Un plan bloqueado no produce digest aplicable.
2. **Idempotencia de mutaciones:** §9.11.6 define una proyección distinta `atlas-admin-operation-intent`; excluye operation ID, request ID, frase de confirmación y evidencia de cada intento, e incluye la intención semántica y `reason`. La autoridad calcula el digest.
3. **Resultados:** §9.12 define los objetos exactos para las siete operaciones, incluidos los resultados discriminados de `authority.operation.status`, el contenido de cada migración y las referencias de auditoría.
4. **Códigos/estados:** §10.4 fija códigos de dominio, operación aplicable y estado envelope. `pending` no se utiliza por ninguna operación actual; commit incierto de mutación es siempre `unknown/RESULT_UNKNOWN`.

**Límites que no cambian:** solo `authority.ping` está implementada. Las otras seis operaciones siguen deshabilitadas; no existe listener persistente, daemon, systemd ni acceso administrativo real a SQLite. No se modificó código ejecutable ni se ejecutaron pruebas. La suite histórica de 1.583 tests no valida HEAD actual ni la corrección pendiente del decoder.

**Siguiente paso:** revisión de consistencia cruzada del contrato y documentos subordinados, seguida de revisión final de seguridad/diff. El propietario debe validar el decoder en Debian por separado.

## 11. Revisión adversarial de consistencia y frontera de confianza — 2026-11-19

La revisión se realizó sobre la rama `work/authority-admin-protocol-contract-alignment`, PR #28, sin ejecutar pruebas ni workflows remotos.

### Hallazgos y correcciones

1. **Interpretación de credenciales del kernel:** el prototipo desempaquetaba `SO_PEERCRED` con tres enteros con signo. En Linux, `pid_t` es con signo, pero `uid_t` y `gid_t` son sin signo. Un UID/GID válido por encima de `INT_MAX` se interpretaba como negativo y era rechazado, contradiciendo el contrato de admitir cualquier UID válido del tipo del sistema. Corregido en `src/atlas/platform_admin_ipc.py` usando el formato `iII`; la allowlist también rechaza valores fuera del rango unsigned de 32 bits. Se añadió una regresión unitaria con UID/GID altos. **Pendiente de ejecución local Debian.**
2. **Digest de `authority.operation.status`:** §9.5 contenía una frase inicial que podía leerse como si la autoridad comparara contra un digest esperado del cliente, aunque el payload solo contiene `operation_id`. Se corrigió la redacción normativa: el servicio demuestra coherencia interna del registro y el cliente compara el digest devuelto con la intención local que conserva.
3. **Deriva del README:** el resumen IPC del README aún declaraba pendientes la canonicalización del plan, los esquemas de resultados y el mapeo de códigos. Se alineó con el contrato 1.1; esas tareas documentales están cerradas, pero las seis operaciones continúan no implementadas y denegadas.

### Reglas que permanecen como puertas de seguridad

- El handler procesa exactamente un paquete, pero el lifecycle de conexión pertenece al caller. Cualquier futuro listener debe cerrar la conexión después de una única respuesta y nunca reutilizarla para otra solicitud; no se debe tratar la responsabilidad del caller como permiso para mantener conexiones abiertas.
- `operator_evidence` sigue siendo declaración no confiable del frontend. TTY foreground, UID declarado y timestamp no se convierten en identidad autenticada ni sustituyen `SO_PEERCRED`.
- Las seis operaciones no implementadas siguen denegadas. No se implementó listener, acceso SQLite ni mutación administrativa.
- No se ejecutaron pruebas, compile, Actions ni comprobaciones en Debian. La prueba nueva y la validación focalizada/completa del decoder quedan a cargo del propietario.

**Resultado de esta revisión:** se corrigieron los hallazgos concretos anteriores en código, prueba y documentación. Esto no equivale a conformidad validada ni aprobación de despliegue. PR #28 permanece Draft y sin merge.
