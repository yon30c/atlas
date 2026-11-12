"""Errores de contrato y dominio."""


class AtlasError(Exception):
    """Base de los errores conocidos del núcleo."""


class ContractError(AtlasError, ValueError):
    """Un valor viola el contrato de dominio."""


class AuthorizationError(AtlasError):
    """La operación no está autorizada."""


class NotFoundError(AtlasError):
    """El recurso no existe o no es visible para el solicitante."""


class ConcurrencyError(AtlasError):
    """Conflicto por modificación concurrente de un recurso."""