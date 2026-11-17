# Propuesta técnica: ejecución distribuida y colaboración entre nodos Atlas

**Estado:** Propuesta técnica — pendiente de evaluación y aprobación  
**Fecha:** 2026-11-17  
**Ámbito:** Evolución futura de Atlas; no forma parte de la implementación actual ni modifica decisiones arquitectónicas ya adoptadas.

## 1. Objetivo

Permitir que dos o más instalaciones/nodos Atlas trabajen simultáneamente, compartan un estado lógico común y distribuyan tareas entre sus recursos. Los nodos deben poder ejecutar tareas diferentes en paralelo, coordinar su progreso y conservar una visión coherente de usuarios, identidades, proyectos, permisos, conversaciones, memoria y resultados.

La propuesta busca que Atlas pueda crecer desde una instalación individual hacia un sistema distribuido sin acoplar su identidad, autorización o datos a una máquina concreta.

## 2. Principios

- **Estado común, ejecución distribuida:** separar los datos y autoridades compartidos de los procesos de ejecución locales a cada nodo.
- **Identidad independiente del nodo:** un usuario Atlas conserva el mismo UserId e identidad canónica al conectarse a cualquier nodo. La identidad técnica de cada instalación/nodo es distinta y no representa a un usuario.
- **Autorización centralmente coherente:** CAM sigue siendo la autoridad para autorizar cada operación. La disponibilidad de una tarea o la pertenencia a un nodo no concede permisos.
- **Broker por nodo:** cada nodo conserva su Atlas Runtime y su Atlas Broker independiente. Runtime, modelos, agentes y Skills no reciben acceso directo a Docker, root ni sockets privilegiados.
- **Asignación explícita:** las tareas se asignan a nodos según capacidades, disponibilidad, límites de recursos, afinidad y restricciones de seguridad declaradas.
- **Ejecución recuperable:** tolerar reinicios, desconexiones y resultados inciertos sin asumir que una tarea fallida puede repetirse sin consecuencias.
- **Portabilidad:** no depender de hostname, UID/GID, rutas personales ni hardware de una máquina específica.
- **Fail-closed:** si no se puede verificar identidad, autorización, propiedad de la tarea o estado de coordinación, la operación protegida no se ejecuta.

## 3. Arquitectura conceptual

La solución separaría dos planos:

### 3.1 Plano de control y estado compartido

Responsable de:
- Usuarios Atlas, autenticación, sesiones e identidades canónicas.
- Proyectos, entornos, workspaces y sus relaciones de ownership.
- Grants, decisiones CAM, aprobaciones y evidencia de auditoría.
- Registro de nodos, capacidades declaradas, salud y estado de disponibilidad.
- Cola/registro durable de tareas, asignaciones, leases, intentos y resultados.
- Referencias a conversaciones, memoria y artefactos compartidos.

Este plano debe exponer contratos de aplicación/API autenticados. Los nodos no deberían manipular directamente tablas internas de otro componente ni compartir un archivo de base de datos.

### 3.2 Plano de ejecución por nodo

Cada nodo mantiene:
- Atlas Runtime y Assistant.
- Adaptadores de ejecución y recursos locales autorizados.
- Su identidad técnica de instalación/nodo.
- Atlas Broker propio, aislado del Runtime.
- Acceso únicamente a workspaces, secretos y recursos explícitamente asignados.

Un nodo solicita o recibe tareas mediante el plano de control, valida el contexto y autorización aplicables y ejecuta a través de sus límites locales. Devuelve eventos y resultados al estado compartido.

## 4. Coordinación y distribución de tareas

Se propone un Task Manager distribuido con estas capacidades:

1. **Registro durable de tareas:** cada tarea tiene identificador global, proyecto/entorno, solicitante, tipo de capacidad, restricciones, estado y política de reintentos.
2. **Cola de trabajo:** tareas elegibles quedan disponibles para los nodos compatibles.
3. **Asignación con lease:** un nodo adquiere temporalmente una tarea mediante una operación atómica con vencimiento. Un heartbeat renueva el lease mientras trabaja.
4. **Prevención de doble asignación:** la adquisición debe ser transaccional y respaldada por restricciones/versiones o mecanismo equivalente.
5. **Idempotencia:** cada operación con efectos debe tener una clave de idempotencia estable y registro durable de resultado. Un timeout no autoriza a repetir ciegamente una operación.
6. **Estados explícitos:** pendiente, elegible, asignada, en ejecución, esperando aprobación, completada, fallida, cancelada y resultado desconocido, o estados equivalentes definidos por el Task Manager.
7. **Recuperación:** al vencer un lease, el coordinador evalúa el último checkpoint y la evidencia disponible antes de reasignar. Las tareas con efectos externos o resultado incierto requieren reconciliación, no reejecución automática.
8. **Cancelación y timeout:** deben propagarse de forma autenticada y auditable; cancelar la coordinación no implica que un proceso remoto haya detenido sus efectos.
9. **Prioridad y fairness:** evitar que un nodo o proyecto monopolice indefinidamente la capacidad compartida.

La asignación debe considerar capacidades verificadas y políticas, no confiar únicamente en etiquetas autodeclaradas por un nodo.

## 5. Datos, almacenamiento y consistencia

- No compartir directamente el archivo SQLite actual entre servidores ni usar un montaje de red como sustituto de una base de datos distribuida.
- Mantener SQLite para el modo local de una sola instancia mientras siga siendo adecuado.
- Evaluar una base de datos cliente-servidor, por ejemplo PostgreSQL, como persistencia compartida para el modo multi-nodo. La elección y el modelo de migración quedan pendientes.
- Los archivos y artefactos requieren almacenamiento compartido mediante un servicio/almacén de objetos o un mecanismo explícito de transferencia y versionado. Las rutas físicas locales no son referencias globales.
- Usar identificadores lógicos, hashes de contenido, versiones y metadatos de ownership para referenciar artefactos.
- Definir garantías de consistencia por dominio. Autenticación, CAM, grants, leases y estado de tareas requieren operaciones atómicas y lecturas coherentes con sus invariantes.
- Conversaciones y memoria deben tener ownership, versionado y reglas de concurrencia explícitas; no asumir que dos nodos pueden sobrescribir el mismo estado sin coordinación.
- La replicación y los backups no sustituyen exportación/restauración verificadas.

## 6. Seguridad y autoridad

- Authentication Authority e Identity Authority nativas deben producir el contexto de identidad verificado consumido por los servicios existentes.
- CAM continúa autorizando cada operación; los nodos no pueden ampliar grants ni convertir la posesión de un lease en permiso.
- La asignación de una tarea debe quedar ligada a la identidad solicitante, proyecto, entorno, capacidad, aprobación aplicable y nodo ejecutor.
- Los mensajes entre nodos y el plano de control requieren autenticación mutua, autorización por operación, protección contra replay, expiración y rotación de credenciales.
- Cada nodo debe tener una identidad técnica revocable y credenciales propias; no compartir secretos de instalación entre nodos.
- El Broker local verifica la solicitud y conserva su frontera de ejecución. La decisión CAM debe estar vinculada a la operación concreta y ser verificable antes de ejecutar.
- Skills y agentes no adquieren privilegios por ejecutarse en un nodo con más recursos.
- Auditoría correlacionada con identificadores de tarea, operación, aprobación, nodo y resultado.

## 7. Fallos y escenarios que deben cubrirse

- Caída de un nodo antes de adquirir una tarea, durante su ejecución o después del efecto pero antes de reportar el resultado.
- Pérdida temporal de conectividad con el plano de control.
- Lease vencido mientras el nodo sigue ejecutando.
- Dos nodos intentando adquirir la misma tarea.
- Resultado desconocido de una operación no idempotente.
- Revocación de usuario, sesión, grant o nodo mientras hay tareas activas.
- Actualización incompatible de protocolo entre nodos.
- Pérdida o corrupción del almacenamiento compartido.
- Reinicio del plano de control y recuperación de tareas en estados intermedios.
- Diferencias de reloj; los vencimientos deben basarse en tiempo del coordinador o en un mecanismo consistente, no solo en relojes locales.

## 8. Evolución incremental propuesta

1. Definir contratos de nodo, tarea, lease, heartbeat, eventos, checkpoints, idempotencia y resultado desconocido.
2. Completar identidad nativa, contexto canónico, ownership de proyectos/entornos/workspaces y persistencia durable en una sola instancia.
3. Extraer los contratos del Task Manager para que no dependan de memoria de proceso ni de una consola local.
4. Implementar un coordinador durable en una sola instancia y validar recuperación, concurrencia e idempotencia.
5. Introducir registro y autenticación de nodos, primero con un segundo nodo de pruebas.
6. Añadir asignación, leases, heartbeats y reconciliación de tareas.
7. Resolver almacenamiento compartido/versionado de artefactos y secretos por nodo.
8. Ejecutar pruebas multi-nodo de fallos, seguridad, carga y recuperación antes de declarar soporte.

## 9. Criterios mínimos para declarar soporte multi-nodo

- Dos nodos pueden ejecutar tareas diferentes en paralelo sobre el mismo estado lógico.
- Una tarea no se asigna concurrentemente a dos nodos salvo que el tipo de tarea permita explícitamente ejecución redundante.
- Las operaciones con efectos no se duplican silenciosamente ante timeout, crash o reintento.
- La identidad y los permisos del usuario se mantienen coherentes entre nodos.
- La revocación y las aprobaciones se aplican también a tareas distribuidas.
- Un nodo desconectado no puede continuar iniciando nuevas operaciones protegidas con autorizaciones caducadas.
- Los artefactos son accesibles mediante referencias lógicas y controles de ownership, no rutas locales implícitas.
- Los eventos y resultados se pueden auditar y correlacionar de extremo a extremo.
- Las pruebas demuestran recuperación ante fallos y comportamiento seguro ante estados desconocidos.

## 10. Fuera de alcance y advertencias

Esta propuesta no aprueba ni implementa:
- Alta disponibilidad automática del plano de control.
- Active-active de la base de datos o multi-master.
- Consistencia eventual para permisos o decisiones CAM.
- Ejecución duplicada o failover automático de cualquier tarea.
- Compartir directamente SQLite entre máquinas.
- Compartir Docker socket, root, Broker o credenciales entre nodos.
- Migración automática de los datos actuales.
- Cambios en el host Debian, systemd, usuarios, grupos, Docker o privilegios.

La primera implementación multi-nodo deberá elegir explícitamente sus garantías de disponibilidad, consistencia, recuperación y límites operativos. No se debe anunciar HA ni tolerancia a fallos antes de probarlas.

## 11. Relación con decisiones existentes

La propuesta complementa, pero no reemplaza:
- La decisión de imagen Linux autónoma OCI.
- La decisión de autenticación nativa de Atlas y portabilidad entre máquinas.
- La separación entre identidad humana, identidad técnica de instalación y permisos del host.
- La autoridad CAM y el aislamiento de Atlas Broker.
- La persistencia SQLite actual, que sigue limitada a una instancia y una base de datos local en el alcance probado.

**Conclusión:** se recomienda conservar esta dirección como objetivo arquitectónico futuro y evaluarla después de estabilizar autenticación nativa, contexto canónico, ownership de workspaces y Task Manager durable. Hasta entonces, Atlas debe seguir considerándose una aplicación de una sola instancia, no un sistema distribuido operativo.
