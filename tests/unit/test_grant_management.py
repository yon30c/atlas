import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from atlas.authorization.grant_management import GrantManagementService
from atlas.authorization.models import Grant, GrantResourceScope
from atlas.core.context import OperationContext
from atlas.core.errors import AuthorizationError, ContractError
from atlas.core.identity import Identity, IdentityKind, IdentityStatus
from tests.fixtures.verified_identity import (
    OWNER_USER_ID, OWNER_IDENTITY_ID, VERIFIED_OWNER,
    FakeVerifiedIdentityContextVerifier,
)


NOW = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)


class InMemoryGrantRepository:
    def __init__(self):
        self.grants = {}

    def create(self, grant):
        self.grants[grant.grant_id] = grant

    def get(self, grant_id):
        return self.grants.get(grant_id)

    def update(self, grant):
        self.grants[grant.grant_id] = grant

    def list_by_owner(self, owner_user_id):
        return tuple(
            grant for grant in self.grants.values()
            if grant.owner_user_id == owner_user_id
        )


class InMemoryAuthorizationUnitOfWork:
    def __init__(self, grants):
        self.grants = grants
        self.renewals = object()
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def commit(self):
        self.committed = True

    def rollback(self):
        self.committed = False


class GrantManagementTests(unittest.TestCase):
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
        self.identity_verifier = FakeVerifiedIdentityContextVerifier()
        self.service = GrantManagementService(
            self.repository,
            unit_of_work_factory=lambda: InMemoryAuthorizationUnitOfWork(self.repository),
            identity_verifier=self.identity_verifier,
        )

    def issue(self, context=None, grant=None, *, service=None, verified_identity=VERIFIED_OWNER, now=NOW):
        target = service or self.service
        return target.issue(
            context or self.context,
            grant or self.grant,
            now,
            verified_identity=verified_identity,
        )

    def test_issue_fails_closed_without_verified_identity_evidence(self):
        with self.assertRaises(AuthorizationError):
            self.service.issue(self.context, self.grant, NOW)

    def test_issue_fails_closed_without_transactional_unit_of_work(self):
        service = GrantManagementService(
            self.repository, identity_verifier=self.identity_verifier
        )
        with self.assertRaisesRegex(ContractError, "unidad de trabajo transaccional"):
            self.issue(service=service)
        self.assertIsNone(self.repository.get(self.grant.grant_id))

    def test_issue_stores_and_returns_grant(self):
        result = self.issue(self.context, self.grant, NOW)
        self.assertEqual(result, self.grant)
        self.assertEqual(self.repository.get(self.grant.grant_id), self.grant)
        self.assertEqual(
            self.repository.list_by_owner(OWNER_USER_ID),
            (self.grant,),
        )

    def test_issue_requires_active_user_matching_context_user(self):
        invalid_actors = (
            Identity(
                identity_id=OWNER_IDENTITY_ID,
                kind=IdentityKind.AGENT,
                status=IdentityStatus.ACTIVE,
            ),
            Identity(
                identity_id="user-001",
                kind=IdentityKind.USER,
                status=IdentityStatus.SUSPENDED,
            ),
            Identity(
                identity_id="different-user",
                kind=IdentityKind.USER,
                status=IdentityStatus.ACTIVE,
            ),
        )
        for actor in invalid_actors:
            with self.subTest(actor=actor):
                with self.assertRaises(AuthorizationError):
                    self.issue(
                        replace(self.context, actor=actor),
                        self.grant,
                        NOW,
                    )

    def test_issue_cannot_grant_for_another_owner(self):
        grant = replace(self.grant, owner_user_id="f6b2b66f-7c72-4d77-8d84-7d0a8c5a1006")
        with self.assertRaises(AuthorizationError):
            self.issue(self.context, grant, NOW)

    def test_issue_requires_matching_project_and_environment(self):
        mismatches = (
            replace(self.grant, project_id="other-project"),
            replace(self.grant, environment="production"),
        )
        for grant in mismatches:
            with self.subTest(grant=grant):
                with self.assertRaises(AuthorizationError):
                    self.issue(self.context, grant, NOW)

    def test_duplicate_grant_id_is_rejected(self):
        self.issue(self.context, self.grant, NOW)
        with self.assertRaises(ContractError):
            self.issue(self.context, self.grant, NOW)

    def test_issue_requires_utc_now_matching_issued_at(self):
        with self.assertRaises(ContractError):
            self.issue(now=datetime(2026, 11, 12, 15, 0))
        with self.assertRaises(ContractError):
            self.issue(now=NOW + timedelta(seconds=1))

    def test_revoke_fails_closed_without_coordinator_and_cam_ports(self):
        self.issue(self.context, self.grant, NOW)
        with self.assertRaises(ContractError):
            self.service.revoke(
                self.context,
                self.grant.grant_id,
                "idem-001",
                NOW + timedelta(seconds=1),
            )


if __name__ == "__main__":
    unittest.main()
