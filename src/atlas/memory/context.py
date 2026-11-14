"""Contexto neutral de solicitud para el Memory Engine.

Este contrato no autentica al actor. Solo un adaptador de integración confiable
debe construirlo después de validar la identidad y sus atributos autoritativos.
El motor vuelve a delegar la decisión de acceso en su puerto de autorización.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from atlas.core.errors import ContractError


def _required(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacía")


@dataclass(frozen=True, slots=True)
class MemoryRequestContext:
    """Atributos de una solicitud autenticada, sin tipos propios de AtlasCore."""

    request_id: str
    correlation_id: str
    actor_id: str
    actor_kind: str
    actor_status: str
    actor_revision: int
    user_id: str
    origin: str
    purpose: str
    classification: str
    created_at: datetime
    delegation: str | None = None
    project_id: str | None = None
    environment: str | None = None

    def __post_init__(self) -> None:
        for field in (
            "request_id", "correlation_id", "actor_id", "actor_kind",
            "actor_status", "user_id", "origin", "purpose", "classification",
        ):
            _required(getattr(self, field), field)
        if isinstance(self.actor_revision, bool) or not isinstance(self.actor_revision, int) or self.actor_revision < 1:
            raise ContractError("actor_revision debe ser un entero positivo")
        for field in ("delegation", "project_id", "environment"):
            value = getattr(self, field)
            if value is not None:
                _required(value, field)
        if (
            not isinstance(self.created_at, datetime)
            or self.created_at.tzinfo is None
            or self.created_at.utcoffset() != timedelta(0)
        ):
            raise ContractError("created_at debe ser un datetime UTC")
