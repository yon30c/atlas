"""Propuestas proactivas sin ejecución de acciones."""
from dataclasses import dataclass
from uuid import UUID

from atlas.core.context import OperationContext
from atlas.core.errors import ContractError
from atlas.core.identity import _required


@dataclass(frozen=True, slots=True)
class ProactiveProposal:
    proposal_id: UUID
    owner_id: str
    rationale: str
    suggested_action: str
    context: OperationContext

    def __post_init__(self) -> None:
        if not isinstance(self.proposal_id, UUID):
            raise ContractError("proposal_id debe ser UUID")
        for name in ("owner_id", "rationale", "suggested_action"):
            _required(getattr(self, name), name)
        if not isinstance(self.context, OperationContext):
            raise ContractError("context debe ser OperationContext")
        if self.owner_id != self.context.user_id:
            raise ContractError("owner_id debe coincidir con el usuario del contexto")