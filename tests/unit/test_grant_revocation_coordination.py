import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from atlas.authorization.grant_management import GrantManagementService
from atlas.authorization.grant_revocation import (
    GrantRevocationAuthorizationResult,
    GrantRevocationAuthorizationStatus,
    GrantRevocationAuthorityChangeAuthorization,
    GrantRevocationResult,
)
from atlas.authorization.models import (
    Grant,
    GrantResourceScope,
    GrantRevocationAuthorizationRequest,
    VerifiedGrantRevocationAuthorization,
)
from atlas.core.context import OperationContext
from atlas.core.errors import AuthorizationError
from atlas.core.enums import DelegationMode
from atlas.core.identity import Identity, IdentityKind, IdentityStatus
from tests.fixtures.verified_identity import (
    OWNER_IDENTITY_ID,
    OWNER_USER_ID,
    VERIFIED_OWNER,
    FakeVerifiedIdentityContextVerifier,
)
from atlas.memory.authority_changes import (
    AuthorityChangeIntent,
    AuthorityChangeReservation,
    AuthorityChangeResult,
    AuthorityChangeStatus,
)
from atlas.memory.consistency import AuthorityKind


NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


class InMemoryGrantRepository:
    def __init__(self):
        self.grants = {}
        self.update_calls = 0

    def create(self, grant):
        self.grants[grant.grant_id] = grant

    def get(self, grant_id):
        return self.grants.get(grant_id)

    def update(self, grant):
        self.update_calls += 1
        self.grants[grant.grant_id] = grant

    def list_by_owner(self, owner_user_id):
        return tuple(
            grant for grant in self.grants.values()
            if grant.owner_user_id == owner_user_id
        )


class FakeClock:
    def now(self):
        return NOW + timedelta(seconds=1)


class FakeCAM:
    def authorize_revocation(self, request):
        return VerifiedGrantRevocationAuthorization(
            proof_id="proof-001",
            decision_id="decision-001",
            request_id=request.request_id,
            actor_identity_id=request.actor_identity_id,
            owner_user_id=request.owner_user_id,
            grant_id=request.grant_id,
            expected_revision=request.expected_revision,
            issued_at=NOW,
            expires_at=NOW + timedelta(minutes=5),
            issuer_id="cam-001",
        )


class DenyingCAM:
    def authorize_revocation(self, request):
        return None


class UncertainProofAuthorization:
    def verify_and_consume_for_change(self, **kwargs):
        raise RuntimeError("consumption result unavailable")


class FakeProofAuthorization:
    def verify_and_consume_for_change(
        self,
        request,
        evidence,
        operation_id,
        idempotency_key,
        proposed_revision,
        now,
    ):
        result = GrantRevocationAuthorizationResult(
            operation_id=operation_id,
            grant_id=request.grant_id,
            proof_id=evidence.proof_id,
            status=GrantRevocationAuthorizationStatus.AUTHORIZED,
        )
        return GrantRevocationAuthorityChangeAuthorization(
            operation_id=operation_id,
            request=request,
            evidence=evidence,
            authorization_result=result,
            proposed_revision=proposed_revision,
            consumed_at=now,
        )


class FakeAuthorityChangeCoordinator:
    def __init__(self, repository):
        self.repository = repository
        self.reservations = {}
        self.results = {}
        self.reserve_calls = 0
        self.apply_calls = 0
        self.abort_calls = 0

    def get_by_idempotency_key(self, consumer_id, idempotency_key):
        for result in self.results.values():
            reservation = self.reservations[result.operation_id]
            if (
                reservation.intent.consumer_id == consumer_id
                and reservation.intent.idempotency_key == idempotency_key
            ):
                return result
        return None

    def get_result(self, operation_id):
        return self.results.get(operation_id)

    def get_reservation(self, operation_id):
        return self.reservations.get(operation_id)

    def reserve_change(self, intent):
        self.reserve_calls += 1
        operation_id = f"operation-{self.reserve_calls}"
        reservation = AuthorityChangeReservation(
            operation_id=operation_id,
            intent=intent,
            status=AuthorityChangeStatus.REQUESTED,
        )
        self.reservations[operation_id] = reservation
        self.results[operation_id] = AuthorityChangeResult(
            operation_id=operation_id,
            authority_kind=intent.authority_kind,
            authority_id=intent.authority_id,
            status=AuthorityChangeStatus.REQUESTED,
            previous_revision=intent.expected_revision,
            proposed_revision=intent.proposed_revision,
        )
        return reservation

    def apply_change(self, reservation, authorization, now):
        self.apply_calls += 1
        self.assert_exact_authorization(reservation, authorization)
        grant = self.repository.get(reservation.intent.authority_id)
        revoked = replace(
            grant,
            revoked_at=now,
            revision=reservation.intent.proposed_revision,
        )
        # El fake simula la escritura del adaptador autoritativo, no del servicio.
        self.repository.grants[grant.grant_id] = revoked
        result = AuthorityChangeResult(
            operation_id=reservation.operation_id,
            authority_kind=AuthorityKind.GRANT,
            authority_id=grant.grant_id,
            status=AuthorityChangeStatus.COMPLETED,
            previous_revision=reservation.intent.expected_revision,
            proposed_revision=reservation.intent.proposed_revision,
            source_revision=reservation.intent.proposed_revision,
            invalidation_id=f"invalidation-{reservation.operation_id}",
        )
        self.results[reservation.operation_id] = result
        return result

    def abort_unstarted(self, reservation, now):
        self.abort_calls += 1
        result = AuthorityChangeResult(
            operation_id=reservation.operation_id,
            authority_kind=reservation.intent.authority_kind,
            authority_id=reservation.intent.authority_id,
            status=AuthorityChangeStatus.ABORTED,
            previous_revision=reservation.intent.expected_revision,
            proposed_revision=reservation.intent.proposed_revision,
            source_revision=reservation.intent.expected_revision,
        )
        self.results[reservation.operation_id] = result
        return result

    @staticmethod
    def assert_exact_authorization(reservation, authorization):
        assert authorization.operation_id == reservation.operation_id
        assert authorization.authority_kind is reservation.intent.authority_kind
        assert authorization.authority_id == reservation.intent.authority_id
        assert authorization.expected_revision == reservation.intent.expected_revision
        assert authorization.proposed_revision == reservation.intent.proposed_revision


class GrantRevocationCoordinationTests(unittest.TestCase):
    def setUp(self):
        self.actor = Identity(
            identity_id=OWNER_IDENTITY_ID,
            kind=IdentityKind.USER,
            status=IdentityStatus.ACTIVE,
        )
        self.context = OperationContext(
            request_id="request-001",
            correlation_id="correlation-001",
            actor=self.actor,
            user_id=OWNER_USER_ID,
            origin="unit-test",
            delegation=None,
            project_id="atlas",
            environment="development",
            purpose="manage grants",
            classification="internal",
            created_at=NOW,
        )
        self.grant = Grant(
            grant_id="grant-001",
            owner_user_id=OWNER_USER_ID,
            subject_identity_id="agent-001",
            project_id="atlas",
            environment="development",
            resource_scope=GrantResourceScope("files", frozenset({"file-001"})),
            actions=frozenset({"read"}),
            issued_at=NOW,
            expires_at=NOW + timedelta(days=7),
        )
        self.repository = InMemoryGrantRepository()
        self.repository.create(self.grant)
        self.coordinator = FakeAuthorityChangeCoordinator(self.repository)
        self.identity_verifier = FakeVerifiedIdentityContextVerifier()
        self.service = GrantManagementService(
            self.repository,
            consumer_id="atlas-consumer-001",
            revocation_authorizer=FakeCAM(),
            proof_authorization=FakeProofAuthorization(),
            change_coordinator=self.coordinator,
            clock=FakeClock(),
            identity_verifier=self.identity_verifier,
        )

    def revoke(
        self,
        context=None,
        grant_id=None,
        idempotency_key="idem-001",
        now=NOW,
        *,
        verified_identity=VERIFIED_OWNER,
    ):
        return self.service.revoke(
            context or self.context,
            grant_id or self.grant.grant_id,
            idempotency_key,
            now,
            verified_identity=verified_identity,
        )

    def test_revoke_fails_closed_without_verified_identity_evidence(self):
        with self.assertRaises(AuthorizationError):
            self.service.revoke(self.context, self.grant.grant_id, "idem-no-proof", NOW)
        self.assertEqual(self.coordinator.reserve_calls, 0)

    def test_revoke_rejects_tampered_verified_identity_context(self):
        from dataclasses import replace as dataclass_replace
        tampered = dataclass_replace(
            VERIFIED_OWNER,
            identity_id="f6b2b66f-7c72-4d77-8d84-7d0a8c5a1006",
        )
        with self.assertRaises(AuthorizationError):
            self.revoke(verified_identity=tampered, idempotency_key="idem-tampered")
        self.assertEqual(self.coordinator.reserve_calls, 0)

    def test_revoke_fails_closed_when_identity_verifier_is_unavailable(self):
        service = GrantManagementService(
            self.repository,
            consumer_id="atlas-consumer-001",
            revocation_authorizer=FakeCAM(),
            proof_authorization=FakeProofAuthorization(),
            change_coordinator=self.coordinator,
            clock=FakeClock(),
        )
        with self.assertRaises(AuthorizationError):
            service.revoke(
                self.context,
                self.grant.grant_id,
                "idem-no-verifier",
                NOW,
                verified_identity=VERIFIED_OWNER,
            )
        self.assertEqual(self.coordinator.reserve_calls, 0)

    def test_revoke_uses_coordinator_and_never_repository_update(self):
        result = self.revoke(
            self.context, self.grant.grant_id, "idem-001", NOW
        )
        self.assertIsInstance(result, GrantRevocationResult)
        self.assertEqual(result.status, AuthorityChangeStatus.COMPLETED)
        self.assertEqual(result.revoked_grant.revision, 2)
        self.assertEqual(self.repository.update_calls, 0)
        self.assertEqual(self.coordinator.apply_calls, 1)

    def test_revoke_replay_returns_same_operation_without_second_effect(self):
        first = self.revoke(
            self.context, self.grant.grant_id, "idem-001", NOW
        )
        second = self.revoke(
            self.context, self.grant.grant_id, "idem-001", NOW + timedelta(seconds=2)
        )
        self.assertEqual(first.operation_id, second.operation_id)
        self.assertEqual(second.status, AuthorityChangeStatus.COMPLETED)
        self.assertEqual(self.coordinator.reserve_calls, 1)
        self.assertEqual(self.coordinator.apply_calls, 1)

    def test_revoke_rejects_non_owner_before_coordinator(self):
        other_actor = Identity(
            identity_id="user-002",
            kind=IdentityKind.USER,
            status=IdentityStatus.ACTIVE,
        )
        other_context = replace(
            self.context,
            actor=other_actor,
            user_id="user-002",
        )
        with self.assertRaises(AuthorizationError):
            self.revoke(
                other_context, self.grant.grant_id, "idem-002", NOW
            )
        self.assertEqual(self.coordinator.reserve_calls, 0)

    def test_cam_denial_aborts_only_when_coordinator_confirms_source_unchanged(self):
        self.service._revocation_authorizer = DenyingCAM()
        result = self.revoke(
            self.context, self.grant.grant_id, "idem-denied", NOW
        )
        self.assertEqual(result.status, AuthorityChangeStatus.ABORTED)
        self.assertEqual(self.coordinator.abort_calls, 1)
        self.assertEqual(self.coordinator.apply_calls, 0)

    def test_uncertain_proof_consumption_never_starts_or_aborts_change(self):
        self.service._proof_authorization = UncertainProofAuthorization()
        result = self.revoke(
            self.context, self.grant.grant_id, "idem-uncertain", NOW
        )
        self.assertEqual(result.status, AuthorityChangeStatus.BLOCKED)
        self.assertEqual(self.coordinator.abort_calls, 0)
        self.assertEqual(self.coordinator.apply_calls, 0)

    def test_revoke_requires_direct_non_delegated_owner_action(self):
        delegated = replace(self.context, delegation=DelegationMode.DELEGATED)
        with self.assertRaises(AuthorizationError):
            self.revoke(
                delegated, self.grant.grant_id, "idem-003", NOW
            )
        self.assertEqual(self.coordinator.reserve_calls, 0)


if __name__ == "__main__":
    unittest.main()
