import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from atlas.authorization.models import (
    Grant,
    GrantRenewalRequest,
    GrantResourceScope,
    RenewalStatus,
)
from atlas.authorization.renewal_service import GrantRenewalService
from atlas.core.context import OperationContext
from atlas.core.enums import DelegationMode
from atlas.core.errors import (
    AuthorizationError,
    ConcurrencyError,
    ContractError,
    NotFoundError,
)
from atlas.core.identity import Identity, IdentityKind, IdentityStatus
from tests.fakes.authorization_unit_of_work import (
    InMemoryAuthorizationUnitOfWorkFactory,
    InMemoryGrantRepository,
    InMemoryRenewalRepository,
    _UnitOfWorkRenewalRepository,
)
from tests.fixtures.verified_identity import (
    OWNER_IDENTITY_ID,
    OWNER_USER_ID,
    VERIFIED_OWNER,
    FakeVerifiedIdentityContextVerifier,
)


NOW = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)


class GrantRenewalServiceTests(unittest.TestCase):
    def setUp(self):
        self.subject = Identity(
            identity_id="agent-001",
            kind=IdentityKind.AGENT,
            status=IdentityStatus.ACTIVE,
        )
        self.context = OperationContext(
            request_id="request-001",
            correlation_id="correlation-001",
            actor=self.subject,
            user_id=OWNER_USER_ID,
            origin="unit-test",
            delegation=DelegationMode.DELEGATED,
            project_id="atlas",
            environment="development",
            purpose="renew grant",
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
            issued_at=NOW - timedelta(days=1),
            expires_at=NOW + timedelta(days=2),
        )
        self.grant_repository = InMemoryGrantRepository()
        self.renewal_repository = InMemoryRenewalRepository()
        self.unit_of_work_factory = InMemoryAuthorizationUnitOfWorkFactory(
            self.grant_repository,
            self.renewal_repository,
        )
        self.grant_repository.create(self.grant)
        self.service = GrantRenewalService(
            self.unit_of_work_factory,
            identity_verifier=FakeVerifiedIdentityContextVerifier(),
        )
        self.proposed_expires_at = NOW + timedelta(days=9)

    def seed_pending_renewal(self, renewal_id="renewal-001"):
        request = GrantRenewalRequest(
            renewal_id=renewal_id,
            grant_id=self.grant.grant_id,
            owner_user_id=self.grant.owner_user_id,
            subject_identity_id=self.grant.subject_identity_id,
            requested_by_identity_id=self.grant.subject_identity_id,
            current_expires_at=self.grant.expires_at,
            proposed_expires_at=self.proposed_expires_at,
            requested_at=NOW,
        )
        self.renewal_repository.create(request)
        return request

    def owner_context(
        self,
        user_id=OWNER_USER_ID,
        project_id="atlas",
        environment="development",
    ):
        actor = Identity(
            identity_id=OWNER_IDENTITY_ID,
            kind=IdentityKind.USER,
            status=IdentityStatus.ACTIVE,
        )
        return replace(
            self.context,
            actor=actor,
            user_id=user_id,
            delegation=None,
            project_id=project_id,
            environment=environment,
        )

    def approve(self, context, renewal_id, now, evidence=VERIFIED_OWNER):
        return self.service.approve_renewal(
            context, renewal_id, now, verified_identity=evidence
        )

    def reject(self, context, renewal_id, now, evidence=VERIFIED_OWNER):
        return self.service.reject_renewal(
            context, renewal_id, now, verified_identity=evidence
        )

    def test_agent_request_is_fail_closed_without_agent_and_delegation_authorities(self):
        with self.assertRaises(AuthorizationError):
            self.service.request_renewal(
                self.context,
                "renewal-001",
                self.grant.grant_id,
                self.proposed_expires_at,
                NOW,
            )
        self.assertIsNone(self.renewal_repository.get("renewal-001"))
        self.assertEqual(
            self.grant_repository.get(self.grant.grant_id),
            self.grant,
        )

    def test_approval_updates_grant_and_records_canonical_owner_decision(self):
        request = self.seed_pending_renewal()
        approval_time = NOW + timedelta(hours=1)
        updated_grant = self.approve(
            self.owner_context(), request.renewal_id, approval_time
        )
        updated_request = self.renewal_repository.get(request.renewal_id)
        self.assertEqual(updated_grant.expires_at, self.proposed_expires_at)
        self.assertEqual(updated_grant.revision, self.grant.revision + 1)
        self.assertEqual(
            self.grant_repository.get(self.grant.grant_id),
            updated_grant,
        )
        self.assertEqual(updated_request.status, RenewalStatus.APPROVED)
        self.assertEqual(updated_request.decided_at, approval_time)
        self.assertEqual(updated_request.decided_by_user_id, OWNER_USER_ID)
        self.assertNotEqual(OWNER_USER_ID, OWNER_IDENTITY_ID)

    def test_approval_requires_verified_owner_and_exact_scope(self):
        request = self.seed_pending_renewal()
        invalid_contexts = (
            self.owner_context(user_id="a6b2b66f-7c72-4d77-8d84-7d0a8c5a1999"),
            self.owner_context(project_id="other-project"),
            self.owner_context(environment="production"),
        )
        for context in invalid_contexts:
            with self.subTest(context=context):
                with self.assertRaises(AuthorizationError):
                    self.approve(
                        context, request.renewal_id, NOW + timedelta(hours=1)
                    )

        with self.assertRaises(AuthorizationError):
            self.service.approve_renewal(
                self.owner_context(),
                request.renewal_id,
                NOW + timedelta(hours=1),
            )

        tampered = replace(
            VERIFIED_OWNER,
            user_id="a6b2b66f-7c72-4d77-8d84-7d0a8c5a1999",
        )
        with self.assertRaises(AuthorizationError):
            self.approve(
                self.owner_context(),
                request.renewal_id,
                NOW + timedelta(hours=1),
                evidence=tampered,
            )

    def test_approval_fails_closed_when_identity_verifier_is_unavailable(self):
        request = self.seed_pending_renewal()
        service = GrantRenewalService(self.unit_of_work_factory)
        with self.assertRaises(AuthorizationError):
            service.approve_renewal(
                self.owner_context(),
                request.renewal_id,
                NOW + timedelta(hours=1),
                verified_identity=VERIFIED_OWNER,
            )

    def test_approval_rejects_changed_or_expired_grant(self):
        request = self.seed_pending_renewal()
        changed_grant = replace(
            self.grant,
            expires_at=self.grant.expires_at + timedelta(days=1),
        )
        self.grant_repository.update(changed_grant)
        with self.assertRaises(ContractError):
            self.approve(
                self.owner_context(),
                request.renewal_id,
                NOW + timedelta(hours=1),
            )

        self.grant_repository.update(self.grant)
        with self.assertRaises(AuthorizationError):
            self.approve(
                self.owner_context(), request.renewal_id, self.grant.expires_at
            )

    def test_rejection_records_decision_without_changing_grant(self):
        request = self.seed_pending_renewal()
        decision_time = NOW + timedelta(hours=1)
        rejected_request = self.reject(
            self.owner_context(), request.renewal_id, decision_time
        )
        self.assertEqual(rejected_request.status, RenewalStatus.REJECTED)
        self.assertEqual(rejected_request.decided_at, decision_time)
        self.assertEqual(rejected_request.decided_by_user_id, OWNER_USER_ID)
        self.assertEqual(
            self.grant_repository.get(self.grant.grant_id),
            self.grant,
        )

    def test_rejection_requires_verified_owner_and_exact_scope(self):
        request = self.seed_pending_renewal()
        invalid_contexts = (
            self.owner_context(user_id="a6b2b66f-7c72-4d77-8d84-7d0a8c5a1999"),
            self.owner_context(project_id="other-project"),
            self.owner_context(environment="production"),
        )
        for context in invalid_contexts:
            with self.subTest(context=context):
                with self.assertRaises(AuthorizationError):
                    self.reject(
                        context, request.renewal_id, NOW + timedelta(hours=1)
                    )
        with self.assertRaises(AuthorizationError):
            self.service.reject_renewal(
                self.owner_context(),
                request.renewal_id,
                NOW + timedelta(hours=1),
            )

    def test_decisions_are_single_use_and_unknown_request_is_not_found(self):
        request = self.seed_pending_renewal()
        owner_context = self.owner_context()
        self.approve(
            owner_context, request.renewal_id, NOW + timedelta(hours=1)
        )
        with self.assertRaises(ContractError):
            self.approve(
                owner_context, request.renewal_id, NOW + timedelta(hours=2)
            )
        with self.assertRaises(ContractError):
            self.reject(
                owner_context, request.renewal_id, NOW + timedelta(hours=2)
            )
        with self.assertRaises(NotFoundError):
            self.reject(
                owner_context, "missing-renewal", NOW + timedelta(hours=1)
            )

    def test_approval_failure_rolls_back_grant_and_request(self):
        request = self.seed_pending_renewal("renewal-atomic")
        self.renewal_repository.fail_on_update = True

        with self.assertRaises(RuntimeError):
            self.approve(
                self.owner_context(),
                request.renewal_id,
                NOW + timedelta(hours=1),
            )

        stored_grant = self.grant_repository.get(self.grant.grant_id)
        stored_request = self.renewal_repository.get(request.renewal_id)
        self.assertEqual(stored_grant, self.grant)
        self.assertEqual(stored_request.status, RenewalStatus.PENDING)

    def test_approval_concurrency_conflict_rolls_back_grant(self):
        request = self.seed_pending_renewal()
        concurrent_request = replace(
            request,
            status=RenewalStatus.REJECTED,
            decided_at=NOW + timedelta(minutes=30),
            decided_by_user_id=OWNER_USER_ID,
            version=2,
        )
        original_update_if_version = (
            _UnitOfWorkRenewalRepository.update_if_version
        )

        def simulate_concurrent_update(
            repository,
            proposed_request,
            expected_version,
        ):
            self.renewal_repository.requests[request.renewal_id] = (
                concurrent_request
            )
            return original_update_if_version(
                repository,
                proposed_request,
                expected_version,
            )

        with patch.object(
            _UnitOfWorkRenewalRepository,
            "update_if_version",
            new=simulate_concurrent_update,
        ):
            with self.assertRaises(ConcurrencyError):
                self.approve(
                    self.owner_context(),
                    request.renewal_id,
                    NOW + timedelta(hours=1),
                )

        self.assertEqual(
            self.grant_repository.get(self.grant.grant_id),
            self.grant,
        )
        self.assertEqual(
            self.renewal_repository.get(request.renewal_id),
            concurrent_request,
        )

    def test_rejection_concurrency_conflict_preserves_concurrent_approval(self):
        request = self.seed_pending_renewal()
        concurrent_request = replace(
            request,
            status=RenewalStatus.APPROVED,
            decided_at=NOW + timedelta(minutes=30),
            decided_by_user_id=OWNER_USER_ID,
            version=2,
        )
        original_update_if_version = (
            _UnitOfWorkRenewalRepository.update_if_version
        )

        def simulate_concurrent_update(
            repository,
            proposed_request,
            expected_version,
        ):
            self.renewal_repository.requests[request.renewal_id] = (
                concurrent_request
            )
            return original_update_if_version(
                repository,
                proposed_request,
                expected_version,
            )

        with patch.object(
            _UnitOfWorkRenewalRepository,
            "update_if_version",
            new=simulate_concurrent_update,
        ):
            with self.assertRaises(ConcurrencyError):
                self.reject(
                    self.owner_context(),
                    request.renewal_id,
                    NOW + timedelta(hours=1),
                )

        self.assertEqual(
            self.grant_repository.get(self.grant.grant_id),
            self.grant,
        )
        self.assertEqual(
            self.renewal_repository.get(request.renewal_id),
            concurrent_request,
        )


if __name__ == "__main__":
    unittest.main()
