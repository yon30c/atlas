# ME-03K-C — Contratos tipados de ancla de confianza y verificación

**Estado:** contrato técnico de diseño con Trust Anchor opcional. El perfil local es el baseline actual; el perfil anclado queda postergado hasta la etapa final de Atlas. Este documento no implementa criptografía, persistencia ni transporte.  
**Rama:** `implementation/me-01-to-me-04-memory-engine`.  
**Dependencias:** ME-03K, ME-03K-A y ME-03K-B.

## 1. Propósito

ME-03K-B establece las garantías de persistencia, autenticidad, continuidad y anti-rollback. Este documento cierra las fronteras tipadas que permiten exigir esas garantías sin seleccionar un algoritmo, formato criptográfico, proveedor de claves, base de datos o transporte.

El adaptador no puede entregar al reducer un estado solo porque sea estructuralmente válido. Debe entregar un estado cuya autenticidad y continuidad hayan sido verificadas conforme al perfil declarado. El perfil local valida la continuidad disponible dentro del conjunto local, pero no demuestra que el head sea el último existente antes de una restauración; el perfil anclado añade verificación contra un Trust Anchor externo vigente.

## 2. Separación de responsabilidades

1. **Journal adapter:** persiste transiciones, checkpoints, claves idempotentes, tombstones y recibos; resuelve escrituras ambiguas.
2. **Trust-anchor provider (opcional):** cuando se habilite el perfil anclado, obtiene y actualiza monotónicamente el último estado durable confirmado fuera del dominio de rollback del journal/checkpoint. No es dependencia del perfil local.
3. **Checkpoint/recovery verifier:** valida autenticidad, continuidad interna, época, posición y proyección del checkpoint; cuando se usa el perfil anclado, valida además el ancla y anti-rollback.
4. **Receipt verifier:** valida autenticidad, emisor autorizado, claims, vigencia, revocación, replay y binding exacto.
5. **Reducer:** procesa únicamente un estado ya verificado. No autentica, no consulta anclas y no decide confianza criptográfica.
6. **Single recovery authority:** serializa las operaciones de lectura, egress, cierres, invalidaciones, recuperación y reapertura según ME-03K-B.

Ninguna de estas fronteras puede sustituir a otra. En particular, el journal no puede autoatestiguar que su propio último checkpoint es el más reciente.

## 3. Trust Anchor externo opcional

La implementación real del Trust Anchor queda postergada hasta la etapa final de Atlas. El baseline actual utiliza un único servidor y el perfil local. La existencia de los modelos/puertos tipados no obliga a desarrollar ni desplegar ahora el proveedor externo.

### 3.1 Modelo lógico (solo perfil anclado)

Cuando el perfil anclado esté habilitado, el ancla confiable debe representar, como mínimo:

- `anchor_id`: identificador opaco único;
- `consistency_domain_id`;
- `authority_epoch`;
- `maximum_committed_sequence`;
- `authenticated_state_commitment`: compromiso autenticado de la posición y estado;
- `issuer_id` y `key_reference`;
- `authentication_evidence` opaca que permite al verificador autenticar el propio ancla;
- `trust_policy_version`;
- `issued_at` y, si aplica, `valid_until`;
- `anchor_revision`: revisión monotónica del propio ancla.

El compromiso protege únicamente el estado de control del journal/checkpoint. No puede contener ni derivarse de contenido de memoria, fragmentos, payloads, embeddings, snippets o hashes de contenido.

### 3.2 Reglas de monotonicidad

- El ancla no puede retroceder de dominio, época, secuencia ni revisión.
- Una nueva época requiere un handoff autenticado y fencing demostrable de la autoridad anterior.
- Actualizar el ancla es una operación condicional sobre la revisión/posición anterior exacta.
- La misma actualización idempotente devuelve el mismo resultado.
- Una actualización incompatible para la misma revisión produce conflicto.
- Un backup restaurado no puede reemplazar ni reducir el ancla vigente.
- Si el proveedor de anclas no está disponible, el estado devuelto es desconocido y el gate permanece cerrado.
- No se permite inicializar silenciosamente un ancla nueva a partir de un journal restaurado. La inicialización requiere un procedimiento de bootstrap explícito y autenticado, fuera del flujo ordinario de recuperación.

### 3.3 Puerto requerido

El proveedor opcional, cuando se implemente, debe ofrecer operaciones equivalentes a:

- `load_current_anchor(domain_id) -> TrustAnchorReadResult`;
- `advance_anchor(TrustAnchorAdvanceRequest) -> TrustAnchorUpdateStatus`, donde la solicitud contiene el ancla previa completa y la nueva ancla autenticada. La revisión debe avanzar exactamente una unidad; dentro de una época la secuencia nunca retrocede y el commitment no cambia sin avanzar secuencia. El cambio de época solo puede ser +1, empezar en secuencia cero y aportar referencia explícita de handoff autenticado.

La lectura usa `TrustAnchorReadResult`: FOUND exige un ancla tipada; NOT_FOUND/UNKNOWN no pueden transportar un ancla. La actualización usa `TrustAnchorUpdateStatus` y distingue UPDATED, REPLAYED, CONFLICT y UNKNOWN. NOT_FOUND no autoriza crear un ancla automáticamente durante una recuperación.

## 4. Envelope autenticado de journal y checkpoint

Cada registro o checkpoint autenticado debe estar acompañado por un envelope que identifique:

- tipo de objeto y versión del envelope;
- dominio, época y posición;
- ID del registro/checkpoint;
- esquema de transición y versión del reducer/proyección;
- referencia autenticada al objeto anterior o checkpoint base;
- compromiso de la representación canónica completa;
- emisor y rol/autoridad autorizados;
- referencia de clave/material de confianza;
- identificador de política de confianza;
- instante de emisión y límites temporales cuando apliquen;
- evidencia de autenticación opaca para la implementación.

El envelope es metadato de autenticación, no contenido de memoria. No se prescribe su serialización física.

Un hash simple, una referencia opaca o un ID de recibo no constituye autenticación. El adaptador debe validar el mecanismo criptográfico concreto antes de aceptar el objeto.

## 5. Verificación de checkpoint y estado recuperado

### 5.1 Solicitud de verificación del perfil anclado

La solicitud debe identificar exactamente:

- dominio y época esperados;
- ancla externa leída y su revisión;
- checkpoint y posición que se pretenden recuperar;
- compromiso autenticado esperado;
- versión de esquema y reducer;
- referencia de continuidad;
- política de confianza y tiempo confiable de verificación.

### 5.2 Resultado verificado del perfil anclado

Solo el verificador puede producir un objeto interno `VerifiedConsistencyRecoveryState`, que contenga:

- el `ConsistencyRecoveryState` validado;
- identidad/revisión del ancla externa usada;
- dominio, época, secuencia y compromiso verificados;
- versión de política de confianza;
- identificador único de verificación;
- instante UTC de verificación;
- estado de continuidad completa.

El constructor/creación de este resultado debe permanecer dentro de la frontera del verificador/adaptador confiable. No debe aceptarse una instancia fabricada por un caller no confiable.

### 5.3 Condiciones de rechazo del perfil anclado del perfil anclado

El resultado debe ser UNKNOWN o REJECTED y no entregar estado al reducer si ocurre cualquiera de estas condiciones:

- ancla ausente, desconocida, antigua, no autenticada o no disponible en perfil anclado;
- checkpoint por debajo de la secuencia máxima del ancla;
- dominio o época distintos;
- compromiso o referencia de continuidad no coincidente;
- huecos, forks, truncamiento, reordenamiento o replay;
- versión de esquema/reducer no admitida;
- firma/MAC/evidencia inválida o clave desconocida/revocada;
- reloj confiable ausente o tiempo fuera de política;
- inventario de tombstones, idempotencia u operaciones activas incompleto;
- imposibilidad de demostrar que el estado restaurado es el último estado confirmado.

No se permite degradar a una validación estructural ni reconstruir scope, owner, generaciones o inventarios por inferencia.


### 5.4 Verificación del perfil local

El perfil local no requiere Trust Anchor. Su solicitud de verificación debe identificar dominio, época, posición esperada, checkpoint/proyección base, cadena local disponible, versiones de esquema/reducer, política de verificación local y tiempo UTC de evaluación. El verificador debe validar autenticidad disponible, estructura, secuencias, referencias, continuidad interna, inventarios, tombstones y operaciones no terminales.

Solo una verificación local satisfactoria puede producir un resultado tipado propio, por ejemplo `VerifiedLocalConsistencyRecoveryState`, que incluya el estado validado, dominio/época/head, compromiso local, identificador y emisor del verificador, política, instante UTC y el perfil explícito `local`. Este resultado MUST NOT incluir un Trust Anchor ficticio, ni reutilizar `VerifiedConsistencyRecoveryState` de perfil anclado, ni afirmar anti-rollback externo.

El perfil local debe rechazar corrupción, huecos, forks, referencias rotas, inventarios incompletos, schema/reducer no soportados y resultados ambiguos. Sin embargo, una cadena local internamente válida no permite demostrar que no se restauró un backup antiguo coherente. El resultado debe conservar explícitamente esa limitación para que no se confunda con una verificación anclada.

## 6. Contrato común de verificación de recibos

### 6.1 Contexto de confianza

Toda solicitud de verificación de recibo debe incluir:

- tipo de recibo esperado;
- dominio y época;
- operación, admisión, endpoint/ruta y generación esperados;
- secuencia o inventario exacto aplicable;
- referencia a la solicitud canónica;
- instante UTC de evaluación obtenido de fuente confiable;
- política de confianza y propósito de uso.

### 6.2 Claims autenticados mínimos

El envelope del recibo debe identificar:

- ID único y tipo/resultando terminal;
- dominio y época;
- operación y admisión cuando apliquen;
- endpoint/ruta cuando aplique;
- generación actual y generación anterior cercada cuando aplique;
- secuencia final o secuencia cercada cuando aplique;
- inventario exacto de rutas/admisiones cubiertas;
- emisor, rol/autoridad, referencia de clave y versión de política;
- emisión y validez temporal;
- binding a la solicitud canónica;
- evidencia de autenticación opaca.

El recibo global debe comprometer el conjunto exacto de recibos terminales ya verificados. Un contador, un subconjunto o una lista no autenticada no satisface el contrato.

### 6.3 Resultado de verificación

El verificador devuelve exactamente uno de:

- VERIFIED: evidencia autenticada, vigente, no revocada, no replayada y con binding exacto;
- REJECTED: evidencia inválida, no autorizada, revocada, expirada, replayada o incompatible;
- UNAVAILABLE: no pudo completar la verificación.

Solo VERIFIED produce el objeto tipado de evidencia verificada. REJECTED y UNAVAILABLE no pueden incluir evidencia aceptable. UNAVAILABLE nunca se interpreta como rechazo definitivo ni como permiso; mantiene la operación pendiente/cerrada.

### 6.4 Independencia y replay

- El finalizador no verifica ni autoaprueba su propio recibo.
- La identidad del emisor no basta: debe validarse su autorización para ese tipo de recibo, dominio, época y periodo.
- El verificador valida clave, política, vigencia, revocación y estado de compromiso.
- La deduplicación/consumo del recibo debe ser durable y atómica con la transición que lo consume.
- Un recibo verificado para una operación no puede reutilizarse en otra, aunque los campos parciales coincidan.
- La rotación de claves debe conservar material histórico suficiente para verificar recibos aún válidos; la revocación se aplica según una política explícita.
- Si no se puede determinar la validez histórica de una clave o recibo, se falla cerrado.

## 7. Resolución durable de operaciones ambiguas

El contrato de `ConsistencyJournalPort.resolve_operation` queda precisado así:

- La consulta se realiza bajo la misma autoridad serializable que confirma escrituras.
- La identidad consultada es `(domain_id, authority_epoch, operation_id, idempotency_key)`.
- El caller presenta la transición canónica esperada y la posición CAS original.
- COMMITTED_EXACT devuelve el commit original, su posición y el registro canónico persistido.
- NOT_COMMITTED solo se permite si la autoridad demuestra ausencia durable y continuidad íntegra hasta la posición actual.
- CONFLICT se devuelve ante reutilización incompatible de clave/operación, múltiples commits o transición distinta.
- UNKNOWN cubre indisponibilidad, falta de ancla, pérdida de continuidad, lectura no consistente o ausencia no demostrable.
- COMMITTED_EXACT no permite repetir la mutación; NOT_COMMITTED permite reintentar únicamente la misma solicitud canónica bajo CAS actualizado; CONFLICT/UNKNOWN bloquean.
- Las consultas eventualmente consistentes no pueden decidir egress, fencing, cierre o reapertura.

## 8. Integración con los puertos existentes

Los siguientes contratos deben alinearse antes de declarar ME-03K-B cerrado:

1. `ConsistencyJournalPort.load_verified_recovery_state` entrega un resultado tipado que identifica el perfil de verificación. En perfil anclado, VERIFIED contiene `VerifiedConsistencyRecoveryState` vinculado al Trust Anchor. En perfil local debe existir un resultado tipado distinto, sin campo ni afirmación de ancla, que exprese integridad/continuidad local y declare explícitamente que anti-rollback externo no está demostrado. `load_recovery_state` desnudo queda limitado a diagnóstico/migración y está prohibido en recuperación operativa.
2. `ConsistencyCheckpoint` debe referenciar el envelope autenticado y la versión de reducer/proyección. La referencia a ancla externa solo aplica al perfil anclado; `integrity_reference` nunca es prueba suficiente por sí sola.
3. `ConsistencyRecoveryState` es únicamente estructural. `VerifiedConsistencyRecoveryState` corresponde exclusivamente al perfil anclado y envuelve el estado junto con el ancla exacta, exigiendo coincidencia de dominio, época, secuencia y commitment. El perfil local utiliza un resultado tipado separado, sin ancla y sin afirmación anti-rollback. El reducer nunca crea esa confianza.
4. `TerminalReceiptVerifierPort` y `RecoveryCompletionVerifierPort` disponen de variantes trust-aware que reciben `ReceiptTrustContext`. El contexto fija tipo de recibo, dominio, época, operación, ID esperado obligatorio, claims de endpoint/admisión o inventarios globales, referencia canónica, política y tiempo UTC. `binds_terminal_request` y `binds_recovery_completion` permiten exigir coincidencia exacta del contexto con la solicitud/recibo. El verificador debe resolver la referencia canónica y comprobar el contenido semántico completo; la referencia por sí sola no es autenticación. La variante legacy se conserva solo para dobles de prueba/migración; no satisface conformidad de adaptador durable.
5. `ProtectedMemoryRecoveryAuthorityPort` sigue siendo una única implementación concreta compartida por Gateway y coordinadores. La verificación no crea una segunda autoridad de orden.
6. `reconcile_and_open_recovery_gate` debe consumir una evidencia verificada vinculada al cierre exacto y confirmar evento + apertura en una sola operación linealizable.
7. Los resultados ambiguos de cualquier operación atómica deben poder consultarse con identidad canónica exacta bajo esa misma autoridad.

## 9. Reloj, expiración y validez histórica

- El tiempo usado para verificar emisión, expiración y revocación debe proceder de una fuente confiable.
- El timestamp declarado por el recibo nunca es fuente de tiempo confiable.
- Los intervalos de validez son explícitos y no admiten gracia implícita.
- Si la política exige expiración y no existe `valid_until`, el recibo no se considera vigente.
- La verificación de un recibo histórico debe considerar el estado de la clave y la política aplicables a su emisión, además de revocaciones posteriores.
- Tiempo ausente, no UTC, retrocedido o no verificable produce UNAVAILABLE/UNKNOWN y no autoriza avanzar.

## 10. Decisiones que permanecen abiertas

La decisión de hacer Trust Anchor opcional y postergarlo hasta la etapa final está aprobada; no vuelve a estar pendiente. Este contrato no selecciona:

- algoritmo de firma/MAC, envelope físico ni canonicalización binaria;
- HSM/KMS, almacén de claves o proveedor de identidad de emisores;
- tecnología o ubicación física del ancla externa;
- mecanismo de consenso, transacción o almacenamiento;
- política operativa de retención de claves, backup y recuperación;
- topología, disponibilidad, RPO/RTO ni proceso de bootstrap.

Cada elección futura debe demostrar conformidad con estos contratos y K01–K07.

## 11. Estado de alineación en código

Se añadieron `src/atlas/memory/trust.py` y `src/atlas/ports/consistency_trust.py` con modelos tipados para ancla externa, resultados de lectura, CAS monotónico, envelope autenticado, solicitud y resultado de verificación de checkpoint, resultado de recuperación verificada y puertos provider-agnostic. El checkpoint base puede ser anterior al head externo, pero la verificación debe recorrer la cadena completa hasta la posición anclada. `ConsistencyJournalPort` ahora define `load_verified_recovery_state`; la carga estructural desnuda queda marcada solo para diagnóstico/migración. Los coordinadores de recuperación, finalización de admisiones y finalización global consumen exclusivamente el resultado VERIFIED y se bloquean ante REJECTED, UNAVAILABLE, excepción o resultado mal tipado. Los fakes de integración crean atestaciones de prueba explícitas; no simulan criptografía real.

Pruebas de contrato añadidas en `tests/unit/test_memory_trust_contracts.py` para bindings de dominio/época/política, rollback, expiración, checkpoint base/head, CAS del ancla, commitment y contexto de recibos terminales/globales. `JournalOperationResolution` ahora incluye la transición esperada y la transición persistida; COMMITTED_EXACT exige igualdad semántica exacta. Se añadió `tests/unit/test_memory_journal_operation_resolution.py` para cubrir resultados ambiguos y conflictos. Estas pruebas y las suites de coordinadores requieren ejecución/CI antes de declarar validada esta alineación. Se intentó CI en Python 3.10–3.13; los cuatro jobs terminaron en FAILURE en aproximadamente dos segundos, con runner_id=0 y sin pasos ejecutados. El segundo intento del run también terminó igual. Por tanto, no existe evidencia de que los tests hayan empezado ni de que el código haya fallado en tests; la validación permanece BLOQUEADA por la ejecución del runner. Se añadieron `TrustAwareTerminalReceiptVerifierPort`, `TrustAwareRecoveryCompletionVerifierPort` y `ReceiptTrustContextFactoryPort`. Los flujos de fencing, finalización de admisiones y finalización global construyen y validan `ReceiptTrustContext` antes de invocar exclusivamente los métodos trust-aware. Los coordinadores rechazan verificadores que solo implementen la interfaz legacy o una factoría de contexto incompleta. La factoría debe resolver `canonical_request_reference` desde el registro confiable de operaciones; el contexto debe coincidir exactamente con los claims, propósito e instante UTC. Los fakes de pruebas implementan esta frontera de forma determinista, pero no aportan autenticidad criptográfica ni conformidad durable. Las interfaces legacy se conservan únicamente para migración/dobles antiguos y no son aceptadas por estos coordinadores. La evidencia de autenticación del ancla es obligatoria en el modelo, pero todavía no existe implementación criptográfica que la valide.

La construcción de `VerifiedConsistencyRecoveryState` es una garantía de tipo dentro del proceso, no una barrera criptográfica frente a código arbitrario del mismo proceso. La procedencia auténtica depende de que solo el adaptador/verificador confiable produzca ese objeto y de que la composición de dependencias no permita inyección de un verificador no confiable.

## 12. Alineación pendiente para cierre integral

1. **Implementado en la frontera de coordinación:** propagar `ReceiptTrustContext` a ambos verificadores trust-aware y rechazar interfaces legacy en los coordinadores. Sigue pendiente una factoría durable que resuelva referencias canónicas desde la autoridad confiable.
2. Añadir pruebas negativas de emisor/clave desconocidos, firma inválida, revocación histórica, replay, timeout y canonicalización incompatible en el verificador de referencia/fakes.
3. Ejecutar las suites focalizadas y CI de Python 3.10–3.13; los modelos tipados por sí solos no prueban autenticidad.
4. Verificar que la autoridad durable consulta ancla, journal y estado idempotente bajo un mismo orden linealizable y no reabre el gate ante resultados ambiguos.

## 13. Criterios de cierre por perfil

El diseño del perfil local puede cerrarse cuando se definen y verifican sus garantías locales, su resultado tipado y sus limitaciones explícitas. El perfil anclado solo puede cerrarse cuando se implemente y valide el proveedor externo y sus garantías anti-rollback.

ME-03K-C queda cerrado en diseño para cada perfil cuando:

**Perfil local:**
1. Existe un resultado tipado de recuperación local, distinto del resultado anclado y sin Trust Anchor.
2. El estado del journal no llega al reducer sin evidencia tipada de autenticidad disponible y continuidad interna.
3. Checkpoints y registros autentican dominio, época, posición, esquema, continuidad disponible y emisor; las limitaciones anti-rollback quedan explícitas.

**Perfil anclado (opcional, etapa final):**
1. Existe un modelo tipado de ancla externa monotónica y sus resultados.
2. El estado del journal no llega al reducer sin evidencia tipada de verificación desde esa ancla.
3. Checkpoints y registros autentican dominio, época, posición, esquema, continuidad y emisor contra el ancla vigente.
4. Recibos operativos/globales comparten claims y contexto de confianza sin permitir autoaprobación.
5. La consulta de resultados ambiguos distingue COMMITTED_EXACT, NOT_COMMITTED, CONFLICT y UNKNOWN bajo consistencia fuerte.
6. Reloj, revocación, replay y recuperación histórica tienen resultados fail-closed definidos.
7. Las interfaces siguen agnósticas a proveedor y no exponen contenido de memoria.

El cierre de diseño no equivale a implementación ni a conformidad operativa. Ninguna lectura protegida ni Forget físico queda autorizada por este documento.


## 14. Decisión del propietario — Trust Anchor opcional y postergado

**Estado: APROBADO — 13 de noviembre de 2026.**

1. Trust Anchor es una capacidad opcional, no un requisito universal para Atlas ni para las etapas actuales del Memory Engine.
2. Su implementación real queda postergada hasta la etapa final del proyecto. No se construirá ahora un proveedor, una VM de confianza ni una integración con un servicio externo.
3. El baseline inicial opera en perfil local sobre un único servidor. El modo de verificación debe quedar explícito en el resultado de recuperación.
4. El perfil local valida autenticidad disponible, estructura, continuidad interna, secuencias, inventarios y recibos; no demuestra que el estado sea el último que existió antes de una restauración coherente del conjunto local y no ofrece anti-rollback externo.
5. El perfil anclado, cuando se implemente, añade verificación contra el ancla externa monotónica. Si el ancla no está disponible, el perfil anclado falla cerrado y no degrada automáticamente al perfil local.
6. El código actual contiene tipos y coordinadores que exigen el resultado verificado con ancla. Este contrato actualizado no significa que el perfil local opcional ya esté implementado. La adaptación de código se planificará en su etapa correspondiente, sin desarrollar ahora el proveedor Trust Anchor.
7. Cualquier garantía que dependa de probar el último estado confirmado fuera del conjunto restaurable —en particular, impedir la reaparición de memorias olvidadas tras restaurar backups antiguos— no se considera cubierta por el perfil local. La restauración afectada debe permanecer bloqueada o someterse a reconciliación explícita con una fuente independiente aprobada.

La decisión no autoriza lecturas protegidas, Forget físico, recuperación productiva ni restauraciones de memoria no reconciliadas.
