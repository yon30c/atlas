# I3-2B.7B.5B — composición confiable y pruebas de integración reales

**Estado:** implementación publicada; validación Debian pendiente.  
**PR:** #16 — Draft, abierto y sin merge.  
**Base:** diseño 7B.5A.  
**Alcance:** adaptador SQLite, composición interna no registrada y pruebas de integración. Sin runtime, HTTP, CLI, migración ni infraestructura.

## 1. Implementación

### Adaptador lifecycle

`SQLiteProjectEnvironmentLifecycleLedger` acepta ahora, además de `SQLiteUnitOfWork`, una `SQLiteLocalAuthorityUnitOfWork` explícita. Cuando recibe esta última:
- exige que la UoW esté activa;
- exige que pertenezca al mismo objeto `SQLiteDatabase`;
- exige conexión disponible y transacción SQLite activa;
- usa esa conexión para lectura/escritura, sin abrir una segunda UoW.

La resolución de la conexión queda encapsulada en el adaptador. No se añade un writer ni una propiedad lifecycle al objeto UoW general. Las rutas anteriores con `SQLiteUnitOfWork` siguen disponibles.

### Composición interna

Se añadió `atlas.application.project_environment_lifecycle_composition`:
- construye una única `SQLiteLocalAuthorityUnitOfWorkFactory`;
- construye el `VerifiedIdentityContextService` real con el mismo factory, Clock, attestor, realm, audience y TTL;
- crea una closure privada que solo acepta `SQLiteLocalAuthorityUnitOfWork` y construye el ledger enlazado a ella;
- construye `ProjectEnvironmentLifecycleService` con el verifier real;
- devuelve únicamente el servicio lifecycle.

El módulo no se exporta desde paquetes públicos ni se registra en runtime, HTTP, CLI o sistema de plugins. El caller confiable sigue siendo responsable de suministrar el attestor y la clave; no se define ni modifica provisión de secretos.

La validación de tipo y transacción en el adapter es una frontera de composición para evitar errores de wiring, no un sandbox contra código Python arbitrario en el mismo proceso. Extensiones no confiables siguen requiriendo aislamiento de proceso.

## 2. Integración real añadida

`tests/unit/test_trusted_project_environment_lifecycle_composition.py` construye una base SQLite temporal con migraciones reales y utiliza:
- `SQLiteLocalAuthorityUnitOfWorkFactory`;
- issuer y binding nativos reales;
- autenticador y proof nativo de un solo uso persistidos por sus repositorios;
- `VerifiedIdentityContextService.admit_proof` para consumir el proof y emitir el contexto;
- `HmacVerifiedIdentityContextAttestor` real con material de clave exclusivo de test;
- bootstrap Platform Admin de fixture en DB temporal;
- composición lifecycle interna y repositorios SQLite reales.

No se reemplaza `verify_in_unit_of_work` por un mock. La prueba de éxito instrumenta el método real mediante un wrapper que delega a la implementación original, confirma que recibe una UoW con transacción activa y verifica el resultado atómico: asociación suspendida/revisión 2, un evento y un marcador.

Casos incluidos:
1. proof nativo válido + HMAC + Platform Admin → transición confirmada;
2. attestation manipulada → rechazo sin escrituras;
3. binding revocado → rechazo sin escrituras;
4. contexto expirado → rechazo sin escrituras;
5. revisión/estado USER cambiado → rechazo sin escrituras;
6. contexto firmado para otra audience → rechazo sin escrituras;
7. grant Platform Admin revocado → rechazo sin escrituras.

Las comprobaciones negativas verifican estado/revisión de asociación, conteo de eventos y marcadores.

## 3. Límites pendientes

Este corte no cubre aún todas las pruebas adversariales previstas en 7B.5A: issuer revocado, realm distinto, delegación/actor discordante, grant expirado o permiso incorrecto, fallo físico de commit y comprobación más explícita de ausencia de rutas alternativas. Esos casos quedan para 7B.5C/revisión de superficie antes de cualquier exposición externa.

La clave HMAC de integración es únicamente material fijo de test; no demuestra custodia, rotación ni provisión de secretos en producción. No se creó bootstrap real ni se modificó la base de datos productiva.

## 4. Validación requerida en Debian

Desde `~/atlas-dev`, después de sincronizar la rama:

```bash
python -m unittest tests.unit.test_trusted_project_environment_lifecycle_composition -v
python -m unittest tests.unit.test_sqlite_project_environment_lifecycle_ledger -v
python -m compileall -q src tests
python -m unittest discover -s tests -v
```

La fase queda **pendiente de validación del propietario** hasta recibir los resultados reales. No se afirma que las pruebas hayan pasado.

## 5. Seguridad y estado operativo

- No se añadió endpoint, CLI, runtime registration ni ruta de ejecución externa.
- No se añadió writer a `SQLiteLocalAuthorityUnitOfWork`.
- No se aplicó V26 a una base productiva.
- No se ejecutó bootstrap real.
- No se modificó systemd, Docker, usuarios, privilegios, host ni secretos.
- PR #16 permanece Draft, abierto y sin merge.
