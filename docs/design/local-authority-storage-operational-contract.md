# Contrato operativo de almacenamiento de autoridad local

**Estado:** decisión de arquitectura aprobada por el propietario; contrato previo a implementación y despliegue.  
**Fecha:** 18 de noviembre de 2026.  
**Alcance:** futura instancia principal de Atlas en un único host Debian.  
**Identidad de servicio propuesta:** `atlas-runtime`.

Este documento fija la frontera operativa de la futura base SQLite de autoridad. No declara que la base exista, que la composición esté conectada al runtime, que el host esté preparado ni que se haya autorizado provisioning real.

## 1. Decisión

La futura autoridad local utilizará una base SQLite dedicada, propiedad de una identidad Linux de servicio exclusiva:

- Usuario y grupo: `atlas-runtime`.
- Cuenta de sistema sin login interactivo.
- Sin pertenencia a `sudo`, `docker` ni grupos privilegiados innecesarios.
- No reutilizar las identidades existentes `greed`, `atlas` o `atlas-sandbox`.
- Todos los procesos que abran la base para escritura, incluidas migraciones y provisioning, deben ejecutarse con UID/GID de `atlas-runtime`.

La identidad administrativa del host y la identidad que ejecuta transacciones de autoridad son responsabilidades distintas. La autoridad del operador se valida en la frontera administrativa; la escritura SQLite ocurre bajo la identidad de servicio.

Esta decisión sustituye, para la futura base principal de autoridad, cualquier supuesto previo de que el archivo SQLite deba ser escribible por root/operador y no por el runtime. No cambia los permisos ni el comportamiento de ninguna base existente.

## 2. Rutas y permisos objetivo

Estructura propuesta:

```text
/var/lib/atlas-runtime/                 atlas-runtime:atlas-runtime  0700
└── authority/                          atlas-runtime:atlas-runtime  0700
    ├── authority.sqlite3               atlas-runtime:atlas-runtime  0600
    ├── authority.sqlite3-wal           atlas-runtime:atlas-runtime  0600*
    ├── authority.sqlite3-shm           atlas-runtime:atlas-runtime  0600*
    └── backups/                        atlas-runtime:atlas-runtime  0700
```

`*` WAL y SHM son archivos auxiliares administrados por SQLite; su existencia y ciclo de vida dependen de la actividad de la base. No deben crearse, copiarse, renombrarse ni borrarse manualmente.

Requisitos:

1. Los directorios que contienen la base son privados para `atlas-runtime` (modo objetivo `0700`).
2. La base y archivos persistentes son accesibles solo por su propietario (modo objetivo `0600`).
3. Los procesos usan `UMask=0077`.
4. El almacenamiento reside en filesystem local con locking y sincronización compatibles con SQLite. NFS y filesystem compartido no validado quedan fuera del baseline.
5. Ningún usuario humano obtiene escritura directa por pertenencia a grupo.
6. El runtime no comparte la base con conversaciones, broker experimental, logs u otros dominios.

Los modos indicados son el estado objetivo que deberá verificarse, no comandos de instalación ni evidencia de que ya estén aplicados.

## 3. Frontera de privilegios para operaciones administrativas

### 3.1 Separación obligatoria

Las operaciones administrativas de autoridad —provisioning offline, y las futuras herramientas de migración/diagnóstico que requieran autorización— tienen dos etapas conceptuales:

**Etapa privilegiada de autorización del operador**
- Verifica que la invocación provenga de la ruta administrativa aprobada.
- Verifica UID real/efectivo y metadatos de sudo según el modelo de amenaza aprobado.
- Exige terminal interactiva en foreground cuando la operación lo requiera.
- Solicita y valida confirmación tipada del alcance exacto y motivo.
- Captura procedencia del operador: UID real, identidad/atributos de sesión confiables disponibles, TTY, timestamp, operation ID y alcance confirmado.
- No abre, migra, consulta ni escribe SQLite.

**Etapa de ejecución de autoridad**
- Se ejecuta con UID/GID de `atlas-runtime`, sin privilegios root recuperables.
- Recibe únicamente una solicitud validada y la evidencia de procedencia por un canal local estrecho, no falsificable por argumentos ordinarios del usuario.
- Abre la base y realiza la transacción.
- Valida de nuevo invariantes de dominio, esquema, checksums, alcance e idempotencia.
- No confía en que la validación de dominio haya ocurrido únicamente en el frontend privilegiado.

La frontera privilegiada no debe conservar un descriptor SQLite abierto, conexión heredada, archivo temporal escribible por root ni ruta alternativa que permita que root cree/modifique la base o sus sidecars.

### 3.2 Requisito de delegación

El mecanismo concreto para pasar del proceso privilegiado al proceso `atlas-runtime` queda pendiente de diseño e implementación. Debe ser pequeño, revisable y fail-closed. Debe demostrar:

- La identidad de ejecución del writer es realmente `atlas-runtime`.
- El proceso hijo no conserva EUID/EGID 0, capacidades Linux ni posibilidad de recuperar privilegios.
- No existe una ventana TOCTOU que permita sustituir ejecutable, configuración, base o directorios entre validación y apertura.
- El canal que transporta la confirmación/procedencia no puede ser reemplazado por datos del solicitante.
- Los errores, cancelaciones y desconexiones no dejan operaciones parciales.
- El frontend no puede invocar rutas arbitrarias ni convertirse en un proxy general de comandos.
- La auditoría distingue claramente al **operador que autorizó** de la **identidad Linux que ejecutó**.

No se aprueba todavía una implementación específica basada en `setuid`, `setpriv`, shell wrappers, pipes, variables de entorno o argumentos. Cada alternativa requiere análisis de seguridad y pruebas adversariales. No se debe implementar una cadena privilegiada improvisada.

### 3.3 Modelo de amenaza y límite de root

Un administrador root del host puede modificar ejecutables, configuración, usuarios, permisos y datos. Este contrato no pretende proteger la base frente a un administrador root malicioso con control irrestricto del host. La separación evita que el flujo normal de escritura de Atlas use root y limita los privilegios del runtime; no convierte el host en una frontera inviolable frente a root.

El acceso de operadores humanos debe gestionarse mediante sudoers y controles del host. La cuenta de servicio no obtiene sudo.

## 4. Relación con el CLI de provisioning existente

El CLI implementado actualmente exige EUID 0, valida UID real, TTY/foreground y confirmación tipada, y abre directamente la base desde el mismo proceso privilegiado. Esa implementación fue diseñada bajo una premisa de filesystem distinta.

**Estado para el futuro despliegue principal: NO APTO PARA EJECUTAR CONTRA LA NUEVA BASE.**

Hasta que sea adaptado y validado:
- No ejecutar `offline_association_provisioning_cli` con `--database` apuntando a la futura `authority.sqlite3`.
- No conceder a root/operador escritura ordinaria sobre el directorio de autoridad para acomodar el CLI actual.
- No cambiar la propiedad de la base a root.
- No interpretar el hecho de que el CLI pase sus pruebas actuales como validación de esta nueva frontera.

La adaptación deberá conservar los guards de invocación y la procedencia del operador, pero separar el frontend privilegiado del writer no privilegiado según §3. La procedencia del operador no debe confundirse con un Atlas USER identity ni con la identidad Linux de ejecución.

## 5. Base única y composición transaccional

La composición raíz de autoridad deberá:

1. Construir una sola instancia de `SQLiteDatabase` para la ruta configurada de autoridad.
2. Construir una sola `SQLiteLocalAuthorityUnitOfWorkFactory` ligada a esa instancia.
3. Inyectar la misma UoW/factory a los servicios que deban compartir una transacción de autoridad.
4. Mantener writers lifecycle y sus ledgers dentro de la misma frontera transaccional.
5. Evitar adaptadores o conexiones paralelas que escriban las mismas entidades fuera de esa UoW.

El alcance previsto incluye las áreas ya agrupadas por `SQLiteLocalAuthorityUnitOfWork`: Identity, Platform Admin, Agent Identity, native identity/authentication, delegations, Project/Environment, Workspace, associations, authority changes y recovery evidence.

La ruta de base será configuración de despliegue, no constante de código ni la ruta de conversaciones. No se considera que la presencia de la UoW o de la composición lifecycle en el repositorio implique que exista un runtime principal conectado.

## 6. Migraciones

- Las migraciones se ejecutan mediante una operación explícita y controlada, como `atlas-runtime`.
- El arranque normal del runtime no aplica migraciones.
- La herramienta verifica versión actual, secuencia completa, checksums y compatibilidad antes de escribir.
- Las migraciones publicadas son inmutables; una discrepancia de checksum bloquea la operación.
- El proceso de migración no debe crear una DB vacía accidentalmente al recibir una ruta incorrecta.
- Fallos o resultados ambiguos detienen la activación y requieren diagnóstico.
- Provisioning de asociaciones verifica el esquema requerido, pero no ejecuta migraciones.

La creación inicial de directorios/identidad del sistema pertenece a la instalación del host. La escritura del esquema pertenece a la identidad `atlas-runtime`. Son operaciones separadas.

## 7. Runtime y systemd

La unidad del futuro runtime deberá cumplir como mínimo:

| Propiedad | Requisito |
|---|---|
| User / Group | `atlas-runtime` |
| UMask | `0077` |
| NoNewPrivileges | `yes` |
| ProtectSystem | `strict` |
| ProtectHome | `yes` |
| PrivateTmp | `yes` |
| Escritura | Solo directorios de estado estrictamente necesarios |
| Capacidades Linux | Ninguna salvo justificación documentada y aprobación |

Puede utilizarse `StateDirectory=atlas-runtime` para el directorio base si la unidad y el ciclo de vida de systemd lo justifican. La subcarpeta `authority/` debe crearse con propietario y modo explícitos. No se reutiliza ni modifica la unidad experimental actual como parte de esta decisión.

Skills, plugins y procesos conversacionales no reciben acceso directo al archivo SQLite. Las operaciones deben pasar por servicios y capacidades de aplicación autorizados. Ninguna skill puede elevar sus permisos ni cambiar la identidad del proceso.

## 8. Backups y recuperación

El backup de autoridad será independiente del backup de conversaciones.

### Backup

1. Obtener snapshot consistente mediante la API de backup SQLite, no copiando solo el archivo principal activo.
2. Verificar `PRAGMA integrity_check`.
3. Verificar esquema, migraciones y checksums.
4. Cifrar con cifrado autenticado.
5. Restringir permisos del artefacto.
6. Mantener claves fuera de la base restaurable y fuera del mismo conjunto de backup.
7. Registrar versión de esquema, timestamp, identificador de backup y resultado de validación.
8. Mantener al menos una copia fuera del directorio de datos y, preferiblemente, fuera del mismo disco físico.

### Restauración

- No restaurar encima de una base activa.
- Detener consumidores y aislar la ruta destino.
- Verificar autenticidad antes de aceptar el contenido descifrado.
- Restaurar a una ruta nueva y privada, propiedad de `atlas-runtime`.
- Validar integridad SQLite y ledger antes de activar runtime.
- Conservar la base anterior hasta completar la verificación y autorización de corte.
- Documentar el punto de recuperación (RPO) y tiempo de recuperación (RTO) una vez medidos.

El cifrado autenticado protege confidencialidad e integridad del artefacto, pero no demuestra que sea el backup más reciente. Anti-rollback requiere un ancla externa de estado/versión no restaurable junto con la DB. Su tecnología, custodia y protocolo quedan pendientes de diseño.

## 9. Claves y secretos

- Claves de firma, HMAC, cifrado y trust anchors no se guardan en tablas restaurables junto con la autoridad.
- No se incluyen en el repositorio, argumentos CLI, logs ni backups ordinarios sin una política explícita.
- El diseño debe definir almacenamiento, permisos, rotación, recuperación, revocación y disponibilidad de claves.
- La pérdida o indisponibilidad de una clave necesaria debe fallar cerrado; no se genera una clave de reemplazo automáticamente al iniciar.
- La restauración de DB y la recuperación de claves deben coordinarse sin hacer que el backup restaurable se convierta en su propia raíz de confianza.

Quedan abiertas la ubicación concreta de claves y la separación entre clave de cifrado de backup, claves de autenticación de autoridad y trust anchor.

## 10. Auditoría

Las operaciones administrativas sensibles registran como mínimo: operador/UID de origen, identidad Linux de ejecución, TTY/sesión cuando aplique, operation ID, recurso y alcance exactos, motivo, timestamp UTC, resultado y referencia a la evidencia transaccional.

La evidencia de procedencia del operador es distinta de:
- la identidad Atlas USER;
- la identidad Linux del writer;
- el evento de dominio/ledger persistido en la transacción.

El diseño debe proteger los registros de auditoría contra modificación por el proceso auditado y definir retención, exportación y verificación. Los logs de servicio no sustituyen el ledger de dominio ni una auditoría externa.

## 11. Criterios de aceptación previos al despliegue

- [ ] Cuenta de sistema `atlas-runtime` sin login interactivo ni grupos privilegiados.
- [ ] Directorios y base con propiedad/modos objetivo comprobados.
- [ ] Runtime y writers se ejecutan con UID/GID `atlas-runtime`.
- [ ] Frontend privilegiado no abre ni escribe SQLite.
- [ ] Delegación de privilegios y canal de procedencia superan revisión adversarial.
- [ ] Ningún proceso de escritura conserva root/capabilities.
- [ ] Una sola instancia SQLiteDatabase alimenta la composición de autoridad.
- [ ] Servicios que comparten transacciones usan la misma UoW.
- [ ] Migraciones explícitas, checksums verificados y sin migración automática al arrancar.
- [ ] CLI provisioning adaptado; el CLI actual queda bloqueado para la futura DB hasta entonces.
- [ ] Skills/plugins no tienen acceso directo a la DB.
- [ ] Backup cifrado verificable y restauración aislada probada.
- [ ] Custodia de claves y limitación anti-rollback documentadas.
- [ ] Auditoría distingue operador, ejecutor y evento de dominio.
- [ ] Unidad systemd cumple hardening y mínimo privilegio.
- [ ] Pruebas cubren permisos, sidecars, concurrencia, fallos, migración, backup y recuperación.

## 12. Secuencia de implementación

1. **Contrato documental:** publicar y revisar este diseño y reconciliar documentos anteriores.
2. **Composición de autoridad:** implementar root de composición, configuración de ruta y pruebas de UoW compartida sin activar runtime.
3. **Operaciones de DB:** diseñar e implementar migrator y provisioning bajo `atlas-runtime`; resolver formalmente el launcher privilegiado.
4. **Backup/restore y claves:** implementar y probar recuperación y custodia.
5. **Runtime aislado:** preparar unidad y pruebas en entorno temporal.
6. **Despliegue:** solo tras aceptación de todos los criterios, con autorización explícita del propietario.

No se ejecutan provisioning real ni migraciones de la futura base durante las fases documentales o de pruebas temporales.

## 13. Decisiones abiertas

- Mecanismo exacto del launcher privilegiado y canal de procedencia no falsificable.
- Modelo de cuenta administrativa humana y alcance sudoers.
- Ubicación, rotación y recuperación de claves.
- Ancla externa anti-rollback y protección de checkpoints de backup.
- Destino externo de backups, retención, RPO/RTO y prueba periódica de restauración.
- Diseño de auditoría externa y política de retención.

Estas cuestiones no invalidan la decisión de identidad dedicada y propiedad de la base por `atlas-runtime`; impiden declarar lista la implementación/despliegue hasta resolverlas.
