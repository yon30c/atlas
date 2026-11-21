# A-IPC-01 — registro de validación local A09a/A09b

> **Fecha:** 2026-11-21  
> **Repositorio:** `yon30c/atlas`  
> **Rama:** `experiment/a-ipc-01-private-unix-listener-probe`  
> **Commit probado:** `1d5bdb122a8480c36b445be7dd961b93806de74b`  
> **Fuente:** salida JSON comunicada por el propietario tras ejecutar el runner en Debian.  
> **Clasificación:** `overall=PASS`, 16 escenarios PASS, 0 SKIP, 0 FAIL.

Este registro supersede las notas anteriores de A-IPC-01 que clasificaban A09 como SKIP y el resultado global como INCOMPLETE. La evidencia es específica del commit, kernel, Python y entorno indicados; no debe proyectarse sobre otros commits ni sobre producción.

## Entorno de ejecución

- Debian 13.
- Kernel: `6.12.117+deb13-amd64`.
- Python: `3.13.5`.
- Runner: UID efectivo 1000; no se ejecutó como root.
- Identidad externa: `atlas-a09-test`, UID 1001, GID primario 984.
- Duración total: 1.72 s.
- Sandbox: `/tmp/atlas-aipc01-l198j40i`.
- Cleanup reportado: `empty sandbox root removed`.

## Resultado por escenario

| Escenario | Resultado | Evidencia principal |
|---|---|---|
| A01 | PASS | Directorio 0700; socket 0600, UID 1000; bind/listen/accept/close |
| A02 | PASS | Archivo regular conservado; bind errno 98 |
| A03 | PASS | Symlink y destino conservados; bind errno 98 |
| A04 | PASS | Segundo bind errno 98; listener ganador operativo |
| A05 | PASS | Socket stale conservado; bind errno 98 |
| A06 | PASS | Cleanup omitido por mismatch; reemplazo conservado |
| A07 | PASS | Socket propio sin cambios eliminado |
| A08 | PASS | Ping permitido; peer UID/GID 1000 |
| A09a | PASS | DAC: peer UID 1001 recibe EACCES; cero conexiones aceptadas |
| A09b | PASS | SO_PEERCRED: handler rechaza UID 1001 con UNAUTHORIZED_PEER; cero bytes de respuesta |
| A10 | PASS | Credenciales kernel del peer permitido: UID/GID 1000 |
| A11 | PASS | Desconexión antes de request controlada |
| A12 | PASS | Truncamiento y ancillary rechazados silenciosamente |
| A13 | PASS | Peer idle liberado por timeout |
| A14 | PASS | peak_active=2; 6 rechazadas; 8 manejadas; 0 activas tras recuperación |
| A15 | PASS | Listener cerrado deja de aceptar |
| A16 | PASS | Dos binds simultáneos: exactamente un ganador operativo |

## Evidencia A09a — aislamiento DAC

El cliente externo se ejecutó como UID 1001/GID 984/PID 5405. El endpoint candidato conservó directorio modo 0700 y socket propiedad de UID 1000 modo 0600. La conexión falló con errno 13 (`EACCES`) y el listener registró cero conexiones aceptadas.

Interpretación: el kernel aplicó la barrera DAC antes de `accept()`. Esto valida el aislamiento filesystem del endpoint candidato; por sí solo no prueba la decisión de autorización del handler.

## Evidencia A09b — autorización mediante SO_PEERCRED

El cliente externo se ejecutó como UID 1001/GID 984/PID 5417 y conectó al fixture independiente de prueba (directorio modo 0711, socket modo 0666). El handler real rechazó el peer con `UNAUTHORIZED_PEER`. El cliente había enviado una solicitud ping de 122 bytes y recibió cero bytes de respuesta; observó cierre por reset.

Interpretación: el fixture permitió alcanzar el handler, que obtuvo/rechazó las credenciales del peer antes de procesar la solicitud. Los permisos 0711/0666 pertenecen exclusivamente al fixture efímero A09b y no modifican ni sustituyen el endpoint candidato 0700/0600.

## Integridad y limpieza

- El reporte final indicó `cleanup: empty sandbox root removed`.
- A09a informó cero accepts y preservación de la identidad/modos del endpoint candidato.
- A09b utilizó un fixture separado; el resultado no indica alteración del endpoint candidato.
- A06 confirmó que un pathname sustituto no se elimina ante mismatch de identidad.
- A07 confirmó eliminación del socket propio cuando su identidad permaneció intacta.

No se reportaron SKIP ni FAIL en ninguno de los 16 escenarios.

## Cambios host y alcance

Para esta ejecución, el propietario actualizó la única entrada temporal de `authorized_keys` de `atlas-a09-test` para forzar:

```text
/usr/bin/python3 -I /tmp/atlas-a09-client.py
```

Se conservaron `from="127.0.0.1",restrict`, la misma clave pública y permisos 0600 del archivo. Se creó un respaldo local del archivo antes del cambio. El propietario revisó de forma read-only los archivos de inicio de shell. Según el procedimiento comunicado, no se modificaron sshd_config, PAM, firewall ni la configuración global de SSH.

Este registro no acredita que se haya eliminado la cuenta temporal, la clave, el archivo de respaldo o los archivos temporales de identidad; cualquier limpieza de esos elementos debe tratarse por separado y con autorización.

## Conclusión y límites

A-IPC-01 queda **validado como probe experimental** en el commit y entorno indicados. A09a y A09b ya no están pendientes para esa ejecución; el resultado global del runner es PASS.

La validación **no**:
- selecciona AF_UNIX pathname como transporte IPC de producción;
- autoriza listener persistente, daemon, systemd o despliegue;
- habilita operaciones administrativas distintas del ping no mutante usado como fixture;
- demuestra separación de privilegios ni autorización SQLite;
- demuestra resistencia frente a root, capabilities suficientes o procesos maliciosos bajo el mismo UID;
- valida system-manager ni cambia la suspensión de socket activation filesystem;
- sustituye revisión de seguridad y decisión de arquitectura para cualquier transporte productivo.

No se ejecutaron pruebas, compilaciones ni workflows desde GitHub. La ejecución fue realizada por el propietario en Debian y comunicada mediante el JSON del runner. `main` no fue modificada por este registro; la rama experimental sigue separada y no se crea ni integra PR mediante este documento.

## Siguiente paso

Conservar esta evidencia y continuar con revisión estática/documental del siguiente incremento del probe, sin convertir el PASS experimental en aprobación de producción. La alternativa C (AF_UNIX abstract namespace) sigue siendo una evaluación independiente si el propietario decide continuar comparando transportes.
