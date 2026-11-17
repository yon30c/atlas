# F2.3 — Frontera de autorización, revisión y ejecución de workspace

> Estado: contratos de evidencia/puerto implementados; validación local pendiente. No hay emisor CAM general, aprobación ni ejecución integrada.
> Fecha: 16 de noviembre de 2026.
> Rama: `feature/terminal-commands`.

## 1. Objetivo

Definir cómo una propuesta `workspace.list` o `workspace.read` pasa de plan a operación ejecutable sin convertir al modelo, al chat ni a una confirmación informal en autoridad de seguridad.

Este diseño cubre el primer flujo local de prueba. No conecta todavía el flujo al runtime conversacional, a `cli.py`, al Broker ni a un ejecutor general.

## 2. Tres decisiones distintas

El flujo debe conservar tres conceptos independientes:

1. **Revisión del plan:** el propietario confirma que Atlas entendió correctamente la tarea y que desea continuar con esos parámetros. Esta confirmación expresa intención; no concede permisos.
2. **Autorización CAM:** CAM determina si la identidad autenticada puede realizar la acción exacta sobre el recurso exacto, dentro del proyecto y entorno correspondientes. Un `DENY` nunca puede convertirse en permiso mediante confirmación humana.
3. **Aprobación de seguridad:** cuando la política de CAM devuelve `REQUIRE_APPROVAL`, se necesita una aprobación válida emitida por el mecanismo de autoridad humana correspondiente. El texto "sí" en una conversación no es, por sí solo, evidencia autenticada de esa aprobación.

La ejecución solo puede considerarse admisible cuando la autorización vigente permite la operación y se han satisfecho todas las aprobaciones requeridas por la política.

## 3. Hallazgos de implementación existente

- `AuthorizationEvaluator` evalúa `AuthorizationRequest` contra Grants explícitos y compara actor, propietario, proyecto, entorno, tipo de recurso, ID exacto, acción y vigencia.
- `AuthorizationEvaluation` es un resultado interno. Su `ALLOW` conserva el Grant que coincidió, pero el propio contrato advierte que no constituye autorización pública.
- `AuthorizationPort.evaluate` recibe `AuthorizationRequest` y devuelve `AuthorizationResult`.
- `AuthorizationResult` exige un `AuthorizationSnapshot` de Memory cuando la decisión es `ALLOW`. Ese snapshot está diseñado para lecturas protegidas de Memory, no para operaciones generales de workspace.
- `MemoryAuthorizationService` es una política específica de lectura de Memory y no debe reutilizarse para autorizar workspace.
- No se encontró un puerto/servicio general de Approval Manager conectado a este flujo.
- `OperationContext` transporta actor, usuario, proyecto, entorno, origen y propósito, pero permite que `project_id` y `environment` estén ausentes. Un flujo protegido debe resolverlos de forma confiable y fallar cerrado cuando sean obligatorios.

**Conclusión:** no conectar directamente `AuthorizationPort` ni `MemoryAuthorizationService` al flujo workspace. Tampoco llamar a `AuthorizationEvaluation(ALLOW)` una autorización pública.

## 4. Identidad de la operación

La operación sometida a revisión/autorización debe quedar ligada a una representación inmutable que incluya, como mínimo:

- identificador del plan y del paso;
- capacidad exacta: `workspace.list` o `workspace.read`;
- workspace ID como recurso exacto;
- acción CAM estable y explícita;
- propietario/tenant del recurso resuelto por configuración confiable;
- actor autenticado y usuario contextual, sin asumir que son equivalentes;
- proyecto y entorno resueltos por autoridad confiable;
- parámetros completos y normalizados;
- referencia a la solicitud y correlación;
- huella determinista del contenido operativo.

La huella debe cubrir todos los campos que cambian el significado o alcance de la operación. No debe incluir texto descriptivo generado por el modelo si ese texto no afecta a la operación. Cambiar capacidad, workspace, parámetros, actor, proyecto o entorno invalida la revisión y cualquier aprobación anterior.

La serialización canónica y el algoritmo de huella se definirán en el contrato de implementación; no se aceptará usar `repr()`, orden de diccionarios accidental ni texto libre como identidad de operación.

## 5. Reglas de decisión

| CAM | Revisión del plan | Aprobación requerida | Resultado |
|---|---|---|---|
| DENY | cualquiera | cualquiera | Bloqueado |
| REQUIRE_APPROVAL | confirmada | ausente | Pendiente; no ejecutar |
| REQUIRE_APPROVAL | confirmada | válida y vigente | Puede continuar solo si CAM confirma la autorización aplicable |
| ALLOW | no confirmada | no requerida | Esperar revisión |
| ALLOW | confirmada | no requerida | Puede continuar |
| ALLOW | confirmada | requerida por política adicional | Esperar aprobación válida |

La aprobación no crea ni modifica Grants, no amplía alcance y no puede revocar un `DENY`. Una aprobación caducada, revocada, reutilizada, emitida para otra huella o no verificable equivale a no aprobada.

La autorización se debe comprobar de nuevo inmediatamente antes de ejecutar. Una decisión anterior no se conserva como permiso indefinido.

## 6. Frontera de implementación propuesta

Antes de integrar el flujo se necesitan contratos compatibles con operaciones generales, sin acoplarlos al snapshot de Memory:

- una solicitud tipada de autorización de operación, basada en `OperationContext` y recurso/acción exactos;
- una decisión pública de CAM cuyo `ALLOW` incluya evidencia verificable específica de operación, no un booleano ni un objeto de Memory;
- un puerto de verificación/consumo de aprobación humana si CAM exige aprobación;
- una solicitud de ejecución inmutable ligada a la huella revisada y autorizada;
- un gate de aplicación que falle cerrado ante puerto ausente, error, respuesta mal formada, contexto incompleto o evidencia no coincidente.

La implementación debe reutilizar la política CAM y el modelo de Grants existentes donde sean compatibles. Si el contrato público actual impide expresar una autorización general, se deberá extender/evolucionar CAM de forma explícita y con pruebas de regresión; no crear un segundo motor de permisos paralelo.

Para el primer entorno de prueba pueden inyectarse dobles de prueba de los puertos, claramente confinados a pruebas unitarias. Un fake que devuelve ALLOW sirve para probar la orquestación, pero no constituye autorización real ni habilita la consola o el runtime.

## 7. Límites de alcance

F2.3 no implementa todavía:

- un Approval Manager de producción;
- autenticación interactiva nueva;
- emisión o modificación de Grants;
- autorización genérica productiva;
- ejecución desde el chat o la consola;
- escritura de archivos, shell o acceso al sistema de archivos fuera del workspace configurado;
- integración con Scheduler, Broker o Skills.

El primer ejecutor seguirá limitado a `workspace.list` y `workspace.read` sobre workspaces configurados localmente. `workspace.read` solo aceptará rutas relativas normalizadas, archivos regulares UTF-8 y un límite de tamaño; no seguirá symlinks ni aceptará rutas arbitrarias fuera del workspace. Ninguna de estas capacidades está conectada aún al runtime.

## 8. Pruebas de aceptación para el siguiente incremento

1. Una propuesta de Gemma nunca puede autorizarse a sí misma.
2. La confirmación de revisión no altera una decisión CAM.
3. `DENY` bloquea incluso con confirmación humana.
4. `REQUIRE_APPROVAL` bloquea si no hay aprobación verificable.
5. Una aprobación ligada a otro plan, paso, actor, workspace, proyecto, entorno o conjunto de parámetros no coincide.
6. Alterar un parámetro después de revisar invalida la revisión/aprobación.
7. Un resultado CAM mal formado, ausente o no verificable falla cerrado.
8. Un contexto sin los atributos obligatorios falla cerrado.
9. Una autorización expirada o revocada no permite continuar.
10. Una aprobación no puede reutilizarse si el contrato la define como de un solo uso.
11. El fake de autorización solo se usa en pruebas y no se incorpora a la composición de CLI.
12. La operación no ejecuta nada durante la revisión ni durante la autorización.

## 9. F2.3.1 — Contrato inicial implementado

Se añadieron, sin modificar el contrato histórico de Memory:

- `src/atlas/authorization/operation_models.py`
  - `OperationAuthorizationEvidence`: claims ligados a request ID, actor y revisión, proyecto, entorno, acción, recurso exacto, propietario, Grant/revisión, ventana temporal e issuer.
  - `matches(request)`: comprueba la correspondencia exacta con `AuthorizationRequest`.
  - `is_current_at(now)`: comprueba únicamente la ventana temporal.
  - `OperationAuthorizationResult`: `ALLOW` requiere evidencia de operación; `DENY` y `REQUIRE_APPROVAL` no pueden transportarla.
- `src/atlas/ports/operation_authorization.py`
  - `OperationAuthorizationPort.authorize_operation(request, now)`.
- `tests/unit/test_operation_authorization_contracts.py`
  - Pruebas de validación, inmutabilidad, correspondencia exacta, contexto, revisiones y ventana temporal.

**Limitación deliberada:** los claims son datos estructurados, no una firma ni prueba de autenticidad. `matches()` y `is_current_at()` no comprueban emisor, revocación actual del Grant, revisión vigente de proyecto/entorno ni consumo de aprobación. El puerto todavía no tiene un adaptador de producción. No se ha conectado al runtime.

## 10. Estado del Ciclo 1 y próximo paso

**Ciclo 1 de lectura validado por el propietario:** suite completa de 1,157 tests en 9.853 s, todos OK; `python -m compileall -q src tests` también pasó. `workspace.list` y `workspace.read` tienen adaptadores/servicios de lectura y catálogo declarativo, pero permanecen desconectados del runtime.

El Ciclo 2 implementa el protocolo de archivos descrito en [assistant-workspace-write-protocol.md](assistant-workspace-write-protocol.md): staging durable, commit explícito, hash esperado para actualizaciones y evaluación de recuperación de solo lectura. **Validado por el propietario con la suite completa: 1,182 tests en 9.769 s, todos OK.** La escritura no se añadió al catálogo ni se conectó al runtime. El protocolo no sustituye CAM, fencing ni aprobación humana, y no afirma atomicidad entre SQLite y el sistema de archivos.


## 11. F2.3.2 — Servicio de verificación de evidencia

Se añadieron:

- `atlas.ports.operation_authorization_verifier.OperationAuthorizationEvidenceVerifierPort`: puerto confiable. Su implementación debe validar issuer/decisión auténticos, estado y revisión actual del actor, Grant exacto y su revisión/revocación/vigencia, y estado/revisión de proyecto y entorno.
- `atlas.authorization.operation_verification.OperationAuthorizationEvidenceVerificationService`: valida localmente la correspondencia de claims y la ventana temporal antes de delegar en el verificador confiable.
- Resultado explícito: `VERIFIED`, `DENIED` o `UNAVAILABLE`. Excepciones del verificador producen `UNAVAILABLE`; respuestas distintas de `True` producen `DENIED`.
- `VERIFIED` no es una orden ni una autorización de ejecución por sí sola. No se crea ejecutor ni se conecta a CLI/runtime.
- Pruebas: correspondencia alterada, expiración, evidencia aún no vigente, denegación autoritativa, fallo del verificador, respuesta mal formada e inputs inválidos.

**Límite:** todavía no hay implementación concreta del puerto confiable. En particular, no se afirma que una lectura puntual de Grant sea suficiente para cerrar carreras de revocación concurrente. Para ejecución con efectos se requerirá una garantía de fencing/consistencia equivalente a la exigida por los contratos de consistencia existentes.


## 12. F2.3.3a — Binding explícito de revisiones de autoridad

La inspección del modelo `Grant`, `AuthorizationEvaluator`, `MemoryMetadataResolver` y los puertos de metadatos reveló que la evidencia general necesitaba declarar también las revisiones de proyecto y entorno. Se añadieron `project_revision` y `environment_revision` como enteros positivos obligatorios en `OperationAuthorizationEvidence`.

Ahora los claims declaran las revisiones de:
- identidad del actor;
- Grant;
- proyecto;
- entorno.

Las pruebas comprueban que las dos revisiones nuevas sean positivas, enteras y no booleanas. Los verificadores confiables deberán comparar estos valores con las fuentes canónicas actuales.

**Límite:** esta ampliación no demuestra que las revisiones estén actuales ni elimina carreras concurrentes. El adaptador de verificación y la garantía de fencing siguen pendientes.


## 13. F2.3.3b — Inspección de consistencia y decisión de integración

La suite local reportada por el propietario valida F2.3.3a con 925/925 pruebas.

La inspección de la rama confirma que existen piezas reutilizables, pero todavía no una autoridad única operativa que permita implementar de forma honesta un verificador genérico de operaciones:

- `RevisionValidationPort` y `RevisionValidationResult` están ligados a `AuthorizationSnapshot` de Memory, `AuthorizationRevisionSet` y `ConsistencyPosition`. Su contrato exige invalidation-first y revalidación del head dentro de la misma `SQLiteUnitOfWork`, pero no existe adaptador que demuestre esa garantía. No se reutilizarán como si fueran un verificador genérico de workspace.
- `GrantRepository` ofrece `get/create/update/list_by_owner`; no impone por sí mismo invalidación durable ni fencing alrededor de cambios.
- `SQLiteIdentityAuthority` proporciona CAS de revisión para estado de identidad en SQLite, pero declara explícitamente que no implementa autorización, recuperación ni coordinación de invalidación.
- `AuthorityChangeCoordinatorPort` define la coordinación de invalidación/fencing/cambio/reconciliación, pero no se encontró implementación concreta en esta rama.
- `SQLiteAuthorityChangeStore` persiste reservas e idempotencia. Su propio contrato excluye calcular admisiones, aplicar fencing, mutar fuentes y reconciliar; no implementa el coordinador.
- `GrantRevocation` ya define una orquestación de revocación con prueba one-shot y coordinador inyectado, pero no demuestra que la composición durable completa esté disponible para validar toda operación de lectura.

**Decisión:** no crear un adaptador que combine lecturas puntuales de identidad, Grant, proyecto y entorno y las presente como autorización segura. Tampoco reutilizar el Recovery Gate o la autoridad de Memory por conveniencia: sus contratos actuales son específicos y la implementación durable está incompleta.

**Siguiente incremento recomendado:** definir una frontera común de admisión/validación de operaciones que esté ligada a una posición de consistencia y que se ejecute dentro de la misma UoW que el coordinador autoritativo. Antes de implementar ese adaptador, debe cerrarse la implementación real del coordinador de invalidación/fencing o limitar explícitamente la prueba a un perfil local sin efectos y sin afirmar garantías de revocación concurrente.

No se ha creado adaptador, no se ha conectado el verificador a SQLite y no se ha habilitado ejecución.


## 14. F2.3.4 — Frontera de consistencia común

La decisión completa se registra en [assistant-operation-consistency-boundary.md](assistant-operation-consistency-boundary.md). La evidencia verificada no basta: hace falta una admisión exacta, ligada a una posición de consistencia y coordinada con invalidación/fencing.

No se reutilizará `RevisionValidationPort` como verificador genérico: pertenece a Memory y su snapshot/posición tienen semántica específica. `SQLiteUnitOfWork` solo ofrece serialización suficiente si todas las fuentes relevantes participan en la misma base y transacción, sin caminos de mutación alternativos.

El primer perfil propuesto es read-only (`workspace.list` y `workspace.read`). Escrituras y runtime siguen desconectados. F2.3.5 inspeccionará la persistencia y composición real de Identity, Grant, Project y Environment antes de implementar el coordinador.


## 15. F2.3.5 — Inventario de persistencia

La inspección confirma que la composición actual no permite una transacción compartida entre Identity, Grant, Project, Environment y journal. Identity crea su propia SQLiteDatabase y cambia estado mediante CAS directo; Grant carece de adaptador SQLite concreto, su UoW cubre solo Grant/renovaciones y emisión escribe directo; Project/Environment solo tienen contratos de metadatos bajo Memory; journal y store de cambios de autoridad no están conectados a esas fuentes.

Por tanto, no hay coordinador de invalidación/fencing que pueda cerrar las carreras de autorización. El siguiente paso requiere decidir si se construye una composición canónica local con las cuatro fuentes y se migran todos los caminos de mutación, o si se aplaza CAM integrado para el primer perfil read-only. No se ha conectado el runtime.

## 11. Ciclo 3.1 — Gate CAM local para capacidades de lectura

Se añade `WorkspaceCapabilityExecutionService` para ejecutar únicamente `workspace.list` y `workspace.read` sobre el workspace configurado. El servicio exige un plan de un paso, coincidencia exacta entre intención y paso, confirmación explícita de revisión y riesgo `READ_ONLY`. La confirmación expresa intención humana; no altera la decisión CAM.

Antes de leer/listar, el servicio abre `SQLiteLocalAuthorityUnitOfWork` (`BEGIN IMMEDIATE`), compara el actor completo con la Identity canónica obtenida mediante `context.user_id`, valida proyecto y entorno activos y evalúa el Grant exacto con `AuthorizationEvaluator`. El propietario del workspace en este primer perfil es el UserId canónico de la sesión. El ID de un archivo se serializa como JSON canónico `[workspace_id, path]`, evitando colisiones entre workspace y ruta. La lectura/listado del filesystem se ejecuta antes de cerrar la UoW.

Se corrige `SQLiteProjectEnvironmentRepository.get_environment()` para utilizar `_read_connection()`, respetando la conexión transaccional inyectada. Se añade una prueba que comprueba visibilidad de una revisión no confirmada dentro de la UoW y rollback exterior.

**Límites:** esta implementación reutiliza el evaluador CAM y la autoridad SQLite local, pero no crea un adaptador genérico de `OperationAuthorizationPort`, no emite evidencia criptográfica, no implementa Approval Manager ni coordinador distribuido. `REQUIRE_APPROVAL` no permite continuar. No se conecta a CLI/runtime y no expone escritura. **VALIDADO por el propietario: suite completa de 1,194 tests en 9.318 s, todos OK.**

## 12. Requisito para el Ciclo 3.2 — contexto confiable de consola

La consola actual usa `LocalConsoleRequestFactory`, que fabrica `Identity` sintética (`local-user:<os-user>`), `user_id` no canónico y `project_id=None`. Ese contexto no puede ser elevado a una identidad CAM válida ni debe mapearse automáticamente a un UserId existente. Antes de conectar el runtime se necesita un bootstrap explícito del propietario, una relación estable y verificable entre la sesión local y la identidad canónica, proyecto/entorno seleccionados desde configuración confiable y un registro explícito de workspaces/owners.

Hasta completar ese paso, el servicio de ejecución permanece como caso de uso aislado, con pruebas unitarias añadidas pero pendientes de ejecución local; no se altera la composición de `cli.py`.
