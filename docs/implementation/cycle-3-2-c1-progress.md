# Cycle 3.2-C1 — progreso de implementación

**Rama:** `feature/cycle-3-2-c1-native-credentials`  
**Base:** PR #8, `design/cycle-3-2-c1-native-authentication-contracts`  
**Estado:** C1-1 a C1-4 validados por suite/compilación en Debian; C1-5 implementado en GitHub y pendiente de validación local.

## Slice C1-1 — credenciales y Argon2id

Se añadieron:

- `LoginHandle`: canonicalización ASCII lowercase, longitud 3–64 y patrón estricto.
- Política de contraseña nueva: mínimo 12 puntos de código Unicode, máximo 1024 bytes UTF-8, sin NUL, sin trim ni normalización silenciosa.
- `Argon2idParameters`: todos los parámetros son obligatorios y validados; no existen defaults de producción implícitos.
- Puerto `PasswordHasherPort`.
- Adaptador `Argon2idPasswordHasher` sobre `argon2-cffi`, usando explícitamente `Type.ID`, salt aleatorio administrado por la biblioteca, PHC encoded hashes, verificación y detección de rehash.
- Dependencia runtime `argon2-cffi>=23.1.0`.

**Validación Debian confirmada por el propietario:**

- Suite completa C1-1: 1,232 pruebas, OK.
- Pruebas focalizadas C1-1: 14 pruebas, OK.
- `python -m compileall -q src tests`: exit code 0.
- Git alineado con origin y árbol limpio antes de C1-2.

Los parámetros pequeños usados en tests son exclusivamente de test y no representan valores de producción. La aceptación de producción requiere benchmark Argon2id en el hardware objetivo.

## Slice C1-2 — contratos de autenticación nativa

Se añadieron en `src/atlas/authentication/native.py`:

- `NativeSubject`: token base64url canónico generado con 32 bytes CSPRNG; expone digest SHA-256 y redacta el valor en repr.
- `NativeProofReference`: referencia one-shot de 256 bits con digest SHA-256 y repr redactado.
- `NativeAuthenticator`: agregado de Authentication Authority con IDs UUIDv4, LoginHandle, PHC Argon2id, revisión de credencial y estados ACTIVE/SUSPENDED/REVOKED. No contiene UserId, Identity ni Grant.
- `NativeAuthenticationProof`: metadata persistible digest-only, con issuer, subject, authenticator, revisión, timestamps UTC, audience y estado. La referencia raw no forma parte del registro.
- Pruebas unitarias para generación/forma de tokens, redacción, digest, invariantes de IDs, PHC, revisión, fechas, audience y estados.

**Validación Debian confirmada:** suite completa de 1,239 pruebas, OK; checkout limpio y alineado en `c69ebe4`. No se reportó compileall explícito para este slice.

Este slice no implementa repositorios, emisión/consumo atómico de proof, bootstrap, sesiones ni endpoints.

## Slice C1-3 — Identity Authority: issuer y binding nativo

Se añadieron:

- `NativeIdentityIssuer`, con realm lógico estable, perfil explícito `NATIVE_AUTHORITY_PROOF`, estado y revisión.
- `NativeIdentityBinding`, que vincula issuer + digest del subject con un `identity_id` canónico, timestamps UTC, revisión y tombstone terminal de revocación.
- `NativeIdentityAuthorityPort`, con consulta/creación de issuer y binding y revocación mediante CAS. La creación recibe `CanonicalUserIdentity`.
- Pruebas unitarias de IDs, realm, perfil, digest, timestamps, revisión y estados.

**Validación Debian confirmada:** suite completa de 1,245 pruebas, OK; checkout limpio y alineado en `5416a8c`. No se reportó compileall explícito para este slice.

## Slice C1-4 — persistencia SQLite de Identity Authority

Se implementó:

- Migración aditiva v19 `native_identity_issuers_and_subject_bindings`; no sintetiza issuers ni bindings para usuarios existentes.
- `native_identity_issuers`: realm único, perfil nativo explícito, estado/revisión y tombstones.
- `native_identity_bindings`: FK a Identity(USER) e issuer, unicidad permanente `(issuer_id, subject_digest)`, digest lowercase, estado/revisión y timestamps.
- Triggers SQL para identidad inmutable, paso exacto de revisión, revocación terminal y prohibición de DELETE.
- Triggers SQL exigen Identity(USER) activa e issuer activo al crear binding.
- `SQLiteNativeIdentityAuthority`: creación/consulta issuer, creación de binding solo tras releer y comparar el UserId/Identity canónico desde SQLite, y revocación CAS.
- `SQLiteLocalAuthorityUnitOfWork.native_identity`: comparte exactamente la transacción SQLite con la autoridad canónica y demás repositorios locales.
- Export de adapter y migración v19.
- Pruebas de persistencia, unicidad, no reasignación tras revocación, identidad canónica stale/mismatch, estado activo, CAS, tombstones y rollback/commit compartido.

**Validación C1-4 confirmada por el propietario:** suite completa 1,254 OK; `python -m compileall -q src tests` con `COMPILE_EXIT_CODE=0`; HEAD `e153a5c`; rama limpia y alineada con origin.

La migración v19 solo se ha añadido al código del PR; no se ha aplicado a la base de datos de producción. La validación local de migración debe hacerse en bases de prueba temporales.

## Slice C1-5 — persistencia Authentication Authority y proofs one-shot

Se añadieron en el branch:

- Migración aditiva v20 para `native_authenticators` y `native_authentication_proofs`; v1–v19 no se modifican.
- Autenticadores con PHC Argon2id, subject nativo, login handle único por issuer, revisión de credencial y estados terminales; sin contraseña en claro.
- Proofs con digest SHA-256 único, audience, timestamps y revisión exacta; no se persiste la referencia raw.
- Triggers de integridad, inmutabilidad, revocación terminal, no-delete y revocación automática de proofs pendientes cuando cambia la credencial o se suspende/revoca el autenticador.
- `SQLiteNativeAuthenticationAuthority` con creación/lectura de autenticadores, rotación de PHC con CAS, emisión y consumo one-shot condicional.
- Consumo usa `BEGIN IMMEDIATE` y UPDATE condicional; audience incorrecta no consume el proof.
- Integración `SQLiteLocalAuthorityUnitOfWork.native_authentication` compartiendo la transacción física.
- Pruebas focalizadas añadidas para digest-only, audiencia, expiración, replay, revisión de credenciales, concurrencia y UoW.

**Validación C1-5 reportada por el propietario en Debian:** suite completa `Ran 1262 tests in 12.863s — OK`; rama local alineada con `origin/feature/cycle-3-2-c1-native-credentials`; HEAD `7f251ca`. La salida compartida no incluye `compileall`, que permanece pendiente de confirmación.

## Límites y bloqueos de seguridad

1. Identity Authority administra issuer y binding; Authentication Authority administra credenciales y proofs. Ninguna de ellas concede CAM Grants.
2. C1-5 añade persistencia interna de autenticadores/proofs y consumo one-shot; todavía no hay bootstrap, sesiones, endpoints ni login operativo.
3. `SQLiteLocalAuthorityUnitOfWork` es un límite transaccional físico; no es un coordinador de Consistency ni demuestra fencing distribuido.
4. **Grant inicial del bootstrap sin perfil CAM aprobado:** el Grant canónico exige owner_user_id, subject_identity_id, project_id, environment, resource_type, IDs concretos de recurso, acciones explícitas y expiración. Antes de implementar bootstrap hay que resolver formalmente si el primer usuario se crea sin activación o si se aprueba un perfil CAM acotado. No se inventará un Grant global ni un proyecto/entorno ficticio.
5. Los parámetros Argon2id de producción requieren benchmark en el hardware objetivo.
6. La migración v20 debe probar upgrade desde v19 con preservación de datos, integridad FK y re-aplicación idempotente.

## Próximo slice

Tras validar C1-5, resolver formalmente el perfil CAM mínimo antes de diseñar bootstrap. Bootstrap permanece bloqueado hasta esa decisión; sesiones y endpoints quedan fuera de C1.
