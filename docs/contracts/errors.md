# Contrato de errores

Los errores del dominio derivan de `AtlasError`. `AuthorizationError` denota denegación explícita; `NotFoundError` no revela recursos fuera del ámbito autorizado; `ContractError` indica datos de entrada inválidos. Los adaptadores futuros deben traducir errores de infraestructura sin filtrar secretos.