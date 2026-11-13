# Contrato de errores

## 1. Propósito

Este contrato define la semántica de los errores conocidos del núcleo de Atlas, sus condiciones de uso y las garantías que deben respetar los componentes y adaptadores.

Los errores permiten comunicar el resultado de una operación fallida sin debilitar la autorización, revelar información protegida ni comprometer la integridad de los recursos.

## 2. Jerarquía de errores

Todos los errores de dominio conocidos del núcleo derivan de `AtlasError`.

| Error | Semántica |
|---|---|
| `AtlasError` | Clase base de los errores conocidos del núcleo. |
| `ContractError` | Un valor, entrada, estado o resultado viola un contrato de dominio. |
| `AuthorizationError` | La identidad o la operación no dispone de la autorización requerida. |
| `NotFoundError` | El recurso no existe o no es visible para el solicitante. |
| `ConcurrencyError` | La operación encuentra un conflicto por modificación concurrente de un recurso. |

La jerarquía descrita corresponde a las clases existentes en `atlas.core.errors`.

No se presupone que todos los errores posibles del sistema deban convertirse en `AtlasError`. Los errores inesperados y los fallos internos no deben ocultarse mediante conversiones indiscriminadas.

## 3. Semántica de cada error

### 3.1 `AtlasError`

Es la clase base para identificar los errores conocidos del núcleo.

No representa por sí misma una causa específica ni sustituye la semántica de las clases derivadas.

Los componentes deben utilizar el tipo más específico que corresponda al fallo.

### 3.2 `ContractError`

Se utiliza cuando una entrada, valor, estado o resultado incumple las condiciones contractuales del dominio.

Ejemplos:

- Tipo de objeto incorrecto.
- Identificador obligatorio vacío o inválido.
- Valor fuera de las condiciones admitidas por el modelo.
- Estado incompatible con la operación solicitada.
- Identificador duplicado cuando el contrato exige unicidad.
- Resultado de repositorio que no corresponde al tipo esperado.

`ContractError` no debe utilizarse para representar una denegación de permisos ni un conflicto de concurrencia cuando existe una clase específica para esos casos.

### 3.3 `AuthorizationError`

Se utiliza cuando la operación no está autorizada bajo la identidad, contexto, delegación, permisos o políticas aplicables.

Ejemplos:

- Identidad suspendida o revocada.
- Actor distinto del requerido para una operación.
- Delegación ausente cuando es obligatoria.
- Grant inexistente, vencido o revocado cuando la operación requiere uno válido.
- Recurso fuera del alcance autorizado.
- Propietario distinto del requerido.

Una denegación no debe permitir eludir CAM ni revelar información protegida.

La presencia de un recurso o identificador en una solicitud nunca constituye autorización para acceder a él.

### 3.4 `NotFoundError`

Se utiliza cuando el recurso solicitado no existe o no puede ser mostrado al solicitante dentro de su ámbito autorizado.

La respuesta no debe permitir distinguir entre:

- Un recurso que realmente no existe.
- Un recurso cuya existencia está protegida frente al solicitante.

Esta regla evita utilizar los errores de búsqueda para descubrir recursos ajenos o protegidos.

`NotFoundError` no sustituye las validaciones de autorización que deben realizarse cuando la operación requiere comprobar permisos adicionales.

### 3.5 `ConcurrencyError`

Se utiliza cuando una operación detecta que el recurso o estado sobre el que pretendía trabajar fue modificado concurrentemente y ya no cumple la versión o condición esperada.

Ejemplos:

- Una actualización condicional por versión deja de ser válida.
- Otra transacción modifica el recurso antes de confirmar la operación.
- Una decisión concurrente cambia el estado de una solicitud antes de su aprobación o rechazo.

El conflicto debe impedir que la operación sobrescriba silenciosamente el cambio concurrente.

Cuando una operación involucra varios recursos o cambios relacionados, el fallo debe preservar las garantías de atomicidad y consistencia establecidas por su contrato.

Un `ConcurrencyError` no equivale a un error de autorización ni a una entrada inválida.

## 4. Reglas de selección

Los componentes deben utilizar la clase que represente la causa real del fallo:

1. Entrada o estado que viola el contrato: `ContractError`.
2. Operación no autorizada: `AuthorizationError`.
3. Recurso inexistente o no visible: `NotFoundError`.
4. Conflicto por modificación concurrente: `ConcurrencyError`.
5. Error conocido del núcleo sin una categoría más específica: `AtlasError`.

No se deben utilizar estas clases para convertir fallos inesperados en resultados aparentemente controlados.

## 5. Concurrencia y reintentos

Un conflicto de concurrencia no autoriza por sí mismo un reintento automático.

Antes de intentar nuevamente una operación, el componente responsable deberá:

1. Obtener el estado actual del recurso.
2. Verificar que el recurso continúa dentro del alcance autorizado.
3. Reevaluar las condiciones de la operación.
4. Confirmar que la operación puede repetirse sin duplicar efectos ni sobrescribir decisiones válidas.
5. Respetar los límites de reintentos y las políticas de recuperación aplicables.

Si no puede garantizarse la seguridad del reintento, la operación deberá permanecer fallida y requerir una nueva decisión o solicitud.

Los reintentos no pueden utilizarse para eludir autorización, controles de concurrencia o límites de ejecución.

## 6. Seguridad y exposición de información

Los errores no deben revelar:

- Contenido de memoria privada o de otros proyectos.
- Datos de recursos fuera del ámbito autorizado.
- Credenciales, tokens, secretos o material criptográfico.
- Detalles internos que permitan eludir controles de seguridad.
- Información sensible de otros usuarios o identidades.

Los mensajes internos pueden aportar contexto suficiente para diagnóstico, pero su exposición a interfaces externas deberá someterse a las reglas de clasificación, autorización y privacidad correspondientes.

La traducción de errores a respuestas externas no debe modificar su semántica de seguridad.

## 7. Adaptadores e infraestructura

Los adaptadores futuros deberán traducir los errores de infraestructura cuando sea necesario para preservar el contrato del núcleo.

La traducción deberá cumplir estas condiciones:

- No exponer detalles internos, secretos ni información sensible.
- No convertir indiscriminadamente todos los fallos en `AtlasError`.
- Preservar la distinción entre validación, autorización, inexistencia y concurrencia.
- No presentar un fallo de infraestructura como una operación completada.
- Mantener las garantías de consistencia y atomicidad del componente correspondiente.

La jerarquía concreta de errores de infraestructura y su traducción por adaptador quedan fuera de este contrato del núcleo.

## 8. Relación con autorización y contexto

Los errores no conceden permisos ni sustituyen las decisiones de CAM.

La existencia de un `OperationContext` válido no demuestra que una operación esté autorizada.

Las comprobaciones de identidad, delegación, proyecto, entorno, recurso y permisos deben realizarse en los límites de autorización correspondientes.

Los errores deben comunicar el resultado de esas comprobaciones sin alterar sus reglas.

## 9. Decisiones técnicas pendientes

Permanecen pendientes de definición durante el diseño de los adaptadores y las interfaces:

- Catálogo de códigos externos de error.
- Formato de respuestas de error por interfaz.
- Política de exposición de mensajes internos y externos.
- Correlación entre errores y eventos de auditoría.
- Clasificación y severidad de eventos asociados a fallos.
- Traducción de excepciones específicas de cada infraestructura.
- Política de reintentos por tipo de operación recuperable.

Estas decisiones no modifican la semántica de las clases existentes ni autorizan a eliminar sus distinciones.

## 10. Reglas aprobadas del contrato

1. Los errores conocidos del núcleo derivan de `AtlasError`.
2. Cada error debe representar una causa coherente con su semántica.
3. La denegación de autorización no puede revelar información protegida.
4. La inexistencia y la falta de visibilidad pueden compartir `NotFoundError`.
5. Los conflictos concurrentes deben impedir sobrescrituras silenciosas.
6. Los reintentos deben reevaluar estado y autorización.
7. Los adaptadores no pueden filtrar secretos ni convertir fallos inesperados en éxitos aparentes.
8. Ningún error sustituye los controles de autorización, aislamiento o consistencia de Atlas.

## 11. Referencias a CT-08

CT-08 complementa este contrato como matriz transversal; las resoluciones siguientes precisan su aplicación sin duplicar sus reglas:

- [CT-08 R08-09](consistency-matrix-ct-08.md#r08-09-errores-y-reevaluacion): Uso del catálogo CT-03 y reevaluación segura ante errores; la denegación, indisponibilidad o concurrencia no habilitan rutas alternativas.
