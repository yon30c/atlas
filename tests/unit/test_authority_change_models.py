import unittest
from datetime import datetime, timezone

from atlas.core.errors import ContractError
from atlas.memory.authority_changes import (
    AuthorityChangeIntent,
    AuthorityChangeReservation,
    AuthorityChangeResult,
    AuthorityChangeStatus,
)
from atlas.memory.consistency import AuthorityKind


NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


class AuthorityChangeModelTests(unittest.TestCase):
    def setUp(self):
        self.intent = AuthorityChangeIntent(
            idempotency_key="idem-001",
            consumer_id="consumer-001",
            authority_kind=AuthorityKind.GRANT,
            authority_id="grant-001",
            expected_revision=4,
            proposed_revision=5,
            change_kind="revoke",
            request_context_ref="request-001",
            requested_at=NOW,
        )

    def test_intent_is_complete_and_does_not_assign_operation_id(self):
        self.assertEqual(self.intent.authority_id, "grant-001")
        self.assertEqual(self.intent.expected_revision, 4)
        self.assertEqual(self.intent.proposed_revision, 5)
        self.assertFalse(hasattr(self.intent, "operation_id"))

    def test_intent_rejects_non_monotonic_revision(self):
        with self.assertRaises(ContractError):
            AuthorityChangeIntent(
                idempotency_key="idem-001",
                consumer_id="consumer-001",
                authority_kind=AuthorityKind.GRANT,
                authority_id="grant-001",
                expected_revision=5,
                proposed_revision=5,
                change_kind="revoke",
                request_context_ref="request-001",
                requested_at=NOW,
            )

    def test_reservation_requires_exact_intent_and_state(self):
        reservation = AuthorityChangeReservation(
            operation_id="operation-001",
            intent=self.intent,
            status=AuthorityChangeStatus.REQUESTED,
        )
        self.assertEqual(reservation.intent, self.intent)
        self.assertEqual(reservation.status, AuthorityChangeStatus.REQUESTED)

    def test_completed_requires_proposed_source_revision_and_invalidation(self):
        result = AuthorityChangeResult(
            operation_id="operation-001",
            authority_kind=AuthorityKind.GRANT,
            authority_id="grant-001",
            status=AuthorityChangeStatus.COMPLETED,
            previous_revision=4,
            proposed_revision=5,
            source_revision=5,
            invalidation_id="invalidation-001",
        )
        self.assertEqual(result.source_revision, 5)
        with self.assertRaises(ContractError):
            AuthorityChangeResult(
                operation_id="operation-001",
                authority_kind=AuthorityKind.GRANT,
                authority_id="grant-001",
                status=AuthorityChangeStatus.COMPLETED,
                previous_revision=4,
                proposed_revision=5,
                source_revision=4,
                invalidation_id="invalidation-001",
            )

    def test_aborted_requires_source_still_at_previous_revision(self):
        AuthorityChangeResult(
            operation_id="operation-001",
            authority_kind=AuthorityKind.GRANT,
            authority_id="grant-001",
            status=AuthorityChangeStatus.ABORTED,
            previous_revision=4,
            proposed_revision=5,
            source_revision=4,
        )
        with self.assertRaises(ContractError):
            AuthorityChangeResult(
                operation_id="operation-001",
                authority_kind=AuthorityKind.GRANT,
                authority_id="grant-001",
                status=AuthorityChangeStatus.ABORTED,
                previous_revision=4,
                proposed_revision=5,
                source_revision=5,
            )


if __name__ == "__main__":
    unittest.main()
