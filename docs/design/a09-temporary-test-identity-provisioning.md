# Diseño — identidad temporal para A09 (A-IPC-01)

**Estado:** propuesta de procedimiento autorizada para diseño; no autorizada todavía para ejecución en Debian.  
**Rama:** `experiment/a-ipc-01-private-unix-listener-probe`.  
**Propósito:** proporcionar un peer Linux de UID distinto para A09a (DAC) y A09b (SO_PEERCRED), sin reutilizar cuentas de servicios ni permitir que el runner cambie credenciales.

## 1. Decisión y límites

El propietario autorizó diseñar una cuenta temporal dedicada, `atlas-a09-test`. Esta autorización cubre el diseño y la preparación documental, no la creación de la cuenta, la instalación de claves, cambios SSH ni ninguna otra modificación del host.

La cuenta existente `atlas-sandbox` queda expresamente excluida: UID 997, contraseña bloqueada, linger activo y procesos de Atlas Broker/rootless containers. No iniciar sesión con ella, cambiar su contraseña, detener sus procesos ni reutilizarla como peer.

El procedimiento debe producir dos identidades de proceso reales:
- servidor/runner bajo la cuenta ordinaria propietaria del checkout (actualmente `greed`, UID 1000);
- cliente bajo `atlas-a09-test`, con UID distinto asignado automáticamente por el sistema.

No se utilizarán mocks de credenciales, `setuid()`, `sudo -u`, `su`, `runuser`, capabilities ni mecanismos de cambio de UID dentro del runner. La sesión cliente se autenticará de forma independiente mediante el mecanismo SSH existente, si ya lo permite.

## 2. Cuenta temporal propuesta

Nombre: `atlas-a09-test`.

Propiedades requeridas:
- cuenta local ordinaria, con UID asignado automáticamente y distinto de 1000; no fijar ni reutilizar un UID;
- grupo primario dedicado con el mismo nombre y sin grupos suplementarios;
- sin pertenencia a `sudo`, `docker`, `lxd`, `adm`, `systemd-journal` u otros grupos de privilegio;
- HOME dedicado fuera del checkout, por ejemplo `/var/lib/atlas-a09-test`, propiedad de la cuenta y modo `0700`;
- shell válida para ejecutar un comando remoto no interactivo (`/bin/bash`), sin archivos de inicio añadidos;
- contraseña bloqueada; no establecer contraseña reutilizable;
- sin linger, servicios de usuario, contenedores, cron, timers, capabilities ni procesos persistentes;
- fecha de expiración de cuenta fijada para el periodo de prueba, si el mecanismo local lo permite sin afectar otras cuentas.

La creación debe abortar si el nombre ya existe, el UID asignado no es distinto, el grupo no es exclusivo o el entorno de autenticación exige relajar controles. No se debe forzar UID/GID ni reutilizar `atlas-sandbox`.

## 3. Autenticación externa prevista

Primera opción: clave SSH Ed25519 efímera, generada para esta prueba y almacenada temporalmente en un directorio privado de runtime de `greed` (modo `0700`). La clave privada no se copiará al HOME del peer ni al repositorio.

La clave pública se instalaría en `~atlas-a09-test/.ssh/authorized_keys` con:
- directorio `.ssh` modo `0700`;
- archivo `authorized_keys` modo `0600`;
- propiedad de `atlas-a09-test`;
- restricción de origen a loopback (`127.0.0.1`) y opciones restrictivas de clave (`restrict`), sin forwarding ni PTY;
- conexión cliente con autenticación exclusivamente por clave pública, `IdentitiesOnly`, sin password ni keyboard-interactive, y verificación estricta de host key.

No se modificará `sshd_config`, PAM, `AllowUsers`, `AuthenticationMethods`, firewall ni servicio SSH. Tampoco se desactivará el bloqueo de contraseña. Si el estado de cuenta bloqueado impide la autenticación de clave pública por las políticas PAM/SSH actuales, se detiene el procedimiento; no se desbloquea la cuenta ni se cambia la política como workaround. Cualquier alternativa requerirá diseño y autorización aparte.

La sesión SSH ejecutará únicamente el cliente A09 preparado para la prueba. No necesita PTY, forwarding, agente SSH ni acceso al repositorio. Si SSH local no está disponible o no acepta la clave restringida sin cambios de configuración, A09 permanece SKIP.

## 4. Separación de A09a y A09b

### A09a — DAC del endpoint candidato

- El runner crea su endpoint normal con directorio `0700` y socket `0600`, dentro del sandbox privado.
- La ruta se comunica al cliente externo sin conceder acceso al checkout.
- El cliente con UID `atlas-a09-test` intenta conectar.
- Resultado esperado: denegación DAC antes de `accept()` (normalmente `EACCES`); el servidor no debe atribuir este resultado a `SO_PEERCRED`.
- La ruta candidata nunca se chmod/chown para facilitar el acceso.

### A09b — autorización real mediante SO_PEERCRED

- El runner crea un fixture independiente, hermano del sandbox privado, directamente bajo un padre temporal compartido cuya propiedad y sticky bit se verifican (por ejemplo `/tmp`, modo `01777`).
- Directorio del fixture: `0711`; socket de prueba: `0666`. Estos permisos solo pertenecen al fixture efímero y nunca al endpoint candidato.
- El fixture no se coloca dentro del sandbox privado `0700`; eso impediría la travesía al UID externo.
- El servidor usa el handler real de `atlas-admin/1`, con allowlist que no incluye el UID externo. El cliente envía un request fijo e inocuo de `authority.ping`.
- Resultado esperado: el kernel informa el UID real mediante `SO_PEERCRED`; el handler rechaza al peer como `UNAUTHORIZED_PEER` antes de leer/procesar el request y no envía bytes de respuesta de protocolo.
- El runner registra el UID esperado, UID/PID/GID observados, resultado del cliente, cierre/EOF y ausencia de respuesta. No se aceptan credenciales simuladas.

El runner actual no implementa A09a/A09b ni coordinación con un cliente externo. Antes de implementar, debe diseñarse un protocolo de coordinación acotado (ruta/nonce de ejecución, tiempos límite, resultado inequívoco y cleanup) que no abra un canal de órdenes genéricas ni exponga el checkout.

## 5. Secuencia de provisión propuesta (todavía no ejecutar)

1. **Preflight read-only:** confirmar UID/GID disponibles y rango normal en `/etc/login.defs`; comprobar que `atlas-a09-test` no existe; revisar que SSH ya escucha en loopback y que la configuración efectiva permite clave pública y comandos no interactivos; verificar host key conocida. No cambiar configuración.
2. **Crear identidad:** crear grupo y cuenta dedicados con UID asignado automáticamente; HOME privado; shell válida; contraseña bloqueada; sin grupos suplementarios, linger ni servicios. Verificar UID, grupos, HOME, shell, estado de contraseña y ausencia de privilegios.
3. **Preparar clave efímera:** generar Ed25519 en directorio temporal privado de `greed`; instalar solo la pública con restricciones de loopback y `restrict`; verificar propietario y modos.
4. **Probar autenticación mínima:** ejecutar por SSH un comando fijo `id` y comprobaciones de grupos/UID. Exigir UID distinto del runner, GID/grupos esperados y que no pueda leer el checkout. Si falla, detenerse; no relajar PAM/SSH ni desbloquear contraseña.
5. **Orquestar A09:** solo después de una revisión separada del diseño de coordinación y de implementar el cliente/runner, ejecutar A09a y A09b en sesiones independientes. No ejecutar el runner con sudo.
6. **Cerrar sesión y limpiar:** terminar la sesión SSH de prueba; comprobar que no quedan procesos de ese UID; retirar `authorized_keys` y la clave privada temporal; eliminar cuenta/grupo y HOME solo después de comprobar que pertenecen exclusivamente a esta prueba. No borrar indiscriminadamente archivos por UID ni tocar archivos ajenos al HOME.
7. **Verificación posterior:** confirmar que `atlas-a09-test` ya no existe, que no quedan sesiones/procesos/linger/servicios y que SSH/PAM/sudoers/systemd/otras cuentas permanecen sin cambios.

## 6. Riesgos y controles

| Riesgo | Control |
|---|---|
| Reutilizar una identidad de servicio | Cuenta dedicada, sin servicios ni linger; excluir `atlas-sandbox` |
| Ampliar privilegios accidentalmente | UID/GID automáticos; grupo primario único; sin grupos suplementarios |
| Exponer clave privada | Clave efímera bajo runtime privado; solo clave pública en `authorized_keys`; borrado al finalizar |
| Abrir SSH a la red o debilitar autenticación | Solo loopback; clave restringida; no modificar configuración SSH/PAM |
| El usuario externo accede al checkout | HOME propio; checkout no compartido; cliente mínimo sin lectura del repositorio |
| Confundir DAC con autorización | A09a y A09b separados y reportados por separado |
| Dejar residuos | Expiración, cierre de sesión, verificación de procesos y eliminación controlada |
| Alterar servicios existentes | No usar ni detener `atlas-sandbox`; no tocar Docker/rootlesskit/Broker |

## 7. Puertas de autorización

La autorización actual permite diseñar este procedimiento. Antes de modificar Debian se requiere una aprobación explícita adicional para:
- crear `atlas-a09-test` y su grupo;
- instalar la clave pública restringida;
- crear el HOME privado;
- iniciar una sesión SSH local de prueba.

La implementación del cliente/runner A09 requiere además revisión estática en GitHub y aprobación separada antes de ejecutarla. No se modificará el handler, contrato, runtime, SQLite, systemd ni servicios de producción.

## 8. Estado

- Cuenta `atlas-a09-test`: **no creada**.
- Claves: **no generadas ni instaladas**.
- SSH/PAM: **sin cambios**.
- A09a/A09b: **no implementados y no validados**.
- Última evidencia A-IPC-01 comunicada: 15 PASS, A09 SKIP, 0 FAIL; global INCOMPLETE.
- `main`: intacta.
- Transporte de producción: no seleccionado ni aprobado.
