# Contrato de contexto de operación

`OperationContext` representa el contexto explícito e inmutable asociado a una operación de Atlas.

## Campos

- `request_id`: identificador de la solicitud.
- `correlation_id`: identificador para relacionar operaciones y eventos.
- `actor`: instancia de `Identity` que representa al actor que ejecuta la operación.
- `user_id`: usuario al que pertenece o en cuyo contexto se realiza la operación.
- `origin`: origen de la solicitud.
- `delegation`: modalidad de delegación (`delegated` o `independent`); `None` representa un valor desconocido o no establecido.
- `project_id`: proyecto asociado, opcional.
- `environment`: entorno asociado, opcional.
- `purpose`: propósito declarado de la operación.
- `classification`: clasificación de la operación.
- `created_at`: instante de creación, obligatorio y expresado en UTC.

## Validaciones

El contrato exige:

- Identificadores y campos obligatorios no vacíos.
- `actor` debe ser una instancia válida de `Identity`.
- `delegation` debe ser una modalidad válida o `None`.
- `project_id` y `environment`, cuando están presentes, no pueden estar vacíos.
- `created_at` debe ser un `datetime` con zona horaria y desplazamiento UTC igual a cero.

## Seguridad

El contexto permite atribuir, correlacionar y describir una operación.

**El contexto no concede permisos por sí mismo.**

La autorización corresponde a la frontera de autorización de Atlas. La presencia de un proyecto o entorno en el contexto no demuestra por sí sola que el actor tenga acceso a ellos.
