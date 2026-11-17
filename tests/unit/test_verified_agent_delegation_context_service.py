"""Focused tests for trusted AGENT delegation evidence issuance and revalidation."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import inspect
import unittest
from uuid import uuid4

from atlas.adapters.hmac_verified_identity_context_attestor import HmacVerifiedIdentityContextAttestor
from atlas.authorization.models import Grant, GrantResourceScope
from atlas.authorization.verified_agent_delegation_context_service import (
    VerifiedAgentDelegationContextRejected,
    VerifiedAgentDelegationContextService,
)
from atlas.core.agent_delegation import (
    AgentDelegation,
    AgentDelegationScope,
    AgentDelegationStatus,
)
from atlas.core.agent_identity import CanonicalAgentIdentity
from atlas.core.identity import Identity, IdentityKind, IdentityStatus
from atlas.core.native_identity import NativeIssuerStatus
from atlas.core.user_identity import CanonicalUserIdentity
from atlas.core.verified_agent_identity_context import VerifiedAgentIdentityContext
from atlas.ports.agent_delegation_authority import AgentDelegationAuthorityPort


def uid():
    return str(uuid4())


class Clock:
    def __init__(self, now):
        self.value = now

    def now(self):
        return self.value


class Unit:
    def __init__(self, owner, agent, delegation, grant, issuer):
        self.identity = SimpleNamespace(get_user_by_identity_id=lambda identity_id: owner if identity_id == owner.identity.identity_id else None)
        self.agent_identity = SimpleNamespace(get_agent_by_identity_id=lambda identity_id: agent if identity_id == agent.identity.identity_id else None)
        self.native_agent_identity = SimpleNamespace(has_active_native_agent_binding=lambda identity_id, issuer_id: identity_id == agent.identity.identity_id and issuer_id == issuer.issuer_id)
        self.native_identity = SimpleNamespace(get_native_issuer=lambda issuer_id: issuer if issuer_id == issuer.issuer_id else None)
        self.agent_delegations = SimpleNamespace(get=lambda delegation_id: delegation if delegation_id == delegation.delegation_id else None)
        self.grants = SimpleNamespace(get=lambda grant_id: grant if grant_id == grant.grant_id else None)
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def commit(self):
        self.committed = True


class VerifiedAgentDelegationContextServiceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
        self.clock = Clock(self.now)
        self.owner = CanonicalUserIdentity(
            user_id=uid(),
            identity=Identity(uid(), IdentityKind.USER, IdentityStatus.ACTIVE, 2),
        )
        self.agent = CanonicalAgentIdentity(
            Identity(uid(), IdentityKind.AGENT, IdentityStatus.ACTIVE, 3)
        )
        self.issuer = SimpleNamespace(issuer_id=uid(), status=NativeIssuerStatus.ACTIVE)
        self.scope = AgentDelegationScope(
            "workspace", frozenset({"workspace-a", "workspace-b"}),
            frozenset({"workspace.read", "workspace.write"}),
        )
        self.grant = Grant(
            grant_id="grant-verified-agent",
            owner_user_id=self.owner.user_id,
            subject_identity_id=self.agent.identity.identity_id,
            project_id="atlas",
            environment="test",
            resource_scope=GrantResourceScope("workspace", frozenset({"workspace-a", "workspace-b", "workspace-c"})),
            actions=frozenset({"workspace.read", "workspace.write", "workspace.delete"}),
            issued_at=self.now - timedelta(minutes=5),
            expires_at=self.now + timedelta(days=1),
            revision=4,
        )
        self.delegation = AgentDelegation(
            delegation_id=uid(),
            owner_user_id=self.owner.user_id,
            owner_identity_id=self.owner.identity.identity_id,
            agent_identity_id=self.agent.identity.identity_id,
            grant_id=self.grant.grant_id,
            grant_revision=self.grant.revision,
            project_id=self.grant.project_id,
            environment=self.grant.environment,
            scope=self.scope,
            issuer_id=self.issuer.issuer_id,
            issued_at=self.now - timedelta(minutes=1),
            not_before=self.now - timedelta(seconds=1),
            expires_at=self.now + timedelta(hours=2),
            created_by_user_identity_id=self.owner.identity.identity_id,
        )
        self.unit = Unit(self.owner, self.agent, self.delegation, self.grant, self.issuer)
        self.agent_context = VerifiedAgentIdentityContext(
            context_id=uid(),
            identity_id=self.agent.identity.identity_id,
            identity_type=IdentityKind.AGENT,
            identity_revision=self.agent.identity.revision,
            binding_id=uid(),
            binding_revision=2,
            issuer_id=self.issuer.issuer_id,
            realm="atlas.agent",
            audience="atlas.agent.operations",
            authenticated_at=self.now - timedelta(seconds=2),
            verified_at=self.now,
            expires_at=self.now + timedelta(minutes=2),
            verification_ref="A" * 43,
            attestation="B" * 43,
        )
        self.binding = SimpleNamespace(
            binding_id=self.agent_context.binding_id,
            identity_id=self.agent.identity.identity_id,
            issuer_id=self.issuer.issuer_id,
            revision=self.agent_context.binding_revision,
            status=SimpleNamespace(value="active"),
        )
        self.unit.native_agent_identity.get_native_agent_binding_by_id = (
            lambda binding_id: self.binding if binding_id == self.binding.binding_id else None
        )
        self.attestor = HmacVerifiedIdentityContextAttestor(b"K" * 32)
        self.service = VerifiedAgentDelegationContextService(
            unit_of_work_factory=lambda: self.unit,
            agent_context_verifier=SimpleNamespace(
                verify_in_unit_of_work=lambda context, unit: self.agent
                if context.identity_id == self.agent.identity.identity_id
                else self._reject_agent()
            ),
            clock=self.clock,
            attestor=self.attestor,
            realm="atlas.agent",
            audience="atlas.agent.delegation",
            context_ttl=timedelta(seconds=45),
        )

    @staticmethod
    def _reject_agent():
        raise VerifiedAgentDelegationContextRejected("AGENT inválido")

    def test_issues_signed_context_from_authenticated_agent_and_current_grant(self):
        context = self.service.verify_for_operation(
            self.delegation.delegation_id,
            expected_revision=self.delegation.revision,
            verified_agent_identity=self.agent_context,
        )
        self.assertEqual(context.agent_identity_id, self.agent.identity.identity_id)
        self.assertEqual(context.grant_revision, self.grant.revision)
        self.assertEqual(context.realm, "atlas.agent")
        self.assertEqual(context.audience, "atlas.agent.delegation")
        self.assertLessEqual(context.expires_at - context.verified_at, timedelta(seconds=45))
        self.assertTrue(self.attestor.verify(
            self.service._payload(context), context.attestation
        ))
        self.assertTrue(self.unit.committed)

    def test_rejects_different_authenticated_agent(self):
        other = replace(self.agent_context, identity_id=uid())
        with self.assertRaises(VerifiedAgentDelegationContextRejected):
            self.service.verify_for_operation(
                self.delegation.delegation_id,
                expected_revision=1,
                verified_agent_identity=other,
            )

    def test_rejects_agent_authenticated_by_different_issuer(self):
        other = replace(self.agent_context, issuer_id=uid())
        with self.assertRaises(VerifiedAgentDelegationContextRejected):
            self.service.verify_for_operation(
                self.delegation.delegation_id,
                expected_revision=1,
                verified_agent_identity=other,
            )

    def test_rejects_stale_delegation_revision(self):
        with self.assertRaises(VerifiedAgentDelegationContextRejected):
            self.service.verify_for_operation(
                self.delegation.delegation_id,
                expected_revision=2,
                verified_agent_identity=self.agent_context,
            )

    def test_rejects_expired_or_not_yet_valid_delegation(self):
        self.unit.agent_delegations.get = lambda delegation_id: replace(
            self.delegation, expires_at=self.now
        )
        with self.assertRaises(VerifiedAgentDelegationContextRejected):
            self.service.verify_for_operation(
                self.delegation.delegation_id,
                expected_revision=1,
                verified_agent_identity=self.agent_context,
            )

    def test_rejects_revoked_delegation(self):
        revoked = replace(
            self.delegation,
            status=AgentDelegationStatus.REVOKED,
            revision=2,
            revoked_at=self.now - timedelta(seconds=1),
            revoked_by_user_id=self.owner.user_id,
        )
        self.unit.agent_delegations.get = lambda delegation_id: revoked
        with self.assertRaises(VerifiedAgentDelegationContextRejected):
            self.service.verify_for_operation(
                revoked.delegation_id,
                expected_revision=2,
                verified_agent_identity=self.agent_context,
            )

    def test_rejects_changed_or_revoked_grant(self):
        self.unit.grants.get = lambda grant_id: replace(self.grant, revision=5)
        with self.assertRaises(VerifiedAgentDelegationContextRejected):
            self.service.verify_for_operation(
                self.delegation.delegation_id,
                expected_revision=1,
                verified_agent_identity=self.agent_context,
            )

    def test_rejects_scope_or_owner_binding_mismatch(self):
        self.unit.identity.get_user_by_identity_id = lambda identity_id: None
        with self.assertRaises(VerifiedAgentDelegationContextRejected):
            self.service.verify_for_operation(
                self.delegation.delegation_id,
                expected_revision=1,
                verified_agent_identity=self.agent_context,
            )

    def test_verifies_context_against_live_state_and_rejects_tampering(self):
        context = self.service.verify_for_operation(
            self.delegation.delegation_id,
            expected_revision=1,
            verified_agent_identity=self.agent_context,
        )
        self.assertEqual(self.service.verify(context), self.delegation)
        tampered = replace(context, project_id="other-project")
        with self.assertRaises(VerifiedAgentDelegationContextRejected):
            self.service.verify(tampered)

    def test_shared_uow_verification_does_not_commit_caller_transaction(self):
        context = self.service.verify_for_operation(
            self.delegation.delegation_id,
            expected_revision=1,
            verified_agent_identity=self.agent_context,
        )
        self.unit.committed = False
        verified = self.service.verify_in_unit_of_work(context, self.unit)
        self.assertEqual(verified, self.delegation)
        self.assertFalse(self.unit.committed)

    def test_rejects_context_after_delegation_revision_changes(self):
        context = self.service.verify_for_operation(
            self.delegation.delegation_id,
            expected_revision=1,
            verified_agent_identity=self.agent_context,
        )
        self.unit.agent_delegations.get = lambda delegation_id: replace(
            self.delegation, revision=2
        )
        with self.assertRaises(VerifiedAgentDelegationContextRejected):
            self.service.verify(context)

    def test_rejects_replaced_or_revoked_agent_binding(self):
        context = self.service.verify_for_operation(
            self.delegation.delegation_id,
            expected_revision=1,
            verified_agent_identity=self.agent_context,
        )
        self.binding.revision = 3
        with self.assertRaises(VerifiedAgentDelegationContextRejected):
            self.service.verify(context)

    def test_caller_cannot_supply_trusted_time_realm_audience_or_ttl(self):
        parameters = inspect.signature(
            AgentDelegationAuthorityPort.verify_for_operation
        ).parameters
        self.assertEqual(
            set(parameters),
            {"self", "delegation_id", "expected_revision", "verified_agent_identity"},
        )


if __name__ == "__main__":
    unittest.main()
