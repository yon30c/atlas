
"""Contexto explicito e inmutable para operaciones Atlas."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from atlas.core.enums import DelegationMode
from atlas.core.errors import ContractError
from atlas.core.identity import Identity, _required


@dataclass(frozen=True, slots=True)
class OperationContext:
    request_id: str
    correlation_id: str
    actor: Identity
    user_id: str
    origin: str
    delegation: DelegationMode | None
    project_id: str | None
    environment: str | None
    purpose: str
    classification: str
    created_at: datetime

    def __post_init__(self) -> None:
        required_fields = (
            "request_id",
            "correlation_id",
            "user_id",
            "origin",
            "purpose",
            "classification",
        )

        for field in required_fields:
            _required(getattr(self, field), field)

        if not isinstance(self.actor, Identity):
            raise ContractError("actor debe ser una Identity valida")

        if self.delegation is not None and not isinstance(
            self.delegation, DelegationMode
        ):
            raise ContractError("delegation no es valido")

        if self.project_id is not None:
            _required(self.project_id, "project_id")

        if self.environment is not None:
            _required(self.environment, "environment")

        if not isinstance(self.created_at, datetime):
            raise ContractError("created_at debe ser datetime")

        if self.created_at.tzinfo is None:
            raise ContractError("created_at debe tener zona horaria")

        if self.created_at.utcoffset() != timedelta(0):
            raise ContractError("created_at debe estar en UTC")
