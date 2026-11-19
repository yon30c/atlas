# Auditoría y cierre de alineación IPC administrativo con atlas-admin/1

**Estado:** etapas 1–5 implementadas en la rama de trabajo; pendientes las pruebas del propietario en Debian y la revisión final antes de integrar.  
**Base de trabajo:** `test/authority-admin-systemd-activation`.  
**Rama de trabajo:** `work/authority-admin-protocol-contract-alignment`.  
**Contrato normativo revisado:** `design/authority-admin-operations-contract`, documento `docs/design/local-authority-administrative-operations-design.md`, blob `e7bec4ee4c467fb72cbedc2b89f262714a880f71`.  
**Alcance:** §10.4–10.6, §11, §15.1–15.2; implementación IPC y pruebas unitarias.  
**Advertencia:** el contrato mantiene estado de propuesta de diseño y no autoriza despliegue, operaciones privilegiadas ni acceso a una base real.

## 1. Resumen ejecutivo

La auditoría inicial encontró que el prototipo demostraba `AF_UNIX/SOCK_SEQPACKET`, `SO_PEERCRED`, allowlist de UID y un ping experimental, pero no implementaba el sobre `atlas-admin/1`, los límites, la respuesta ni los errores normativos.

Las etapas 2–4 alinearon el envelope, los límites, la validación estricta, los errores de transporte y el resultado de ping. La revisión de etapa 5 detectó y corrigió además una brecha: los errores de protocolo recuperables deben producir una respuesta `rejected` segura, no limitarse a propagar una excepción.

La implementación sigue siendo deliberadamente estrecha: solo acepta `authority.ping`. Las otras seis operaciones del catálogo no se habilitaron.

## 2. Hallazgos de la auditoría inicial

La siguiente tabla registra el estado encontrado antes de los cambios, no el estado actual:

| ID | Severidad inicial | Hallazgo inicial | Resolución |
|---|---|---|---|
| A-01 | Crítica | Request usaba `version: 1` entero | Cerrado: `protocol: "atlas-admin/1"` exacto |
| A-02 | Alta | Request máximo 64 KiB | Cerrado: 16 KiB |
| A-03 | Alta | Response máximo 4 KiB | Cerrado: 64 KiB |
| A-04 | Alta | Response experimental no contractual | Cerrado: envelope §10.5 |
| A-05 | Alta | Ping no informaba versión del servicio ni handler | Cerrado: resultado mínimo §15.2 |
| A-06 | Alta | Errores sin códigos estables | Cerrado para errores de transporte/protocolo de esta operación |
| A-07 | Alta | Sin límite explícito de profundidad | Cerrado: máximo 16 niveles de contenedores JSON |
| A-08 | Media | Un timeout compartido para lectura/escritura | Cerrado: parámetros independientes, default 5 s, máximo 60 s |
| A-09 | Media | Desconexión durante envío no manejada | Cerrado: se clasifica como desconexión de transporte, sin falsear resultado |
| A-10 | Media | Paquete vacío y EOF no diferenciados | Cerrado conservadoramente: ambos se tratan como cierre sin operación ni respuesta |
| A-11 | Media | Truncamiento y ancillary compartían rechazo genérico | Cerrado: códigos diferenciados; no se responde a esos casos |
| A-12 | Media | UTF-8 y JSON compartían rechazo genérico | Cerrado: `INVALID_UTF8` y `INVALID_JSON` |
| A-13 | Media | Versión, operación y payload compartían rechazo genérico | Cerrado: códigos diferenciados |
| A-14 | Baja | Modelo de request conservaba campo entero `version` | Cerrado: `AdminRequest.protocol` es string |

## 3. Contrato implementado

### Request

El único request aceptado tiene exactamente estas claves:

```json
{
  "protocol": "atlas-admin/1",
  "request_id": "UUIDv4",
  "operation": "authority.ping",
  "payload": {}
}
```

No se admite compatibilidad con el sobre experimental `version: 1`. El código reconoce exactamente los siete nombres del catálogo cerrado de §11. Solo `authority.ping` está implementada; las otras seis se rechazan con `OPERATION_DENIED`, mientras que nombres ajenos al catálogo reciben `UNKNOWN_OPERATION`. No se han activado alias ni operaciones adicionales.

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

La versión de servicio se obtiene de los metadatos de la distribución `atlas-assistant`. Si se ejecuta desde un checkout sin metadatos instalados, se usa el fallback `0.1.0`, que debe mantenerse sincronizado con `[project].version` en `pyproject.toml`.

### Response de rechazo recuperable

Para errores de validación de una solicitud recibida de un peer autorizado, cuando no hay truncamiento ni ancillary prohibido, se envía:

```json
{
  "protocol": "atlas-admin/1",
  "request_id": "UUIDv4-or-null",
  "status": "rejected",
  "code": "INVALID_REQUEST",
  "summary": "Request rejected",
  "result": {},
  "audit_ref": null
}
```

El request ID solo se incluye cuando se pudo recuperar y validar como UUIDv4 canónico. Para UTF-8/JSON malformado, claves duplicadas o solicitudes cuyo ID no puede validarse se devuelve `null`.

Para peer no autorizado, `MSG_TRUNC`, `MSG_CTRUNC`/ancillary prohibido y cierre de transporte, se cierra sin respuesta conforme a §10.5.

### Resultado de ping

El resultado contiene exclusivamente:
- `protocol_version`;
- `service_version`;
- `handler_status: "available"`.

No incluye rutas, variables de entorno, configuración secreta, identidad del operador ni inventario interno. Ping no abre SQLite ni inspecciona el filesystem de la DB; tampoco demuestra su salud o integridad.

## 4. Validación y transporte implementados

- UTF-8 estricto, JSON estricto, claves duplicadas rechazadas y constantes no estándar rechazadas.
- Rechazo de floats no finitos, incluidos valores como `1e999` que se convierten a infinito al parsear.
- Profundidad máxima de 16 niveles de contenedores JSON.
- Sobre exacto, UUIDv4 canónico, campos exactos, allowlist cerrada y payload vacío para ping.
- Request 16 KiB y response 64 KiB.
- Códigos de rechazo estables: `UNAUTHORIZED_PEER`, `EMPTY_REQUEST`, `REQUEST_TOO_LARGE`, `MESSAGE_TRUNCATED`, `ANCILLARY_DATA_FORBIDDEN`, `INVALID_UTF8`, `INVALID_JSON`, `INVALID_REQUEST`, `UNSUPPORTED_PROTOCOL_VERSION`, `UNKNOWN_OPERATION`, `INVALID_ARGUMENTS` y `TIMEOUT`.
- Timeouts independientes de lectura/escritura, cada uno con default 5 s y máximo 60 s.
- `SO_PEERCRED` se consulta antes de leer el paquete.
- Un solo request por conexión, transporte `AF_UNIX/SOCK_SEQPACKET`.
- `BrokenPipeError`, reset/cierre del peer y timeout no se convierten en errores de dominio.
- No hay listener, loop servidor, socket activation ni unidad systemd en este cambio. El futuro loop debe capturar errores por conexión y continuar sin terminar el proceso.

## 5. Cinco etapas ejecutadas

1. **Auditoría:** comparación del contrato §10/§11/§15 con código, pruebas y documentación; hallazgos registrados.
2. **Sobre y límites:** envelope `atlas-admin/1`, límites 16/64 KiB y envelope de respuesta contractual.
3. **Validación y errores:** profundidad 16, JSON estricto, códigos estables, timeouts independientes y manejo conservador de cierre/truncamiento/ancillary/desconexión.
4. **Ping completo:** versión de protocolo, versión de servicio y estado del handler; sin acceso a DB.
5. **Revisión e integración:** se revisó el diff, se añadió respuesta `rejected` para errores recuperables y se preparó la rama para validación del propietario.

No se implementaron `diagnose`, `migrations.plan`, `operation.status`, `initialize`, `migrations.apply` ni `project_environment.provision`.

## 6. Límites y riesgos pendientes

- **Pruebas:** esta rama no ha sido ejecutada. Los resultados de 1.576 tests y 1 omitido comunicados por el propietario corresponden a la rama base anterior a estos cambios.
- **Kernel/EOF:** el código adopta la regla conservadora del contrato para una recepción vacía; la validación empírica del comportamiento de Debian sigue pendiente.
- **Concurrencia:** no existe listener ni límite de concurrencia en este módulo; corresponderá al servidor futuro.
- **Errores internos:** los códigos de operaciones futuras (`OPERATION_DENIED`, `IDEMPOTENCY_CONFLICT`, `OPERATION_FAILED`, `RESULT_UNKNOWN`, etc.) no se simulan mientras esas operaciones no existan.
- **Producción:** el cambio no autoriza despliegue, cambios de systemd, acceso a la DB real ni mutaciones.

## 7. Validación que debe ejecutar el propietario en Debian

Desde el checkout de `work/authority-admin-protocol-contract-alignment`:

```bash
python -m unittest -v tests.unit.test_platform_admin_ipc
python -m compileall -q src tests
git diff --check
git status --short --branch
```

Después, ejecutar la suite completa del repositorio con el mecanismo de discovery que ya funcionó en Debian y reportar:
- comando exacto;
- número de tests ejecutados;
- skips;
- resultado completo.

No se ejecutaron pruebas desde GitHub ni desde esta intervención.

## 8. Criterio de cierre

La implementación y documentación de las etapas 1–5 están preparadas en la rama de trabajo. La revisión final también verificó que los siete nombres del catálogo se distinguen de nombres desconocidos y que los seis todavía no implementados se rechazan con `OPERATION_DENIED`. La etapa solo se considera validada e integrable en la rama base después de que el propietario ejecute las pruebas en Debian y se revisen sus resultados.
