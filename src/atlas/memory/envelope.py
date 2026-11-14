"""Typed authenticated envelope shared by journal models and trust contracts."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from atlas.core.errors import ContractError


def _required(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacía")


def _positive(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractError(f"{field} debe ser un entero positivo")


def _utc(value: object, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ContractError(f"{field} debe ser datetime UTC")


from dataclasses import dataclass
from datetime import datetime, timedelta
from atlas.core.errors import ContractError


@dataclass(frozen=True, slots=True)
class AuthenticatedConsistencyEnvelope:
    """Opaque authentication envelope bound to one exact journal/checkpoint object."""

    object_kind: str
    envelope_version: int
    consistency_domain_id: str
    authority_epoch: int
    sequence: int
    object_id: str
    schema_version: int
    reducer_version: str
    previous_commitment: str | None
    object_commitment: str
    issuer_id: str
    issuer_role: str
    key_reference: str
    trust_policy_version: str
    issued_at: datetime
    authentication_evidence: str

    def __post_init__(self) -> None:
        for field in (
            "object_kind", "consistency_domain_id", "object_id", "reducer_version",
            "object_commitment", "issuer_id", "issuer_role", "key_reference",
            "trust_policy_version", "authentication_evidence",
        ):
            _required(getattr(self, field), field)
        _positive(self.envelope_version, "envelope_version")
        _positive(self.authority_epoch, "authority_epoch")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 0:
            raise ContractError("sequence debe ser no negativo")
        _positive(self.schema_version, "schema_version")
        if self.previous_commitment is not None:
            _required(self.previous_commitment, "previous_commitment")
        _utc(self.issued_at, "issued_at")
