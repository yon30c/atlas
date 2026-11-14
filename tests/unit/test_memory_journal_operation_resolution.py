"""Tests puros del contrato de resolución de escrituras ambiguas ME-03K-B."""
import unittest

from atlas.core.errors import ContractError
from atlas.memory.journal import (
    ConsistencyPosition,
    JournalCommit,
    JournalOperationResolution,
    JournalOperationResolutionStatus,
)


class JournalOperationResolutionTests(unittest.TestCase):
    def setUp(self):
        self.expected = ConsistencyPosition("domain-a", 3, 10)
        self.committed = JournalCommit(
            ConsistencyPosition("domain-a", 3, 11),
            "018bcfe5-7b3a-7cc2-98c4-dc0c0c074901",
            False,
        )

    def test_committed_exact_requires_exact_next_sequence(self):
        result = JournalOperationResolution(
            JournalOperationResolutionStatus.COMMITTED_EXACT,
            "operation-1", "idem-1", self.expected,
            ConsistencyPosition("domain-a", 3, 14), self.committed,
        )
        self.assertIs(result.status, JournalOperationResolutionStatus.COMMITTED_EXACT)

    def test_committed_exact_rejects_wrong_domain_or_epoch(self):
        with self.assertRaises(ContractError):
            JournalOperationResolution(
                JournalOperationResolutionStatus.COMMITTED_EXACT,
                "operation-1", None, self.expected,
                ConsistencyPosition("domain-b", 3, 11), self.committed,
            )

    def test_committed_exact_rejects_non_adjacent_commit(self):
        bad = JournalCommit(
            ConsistencyPosition("domain-a", 3, 12),
            "018bcfe5-7b3a-7cc2-98c4-dc0c0c074902", False,
        )
        with self.assertRaises(ContractError):
            JournalOperationResolution(
                JournalOperationResolutionStatus.COMMITTED_EXACT,
                "operation-1", None, self.expected,
                ConsistencyPosition("domain-a", 3, 12), bad,
            )

    def test_not_committed_requires_proven_current_position(self):
        result = JournalOperationResolution(
            JournalOperationResolutionStatus.NOT_COMMITTED,
            "operation-1", "idem-1", self.expected,
            ConsistencyPosition("domain-a", 3, 13), None,
        )
        self.assertIs(result.status, JournalOperationResolutionStatus.NOT_COMMITTED)

    def test_not_committed_rejects_rollback_or_epoch_change(self):
        for current in (
            ConsistencyPosition("domain-a", 3, 9),
            ConsistencyPosition("domain-a", 4, 10),
        ):
            with self.subTest(current=current), self.assertRaises(ContractError):
                JournalOperationResolution(
                    JournalOperationResolutionStatus.NOT_COMMITTED,
                    "operation-1", None, self.expected, current, None,
                )

    def test_unknown_and_conflict_cannot_claim_commit(self):
        for status in (JournalOperationResolutionStatus.UNKNOWN,
                       JournalOperationResolutionStatus.CONFLICT):
            with self.subTest(status=status), self.assertRaises(ContractError):
                JournalOperationResolution(
                    status, "operation-1", None, self.expected,
                    ConsistencyPosition("domain-a", 3, 11), self.committed,
                )

    def test_unknown_is_explicit_and_has_no_commit(self):
        result = JournalOperationResolution(
            JournalOperationResolutionStatus.UNKNOWN,
            "operation-1", "idem-1", self.expected, None, None,
        )
        self.assertIs(result.status, JournalOperationResolutionStatus.UNKNOWN)


if __name__ == "__main__":
    unittest.main()