"""Contratos neutrales para coordinar cambios de autoridades del Memory Engine."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Protocol

from atlas.core.errors import ContractError
from atlas.memory.consistency import AuthorityKind


class AuthorityChangeStatus(str, Enum):
    REQUESTED = "REQUESTED"
    INVALIDATION_PENDING = "INVALIDATION_PENDING"
    SOURCE_PENDING = "SOURCE_PENDING"
    SOURCE_CONFIRMED = "SOURCE_CONFIRMED"
    RECONCILING = "RECONCILING"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    BLOCKED = "BLOCKED"


class AuthorityChangeTargetKind(str, Enum):
    """Canonical resource kinds supported by multi-authority operations."""

    MEMORY = "memory"
    MEMORY_VERSION = "memory_version"
    IDENTITY = "identity"
    PROJECT = "project"
    ENVIRONMENT = "environment"
    GRANT = "grant"
    GRANT_RENEWAL = "grant_renewal"
    CONSISTENCY = "consistency"


@dataclass(frozen=True, slots=True)
class AuthorityChangeTarget:
    """One exact authority revision transition within a larger operation."""

    authority_kind: AuthorityChangeTargetKind
    authority_id: str
    expected_revision: int
    proposed_revision: int

    def __post_init__(self) -> None:
        if not isinstance(self.authority_kind, AuthorityChangeTargetKind):
            raise ContractError("authority_kind debe ser AuthorityChangeTargetKind")
        _required(self.authority_id, "authority_id")
        _positive(self.expected_revision, "expected_revision")
        _positive(self.proposed_revision, "proposed_revision")
        if self.proposed_revision != self.expected_revision + 1:
            raise ContractError(
                "proposed_revision debe ser expected_revision + 1"
            )


@dataclass(frozen=True, slots=True)
class MultiAuthorityChangeIntent:
    """Immutable semantic intent that atomically claims multiple authorities."""

    idempotency_key: str
    consumer_id: str
    action: str
    actor_identity_id: str
    owner_id: str
    project_id: str | None
    environment_id: str | None
    targets: tuple[AuthorityChangeTarget, ...]
    request_context_ref: str
    requested_at: datetime

    def __post_init__(self) -> None:
        for field in (
            "idempotency_key",
            "consumer_id",
            "action",
            "actor_identity_id",
            "owner_id",
            "request_context_ref",
        ):
            _required(getattr(self, field), field)
        if self.project_id is not None:
            _required(self.project_id, "project_id")
        if self.environment_id is not None:
            _required(self.environment_id, "environment_id")
        if not isinstance(self.targets, tuple) or len(self.targets) < 2:
            raise ContractError("targets debe contener al menos dos objetivos")
        if any(not isinstance(target, AuthorityChangeTarget) for target in self.targets):
            raise ContractError("todos los targets deben ser AuthorityChangeTarget")
        identities = [
            (target.authority_kind.value, target.authority_id)
            for target in self.targets
        ]
        if len(set(identities)) != len(identities):
            raise ContractError("la intención no puede repetir objetivos")
        canonical = tuple(
            sorted(
                self.targets,
                key=lambda target: (
                    target.authority_kind.value,
                    target.authority_id,
                ),
            )
        )
        object.__setattr__(self, "targets", canonical)
        _utc(self.requested_at, "requested_at")


def _required(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacía")


def _positive(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractError(f"{field} debe ser un entero positivo")


def _utc(value: object, field: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ContractError(f"{field} debe ser un datetime UTC")


@dataclass(frozen=True, slots=True)
class MultiAuthorityChangeReservation:
    """Durable operation identity and exact multi-authority intent."""

    operation_id: str
    intent: MultiAuthorityChangeIntent
    status: AuthorityChangeStatus

    def __post_init__(self) -> None:
        _required(self.operation_id, "operation_id")
        if not isinstance(self.intent, MultiAuthorityChangeIntent):
            raise ContractError("intent debe ser MultiAuthorityChangeIntent")
        if not isinstance(self.status, AuthorityChangeStatus):
            raise ContractError("status debe ser AuthorityChangeStatus")


@dataclass(frozen=True, slots=True)
class AuthorityChangeIntent:
    """Intención sin operation_id; la autoridad coordinadora asigna ese ID."""

    idempotency_key: str
    consumer_id: str
    authority_kind: AuthorityKind
    authority_id: str
    expected_revision: int
    proposed_revision: int
    change_kind: str
    request_context_ref: str
    requested_at: datetime

    def __post_init__(self) -> None:
        for field in (
            "idempotency_key",
            "consumer_id",
            "authority_id",
            "change_kind",
            "request_context_ref",
        ):
            _required(getattr(self, field), field)
        if not isinstance(self.authority_kind, AuthorityKind):
            raise ContractError("authority_kind debe ser AuthorityKind")
        _positive(self.expected_revision, "expected_revision")
        _positive(self.proposed_revision, "proposed_revision")
        if self.proposed_revision <= self.expected_revision:
            raise ContractError("proposed_revision debe superar expected_revision")
        _utc(self.requested_at, "requested_at")


@dataclass(frozen=True, slots=True)
class AuthorityChangeReservation:
    """Identidad durable asignada a una intención por el coordinador."""

    operation_id: str
    intent: AuthorityChangeIntent
    status: AuthorityChangeStatus

    def __post_init__(self) -> None:
        _required(self.operation_id, "operation_id")
        if not isinstance(self.intent, AuthorityChangeIntent):
            raise ContractError("intent debe ser AuthorityChangeIntent")
        if not isinstance(self.status, AuthorityChangeStatus):
            raise ContractError("status debe ser AuthorityChangeStatus")


@dataclass(frozen=True, slots=True)
class AuthorityChangeResult:
    """Resultado reconciliado de una operación sobre una autoridad."""

    operation_id: str
    authority_kind: AuthorityKind
    authority_id: str
    status: AuthorityChangeStatus
    previous_revision: int
    proposed_revision: int
    source_revision: int | None = None
    invalidation_id: str | None = None

    def __post_init__(self) -> None:
        _required(self.operation_id, "operation_id")
        _required(self.authority_id, "authority_id")
        if not isinstance(self.authority_kind, AuthorityKind):
            raise ContractError("authority_kind debe ser AuthorityKind")
        if not isinstance(self.status, AuthorityChangeStatus):
            raise ContractError("status debe ser AuthorityChangeStatus")
        _positive(self.previous_revision, "previous_revision")
        _positive(self.proposed_revision, "proposed_revision")
        if self.proposed_revision <= self.previous_revision:
            raise ContractError("proposed_revision debe superar previous_revision")
        if self.source_revision is not None:
            _positive(self.source_revision, "source_revision")
        if self.invalidation_id is not None:
            _required(self.invalidation_id, "invalidation_id")
        if self.status is AuthorityChangeStatus.COMPLETED:
            if self.source_revision != self.proposed_revision:
                raise ContractError(
                    "COMPLETED requiere source_revision igual a proposed_revision"
                )
            if self.invalidation_id is None:
                raise ContractError("COMPLETED requiere invalidation_id reconciliado")
        elif self.status is AuthorityChangeStatus.ABORTED:
            if self.source_revision != self.previous_revision:
                raise ContractError(
                    "ABORTED requiere evidencia de que la fuente sigue en previous_revision"
                )


class VerifiedAuthorityChangeAuthorization(Protocol):
    """Evidencia CAM ya verificada y consumida, adaptada al cambio exacto."""

    @property
    def operation_id(self) -> str: ...

    @property
    def proof_id(self) -> str: ...

    @property
    def decision_id(self) -> str: ...

    @property
    def request_id(self) -> str: ...

    @property
    def actor_identity_id(self) -> str: ...

    @property
    def owner_id(self) -> str: ...

    @property
    def authority_kind(self) -> AuthorityKind: ...

    @property
    def authority_id(self) -> str: ...

    @property
    def expected_revision(self) -> int: ...

    @property
    def proposed_revision(self) -> int: ...

    @property
    def issuer_id(self) -> str: ...

    @property
    def issued_at(self) -> datetime: ...

    @property
    def consumed_at(self) -> datetime: ...

class AuthorityChangeTerminalOutcome(str, Enum):
    """Terminal outcome asserted by a durable reconciliation receipt."""

    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


@dataclass(frozen=True, slots=True)
class AuthorityChangeTerminalTarget:
    """Observed final revision for one exact reserved authority target."""

    authority_kind: AuthorityChangeTargetKind
    authority_id: str
    expected_revision: int
    proposed_revision: int
    observed_revision: int

    def __post_init__(self) -> None:
        if not isinstance(self.authority_kind, AuthorityChangeTargetKind):
            raise ContractError("authority_kind debe ser AuthorityChangeTargetKind")
        _required(self.authority_id, "authority_id")
        _positive(self.expected_revision, "expected_revision")
        _positive(self.proposed_revision, "proposed_revision")
        _positive(self.observed_revision, "observed_revision")
        if self.proposed_revision != self.expected_revision + 1:
            raise ContractError("proposed_revision debe ser expected_revision + 1")


@dataclass(frozen=True, slots=True)
class AuthorityChangeTerminalEvidence:
    """Immutable receipt binding a terminal claim to every reserved target.

    This contract validates structure and revision claims only. It does not
    authenticate evidence_ref, prove that reconciliation occurred, or grant
    permission to release resource claims.
    """

    evidence_id: str
    operation_id: str
    outcome: AuthorityChangeTerminalOutcome
    targets: tuple[AuthorityChangeTerminalTarget, ...]
    evidence_ref: str
    recorded_by: str
    recorded_at: datetime

    def __post_init__(self) -> None:
        for field in (
            "evidence_id", "operation_id", "evidence_ref", "recorded_by",
        ):
            _required(getattr(self, field), field)
        if not isinstance(self.outcome, AuthorityChangeTerminalOutcome):
            raise ContractError("outcome debe ser AuthorityChangeTerminalOutcome")
        if not isinstance(self.targets, tuple) or len(self.targets) < 2:
            raise ContractError("targets debe contener al menos dos objetivos")
        if any(
            not isinstance(target, AuthorityChangeTerminalTarget)
            for target in self.targets
        ):
            raise ContractError(
                "todos los targets deben ser AuthorityChangeTerminalTarget"
            )
        identities = [
            (target.authority_kind.value, target.authority_id)
            for target in self.targets
        ]
        if len(set(identities)) != len(identities):
            raise ContractError("la evidencia no puede repetir objetivos")
        canonical = tuple(sorted(
            self.targets,
            key=lambda target: (target.authority_kind.value, target.authority_id),
        ))
        object.__setattr__(self, "targets", canonical)
        for target in canonical:
            expected_observation = (
                target.proposed_revision
                if self.outcome is AuthorityChangeTerminalOutcome.COMPLETED
                else target.expected_revision
            )
            if target.observed_revision != expected_observation:
                raise ContractError(
                    "la revisión observada no coincide con el resultado terminal"
                )
        _utc(self.recorded_at, "recorded_at")

    def matches(self, reservation: MultiAuthorityChangeReservation) -> bool:
        """Return whether this receipt binds exactly to a reservation's targets."""
        if not isinstance(reservation, MultiAuthorityChangeReservation):
            raise ContractError(
                "reservation debe ser MultiAuthorityChangeReservation"
            )
        if self.operation_id != reservation.operation_id:
            return False
        expected = tuple(
            (
                target.authority_kind,
                target.authority_id,
                target.expected_revision,
                target.proposed_revision,
            )
            for target in reservation.intent.targets
        )
        observed = tuple(
            (
                target.authority_kind,
                target.authority_id,
                target.expected_revision,
                target.proposed_revision,
            )
            for target in self.targets
        )
        return observed == expected



class MultiAuthorityClaimAuditStatus(str, Enum):
    """Read-only classification of durable multi-authority claim state."""

    UNCLAIMED = "UNCLAIMED"
    CLAIMED = "CLAIMED"
    TERMINAL_CLAIMS_HELD = "TERMINAL_CLAIMS_HELD"
    RELEASED = "RELEASED"
    INCONSISTENT = "INCONSISTENT"


@dataclass(frozen=True, slots=True)
class MultiAuthorityClaimAudit:
    """Read-only recovery snapshot; never authorizes mutation or claim release."""

    operation_id: str
    operation_status: AuthorityChangeStatus
    audit_status: MultiAuthorityClaimAuditStatus
    reserved_targets: tuple[AuthorityChangeTarget, ...]
    claimed_targets: tuple[AuthorityChangeTarget, ...]
    terminal_evidence: AuthorityChangeTerminalEvidence | None = None
    release_digest: str | None = None

    def __post_init__(self) -> None:
        _required(self.operation_id, "operation_id")
        if not isinstance(self.operation_status, AuthorityChangeStatus):
            raise ContractError("operation_status debe ser AuthorityChangeStatus")
        if not isinstance(self.audit_status, MultiAuthorityClaimAuditStatus):
            raise ContractError(
                "audit_status debe ser MultiAuthorityClaimAuditStatus"
            )
        if not isinstance(self.reserved_targets, tuple) or any(
            not isinstance(item, AuthorityChangeTarget)
            for item in self.reserved_targets
        ):
            raise ContractError("reserved_targets debe ser tuple de AuthorityChangeTarget")
        if not isinstance(self.claimed_targets, tuple) or any(
            not isinstance(item, AuthorityChangeTarget)
            for item in self.claimed_targets
        ):
            raise ContractError("claimed_targets debe ser tuple de AuthorityChangeTarget")
        if self.terminal_evidence is not None and not isinstance(
            self.terminal_evidence, AuthorityChangeTerminalEvidence
        ):
            raise ContractError(
                "terminal_evidence debe ser AuthorityChangeTerminalEvidence o None"
            )
        if self.release_digest is not None:
            if (
                not isinstance(self.release_digest, str)
                or len(self.release_digest) != 64
                or any(ch not in "0123456789abcdef" for ch in self.release_digest)
            ):
                raise ContractError("release_digest debe ser SHA-256 hexadecimal")


class MultiAuthorityRecoveryDisposition(str, Enum):
    """Read-only interpretation of a durable operation's recovery position."""

    NOT_STARTED = "NOT_STARTED"
    CLAIMED_BEFORE_INVALIDATION = "CLAIMED_BEFORE_INVALIDATION"
    INVALIDATION_OUTCOME_UNKNOWN = "INVALIDATION_OUTCOME_UNKNOWN"
    SOURCE_OUTCOME_UNKNOWN = "SOURCE_OUTCOME_UNKNOWN"
    SOURCE_CONFIRMATION_RECORDED = "SOURCE_CONFIRMATION_RECORDED"
    RECONCILIATION_IN_PROGRESS = "RECONCILIATION_IN_PROGRESS"
    TERMINAL_CLAIMS_HELD = "TERMINAL_CLAIMS_HELD"
    TERMINAL_RELEASED = "TERMINAL_RELEASED"
    INCONSISTENT = "INCONSISTENT"


@dataclass(frozen=True, slots=True)
class MultiAuthorityRecoveryAssessment:
    """Read-only recovery classification; never authorizes retry or mutation."""

    disposition: MultiAuthorityRecoveryDisposition
    claim_audit: MultiAuthorityClaimAudit

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, MultiAuthorityRecoveryDisposition):
            raise ContractError(
                "disposition debe ser MultiAuthorityRecoveryDisposition"
            )
        if not isinstance(self.claim_audit, MultiAuthorityClaimAudit):
            raise ContractError(
                "claim_audit debe ser MultiAuthorityClaimAudit"
            )


class MultiAuthorityRecoveryEvidenceKind(str, Enum):
    """Independent evidence classes accepted by the recovery boundary."""

    INVALIDATION_RECEIPT = "INVALIDATION_RECEIPT"
    SOURCE_OUTCOME_RECEIPT = "SOURCE_OUTCOME_RECEIPT"
    CANONICAL_REVISION_SNAPSHOT = "CANONICAL_REVISION_SNAPSHOT"
    FENCING_STATE = "FENCING_STATE"
    TERMINAL_RECONCILIATION_RECEIPT = "TERMINAL_RECONCILIATION_RECEIPT"


@dataclass(frozen=True, slots=True)
class MultiAuthorityRecoveryEvidence:
    """Untrusted evidence claim; authenticity is established only by a verifier.

    payload_digest and attestation_ref are claims, not proof. A trusted verifier
    must authenticate the issuer, attestation, payload bytes and authoritative
    source, and must check replay/revocation/currentness before returning True.
    """

    evidence_id: str
    operation_id: str
    evidence_kind: MultiAuthorityRecoveryEvidenceKind
    issuer_id: str
    issued_at: datetime
    expires_at: datetime
    payload_digest: str
    attestation_ref: str
    targets: tuple[AuthorityChangeTerminalTarget, ...]

    def __post_init__(self) -> None:
        for field in (
            "evidence_id", "operation_id", "issuer_id",
            "payload_digest", "attestation_ref",
        ):
            _required(getattr(self, field), field)
        if not isinstance(self.evidence_kind, MultiAuthorityRecoveryEvidenceKind):
            raise ContractError("evidence_kind debe ser MultiAuthorityRecoveryEvidenceKind")
        _utc(self.issued_at, "issued_at")
        _utc(self.expires_at, "expires_at")
        if self.expires_at <= self.issued_at:
            raise ContractError("expires_at debe ser posterior a issued_at")
        if (
            len(self.payload_digest) != 64
            or any(char not in "0123456789abcdef" for char in self.payload_digest)
        ):
            raise ContractError("payload_digest debe ser SHA-256 hexadecimal lowercase")
        if not isinstance(self.targets, tuple) or len(self.targets) < 2:
            raise ContractError("targets debe contener al menos dos objetivos")
        if any(
            not isinstance(target, AuthorityChangeTerminalTarget)
            for target in self.targets
        ):
            raise ContractError("targets contiene un tipo no permitido")
        identities = tuple(
            (target.authority_kind.value, target.authority_id)
            for target in self.targets
        )
        if len(set(identities)) != len(identities):
            raise ContractError("targets no puede contener identidades duplicadas")
        canonical = tuple(sorted(
            self.targets,
            key=lambda target: (target.authority_kind.value, target.authority_id),
        ))
        object.__setattr__(self, "targets", canonical)

    def matches(
        self,
        operation_id: str,
        evidence_kind: MultiAuthorityRecoveryEvidenceKind,
        targets: tuple[AuthorityChangeTarget, ...],
    ) -> bool:
        if (
            self.operation_id != operation_id
            or self.evidence_kind is not evidence_kind
            or not isinstance(targets, tuple)
        ):
            return False
        expected = tuple(sorted(
            (
                target.authority_kind.value,
                target.authority_id,
                target.expected_revision,
                target.proposed_revision,
            )
            for target in targets
            if isinstance(target, AuthorityChangeTarget)
        ))
        if len(expected) != len(targets):
            return False
        actual = tuple(
            (
                target.authority_kind.value,
                target.authority_id,
                target.expected_revision,
                target.proposed_revision,
            )
            for target in self.targets
        )
        return actual == expected


class MultiAuthorityRecoveryDecisionKind(str, Enum):
    """Non-executable recommendation for handling an assessed operation."""

    NO_RECOVERY_ACTION = "NO_RECOVERY_ACTION"
    REVALIDATE_AUTHORITY = "REVALIDATE_AUTHORITY"
    VERIFY_INVALIDATION_OUTCOME = "VERIFY_INVALIDATION_OUTCOME"
    VERIFY_SOURCE_OUTCOME = "VERIFY_SOURCE_OUTCOME"
    VERIFY_SOURCE_BEFORE_RECONCILIATION = "VERIFY_SOURCE_BEFORE_RECONCILIATION"
    VERIFY_RECONCILIATION_STATE = "VERIFY_RECONCILIATION_STATE"
    VERIFY_TERMINAL_EVIDENCE_BEFORE_RELEASE = "VERIFY_TERMINAL_EVIDENCE_BEFORE_RELEASE"
    MANUAL_INTERVENTION_REQUIRED = "MANUAL_INTERVENTION_REQUIRED"


class MultiAuthorityRecoveryEvidenceRequirement(str, Enum):
    """Independent evidence required before a human/coordinator may proceed."""

    FRESH_AUTHORIZATION = "FRESH_AUTHORIZATION"
    CANONICAL_REVISION_SNAPSHOT = "CANONICAL_REVISION_SNAPSHOT"
    INVALIDATION_OUTCOME_RECEIPT = "INVALIDATION_OUTCOME_RECEIPT"
    SOURCE_OUTCOME_RECEIPT = "SOURCE_OUTCOME_RECEIPT"
    FENCING_STATE = "FENCING_STATE"
    AUTHENTICATED_TERMINAL_EVIDENCE = "AUTHENTICATED_TERMINAL_EVIDENCE"
    HUMAN_REVIEW = "HUMAN_REVIEW"


@dataclass(frozen=True, slots=True)
class MultiAuthorityRecoveryDecision:
    """Auditable recommendation; never grants permission or triggers an action.

    The recommendation is bound to one operation and one read-only assessment.
    Required evidence must be independently obtained and verified by a future
    coordinator. No decision in this contract permits automatic execution.
    """

    operation_id: str
    disposition: MultiAuthorityRecoveryDisposition
    decision: MultiAuthorityRecoveryDecisionKind
    required_evidence: tuple[MultiAuthorityRecoveryEvidenceRequirement, ...]
    reason_code: str

    def __post_init__(self) -> None:
        _required(self.operation_id, "operation_id")
        if not isinstance(self.disposition, MultiAuthorityRecoveryDisposition):
            raise ContractError("disposition debe ser MultiAuthorityRecoveryDisposition")
        if not isinstance(self.decision, MultiAuthorityRecoveryDecisionKind):
            raise ContractError("decision debe ser MultiAuthorityRecoveryDecisionKind")
        if not isinstance(self.required_evidence, tuple):
            raise ContractError("required_evidence debe ser tuple")
        if any(
            not isinstance(item, MultiAuthorityRecoveryEvidenceRequirement)
            for item in self.required_evidence
        ):
            raise ContractError("required_evidence contiene un tipo no permitido")
        if len(set(self.required_evidence)) != len(self.required_evidence):
            raise ContractError("required_evidence no puede contener duplicados")
        canonical = tuple(sorted(self.required_evidence, key=lambda item: item.value))
        object.__setattr__(self, "required_evidence", canonical)
        _required(self.reason_code, "reason_code")

    @property
    def automatic_action_permitted(self) -> bool:
        """Recovery decisions are advisory only; automation is never authorized."""
        return False


def recommend_multi_recovery_decision(
    assessment: MultiAuthorityRecoveryAssessment,
) -> MultiAuthorityRecoveryDecision:
    """Return a pure, non-authorizing recommendation for one recovery assessment."""
    if not isinstance(assessment, MultiAuthorityRecoveryAssessment):
        raise ContractError("assessment debe ser MultiAuthorityRecoveryAssessment")

    plans = {
        MultiAuthorityRecoveryDisposition.NOT_STARTED: (
            MultiAuthorityRecoveryDecisionKind.NO_RECOVERY_ACTION,
            (),
            "OPERATION_NOT_STARTED",
        ),
        MultiAuthorityRecoveryDisposition.CLAIMED_BEFORE_INVALIDATION: (
            MultiAuthorityRecoveryDecisionKind.REVALIDATE_AUTHORITY,
            (
                MultiAuthorityRecoveryEvidenceRequirement.FRESH_AUTHORIZATION,
                MultiAuthorityRecoveryEvidenceRequirement.CANONICAL_REVISION_SNAPSHOT,
            ),
            "CLAIMS_HELD_BEFORE_INVALIDATION",
        ),
        MultiAuthorityRecoveryDisposition.INVALIDATION_OUTCOME_UNKNOWN: (
            MultiAuthorityRecoveryDecisionKind.VERIFY_INVALIDATION_OUTCOME,
            (
                MultiAuthorityRecoveryEvidenceRequirement.INVALIDATION_OUTCOME_RECEIPT,
                MultiAuthorityRecoveryEvidenceRequirement.FENCING_STATE,
            ),
            "INVALIDATION_RESULT_MUST_BE_VERIFIED",
        ),
        MultiAuthorityRecoveryDisposition.SOURCE_OUTCOME_UNKNOWN: (
            MultiAuthorityRecoveryDecisionKind.VERIFY_SOURCE_OUTCOME,
            (
                MultiAuthorityRecoveryEvidenceRequirement.CANONICAL_REVISION_SNAPSHOT,
                MultiAuthorityRecoveryEvidenceRequirement.SOURCE_OUTCOME_RECEIPT,
                MultiAuthorityRecoveryEvidenceRequirement.FENCING_STATE,
            ),
            "SOURCE_RESULT_MUST_BE_VERIFIED_WITHOUT_RETRY",
        ),
        MultiAuthorityRecoveryDisposition.SOURCE_CONFIRMATION_RECORDED: (
            MultiAuthorityRecoveryDecisionKind.VERIFY_SOURCE_BEFORE_RECONCILIATION,
            (
                MultiAuthorityRecoveryEvidenceRequirement.CANONICAL_REVISION_SNAPSHOT,
                MultiAuthorityRecoveryEvidenceRequirement.INVALIDATION_OUTCOME_RECEIPT,
                MultiAuthorityRecoveryEvidenceRequirement.FENCING_STATE,
            ),
            "RECORDED_SOURCE_CONFIRMATION_REQUIRES_INDEPENDENT_VERIFICATION",
        ),
        MultiAuthorityRecoveryDisposition.RECONCILIATION_IN_PROGRESS: (
            MultiAuthorityRecoveryDecisionKind.VERIFY_RECONCILIATION_STATE,
            (
                MultiAuthorityRecoveryEvidenceRequirement.CANONICAL_REVISION_SNAPSHOT,
                MultiAuthorityRecoveryEvidenceRequirement.INVALIDATION_OUTCOME_RECEIPT,
                MultiAuthorityRecoveryEvidenceRequirement.FENCING_STATE,
            ),
            "RECONCILIATION_MUST_BE_VERIFIED_FOR_ALL_TARGETS",
        ),
        MultiAuthorityRecoveryDisposition.TERMINAL_CLAIMS_HELD: (
            MultiAuthorityRecoveryDecisionKind.VERIFY_TERMINAL_EVIDENCE_BEFORE_RELEASE,
            (
                MultiAuthorityRecoveryEvidenceRequirement.AUTHENTICATED_TERMINAL_EVIDENCE,
                MultiAuthorityRecoveryEvidenceRequirement.CANONICAL_REVISION_SNAPSHOT,
                MultiAuthorityRecoveryEvidenceRequirement.FENCING_STATE,
            ),
            "TERMINAL_CLAIMS_REQUIRE_AUTHENTICATED_EVIDENCE",
        ),
        MultiAuthorityRecoveryDisposition.TERMINAL_RELEASED: (
            MultiAuthorityRecoveryDecisionKind.NO_RECOVERY_ACTION,
            (),
            "TERMINAL_OPERATION_ALREADY_RELEASED",
        ),
        MultiAuthorityRecoveryDisposition.INCONSISTENT: (
            MultiAuthorityRecoveryDecisionKind.MANUAL_INTERVENTION_REQUIRED,
            (
                MultiAuthorityRecoveryEvidenceRequirement.CANONICAL_REVISION_SNAPSHOT,
                MultiAuthorityRecoveryEvidenceRequirement.FENCING_STATE,
                MultiAuthorityRecoveryEvidenceRequirement.HUMAN_REVIEW,
            ),
            "PERSISTED_STATE_IS_INCONSISTENT",
        ),
    }
    decision, evidence, reason = plans[assessment.disposition]
    return MultiAuthorityRecoveryDecision(
        operation_id=assessment.claim_audit.operation_id,
        disposition=assessment.disposition,
        decision=decision,
        required_evidence=evidence,
        reason_code=reason,
    )
