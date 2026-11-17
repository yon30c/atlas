from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from atlas.adapters.hmac_verified_identity_context_attestor import (
    HmacVerifiedIdentityContextAttestor,
)
from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.local_authority_unit_of_work import (
    SQLiteLocalAuthorityUnitOfWorkFactory,
)
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.authentication.credentials import LoginHandle
from atlas.authentication.native import (
    NativeAuthenticationProof,
    NativeAuthenticator,
    NativeProofReference,
    NativeSubject,
)
from atlas.identity.verified_identity_context_service import (
    VerifiedIdentityContextRejected,
    VerifiedIdentityContextService,
)
from atlas.identity.verified_operation_context_factory import (
    VerifiedOperationContextFactory,
)


_PHC = "$argon2id$v=19$m=8,t=1,p=1$c2FsdHNhbHRzYWx0c2FsdA$aGFzaGhhc2hoYXNo"


class FixedClock:
    def __init__(self):
        self.value = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)

    def now(self):
        return self.value


class VerifiedOperationContextFactoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "operation-context.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.factory = SQLiteLocalAuthorityUnitOfWorkFactory(self.database)
        self.clock = FixedClock()
        with self.factory() as unit:
            self.user = unit.identity.create_user()
            issuer = unit.native_identity.create_native_issuer("atlas.primary")
            subject = NativeSubject.generate()
            unit.native_identity.create_native_binding(
                self.user, issuer.issuer_id, subject.digest,
                verified_at=self.clock.now(),
            )
            authenticator = NativeAuthenticator(
                authenticator_id=str(uuid4()), issuer_id=issuer.issuer_id,
                native_subject=subject, login_handle=LoginHandle("owner"),
                password_hash_phc=_PHC,
            )
            unit.native_authentication.create_native_authenticator(authenticator)
            self.reference = NativeProofReference.generate()
            unit.native_authentication.create_native_authentication_proof(
                NativeAuthenticationProof(
                    proof_id=str(uuid4()), reference_digest=self.reference.digest,
                    issuer_id=issuer.issuer_id, native_subject=subject,
                    authenticator_id=authenticator.authenticator_id,
                    credential_revision=1,
                    authenticated_at=self.clock.now() - timedelta(seconds=1),
                    expires_at=self.clock.now() + timedelta(minutes=1),
                    audience="atlas.internal",
                )
            )
            unit.commit()
        self.identity_service = VerifiedIdentityContextService(
            unit_of_work_factory=self.factory,
            clock=self.clock,
            attestor=HmacVerifiedIdentityContextAttestor(b"A" * 32),
            realm="atlas.primary",
            audience="atlas.internal",
            context_ttl=timedelta(minutes=2),
        )
        self.context = self.identity_service.admit_proof(self.reference)
        self.operation_factory = VerifiedOperationContextFactory(
            identity_context_service=self.identity_service,
            clock=self.clock,
        )

    def test_derives_user_operation_without_delegation_or_caller_selected_identity(self):
        operation = self.operation_factory.create(
            self.context,
            request_id="req-1",
            correlation_id="corr-1",
            origin="local-console",
            purpose="owner.settings",
            classification="internal",
        )
        self.assertEqual(operation.actor, self.user.identity)
        self.assertEqual(operation.user_id, self.user.user_id)
        self.assertNotEqual(operation.actor.identity_id, operation.user_id)
        self.assertIsNone(operation.delegation)
        self.assertIsNone(operation.project_id)
        self.assertIsNone(operation.environment)
        self.assertEqual(operation.created_at, self.clock.now())

    def test_invalid_or_stale_verified_context_cannot_derive_operation(self):
        self.clock.value += timedelta(minutes=3)
        with self.assertRaises(VerifiedIdentityContextRejected):
            self.operation_factory.create(
                self.context,
                request_id="req-2",
                correlation_id="corr-2",
                origin="local-console",
                purpose="owner.settings",
                classification="internal",
            )


if __name__ == "__main__":
    unittest.main()
