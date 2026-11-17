from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest
from uuid import uuid4

from atlas.core.agent_delegation import (
    AgentDelegation,
    AgentDelegationScope,
    AgentDelegationStatus,
    VerifiedAgentDelegationContext,
)
from atlas.core.agent_identity import CanonicalAgentIdentity
from atlas.core.errors import ContractError
from atlas.core.identity import Identity, IdentityKind, IdentityStatus
from atlas.core.native_agent_identity import (
    NativeAgentIdentityBinding,
    NativeAgentIdentityBindingStatus,
)
from atlas.core.verified_agent_identity_context import VerifiedAgentIdentityContext


def uid():
    return str(uuid4())


class AgentDelegationDomainContractTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
        self.agent_id = uid()
        self.owner_identity_id = uid()
        self.owner_user_id = uid()
        self.issuer_id = uid()
        self.binding_id = uid()
        self.delegation_id = uid()
        self.agent = CanonicalAgentIdentity(
            Identity(self.agent_id, IdentityKind.AGENT, IdentityStatus.ACTIVE, 3)
        )
        self.scope = AgentDelegationScope(
            resource_type="workspace",
            resource_ids=frozenset({"workspace-1", "workspace-2"}),
            actions=frozenset({"workspace.read", "grant.renewal.request"}),
        )

    def _agent_context(self):
        return VerifiedAgentIdentityContext(
            context_id=uid(),
            identity_id=self.agent_id,
            identity_type=IdentityKind.AGENT,
            identity_revision=3,
            binding_id=self.binding_id,
            binding_revision=2,
            issuer_id=self.issuer_id,
            authenticated_at=self.now - timedelta(seconds=2),
            verified_at=self.now,
            expires_at=self.now + timedelta(minutes=2),
            verification_ref="A" * 43,
            attestation="B" * 43,
        )

    def _delegation(self, **changes):
        values = dict(
            delegation_id=self.delegation_id,
            owner_user_id=self.owner_user_id,
            owner_identity_id=self.owner_identity_id,
            agent_identity_id=self.agent_id,
            grant_id="grant-123",
            grant_revision=4,
            project_id="project-1",
            environment="production",
            scope=self.scope,
            issuer_id=self.issuer_id,
            issued_at=self.now,
            not_before=self.now,
            expires_at=self.now + timedelta(days=1),
            created_by_user_identity_id=self.owner_identity_id,
        )
        values.update(changes)
        return AgentDelegation(**values)

    def _delegation_context(self):
        return VerifiedAgentDelegationContext(
            context_id=uid(),
            delegation_id=self.delegation_id,
            delegation_revision=2,
            owner_user_id=self.owner_user_id,
            owner_identity_id=self.owner_identity_id,
            agent_identity_id=self.agent_id,
            grant_id="grant-123",
            grant_revision=4,
            project_id="project-1",
            environment="production",
            scope=self.scope,
            issuer_id=self.issuer_id,
            verified_at=self.now,
            expires_at=self.now + timedelta(minutes=1),
            verification_ref="C" * 43,
            attestation="D" * 43,
        )

    def test_canonical_agent_identity_accepts_only_agent(self):
        self.assertEqual(self.agent.identity.kind, IdentityKind.AGENT)
        with self.assertRaises(ContractError):
            CanonicalAgentIdentity(
                Identity(uid(), IdentityKind.USER, IdentityStatus.ACTIVE)
            )
        with self.assertRaises(ContractError):
            CanonicalAgentIdentity(
                Identity("not-a-uuid", IdentityKind.AGENT, IdentityStatus.ACTIVE)
            )

    def test_verified_agent_context_is_agent_only(self):
        context = self._agent_context()
        self.assertIn(b'"identity_type":"agent"', context.attestation_payload())
        with self.assertRaises(ContractError):
            replace(context, identity_type=IdentityKind.USER)
        with self.assertRaises(ContractError):
            replace(context, identity_revision=True)
        with self.assertRaises(ContractError):
            replace(context, expires_at=context.verified_at)
        self.assertNotIn("attestation=", repr(context))

    def test_native_agent_binding_enforces_type_independent_identity_id_and_lifecycle(self):
        binding = NativeAgentIdentityBinding(
            binding_id=self.binding_id,
            identity_id=self.agent_id,
            issuer_id=self.issuer_id,
            subject_digest="a" * 64,
            status=NativeAgentIdentityBindingStatus.ACTIVE,
            created_at=self.now - timedelta(seconds=1),
            verified_at=self.now,
            revision=2,
        )
        self.assertEqual(binding.revision, 2)
        with self.assertRaises(ContractError):
            replace(binding, subject_digest="A" * 64)
        with self.assertRaises(ContractError):
            replace(binding, status=NativeAgentIdentityBindingStatus.REVOKED)
        revoked = replace(
            binding,
            status=NativeAgentIdentityBindingStatus.REVOKED,
            revision=3,
            revoked_at=self.now + timedelta(seconds=1),
        )
        self.assertEqual(revoked.status, NativeAgentIdentityBindingStatus.REVOKED)
        with self.assertRaises(ContractError):
            replace(revoked, status=NativeAgentIdentityBindingStatus.ACTIVE)

    def test_scope_rejects_empty_sets_and_wildcards(self):
        with self.assertRaises(ContractError):
            AgentDelegationScope("workspace", frozenset(), frozenset({"workspace.read"}))
        with self.assertRaises(ContractError):
            AgentDelegationScope("workspace", frozenset({"*"}), frozenset({"workspace.read"}))
        with self.assertRaises(ContractError):
            AgentDelegationScope("workspace", frozenset({"workspace-1"}), frozenset({"*"}))

    def test_delegation_binds_owner_agent_grant_revision_and_window(self):
        delegation = self._delegation()
        self.assertEqual(delegation.owner_user_id, self.owner_user_id)
        self.assertEqual(delegation.owner_identity_id, self.owner_identity_id)
        self.assertEqual(delegation.agent_identity_id, self.agent_id)
        self.assertEqual(delegation.grant_revision, 4)
        with self.assertRaises(ContractError):
            self._delegation(agent_identity_id=self.owner_identity_id)
        with self.assertRaises(ContractError):
            self._delegation(not_before=self.now - timedelta(seconds=1))
        with self.assertRaises(ContractError):
            self._delegation(expires_at=self.now)
        with self.assertRaises(ContractError):
            self._delegation(grant_revision=True)

    def test_delegation_revocation_is_terminal_and_auditable(self):
        active = self._delegation()
        revoked = replace(
            active,
            status=AgentDelegationStatus.REVOKED,
            revision=2,
            revoked_at=self.now + timedelta(seconds=1),
            revoked_by_user_id=self.owner_user_id,
        )
        self.assertEqual(revoked.status, AgentDelegationStatus.REVOKED)
        with self.assertRaises(ContractError):
            replace(revoked, status=AgentDelegationStatus.ACTIVE, revoked_at=None, revoked_by_user_id=None)
        with self.assertRaises(ContractError):
            self._delegation(
                status=AgentDelegationStatus.REVOKED,
                revoked_at=self.now,
                revoked_by_user_id=None,
            )

    def test_verified_delegation_context_is_canonical_and_deterministic(self):
        context = self._delegation_context()
        payload = context.attestation_payload()
        self.assertIn(b'"protocol":"atlas:verified-agent-delegation:v1"', payload)
        self.assertIn(b'"grant_revision":4', payload)
        self.assertEqual(payload, context.attestation_payload())
        self.assertNotIn("attestation=", repr(context))
        with self.assertRaises(ContractError):
            replace(context, grant_revision=0)
        with self.assertRaises(ContractError):
            replace(context, expires_at=context.verified_at)

    def test_verified_delegation_context_rejects_noncanonical_identity_ids(self):
        context = self._delegation_context()
        with self.assertRaises(ContractError):
            replace(context, agent_identity_id="not-a-canonical-uuid")


if __name__ == "__main__":
    unittest.main()
