"""Real Identity Authority + HMAC integration for trusted lifecycle composition."""

from dataclasses import replace
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from atlas.adapters.hmac_verified_identity_context_attestor import HmacVerifiedIdentityContextAttestor
from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.local_authority_unit_of_work import (
    SQLiteLocalAuthorityUnitOfWork,
    SQLiteLocalAuthorityUnitOfWorkFactory,
)
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.adapters.sqlite.platform_admin_bootstrap import SQLitePlatformAdminBootstrapAdapter
from atlas.adapters.sqlite.project_environment_lifecycle_ledger import SQLiteProjectEnvironmentLifecycleLedger
from atlas.authentication.credentials import LoginHandle
from atlas.authentication.native import NativeAuthenticationProof, NativeAuthenticator, NativeProofReference, NativeSubject
from atlas.core.context import OperationContext
from atlas.core.enums import DelegationMode
from atlas.core.errors import AuthorizationError, ContractError
from atlas.identity.verified_identity_context_service import VerifiedIdentityContextRejected
from atlas.core.identity import IdentityStatus
from atlas.core.platform_admin import (
    INITIAL_PLATFORM_ADMIN_PERMISSIONS,
    PlatformAdminBootstrapCommand,
    PlatformAdminBootstrapProvenance,
    PlatformAdminBootstrapRequest,
    PlatformAdminGrant,
    PlatformAdminProvisioningMethod,
)
from atlas.core.project_environment_lifecycle import ProjectEnvironmentLifecycleRequest
from atlas.application.project_environment_lifecycle_composition import build_trusted_project_environment_lifecycle_service
from atlas.identity.verified_identity_context_service import VerifiedIdentityContextService
from atlas.memory.metadata import EnvironmentMetadata, ProjectMetadata
from atlas.memory.models import EnvironmentId, ProjectId
from tests.unit.association_provisioning_test_support import provision_association
from atlas.workspace.models import ProjectEnvironmentAssociation, ProjectEnvironmentStatus


NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
REALM = "atlas.primary"
AUDIENCE = "atlas.internal"
_PHC = "$argon2id$v=19$m=8,t=1,p=1$c2FsdHNhbHRzYWx0c2FsdA$aGFzaGhhc2hoYXNo"


class FixedClock:
    def __init__(self):
        self.value = NOW

    def now(self):
        return self.value


def _uuid():
    return str(uuid4())


class TrustedLifecycleCompositionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "integration.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.factory = SQLiteLocalAuthorityUnitOfWorkFactory(self.database)
        self.clock = FixedClock()
        self.attestor = HmacVerifiedIdentityContextAttestor(b"test-only-key-material-32-bytes!!")
        with self.factory() as unit:
            self.user = unit.identity.create_user()
            self.issuer = unit.native_identity.create_native_issuer(REALM)
            self.subject = NativeSubject.generate()
            self.binding = unit.native_identity.create_native_binding(
                self.user, self.issuer.issuer_id, self.subject.digest,
                verified_at=self.clock.now() - timedelta(seconds=2),
            )
            self.authenticator_id = _uuid()
            authenticator = NativeAuthenticator(
                authenticator_id=self.authenticator_id, issuer_id=self.issuer.issuer_id,
                native_subject=self.subject, login_handle=LoginHandle("atlas.owner"),
                password_hash_phc=_PHC,
            )
            unit.native_authentication.create_native_authenticator(authenticator)
            self.reference = NativeProofReference.generate()
            unit.native_authentication.create_native_authentication_proof(
                NativeAuthenticationProof(
                    proof_id=_uuid(), reference_digest=self.reference.digest,
                    issuer_id=self.issuer.issuer_id, native_subject=self.subject,
                    authenticator_id=authenticator.authenticator_id,
                    credential_revision=1,
                    authenticated_at=self.clock.now() - timedelta(seconds=1),
                    expires_at=self.clock.now() + timedelta(minutes=1),
                    audience=AUDIENCE,
                )
            )
            unit.project_environments.create_project(
                ProjectMetadata(ProjectId("atlas"), "active", 1)
            )
            unit.project_environments.create_environment(
                EnvironmentMetadata(EnvironmentId("test"), "active", 1)
            )
            provision_association(
                self.database,
                ProjectEnvironmentAssociation(
                    ProjectId("atlas"), EnvironmentId("test"),
                    ProjectEnvironmentStatus.ACTIVE,
                ),
                unit_of_work=unit._unit,
            )
            unit.commit()
        self._provision_admin()
        self.identity_service = VerifiedIdentityContextService(
            unit_of_work_factory=self.factory, clock=self.clock,
            attestor=self.attestor, realm=REALM, audience=AUDIENCE,
            context_ttl=timedelta(minutes=2),
        )
        self.lifecycle = build_trusted_project_environment_lifecycle_service(
            database=self.database, clock=self.clock, attestor=self.attestor,
            realm=REALM, audience=AUDIENCE, context_ttl=timedelta(minutes=2),
        )
        self.context = OperationContext(
            request_id=_uuid(), correlation_id=_uuid(), actor=self.user.identity,
            user_id=self.user.user_id, origin="integration-test", delegation=None,
            project_id="atlas", environment="test", purpose="association lifecycle",
            classification="internal", created_at=NOW,
        )

    def test_lifecycle_composition_reuses_the_supplied_authority_factory(self):
        lifecycle = build_trusted_project_environment_lifecycle_service(
            database=self.database,
            clock=self.clock,
            attestor=self.attestor,
            realm=REALM,
            audience=AUDIENCE,
            context_ttl=timedelta(minutes=2),
            unit_of_work_factory=self.factory,
        )

        self.assertIs(lifecycle._unit_of_work_factory, self.factory)
        self.assertIs(
            lifecycle._identity_verifier._uow_factory,
            self.factory,
        )

    def test_lifecycle_composition_rejects_a_factory_for_another_database(self):
        other_database = SQLiteDatabase(
            Path(self.temp_dir.name) / "other-authority.sqlite"
        )
        other_factory = SQLiteLocalAuthorityUnitOfWorkFactory(other_database)

        with self.assertRaises(ContractError):
            build_trusted_project_environment_lifecycle_service(
                database=self.database,
                clock=self.clock,
                attestor=self.attestor,
                realm=REALM,
                audience=AUDIENCE,
                context_ttl=timedelta(minutes=2),
                unit_of_work_factory=other_factory,
            )

    def _provision_admin(self):
        # Keep the valid 90-day grant close to expiry so tests can prove grant expiry
        # while the independently attested USER context remains valid.
        confirmed = NOW - timedelta(days=90) + timedelta(minutes=1)
        request = PlatformAdminBootstrapRequest(
            operation_id=_uuid(), user_id=self.user.user_id,
            permissions=INITIAL_PLATFORM_ADMIN_PERMISSIONS,
        )
        provenance = PlatformAdminBootstrapProvenance(
            event_id=_uuid(), grant_id=_uuid(), operator_real_uid=1000,
            operator_effective_uid=1000, terminal_id="/dev/pts/test",
            confirmed_at=confirmed,
        )
        grant = PlatformAdminGrant(
            grant_id=provenance.grant_id, user_id=self.user.user_id,
            user_identity_id=self.user.identity.identity_id,
            user_identity_revision=self.user.identity.revision,
            permissions=INITIAL_PLATFORM_ADMIN_PERMISSIONS,
            provisioning_method=PlatformAdminProvisioningMethod.OFFLINE_BOOTSTRAP,
            bootstrap_event_id=provenance.event_id, issued_at=confirmed,
            not_before=confirmed, expires_at=confirmed + timedelta(days=90),
        )
        SQLitePlatformAdminBootstrapAdapter(self.database).provision_first_admin(
            PlatformAdminBootstrapCommand(request, provenance, grant)
        )

    def _evidence(self):
        return self.identity_service.admit_proof(self.reference)

    def _request(self):
        return ProjectEnvironmentLifecycleRequest(
            ProjectId("atlas"), EnvironmentId("test"),
            ProjectEnvironmentStatus.SUSPENDED, expected_revision=1,
            reason="Approved maintenance action",
        )

    def _state(self):
        with self.database.connection() as connection:
            association = connection.execute(
                "SELECT status, revision FROM atlas_project_environments"
            ).fetchone()
            events = connection.execute(
                "SELECT COUNT(*) FROM atlas_project_environment_lifecycle_events"
            ).fetchone()[0]
            markers = connection.execute(
                "SELECT COUNT(*) FROM atlas_project_environment_lifecycle_commits"
            ).fetchone()[0]
        return (association["status"], association["revision"], events, markers)

    def test_real_native_proof_hmac_verifier_and_lifecycle_share_transaction(self):
        evidence = self._evidence()
        verifier = self.lifecycle._identity_verifier
        self.assertIsInstance(verifier, VerifiedIdentityContextService)
        seen = []
        original = verifier.verify_in_unit_of_work

        def observe(context, unit):
            self.assertTrue(unit._connection.in_transaction)
            seen.append((id(unit), id(unit._connection)))
            return original(context, unit)

        verifier.verify_in_unit_of_work = observe
        ledger_connection_ids = []
        original_append = SQLiteProjectEnvironmentLifecycleLedger.append_event

        def observe_append(ledger, event):
            with ledger._write_connection() as connection:
                ledger_connection_ids.append(id(connection))
            return original_append(ledger, event)

        SQLiteProjectEnvironmentLifecycleLedger.append_event = observe_append
        try:
            event = self.lifecycle.transition(self.context, evidence, self._request())
        finally:
            SQLiteProjectEnvironmentLifecycleLedger.append_event = original_append
        self.assertEqual(event.new_status, ProjectEnvironmentStatus.SUSPENDED)
        self.assertEqual(len(seen), 1)
        self.assertEqual(ledger_connection_ids, [seen[0][1]])
        self.assertEqual(self._state(), ("suspended", 2, 1, 1))

    def test_tampered_attestation_denies_without_any_lifecycle_write(self):
        evidence = self._evidence()
        tampered = replace(evidence, attestation=("A" if evidence.attestation[0] != "A" else "B") + evidence.attestation[1:])
        with self.assertRaises(AuthorizationError):
            self.lifecycle.transition(self.context, tampered, self._request())
        self.assertEqual(self._state(), ("active", 1, 0, 0))

    def test_revoked_binding_denies_without_any_lifecycle_write(self):
        evidence = self._evidence()
        with self.factory() as unit:
            unit.native_identity.revoke_native_binding(
                self.binding.binding_id, expected_revision=1,
                revoked_at=self.clock.now() + timedelta(seconds=1),
            )
            unit.commit()
        with self.assertRaises(AuthorizationError):
            self.lifecycle.transition(self.context, evidence, self._request())
        self.assertEqual(self._state(), ("active", 1, 0, 0))

    def test_expired_context_denies_without_any_lifecycle_write(self):
        evidence = self._evidence()
        self.clock.value += timedelta(minutes=3)
        with self.assertRaises(AuthorizationError):
            self.lifecycle.transition(self.context, evidence, self._request())
        self.assertEqual(self._state(), ("active", 1, 0, 0))

    def test_changed_canonical_user_revision_denies_without_any_lifecycle_write(self):
        evidence = self._evidence()
        with self.factory() as unit:
            unit.identity.update_user_status(
                self.user.user_id, expected_revision=1,
                status=IdentityStatus.SUSPENDED,
            )
            unit.commit()
        with self.assertRaises(AuthorizationError):
            self.lifecycle.transition(self.context, evidence, self._request())
        self.assertEqual(self._state(), ("active", 1, 0, 0))

    def test_wrong_audience_attestation_denies_without_any_lifecycle_write(self):
        other_reference = NativeProofReference.generate()
        with self.factory() as unit:
            unit.native_authentication.create_native_authentication_proof(
                NativeAuthenticationProof(
                    proof_id=_uuid(), reference_digest=other_reference.digest,
                    issuer_id=self.issuer.issuer_id, native_subject=self.subject,
                    authenticator_id=self.authenticator_id,
                    credential_revision=1,
                    authenticated_at=self.clock.now() - timedelta(seconds=1),
                    expires_at=self.clock.now() + timedelta(minutes=1),
                    audience="atlas.other",
                )
            )
            unit.commit()

        other = VerifiedIdentityContextService(
            unit_of_work_factory=self.factory, clock=self.clock,
            attestor=self.attestor, realm=REALM, audience="atlas.other",
            context_ttl=timedelta(minutes=2),
        )
        wrong_audience_evidence = other.admit_proof(other_reference)
        with self.assertRaises(VerifiedIdentityContextRejected):
            self.lifecycle._identity_verifier.verify(wrong_audience_evidence)
        with self.assertRaises(AuthorizationError):
            self.lifecycle.transition(
                self.context, wrong_audience_evidence, self._request()
            )
        self.assertEqual(self._state(), ("active", 1, 0, 0))


    def test_revoked_platform_admin_grant_denies_without_any_lifecycle_write(self):
        evidence = self._evidence()
        with self.database.unit_of_work() as unit:
            unit._connection_for(self.database).execute(
                """
                UPDATE platform_admin_grants
                SET status='revoked', revision=revision+1, revoked_at=?,
                    revoked_by_user_id=?
                """,
                (self.clock.now().isoformat(), self.user.user_id),
            )
        with self.assertRaises(AuthorizationError):
            self.lifecycle.transition(self.context, evidence, self._request())
        self.assertEqual(self._state(), ("active", 1, 0, 0))


    def test_revoked_native_issuer_denies_without_any_lifecycle_write(self):
        evidence = self._evidence()
        with self.database.unit_of_work() as unit:
            connection = unit._connection_for(self.database)
            connection.execute(
                """
                UPDATE native_identity_issuers
                SET status='REVOKED', revision=revision+1, updated_at=?
                WHERE issuer_id=?
                """,
                (self.clock.now().isoformat(), self.issuer.issuer_id),
            )
        with self.assertRaises(AuthorizationError):
            self.lifecycle.transition(self.context, evidence, self._request())
        self.assertEqual(self._state(), ("active", 1, 0, 0))

    def test_wrong_realm_configuration_denies_without_any_lifecycle_write(self):
        evidence = self._evidence()
        wrong_realm_lifecycle = build_trusted_project_environment_lifecycle_service(
            database=self.database, clock=self.clock, attestor=self.attestor,
            realm="atlas.secondary", audience=AUDIENCE,
            context_ttl=timedelta(minutes=2),
        )
        with self.assertRaises(AuthorizationError):
            wrong_realm_lifecycle.transition(self.context, evidence, self._request())
        self.assertEqual(self._state(), ("active", 1, 0, 0))

    def test_actor_mismatch_and_delegated_context_deny_without_writes(self):
        evidence = self._evidence()
        with self.factory() as unit:
            other_user = unit.identity.create_user()
            unit.commit()
        invalid_contexts = (
            replace(self.context, actor=other_user.identity),
            replace(self.context, delegation=DelegationMode.DELEGATED),
        )
        for invalid_context in invalid_contexts:
            with self.subTest(delegation=invalid_context.delegation):
                with self.assertRaises(AuthorizationError):
                    self.lifecycle.transition(invalid_context, evidence, self._request())
                self.assertEqual(self._state(), ("active", 1, 0, 0))

    def test_expired_platform_admin_grant_denies_while_user_context_is_still_valid(self):
        evidence = self._evidence()
        self.clock.value += timedelta(seconds=61)
        self.assertGreater(evidence.expires_at, self.clock.now())
        with self.assertRaises(AuthorizationError):
            self.lifecycle.transition(self.context, evidence, self._request())
        self.assertEqual(self._state(), ("active", 1, 0, 0))

    def test_missing_exact_platform_admin_permission_denies_without_writes(self):
        with self.factory() as unit:
            limited_user = unit.identity.create_user()
            subject = NativeSubject.generate()
            unit.native_identity.create_native_binding(
                limited_user, self.issuer.issuer_id, subject.digest,
                verified_at=self.clock.now() - timedelta(seconds=2),
            )
            authenticator_id = _uuid()
            authenticator = NativeAuthenticator(
                authenticator_id=authenticator_id, issuer_id=self.issuer.issuer_id,
                native_subject=subject, login_handle=LoginHandle("atlas.limited-owner"),
                password_hash_phc=_PHC,
            )
            unit.native_authentication.create_native_authenticator(authenticator)
            reference = NativeProofReference.generate()
            unit.native_authentication.create_native_authentication_proof(
                NativeAuthenticationProof(
                    proof_id=_uuid(), reference_digest=reference.digest,
                    issuer_id=self.issuer.issuer_id, native_subject=subject,
                    authenticator_id=authenticator_id, credential_revision=1,
                    authenticated_at=self.clock.now() - timedelta(seconds=1),
                    expires_at=self.clock.now() + timedelta(minutes=1),
                    audience=AUDIENCE,
                )
            )
            event_id, grant_id, operation_id = _uuid(), _uuid(), _uuid()
            confirmed = NOW - timedelta(days=1)
            connection = unit._unit._connection_for(self.database)
            connection.execute(
                "INSERT INTO platform_admin_bootstrap_events (event_id, grant_id, user_id, user_identity_id, user_identity_revision, operation_id, operator_real_uid, operator_effective_uid, terminal_id, confirmed_at) VALUES (?, ?, ?, ?, ?, ?, 1000, 1000, '/dev/pts/test', ?)",
                (event_id, grant_id, limited_user.user_id, limited_user.identity.identity_id,
                 limited_user.identity.revision, operation_id, confirmed.isoformat()),
            )
            connection.execute(
                "INSERT INTO platform_admin_grants (grant_id, user_id, user_identity_id, user_identity_revision, permissions_json, provisioning_method, bootstrap_event_id, issued_at, not_before, expires_at, status, revision) VALUES (?, ?, ?, ?, '[\"association.reactivate\"]', 'offline_bootstrap', ?, ?, ?, ?, 'active', 1)",
                (grant_id, limited_user.user_id, limited_user.identity.identity_id,
                 limited_user.identity.revision, event_id, confirmed.isoformat(),
                 confirmed.isoformat(), (confirmed + timedelta(days=90)).isoformat()),
            )
            unit.commit()
        limited_evidence = self.identity_service.admit_proof(reference)
        limited_context = OperationContext(
            request_id=_uuid(), correlation_id=_uuid(), actor=limited_user.identity,
            user_id=limited_user.user_id, origin="integration-test", delegation=None,
            project_id="atlas", environment="test", purpose="association lifecycle",
            classification="internal", created_at=NOW,
        )
        with self.assertRaises(AuthorizationError):
            self.lifecycle.transition(limited_context, limited_evidence, self._request())
        self.assertEqual(self._state(), ("active", 1, 0, 0))

    def test_commit_failure_rolls_back_real_composed_lifecycle_transaction(self):
        evidence = self._evidence()
        with patch.object(SQLiteLocalAuthorityUnitOfWork, "commit",
                          side_effect=RuntimeError("injected commit failure")):
            with self.assertRaisesRegex(RuntimeError, "injected commit failure"):
                self.lifecycle.transition(self.context, evidence, self._request())
        self.assertEqual(self._state(), ("active", 1, 0, 0))

    def test_lifecycle_writer_is_not_a_public_package_or_uow_capability(self):
        import atlas.adapters.sqlite as sqlite_package
        import atlas.application as application_package
        self.assertNotIn("SQLiteProjectEnvironmentLifecycleLedger", sqlite_package.__all__)
        self.assertFalse(hasattr(sqlite_package, "SQLiteProjectEnvironmentLifecycleLedger"))
        self.assertFalse(hasattr(application_package, "build_trusted_project_environment_lifecycle_service"))
        with self.factory() as unit:
            self.assertFalse(hasattr(unit, "lifecycle_ledger"))
            self.assertFalse(hasattr(unit, "project_environment_lifecycle_ledger"))
            unit.commit()

if __name__ == "__main__":
    unittest.main()
