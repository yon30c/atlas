# Auditoría estática de sudo, ejecutable y TTY — bootstrap LOCAL

**Fecha de corte:** 23 de noviembre de 2026  
**Rama:** `work/atlas-mvp-runtime`  
**Estado:** revisión estática/documental; Candidate A no aprobado. No se ejecutaron comandos en el host ni pruebas desde GitHub.  
**Relacionado:** `local-bootstrap-privilege-validation-contract.md`, `local-bootstrap-chain-observer-v3-design.md`, `local-bootstrap-candidate-evaluation-2026-11-16.md`, `local-bootstrap-privilege-boundary.md`.

## 1. Alcance

Esta auditoría revisa la evidencia ya documentada del host, el contrato de privilegios y el código V3. No sustituye una inspección actual de Debian. Distingue:

- **Evidencia reportada por el propietario:** observaciones comunicadas en sesiones anteriores o el 23-11-2026.
- **Hallazgo estático:** lo que el código/documentación implementan realmente.
- **Pendiente de host:** algo que no se puede concluir sin la salida actual de comandos de solo lectura.

No se modifica sudoers, PAM, SSH, systemd, cuentas, grupos, permisos, claves ni servicios.

## 2. Evidencia de sudo ya disponible

La inspección del host documentada el 16-11-2026 reportó:

| Dato | Evidencia reportada | Alcance |
|---|---|---|
| Versión | sudo 1.9.16p2; plugins sudoers e I/O de la misma versión | No prueba integridad del paquete/binario |
| Política del usuario | `greed` puede ejecutar `(ALL : ALL) ALL` | Acceso administrativo general |
| Defaults | `env_reset`, `mail_badpass`, `secure_path`, `use_pty` | No equivale al volcado completo de defaults efectivos para cada comando |
| Entorno | No se observaron excepciones activas `env_keep` en la inspección compartida | Requiere confirmar con la política efectiva actual |
| Sintaxis | `visudo -c` reportado correcto | Solo demuestra que los archivos inspeccionados parsean; no demuestra política segura |

La salida detallada completa de `sudo -ll`, los defaults específicos por comando y la configuración efectiva actual no están incluidos en la evidencia que se ha conservado en este documento.

### 2.1 Consecuencia para el modelo de amenaza

Mientras `greed` conserve `(ALL : ALL) ALL`, esa cuenta puede ejecutar operaciones arbitrarias como root. Por tanto:

- Un helper root-owned no protege contra el propio `greed` si este actúa maliciosamente como administrador.
- La autenticación PAM del helper puede servir como confirmación humana adicional y como frontera frente a procesos Atlas sin privilegios, pero no convierte sudo en sandbox.
- No se debe presentar Candidate A como protección contra compromiso de la cuenta cotidiana que conserva sudo irrestricto.
- La propuesta de separar cuenta cotidiana y cuenta administrativa independiente sigue siendo una decisión de arquitectura/host no aprobada. No se cambia ninguna cuenta ni privilegio durante esta auditoría.

## 3. Auditoría del código V3

### 3.1 Identidad del ejecutable sudo

En `tools/bootstrap-chain-observer/bootstrap_chain_observer.c`, `aco_is_sudo_candidate()` clasifica un proceso como candidato diagnóstico cuando:

- el destino textual de `/proc/PID/exe` tiene basename `sudo`;
- el objeto abierto es regular;
- UID/GID del objeto son 0/0;
- tiene bit setuid;
- no es escribible por grupo ni otros.

El recolector compara dos muestras de metadatos y conserva dispositivo/inode/modo/propietario como datos de estabilidad observada.

**Lo que no hace:** no valida el paquete Debian, versión aprobada, firma/repositorio, hash contra una referencia protegida, ruta canónica aprobada, plugins sudo, integridad de sudoers ni defaults efectivos. La ruta de `readlink` y los metadatos son indicadores de forma, no una raíz de confianza.

**Conclusión:** V3 no puede ser reutilizada como verificador de identidad de sudo para un helper privilegiado. Para Candidate A hace falta una referencia de confianza administrativa y un proceso explícito de actualización tras upgrades; además, se debe revisar el ejecutable real y su paquete en Debian. Un hash aislado copiado a un archivo editable por `greed` no sería una referencia confiable.

### 3.2 Relación de procesos y carreras

V3 exige padre directo compatible con sudo, credenciales esperadas, enlaces PPID, SID/PGID, pidfd y dos muestras. Esto mejora la calidad de la observación, pero el propio contrato reconoce que pidfd no congela ejecutable, credenciales, PPID, SID, PGID o TTY y que procfs no ofrece una instantánea atómica.

**Conclusión:** el resultado positivo es estrictamente diagnóstico. El helper futuro necesitaría revalidaciones en cada fase sensible y un análisis explícito de las carreras residuales. No se puede elevar el resultado V3 a autorización ni afirmar que pidfd resuelve TOCTOU.

### 3.3 Qué comprueba realmente la regla de TTY

La regla actual localiza el primer ancestro que no se clasifica como sudo y exige:

- `origin.stat.tty_nr != 0`;
- `outermost_sudo.stat.tty_nr != 0`;
- ambos `tty_nr` iguales;
- `origin.stat.tpgid == outermost_sudo.stat.pgrp`;
- el TTY del observador está disponible y sus SID/foreground coinciden con el observador.

Esto comprueba una relación entre el **TTY controlador del primer ancestro no sudo** y el proceso sudo monitor más externo según la topología observada. No inspecciona los descriptores del ancestro, no asocia un descriptor `/dev/ptmx` con un PTY esclavo y no autentica el canal SSH.

La evidencia histórica del host indica que:

- SSH interactivo con PTY, entrando primero a una shell y luego ejecutando sudo directo, coincidió diagnósticamente;
- SSH con PTY que ejecuta directamente `sudo -- observer` fue rechazado porque `sshd-session` aparecía como primer ancestro no sudo con `tty_nr=0`;
- una inspección separada observó descriptores `/dev/ptmx` en `sshd-session`, con `fdinfo tty-index` coincidente con el PTY de la shell.

La observación de `/dev/ptmx` demuestra que `tty_nr=0` en `sshd-session` no permite concluir, por sí solo, que no exista un PTY asignado. Pero esa inspección separada no fue incorporada ni validada como una relación de procedencia segura por V3.

**Hallazgo crítico:** V3 no prueba la procedencia del TTY. Prueba una relación de TTY controlador en una cadena de procesos concreta. Su rechazo de la invocación SSH remota directa no demuestra que esa conexión careciera de PTY; demuestra que no cumplió la regla de ancestro/TTY implementada.

### 3.4 Ambigüedad funcional pendiente

La política de producto dice que se admite “SSH interactivo con PTY” y se rechaza “SSH sin PTY y toda ejecución no interactiva”. Hay que distinguir dos interpretaciones antes de diseñar el mecanismo:

1. **Shell interactiva:** solo se acepta una sesión SSH que inicia una shell interactiva y desde ella ejecuta sudo.
2. **Cualquier solicitud SSH con PTY:** también se acepta `ssh -t host 'sudo ...'` si el servidor asignó un PTY, aunque el cliente envíe un comando remoto en vez de abrir una shell interactiva.

Los resultados actuales no permiten declarar que ambas políticas sean equivalentes. La interpretación elegida cambia el criterio de aceptación y las pruebas negativas. Ninguna implementación debe inferirla.

## 4. Matriz de decisión actual

| Control | Estado | Decisión |
|---|---|---|
| sudo 1.9.16p2 y defaults generales | Evidencia histórica reportada | Reconfirmar en host |
| Regla `greed: (ALL : ALL) ALL` | Evidencia histórica reportada | Modelo de amenaza explícito; no defender contra root/greed malicioso |
| Defaults efectivos para el helper exacto | No demostrados con salida completa | Bloqueador de A |
| Identidad del binario/paquete sudo | No demostrada por V3 | Bloqueador de A |
| Integridad y procedencia del TTY | No demostradas | Bloqueador de A |
| V3 build/tests y escenarios directos/sudo | Validados por el propietario el 23-11-2026 | Solo diagnóstico |
| Revisión de carreras en helper real | No implementada | Bloqueador de A |
| Candidate B (socket + SO_PEERCRED + SCM_RIGHTS) | Diseño alternativo, no probado | No aprobado automáticamente |

## 5. Evidencia de solo lectura que falta en Debian

Cuando se recoja la siguiente evidencia, ejecutar desde la sesión normal de `greed`. No cambiar configuración ni instalar herramientas.

### 5.1 Sudo efectivo

```bash
printf '%s\n' '===== SUDO VERSION / BUILD ====='
sudo -V
printf '%s\n' '===== PRIVILEGIOS EFECTIVOS COMPLETOS ====='
sudo -ll
printf '%s\n' '===== REGLA PARA LA RUTA PROPUESTA ====='
sudo -ll /usr/libexec/atlas/local-bootstrap-authenticator
printf '%s\n' '===== SINTAXIS SUDOERS ====='
sudo visudo -c
printf '%s\n' '===== DIRECTIVAS RELEVANTES ====='
sudo grep -RInE '^[[:space:]]*(Defaults|#include|@include)|env_reset|env_keep|env_delete|setenv|secure_path|timestamp_type|use_pty|requiretty|!authenticate|NOPASSWD|SETENV|PASSWD' /etc/sudoers /etc/sudoers.d 2>/dev/null
```

`sudo -ll` es la evidencia principal de privilegios/defaults que sudo muestra para el usuario actual. El grep es solo inventario textual: no resuelve por sí solo orden, precedencia, includes, aliases ni coincidencia efectiva de reglas. `visudo -c` valida sintaxis, no política.

La ruta del helper todavía no existe; la consulta de esa ruta es una comprobación de la regla prevista, no prueba de que el helper esté instalado. Si sudo no acepta la forma de consulta, conservar el error sin improvisar cambios.

### 5.2 Identidad del ejecutable y paquete sudo

```bash
sudo_bin=$(readlink -f "$(command -v sudo)")
printf 'sudo_path=%s\n' "$sudo_bin"
stat -Lc 'path=%n type=%F owner=%U:%G mode=%a (%A) dev=%D inode=%i' "$sudo_bin"
dpkg-query -S "$sudo_bin"
dpkg-query -W -f='${Package} ${Version} ${Architecture}\n' sudo
dpkg -V sudo
sha256sum "$sudo_bin"
getcap "$sudo_bin" 2>/dev/null || true
namei -l "$sudo_bin"
```

Esto aporta ruta resuelta, metadatos, propietario de paquete, versión instalada, verificación disponible del paquete, digest de la muestra y permisos de los directorios padres. El digest solo sirve como evidencia de esa muestra: para ser ancla de confianza debe compararse con una referencia autenticada y protegida, no con un valor que el mismo usuario cotidiano pueda modificar.

### 5.3 Datos que deben revisarse antes de compartir

- Revisar la salida de `sudo -ll` para descartar datos de rutas/comandos que no se quieran compartir.
- No compartir contraseñas, tokens, claves ni contenido de archivos privados.
- La salida no debe incluir el contenido de sudoers completo si no es necesario; las directivas y defaults relevantes son suficientes.

## 6. Recomendación y puerta de decisión

1. Mantener V3 como observador diagnóstico; no reutilizar su resultado como prueba de autorización.
2. No implementar ni instalar el helper, no activar PAM y no generar claves todavía.
3. Reconfirmar en Debian la política efectiva y la identidad del paquete/binario con §5.
4. Resolver explícitamente si “SSH interactivo con PTY” significa shell interactiva o cualquier sesión SSH que tenga PTY asignado.
5. Diseñar una comprobación de TTY basada en evidencia real de descriptores/procesos del host, con pruebas de shell interactiva, comando remoto con `-t`, SSH sin PTY y terminal local. Si no puede distinguirse de forma estable lo que la política requiere, Candidate A se descarta sin relajar la política.
6. Revisar Candidate B por separado; `SO_PEERCRED` autentica credenciales del peer del socket, no la procedencia de un TTY transferido. El receptor debe validar el descriptor recibido y mantener el mismo modelo de amenaza. B no es automáticamente más seguro.

**Decisión actual:** Candidate A sigue sin aprobación para ejecución privilegiada. La evidencia V3 del 23-11-2026 no cierra la política efectiva de sudo, la identidad del ejecutable ni la procedencia del TTY. No se ha cambiado el host ni se han ejecutado pruebas desde GitHub.


## 7. Evidencia adicional recibida del propietario — 2026-11-23

Se recibió una nueva captura de solo lectura desde Debian 13, VM `Atlas-VM-test`. Esta evidencia sustituye las dudas históricas solo para los campos que muestra; no constituye aprobación de Candidate A.

### 7.1 Política sudo efectiva

`sudo -V` reportó:

- Sudo, plugin sudoers, gramática sudoers y plugins I/O/audit: versión `1.9.16p2`.
- Paquete Debian: `sudo 1.9.16p2-3+deb13u2 amd64`.

`sudo -ll` reportó para `greed`:

- Defaults efectivos mostrados: `env_reset`, `mail_badpass`, `secure_path=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin` y `use_pty`.
- Regla efectiva en `/etc/sudoers`: `RunAsUsers: ALL`, `RunAsGroups: ALL`, comando `ALL`.

La búsqueda textual compartida no encontró directivas activas adicionales de `env_keep`, `SETENV`, `NOPASSWD`, `requiretty` o similares en los archivos inspeccionados; sí mostró los defaults e includes descritos. Este grep no reemplaza el resultado efectivo de sudo.

La consulta `sudo -ll /usr/libexec/atlas/local-bootstrap-authenticator` devolvió `command not found`. La ruta propuesta aún no existe; por tanto, no se obtuvo un conjunto de defaults/reglas efectivo para el helper concreto. No debe interpretarse como una regla sudoers específica ya instalada.

`sudo visudo -c` reportó que `/etc/sudoers` y `/etc/sudoers.d/README` parsean correctamente. Esto acredita sintaxis, no restricción de privilegios.

### 7.2 Identidad observada del binario

La captura reportó:

| Campo | Resultado |
|---|---|
| Ruta resuelta | `/usr/bin/sudo` |
| Tipo | Archivo regular |
| Propietario | `root:root` |
| Modo | `4755` (`-rwsr-xr-x`) |
| Paquete propietario | `sudo` |
| Versión/arquitectura | `1.9.16p2-3+deb13u2 amd64` |
| SHA-256 observado | `a59f393bad5037644b89de64fe558ae6d5d1473c25c63022241e7c7019ad2f0c` |
| File capabilities | `getcap` no mostró ninguna |
| Componentes de ruta | `/`, `/usr`, `/usr/bin` y el binario aparecen propiedad root; directorios con modo `755` |

La huella SHA-256 identifica la muestra observada, pero no se comparó con un digest obtenido de una fuente autenticada independiente. No es todavía una raíz de confianza ni una política de actualización.

### 7.3 Verificación dpkg inconclusa

El comando compartido fue `dpkg -V sudo` sin privilegios root y mostró:

```text
????????? c /etc/sudoers
????????? c /etc/sudoers.d/README
```

La verificación de esos archivos queda **inconclusa**. Los signos de interrogación no se deben interpretar como una modificación confirmada ni como integridad confirmada. La ejecución no privilegiada no aportó evidencia suficiente para verificar esos archivos protegidos.

Para cerrar únicamente esta comprobación, ejecutar:

```bash
sudo dpkg -V sudo
```

Si no produce salida, registrar exactamente que `dpkg -V` no reportó discrepancias para los archivos que puede verificar según los metadatos del paquete; no convertirlo en prueba criptográfica de procedencia del paquete ni de que sudoers sea una política segura. Si produce salida, compartirla sin editar archivos.

### 7.4 Consecuencias y estado actualizado

- La política irrestricta `greed: (ALL : ALL) ALL` queda reconfirmada en la VM. Candidate A no puede defenderse de `greed` actuando como root; esta limitación ya forma parte explícita del modelo de amenaza.
- Los defaults generales efectivos indicados por `sudo -ll` quedan reconfirmados. La política efectiva de la ruta helper sigue sin verificarse porque el ejecutable no existe.
- La identidad de ruta, paquete, versión, propietario, modo y hash de `/usr/bin/sudo` queda inventariada. La confianza criptográfica de ese binario y la integridad verificable de los archivos sudoers no quedan demostradas por esta captura.
- No se modificó sudoers, PAM, SSH, systemd, usuarios, grupos, permisos, claves ni servicios. No se instaló helper y no se ejecutaron pruebas desde GitHub.

**Matriz actualizada:** política general de sudo y paquete/binario inventariados; regla del helper aún no aplicable; verificación dpkg pendiente de repetición como root; procedencia del TTY y resolución de la ambigüedad SSH/PTY siguen abiertas. Candidate A continúa **no aprobado**.



## 8. Decisión de política SSH/PTY — 2026-11-23

El propietario acepta la recomendación conservadora: **solo se admite una sesión SSH que establezca primero una shell interactiva con PTY y desde esa shell se invoque el helper mediante sudo directo**.

### 8.1 Casos permitidos y rechazados

| Escenario | Política |
|---|---|
| Terminal local interactiva y sudo directo | Permitido, sujeto a los demás controles |
| SSH con PTY, abrir shell interactiva y ejecutar sudo directo desde ella | Permitido, sujeto a los demás controles |
| `ssh -t host 'sudo ...'` (comando remoto directo, aunque tenga PTY) | Rechazado |
| SSH sin PTY | Rechazado |
| Comando remoto no interactivo | Rechazado |
| Shell/wrapper intermedio entre shell interactiva y sudo/helper | Rechazado |

La política se refiere al flujo de invocación requerido; **no afirma que la implementación actual pueda demostrarlo de forma segura**. El hecho de que V3 haya coincidido diagnósticamente en una shell SSH interactiva es evidencia de topología observada, no autenticación del canal SSH ni prueba suficiente para conceder autoridad.

### 8.2 Consecuencia para V3 y Candidate A

- V3 permanece como observador no privilegiado y exclusivamente diagnóstico.
- Su regla actual puede reconocer algunos casos de shell interactiva seguida de sudo directo, pero no autentica que el origen sea una shell SSH interactiva ni demuestra la procedencia del PTY.
- No se debe convertir el patrón V3 en autorización ni ampliar la regla para aceptar `sshd-session` a partir de `/dev/ptmx`/ `tty-index` sin un contrato y validación específicos.
- El diseño siguiente debe demostrar de forma fail-closed la diferencia entre una shell interactiva de sesión y un comando remoto con PTY. Si no puede probarse de forma estable, Candidate A se descarta; no se relaja la política.
- La política general `greed: (ALL : ALL) ALL` sigue limitando el modelo de amenaza: el helper no protege frente a ese usuario actuando como root.

**Decisión funcional cerrada; mecanismo técnico abierto.** Candidate A continúa no aprobado. No se implementó helper ni se modificó PAM, sudoers, SSH, systemd o el host.


## 9. Auditoría de la frontera de petición SSH — 2026-11-23

### 9.1 Verificación del paquete sudo completada

El propietario ejecutó en Debian 13 / Atlas-VM-test:

    sudo dpkg -V sudo

La salida fue vacía. Se registra como: **dpkg no reportó discrepancias en los archivos del paquete que pudo verificar**. No es una verificación criptográfica independiente, no demuestra que la política sudo sea segura y no elimina la limitación de greed: (ALL : ALL) ALL. La comprobación pendiente de §7.3 queda cerrada en ese alcance limitado.

### 9.2 OpenSSH conoce una distinción que V3 no observa

La revisión de OpenSSH identifica una frontera más temprana que procfs:

- Petición de shell sin comando: OpenSSH ejecuta la login shell con argv[0] precedido por - y sin -c.
- Petición exec: OpenSSH ejecuta la login shell con -c y el comando solicitado.
- Asignar PTY no convierte una petición exec en una petición de shell. Un comando remoto puede recibir PTY.

El código de OpenSSH muestra ambas formas de invocación en do_child() y la asignación del TTY en do_exec_pty(): [session.c — OpenSSH](https://github.com/openssh/openssh-portable/blob/master/session.c). La documentación de ForceCommand especifica que se aplica a shell, command y subsystem, y expone el comando original mediante SSH_ORIGINAL_COMMAND: [sshd_config(5)](https://man.openbsd.org/sshd_config.5).

Por ello, la política aprobada no puede demostrarse solo con tty_nr, tpgid, SSH_TTY ni el PTY master observado en sshd-session.

### 9.3 Alternativa de diseño identificada

Se añadió [local-bootstrap-sshd-session-gate-design.md](local-bootstrap-sshd-session-gate-design.md). Evalúa una puerta C root-owned como login shell de una cuenta SSH administrada, combinada con un ForceCommand administrativo fijo. La puerta recibiría la invocación de OpenSSH antes de iniciar la shell real, distinguiría comando original de petición de shell, exigiría TTY controlador y luego haría execve() de la shell real sin dejar un proceso intermediario.

La alternativa es **prometedora, no aprobada**. Requiere, entre otros puntos, validar la versión Debian exacta de OpenSSH, la configuración efectiva de todos los listeners, la protección de SSH_ORIGINAL_COMMAND, el tratamiento de SFTP/subsystems, la inmutabilidad administrativa de la login shell, el forwarding, la cadena sudo→shell→sshd y los casos de wrapper/exec. La documentación de ForceCommand advierte que no deshabilita por sí sola los distintos tipos de forwarding.

### 9.4 Estado de decisión

- V3 continúa siendo observador diagnóstico; no se reutiliza como autorización.
- La inferencia posterior basada solo en procfs/TTY no demuestra el tipo de petición SSH.
- La puerta de sesión administrada por sshd pasa a ser la siguiente alternativa que merece evaluación aislada; no se implementa ni instala en este incremento.
- El helper todavía tendría que verificar la cadena de procesos y rechazar wrappers. La posibilidad de distinguir un reemplazo deliberado de shell mediante exec sigue siendo un límite abierto.
- Si los requisitos de política no pueden demostrarse con evidencia estable, Candidate A se descarta sin relajar la política.

No se modificaron sudoers, PAM, sshd, cuentas, shells, systemd, claves, permisos ni host. No se ejecutaron pruebas desde GitHub.
