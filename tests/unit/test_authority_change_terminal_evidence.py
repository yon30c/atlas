"""Contracts for durable terminal evidence of multi-authority operations."""
from datetime import datetime, timezone
import unittest

from atlas.core.errors import ContractError
from atlas.memory.authority_changes import (
    AuthorityChangeStatus,
    AuthorityChangeTarget,
    AuthorityChangeTargetKind,
    AuthorityChangeTerminalEvidence,
    AuthorityChangeTerminalOutcome,
    AuthorityChangeTerminalTarget,
    MultiAuthorityChangeIntent,
    MultiAuthorityChangeReservation,
)


NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def reservation():
    intent = MultiAuthorityChangeIntent(
        idempotency_key="renewal-001",
        consumer_id="atlas-consumer",
        action="grant.renewal.approve",
        actor_identity_id="user-001",
        owner_id="user-001",
        project_id="project-001",
        environment_id="development",
        targets=(
            AuthorityChangeTarget(
                AuthorityChangeTargetKind.GRANT, "grant-001", 4, 5
            ),
            AuthorityChangeTarget(
                AuthorityChangeTargetKind.GRANT_RENEWAL, "renewal-001", 2, 3
            ),
        ),
        request_context_ref="request-001",
        requested_at=NOW,
    )
    return MultiAuthorityChangeReservation(
        operation_id="operation-001",
        intent=intent,
        status=AuthorityChangeStatus.RECONCILING,
    )


def targets(*, outcome=AuthorityChangeTerminalOutcome.COMPLETED):
    grant_revision = 5 if outcome is AuthorityChangeTerminalOutcome.COMPLETED else 4
    renewal_revision = 3 if outcome is AuthorityChangeTerminalOutcome.COMPLETED else 2
    return (
        AuthorityChangeTerminalTarget(
            AuthorityChangeTargetKind.GRANT, "grant-001", 4, 5, grant_revision
        ),
        AuthorityChangeTerminalTarget(
            AuthorityChangeTargetKind.GRANT_RENEWAL,
            "renewal-001", 2, 3, renewal_revision,
        ),
    )


def evidence(**overrides):
    values = {
        "evidence_id": "receipt-001",
        "operation_id": "operation-001",
        "outcome": AuthorityChangeTerminalOutcome.COMPLETED,
        "targets": targets(),
        "evidence_ref": "reconciliation://receipt-001",
        "recorded_by": "consistency-coordinator",
        "recorded_at": NOW,
    }
    values.update(overrides)
    return AuthorityChangeTerminalEvidence(**values)


class AuthorityChangeTerminalEvidenceTests(unittest.TestCase):
    def test_completed_evidence_binds_every_proposed_revision(self):
        receipt = evidence()
        self.assertTrue(receipt.matches(reservation()))
        self.assertEqual(receipt.outcome, AuthorityChangeTerminalOutcome.COMPLETED)

    def test_aborted_evidence_binds_every_original_revision(self):
        receipt = evidence(
            outcome=AuthorityChangeTerminalOutcome.ABORTED,
            targets=targets(outcome=AuthorityChangeTerminalOutcome.ABORTED),
        )
        self.assertTrue(receipt.matches(reservation()))

    def test_evidence_rejects_observed_revision_not_matching_outcome(self):
        wrong = (
            AuthorityChangeTerminalTarget(
                AuthorityChangeTargetKind.GRANT, "grant-001", 4, 5, 4
            ),
            targets()[1],
        )
        with self.assertRaises(ContractError):
            evidence(targets=wrong)

    def test_evidence_must_cover_exact_operation_and_all_targets(self):
        self.assertFalse(evidence(operation_id="another-operation").matches(reservation()))
        incomplete = evidence(targets=(targets()[0],))
        self.assertFalse(incomplete.matches(reservation()))

    def test_evidence_rejects_changed_target_revision_or_identity(self):
        changed = (
            AuthorityChangeTerminalTarget(
                AuthorityChangeTargetKind.GRANT, "grant-001", 4, 5, 5
            ),
            AuthorityChangeTerminalTarget(
                AuthorityChangeTargetKind.GRANT_RENEWAL,
                "renewal-other", 2, 3, 3,
            ),
        )
        self.assertFalse(evidence(targets=changed).matches(reservation()))

    def test_evidence_rejects_duplicate_targets(self):
        duplicate = (targets()[0], targets()[0])
        with self.assertRaises(ContractError):
            evidence(targets=duplicate)

    def test_evidence_requires_durable_reference_and_recorder(self):
        with self.assertRaises(ContractError):
            evidence(evidence_ref=" ")
        with self.assertRaises(ContractError):
            evidence(recorded_by=" ")

    def test_evidence_requires_utc_timestamp(self):
        with self.assertRaises(ContractError):
            evidence(recorded_at=datetime(2026, 11, 16, 12, 0))

    def test_evidence_and_targets_are_immutable(self):
        receipt = evidence()
        with self.assertRaises((AttributeError, TypeError)):
            receipt.outcome = AuthorityChangeTerminalOutcome.ABORTED
        with self.assertRaises((AttributeError, TypeError)):
            receipt.targets[0].observed_revision = 4

    def test_targets_are_canonicalized(self):
        reversed_targets = tuple(reversed(targets()))
        receipt = evidence(targets=reversed_targets)
        self.assertEqual(
            [(item.authority_kind.value, item.authority_id) for item in receipt.targets],
            [("grant", "grant-001"), ("grant_renewal", "renewal-001")],
        )


if __name__ == "__main__":
    unittest.main()
