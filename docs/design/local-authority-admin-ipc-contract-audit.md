# Auditoría de alineación IPC administrativo con atlas-admin/1

**Estado:** etapa 1 completada; auditoría documental y de código, sin cambios de comportamiento.
**Base de trabajo:** `test/authority-admin-systemd-activation`.
**Contrato normativo revisado:** `design/authority-admin-operations-contract`, documento `docs/design/local-authority-administrative-operations-design.md`, blob `e7bec4ee4c467fb72cbedc2b89f262714a880f71`.
**Alcance:** §10.4–10.6, §11, §15.1–15.2; implementación IPC y pruebas unitarias actuales.
**Advertencia:** el propio contrato mantiene estado de propuesta de diseño y no autoriza despliegue, operaciones privilegiadas ni acceso a una base real.

## 1. Resumen ejecutivo

El prototipo actual demuestra una frontera experimental `AF_UNIX/SOCK_SEQPACKET`, autenticación del peer mediante `SO_PEERCRED`, una allowlist de UID y aceptación de un único paquete JSON para `authority.ping`. No implementa todavía el sobre `atlas-admin/1` ni el contrato de respuesta y errores de §10.

La brecha no se resuelve con un cambio aislado de nombres: afecta el modelo de request, límites, validación JSON, errores tipados, timeouts, respuesta y pruebas. La implementación de las otras seis operaciones queda expresamente fuera del alcance de esta alineación inicial.

## 2. Hallazgos

| ID | Severidad | Área | Estado actual | Requisito contractual |
|---|---|---|---|---|
| A-01 | Crítica | Request envelope | Usa `version: 1` entero | Debe usar `protocol: "atlas-admin/1"` |
| A-02 | Alta | Límite de request | `MAX_REQUEST_BYTES = 64 KiB` | Máximo 16 KiB |
| A-03 | Alta | Límite de response | `MAX_RESPONSE_BYTES = 4 KiB` | Máximo 64 KiB |
| A-04 | Alta | Response envelope | Devuelve `version`, `status: "ok"`, `operation` | Debe devolver `protocol`, `request_id`, estado contractual, `code`, `summary`, `result` y `audit_ref` |
| A-05 | Alta | Ping | No devuelve versión del servicio ni estado explícito del handler | §15.2 requiere versión de protocolo, versión de servicio y disponibilidad del handler |
| A-06 | Alta | Errores | Excepciones genéricas; los mensajes no forman un catálogo estable | Debe mapear a los códigos de §10.6, sin depender de mensajes de excepción |
| A-07 | Alta | Profundidad JSON | No existe límite explícito de profundidad 16 | Rechazar profundidad superior a 16 |
| A-08 | Media | Timeout | Un timeout se aplica conjuntamente a recepción y envío | Default 5 s y máximo configurable 60 s para read y write; conviene separarlos |
| A-09 | Media | Desconexión de peer | `BrokenPipeError` no está manejado explícitamente | Desconexión es error de transporte y no debe tumbar el proceso ni falsear el resultado de una mutación |
| A-10 | Media | Paquete vacío/EOF | El paquete vacío acaba como rechazo genérico de tamaño; no distingue EOF | Verificar el comportamiento del kernel; si no se distingue, cerrar sin operación ni respuesta |
| A-11 | Media | Truncamiento/ancillary | `MSG_TRUNC` y `MSG_CTRUNC` comparten rechazo genérico; ancillary presente tiene otro mensaje genérico | Mapear a `MESSAGE_TRUNCATED` y `ANCILLARY_DATA_FORBIDDEN` según la causa |
| A-12 | Media | UTF-8/JSON | UTF-8 inválido y JSON malformado comparten una excepción genérica | Distinguir `INVALID_UTF8` de `INVALID_JSON`; mantener rechazo de claves duplicadas y constantes no estándar |
| A-13 | Media | Versión/operación/payload | Versión, operación y payload inválidos comparten `AdminProtocolRejected` | Diferenciar versión no soportada, operación desconocida y argumentos inválidos |
| A-14 | Baja | Contrato de datos | `AdminRequest.version` representa un entero | Debe reflejar el identificador de protocolo string sin crear alias legacy |

### 2.1 Propiedades ya presentes que deben conservarse

- Solo `AF_UNIX/SOCK_SEQPACKET`; se rechaza `SOCK_STREAM`.
- `SO_PEERCRED` se consulta desde el kernel antes de leer el paquete.
- El UID permitido se entrega mediante allowlist explícita; no se confía en identidad declarada en JSON.
- Un request por conexión y payload de ping vacío.
- Se rechazan claves JSON duplicadas, campos extra, UUID no canónico/no UUIDv4, booleano como versión, UTF-8 inválido, JSON inválido, `NaN`/`Infinity`, ancillary data y paquetes truncados.
- El módulo no abre SQLite, no inspecciona el filesystem de la DB, no crea listener ni cambia UID/GID.

## 3. Contrato objetivo para la operación implementada

### Request

El único request aceptado en esta etapa debe tener exactamente estas claves:

```json
{
  "protocol": "atlas-admin/1",
  "request_id": "UUIDv4",
  "operation": "authority.ping",
  "payload": {}
}
```

No se conservará compatibilidad con el sobre experimental `version: 1`: aceptar ambos formatos crearía dos protocolos de facto y debilitaría la validación exacta.

### Response

El ping correcto debe producir un sobre equivalente a:

```json
{
  "protocol": "atlas-admin/1",
  "request_id": "UUIDv4",
  "status": "completed",
  "code": "OK",
  "summary": "Operation completed",
  "result": {
    "protocol": "atlas-admin/1",
    "service_version": "version-defined-by-build-metadata",
    "handler": "available"
  },
  "audit_ref": null
}
```

El campo `service_version` debe provenir de metadatos de versión mantenidos por el proyecto; no se debe inventar ni derivar de una ruta, variable de entorno arbitraria o dato del cliente. Su fuente concreta se resolverá antes de implementar la respuesta.

El resultado no incluirá rutas, configuración, variables de entorno, identidad del operador, datos de SQLite ni inventario interno. Ping no crea sesión ni estado entre conexiones.

## 4. Estrategia de implementación por etapas

1. **Auditoría (esta etapa):** inventariar discrepancias, conservar invariantes existentes y definir el comportamiento contractual de ping.
2. **Sobre y límites:** introducir `protocol`, UUIDv4, allowlist cerrada temporal de ping, límites 16/64 KiB y respuesta con estructura contractual. No añadir operaciones de catálogo en esta etapa.
3. **Validación y transporte:** profundidad JSON 16, errores estables, timeouts read/write explícitos, tratamiento seguro de EOF, truncamiento, ancillary data y desconexión.
4. **Ping completo:** obtener una versión de servicio confiable, devolver la disponibilidad del handler y mantener cero acceso a SQLite/filesystem de DB y cero efectos laterales.
5. **Revisión e integración:** revisar diff, documentación y coherencia; preparar instrucciones de validación para Debian. La suite y las pruebas de integración serán ejecutadas por el propietario en Debian, no por esta intervención.

Cada etapa tendrá su propio commit y revisión antes de avanzar. No se implementarán `diagnose`, migraciones, status, initialize ni provisioning en esta secuencia.

## 5. Riesgos y decisiones que requieren atención

- **No ampliar la superficie:** el catálogo normativo contiene siete operaciones, pero esta rama seguirá aceptando solo `authority.ping` hasta que las operaciones read-only y mutables tengan sus propios contratos e implementación revisada.
- **No confundir protocolo con salud de dominio:** ping solo prueba que el canal y handler responden; no prueba SQLite.
- **No responder siempre:** peer no autorizado, truncamiento y ancillary prohibido pueden cerrarse sin respuesta conforme a §10.5. La respuesta de error solo se construirá cuando sea seguro recuperar el request ID.
- **No convertir excepciones de validación en fallos de proceso:** el loop servidor futuro deberá capturar rechazos por conexión y continuar; este módulo todavía no implementa un listener.
- **Commit ambiguity:** no hay mutaciones en el prototipo; los estados `pending` y `unknown` no deben simularse para ping.
- **Versión del servicio:** antes de implementar §15.2 se debe localizar la fuente de versión del paquete/proyecto y elegir una única fuente mantenida.

## 6. Validación existente y alcance de esta intervención

El propietario informó previamente que, en Debian, la rama base pasó 1.576 tests con 1 omitido, además de las pruebas aisladas de IPC y de systemd socket activation. Estos resultados corresponden a la rama base antes de los cambios de esta secuencia; no son evidencia de pruebas de esta rama de trabajo.

No se ejecutaron pruebas desde GitHub ni desde esta intervención. Todas las pruebas de las etapas siguientes se solicitarán al propietario en Debian.

## 7. Criterio de aceptación de esta auditoría

- Las discrepancias entre §10/§15 y el prototipo están identificadas.
- Se preserva el alcance experimental y la única operación ping.
- No se toca SQLite, filesystem de DB, listener productivo, systemd ni identidad del proceso.
- Las siguientes etapas tienen límites explícitos y no habilitan operaciones no revisadas.
