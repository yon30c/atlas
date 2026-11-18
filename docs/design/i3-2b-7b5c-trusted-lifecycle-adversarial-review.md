# I3-2B.7B.5C — pruebas adversariales y revisión de superficie lifecycle

**Estado:** implementación y validación Debian confirmadas por el propietario.  
**PR:** #16 — Draft, abierto y sin merge.  
**Dependencia:** 7B.5B validada por el propietario con 1,510 tests OK.  
**Alcance:** pruebas de integración adversariales y reducción de exportación accidental. Sin endpoint, CLI, runtime registration, migración ni infraestructura.

## 1. Objetivo

Completar los casos adversariales prioritarios del diseño 7B.5A usando la composición real de 7B.5B. Cada rechazo debe dejar asociación, revisión, eventos y marcadores sin cambios. La revisión de superficie debe reducir exports públicos accidentales sin afirmar que los módulos Python internos sean un sandbox.

## 2. Pruebas añadidas

En `tests/unit/test_trusted_project_environment_lifecycle_composition.py`:

1. **Issuer revocado:** emitir evidencia nativa/HMAC real, revocar el issuer en la DB temporal mediante transición terminal de estado y exigir rechazo sin escrituras lifecycle.
2. **Realm discordante:** construir una composición confiable configurada para otro realm y presentar evidencia válida emitida bajo el realm original; exigir rechazo.
3. **Actor discordante:** evidencia de un USER presentada con OperationContext cuyo actor canónico es otro USER; denegar sin escrituras.
4. **Delegación presente:** presentar evidencia USER directa con `DelegationMode.DELEGATED`; la ruta owner-direct debe denegar.
5. **Platform Admin expirado:** fixture con grant válido de 90 días cuyo vencimiento está a un minuto del reloj inicial. Avanzar 61 segundos y comprobar que la evidencia USER sigue vigente, pero el grant ya expiró; denegar sin escrituras.
6. **Permiso exacto ausente:** segundo USER con autenticación nativa real y un grant persistido de alcance limitado a `association.reactivate`; intentar suspender y comprobar DENY. La fila se crea solo en DB temporal como fixture adversarial; no se amplía el contrato del bootstrap offline.
7. **Fallo en commit del servicio:** inyectar fallo en el límite `commit()` de la UoW real y comprobar rollback de asociación, evento y marcador.
8. **Superficie pública:** comprobar que el ledger no aparece como export de `atlas.adapters.sqlite`, que la composición no se exporta desde `atlas.application` y que la UoW no incorpora un writer lifecycle.

Los casos actor y delegación se ejecutan dentro de un mismo método de prueba con escenarios separados. Se conservan los casos previos de HMAC manipulado, binding revocado, contexto expirado, USER suspendido, audiencia discordante y Platform Admin revocado.

## 3. Cambio de superficie

Se retiró `SQLiteProjectEnvironmentLifecycleLedger` del import y de `__all__` de `atlas.adapters.sqlite`. Los consumidores internos de pruebas siguen importando el adapter desde su módulo de infraestructura explícito. La composición lifecycle sigue sin exportarse desde `atlas.application` ni conectarse a runtime.

Esta reducción evita presentar el ledger como parte de la API de paquete, pero no impide imports deliberados de módulos internos por código Python dentro del mismo proceso. Tampoco convierte `SQLiteWorkspaceRegistryRepository.update_association` en una frontera de seguridad. Esas capacidades siguen siendo infraestructura interna: ninguna ruta externa debe invocarlas directamente; toda operación autorizada debe pasar por el servicio lifecycle.

## 4. Límites

- No se añadió método de revocación de issuer al producto; el test usa SQL solo sobre la base temporal para simular el estado terminal que el verifier debe revalidar.
- El fallo de commit se inyecta en el método `commit()` antes del commit físico; comprueba rollback de la UoW real, no fallos de hardware/fsync.
- El grant con permiso limitado es un fixture DB adversarial y no una nueva vía de bootstrap soportada.
- No se demuestra custodia/rotación de clave HMAC en producción.
- No se habilita runtime, HTTP, CLI, plugins ni agente.
- No se modifica schema, migraciones, DB productiva, host, systemd, Docker, usuarios, privilegios o secretos.

## 5. Validación Debian requerida

Desde `~/atlas-dev`:

```bash
git pull --ff-only
PYTHONPATH=tests:tests/unit python -m unittest test_trusted_project_environment_lifecycle_composition -v
python -m compileall -q src tests
echo "COMPILE_EXIT_CODE=$?"
python -m unittest discover -s tests -v
```

### Resultado confirmado por el propietario

El propietario ejecutó la suite completa en Debian: **1,517 tests en 30.234 s — OK**. Con este resultado, 7B.5C queda validada por el propietario. El alcance sigue limitado a pruebas adversariales y revisión de superficie: no habilita runtime, endpoint, CLI, plugins ni nuevas rutas de escritura. No se atribuye un resultado de `compileall`, ya que no fue incluido en la confirmación recibida.

PR #16 debe permanecer Draft, abierto y sin merge.
