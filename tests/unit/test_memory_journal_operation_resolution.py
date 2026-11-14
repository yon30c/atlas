"""Tests puros del contrato de resolución de escrituras ambiguas ME-03K-B."""
from datetime import datetime, timezone
import unittest

from atlas.core.errors import ContractError
from atlas.memory.journal import (
    ConsistencyPosition,
    ConsistencyRecordKind,
    ConsistencyTransition,
    JournalCommit,
    JournalOperationResolution,
    JournalOperationResolutionStatus,
)


class JournalOperationResolutionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
        self.expected = ConsistencyPosition("domain-a", 3, 10)
        self.transition = ConsistencyTransition(
            record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074502",
            schema_version=1,
            record_kind=ConsistencyRecordKind.FORGET_CLOSED,
            operation_id="forget:op-10",
            occurred_at=self.now,
            idempotency_key="forget-idem-10",
            request_id="forget-request-10",
            actor_identity_id="owner-identity-10",
            subject_user_id="owner-user-10",
            owner_id="owner-user-10",
            memory_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074503",
            generation=1,
            proof_reference="forget-proof-10",
        )
        self.commit = JournalCommit(
            position=ConsistencyPosition("domain-a", 3, 11),
            record_id=self.transition.record_id,
            replayed=False,
        )

    def _result(self, status, **overrides):
        values = dict(
            status=status,
            operation_id=self.transition.operation_id,
            idempotency_key=self.transition.idempotency_key,
            expected_position=self.expected,
            expected_transition=self.transition,
            current_position=ConsistencyPosition("domain-a", 3, 11),
            commit=None,
            committed_transition=None,
        )
        values.update(overrides)
        return JournalOperationResolution(**values)

    def test_committed_exact_requires_exact_persisted_transition(self):
        result = self._result(
            JournalOperationResolutionStatus.COMMITTED_EXACT,
            commit=self.commit,
            committed_transition=self.transition,
        )
        self.assertIs(result.status, JournalOperationResolutionStatus.COMMITTED_EXACT)

    def test_committed_exact_rejects_different_transition_even_if_record_id_matches(self):
        conflicting = ConsistencyTransition(
            record_id=self.transition.record_id,
            schema_version=1,
            record_kind=ConsistencyRecordKind.FORGET_CLOSED,
            operation_id=self.transition.operation_id,
            occurred_at=self.now,
            idempotency_key=self.transition.idempotency_key,
            request_id="forget-request-10",
            actor_identity_id="owner-identity-10",
            subject_user_id="owner-user-10",
            owner_id="owner-user-10",
            memory_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074503",
            generation=1,
            proof_reference="different-forget-proof",
        )
        with self.assertRaises(ContractError):
            self._result(
                JournalOperationResolutionStatus.COMMITTED_EXACT,
                commit=self.commit,
                committed_transition=conflicting,
            )

    def test_not_committed_requires_proven_current_position_and_no_commit(self):
        result = self._result(
            JournalOperationResolutionStatus.NOT_COMMITTED,
            current_position=ConsistencyPosition("domain-a", 3, 12),
        )
        self.assertEqual(result.current_position.sequence, 12)

    def test_not_committed_rejects_commit_evidence(self):
        with self.assertRaises(ContractError):
            self._result(
                JournalOperationResolutionStatus.NOT_COMMITTED,
                commit=self.commit,
            )

    def test_unknown_cannot_claim_commit_or_persisted_transition(self):
        with self.assertRaises(ContractError):
            self._result(
                JournalOperationResolutionStatus.UNKNOWN,
                committed_transition=self.transition,
            )

    def test_conflict_does_not_expose_a_commit_as_exact(self):
        result = self._result(
            JournalOperationResolutionStatus.CONFLICT,
            current_position=ConsistencyPosition("domain-a", 3, 11),
        )
        self.assertIs(result.status, JournalOperationResolutionStatus.CONFLICT)

    def test_resolution_cannot_mismatch_operation_or_idempotency_key(self):
        with self.assertRaises(ContractError):
            self._result(
                JournalOperationResolutionStatus.UNKNOWN,
                operation_id="different-operation",
            )
        with self.assertRaises(ContractError):
            self._result(
                JournalOperationResolutionStatus.UNKNOWN,
                idempotency_key="different-key",
            )


if __name__ == "__main__":
    unittest.main()
