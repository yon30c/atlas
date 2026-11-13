import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from atlas.authorization.models import (
    Grant,
    GrantRenewalRequest,
    RenewalStatus,
    GrantResourceScope,
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
            user_id="user-001",
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
            owner_user_id="user-001",
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
        self.service = GrantRenewalService(self.unit_of_work_factory)
        self.proposed_expires_at = NOW + timedelta(days=9)

    def request_renewal(self, renewal_id="renewal-001"):
        return self.service.request_renewal(
            self.context,
            renewal_id,
            self.grant.grant_id,
            self.proposed_expires_at,
            NOW,
        )

    def owner_context(
        self,
        user_id="user-001",
        project_id="atlas",
        environment="development",
    ):
        actor = Identity(
            identity_id=user_id,
            kind=IdentityKind.USER,
            status=IdentityStatus.ACTIVE,
        )
        return replace(
            self.context,
            actor=actor,
            user_id=user_id,
            project_id=project_id,
            environment=environment,
        )

    def test_request_creates_pending_request_without_changing_grant(self):
        request = self.request_renewal()
        self.assertEqual(request.status, RenewalStatus.PENDING)
        self.assertEqual(
            self.renewal_repository.get(request.renewal_id),
            request,
        )
        self.assertEqual(
            self.grant_repository.get(self.grant.grant_id).expires_at,
            self.grant.expires_at,
        )

    def test_request_requires_active_agent_who_is_the_grant_subject(self):
        invalid_subjects = (
            Identity(
                identity_id="agent-001",
                kind=IdentityKind.USER,
                status=IdentityStatus.ACTIVE,
            ),
            Identity(
                identity_id="agent-001",
                kind=IdentityKind.AGENT,
                status=IdentityStatus.SUSPENDED,
            ),
            Identity(
                identity_id="other-agent",
                kind=IdentityKind.AGENT,
                status=IdentityStatus.ACTIVE,
            ),
        )
        for actor in invalid_subjects:
            with self.subTest(actor=actor):
                with self.assertRaises(AuthorizationError):
                    self.service.request_renewal(
                        replace(self.context, actor=actor),
                        "renewal-001",
                        self.grant.grant_id,
                        self.proposed_expires_at,
                        NOW,
                    )

    def test_request_rejects_missing_delegation(self):
        context = replace(self.context, delegation=None)
        with self.assertRaises(AuthorizationError):
            self.service.request_renewal(
                context,
                "renewal-001",
                self.grant.grant_id,
                self.proposed_expires_at,
                NOW,
            )

    def test_request_rejects_independent_delegation(self):
        context = replace(
            self.context,
            delegation=DelegationMode.INDEPENDENT,
        )
        with self.assertRaises(AuthorizationError):
            self.service.request_renewal(
                context,
                "renewal-001",
                self.grant.grant_id,
                self.proposed_expires_at,
                NOW,
            )

    def test_request_requires_owner_context_and_exact_scope(self):
        invalid_contexts = (
            replace(self.context, user_id="user-002"),
            replace(self.context, project_id="other-project"),
            replace(self.context, environment="production"),
        )
        for context in invalid_contexts:
            with self.subTest(context=context):
                with self.assertRaises(AuthorizationError):
                    self.service.request_renewal(
                        context,
                        "renewal-001",
                        self.grant.grant_id,
                        self.proposed_expires_at,
                        NOW,
                    )

    def test_request_requires_active_grant_later_expiry_and_unique_id(self):
        with self.assertRaises(ContractError):
            self.service.request_renewal(
                self.context,
                "renewal-001",
                self.grant.grant_id,
                self.grant.expires_at,
                NOW,
            )

        expired_grant = replace(self.grant, expires_at=NOW)
        self.grant_repository.update(expired_grant)
        with self.assertRaises(AuthorizationError):
            self.request_renewal()

        revoked_grant = replace(
            self.grant,
            revoked_at=NOW - timedelta(seconds=1),
        )
        self.grant_repository.update(revoked_grant)
        with self.assertRaises(AuthorizationError):
            self.request_renewal()

        self.grant_repository.update(self.grant)
        self.request_renewal()
        with self.assertRaises(ContractError):
            self.request_renewal()

    def test_approval_updates_grant_and_records_owner_decision(self):
        request = self.request_renewal()
        approval_time = NOW + timedelta(hours=1)
        updated_grant = self.service.approve_renewal(
            self.owner_context(),
            request.renewal_id,
            approval_time,
        )
        updated_request = self.renewal_repository.get(request.renewal_id)
        self.assertEqual(updated_grant.expires_at, self.proposed_expires_at)
        self.assertEqual(
            self.grant_repository.get(self.grant.grant_id),
            updated_grant,
        )
        self.assertEqual(updated_request.status, RenewalStatus.APPROVED)
        self.assertEqual(updated_request.decided_at, approval_time)
        self.assertEqual(updated_request.decided_by_user_id, "user-001")

    def test_approval_requires_owner_and_exact_scope(self):
        request = self.request_renewal()
        invalid_contexts = (
            self.owner_context(user_id="user-002"),
            self.owner_context(project_id="other-project"),
            self.owner_context(environment="production"),
        )
        for context in invalid_contexts:
            with self.subTest(context=context):
                with self.assertRaises(AuthorizationError):
                    self.service.approve_renewal(
                        context,
                        request.renewal_id,
                        NOW + timedelta(hours=1),
                    )

    def test_approval_rejects_changed_or_expired_grant(self):
        request = self.request_renewal()
        changed_grant = replace(
            self.grant,
            expires_at=self.grant.expires_at + timedelta(days=1),
        )
        self.grant_repository.update(changed_grant)
        with self.assertRaises(ContractError):
            self.service.approve_renewal(
                self.owner_context(),
                request.renewal_id,
                NOW + timedelta(hours=1),
            )

        self.grant_repository.update(self.grant)
        with self.assertRaises(AuthorizationError):
            self.service.approve_renewal(
                self.owner_context(),
                request.renewal_id,
                self.grant.expires_at,
            )

    def test_rejection_records_decision_without_changing_grant(self):
        request = self.request_renewal()
        decision_time = NOW + timedelta(hours=1)
        rejected_request = self.service.reject_renewal(
            self.owner_context(),
            request.renewal_id,
            decision_time,
        )
        self.assertEqual(rejected_request.status, RenewalStatus.REJECTED)
        self.assertEqual(rejected_request.decided_at, decision_time)
        self.assertEqual(rejected_request.decided_by_user_id, "user-001")
        self.assertEqual(
            self.grant_repository.get(self.grant.grant_id),
            self.grant,
        )

    def test_rejection_requires_owner_and_exact_scope(self):
        request = self.request_renewal()
        invalid_contexts = (
            self.owner_context(user_id="user-002"),
            self.owner_context(project_id="other-project"),
            self.owner_context(environment="production"),
        )
        for context in invalid_contexts:
            with self.subTest(context=context):
                with self.assertRaises(AuthorizationError):
                    self.service.reject_renewal(
                        context,
                        request.renewal_id,
                        NOW + timedelta(hours=1),
                    )

    def test_decisions_are_single_use_and_unknown_request_is_not_found(self):
        request = self.request_renewal()
        owner_context = self.owner_context()
        self.service.approve_renewal(
            owner_context,
            request.renewal_id,
            NOW + timedelta(hours=1),
        )
        with self.assertRaises(ContractError):
            self.service.approve_renewal(
                owner_context,
                request.renewal_id,
                NOW + timedelta(hours=2),
            )
        with self.assertRaises(ContractError):
            self.service.reject_renewal(
                owner_context,
                request.renewal_id,
                NOW + timedelta(hours=2),
            )
        with self.assertRaises(NotFoundError):
            self.service.reject_renewal(
                owner_context,
                "missing-renewal",
                NOW + timedelta(hours=1),
            )

    def test_approval_failure_rolls_back_grant_and_request(self):
        request = GrantRenewalRequest(
            renewal_id="renewal-atomic",
            grant_id=self.grant.grant_id,
            owner_user_id=self.grant.owner_user_id,
            subject_identity_id=self.grant.subject_identity_id,
            requested_by_identity_id=self.grant.subject_identity_id,
            current_expires_at=self.grant.expires_at,
            proposed_expires_at=self.proposed_expires_at,
            requested_at=NOW,
        )
        self.renewal_repository.create(request)
        self.renewal_repository.fail_on_update = True

        with self.assertRaises(RuntimeError):
            self.service.approve_renewal(
                self.owner_context(),
                request.renewal_id,
                NOW + timedelta(hours=1),
            )

        stored_grant = self.grant_repository.get(self.grant.grant_id)
        stored_request = self.renewal_repository.get(request.renewal_id)
        self.assertEqual(stored_grant, self.grant)
        self.assertEqual(stored_request.status, RenewalStatus.PENDING)

    def test_approval_concurrency_conflict_rolls_back_grant(self):
        request = self.request_renewal()
        concurrent_request = replace(
            request,
            status=RenewalStatus.REJECTED,
            decided_at=NOW + timedelta(minutes=30),
            decided_by_user_id="user-001",
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
                self.service.approve_renewal(
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
        request = self.request_renewal()
        concurrent_request = replace(
            request,
            status=RenewalStatus.APPROVED,
            decided_at=NOW + timedelta(minutes=30),
            decided_by_user_id="user-001",
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
                self.service.reject_renewal(
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
