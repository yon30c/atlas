"""Authoritative issuer inventory contracts, separate from trust policies."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from atlas.core.errors import ContractError


def _require_utc(value: object, field: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ContractError(f"{field} debe ser un datetime UTC")


@dataclass(frozen=True, slots=True)
class RecoveryEvidenceIssuerRegistration:
    """One immutable inventory snapshot; registration does not grant trust."""

    issuer_id: str
    registry_revision: int
    enabled: bool
    changed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.issuer_id, str) or not self.issuer_id.strip():
            raise ContractError("issuer_id debe ser una cadena no vacía")
        if (
            isinstance(self.registry_revision, bool)
            or not isinstance(self.registry_revision, int)
            or self.registry_revision < 1
        ):
            raise ContractError("registry_revision debe ser un entero positivo")
        if not isinstance(self.enabled, bool):
            raise ContractError("enabled debe ser bool")
        _require_utc(self.changed_at, "changed_at")
