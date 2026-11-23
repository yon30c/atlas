# Evaluación del bootstrap LOCAL: Candidate A/B y separación de privilegios

**Fecha de corte:** 16 de noviembre de 2026  
**Rama:** `feature/terminal-commands`  
**Estado:** evaluación y propuesta; no autoriza cambios en el host.

## 1. Propósito

Registrar la evidencia más reciente de la cadena sudo, aclarar el límite de confianza que introduce el acceso root irrestricto de `greed`, y proponer una separación de identidades antes de implementar un helper privilegiado. Este documento complementa, no reemplaza, los diseños del autenticador PAM, el protocolo de prueba, la arquitectura de coordinación y la frontera de privilegios.

## 2. Estado del host observado

La inspección compartida por el propietario reporta:

- Debian con sudo 1.9.16p2 (sudoers policy plugin y I/O plugin 1.9.16p2).
- `sudo -l`: `greed` puede ejecutar `(ALL : ALL) ALL`.
- Defaults activos: `env_reset`, `mail_badpass`, `secure_path`, `use_pty`.
- `visudo -c` valida sintácticamente los archivos sudoers inspeccionados.
- No se observaron excepciones activas `env_keep` en la salida compartida.

Esto confirma que `greed` tiene autoridad administrativa general a través de sudo. La validación sintáctica de sudoers no demuestra que toda la política sea óptima ni que el host esté libre de otras rutas administrativas.

## 3. Resultados de las dos pruebas `sudo -- sh -c`

### 3.1 Relación de procesos y terminal

La salida del primer comando mostró:

- Proceso `sudo`: PID 13618, PPID 13616, SID 13618, PGID 13618, TPGID 13619, TTY `pts/1`.
- Proceso hijo `sh`: PID 13619, PPID 13618, SID 13618, PGID 13619, TPGID 13619, TTY `pts/1`.
- `tty` del shell: `/dev/pts/1`.
- FD 0 de sudo: `/dev/pts/0`.
- FD 0 del shell hijo: `/dev/pts/1`.

Interpretación: sudo y el hijo aparecen en la misma sesión y terminal reportada, pero el monitor sudo y el comando hijo no comparten el mismo descriptor de entrada. El hijo está en el grupo foreground observado. Esto es compatible con la mediación PTY de sudo y ayuda a explicar por qué no se debe inferir el TTY de origen únicamente desde el descriptor del hijo.

### 3.2 Credenciales del proceso hijo

La segunda ejecución mostró un shell `sh` con UID y GID real, efectivo, saved y filesystem todos en 0. Su `stat` mostró PPID 13645, SID 13645, PGID 13646, TTY 34817 y TPGID 13646.

Interpretación: el proceso hijo ejecutado por sudo tiene credenciales root. La muestra aislada no establece por sí sola la relación completa con el proceso padre ni demuestra estabilidad temporal; debe correlacionarse con snapshots y validaciones del observador.

### 3.3 Qué no demuestran

Estas pruebas no demuestran:
- presencia física del operador;
- autenticidad o procedencia criptográfica de una sesión SSH/PTY;
- autenticación PAM reciente;
- que sudo no pueda cambiar de comportamiento por configuración o versión;
- ausencia de carreras en procfs;
- resistencia frente a root o frente a un usuario que conserva sudo irrestricto;
- autorización CAM ni apertura de Recovery Gate.

No se debe convertir una coincidencia de proceso/TTY en una decisión de autorización.

## 4. Configuración de sudo y modelo de amenaza

Mientras `greed` tenga `(ALL : ALL) ALL`, puede ejecutar comandos root arbitrarios. Por tanto, si actúa maliciosamente, puede modificar o sustituir un helper, su configuración, claves, servicios y mecanismos del host. Un helper root-owned no puede protegerse del propio administrador que tiene capacidad irrestricta para actuar como root.

El helper sí puede ser útil para establecer una frontera entre:
- Assistant, procesos Atlas ordinarios, Skills y consumidores sin privilegios; y
- una operación administrativa acotada, mediada por código root-owned y autenticación PAM.

Pero esa frontera no protege contra el titular de privilegios administrativos generales. La documentación debe declarar esta limitación, no insinuar que el helper convierte sudo en un sandbox.

## 5. Separación de identidades propuesta

Se propone evaluar este modelo:

| Identidad | Función | Autoridad prevista |
|---|---|---|
| `greed` | Usuario cotidiano, cliente local y operador de Atlas | Sin sudo general ni administración directa del host |
| Cuenta administrativa independiente | Mantenimiento y recuperación del Debian | Administración completa, uso excepcional |
| Servicio `atlas` | Ejecutar componentes centrales de Atlas | Privilegios mínimos y recursos explícitamente asignados |

La cuenta administrativa no debe confundirse con el propietario canónico de Atlas. La identidad Unix usada para mantenimiento, el sujeto que realiza el bootstrap y el `UserId` canónico generado por CAM son conceptos distintos que deben vincularse mediante evidencia y política explícitas.

### 5.1 Beneficios esperados

- Reduce la capacidad de un proceso cotidiano comprometido para alterar el host.
- Hace más significativa la frontera entre procesos Atlas sin privilegios y el helper acotado.
- Permite reservar administración del sistema para una cuenta separada.
- Facilita auditar qué operaciones requieren elevación.

### 5.2 Riesgos y condiciones previas

- Pérdida de acceso administrativo si la cuenta nueva no se prueba antes de retirar privilegios.
- Servicios, cron jobs, archivos, sockets, contenedores o tareas pueden depender de UID/GID, HOME o permisos de `greed`.
- Cambiar grupos o sudoers prematuramente puede interrumpir mantenimiento, Docker/Broker o recuperación.
- Una cuenta administrativa separada no protege frente a compromiso de root, kernel o credenciales administrativas.
- La cuenta administrativa debe tener credenciales y un método de recuperación probado y documentado.

### 5.3 Secuencia segura propuesta

1. Inventario read-only de cuentas, grupos, servicios, procesos, tareas programadas, rutas y recursos que dependen de `greed`.
2. Identificar todas las rutas de administración existentes (sudo, grupos privilegiados, sockets, Docker, systemd, consolas y acceso fuera de banda).
3. Diseñar la cuenta administrativa y el mecanismo de recuperación sin aplicarlos todavía.
4. Crear/probar acceso administrativo independiente en una ventana aprobada; comprobar una nueva sesión y una operación inocua de verificación.
5. Migrar dependencias de servicios de forma explícita, sin cambiar la identidad del usuario cotidiano por accidente.
6. Solo tras verificación y aprobación separada, reducir privilegios de `greed`.
7. Ejecutar pruebas de regresión de SSH, Docker/Broker, Atlas, backups y mantenimiento.

Ningún paso de esta secuencia se ha ejecutado. No se debe cambiar sudoers, PAM, systemd, grupos, usuarios, permisos o servicios como parte de una inspección.

## 6. Estado de Candidate A/B

### Candidate A — helper root-owned invocado mediante sudo

**Preferido para seguir evaluando, no aprobado.**

Requisitos que siguen abiertos:
- contrato de invocación y validación de proceso/TTY completo;
- configuración efectiva de sudo para el comando exacto;
- integridad del ejecutable y de la configuración protegida;
- revisión de carreras y revalidación;
- confirmación directa del descriptor en TTY;
- PAM `pam_authenticate` y `pam_acct_mgmt`;
- protocolo de proof canónico, firma, transporte y consumo anti-replay;
- integración transaccional con identidad, binding, evento de génesis y Recovery Gate;
- revisión de código y aprobación explícita antes de cualquier instalación.

La evidencia V3 permite diagnosticar determinados patrones; no aprueba A. La topología de `sudo -- sh -c` es un caso indirecto que el contrato V3 rechaza por padre directo shell. No se debe relajar ese rechazo solo para aceptar envoltorios de shell.

### Candidate B — servicio privilegiado con socket Unix

Alternativa si A no puede satisfacer los requisitos sin debilitar controles. Requiere definir y probar identidad del peer mediante `SO_PEERCRED`, transferencia/validación del TTY con `SCM_RIGHTS`, ciclo de vida del daemon, superficie IPC, control de acceso al socket y recuperación del servicio. Tampoco debe asumirse seguro por el mero uso de un socket.

### Decisión vigente

- A: candidato en evaluación; no aprobado.
- B: alternativa de reserva.
- Helper, PAM dedicado, claves, configuración protegida, proof verifier/consumer y bootstrap CAM: no implementados.
- No hay autorización para instalar, activar o modificar componentes del host.
- CAM no está inicializado por este flujo y Recovery Gate permanece cerrado.

## 7. Próximas fases propuestas para discutir

Esta secuencia es una propuesta de planificación; no reemplaza ni cambia todavía el roadmap general (Fase 4 sigue siendo la prioridad de producto acordada).

| Orden propuesto | Fase | Resultado verificable |
|---:|---|---|
| B0 | Inventario y separación de privilegios | Mapa de dependencias de `greed`, rutas administrativas y plan de recuperación aprobado |
| B1 | Decisión A/B | Contrato de amenaza, invocación y TTY cerrado; A demostrado en prototipo aislado o B seleccionado |
| B2 | Protocolo de bootstrap | Descriptor canónico, prueba firmada, nonce/request/proof IDs, expiración, replay e idempotencia definidos |
| B3 | Coordinación CAM transaccional | Una UoW consume proof, crea identidad y binding, registra génesis y actualiza head/gate atómicamente |
| B4 | Helper y verificador | Helper mínimo sin acceso a CAM; verificador independiente; pruebas negativas y revisión |
| B5 | Integración PAM controlada | Servicio PAM dedicado probado en entorno aislado; pruebas de lockout y no regresión del login normal |
| B6 | Bootstrap integrado | Génesis local verificable de extremo a extremo; Recovery Gate solo cambia tras evidencia válida |
| B7 | Operación y recuperación | Reinicio, pérdida de respuesta, replay, concurrencia, backup/restore y recuperación probados |

No se recomienda empezar por B4 (codificar helper) antes de cerrar B0–B3. La separación de privilegios puede ser una decisión de host independiente, pero no debe aplicarse hasta tener acceso administrativo de recuperación probado.

## 8. Límites explícitos

Este documento no:
- aprueba cambios de cuentas, grupos, sudoers, PAM, systemd o permisos;
- autoriza instalación de paquetes, helper o daemon;
- define aún el formato criptográfico final ni la ubicación de claves;
- declara terminada la evaluación A/B;
- inicializa CAM ni abre Recovery Gate;
- sustituye las fases funcionales de Atlas Assistant/Workstation.



## 9. Decisión de política SSH/PTY posterior — 2026-11-23

El propietario aceptó la recomendación conservadora para la política de invocación:

- Terminal local interactiva: sudo directo.
- SSH: primero abrir shell interactiva con PTY; desde ella ejecutar sudo/helper directamente.
- Rechazar `ssh -t host 'sudo ...'`, incluso con PTY asignado.
- Rechazar SSH sin PTY, comandos remotos no interactivos y wrappers/shells intermedias.

La decisión funcional ya no está pendiente. El mecanismo que demuestre que la solicitud procede de una shell interactiva SSH (y no de un comando remoto con PTY) sí permanece pendiente. La evidencia V3 no resuelve esta distinción: su resultado es diagnóstico, no autorización. Candidate A sigue sin aprobarse; si la condición no puede demostrarse de forma estable y fail-closed, se descarta y B se evalúa independientemente. No se han realizado cambios de host.
