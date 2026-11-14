"""Independent allowlist policy for local consistency recovery verification.

The policy is supplied by trusted server composition/configuration. It is never
loaded from the journal, checkpoint, backup, or any recovered object.
"""
from dataclasses import dataclass

from atlas.core.errors import ContractError
from atlas.memory.envelope import AuthenticatedConsistencyEnvelope


def _required(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacía")


def _version_set(values: object, field: str) -> None:
    if not isinstance(values, frozenset) or not values:
        raise ContractError(f"{field} debe ser un frozenset no vacío")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 1
           for value in values):
        raise ContractError(f"{field} solo admite enteros positivos")


@dataclass(frozen=True, slots=True)
class LocalIssuerAuthorization:
    """One exact issuer/role pair authorized for one envelope object kind."""

    object_kind: str
    issuer_id: str
    issuer_role: str

    def __post_init__(self) -> None:
        if self.object_kind not in ("checkpoint", "journal_entry"):
            raise ContractError("object_kind no está permitido para recuperación local")
        _required(self.issuer_id, "issuer_id")
        _required(self.issuer_role, "issuer_role")


@dataclass(frozen=True, slots=True)
class LocalConsistencyTrustPolicy:
    """Immutable trust allowlist injected from trusted server configuration.

    Authorizations are exact triples, not independent issuer/role sets, to
    prevent unintended cross-product authorization. Empty allowlists are
    rejected so an accidentally incomplete configuration cannot be deployed.
    """

    policy_version: str
    consistency_domain_id: str
    issuer_authorizations: frozenset[LocalIssuerAuthorization]
    allowed_key_references: frozenset[str]
    allowed_envelope_versions: frozenset[int]
    allowed_canonicalization_versions: frozenset[int]
    allowed_schema_versions: frozenset[int]
    allowed_reducer_versions: frozenset[str]

    def __post_init__(self) -> None:
        _required(self.policy_version, "policy_version")
        _required(self.consistency_domain_id, "consistency_domain_id")
        if not isinstance(self.issuer_authorizations, frozenset) or not self.issuer_authorizations:
            raise ContractError("issuer_authorizations debe ser un frozenset no vacío")
        if any(not isinstance(item, LocalIssuerAuthorization)
               for item in self.issuer_authorizations):
            raise ContractError("issuer_authorizations contiene tipos no permitidos")
        for field in ("allowed_key_references", "allowed_reducer_versions"):
            values = getattr(self, field)
            if not isinstance(values, frozenset) or not values:
                raise ContractError(f"{field} debe ser un frozenset no vacío")
            for value in values:
                _required(value, field)
        for field in (
            "allowed_envelope_versions",
            "allowed_canonicalization_versions",
            "allowed_schema_versions",
        ):
            _version_set(getattr(self, field), field)

    def authorizes_envelope(
        self, envelope: AuthenticatedConsistencyEnvelope
    ) -> bool:
        """Check every policy-bound claim before attempting key resolution."""
        if not isinstance(envelope, AuthenticatedConsistencyEnvelope):
            return False
        return all((
            envelope.consistency_domain_id == self.consistency_domain_id,
            envelope.trust_policy_version == self.policy_version,
            envelope.object_kind in ("checkpoint", "journal_entry"),
            envelope.envelope_version in self.allowed_envelope_versions,
            envelope.schema_version in self.allowed_schema_versions,
            envelope.reducer_version in self.allowed_reducer_versions,
            envelope.key_reference in self.allowed_key_references,
            LocalIssuerAuthorization(
                envelope.object_kind, envelope.issuer_id, envelope.issuer_role
            ) in self.issuer_authorizations,
        ))

    def supports_canonicalization(self, version: int) -> bool:
        """Whether the configured policy permits the verifier's canonicalizer."""
        return (
            not isinstance(version, bool)
            and isinstance(version, int)
            and version in self.allowed_canonicalization_versions
        )
