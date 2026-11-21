# Diseño — identidad temporal para A09 (A-IPC-01)

**Estado:** cuenta temporal creada y verificada por el propietario en Debian; instalación de clave SSH y sesión de prueba todavía no autorizadas.  
**Rama:** `experiment/a-ipc-01-private-unix-listener-probe`.  
**Propósito:** proporcionar un peer Linux de UID distinto para A09a (DAC) y A09b (SO_PEERCRED), sin reutilizar cuentas de servicios ni permitir que el runner cambie credenciales.

## 1. Decisión y límites

El propietario autorizó expresamente crear la cuenta y el grupo dedicados. El propietario confirmó que la creación terminó correctamente y aportó la verificación de identidad, grupos, contraseña y HOME. Esta autorización no cubre la instalación de claves, el inicio de sesión SSH, la ejecución A09 ni cambios de SSH/PAM/firewall.

La cuenta existente `atlas-sandbox` queda expresamente excluida: UID 997, contraseña bloqueada, linger activo y procesos de Atlas Broker/rootless containers. No iniciar sesión con ella, cambiar su contraseña, detener sus procesos ni reutilizarla como peer.

El procedimiento debe producir dos identidades de proceso reales:
- servidor/runner bajo la cuenta ordinaria propietaria del checkout (actualmente `greed`, UID 1000);
- cliente bajo `atlas-a09-test`, con UID distinto asignado automáticamente por el sistema.

No se utilizarán mocks de credenciales, `setuid()`, `sudo -u`, `su`, `runuser`, capabilities ni mecanismos de cambio de UID dentro del runner. La sesión cliente se autenticará de forma independiente mediante el mecanismo SSH existente, si ya lo permite.

## 2. Cuenta temporal creada y verificada

Nombre: `atlas-a09-test`.

Propiedades observadas en Debian según la salida comunicada por el propietario:
- passwd: `atlas-a09-test:x:1001:984::/var/lib/atlas-a09-test:/bin/bash`; UID `1001`, GID primario `984`;
- grupo dedicado: `atlas-a09-test:x:984:`;
- `id`: `uid=1001(atlas-a09-test) gid=984(atlas-a09-test) grupos=984(atlas-a09-test)`; no aparecen grupos suplementarios adicionales;
- `passwd -S`: estado `L` (contraseña bloqueada);
- HOME `/var/lib/atlas-a09-test`, directory, owner/group `atlas-a09-test`, modo `0700`;
- shell `/bin/bash`.

La cuenta cumple el aislamiento de identidad solicitado. La salida no demuestra por sí sola ausencia de procesos/sesiones/servicios/linger; esos puntos deben comprobarse antes y después de la prueba SSH.

Propiedades de diseño restantes:
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

## 5. Secuencia restante (no ejecutar sin aprobación específica)

1. **Identidad:** completada por el propietario. UID `1001`, GID `984`, grupo primario dedicado, sin grupos suplementarios adicionales, HOME `0700`, shell `/bin/bash`, contraseña bloqueada.
2. **Preflight SSH:** completado de forma read-only. `sshd` efectivo informa `pubkeyauthentication yes`, `passwordauthentication yes`, `kbdinteractiveauthentication no`, `usepam yes`, `strictmodes yes`, `permituserenvironment no`, pero también `x11forwarding yes`, `allowtcpforwarding yes` y `allowagentforwarding yes`. No modificar la configuración global; la clave de prueba debe usar `restrict`, `from=127.0.0.1` y comando forzado.
3. **Alcance de red:** SSH escucha en `0.0.0.0:22` y `[::]:22`. El ruleset nftables comunicado muestra políticas `INPUT accept` para IPv4 e IPv6; no se ha demostrado un filtro general que limite SSH a loopback. Por tanto, el daemon no está limitado a loopback. La opción `from=127.0.0.1` restringiría únicamente la clave de prueba, no la exposición global del servicio. No modificar firewall ni SSH dentro de este experimento.
4. **Host key:** `ssh-keyscan` obtuvo ED25519 `SHA256:txiDPT+/ldcIwnN6BPotbeL7QsofAieAeqF3GKMa9xI`, coincidente con el fingerprint local previamente leído de `/etc/ssh/ssh_host_ed25519_key.pub`. RSA/ECDSA también fueron anunciadas, pero la prueba deberá fijar ED25519. El archivo temporal de known_hosts no equivale todavía a una autenticación SSH probada.
5. **Preparar clave efímera:** pendiente de aprobación separada. Generar Ed25519 en runtime privado de `greed`; instalar solo la pública con `from=127.0.0.1`, `restrict` y comando forzado; verificar propietario/modos. No copiar la privada al HOME peer ni al repositorio.
6. **Probar autenticación mínima:** pendiente de aprobación separada. Ejecutar por SSH solo un comando fijo de identidad; usar `IdentitiesOnly`, `BatchMode`, `StrictHostKeyChecking=yes` y `HostKeyAlgorithms=ssh-ed25519` con known_hosts temporal previamente verificado. Si falla, detenerse; no relajar PAM/SSH ni desbloquear contraseña.
7. **Orquestar A09:** requiere revisión estática del diseño de coordinación, implementación del cliente/runner y aprobación separada. A09a/A09b deben ejecutarse en sesiones independientes; nunca ejecutar el runner con sudo.
8. **Cerrar sesión y limpiar:** después de la prueba autorizada, terminar sesión; comprobar que no quedan procesos del UID; retirar `authorized_keys` y clave privada temporal; la eliminación de cuenta/grupo/HOME requiere autorización separada.
9. **Verificación posterior:** confirmar ausencia de residuos y que SSH/PAM/sudoers/systemd/otras cuentas permanecen sin cambios.

## 6. Riesgos y controles

| Riesgo | Control |
|---|---|
| Reutilizar una identidad de servicio | Cuenta dedicada, sin servicios ni linger; excluir `atlas-sandbox` |
| Ampliar privilegios accidentalmente | UID/GID automáticos; grupo primario único; sin grupos suplementarios |
| Exponer clave privada | Clave efímera bajo runtime privado; solo clave pública en `authorized_keys`; borrado al finalizar |
| Exposición de SSH | El daemon escucha en todas las interfaces y INPUT es ACCEPT; no afirmar aislamiento global. La clave experimental se restringe a origen loopback y `restrict`; no modificar configuración SSH/PAM/firewall |
| El usuario externo accede al checkout | HOME propio; checkout no compartido; cliente mínimo sin lectura del repositorio |
| Confundir DAC con autorización | A09a y A09b separados y reportados por separado |
| Dejar residuos | Expiración, cierre de sesión, verificación de procesos y eliminación controlada |
| Alterar servicios existentes | No usar ni detener `atlas-sandbox`; no tocar Docker/rootlesskit/Broker |

## 7. Puertas de autorización

La autorización para crear la identidad fue concedida y consumida. El propietario confirmó la creación del grupo, cuenta y HOME; no se requieren más cambios para esa fase. Antes de modificar Debian se requiere aprobación explícita separada para:
- generar e instalar la clave pública restringida en `authorized_keys`;
- iniciar una sesión SSH local de prueba.

La implementación del cliente/runner A09 requiere además revisión estática en GitHub y aprobación separada antes de ejecutarla. La eliminación futura de la cuenta/grupo/HOME también requerirá aprobación separada. No se modificará el handler, contrato, runtime, SQLite, systemd ni servicios de producción.

## 8. Estado

- Cuenta `atlas-a09-test`: **creada y verificada por el propietario**; UID `1001`, GID `984`, grupo primario dedicado, sin grupos suplementarios adicionales, HOME `0700`, shell `/bin/bash`, contraseña bloqueada.
- Claves: **no generadas ni instaladas**; no se ha probado autenticación SSH.
- SSH/PAM/firewall: **sin cambios**. El daemon escucha en todas las interfaces; la clave experimental, si se autoriza, deberá limitarse a loopback.
- Host key ED25519 de loopback verificada por fingerprint coincidente: `SHA256:txiDPT+/ldcIwnN6BPotbeL7QsofAieAeqF3GKMa9xI`.
- A09a/A09b: **no implementados y no validados**.
- Última evidencia A-IPC-01 comunicada: 15 PASS, A09 SKIP, 0 FAIL; global INCOMPLETE.
- `main`: intacta.
- Transporte de producción: no seleccionado ni aprobado.
