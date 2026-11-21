# Frontera de confianza y autenticación mutua — alternativa A

**Fecha:** 2026-11-21  
**Estado:** diseño candidato para decisión del propietario; no aprobado para implementación persistente ni producción.  
**Rama:** experiment/a-ipc-01-private-unix-listener-probe  
**Dependencias:** contrato atlas-admin/1, lifecycle del listener y auditoría inicial del modelo de amenazas.

## 1. Objetivo

Definir qué identidades confía cada extremo de la conexión AF_UNIX/SOCK_SEQPACKET, cómo se autentican usando credenciales del kernel y cuáles son los límites explícitos del modelo. Este documento no implementa un listener ni modifica el contrato normativo.

## 2. Base comprobada en el repositorio

El código actual src/atlas/platform_admin_ipc.py ofrece:

- read_peer_credentials(connection): obtiene PID/UID/GID con SO_PEERCRED.
- handle_admin_connection(..., allowed_peer_uids=...): valida AF_UNIX/SOCK_SEQPACKET y obtiene las credenciales del peer antes de recibir el paquete.
- La allowlist se entrega al handler como argumento; el handler no determina por sí solo qué UID debe estar autorizado.
- El handler no crea listener, no cambia credenciales ni abre SQLite.
- El contrato §3.2 deja el UID concreto como política local; UID 0 es candidato, no una autorización universal.
- El contrato §3.3 deja fuera del protocolo la creación del endpoint y su lifecycle.

Por tanto, la autenticación del cliente hacia el servidor está parcialmente implementada como mecanismo reutilizable, pero la política de identidad todavía debe fijarse por el futuro caller. La autenticación del servidor hacia el cliente aún no está implementada ni especificada.

## 3. Modelo de confianza recomendado para evaluación

### 3.1 Modelo TCB-1: UID de servicio como dominio de confianza

**Recomendación de diseño para la siguiente fase, sujeta a aprobación del propietario:** tratar todos los procesos que ejecuten efectivamente bajo la cuenta dedicada atlas-runtime como un único dominio de confianza (Trusted Computing Base, TCB).

Consecuencias:

- El aislamiento del directorio 0700 y socket 0600 protege frente a UIDs ordinarios distintos y no privilegiados.
- No protege frente a otro proceso que ya se ejecute como atlas-runtime. Ese proceso tiene autoridad DAC equivalente sobre el directorio y puede interferir con el pathname.
- SO_PEERCRED no distingue dos procesos con el mismo UID. Comprobar también PID/GID no crea por sí solo una identidad criptográfica del ejecutable.
- La cuenta debe ser dedicada, sin login interactivo, sin ejecución arbitraria ni tareas no relacionadas. El servicio y cualquier helper ejecutado bajo ese UID forman parte de la TCB.
- Si no se puede garantizar esa exclusividad operativa, TCB-1 no es suficiente: se requiere una frontera adicional de proceso/identidad antes de continuar.

Root, procesos con capabilities suficientes para alterar el servicio y el kernel se consideran autoridades superiores dentro de la TCB del host; no son adversarios frente a los que este canal promete protección.

### 3.2 Modelo TCB-2: procesos del mismo UID no confiables

Este modelo no queda satisfecho por A tal como está diseñado. Directorio 0700, socket 0600 y SO_PEERCRED no separan procesos del mismo UID. Si el requisito es resistir un proceso hostil bajo atlas-runtime, se debe detener el diseño de A en esta forma y diseñar una frontera adicional (por ejemplo, identidades distintas o aislamiento de procesos con una autoridad de lanzamiento verificable). No intentar simular esa separación con una allowlist de PID estática ni con el nombre del socket.

## 4. Autenticación mutua candidata mediante SO_PEERCRED

Bajo TCB-1, el diseño candidato es autenticación mutua de identidad de sistema operativo, no autenticación criptográfica independiente de procesos.

### 4.1 Servidor autentica al cliente

1. El servidor acepta una conexión en su listener AF_UNIX/SOCK_SEQPACKET.
2. Antes de leer bytes de solicitud, obtiene SO_PEERCRED del socket aceptado.
3. Compara el UID kernel con una allowlist inmutable cargada desde configuración confiable del servicio.
4. Si no coincide, cierra sin leer solicitud y sin enviar envelope de protocolo.
5. PID/GID pueden registrarse para diagnóstico limitado; no sustituyen la decisión de UID ni se aceptan desde JSON.

**Valor candidato:** UID 0 para el frontend administrativo privilegiado, tal como aparece en el lifecycle. No está aprobado ni probado en el host. El valor definitivo debe corresponder al proceso cliente real y ser fijado por el propietario.

### 4.2 Cliente autentica al servidor

1. El cliente conecta exclusivamente a la ruta fija y local documentada; no acepta ruta arbitraria de argumento, solicitud o entorno no confiable.
2. Inmediatamente después de connect y antes de enviar la solicitud, consulta SO_PEERCRED en el socket conectado.
3. Compara el UID kernel del peer con el UID numérico esperado del servicio atlas-runtime, resuelto desde una fuente de configuración confiable y validado antes de usarlo.
4. Si no coincide, cierra sin enviar solicitud y registra un error genérico de autenticación.
5. Solo después de validar al peer envía un único paquete atlas-admin/1.

La verificación de UID del servidor autentica el dominio de confianza TCB-1, no un PID o binario específico. Un proceso distinto bajo el mismo UID sería indistinguible y se considera confiable bajo ese modelo. Si esto no es aceptable, se debe elegir TCB-2 y diseñar otra frontera.

### 4.3 Qué significa y qué no significa “mutua”

Con estas reglas, ambos extremos verifican la identidad UID del otro mediante credenciales entregadas por el kernel. No se obtiene identidad humana, identidad Atlas, autorización por operación ni prueba criptográfica del ejecutable. Tampoco protege frente a root, kernel comprometido o procesos que ya pertenezcan a la TCB de la otra parte.

No añadir un handshake secreto inventado, campos UID/PID en JSON ni una clave compartida legible por ambos UIDs como sustituto de una frontera de confianza. Si se requiere autenticación del ejecutable o del proceso concreto, debe diseñarse y probarse como mecanismo separado.

## 5. Configuración de identidad y política

La futura configuración del servicio debe fijar, antes de abrir el listener:

- UID/GID esperados del servicio atlas-runtime.
- UID(s) autorizados del cliente administrativo.
- Ruta absoluta fija del endpoint y nombre de socket.
- Tipo de socket obligatorio AF_UNIX/SOCK_SEQPACKET.
- Política cerrada de fallo si falta una identidad, la configuración no es válida o los valores no coinciden con el proceso efectivo.

Requisitos:

- La configuración no puede proceder de payload JSON, variables controladas por el cliente ni argumentos arbitrarios del cliente.
- Validar UID real, efectivo y saved UID del servicio; validar GID real, efectivo y saved GID conforme a la política aprobada.
- El proceso debe rechazar inicio si la identidad efectiva no coincide con la configuración esperada.
- La allowlist debe construirse una sola vez y permanecer inmutable durante la vida del listener.
- No inferir UID numérico de un nombre mutable después de iniciar el servicio; resolverlo durante preflight confiable y registrar la identidad numérica efectiva.
- No realizar cambios de usuario/grupo, permisos ni host como parte de esta etapa de diseño.

Los valores numéricos definitivos no se fijan aquí: UID 0 y atlas-runtime siguen siendo candidatos del lifecycle, no una decisión de despliegue.

## 6. Flujo de conexión y orden obligatorio

| Paso | Cliente | Servidor |
|---|---|---|
| 1 | Lee endpoint fijo de configuración confiable | Valida identidad y configuración local |
| 2 | Conecta AF_UNIX/SOCK_SEQPACKET | Listener ya está creado y en listen |
| 3 | Comprueba UID peer del servidor con SO_PEERCRED | Acepta socket |
| 4 | Si falla, cierra sin enviar bytes | Obtiene SO_PEERCRED antes de recv |
| 5 | Envía un único request solo tras autenticar servidor | Compara UID peer con allowlist inmutable |
| 6 | Recibe como máximo una respuesta y valida envelope/request_id | Si peer no autorizado, cierra sin respuesta; si autorizado, procesa contrato |
| 7 | Cierra conexión | Envía respuesta permitida y cierra conexión |

El orden del servidor preserva el contrato atlas-admin/1 §3.1 y §6: autenticación del peer antes de leer el paquete. La comprobación del cliente antes de enviar evita entregar solicitudes a un endpoint cuyo UID no pertenece al dominio de servicio esperado.

## 7. Amenazas y decisiones

| Amenaza | Control candidato | Límite / estado |
|---|---|---|
| Cliente local con UID distinto | DAC 0700/0600 + SO_PEERCRED allowlist | A09 aporta evidencia experimental para UID 1001, no para UID 0 |
| Cliente se conecta a socket de otro UID | Cliente consulta SO_PEERCRED y exige UID de servicio | Diseño; no implementado ni probado |
| Proceso distinto bajo UID atlas-runtime sustituye endpoint | TCB-1 declara todo el UID confiable | No se protege contra ese actor; decisión del propietario |
| Cliente envía UID falso en JSON | Ignorar identidad declarada; usar SO_PEERCRED | Handler actual ya lo hace |
| Configuración del allowlist manipulada por cliente | Configuración confiable e inmutable del servicio | Pendiente de diseño de configuración |
| Root/capabilities/kernel comprometido | Fuera del modelo de protección | Límite explícito |
| Ejecutable cliente distinto pero mismo UID 0 | UID identifica dominio, no ejecutable | No se distingue en este modelo |

## 8. Requisitos previos a implementación

1. El propietario acepta o rechaza explícitamente TCB-1 (todos los procesos atlas-runtime confiables). Si exige aislamiento intra-UID, no implementar A bajo este modelo.
2. El propietario confirma la identidad del cliente administrativo real y su UID esperado; UID 0 continúa siendo solo candidato.
3. Se especifica dónde reside la configuración confiable, quién la posee y cómo se impide que el cliente la modifique.
4. Se define la política de UID/GID reales/efectivos/saved y capabilities del servicio.
5. Se define el comportamiento del cliente si el UID de servidor no coincide: cierre antes de enviar cualquier byte.
6. Se añade un probe aislado que pruebe la verificación de identidad en ambos extremos, incluida identidad incorrecta, antes de integrar el listener.
7. Se completa el procedimiento operacional de socket residual y las brechas restantes A-THREAT-04 a A-THREAT-09.

## 9. Criterio de salida

La frontera queda lista para implementación solo cuando TCB-1/TCB-2 y las identidades cliente/servicio hayan sido aceptadas por el propietario, la fuente de configuración esté especificada y las pruebas aisladas demuestren el orden de autenticación de ambos lados. Este documento por sí solo no aprueba listener persistente, systemd, cambios del host, usuarios/grupos, privilegios, SQLite, provisioning ni despliegue.

## 10. Límites de esta actualización

- Revisión y diseño estático desde GitHub.
- No se modificó código ni contrato normativo.
- No se ejecutaron pruebas, compilaciones ni workflows.
- No se realizaron cambios en Debian ni en el host.
- No se modificó main, no se creó PR ni se aprobó transporte de producción.


## Decisión del propietario y seguimiento — 2026-11-21

El propietario aceptó explícitamente TCB-1: todos los procesos ejecutados bajo la cuenta dedicada atlas-runtime pertenecen al mismo dominio confiable. No se exige aislamiento intra-UID para esta alternativa. Esta decisión no autoriza crear/modificar cuentas, grupos, permisos, servicios ni desplegar.

La configuración de identidades y endpoint se desarrolla en [Configuración confiable de identidad — alternativa A](local-authority-admin-private-listener-identity-config.md). UID 0 continúa siendo candidato para el cliente, no una identidad confirmada. El siguiente paso es identificar el proceso cliente real y revisar su entrypoint/privilegios antes de fijar allowlist y valores operativos.


## Aclaración sobre identidad del cliente — 2026-11-21

La inspección de docs/design/local-authority-administrative-operations-design.md (nombre canónico en el repositorio: local-authority-admin-administrative-operations-design.md) confirma que el modelo de dominio prevé un frontend privilegiado con EUID 0 (§§2.2/5.1). No se encontró una implementación cliente IPC ni un entrypoint ejecutable que realice connect en el estado revisado. Por tanto, UID 0 es el candidato de diseño recomendado para la allowlist, pero todavía no está validado como identidad efectiva del proceso cliente real.

La fuente y el esquema candidatos están definidos en local-authority-admin-private-listener-identity-config.md. El siguiente paso es definir el entrypoint del frontend cliente y fijar su contexto de ejecución; no se debe implementar listener persistente antes de eso.
