from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest

from atlas.authorization.models import (
    Grant,
    GrantRenewalRequest,
    GrantResourceScope,
    RenewalStatus,
)
from atlas.authorization.renewal_service import GrantRenewalService
from atlas.core.agent_delegation import (
    AgentDelegation,
    AgentDelegationScope,
    AgentDelegationStatus,
)
from atlas.core.agent_identity import CanonicalAgentIdentity
from atlas.core.context import OperationContext
from atlas.core.errors import AuthorizationError
from atlas.core.identity import Identity, IdentityKind, IdentityStatus
from atlas.core.user_identity import CanonicalUserIdentity
from atlas.workspace.models import ProjectEnvironmentStatus
from tests.fakes.authorization_unit_of_work import (
    InMemoryAuthorizationUnitOfWorkFactory,
    InMemoryGrantRepository,
    InMemoryRenewalRepository,
)
from tests.fixtures.verified_identity import (
    OWNER_IDENTITY_ID,
    OWNER_USER_ID,
    VERIFIED_OWNER,
    FakeVerifiedIdentityContextVerifier,
)


NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
AGENT_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
ISSUER_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
DELEGATION_ID = "22222222-2222-4222-8222-222222222222"
RENEWAL_ID = "renewal-agent-approval"
ACTION = "grant.renewal.request"


class FakeClock:
    def now(self):
        return NOW


class AgentRenewalApprovalLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.agent_identity = Identity(
            identity_id=AGENT_ID,
            kind=IdentityKind.AGENT,
            status=IdentityStatus.ACTIVE,
            revision=3,
        )
        self.canonical_agent = CanonicalAgentIdentity(self.agent_identity)
        self.owner_identity = Identity(
            identity_id=OWNER_IDENTITY_ID,
            kind=IdentityKind.USER,
            status=IdentityStatus.ACTIVE,
            revision=1,
        )
        self.canonical_owner = CanonicalUserIdentity(
            user_id=OWNER_USER_ID,
            identity=self.owner_identity,
        )
        self.resource_ids = frozenset({"workspace-a", "workspace-b"})
        self.grant = Grant(
            grant_id="grant-agent-approval",
            owner_user_id=OWNER_USER_ID,
            subject_identity_id=AGENT_ID,
            project_id="atlas",
            environment="development",
            resource_scope=GrantResourceScope("workspace", self.resource_ids),
            actions=frozenset({ACTION, "read"}),
            issued_at=NOW - timedelta(days=1),
            expires_at=NOW + timedelta(days=3),
            revision=7,
        )
        self.delegation = AgentDelegation(
            delegation_id=DELEGATION_ID,
            owner_user_id=OWNER_USER_ID,
            owner_identity_id=OWNER_IDENTITY_ID,
            agent_identity_id=AGENT_ID,
            grant_id=self.grant.grant_id,
            grant_revision=self.grant.revision,
            project_id=self.grant.project_id,
            environment=self.grant.environment,
            scope=AgentDelegationScope(
                "workspace", self.resource_ids, frozenset({ACTION})
            ),
            issuer_id=ISSUER_ID,
            issued_at=NOW - timedelta(hours=2),
            not_before=NOW - timedelta(hours=1),
            expires_at=NOW + timedelta(days=1),
            created_by_user_identity_id=OWNER_IDENTITY_ID,
            status=AgentDelegationStatus.ACTIVE,
            revision=4,
        )
        self.request = GrantRenewalRequest(
            renewal_id=RENEWAL_ID,
            grant_id=self.grant.grant_id,
            owner_user_id=OWNER_USER_ID,
            subject_identity_id=AGENT_ID,
            requested_by_identity_id=AGENT_ID,
            current_expires_at=self.grant.expires_at,
            proposed_expires_at=self.grant.expires_at + timedelta(days=7),
            requested_at=NOW - timedelta(minutes=10),
            grant_revision=self.grant.revision,
            delegation_id=DELEGATION_ID,
            delegation_revision=self.delegation.revision,
        )
        self.grants = InMemoryGrantRepository()
        self.grants.create(self.grant)
        self.renewals = InMemoryRenewalRepository()
        self.renewals.create(self.request)
        self.delegation_state = {"value": self.delegation}
        self.association_state = {
            "value": SimpleNamespace(
                project_id="atlas",
                environment_id="development",
                status=ProjectEnvironmentStatus.ACTIVE,
                revision=1,
            )
        }
        self.binding_active = {"value": True}
        base_factory = InMemoryAuthorizationUnitOfWorkFactory(
            self.grants, self.renewals
        )

        def factory():
            unit = base_factory()
            unit.agent_delegations = SimpleNamespace(
                get=lambda delegation_id: (
                    self.delegation_state["value"]
                    if delegation_id == DELEGATION_ID else None
                )
            )
            unit.identity = SimpleNamespace(
                get_user_by_identity_id=lambda identity_id: (
                    self.canonical_owner
                    if identity_id == OWNER_IDENTITY_ID else None
                )
            )
            unit.agent_identity = SimpleNamespace(
                get_agent_by_identity_id=lambda identity_id: (
                    self.canonical_agent if identity_id == AGENT_ID else None
                )
            )
            unit.native_agent_identity = SimpleNamespace(
                has_active_native_agent_binding=lambda identity_id, issuer_id: (
                    self.binding_active["value"]
                    and identity_id == AGENT_ID
                    and issuer_id == ISSUER_ID
                )
            )
            unit.project_environments = SimpleNamespace(
                get_project=lambda project_id: (
                    SimpleNamespace(project_id=project_id, status="active")
                    if project_id == "atlas" else None
                ),
                get_environment=lambda environment_id: (
                    SimpleNamespace(environment_id=environment_id, status="active")
                    if environment_id == "development" else None
                ),
            )
            unit.workspaces = SimpleNamespace(
                get_association=lambda project_id, environment_id: (
                    self.association_state["value"]
                    if (project_id, environment_id) == ("atlas", "development")
                    else None
                )
            )
            return unit

        self.service = GrantRenewalService(
            factory,
            identity_verifier=FakeVerifiedIdentityContextVerifier(),
            clock=FakeClock(),
        )
        self.owner_context = OperationContext(
            request_id="owner-approval-request",
            correlation_id="owner-approval-correlation",
            actor=self.owner_identity,
            user_id=OWNER_USER_ID,
            origin="owner",
            delegation=None,
            project_id="atlas",
            environment="development",
            purpose="approve AGENT renewal",
            classification="internal",
            created_at=NOW,
        )

    def approve(self):
        return self.service.approve_renewal(
            self.owner_context,
            RENEWAL_ID,
            NOW - timedelta(days=30),  # untrusted legacy argument
            verified_identity=VERIFIED_OWNER,
        )

    def assert_denied_without_mutation(self):
        with self.assertRaises(AuthorizationError):
            self.approve()
        self.assertEqual(self.grants.get(self.grant.grant_id), self.grant)
        self.assertEqual(
            self.renewals.get(RENEWAL_ID).status, RenewalStatus.PENDING
        )

    def test_active_association_and_delegation_allow_owner_approval(self):
        updated = self.approve()
        self.assertEqual(
            updated.expires_at, self.request.proposed_expires_at
        )
        self.assertEqual(updated.revision, self.grant.revision + 1)
        stored = self.renewals.get(RENEWAL_ID)
        self.assertIs(stored.status, RenewalStatus.APPROVED)
        self.assertEqual(stored.decided_at, NOW)

    def test_suspended_association_blocks_pending_agent_approval(self):
        self.association_state["value"] = replace(
            self.association_state["value"],
            status=ProjectEnvironmentStatus.SUSPENDED,
            revision=2,
        )
        self.assert_denied_without_mutation()

    def test_revoked_delegation_blocks_pending_agent_approval(self):
        self.delegation_state["value"] = replace(
            self.delegation,
            status=AgentDelegationStatus.REVOKED,
            revision=5,
            revoked_at=NOW - timedelta(minutes=1),
            revoked_by_user_id=OWNER_USER_ID,
        )
        self.assert_denied_without_mutation()

    def test_changed_delegation_revision_blocks_pending_agent_approval(self):
        self.delegation_state["value"] = replace(
            self.delegation, revision=5
        )
        self.assert_denied_without_mutation()

    def test_inactive_native_binding_blocks_pending_agent_approval(self):
        self.binding_active["value"] = False
        self.assert_denied_without_mutation()

    def test_owner_can_reject_pending_request_after_association_suspension_and_revocation(self):
        self.association_state["value"] = replace(
            self.association_state["value"],
            status=ProjectEnvironmentStatus.SUSPENDED,
            revision=2,
        )
        self.delegation_state["value"] = replace(
            self.delegation,
            status=AgentDelegationStatus.REVOKED,
            revision=5,
            revoked_at=NOW - timedelta(minutes=1),
            revoked_by_user_id=OWNER_USER_ID,
        )
        rejected = self.service.reject_renewal(
            self.owner_context,
            RENEWAL_ID,
            NOW,
            verified_identity=VERIFIED_OWNER,
        )
        self.assertIs(rejected.status, RenewalStatus.REJECTED)
        self.assertEqual(self.grants.get(self.grant.grant_id), self.grant)

    def test_agent_approval_fails_closed_without_trusted_clock(self):
        self.service._clock = None
        self.assert_denied_without_mutation()

    def test_partial_or_changed_delegation_scope_blocks_pending_agent_approval(self):
        narrowed = replace(
            self.delegation.scope,
            resource_ids=frozenset({"workspace-a"}),
        )
        self.delegation_state["value"] = replace(
            self.delegation, scope=narrowed
        )
        self.assert_denied_without_mutation()


if __name__ == "__main__":
    unittest.main()
