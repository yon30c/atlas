from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest

from atlas.authorization.models import (
    Grant,
    GrantResourceScope,
    GrantRenewalRequest,
    RenewalStatus,
)
from atlas.authorization.renewal_service import GrantRenewalService
from atlas.core.agent_delegation import (
    AgentDelegation,
    AgentDelegationScope,
    AgentDelegationStatus,
    VerifiedAgentDelegationContext,
)
from atlas.core.context import OperationContext
from atlas.core.enums import DelegationMode
from atlas.core.errors import AuthorizationError, ContractError
from atlas.core.identity import Identity, IdentityKind, IdentityStatus
from atlas.core.agent_identity import CanonicalAgentIdentity
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
ACTION = "grant.renewal.request"


class FakeClock:
    def now(self):
        return NOW


class FakeVerifier:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def verify_in_unit_of_work(self, evidence, unit):
        self.calls += 1
        self.assert_unit = unit
        return self.result


class FakeProjectEnvironment:
    def get_project(self, project_id):
        return SimpleNamespace(project_id=project_id, status="active", revision=1)

    def get_environment(self, environment_id):
        return SimpleNamespace(environment_id=environment_id, status="active", revision=1)


class FakeRenewals:
    def __init__(self):
        self.items = {}

    def get(self, renewal_id):
        return self.items.get(renewal_id)

    def list_by_grant(self, grant_id):
        return tuple(item for item in self.items.values() if item.grant_id == grant_id)

    def create(self, request):
        if request.renewal_id in self.items:
            raise ContractError("duplicate renewal")
        self.items[request.renewal_id] = request


class FakeUnit:
    def __init__(self, grant, renewals):
        self.grants = SimpleNamespace(get=lambda grant_id: grant if grant_id == grant.grant_id else None)
        self.renewals = renewals
        self.agent_identity = object()
        self.agent_delegations = object()
        self.native_agent_identity = object()
        self.native_identity = object()
        self.identity = object()
        self.project_environments = FakeProjectEnvironment()
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def commit(self):
        self.committed = True


class AgentRenewalServiceTests(unittest.TestCase):
    def setUp(self):
        self.agent = Identity(
            AGENT_ID, IdentityKind.AGENT, IdentityStatus.ACTIVE, revision=3
        )
        self.canonical_agent = CanonicalAgentIdentity(self.agent)
        self.agent_evidence = VerifiedAgentIdentityContext(
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
            "workspace",
            frozenset({"workspace-a", "workspace-b"}),
            frozenset({ACTION}),
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
            actions=frozenset({ACTION, "read"}),
            issued_at=NOW - timedelta(days=1),
            expires_at=NOW + timedelta(days=3),
            revision=7,
        )
        self.delegation = AgentDelegation(
            delegation_id=DELEGATION_ID,
            owner_user_id=OWNER_ID,
            owner_identity_id=OWNER_IDENTITY_ID,
            agent_identity_id=AGENT_ID,
            grant_id=self.grant.grant_id,
            grant_revision=self.grant.revision,
            project_id=self.grant.project_id,
            environment=self.grant.environment,
            scope=self.scope,
            issuer_id=ISSUER_ID,
            issued_at=NOW - timedelta(minutes=5),
            not_before=NOW - timedelta(minutes=4),
            expires_at=NOW + timedelta(days=1),
            created_by_user_identity_id=OWNER_IDENTITY_ID,
            status=AgentDelegationStatus.ACTIVE,
            revision=4,
        )
        self.delegation_evidence = VerifiedAgentDelegationContext(
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
            actor=self.agent,
            user_id=OWNER_ID,
            origin="agent",
            delegation=DelegationMode.DELEGATED,
            project_id="atlas",
            environment="development",
            purpose="request Grant renewal",
            classification="internal",
            created_at=NOW,
        )
        self.renewals = FakeRenewals()
        self.units = []

        def factory():
            unit = FakeUnit(self.grant, self.renewals)
            self.units.append(unit)
            return unit

        self.agent_verifier = FakeVerifier(self.canonical_agent)
        self.delegation_verifier = FakeVerifier(self.delegation)
        self.service = GrantRenewalService(
            factory,
            agent_identity_verifier=self.agent_verifier,
            delegation_context_verifier=self.delegation_verifier,
            clock=FakeClock(),
        )

    def request(self, renewal_id="renewal-001", **kwargs):
        args = {
            "context": self.context,
            "renewal_id": renewal_id,
            "grant_id": self.grant.grant_id,
            "proposed_expires_at": self.grant.expires_at + timedelta(days=7),
            "now": NOW - timedelta(days=365),  # untrusted compatibility argument
            "verified_agent_identity": self.agent_evidence,
            "verified_delegation": self.delegation_evidence,
            "expected_delegation_revision": 4,
        }
        args.update(kwargs)
        return self.service.request_renewal(**args)

    def test_valid_request_persists_exact_authority_revisions(self):
        request = self.request()
        self.assertEqual(request.grant_revision, 7)
        self.assertEqual(request.delegation_id, DELEGATION_ID)
        self.assertEqual(request.delegation_revision, 4)
        self.assertEqual(request.requested_by_identity_id, AGENT_ID)
        self.assertEqual(request.requested_at, NOW)
        self.assertIs(request.status, RenewalStatus.PENDING)
        self.assertTrue(self.units[-1].committed)

    def test_missing_evidence_remains_fail_closed(self):
        with self.assertRaises(AuthorizationError):
            self.request(verified_agent_identity=None, verified_delegation=None)

    def test_partial_delegation_is_denied_without_write(self):
        partial_scope = replace(self.scope, resource_ids=frozenset({"workspace-a"}))
        partial_evidence = replace(self.delegation_evidence, scope=partial_scope)
        with self.assertRaises(AuthorizationError):
            self.request(verified_delegation=partial_evidence)
        self.assertEqual(self.renewals.items, {})
        self.assertFalse(self.units[-1].committed)

    def test_stale_delegation_revision_is_denied_without_write(self):
        with self.assertRaises(AuthorizationError):
            self.request(expected_delegation_revision=3)
        self.assertEqual(self.renewals.items, {})
        self.assertFalse(self.units[-1].committed)

    def test_project_must_be_active(self):
        class InactiveProjects(FakeProjectEnvironment):
            def get_project(self, project_id):
                return SimpleNamespace(project_id=project_id, status="suspended", revision=2)

        original = FakeUnit
        def factory():
            unit = original(self.grant, self.renewals)
            unit.project_environments = InactiveProjects()
            self.units.append(unit)
            return unit
        self.service._unit_of_work_factory = factory
        with self.assertRaises(AuthorizationError):
            self.request()
        self.assertEqual(self.renewals.items, {})
        self.assertFalse(self.units[-1].committed)

    def test_same_id_and_same_intent_is_idempotent(self):
        first = self.request()
        second = self.request()
        self.assertEqual(first, second)
        self.assertEqual(len(self.renewals.items), 1)
        self.assertFalse(self.units[-1].committed)

    def test_different_pending_request_for_same_grant_is_denied(self):
        self.request()
        with self.assertRaises(AuthorizationError):
            self.request("renewal-002")
        self.assertEqual(len(self.renewals.items), 1)
        self.assertFalse(self.units[-1].committed)

    def test_reused_renewal_id_with_different_intent_is_denied(self):
        self.request()
        with self.assertRaises(ContractError):
            self.request(
                proposed_expires_at=self.grant.expires_at + timedelta(days=30)
            )
        self.assertEqual(len(self.renewals.items), 1)


if __name__ == "__main__":
    unittest.main()
