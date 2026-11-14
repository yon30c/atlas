"""Orchestration for verified local checkpoint publication and SQLite commit.

The coordinator keeps independent projection storage outside SQLite's writer
transaction. It makes no external anti-rollback claim.
"""
from datetime import datetime, timedelta
from typing import Any

from atlas.core.errors import ContractError
from atlas.memory.checkpoint_projection_codec import (
    build_checkpoint_projection_artifacts,
)
from atlas.memory.journal import (
    CheckpointCommitResult,
    CheckpointCommitStatus,
    ConsistencyCheckpoint,
    ConsistencyPosition,
    ConsistencyRecordKind,
    JournalCommit,
)
from atlas.memory.local_trust_policy import (
    LocalConsistencyTrustPolicy,
    LocalIssuerAuthorization,
)
from atlas.memory.trust import (
    ConsistencyRecoveryVerificationResult,
    ConsistencyRecoveryVerificationStatus,
    VerifiedLocalConsistencyRecoveryState,
)
from atlas.ports.checkpoint_projection_store import (
    LocalCheckpointProjectionPublisherPort,
)
from atlas.memory.ports.recovery import (
    CheckpointProjectionPort,
    CheckpointProjectionRequest,
    CheckpointProjectionResult,
    RecoveryVerificationStatus,
    require_verified_checkpoint_projection,
)


class LocalCheckpointCoordinator:
    """Publish, read back, verify and atomically commit a local checkpoint.

    The journal must already be composed with a recovery verifier and the same
    independent projection resolver. The publisher/resolver supplied here must
    address storage independent from the SQLite journal.
    """

    def __init__(
        self,
        journal: Any,
        projection_publisher: LocalCheckpointProjectionPublisherPort,
        projection_resolver: CheckpointProjectionPort,
        trust_policy: LocalConsistencyTrustPolicy,
        *,
        reducer_version: str,
    ) -> None:
        if not callable(getattr(journal, "load_verified_recovery_state", None)):
            raise ContractError("journal debe exponer load_verified_recovery_state")
        if not callable(getattr(journal, "commit_checkpoint", None)):
            raise ContractError("journal debe exponer commit_checkpoint")
        if not callable(getattr(projection_publisher, "publish_checkpoint_projection", None)):
            raise ContractError("projection_publisher debe implementar publish_checkpoint_projection")
        if not callable(getattr(projection_resolver, "resolve_checkpoint_projection", None)):
            raise ContractError("projection_resolver debe implementar resolve_checkpoint_projection")
        for name in ("issuer_id", "issuer_role", "key_reference"):
            value = getattr(journal, name, None)
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"journal.{name} debe ser una cadena no vacía")
        if getattr(journal, "reducer_version", None) != reducer_version:
            raise ContractError("reducer_version no coincide con el journal")
        if getattr(journal, "trust_policy_version", None) != getattr(
            trust_policy, "policy_version", None
        ):
            raise ContractError("trust_policy_version no coincide con el journal")
        if getattr(journal, "recovery_trust_policy", None) is not trust_policy:
            raise ContractError("el journal debe usar exactamente trust_policy")
        if getattr(journal, "checkpoint_projection_port", None) is not projection_resolver:
            raise ContractError(
                "el journal debe usar el mismo resolver de proyecciones que el coordinador"
            )
        if not isinstance(trust_policy, LocalConsistencyTrustPolicy):
            raise ContractError("trust_policy debe ser LocalConsistencyTrustPolicy")
        if not isinstance(reducer_version, str) or not reducer_version.strip():
            raise ContractError("reducer_version debe ser una cadena no vacía")
        if reducer_version not in trust_policy.allowed_reducer_versions:
            raise ContractError("reducer_version no está permitida por trust_policy")
        if 1 not in trust_policy.allowed_schema_versions:
            raise ContractError("schema_version 1 debe estar permitida por trust_policy")
        self._trust_policy = trust_policy
        self._reducer_version = reducer_version
        self._journal = journal
        self._publisher = projection_publisher
        self._resolver = projection_resolver

    @staticmethod
    def _conflict() -> CheckpointCommitResult:
        return CheckpointCommitResult(CheckpointCommitStatus.CONFLICT)

    @staticmethod
    def _unavailable() -> CheckpointCommitResult:
        return CheckpointCommitResult(CheckpointCommitStatus.UNAVAILABLE)

    @staticmethod
    def _replayed_existing(
        checkpoint: ConsistencyCheckpoint,
        entries: tuple,
        expected_position: ConsistencyPosition,
        created_at: datetime,
    ) -> CheckpointCommitResult | None:
        """Recognize an exact already-committed checkpoint after an uncertain reply."""
        if (
            checkpoint.position != expected_position
            or checkpoint.created_at != created_at
            or checkpoint.envelope is None
            or not entries
        ):
            return None

        marker_entry = entries[0]
        marker = marker_entry.transition
        if (
            marker_entry.position.sequence != expected_position.sequence + 1
            or marker_entry.position.consistency_domain_id
                != expected_position.consistency_domain_id
            or marker_entry.position.authority_epoch != expected_position.authority_epoch
            or marker.record_id != checkpoint.checkpoint_id
            or marker.record_kind is not ConsistencyRecordKind.CHECKPOINT_COMMITTED
            or marker.operation_id != f"checkpoint:{checkpoint.checkpoint_id}"
            or marker.checkpoint_reference != checkpoint.state_reference
            or marker.occurred_at != checkpoint.created_at
        ):
            return None

        return CheckpointCommitResult(
            CheckpointCommitStatus.REPLAYED,
            checkpoint,
            JournalCommit(marker_entry.position, checkpoint.checkpoint_id, True),
        )

    def commit_checkpoint(
        self,
        checkpoint_id: str,
        expected_position: ConsistencyPosition,
        created_at: datetime,
    ) -> CheckpointCommitResult:
        """Commit a checkpoint for one exact verified head.

        checkpoint_id, expected_position and created_at form the stable retry
        identity. Reuse all three unchanged after UNKNOWN. A changed head is a
        conflict; it is never silently checkpointed as a new request.
        """
        if (
            not isinstance(expected_position, ConsistencyPosition)
            or not isinstance(checkpoint_id, str)
            or not checkpoint_id.strip()
            or not isinstance(created_at, datetime)
            or created_at.tzinfo is None
            or created_at.utcoffset() != timedelta(0)
            or expected_position.consistency_domain_id
                != self._trust_policy.consistency_domain_id
        ):
            return self._conflict()

        try:
            # The checkpoint model validates the Atlas UUIDv7 and UTC timestamp.
            ConsistencyCheckpoint(
                checkpoint_id=checkpoint_id,
                position=expected_position,
                state_reference="pending-state-reference",
                integrity_reference="pending-integrity-reference",
                created_at=created_at,
            )
        except ContractError:
            return self._conflict()

        try:
            verification = self._journal.load_verified_recovery_state(
                self._trust_policy.consistency_domain_id
            )
        except Exception:
            return self._unavailable()

        if not isinstance(verification, ConsistencyRecoveryVerificationResult):
            return self._conflict()
        if verification.status is ConsistencyRecoveryVerificationStatus.UNAVAILABLE:
            return self._unavailable()
        if verification.status is not ConsistencyRecoveryVerificationStatus.VERIFIED:
            return self._conflict()

        verified = verification.verified_local_state
        if not isinstance(verified, VerifiedLocalConsistencyRecoveryState):
            # This coordinator is deliberately restricted to the local profile.
            return self._conflict()
        if verified.trust_policy_version != self._trust_policy.policy_version:
            return self._conflict()

        state = verified.state
        if state.checkpoint is not None and state.checkpoint.checkpoint_id == checkpoint_id:
            replay = self._replayed_existing(
                state.checkpoint, state.entries, expected_position, created_at
            )
            return replay if replay is not None else self._conflict()

        if (
            verified.consistency_domain_id != expected_position.consistency_domain_id
            or verified.authority_epoch != expected_position.authority_epoch
            or verified.head_sequence != expected_position.sequence
            or state.continuity_reference != verified.local_state_commitment
            or not state.entries
        ):
            return self._conflict()

        checkpoint_authorization = LocalIssuerAuthorization(
            "checkpoint", self._journal.issuer_id, self._journal.issuer_role
        )
        journal_authorization = LocalIssuerAuthorization(
            "journal_entry", self._journal.issuer_id, self._journal.issuer_role
        )
        if (
            checkpoint_authorization not in self._trust_policy.issuer_authorizations
            or journal_authorization not in self._trust_policy.issuer_authorizations
            or self._journal.key_reference not in self._trust_policy.allowed_key_references
        ):
            return self._conflict()

        projection = verified.projection
        if (
            projection is None
            or projection.domain_id != expected_position.consistency_domain_id
            or projection.authority_epoch != expected_position.authority_epoch
            or projection.head_sequence != expected_position.sequence
            or projection.replay_metadata_version != 1
        ):
            return self._conflict()

        try:
            artifacts = build_checkpoint_projection_artifacts(
                projection,
                checkpoint_id=checkpoint_id,
                schema_version=1,
                reducer_version=self._reducer_version,
                trust_policy_version=self._trust_policy.policy_version,
            )
            self._publisher.publish_checkpoint_projection(artifacts)
        except ContractError:
            return self._conflict()
        except Exception:
            return self._unavailable()

        try:
            checkpoint = ConsistencyCheckpoint(
                checkpoint_id=checkpoint_id,
                position=expected_position,
                state_reference=artifacts.state_reference,
                integrity_reference=artifacts.integrity_reference,
                created_at=created_at,
            )
            request = CheckpointProjectionRequest(
                checkpoint=checkpoint,
                consistency_domain_id=expected_position.consistency_domain_id,
                authority_epoch=expected_position.authority_epoch,
                trust_policy_version=self._trust_policy.policy_version,
                allowed_schema_versions=self._trust_policy.allowed_schema_versions,
                allowed_reducer_versions=self._trust_policy.allowed_reducer_versions,
            )
            resolution = self._resolver.resolve_checkpoint_projection(request)
        except Exception:
            return self._unavailable()

        if not isinstance(resolution, CheckpointProjectionResult):
            return self._conflict()
        if resolution.status is RecoveryVerificationStatus.UNAVAILABLE:
            return self._unavailable()
        if resolution.status is not RecoveryVerificationStatus.VERIFIED:
            return self._conflict()

        try:
            evidence = require_verified_checkpoint_projection(request, resolution)
        except ContractError:
            return self._conflict()
        if (
            evidence.projection != projection
            or evidence.schema_version != 1
            or evidence.reducer_version != self._reducer_version
            or evidence.trust_policy_version != self._trust_policy.policy_version
            or evidence.state_commitment != artifacts.state_commitment
            or evidence.integrity_commitment != artifacts.integrity_commitment
        ):
            return self._conflict()

        try:
            result = self._journal.commit_checkpoint(
                expected_position,
                verified.local_state_commitment,
                checkpoint,
            )
        except Exception:
            # The SQLite commit may have succeeded while its response was lost.
            return CheckpointCommitResult(CheckpointCommitStatus.UNKNOWN)
        if not isinstance(result, CheckpointCommitResult):
            return CheckpointCommitResult(CheckpointCommitStatus.UNKNOWN)
        return result
