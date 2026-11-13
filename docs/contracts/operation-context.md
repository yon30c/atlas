# Contrato de contexto de operación

## 1. Propósito

`OperationContext` representa el contexto explícito e inmutable asociado a una operación de Atlas.

Su función es conservar información suficiente para identificar al actor que ejecuta una operación, relacionarla con un usuario y un origen, declarar su propósito y clasificación, y mantener la correlación con otras operaciones y eventos.

El contexto permite atribuir y describir una operación. No constituye por sí mismo una credencial, una prueba de autenticación ni una autorización.

## 2. Modelo de datos

El modelo actual contiene los siguientes campos:

| Campo | Tipo lógico | Descripción |
|---|---|---|
| `request_id` | `string` | Identificador de la solicitud. |
| `correlation_id` | `string` | Identificador utilizado para relacionar operaciones y eventos. |
| `actor` | `Identity` | Identidad que representa al actor ejecutor de la operación. |
| `user_id` | `string` | Identificador del usuario al que pertenece o en cuyo contexto se realiza la operación. |
| `origin` | `string` | Origen declarado de la solicitud. |
| `delegation` | `DelegationMode \| None` | Modalidad de delegación declarada, cuando corresponda. |
| `project_id` | `string \| None` | Identificador del proyecto asociado, cuando corresponda. |
| `environment` | `string \| None` | Identificador del entorno asociado, cuando corresponda. |
| `purpose` | `string` | Propósito declarado de la operación. |
| `classification` | `string` | Clasificación declarada para la operación. |
| `created_at` | `datetime` | Instante de creación del contexto, expresado en UTC. |

Este contrato describe el modelo lógico actual. No establece formatos físicos, catálogos ni mecanismos de autenticación que todavía no hayan sido definidos.

## 3. Actor y usuario contextual

`actor` y `user_id` representan conceptos diferentes y no deben tratarse como equivalentes.

### 3.1. Actor

`actor` identifica la identidad que ejecuta la operación.

Puede representar una identidad de tipo `USER`, `AGENT`, `SERVICE`, `WATCHER` o `SYSTEM`, conforme al contrato de identidad.

El actor debe ser una instancia válida de `Identity`.

El estado de la identidad y su participación en una operación protegida deben evaluarse conforme a las reglas de identidad y autorización. La existencia de una instancia `Identity` en el contexto no concede permisos.

### 3.2. Usuario contextual

`user_id` identifica al usuario al que pertenece o en cuyo contexto se realiza la operación.

Puede ser diferente de `actor.identity_id`. Por ejemplo, un agente puede ejecutar una operación dentro del contexto de un usuario.

La presencia de un `user_id` no demuestra que ese usuario haya autenticado la solicitud, que haya autorizado la operación o que haya concedido una delegación.

La relación entre el actor, el usuario contextual y la identidad autenticada debe verificarse mediante los mecanismos de autenticación y autorización correspondientes.

### 3.3. Separación de responsabilidades

El contexto no sustituye la identidad autenticada ni la evidencia de autenticación.

La identidad autenticada, el actor efectivo, el origen y la delegación son conceptos distintos. Cuando una operación requiera comprobar su correspondencia, esa comprobación debe realizarse en la frontera de seguridad correspondiente.

## 4. Delegación

El campo `delegation` registra la modalidad de delegación declarada para la operación.

Los valores admitidos por el modelo son:

- `DELEGATED` (`delegated`): el actor actúa en nombre del usuario dentro de los permisos y límites expresamente concedidos.
- `INDEPENDENT` (`independent`): el actor actúa únicamente bajo su propia identidad y autoridad.

La delegación debe ser explícita, verificable y limitada. No amplía los permisos del actor ni sustituye la evaluación de CAM.

### 4.1. Valor `None`

El modelo permite que `delegation` sea `None`.

Este valor significa que el contexto no registra una modalidad de delegación.

`None` no debe interpretarse automáticamente como:

- `INDEPENDENT`.
- Una operación directa del propietario.
- Una delegación implícitamente concedida.
- Evidencia de que no se necesita autorización.

Cuando una operación requiera una modalidad de delegación explícita, un valor `None` no satisface ese requisito.

La política de cada operación determina si la ausencia de modalidad es admisible. No se debe inferir una modalidad a partir de `actor`, `user_id`, `origin` u otros campos.

### 4.2. Límites de autoridad

La delegación no concede por sí misma permisos de ejecución. Las operaciones protegidas continúan sujetas a CAM y a los Grants correspondientes.

Las decisiones sobre aprobación, rechazo y olvido de memorias permanecen bajo autoridad exclusiva y no delegable del propietario, conforme a los contratos de arquitectura y memoria.

## 5. Proyecto y entorno

`project_id` y `environment` identifican el ámbito de proyecto y entorno asociado a una operación, cuando corresponda.

Ambos campos pueden ser `None` en el modelo actual. Cuando contienen un valor, este no puede ser una cadena vacía o compuesta únicamente por espacios.

Su ausencia no significa que la operación tenga alcance global.

### 5.1. Proyecto

Los requisitos de `project_id` dependen del scope y de la operación correspondiente.

Para operaciones sobre memoria:

- En memoria `PRIVATE`, la ausencia de `project_id` es válida únicamente cuando el scope privado está declarado explícitamente.
- En memoria `PROJECT`, `project_id` debe estar presente, ser válido y coincidir con el proyecto asociado a la memoria.
- Un proyecto ausente, ambiguo o inconsistente no puede interpretarse como autorización global ni como acceso a otros proyectos.

El scope pertenece al recurso o a la propuesta correspondiente. No debe inferirse únicamente a partir de `OperationContext.project_id`.

### 5.2. Entorno

`environment` identifica el entorno asociado a la operación cuando corresponda.

La obligatoriedad, validez y coincidencia del entorno se determinan mediante la política específica de la operación y sus controles de autorización.

La presencia de un identificador de entorno no demuestra que el actor tenga acceso a él.

### 5.3. Validación del alcance

El servicio responsable de una operación debe comprobar que el contexto contiene los datos de alcance requeridos y que estos coinciden con el recurso y la autorización evaluados.

La validación estructural de `OperationContext` no sustituye estas comprobaciones.

## 6. Origen, propósito y clasificación

### 6.1. `origin`

Identifica el origen declarado de la solicitud.

Permite conservar información de procedencia y atribución. No demuestra por sí solo la identidad autenticada del origen ni concede permisos.

### 6.2. `purpose`

Describe el propósito declarado de la operación.

Debe permitir comprender por qué se solicita una operación, pero su contenido no constituye una autorización ni sustituye las restricciones de la política aplicable.

### 6.3. `classification`

Registra la clasificación declarada para la operación.

El modelo actual exige un valor no vacío, pero no implementa un catálogo ni valida categorías concretas.

La clasificación y sus reglas de propagación deben respetar el catálogo y las políticas que Atlas defina. No se deben inventar categorías ni inferir niveles de acceso a partir de una cadena declarada.

## 7. Identificadores y correlación

### 7.1. `request_id`

Identifica la solicitud asociada al contexto.

El modelo actual exige que sea una cadena no vacía. No establece por sí solo un formato, un mecanismo de generación ni una garantía de unicidad.

### 7.2. `correlation_id`

Permite relacionar operaciones y eventos que pertenecen a una misma secuencia o contexto de trabajo.

Los eventos derivados deben conservar la correlación que corresponda, de acuerdo con las reglas de propagación del flujo.

El identificador de correlación no sustituye la identidad de una solicitud, un evento, una tarea o un recurso.

### 7.3. Límites actuales

La validación del modelo no garantiza:

- Unicidad global de los identificadores.
- Ausencia de colisiones.
- Generación segura.
- Propagación automática entre operaciones.
- Idempotencia de solicitudes o eventos.

Estas garantías solo podrán exigirse cuando se definan explícitamente para el mecanismo u operación correspondiente.

## 8. Tiempo e inmutabilidad

### 8.1. `created_at`

Representa el instante de creación del contexto.

Debe ser un objeto `datetime` con información de zona horaria y desplazamiento UTC igual a cero.

El modelo no acepta fechas sin zona horaria ni fechas con un desplazamiento distinto de UTC.

`created_at` no representa necesariamente el momento de autorización, inicio, finalización o persistencia de la operación.

### 8.2. Inmutabilidad

`OperationContext` es un modelo inmutable después de su creación.

La implementación utiliza una estructura de datos congelada. Sus campos representan datos del contexto y no deben modificarse durante el ciclo de vida de la operación.

Una operación posterior que necesite un contexto diferente debe recibir un contexto nuevo, sin alterar retroactivamente el contexto original.

## 9. Seguridad y autorización

El contexto permite conservar y transmitir información necesaria para evaluar una operación, pero no concede autoridad.

Se aplican las siguientes reglas:

1. La identidad del actor debe ser válida conforme al contrato de identidad.
2. La identidad autenticada debe verificarse mediante el mecanismo de autenticación correspondiente; no basta con declarar un `actor` en el contexto.
3. La relación entre `actor` y `user_id` debe verificarse cuando la operación lo requiera.
4. La delegación debe ser explícita y verificable cuando la política de la operación la exija.
5. El proyecto y el entorno deben validarse conforme al alcance del recurso y de la operación.
6. Los campos `origin`, `purpose` y `classification` no conceden permisos.
7. Las operaciones protegidas deben pasar por CAM.
8. La ausencia de información obligatoria, una discrepancia de alcance o la imposibilidad de verificar una condición de autorización debe impedir la operación protegida.

La evaluación de permisos corresponde a CAM y no debe implementarse como una inferencia basada únicamente en los campos del contexto.

## 10. Validaciones del modelo actual

La implementación actual de `OperationContext` exige:

- `request_id`, `correlation_id`, `user_id`, `origin`, `purpose` y `classification` deben ser cadenas no vacías.
- `actor` debe ser una instancia de `Identity`.
- `delegation` debe ser una instancia válida de `DelegationMode` o `None`.
- `project_id` puede ser `None`; si está presente, debe ser una cadena no vacía.
- `environment` puede ser `None`; si está presente, debe ser una cadena no vacía.
- `created_at` debe ser un `datetime` con zona horaria y desplazamiento UTC igual a cero.

Estas validaciones son estructurales. No implementan por sí solas autenticación, autorización, comprobación de existencia de proyectos, validación de entornos ni verificación de delegaciones.

Los requisitos adicionales deben ser aplicados por el servicio, política o frontera responsable de la operación.

## 11. Errores de contrato

Los valores que incumplan las validaciones estructurales del modelo deben producir `ContractError`, conforme al contrato de errores de Atlas.

Una discrepancia de autorización o de alcance no debe confundirse con un error estructural del contexto. Debe resolverse mediante los controles de autorización correspondientes.

## 12. Decisiones técnicas pendientes

Las siguientes decisiones requieren especificación adicional:

- **Identificadores:** formato, longitud, normalización, generación, unicidad y alcance de unicidad de `request_id` y `correlation_id`.
- **Propagación:** reglas para conservar o crear identificadores de correlación en operaciones derivadas, tareas y eventos.
- **Delegación:** evidencia verificable de la delegación, referencia al Grant y validación de vigencia, alcance y revocación.
- **Modalidad inicial:** elección de la modalidad inicial de delegación de Atlas, que continúa pendiente en el contrato principal.
- **Usuario contextual:** reglas generales para vincular `user_id` con el principal autenticado y con el actor, según cada tipo de operación.
- **Origen:** catálogo, formato y validación de los valores de `origin`.
- **Propósito:** catálogo o mecanismo de validación de los valores de `purpose`, si se requiere.
- **Clasificación:** catálogo, jerarquía y reglas de propagación de `classification`.
- **Proyecto y entorno:** mecanismos para verificar existencia, vigencia y correspondencia con los recursos.
- **Contextos derivados:** reglas para crear nuevos contextos a partir de operaciones existentes sin alterar la atribución ni ampliar autoridad.
- **Evidencia temporal:** relación entre `created_at` y los registros temporales de autorización, eventos y auditoría.

### 12.1. Límites de las decisiones pendientes

Estas decisiones técnicas no reabren ni modifican las políticas arquitectónicas aprobadas:

- El contexto no concede permisos.
- La identidad autenticada, el actor, el origen y la delegación son conceptos distintos.
- La delegación debe ser explícita, verificable y limitada.
- La ausencia de `project_id` no implica alcance global.
- El acceso a memoria privada y de proyecto debe respetar las reglas explícitas de scope y autorización.
- Las operaciones protegidas deben pasar por CAM.
- Ningún componente puede utilizar el contexto para atribuirse permisos que no hayan sido concedidos.

Cualquier implementación posterior debe respetar estas reglas y no puede introducir capacidades incompatibles con ellas sin una revisión explícita del contrato arquitectónico.
