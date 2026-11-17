"""Owner-verified AGENT delegation issuance tests."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4
from unittest.mock import patch

from atlas.adapters.hmac_verified_identity_context_attestor import HmacVerifiedIdentityContextAttestor
from atlas.adapters.sqlite import (
    SQLiteAgentDelegationRepository,
    SQLiteDatabase,
    SQLiteGrantRepository,
    SQLiteLocalAuthorityUnitOfWorkFactory,
    SQLITE_MIGRATIONS,
)
from atlas.authentication.credentials import LoginHandle
from atlas.authentication.native import NativeAuthenticationProof, NativeAuthenticator, NativeProofReference, NativeSubject
from atlas.authorization.agent_delegation_authority import SQLiteAgentDelegationAuthority
from atlas.authorization.models import Grant, GrantResourceScope
from atlas.core.agent_delegation import AgentDelegationScope
from atlas.core.errors import AuthorizationError, ContractError
from atlas.identity.verified_identity_context_service import (
    VerifiedIdentityContextRejected,
    VerifiedIdentityContextService,
)


_PHC = "$argon2id$v=19$m=8,t=1,p=1$c2FsdHNhbHRzYWx0c2FsdA$aGFzaGhhc2hoYXNo"


class FixedClock:
    def __init__(self):
        self.value = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)

    def now(self):
        return self.value


class SQLiteAgentDelegationAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "delegation-authority.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.factory = SQLiteLocalAuthorityUnitOfWorkFactory(self.database)
        self.clock = FixedClock()
        self.attestor = HmacVerifiedIdentityContextAttestor(b"K" * 32)

        with self.factory() as unit:
            self.owner = unit.identity.create_user()
            self.agent = unit.agent_identity.create_agent()
            self.issuer = unit.native_identity.create_native_issuer("atlas.owner")
            self.subject = NativeSubject.generate()
            unit.native_identity.create_native_binding(
                self.owner, self.issuer.issuer_id, self.subject.digest,
                verified_at=self.clock.now() - timedelta(seconds=2),
            )
            unit.native_agent_identity.create_native_agent_binding(
                self.agent, self.issuer.issuer_id, "b" * 64,
                verified_at=self.clock.now() - timedelta(seconds=2),
            )
            self.authenticator = NativeAuthenticator(
                authenticator_id=str(uuid4()),
                issuer_id=self.issuer.issuer_id,
                native_subject=self.subject,
                login_handle=LoginHandle("atlas.owner"),
                password_hash_phc=_PHC,
            )
            unit.native_authentication.create_native_authenticator(self.authenticator)
            self.reference = NativeProofReference.generate()
            unit.native_authentication.create_native_authentication_proof(
                NativeAuthenticationProof(
                    proof_id=str(uuid4()),
                    reference_digest=self.reference.digest,
                    issuer_id=self.issuer.issuer_id,
                    native_subject=self.subject,
                    authenticator_id=self.authenticator.authenticator_id,
                    credential_revision=1,
                    authenticated_at=self.clock.now() - timedelta(seconds=1),
                    expires_at=self.clock.now() + timedelta(minutes=1),
                    audience="atlas.internal",
                )
            )
            self.grant = Grant(
                grant_id="grant-agent-delegation",
                owner_user_id=self.owner.user_id,
                subject_identity_id=self.agent.identity.identity_id,
                project_id="atlas",
                environment="test",
                resource_scope=GrantResourceScope(
                    "workspace", frozenset({"workspace-a", "workspace-b"})
                ),
                actions=frozenset({"read", "list", "write"}),
                issued_at=self.clock.now() - timedelta(minutes=5),
                expires_at=self.clock.now() + timedelta(days=3),
            )
            unit.grants.create(self.grant)
            unit.commit()

        self.owner_context_service = VerifiedIdentityContextService(
            unit_of_work_factory=self.factory,
            clock=self.clock,
            attestor=self.attestor,
            realm="atlas.owner",
            audience="atlas.internal",
            context_ttl=timedelta(minutes=2),
        )
        self.owner_context = self.owner_context_service.admit_proof(self.reference)
        self.authority = SQLiteAgentDelegationAuthority(
            unit_of_work_factory=self.factory,
            owner_context_verifier=self.owner_context_service,
            clock=self.clock,
        )

    def _create(self, **changes):
        values = {
            "grant_id": self.grant.grant_id,
            "agent_identity_id": self.agent.identity.identity_id,
            "scope": AgentDelegationScope(
                "workspace", frozenset({"workspace-a"}), frozenset({"read"})
            ),
            "not_before": self.clock.now(),
            "expires_at": self.clock.now() + timedelta(days=1),
            "verified_owner_identity": self.owner_context,
        }
        values.update(changes)
        return self.authority.create_for_grant(**values)

    def _stored(self, delegation_id):
        return SQLiteAgentDelegationRepository(self.database).get(delegation_id)

    def test_issues_delegation_from_canonical_owner_and_exact_grant(self):
        delegation = self._create()
        self.assertEqual(delegation.owner_user_id, self.owner.user_id)
        self.assertEqual(delegation.owner_identity_id, self.owner.identity.identity_id)
        self.assertEqual(delegation.created_by_user_identity_id, self.owner.identity.identity_id)
        self.assertEqual(delegation.agent_identity_id, self.agent.identity.identity_id)
        self.assertEqual(delegation.grant_revision, self.grant.revision)
        self.assertEqual(delegation.issuer_id, self.issuer.issuer_id)
        self.assertEqual(self._stored(delegation.delegation_id), delegation)

    def test_forged_or_expired_owner_context_is_rejected(self):
        forged = replace(self.owner_context, user_id=str(uuid4()))
        with self.assertRaises(VerifiedIdentityContextRejected):
            self._create(verified_owner_identity=forged)
        self.clock.value += timedelta(minutes=3)
        with self.assertRaises(VerifiedIdentityContextRejected):
            self._create()

    def test_inactive_agent_or_revoked_native_binding_is_rejected(self):
        with self.factory() as unit:
            unit.native_agent_identity.revoke_native_agent_binding(
                self._active_binding_id(), expected_revision=1,
                revoked_at=self.clock.now(),
            )
            unit.commit()
        with self.assertRaises(AuthorizationError):
            self._create()

    def _active_binding_id(self):
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT binding_id FROM native_agent_identity_bindings WHERE identity_id = ?",
                (self.agent.identity.identity_id,),
            ).fetchone()
        return row["binding_id"]


    def test_agent_binding_from_different_issuer_does_not_satisfy_delegation(self):
        with self.factory() as unit:
            unit.native_agent_identity.revoke_native_agent_binding(
                self._active_binding_id(), expected_revision=1,
                revoked_at=self.clock.now(),
            )
            other_issuer = unit.native_identity.create_native_issuer("atlas.agent-other")
            unit.native_agent_identity.create_native_agent_binding(
                self.agent, other_issuer.issuer_id, "c" * 64,
                verified_at=self.clock.now(),
            )
            unit.commit()
        with self.assertRaises(AuthorizationError):
            self._create()

    def test_revoked_grant_is_rejected(self):
        changed = replace(self.grant, revoked_at=self.clock.now(), revision=2)
        SQLiteGrantRepository(self.database).update(changed)
        with self.assertRaises(AuthorizationError):
            self._create()


    def test_expired_grant_is_rejected(self):
        changed = replace(
            self.grant,
            expires_at=self.clock.now() - timedelta(seconds=1),
            revision=2,
        )
        SQLiteGrantRepository(self.database).update(changed)
        with self.assertRaises(AuthorizationError):
            self._create()

    def test_valid_but_different_owner_context_cannot_issue_for_this_grant(self):
        with self.factory() as unit:
            other_owner = unit.identity.create_user()
            other_subject = NativeSubject.generate()
            unit.native_identity.create_native_binding(
                other_owner, self.issuer.issuer_id, other_subject.digest,
                verified_at=self.clock.now() - timedelta(seconds=2),
            )
            other_authenticator = NativeAuthenticator(
                authenticator_id=str(uuid4()),
                issuer_id=self.issuer.issuer_id,
                native_subject=other_subject,
                login_handle=LoginHandle("atlas.other-owner"),
                password_hash_phc=_PHC,
            )
            unit.native_authentication.create_native_authenticator(other_authenticator)
            other_reference = NativeProofReference.generate()
            unit.native_authentication.create_native_authentication_proof(
                NativeAuthenticationProof(
                    proof_id=str(uuid4()),
                    reference_digest=other_reference.digest,
                    issuer_id=self.issuer.issuer_id,
                    native_subject=other_subject,
                    authenticator_id=other_authenticator.authenticator_id,
                    credential_revision=1,
                    authenticated_at=self.clock.now() - timedelta(seconds=1),
                    expires_at=self.clock.now() + timedelta(minutes=1),
                    audience="atlas.internal",
                )
            )
            unit.commit()
        other_context = self.owner_context_service.admit_proof(other_reference)
        with self.assertRaises(AuthorizationError):
            self._create(verified_owner_identity=other_context)

    def test_scope_expansion_and_resource_type_mismatch_are_rejected(self):
        with self.assertRaises(AuthorizationError):
            self._create(scope=AgentDelegationScope(
                "workspace", frozenset({"workspace-c"}), frozenset({"read"})
            ))
        with self.assertRaises(AuthorizationError):
            self._create(scope=AgentDelegationScope(
                "project", frozenset({"workspace-a"}), frozenset({"read"})
            ))

    def test_delegation_window_must_fit_inside_current_grant(self):
        with self.assertRaises(AuthorizationError):
            self._create(expires_at=self.grant.expires_at + timedelta(seconds=1))
        with self.assertRaises(ContractError):
            self._create(not_before=self.clock.now() - timedelta(seconds=1))

    def test_failed_write_rolls_back_the_entire_issuance(self):
        original = SQLiteAgentDelegationRepository.create

        def create_then_fail(repository, delegation):
            original(repository, delegation)
            raise RuntimeError("injected failure after insert")

        with patch.object(SQLiteAgentDelegationRepository, "create", create_then_fail):
            with self.assertRaisesRegex(RuntimeError, "injected failure"):
                self._create()
        with self.database.connection() as connection:
            count = connection.execute(
                "SELECT COUNT(*) AS total FROM agent_delegations"
            ).fetchone()["total"]
        self.assertEqual(count, 0)

    def test_no_delegation_is_persisted_when_owner_evidence_is_missing(self):
        with self.assertRaises(AuthorizationError):
            self._create(verified_owner_identity=None)
        with self.database.connection() as connection:
            count = connection.execute(
                "SELECT COUNT(*) AS total FROM agent_delegations"
            ).fetchone()["total"]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
