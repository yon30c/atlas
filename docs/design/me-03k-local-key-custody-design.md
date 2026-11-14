# ME-03K — Custodia local de claves y firmante HMAC

**Estado:** implementación de código publicada; pruebas Debian pendientes. No provisiona secretos ni modifica systemd.  
**Rama:** `feature/me-03k-local-profile`.  
**Dependencia:** decisión del propietario de usar systemd credentials con clave de host (`--with-key=host`) aprobada previamente.

## 1. Objetivo y orden

Antes de implementar la lectura durable autenticada necesaria para K02/K06, Atlas necesita una ruta productiva y explícita para:

1. seleccionar una clave activa para firmar envelopes nuevos;
2. resolver claves históricas por `key_reference` para verificar journal/checkpoints existentes;
3. entregar las claves desde systemd credentials sin almacenarlas en SQLite, Git ni backups ordinarios.

Esta subetapa implementa los puertos y adaptadores en código y los prueba con directorios temporales. La instalación real de credenciales y los cambios a la unidad systemd quedan fuera de esta subetapa.

## 2. Componentes y límites

### 2.1 `ActiveLocalConsistencyKey`

DTO inmutable que contiene:

- `key_reference`: referencia opaca, no secreta;
- `key`: exactamente 32 bytes HMAC-SHA-256.

La representación del DTO debe ocultar los bytes de clave (`repr=False`). No debe implementar serialización, logging ni exportación.

### 2.2 `ActiveLocalConsistencyKeyProvider`

Puerto de solo lectura:

```python
load_active_key() -> ActiveLocalConsistencyKey | None
```

La selección de clave activa proviene exclusivamente de configuración confiable de composición. El proveedor no elige una clave por orden de archivos, fecha, contenido del journal o datos recuperados.

### 2.3 `SystemdCredentialKeyProvider`

Adaptador que implementa la resolución histórica `LocalConsistencyKeyPort.load_key(key_reference)`.

Recibe explícitamente:

- el directorio de credenciales proporcionado por systemd;
- un mapa inmutable `key_reference -> credential_name`.

Reglas:

- Cada nombre de credencial es un único componente de ruta; no se permiten rutas absolutas, separadores, `..` ni nombres vacíos.
- Solo se leen archivos regulares; no se siguen enlaces simbólicos.
- El contenido debe ser exactamente 32 bytes.
- Referencia desconocida, archivo ausente, ilegible, no regular, enlace simbólico o longitud incorrecta => clave no disponible (`None`).
- No se buscan claves alternativas ni se intenta generar/reparar una credencial.
- El adaptador no consulta el journal para decidir qué referencia es confiable.

La raíz de composición puede obtener `CREDENTIALS_DIRECTORY` del entorno administrado por systemd y pasar la ruta ya resuelta al adaptador. La lógica de dominio no lee variables de entorno.

### 2.4 `ConfiguredActiveLocalConsistencyKeyProvider`

Adaptador pequeño que recibe un `SystemdCredentialKeyProvider` y una única `active_key_reference` explícita. Llama a `load_key(active_key_reference)` y devuelve `ActiveLocalConsistencyKey` solo si la clave está disponible y tiene longitud válida.

La referencia activa no se infiere de la última fila, del timestamp ni del mayor número de versión.

### 2.5 `HmacLocalConsistencySigner`

Implementa `LocalConsistencySignerPort`:

1. solicita la clave activa;
2. falla con excepción si no está disponible;
3. exige que `active_key.key_reference == envelope.key_reference`;
4. llama a `authenticate_envelope(envelope, object_value, key)`;
5. devuelve el envelope autenticado.

No modifica issuer, role, dominio, época, secuencia, reducer, política, referencia de clave ni timestamp. Solo completa `object_commitment` y `authentication_evidence` mediante el primitivo criptográfico existente.

## 3. Configuración y custodia

- La credencial en reposo se cifra con systemd credentials usando explícitamente `--with-key=host`.
- systemd descifra la credencial en el directorio privado de credenciales del servicio.
- Atlas recibe únicamente la ruta de ese directorio y lee el material durante el proceso.
- La clave HMAC de 32 bytes y la clave de cifrado del host de systemd son secretos distintos con propósitos distintos.
- `key_reference` es identificador no secreto; los bytes nunca se escriben en SQLite, journal, logs, Git o backups ordinarios.
- El mapa debe conservar las referencias históricas necesarias para verificar evidencia anterior.
- La clave activa y las referencias permitidas por `LocalConsistencyTrustPolicy` deben coincidir exactamente.
- No hay generación, rotación, sustitución ni fallback automático.
- Una referencia histórica perdida produce `UNAVAILABLE`; una clave disponible pero incorrecta produce `REJECTED` durante la verificación HMAC.

## 4. Fallos y seguridad

| Condición | Resultado |
|---|---|
| Clave activa ausente o inaccesible | Firma no disponible; append abortado |
| Referencia activa distinta a la del envelope | Firma abortada |
| Clave histórica ausente | Verificación `UNAVAILABLE` |
| Clave histórica de longitud incorrecta | Verificación `UNAVAILABLE` |
| Clave disponible pero MAC incorrecto | Verificación `REJECTED` |
| Credential name con traversal o separador | Configuración rechazada |
| Credential path es symlink o no es archivo regular | Clave no disponible |
| Excepción al firmar | Transacción abortada y rollback |

No convertir `UNAVAILABLE` en `REJECTED`, no omitir un envelope y no cambiar al perfil anclado/local implícitamente.

## 5. Pruebas requeridas

Pruebas unitarias sin systemd real:

1. carga correcta de una clave histórica;
2. selección explícita de la clave activa;
3. rechazo de referencia desconocida;
4. archivo ausente o ilegible => no disponible;
5. longitud distinta de 32 bytes => no disponible;
6. symlink y rutas traversal rechazados;
7. mapa de referencias inmutable;
8. firmante produce un envelope verificable con `verify_envelope`;
9. referencia activa que no coincide con `envelope.key_reference` aborta;
10. proveedor ausente/rotura aborta sin producir evidencia;
11. repr del DTO no revela bytes de clave.

Pruebas de integración posteriores:

- carga desde `CREDENTIALS_DIRECTORY` real;
- `LoadCredentialEncrypted=` con credencial cifrada por host;
- reinicio del servicio y lectura de la misma referencia;
- acceso de usuario/grupo efectivo y ausencia de secretos en logs;
- verificación de envelopes anteriores con referencias históricas.

## 6. Fuera de alcance

- Ejecutar `systemd-creds setup`, generar o cifrar claves.
- Crear archivos de credenciales en el host.
- Modificar `atlas-broker.service` o cualquier unidad de producción.
- Reiniciar servicios.
- Rotación automática o eliminación de claves históricas.
- Trust Anchor externo y anti-rollback.
- Apertura del Recovery Gate o activación de lecturas protegidas.

## 7. Implementación publicada

Código añadido en la rama de trabajo:

- `src/atlas/memory/local_keys.py`: DTO con bytes de clave ocultos en `repr`.
- `src/atlas/ports/active_local_consistency_keys.py`: puerto de selección de clave activa.
- `src/atlas/adapters/systemd_credentials.py`: resolución histórica desde el directorio de credenciales, mapa de referencias inmutable y selección activa explícita.
- `src/atlas/adapters/local_hmac_signer.py`: firmante HMAC que exige coincidencia exacta de `key_reference` y usa el canonicalizador/autenticador existente.
- `tests/unit/test_systemd_credentials.py`: pruebas de carga, ausencia, tamaño, symlink, traversal y selección activa.
- `tests/unit/test_local_hmac_signer.py`: pruebas de firma, verificación, referencia y fallos del proveedor.

## 8. Criterio de salida

La subetapa de código termina cuando los puertos, proveedores y firmante pasan pruebas unitarias y el adaptador SQLite puede usar el firmante real mediante inyección. La activación en Debian requiere una tarea separada, revisión de permisos, provisionamiento explícito por el propietario y verificación operativa sin exponer bytes de clave.

La suite todavía debe ejecutarse en Debian. No se ha ejecutado `systemd-creds setup`, no se han generado ni cifrado claves y no se ha modificado ninguna unidad systemd.
