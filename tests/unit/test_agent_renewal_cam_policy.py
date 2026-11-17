from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest

from atlas.authorization.agent_renewal_policy import (
    GRANT_RENEWAL_REQUEST_ACTION,
    require_agent_renewal_cam_allow,
)
from atlas.authorization.evaluator import AuthorizationEvaluator
from atlas.authorization.models import Grant, GrantResourceScope
from atlas.core.agent_delegation import (
    AgentDelegationScope,
    VerifiedAgentDelegationContext,
)
from atlas.core.context import OperationContext
from atlas.core.enums import DelegationMode
from atlas.core.errors import AuthorizationError
from atlas.core.identity import Identity, IdentityKind, IdentityStatus
from atlas.core.verified_agent_identity_context import VerifiedAgentIdentityContext


NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
OWNER_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OWNER_IDENTITY_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
AGENT_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
ISSUER_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
AGENT_CONTEXT_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
BINDING_ID = "ffffffff-ffff-4fff-8fff-ffffffffffff"
DELEGATION_CONTEXT_ID = "11111111-1111-4111-8111-111111111111"
DELEGATION_ID = "22222222-2222-4222-8222-222222222222"
TOKEN = "A" * 43


class AgentRenewalCamPolicyTests(unittest.TestCase):
    def setUp(self):
        self.agent_identity = VerifiedAgentIdentityContext(
            context_id=AGENT_CONTEXT_ID,
            identity_id=AGENT_ID,
            identity_type=IdentityKind.AGENT,
            identity_revision=3,
            binding_id=BINDING_ID,
            binding_revision=2,
            issuer_id=ISSUER_ID,
            realm="atlas",
            audience="atlas.renewal",
            authenticated_at=NOW - timedelta(seconds=2),
            verified_at=NOW - timedelta(seconds=1),
            expires_at=NOW + timedelta(seconds=30),
            verification_ref=TOKEN,
            attestation=TOKEN,
        )
        self.scope = AgentDelegationScope(
            resource_type="workspace",
            resource_ids=frozenset({"workspace-a", "workspace-b"}),
            actions=frozenset({GRANT_RENEWAL_REQUEST_ACTION}),
        )
        self.grant = Grant(
            grant_id="grant-001",
            owner_user_id=OWNER_ID,
            subject_identity_id=AGENT_ID,
            project_id="atlas",
            environment="development",
            resource_scope=GrantResourceScope(
                "workspace", frozenset({"workspace-a", "workspace-b"})
            ),
            actions=frozenset({GRANT_RENEWAL_REQUEST_ACTION, "read"}),
            issued_at=NOW - timedelta(days=1),
            expires_at=NOW + timedelta(days=3),
            revision=7,
        )
        self.delegation = VerifiedAgentDelegationContext(
            context_id=DELEGATION_CONTEXT_ID,
            delegation_id=DELEGATION_ID,
            delegation_revision=4,
            owner_user_id=OWNER_ID,
            owner_identity_id=OWNER_IDENTITY_ID,
            agent_identity_id=AGENT_ID,
            agent_identity_revision=3,
            agent_context_id=AGENT_CONTEXT_ID,
            agent_binding_id=BINDING_ID,
            agent_binding_revision=2,
            grant_id=self.grant.grant_id,
            grant_revision=self.grant.revision,
            project_id=self.grant.project_id,
            environment=self.grant.environment,
            scope=self.scope,
            issuer_id=ISSUER_ID,
            realm="atlas",
            audience="atlas.renewal",
            verified_at=NOW - timedelta(seconds=1),
            expires_at=NOW + timedelta(seconds=20),
            verification_ref=TOKEN,
            attestation=TOKEN,
        )
        self.context = OperationContext(
            request_id="request-001",
            correlation_id="correlation-001",
            actor=Identity(
                identity_id=AGENT_ID,
                kind=IdentityKind.AGENT,
                status=IdentityStatus.ACTIVE,
                revision=3,
            ),
            user_id=OWNER_ID,
            origin="agent",
            delegation=DelegationMode.DELEGATED,
            project_id="atlas",
            environment="development",
            purpose="request Grant renewal",
            classification="internal",
            created_at=NOW,
        )
        self.evaluator = AuthorizationEvaluator()

    def allow(self, **changes):
        args = {
            "context": self.context,
            "verified_agent_identity": self.agent_identity,
            "verified_delegation": self.delegation,
            "grant": self.grant,
            "evaluator": self.evaluator,
            "now": NOW,
        }
        args.update(changes)
        return require_agent_renewal_cam_allow(**args)

    def test_exact_full_scope_and_explicit_action_are_allowed(self):
        self.assertIsNone(self.allow())

    def test_partial_resource_scope_is_denied(self):
        delegation = replace(
            self.delegation,
            scope=replace(
                self.scope, resource_ids=frozenset({"workspace-a"})
            ),
        )
        with self.assertRaises(AuthorizationError):
            self.allow(verified_delegation=delegation)

    def test_missing_action_in_grant_is_denied(self):
        grant = replace(self.grant, actions=frozenset({"read"}))
        with self.assertRaises(AuthorizationError):
            self.allow(grant=grant)

    def test_missing_action_in_delegation_is_denied(self):
        delegation = replace(
            self.delegation,
            scope=replace(self.scope, actions=frozenset({"read"})),
        )
        with self.assertRaises(AuthorizationError):
            self.allow(verified_delegation=delegation)

    def test_wrong_actor_kind_or_identity_is_denied(self):
        user_context = replace(
            self.context,
            actor=Identity(OWNER_IDENTITY_ID, IdentityKind.USER, IdentityStatus.ACTIVE),
            delegation=None,
        )
        with self.assertRaises(AuthorizationError):
            self.allow(context=user_context)
        wrong_agent = replace(
            self.context,
            actor=replace(self.context.actor, identity_id="other-agent"),
        )
        with self.assertRaises(AuthorizationError):
            self.allow(context=wrong_agent)

    def test_context_owner_project_and_environment_are_bound(self):
        for changes in (
            {"user_id": "other-owner"},
            {"project_id": "other-project"},
            {"environment": "production"},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(AuthorizationError):
                    self.allow(context=replace(self.context, **changes))

    def test_agent_binding_and_delegation_claims_are_exact(self):
        changed = replace(
            self.delegation,
            agent_binding_revision=self.delegation.agent_binding_revision + 1,
        )
        with self.assertRaises(AuthorizationError):
            self.allow(verified_delegation=changed)

    def test_grant_revision_and_subject_must_match_delegation(self):
        changed_grant = replace(self.grant, revision=self.grant.revision + 1)
        with self.assertRaises(AuthorizationError):
            self.allow(grant=changed_grant)

    def test_cam_denies_expired_or_revoked_grant(self):
        expired = replace(self.grant, expires_at=NOW)
        with self.assertRaises(AuthorizationError):
            self.allow(grant=expired)
        revoked = replace(self.grant, revoked_at=NOW)
        with self.assertRaises(AuthorizationError):
            self.allow(grant=revoked)

    def test_cam_evaluates_every_resource_in_the_exact_grant(self):
        class RecordingEvaluator(AuthorizationEvaluator):
            def __init__(self):
                self.resources = []

            def evaluate(self, request, grants, now):
                self.resources.append(request.resource_id)
                return super().evaluate(request, grants, now)

        evaluator = RecordingEvaluator()
        self.allow(evaluator=evaluator)
        self.assertEqual(evaluator.resources, ["workspace-a", "workspace-b"])


if __name__ == "__main__":
    unittest.main()
