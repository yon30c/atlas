# Evaluación y adaptación de Cognee para Atlas Memory Engine

> Estado: decisión de iniciar evaluación; no autoriza instalación, integración ni cambios en el servidor.
> Rama documental: `feature/terminal-commands`.
> Repositorio de Atlas: `yon30c/atlas`.
> Fecha de registro: 17 de noviembre de 2026.

## 1. Objetivo

Evaluar Cognee como base tecnológica candidata para determinadas capacidades de Atlas Memory Engine. La intención no es adoptar Cognee como sistema de memoria completo ni adaptar Atlas a su arquitectura. Primero se analizará el proyecto externo y, posteriormente, se conservarán o adaptarán únicamente los componentes que aporten valor a los requisitos de Atlas.

La dirección acordada es construir una solución de memoria propia de Atlas, potencialmente **basada parcialmente en Cognee**, manteniendo Cognee intercambiable y evitando dependencias innecesarias.

## 2. Decisión de trabajo

Se adopta la siguiente estrategia inicial:

1. Mantener Cognee como dependencia externa e intacta durante la primera etapa.
2. Analizar su arquitectura, módulos, dependencias, contratos, almacenamiento y ciclo de procesamiento.
3. Identificar qué capacidades se pueden reutilizar a través de un adaptador sin modificar Cognee.
4. Crear una prueba de concepto aislada y no privilegiada únicamente después de revisar el análisis y acordar su alcance.
5. Determinar con evidencia si conviene mantener la dependencia, crear un fork o extraer selectivamente módulos.
6. Adaptar la selección final a los contratos y políticas de Atlas, no al revés.

**No instalar Cognee todavía.** La primera actividad es análisis estático del repositorio y de sus dependencias. Cualquier instalación o ejecución de código externo requerirá una decisión posterior y un entorno aislado aprobado.

## 3. Capacidades de Cognee que interesa evaluar

Cognee se presenta como un motor de memoria/conocimiento para aplicaciones de IA. Las capacidades que justifican su evaluación incluyen:

- Ingesta y procesamiento de contenido.
- Extracción de entidades y relaciones.
- Construcción y consulta de grafos de conocimiento.
- Embeddings y recuperación semántica.
- Recuperación contextual y enfoques GraphRAG.
- Enriquecimiento y transformación de conocimiento mediante modelos.
- Abstracciones para proveedores de modelos, almacenamiento y bases de datos.

Estas capacidades son candidatas, no una lista de componentes ya aprobados. Deben verificarse en la versión concreta que se evalúe, incluyendo madurez, límites, configuración y dependencias transitivas.

## 4. Límites de autoridad: responsabilidades de Atlas

Cognee no será la autoridad de Atlas. Aunque ofrezca mecanismos propios de usuarios, espacios, permisos o almacenamiento, no se asumirán como sustitutos de los controles centrales de Atlas.

Atlas conservará el control de:

- Identidad canónica del usuario y del actor.
- Autoridad de acceso y decisiones CAM.
- Propiedad de los recuerdos y sus ámbitos.
- Separación entre memoria personal y memoria de proyecto.
- Políticas de lectura, escritura, recuperación y salida de datos (egress).
- Aprobación y revisión de propuestas de memoria.
- Versionado, estado de validez, actualización e invalidación.
- Retención, olvido, procedencia y auditoría.
- Reglas para relaciones y recuperación entre ámbitos.

El motor semántico no concede permisos. Una coincidencia en un embedding o una arista de un grafo nunca demuestra autorización para leer el recuerdo relacionado.

## 5. Modelo conceptual de memoria para Atlas

La conversación identificó tres dimensiones que deben diseñarse formalmente. Esta sección registra la dirección conceptual, no un esquema definitivo.

### 5.1 Memoria personal

Conocimiento persistente asociado a un usuario: preferencias, contexto personal, decisiones y hechos que el usuario quiera conservar. Debe tener propietario, procedencia, estado, vigencia y reglas de acceso.

### 5.2 Memoria de proyecto

Conocimiento asociado a un proyecto: objetivos, requisitos, decisiones, documentación, arquitectura, restricciones, estado y contexto operativo. Debe permanecer aislado de otros proyectos salvo autorización explícita.

### 5.3 Memoria relacional o Graph Memory

Capa que conecta recuerdos, entidades y conceptos para descubrir relaciones y mejorar la recuperación contextual. Atlas debería poder detectar relaciones candidatas aunque el usuario no haya declarado explícitamente que dos recuerdos están relacionados.

Se deben distinguir al menos:

- Relaciones explícitas: declaradas directamente o respaldadas por una fuente explícita.
- Relaciones inferidas: propuestas por procesamiento o análisis automático.
- Relaciones confirmadas: revisadas y aceptadas según las reglas de Atlas.

Las relaciones inferidas deben conservar evidencia, procedencia, método y grado de confianza; no se convertirán automáticamente en hechos confirmados. Una correlación o proximidad semántica no demuestra causalidad.

El grafo debería poder referenciar recuerdos y entidades canónicas mediante identificadores, en vez de duplicar indiscriminadamente el contenido. El diseño final debe definir cómo se manejan versiones, borrado, invalidación y referencias rotas.

La relación entre memoria personal y memoria de proyecto no se habilitará por defecto. Toda consulta o conexión entre ámbitos debe pasar por la autorización de Atlas.

## 6. Arquitectura candidata

La arquitectura de referencia para la evaluación es:

```
Atlas Assistant / casos de uso
             |
      Atlas Memory Gateway
             |
    Atlas Memory Application
             |
      Cognee Adapter
             |
       Cognee Core
             |
  Graph / Vector / Relational stores
             |
     Local model providers
```

Responsabilidades:

- **Atlas Memory Gateway:** punto de entrada sujeto a identidad, autorización, scope y políticas Atlas.
- **Atlas Memory Application:** ciclo de vida del recuerdo, propuestas, versiones, procedencia, retención y auditoría.
- **Cognee Adapter:** traduce los contratos propios de Atlas a las operaciones del motor y normaliza sus resultados.
- **Cognee Core:** capacidades seleccionadas de ingesta, extracción, grafo y recuperación.
- **Backends:** almacenamiento relacional, grafo y vectorial, elegidos después de revisar compatibilidad y necesidades reales.
- **Proveedor de modelos:** inicialmente se evaluará compatibilidad con modelos locales/Ollama, sin asumir que todos los flujos funcionarán igual con cada modelo.

Los nombres y límites de los componentes son una arquitectura candidata. Se deberán contrastar con los módulos existentes de Memory Engine y evitar duplicar infraestructura ya implementada.

## 7. Estrategias de reutilización a comparar

### A. Dependencia externa + adaptador

Consumir Cognee sin modificarlo y encapsularlo detrás de un adaptador Atlas.

- Menor coste inicial.
- Facilita actualizar o sustituir Cognee.
- Preferida para la primera prueba de concepto, si los contratos existentes lo permiten.

### B. Fork personalizado

Mantener una bifurcación de Cognee cuando se demuestre que son necesarios cambios profundos que no pueden resolverse limpiamente desde el adaptador.

- Mayor control sobre el comportamiento interno.
- Añade responsabilidad de sincronizar cambios upstream, revisar seguridad y mantener dependencias.
- No se hará un fork preventivo.

### C. Extracción selectiva de módulos

Tomar solo los módulos necesarios y mantenerlos dentro de una implementación propia de Atlas.

- Mayor control y menor superficie funcional innecesaria.
- Puede reducir dependencias y facilitar adaptar contratos.
- Requiere mapear dependencias internas, licencias y obligaciones de atribución.
- Solo se elegirá después de comprender la cohesión y el acoplamiento del código.

No se copiarán módulos por nombre o conveniencia sin analizar sus dependencias internas, contratos y licencias.

## 8. Licencia y procedencia

La revisión realizada identificó el repositorio público de Cognee bajo **Apache License 2.0**. En los archivos revisados, `pyproject.toml` declaraba `Apache-2.0`; la versión observada en ese archivo era v1.6.6, mientras que la página de releases mostraba v1.6.7. Estos datos son una referencia de la revisión del 17 de noviembre de 2026 y deben verificarse de nuevo al seleccionar el commit/tag concreto.

La licencia Apache 2.0 permite uso, modificación y distribución, sujeto a sus condiciones. Antes de incorporar código se debe:

- Conservar copias de la licencia y los avisos de copyright aplicables.
- Indicar de forma clara los archivos que hayan sido modificados.
- Incluir el archivo NOTICE cuando corresponda y conservar sus avisos pertinentes.
- Revisar las licencias de dependencias directas y transitivas.
- Registrar origen, versión, commit, cambios locales y componentes reutilizados.
- No asumir que el nombre o las marcas Cognee quedan licenciados por la licencia de código.

La revisión de este documento no constituye una auditoría legal completa ni una aprobación de redistribución.

Repositorio de referencia: https://github.com/topoteretes/cognee

## 9. Plan de evaluación

### Etapa 1 — Inspección estática (siguiente paso)

Sin instalar ni ejecutar Cognee:

1. Fijar el tag/commit que se evaluará.
2. Revisar estructura de carpetas y responsabilidades de cada módulo.
3. Leer documentación de arquitectura, configuración y extensibilidad.
4. Inspeccionar `pyproject.toml`, dependencias y extras opcionales.
5. Trazar los flujos principales de ingesta, extracción, persistencia y búsqueda.
6. Identificar interfaces públicas frente a módulos internos.
7. Localizar integraciones con proveedores LLM, embeddings, bases de datos y grafos.
8. Revisar autenticación, aislamiento multiusuario, borrado, actualización y observabilidad.
9. Identificar dependencias pesadas, código acoplado y puntos de extensión.
10. Producir una matriz de componentes: reutilizar, adaptar, reemplazar o descartar.

**Resultado esperado:** informe de arquitectura y dependencias, con rutas concretas del código y riesgos; todavía sin cambios en Atlas ni instalación de Cognee.

### Etapa 2 — Diseño del adaptador

- Comparar las APIs de Cognee con los contratos existentes de Memory Engine.
- Definir el mapeo de IDs, scopes, versiones, procedencia y resultados.
- Establecer cómo Atlas aplica autorización antes de recuperar o exponer contenido.
- Definir operaciones de sincronización para actualizar, invalidar y olvidar recuerdos.
- Asegurar que el motor no pueda ampliar sus propios permisos.
- Definir límites de datos enviados al proveedor de modelos y backends.

**Resultado esperado:** contrato de integración revisable y lista de incompatibilidades.

### Etapa 3 — Prueba de concepto aislada

Solo después de aprobar el diseño:

- Crear un entorno descartable y aislado.
- Usar datos sintéticos, no recuerdos personales ni datos reales de proyectos.
- Medir calidad de extracción, relaciones, recuperación y precisión.
- Probar separación de ámbitos, eliminación e invalidación.
- Evaluar latencia, uso de recursos, fallos y recuperación.
- Registrar resultados reproducibles y dependencias exactas.

La PoC no se conectará al Assistant de producción ni se considerará autoridad de memoria.

### Etapa 4 — Decisión de adaptación

Con evidencia de las etapas anteriores, elegir entre:

- Mantener Cognee externo con adaptador.
- Crear un fork mantenido por Atlas.
- Extraer selectivamente componentes.
- Descartar Cognee si el coste, el acoplamiento o las limitaciones superan su valor.

La decisión debe considerar funcionalidad, seguridad, licencias, mantenibilidad, rendimiento, portabilidad y coste de actualización.

### Etapa 5 — Integración progresiva con Atlas

La integración con Assistant solo comenzará cuando Memory Engine tenga persistencia real, autorización, aislamiento, ciclo de vida y auditoría suficientes para el flujo seleccionado. Se respetará el orden general de integración de Atlas y el Recovery Gate seguirá cerrado hasta satisfacer sus propios criterios.

## 10. Criterios de aceptación de la evaluación

La evaluación no se considerará terminada hasta poder responder con evidencia:

- ¿Qué módulos concretos de Cognee necesitamos y cuáles no?
- ¿Qué dependencias arrastra cada módulo elegido?
- ¿Podemos usarlo sin fork?
- ¿Qué parte del modelo de memoria de Atlas no encaja con Cognee?
- ¿Cómo se garantizan autorización y aislamiento antes de recuperar contenido?
- ¿Cómo se propagan actualización, invalidación y olvido?
- ¿Cómo se distinguen relaciones inferidas de hechos confirmados?
- ¿Podemos sustituir Cognee sin rediseñar Memory Engine?
- ¿Qué coste operativo y de mantenimiento introduce?
- ¿Qué obligaciones de licencia y atribución aplican a los componentes seleccionados?

## 11. Riesgos y restricciones

- No confundir extracción automática con verdad: las relaciones inferidas pueden ser erróneas.
- No permitir que la recuperación semántica atraviese scopes sin autorización.
- No delegar CAM, identidad ni propiedad de datos en Cognee.
- No duplicar el historial conversacional dentro de la memoria de producto automáticamente.
- No acoplar los contratos de Atlas a tipos internos de Cognee.
- No asumir que una función presente en Cognee es necesaria para Atlas.
- No instalar dependencias externas ni ejecutar código de Cognee en el host o servidor durante la etapa estática.
- No modificar el servidor Debian, servicios, usuarios, permisos ni configuración protegida como parte de esta evaluación.
- Registrar versión y commit exactos para que los resultados sean reproducibles.

## 12. Relación con el roadmap de Atlas

Esta evaluación es una actividad de diseño y desarrollo aislado asociada al subsistema transversal **Memory Engine** (sección 10 del roadmap funcional). No cambia por sí sola la prioridad inmediata de Cycle 3.2, Task Manager ni la secuencia de integración definida en la sección 12 del roadmap.

Puede avanzar en paralelo como análisis documental no privilegiado. La integración real con Assistant queda subordinada a los criterios de salida de Memory Engine y a las fronteras de identidad, autorización, persistencia y recuperación de Atlas.

---

## Referencias revisadas

- Cognee — repositorio: https://github.com/topoteretes/cognee
- Licencia Apache 2.0 del repositorio: `LICENSE`
- Metadatos de paquete y dependencias: `pyproject.toml`
- Guía de estructura y contribución: `AGENTS.md`
- Releases del proyecto: https://github.com/topoteretes/cognee/releases

**Estado actual:** recomendación aprobada para iniciar análisis estático; no hay instalación, fork, extracción de código ni integración de Cognee en Atlas.
