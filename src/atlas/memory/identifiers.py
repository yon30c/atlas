"""Validación de identificadores Atlas para el dominio de memoria."""
from uuid import UUID

from atlas.core.errors import ContractError


def validate_atlas_id(value: str, field: str) -> str:
    """Exige un UUIDv7 canónico lowercase; no genera ni normaliza IDs."""
    if not isinstance(value, str):
        raise ContractError(f"{field} debe ser un UUIDv7")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise ContractError(f"{field} debe ser un UUIDv7") from None
    # UUID.version solo devuelve 7 cuando el variant también es RFC 4122.
    if parsed.version != 7:
        raise ContractError(f"{field} debe ser un UUIDv7")
    if str(parsed) != value:
        raise ContractError(f"{field} debe usar UUIDv7 canónico lowercase")
    return value
