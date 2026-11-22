# Custodia de la clave HMAC de Identity mediante systemd credentials

**Estado:** adaptador de lectura implementado en `work/atlas-mvp-runtime`; pruebas locales pendientes. No provisiona secretos ni modifica unidades systemd.

## Decisión aplicada

La clave de `HmacVerifiedIdentityContextAttestor` se carga desde una credencial systemd dedicada a Identity. No se reutiliza, deriva ni comparte la clave de Local Consistency de ME-03K.

El adaptador `SystemdCredentialVerifiedIdentityContextAttestor`:

- recibe explícitamente el directorio de credenciales y un nombre de credencial simple;
- abre el directorio con `O_DIRECTORY | O_NOFOLLOW` y el archivo relativo con `O_NOFOLLOW`;
- exige un archivo regular con exactamente 32 bytes;
- falla durante la composición si falta, es un symlink, no es regular o tiene longitud incorrecta;
- no tiene fallback, generación, rotación ni lectura de rutas arbitrarias;
- carga la clave una sola vez; el cambio de credencial requiere reconstruir/reiniciar el proceso;
- expone únicamente `sign` y `verify`, delegando en el attestor HMAC existente.

La ruta del directorio debe proceder de la composición confiable del servicio (normalmente `CREDENTIALS_DIRECTORY` entregado por systemd), nunca de una petición, consola o parámetro controlado por el usuario.

## Configuración futura

La unidad del proceso autorizado deberá declarar una credencial propia, por ejemplo mediante `LoadCredentialEncrypted=`, con una referencia de archivo y nombre dedicados a Identity. La configuración exacta, permisos, propietario efectivo, cifrado con clave de host y procedimiento de rotación se revisarán en una tarea de composición/deployment separada.

No se debe apuntar esta credencial al archivo de ME-03K ni reutilizar su `key_reference`. La clave de Identity y la de Local Consistency tienen propósitos, autoridades y ciclos de vida distintos.

## Pruebas que debe ejecutar el propietario en Debian

```bash
.venv/bin/python -m unittest -v tests.unit.test_systemd_identity_attestor
.venv/bin/python -m compileall -q src tests
git diff --check
```

La prueba de integración con systemd real, la creación/cifrado de la credencial, la modificación de una unidad y el reinicio del servicio siguen fuera de este incremento. No se ejecutaron pruebas ni se modificó el host.
