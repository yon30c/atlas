# Atlas — resumen de armonización documental de Memory Engine

**Fecha:** 12 de noviembre de 2026  
**Repositorio:** `yon30c/atlas`  
**Rama:** `main`  
**Estado:** correcciones documentales aplicadas y verificadas en GitHub.  
**Código:** no se modificó código Python ni se ejecutaron cambios de infraestructura.

## 1. Objetivo

Armonizar el contrato principal de Atlas v1 con el contrato técnico de Memory Engine, incorporando las decisiones confirmadas por el propietario y eliminando la presentación de decisiones ya aprobadas como asuntos pendientes.

Esta actualización no declara implementadas las capacidades descritas. Establece las reglas que deberá respetar su futura implementación.

## 2. Archivos actualizados

1. `Contrato-de-diseno-Atlas-v1.md`
   - Reglas de acceso a memoria privada y de proyecto.
   - Autorización granular de CAM.
   - Contexto de operación para scopes privados.
   - Versionado, clasificación y sustitución atómica.
   - Supresión, respaldos y reconciliación.
   - Registro de cambios y parámetros técnicos pendientes.

2. `docs/design/memory-engine-technical-contract.md`
   - Representación canónica de `MemoryScope`, sin duplicar `owner_id`.
   - Reglas de autorización privada y de proyecto.
   - Clasificación por versión.
   - Relación entre `MemoryProposal`, `Memory` y `MemoryVersion`.
   - Separación entre ciclo de vida de versiones y proceso de supresión.
   - Sección de parámetros pendientes corregida para no reabrir decisiones confirmadas.

## 3. Decisiones consolidadas

### Autorización y scopes

- El propietario accede a su memoria privada mediante una regla explícita evaluada por CAM, sin necesitar un Grant de proyecto.
- Memory Gateway sigue siendo obligatorio; esta regla no es un bypass de autorización.
- Ningún otro actor obtiene acceso a la memoria privada por defecto.
- La memoria de proyecto requiere un `project_id` explícito, válido y coincidente con su scope, además de autorización CAM.
- Scopes ausentes, ambiguos o inconsistentes producen denegación.
- Para recursos concretos, CAM verifica `resource_id`; una autorización por tipo no concede acceso implícito a todas las instancias.

### Modelo y versiones

- `Memory` es la identidad lógica y mantiene el `owner_id` canónico.
- `MemoryScope` expresa `PRIVATE` o `PROJECT`; no duplica el propietario.
- `MemoryVersion` contiene contenido inmutable, estado, clasificación y procedencia.
- Una propuesta distingue entre crear una memoria nueva y crear una versión de una memoria existente.
- Una versión pendiente no desplaza a la versión aprobada vigente.
- La aprobación de una nueva versión, la sustitución de la anterior y la actualización de la referencia vigente deben ser atómicas.
- La clasificación es explícita por versión y no puede reducirse automáticamente.

### Procedencia y decisiones

- La procedencia se conserva por versión.
- Las referencias a fuentes o evidencias no conceden acceso.
- Una fuente desaparecida se conserva como referencia histórica no disponible.
- Aprobación, rechazo y olvido siguen siendo decisiones directas y no delegables del propietario, con evidencia verificable pendiente de especificación técnica.

### Supresión y respaldos

- El registro de supresión usa identificadores opacos y no conserva contenido original ni hashes de contenido vulnerables a ataques de diccionario.
- La supresión lógica bloquea inmediatamente consulta, recuperación y exposición.
- Restauraciones, reindexaciones e importaciones deben aplicar el registro antes de exponer datos.
- Un destino no disponible o una eliminación parcial mantiene el proceso pendiente; no se comunica éxito.
- Los respaldos inmutables se rigen por retención y no se declara finalización física mientras sigan retenidos.
- El estado de supresión de la memoria lógica se mantiene separado de los estados normativos de las versiones.

## 4. Parámetros técnicos que siguen pendientes

Las siguientes cuestiones no se consideran resueltas por esta actualización:

- Formato final de identificadores y política de transferencia entre scopes.
- Catálogo de clasificación específico de Memory Engine.
- Evidencia técnica de aprobación directa del propietario.
- Retención de versiones históricas.
- Plazo de retención de respaldos y propagación máxima.
- Inventario de almacenes, índices, cachés, réplicas y respaldos.
- Formato, persistencia y reconciliación del registro de supresión.
- Semántica de operaciones colectivas autorizadas por tipo.
- Límites de contenido y metadatos del índice global.
- Permisos específicos para proponer cada clase de memoria.

Estos parámetros deben definirse sin debilitar las decisiones consolidadas.

## 5. Verificación realizada

Se volvieron a consultar los dos archivos en `main` después de las actualizaciones. Se verificó que:

- La regla de memoria privada aparece en ambos documentos.
- La comprobación de `resource_id` está en el contrato principal.
- El contexto permite ausencia de `project_id` únicamente cuando el scope privado está explícito.
- `owner_id` tiene una representación canónica.
- La clasificación está definida por versión.
- La sección de parámetros pendientes ya no presenta como pendientes las decisiones confirmadas.
- Las reglas de supresión, respaldos y sustitución atómica están reflejadas.
- Los documentos no afirman que el código esté implementado.

## 6. Historial de commits

- Contrato principal: `99f59553f90c560e9ee2417f4e1ddd825c1cb991`
- Contrato técnico: `1d4c8e6bb15f274e1fdfb4457932941ffc9be2c9`

## 7. Alcance y exclusiones

Esta actualización es documental. No modifica:

- Código Python ni pruebas.
- Atlas Broker ni Registry v2.
- Servicios o infraestructura de producción.
- Docker, bases de datos ni despliegues.
- SecurityAudit, cuya implementación continúa postergada.
- Cognee, Telegram, Scheduler o RLM.

## 8. Próximo paso recomendado

Antes de implementar Memory Engine, especificar los parámetros técnicos pendientes que bloquean los flujos correspondientes y traducir las invariantes consolidadas en pruebas de aceptación. La implementación debe comenzar por modelos y contratos de dominio, seguida por Gateway/CAM, revisión y, una vez resuelta la estrategia de persistencia y supresión, el flujo de olvido.
