import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from atlas.authorization.grant_management import GrantManagementService
from atlas.authorization.models import Grant
from atlas.core.context import OperationContext
from atlas.core.errors import (
    AuthorizationError,
    ContractError,
    NotFoundError,
)
from atlas.core.identity import Identity, IdentityKind, IdentityStatus


NOW = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)


class InMemoryGrantRepository:
    """Repositorio temporal utilizado exclusivamente en pruebas."""

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
            grant
            for grant in self.grants.values()
            if grant.owner_user_id == owner_user_id
        )


class GrantManagementTests(unittest.TestCase):
    def setUp(self):
        self.actor = Identity(
            identity_id="user-001",
            kind=IdentityKind.USER,
            status=IdentityStatus.ACTIVE,
        )
        self.context = OperationContext(
            request_id="request-001",
            correlation_id="correlation-001",
            actor=self.actor,
            user_id="user-001",
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
            owner_user_id="user-001",
            subject_identity_id="agent-001",
            project_id="atlas",
            environment="development",
            resource_type="files",
            actions=frozenset({"read"}),
            issued_at=NOW,
            expires_at=NOW + timedelta(days=7),
        )
        self.repository = InMemoryGrantRepository()
        self.service = GrantManagementService(self.repository)

    def test_issue_stores_and_returns_grant(self):
        result = self.service.issue(self.context, self.grant, NOW)
        self.assertEqual(result, self.grant)
        self.assertEqual(self.repository.get(self.grant.grant_id), self.grant)
        self.assertEqual(
            self.repository.list_by_owner("user-001"),
            (self.grant,),
        )

    def test_issue_requires_active_user_matching_context_user(self):
        invalid_actors = (
            Identity(
                identity_id="user-001",
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
                    self.service.issue(
                        replace(self.context, actor=actor),
                        self.grant,
                        NOW,
                    )

    def test_issue_cannot_grant_for_another_owner(self):
        grant = replace(self.grant, owner_user_id="user-002")
        with self.assertRaises(AuthorizationError):
            self.service.issue(self.context, grant, NOW)

    def test_issue_requires_matching_project_and_environment(self):
        mismatches = (
            replace(self.grant, project_id="other-project"),
            replace(self.grant, environment="production"),
        )
        for grant in mismatches:
            with self.subTest(grant=grant):
                with self.assertRaises(AuthorizationError):
                    self.service.issue(self.context, grant, NOW)

    def test_duplicate_grant_id_is_rejected(self):
        self.service.issue(self.context, self.grant, NOW)
        with self.assertRaises(ContractError):
            self.service.issue(self.context, self.grant, NOW)

    def test_issue_requires_utc_now_matching_issued_at(self):
        with self.assertRaises(ContractError):
            self.service.issue(
                self.context,
                self.grant,
                datetime(2026, 11, 12, 15, 0),
            )
        with self.assertRaises(ContractError):
            self.service.issue(
                self.context,
                self.grant,
                NOW + timedelta(seconds=1),
            )

    def test_revoke_sets_timestamp_without_deleting_grant(self):
        self.service.issue(self.context, self.grant, NOW)
        revoked_at = NOW + timedelta(hours=1)
        revoked_grant = self.service.revoke(
            self.context,
            self.grant.grant_id,
            revoked_at,
        )
        self.assertEqual(revoked_grant.revoked_at, revoked_at)
        self.assertEqual(
            self.repository.get(self.grant.grant_id),
            revoked_grant,
        )
        self.assertEqual(
            self.repository.list_by_owner("user-001"),
            (revoked_grant,),
        )

    def test_revoke_rejects_another_owner(self):
        self.service.issue(self.context, self.grant, NOW)
        another_owner = Identity(
            identity_id="user-002",
            kind=IdentityKind.USER,
            status=IdentityStatus.ACTIVE,
        )
        other_context = replace(
            self.context,
            actor=another_owner,
            user_id="user-002",
        )
        with self.assertRaises(AuthorizationError):
            self.service.revoke(
                other_context,
                self.grant.grant_id,
                NOW + timedelta(hours=1),
            )

    def test_revoke_is_idempotent_and_missing_grant_is_not_found(self):
        self.service.issue(self.context, self.grant, NOW)
        first_revocation = NOW + timedelta(hours=1)
        first_result = self.service.revoke(
            self.context,
            self.grant.grant_id,
            first_revocation,
        )
        second_result = self.service.revoke(
            self.context,
            self.grant.grant_id,
            NOW + timedelta(hours=2),
        )
        self.assertEqual(second_result.revoked_at, first_revocation)
        self.assertEqual(second_result, first_result)
        self.assertEqual(self.repository.update_calls, 1)

        with self.assertRaises(NotFoundError):
            self.service.revoke(
                self.context,
                "missing-grant",
                NOW + timedelta(hours=2),
            )


if __name__ == "__main__":
    unittest.main()
