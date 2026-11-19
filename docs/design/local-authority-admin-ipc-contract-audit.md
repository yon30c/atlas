# Auditoría y cierre de alineación IPC administrativo con atlas-admin/1

**Estado:** etapas 1–5 implementadas; la suite completa de 1.583 tests corresponde a una revisión anterior. La corrección posterior del decoder para enteros JSON extremos está pendiente de validación local Debian; pendiente revisión final antes de integrar.  
**Base de trabajo:** `test/authority-admin-systemd-activation`.  
**Rama de trabajo:** `work/authority-admin-protocol-contract-alignment`.  
**Fuente normativa IPC:** `docs/contracts/local-authority-admin-ipc-atlas-admin-1.md`. Este documento de auditoría es descriptivo y no sustituye el contrato.  
**Alcance:** transporte IPC, validación del protocolo, ping, pruebas y documentación.  
**Advertencia:** el contrato mantiene estado de propuesta de diseño y no autoriza despliegue, operaciones privilegiadas ni acceso a una base real.

## 1. Resumen ejecutivo

La auditoría inicial encontró que el prototipo demostraba `AF_UNIX/SOCK_SEQPACKET`, `SO_PEERCRED`, allowlist de UID y un ping experimental, pero no implementaba el sobre `atlas-admin/1`, los límites, la respuesta ni los errores normativos.

Las etapas 1–5 alinearon el envelope, los límites, la validación estricta, los errores de transporte y el resultado de ping. La revisión también corrigió una brecha: los errores de protocolo recuperables producen una respuesta `rejected` segura, no una excepción sin envelope.

La implementación sigue siendo deliberadamente estrecha: solo acepta `authority.ping`. Las otras seis operaciones del catálogo se reconocen, pero se rechazan con `OPERATION_DENIED`.

## 2. Hallazgos iniciales y resolución

| ID | Hallazgo inicial | Resolución |
|---|---|---|
| A-01 | Request usaba `version: 1` entero | `protocol: "atlas-admin/1"` exacto |
| A-02 | Request máximo 64 KiB | 16 KiB |
| A-03 | Response máximo 4 KiB | 64 KiB |
| A-04 | Response experimental | Envelope normativo §7 |
| A-05 | Ping sin versión de servicio/estado | Resultado mínimo §15.2 |
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

- No se implementaron `diagnose`, `migrations.plan`, `operation.status`, `initialize`, `migrations.apply` ni `project_environment.provision`.
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
