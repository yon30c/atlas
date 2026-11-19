# Lifecycle seguro del listener IPC administrativo de autoridad

**Estado:** diseño de revisión; no aprobado para producción.  
**Fase:** 2.5.3.  
**Dependencia:** prototipo de protocolo y pruebas de sockets temporales de las Fases 2.5.2/2.5.2b.

## Objetivo y límites

Definir las condiciones de seguridad que debe cumplir un listener Unix persistente antes de implementarlo. Este documento no crea sockets, usuarios, directorios, unidades systemd ni modifica el host. Tampoco selecciona todavía entre un listener creado por el proceso y socket activation de systemd.

El canal sigue siendo experimental. La única operación implementada continúa siendo authority.ping; no se habilitan SQLite, migraciones, bootstrap, provisioning ni otras mutaciones.

## Identidad y permisos propuestos

La identidad de servicio candidata es la cuenta dedicada atlas-runtime, sin login interactivo. No se deben reutilizar greed, atlas-sandbox ni la identidad del despliegue antiguo.

Para un socket creado por el servicio, el modelo inicial a validar es:

- Directorio padre dedicado, preaprovisionado y privado: propietario atlas-runtime:atlas-runtime, modo 0700.
- Nombre fijo y documentado dentro de ese directorio; nunca aceptar una ruta arbitraria desde el cliente.
- Socket: tipo AF_UNIX/SOCK_SEQPACKET, propietario esperado atlas-runtime, modo inicial objetivo 0600.
- Sin acceso por grupo ni ACL adicionales en el primer diseño.
- Cliente administrativo privilegiado: UID esperado explícito (candidato UID 0 para el frontend administrativo), verificado con SO_PEERCRED; no confiar en UID/PID/GID declarados en el paquete.
- El servicio no debe inferir identidad Atlas USER, identidad civil ni autoridad de dominio a partir de las credenciales Linux. La autorización de cada operación deberá ser una capa separada y futura.

Estos valores son una propuesta de mínimo privilegio, no una configuración aprobada. Deben verificarse contra el modelo final del frontend y las unidades systemd antes de codificar.

## Invariantes del ciclo de vida

1. **Directorio confiable:** antes de usar la ruta, comprobar con operaciones que no sigan symlinks que el directorio esperado existe, es un directorio real, tiene el propietario y modo previstos y no es escribible por usuarios no confiables.
2. **No reemplazar rutas existentes:** crear/bindear debe fallar si el nombre ya existe. Nunca borrar primero una ruta preexistente para “liberar” el nombre.
3. **No recuperar sockets stale automáticamente:** un socket existente puede pertenecer a otro proceso, a una instancia activa o ser una ruta colocada deliberadamente. El arranque debe fallar cerrado y requerir diagnóstico administrativo separado. No conectar para decidir si se puede borrar ni hacer unlink preventivo.
4. **Verificación posterior al bind:** inspeccionar la entrada creada sin seguir symlinks y verificar tipo socket, dispositivo/inode, propietario y modo. Si cualquier condición falla, cerrar el descriptor y aplicar limpieza limitada a la entrada que el proceso pueda demostrar que creó.
5. **Descriptor y ruta:** conservar el descriptor del listener durante toda su vida. No tratar la existencia de la ruta como prueba de que el descriptor sigue asociado al mismo inode.
6. **Limpieza condicionada:** al apagar, cerrar primero el listener y eliminar la ruta solo si sigue siendo un socket y coincide con la identidad de filesystem (al menos st_dev + st_ino) registrada inmediatamente después del bind. Nunca eliminar un archivo, symlink o socket sustituto.
7. **Fallo seguro ante carrera:** si la entrada fue reemplazada o no puede verificarse, no eliminarla. Registrar el incidente y dejar que el procedimiento operacional lo resuelva.
8. **Permisos explícitos:** no depender del umask heredado como única protección. Establecer y verificar los modos requeridos; rechazar permisos más amplios que la política.
9. **Conexiones acotadas:** cada conexión procesa un solo paquete, con límites de tamaño y timeout de lectura/escritura; cerrar siempre el descriptor aceptado en un bloque de limpieza incluso ante errores de protocolo o cliente desconectado.
10. **Sin privilegios heredados:** el proceso de servicio no debe conservar descriptores no previstos ni capacidades o IDs efectivos/saved que permitan elevar privilegios. El diseño del frontend privilegiado se revisará aparte.

## Secuencia candidata para un listener gestionado por el proceso

Esta secuencia es una especificación para revisar, no una instrucción de ejecución:

1. Arrancar bajo UID/GID atlas-runtime y validar configuración estática allowlisted.
2. Abrir el directorio padre con flags de directorio y no-follow; validar su metadata mediante el descriptor abierto.
3. Intentar bind() al nombre fijo. Si existe cualquier entrada, fallar sin eliminarla.
4. Aplicar modo explícito al socket y leer metadata sin seguir symlinks.
5. Confirmar tipo, propietario, modo y registrar st_dev/st_ino de la entrada creada.
6. Llamar listen(); si falla, cerrar y ejecutar únicamente la limpieza condicionada del inode propio.
7. Aceptar conexiones con límites de concurrencia y timeouts; validar SO_PEERCRED antes de leer el paquete.
8. En apagado ordenado, dejar de aceptar conexiones, cerrar conexiones activas con plazo limitado, cerrar listener y limpiar solo la ruta propia verificada.
9. Ante terminación abrupta, no ejecutar un mecanismo de “stale cleanup” automático en el siguiente arranque. Requerir diagnóstico explícito.

La implementación debe preferir operaciones relativas a un descriptor de directorio (dir_fd) y O_NOFOLLOW donde estén disponibles. Python no ofrece una operación portable de unlink condicional por inode: una secuencia stat-then-unlink conserva una ventana TOCTOU. La protección principal debe ser que el directorio no sea modificable por un atacante no confiable; las carreras frente a root y el mecanismo exacto de limpieza necesitan revisión específica antes de implementar.

## Evaluación técnica de socket activation en Debian

La documentación de systemd para Debian Trixie confirma:

- ListenSequentialPacket= crea un socket SOCK_SEQPACKET y está limitado a AF_UNIX.
- Con Accept=no, systemd pasa el descriptor del listener al servicio; el daemon debe aceptar conexiones sobre ese descriptor y **no debe hacer unlink del socket de filesystem**.
- SocketUser=, SocketGroup= y SocketMode= permiten fijar ownership y permisos. Los defaults son root/grupo predeterminado y modo 0666, por lo que no deben dejarse implícitos.
- DirectoryMode= controla el modo de los directorios padre que systemd cree automáticamente; su default es 0755. El directorio sensible debe preaprovisionarse con ownership y modo explícitos, o verificarse cuidadosamente.
- RemoveOnStop= está desactivado por defecto. Si se activa, systemd elimina los nodos creados por la unidad al detenerla; la documentación advierte que esto puede ser inconveniente si el servicio continúa ejecutándose y el socket debe seguir accesible.

Consecuencia de diseño: socket activation elimina del daemon la responsabilidad de bind/listen y del unlink normal del socket. No elimina la necesidad de validar el descriptor recibido, autenticar cada peer con SO_PEERCRED, limitar conexiones, manejar errores y coordinar el ciclo de vida de las unidades. Tampoco justifica habilitar RemoveOnStop sin definir claramente qué unidad detiene a cuál.

**Estado del candidato systemd:** suspendido; no existe una opción preferida aprobada. Aunque `ListenSequentialPacket=` con `Accept=no` reduce la gestión del socket dentro del daemon, la prueba de integración del usuario-manager observó en Debian systemd 257.13 que una ruta preexistente con archivo regular perdió su contenido durante el intento de activación. El probe dejó de repetir el caso destructivo y ahora usa exclusivamente una ruta ausente dentro de un directorio privado. Por tanto, la activación de sockets sobre filesystem no satisface todavía el invariante de no reemplazar rutas existentes.

Antes de reconsiderar este candidato deben demostrarse, en un entorno desechable, una estrategia de propiedad de ruta que impida la colisión destructiva, descriptor heredado correcto y tipo SOCK_SEQPACKET, credenciales SO_PEERCRED, permisos reales del socket/directorio, reinicio del servicio conservando el listener, parada coordinada y comportamiento de RemoveOnStop. La evidencia del user-manager no sustituye una prueba separada del system-manager con la identidad y permisos objetivo de `atlas-runtime`. No instalar ni desplegar unidades Atlas.

## Evaluación de propiedad de ruta y alternativas de transporte

La colisión observada con systemd obliga a separar dos decisiones: quién crea/posee el endpoint y si el endpoint tiene una entrada en filesystem. La evidencia disponible no autoriza a conservar la preferencia anterior por socket activation filesystem.

### Alternativa A — Listener creado por el proceso sobre filesystem privado

**Candidato recomendado para el siguiente experimento aislado; no aprobado para producción.**

- Un directorio padre debe ser preaprovisionado por el administrador del host con propietario `atlas-runtime:atlas-runtime` y modo `0700`; el servicio no crea ni cambia la propiedad de ese directorio durante el arranque.
- El proceso `atlas-runtime` crea el socket `AF_UNIX/SOCK_SEQPACKET` con un nombre fijo configurado, sin aceptar rutas del cliente.
- No se elimina, renombra ni trunca ningún objeto antes de `bind()`. Una entrada preexistente de cualquier tipo debe causar fallo cerrado; el probe debe demostrar que un archivo regular conserva inode, tipo y contenido ante la colisión.
- Tras `bind()`, se verifica tipo, UID, modo, dispositivo e inode. El descriptor listener se conserva durante toda la vida del servicio.
- No se hace recuperación automática de sockets stale. Si un cierre abrupto deja una entrada, el siguiente arranque falla y exige diagnóstico/recuperación operacional explícita.
- El cleanup ordenado solo puede retirar el socket creado por esa instancia y verificado como el mismo objeto. La secuencia pathname stat-then-unlink no es atómica; su aceptabilidad depende de que el directorio sea privado y de que no existan procesos no confiables bajo el mismo UID. Root permanece fuera del modelo de protección.
- El servicio debe ser una instancia única, no permitir ejecución arbitraria bajo el UID `atlas-runtime`, y no exponer el directorio a otros usuarios.

**Ventajas:** el kernel hace el bind en el proceso que posee el descriptor; no hay pre-bind de systemd que gestione la ruta; la colisión se puede tratar como fallo cerrado del propio `bind()`.

**Costos/riesgos:** el proceso debe gestionar bind/listen/shutdown; una caída puede dejar un socket stale; cleanup por nombre tiene límite TOCTOU; requiere aprovisionamiento fiable del directorio y prueba real de colisiones.

### Alternativa B — Socket activation systemd sobre filesystem

**Suspendida; no usar como baseline.**

La prueba en Debian systemd 257.13 observó pérdida del contenido de un archivo regular preexistente en la ruta configurada. El probe actual evita repetir el escenario destructivo. No basta con que el directorio sea privado: debe explicarse y probarse el comportamiento de colisión de systemd antes de reconsiderar esta alternativa.

No se debe configurar `RemoveOnStop=` para compensar la colisión ni asumir que ownership/mode del socket resuelve la propiedad de la ruta. El daemon que recibe un descriptor con `Accept=no` no debe eliminar el nodo filesystem.

### Alternativa C — Socket abstracto AF_UNIX/SOCK_SEQPACKET

**Alternativa experimental que merece un probe separado; no aprobada para producción.**

Linux y systemd admiten direcciones abstractas AF_UNIX; en una unidad systemd se representan con prefijo `@`, que se convierte en NUL antes de bind. Esto evita la creación de una entrada filesystem, elimina stale path files y no requiere unlink durante shutdown.

Límites que deben quedar explícitos:

- No hay inode, propietario, modo, ACL ni permisos de directorio que protejan el endpoint. Los permisos filesystem no aplican al nombre abstracto.
- El endpoint puede ser contactado por procesos locales que conozcan el nombre. Cada conexión debe pasar `SO_PEERCRED` antes de leer cualquier paquete; la autorización de dominio permanece separada.
- Un proceso local puede intentar reclamar el nombre primero y causar denegación de servicio. Un nombre aleatorio dificulta colisiones accidentales, pero no es una frontera de autorización y complica el descubrimiento por clientes.
- Deben probarse el ámbito real del namespace en el host objetivo, colisiones de nombre, comportamiento ante restart, exposición a otros UIDs, backlog/conexiones abusivas y activación tanto user-manager como system-manager.
- No se debe afirmar que el nombre abstracto es secreto ni que reemplaza la allowlist de credenciales.

### Recomendación de secuencia

1. Mantener deshabilitada cualquier activación systemd sobre ruta filesystem.
2. Crear un probe opt-in, puramente temporal, para el listener gestionado por proceso en directorio privado. Debe verificar que archivo regular, symlink, socket activo y socket stale nunca son reemplazados ni eliminados; dos binds concurrentes deben producir un solo ganador.
3. Crear un segundo probe aislado para socket abstracto y documentar el alcance de visibilidad y la colisión/preclaim.
4. Comparar evidencia de ambas alternativas, incluidos los límites de cleanup y DoS. No convertir una prueba user-manager en aprobación del system-manager.
5. Solicitar decisión explícita del propietario antes de seleccionar transporte, crear unidades de producción o implementar listener persistente.

Ninguno de estos probes debe tocar rutas, usuarios, sockets, bases o unidades Atlas existentes. No ejecutar con `sudo`, no usar `/run` ni `/var/lib`, y no modificar el host. La prueba debe usar recursos únicos bajo un directorio temporal privado y cleanup por identidad registrada.

## Pruebas requeridas antes de implementación

Todas deben usar directorios y sockets temporales creados por tests. No utilizar /run, /var/lib, sockets de Atlas ni servicios activos.

- Directorio ausente, symlink, propietario incorrecto, modo demasiado amplio y directorio no escribible.
- Ruta ocupada por archivo regular, symlink, socket activo y socket stale; confirmar que nunca se reemplazan ni eliminan automáticamente.
- Verificación de tipo, propietario, modo e inode después de bind.
- Fallo inyectado después de bind y antes/después de listen; comprobar limpieza únicamente del inode creado.
- Sustitución deliberada de la ruta antes de cleanup; comprobar que el sustituto permanece intacto.
- Dos procesos concurrentes intentando bind al mismo nombre; solo uno puede adquirirlo y el otro debe fallar cerrado.
- Timeout, peer que conecta y no envía, paquete inválido, desconexión, cliente concurrente, cierre ordenado y reinicio.
- Confirmar que las conexiones rechazadas por UID se rechazan antes de leer datos.
- Comprobar que los descriptores se cierran y que no quedan sockets temporales tras cada test.
- Para socket activation, probar descriptor heredado, tipo, reinicio, colisión, ownership/mode y parada coordinada en un entorno desechable.

Las pruebas con múltiples UIDs deben ser opcionales y explícitas; nunca convertir la suite completa en una ejecución privilegiada por defecto. No crear ni modificar cuentas locales para satisfacer tests.

## Observabilidad y operación

- Registrar inicio, fallo de bind, rechazo de peer, error de protocolo, apagado y fallo de cleanup sin incluir payloads sensibles.
- No registrar secretos ni permitir que el cliente elija rutas, nombres de archivo, comandos o argumentos de proceso.
- Un socket preexistente debe producir un diagnóstico accionable (ruta fija, tipo y metadata observada cuando sea seguro), pero no debe provocar su eliminación.
- La limpieza manual, si finalmente se requiere, será una operación administrativa separada, autenticada y auditada; no forma parte del arranque normal.
- Los logs del proceso no sustituyen al ledger de auditoría de operaciones administrativas futuras.

## Puertas de decisión

Antes de escribir listener de producción deben aprobarse explícitamente:

1. Identidad real del cliente administrativo y UID/GID permitidos.
2. Directorio, propietario, modo y política de ACL.
3. Listener propio frente a socket activation.
4. Estrategia TOCTOU y límites aceptables de limpieza.
5. Concurrencia, timeouts, shutdown y reinicio.
6. Hardening systemd, capacidades, descriptores y límites de recursos.
7. Matriz de pruebas y revisión adversarial.

La aprobación de este documento o de los tests temporales no autoriza cambios en el host, despliegue, creación de usuarios, configuración systemd, apertura de SQLite ni ejecución de provisioning.
