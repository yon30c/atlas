import unittest
from datetime import datetime, timezone

from atlas.core.errors import ContractError
from atlas.memory.authority_changes import (
    AuthorityChangeIntent,
    AuthorityChangeReservation,
    AuthorityChangeResult,
    AuthorityChangeStatus,
    AuthorityChangeTarget,
    AuthorityChangeTargetKind,
    MultiAuthorityChangeIntent,
)
from atlas.memory.consistency import AuthorityKind


NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


class MultiAuthorityChangeModelTests(unittest.TestCase):
    def setUp(self):
        self.grant = AuthorityChangeTarget(
            authority_kind=AuthorityChangeTargetKind.GRANT,
            authority_id="grant-001",
            expected_revision=4,
            proposed_revision=5,
        )
        self.renewal = AuthorityChangeTarget(
            authority_kind=AuthorityChangeTargetKind.GRANT_RENEWAL,
            authority_id="renewal-001",
            expected_revision=2,
            proposed_revision=3,
        )

    def make_intent(self, targets=None):
        return MultiAuthorityChangeIntent(
            idempotency_key="idem-renew-001",
            consumer_id="atlas-consumer",
            action="grant.renewal.approve",
            actor_identity_id="user-001",
            owner_id="user-001",
            project_id="project-001",
            environment_id="development",
            targets=tuple(targets or (self.grant, self.renewal)),
            request_context_ref="request-001",
            requested_at=NOW,
        )

    def test_intent_binds_grant_and_renewal_targets(self):
        intent = self.make_intent()
        self.assertEqual(len(intent.targets), 2)
        self.assertEqual(
            {target.authority_kind for target in intent.targets},
            {
                AuthorityChangeTargetKind.GRANT,
                AuthorityChangeTargetKind.GRANT_RENEWAL,
            },
        )

    def test_targets_are_canonicalized_independent_of_input_order(self):
        first = self.make_intent((self.grant, self.renewal))
        second = self.make_intent((self.renewal, self.grant))
        self.assertEqual(first.targets, second.targets)

    def test_intent_rejects_duplicate_target_identity(self):
        duplicate = AuthorityChangeTarget(
            authority_kind=AuthorityChangeTargetKind.GRANT,
            authority_id="grant-001",
            expected_revision=7,
            proposed_revision=8,
        )
        with self.assertRaises(ContractError):
            self.make_intent((self.grant, duplicate))

    def test_intent_requires_at_least_two_targets(self):
        with self.assertRaises(ContractError):
            self.make_intent((self.grant,))

    def test_target_requires_exactly_one_revision_step(self):
        with self.assertRaises(ContractError):
            AuthorityChangeTarget(
                authority_kind=AuthorityChangeTargetKind.GRANT,
                authority_id="grant-001",
                expected_revision=4,
                proposed_revision=6,
            )

    def test_target_rejects_boolean_revision(self):
        with self.assertRaises(ContractError):
            AuthorityChangeTarget(
                authority_kind=AuthorityChangeTargetKind.GRANT,
                authority_id="grant-001",
                expected_revision=True,
                proposed_revision=2,
            )

    def test_intent_rejects_missing_actor_or_action(self):
        with self.assertRaises(ContractError):
            MultiAuthorityChangeIntent(
                idempotency_key="idem",
                consumer_id="consumer",
                action=" ",
                actor_identity_id="user-001",
                owner_id="user-001",
                project_id=None,
                environment_id=None,
                targets=(self.grant, self.renewal),
                request_context_ref="request",
                requested_at=NOW,
            )

    def test_intent_rejects_non_utc_timestamp(self):
        with self.assertRaises(ContractError):
            MultiAuthorityChangeIntent(
                idempotency_key="idem",
                consumer_id="consumer",
                action="grant.renewal.approve",
                actor_identity_id="user-001",
                owner_id="user-001",
                project_id=None,
                environment_id=None,
                targets=(self.grant, self.renewal),
                request_context_ref="request",
                requested_at=datetime(2026, 11, 14, 12, 0),
            )

    def test_intent_is_immutable(self):
        intent = self.make_intent()
        with self.assertRaises((AttributeError, TypeError)):
            intent.action = "grant.revoke"


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
