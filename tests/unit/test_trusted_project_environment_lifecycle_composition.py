"""Real Identity Authority + HMAC integration for trusted lifecycle composition."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from atlas.adapters.hmac_verified_identity_context_attestor import HmacVerifiedIdentityContextAttestor
from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.local_authority_unit_of_work import SQLiteLocalAuthorityUnitOfWorkFactory
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.adapters.sqlite.platform_admin_bootstrap import SQLitePlatformAdminBootstrapAdapter
from atlas.authentication.credentials import LoginHandle
from atlas.authentication.native import NativeAuthenticationProof, NativeAuthenticator, NativeProofReference, NativeSubject
from atlas.core.context import OperationContext
from atlas.core.errors import AuthorizationError
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
            authenticator = NativeAuthenticator(
                authenticator_id=_uuid(), issuer_id=self.issuer.issuer_id,
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
            unit.workspaces.create_association(
                ProjectEnvironmentAssociation(
                    ProjectId("atlas"), EnvironmentId("test"),
                    ProjectEnvironmentStatus.ACTIVE,
                )
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

    def _provision_admin(self):
        confirmed = NOW - timedelta(days=1)
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
        event = self.lifecycle.transition(self.context, evidence, self._request())
        self.assertEqual(event.new_status, ProjectEnvironmentStatus.SUSPENDED)
        self.assertEqual(len(seen), 1)
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
        evidence = self._evidence()
        other = VerifiedIdentityContextService(
            unit_of_work_factory=self.factory, clock=self.clock,
            attestor=self.attestor, realm=REALM, audience="atlas.other",
            context_ttl=timedelta(minutes=2),
        )
        with self.assertRaises(VerifiedIdentityContextRejected):
            other.verify(evidence)
        with self.assertRaises(AuthorizationError):
            self.lifecycle.transition(self.context, evidence, self._request())
        self.assertEqual(self._state(), ("active", 1, 0, 0))


if __name__ == "__main__":
    unittest.main()
