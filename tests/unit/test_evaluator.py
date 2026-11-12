from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest

from atlas.authorization.evaluator import AuthorizationEvaluator
from atlas.authorization.models import (
    AuthorizationDecision,
    AuthorizationRequest,
    Grant,
)
from atlas.core.context import OperationContext
from atlas.core.errors import ContractError
from atlas.core.identity import Identity, IdentityKind, IdentityStatus


NOW = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)


class AuthorizationEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.actor = Identity(
            identity_id="agent-001",
            kind=IdentityKind.AGENT,
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
            purpose="test authorization",
            classification="internal",
            created_at=NOW,
        )
        self.request = AuthorizationRequest(
            context=self.context,
            action="read",
            resource_type="files",
            resource_id="file-001",
            resource_owner_id="user-001",
        )
        self.grant = Grant(
            grant_id="grant-001",
            owner_user_id="user-001",
            subject_identity_id="agent-001",
            project_id="atlas",
            environment="development",
            resource_type="files",
            actions=frozenset({"read"}),
            issued_at=NOW - timedelta(days=1),
            expires_at=NOW + timedelta(days=1),
        )
        self.evaluator = AuthorizationEvaluator()

    def evaluate(self, request=None, grants=None, now=NOW):
        return self.evaluator.evaluate(
            self.request if request is None else request,
            [self.grant] if grants is None else grants,
            now,
        )

    def test_matching_grant_allows_resource_type_not_specific_id(self):
        request = replace(self.request, resource_id="another-file")
        result = self.evaluate(request=request)
        self.assertIs(result.decision, AuthorizationDecision.ALLOW)

    def test_missing_or_mismatched_grant_is_denied(self):
        self.assertIs(
            self.evaluate(grants=[]).decision,
            AuthorizationDecision.DENY,
        )

        mismatches = (
            {"subject_identity_id": "other-agent"},
            {"owner_user_id": "other-user"},
            {"project_id": "other-project"},
            {"environment": "production"},
            {"resource_type": "documents"},
            {"actions": frozenset({"write"})},
        )
        for changes in mismatches:
            with self.subTest(changes=changes):
                grant = replace(self.grant, **changes)
                self.assertIs(
                    self.evaluate(grants=[grant]).decision,
                    AuthorizationDecision.DENY,
                )

    def test_resource_owner_must_match_context_owner(self):
        request = replace(self.request, resource_owner_id="other-user")
        self.assertIs(
            self.evaluate(request=request).decision,
            AuthorizationDecision.DENY,
        )

    def test_inactive_actor_is_denied(self):
        inactive_actor = replace(
            self.actor,
            status=IdentityStatus.SUSPENDED,
        )
        context = replace(self.context, actor=inactive_actor)
        request = replace(self.request, context=context)
        self.assertIs(
            self.evaluate(request=request).decision,
            AuthorizationDecision.DENY,
        )

    def test_grant_issue_time_is_inclusive_and_expiration_is_exclusive(self):
        issued_now = replace(self.grant, issued_at=NOW)
        self.assertIs(
            self.evaluate(grants=[issued_now]).decision,
            AuthorizationDecision.ALLOW,
        )

        expires_now = replace(self.grant, expires_at=NOW)
        self.assertIs(
            self.evaluate(grants=[expires_now]).decision,
            AuthorizationDecision.DENY,
        )

    def test_revoked_grant_is_denied_at_and_after_revocation(self):
        revoked_now = replace(self.grant, revoked_at=NOW)
        self.assertIs(
            self.evaluate(grants=[revoked_now]).decision,
            AuthorizationDecision.DENY,
        )

        revoked_later = replace(
            self.grant,
            revoked_at=NOW + timedelta(seconds=1),
        )
        self.assertIs(
            self.evaluate(grants=[revoked_later]).decision,
            AuthorizationDecision.ALLOW,
        )

    def test_request_must_have_expected_type(self):
        with self.assertRaises(ContractError):
            self.evaluate(request="request")

    def test_grants_must_contain_only_grant_instances(self):
        with self.assertRaises(ContractError):
            self.evaluate(grants=[object()])

    def test_now_must_be_utc_aware_datetime(self):
        invalid_times = (
            datetime(2026, 11, 12, 12, 0),
            datetime(
                2026,
                11,
                12,
                12,
                0,
                tzinfo=timezone(timedelta(hours=1)),
            ),
        )
        for now in invalid_times:
            with self.subTest(now=now):
                with self.assertRaises(ContractError):
                    self.evaluate(now=now)


if __name__ == "__main__":
    unittest.main()
