from dataclasses import replace
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
from atlas.adapters.sqlite.native_identity_authority import SQLiteNativeIdentityAuthority
from atlas.authentication.credentials import LoginHandle
from atlas.authentication.native import (
    NativeAuthenticationProof,
    NativeAuthenticator,
    NativeProofReference,
    NativeSubject,
)
from atlas.core.errors import ContractError
from atlas.core.identity import IdentityStatus
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


class VerifiedIdentityContextServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(
            Path(self.temp_dir.name) / "verified-context.sqlite"
        )
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.factory = SQLiteLocalAuthorityUnitOfWorkFactory(self.database)
        self.clock = FixedClock()
        self.attestor = HmacVerifiedIdentityContextAttestor(b"K" * 32)

        with self.factory() as unit:
            self.user = unit.identity.create_user()
            self.issuer = unit.native_identity.create_native_issuer("atlas.primary")
            self.subject = NativeSubject.generate()
            self.binding = unit.native_identity.create_native_binding(
                self.user,
                self.issuer.issuer_id,
                self.subject.digest,
                verified_at=self.clock.now() - timedelta(seconds=2),
            )
            self.authenticator = NativeAuthenticator(
                authenticator_id=str(uuid4()),
                issuer_id=self.issuer.issuer_id,
                native_subject=self.subject,
                login_handle=LoginHandle("atlas.owner"),
                password_hash_phc=_PHC,
            )
            unit.native_authentication.create_native_authenticator(
                self.authenticator
            )
            self.reference = NativeProofReference.generate()
            proof = NativeAuthenticationProof(
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
            unit.native_authentication.create_native_authentication_proof(proof)
            unit.commit()

    def _service(self, *, audience="atlas.internal", attestor=None):
        return VerifiedIdentityContextService(
            unit_of_work_factory=self.factory,
            clock=self.clock,
            attestor=attestor or self.attestor,
            realm="atlas.primary",
            audience=audience,
            context_ttl=timedelta(minutes=2),
        )

    def _proof_status(self):
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT status FROM native_authentication_proofs WHERE reference_digest = ?",
                (self.reference.digest,),
            ).fetchone()
        return None if row is None else row["status"]

    def test_admission_issues_attested_context_and_preserves_distinct_ids(self):
        service = self._service()
        context = service.admit_proof(self.reference)
        self.assertEqual(context.identity_id, self.user.identity.identity_id)
        self.assertEqual(context.user_id, self.user.user_id)
        self.assertNotEqual(context.identity_id, context.user_id)
        self.assertEqual(context.binding_id, self.binding.binding_id)
        self.assertEqual(context.binding_revision, 1)
        self.assertEqual(self._proof_status(), "CONSUMED")
        self.assertEqual(service.verify(context), self.user)

    def test_proof_replay_is_rejected(self):
        service = self._service()
        service.admit_proof(self.reference)
        with self.assertRaises(VerifiedIdentityContextRejected):
            service.admit_proof(self.reference)

    def test_wrong_audience_does_not_consume_proof(self):
        with self.assertRaises(VerifiedIdentityContextRejected):
            self._service(audience="atlas.other").admit_proof(self.reference)
        self.assertEqual(self._proof_status(), "PENDING")
        context = self._service().admit_proof(self.reference)
        self.assertEqual(context.issuer_id, self.issuer.issuer_id)
        self.assertEqual(self._proof_status(), "CONSUMED")

    def test_fabricated_context_claims_fail_hmac_attestation(self):
        service = self._service()
        context = service.admit_proof(self.reference)
        forged = replace(context, user_id=str(uuid4()))
        with self.assertRaises(VerifiedIdentityContextRejected):
            service.verify(forged)

    def test_context_signed_by_another_key_is_rejected(self):
        context = self._service().admit_proof(self.reference)
        other_service = self._service(
            attestor=HmacVerifiedIdentityContextAttestor(b"Z" * 32)
        )
        with self.assertRaises(VerifiedIdentityContextRejected):
            other_service.verify(context)

    def test_context_cannot_be_replayed_across_audiences(self):
        context = self._service().admit_proof(self.reference)
        other_audience_service = self._service(audience="atlas.other")
        with self.assertRaises(VerifiedIdentityContextRejected):
            other_audience_service.verify(context)

    def test_revoked_binding_invalidates_context(self):
        service = self._service()
        context = service.admit_proof(self.reference)
        authority = SQLiteNativeIdentityAuthority(self.database)
        authority.revoke_native_binding(
            self.binding.binding_id,
            expected_revision=1,
            revoked_at=self.clock.now() + timedelta(seconds=1),
        )
        with self.assertRaises(VerifiedIdentityContextRejected):
            service.verify(context)

    def test_identity_revision_change_invalidates_context(self):
        service = self._service()
        context = service.admit_proof(self.reference)
        with self.factory() as unit:
            unit.identity.update_user_status(
                self.user.user_id,
                expected_revision=1,
                status=IdentityStatus.SUSPENDED,
            )
            unit.commit()
        with self.assertRaises(VerifiedIdentityContextRejected):
            service.verify(context)

    def test_proof_authenticated_before_binding_verification_is_rejected(self):
        earlier_reference = NativeProofReference.generate()
        with self.factory() as unit:
            unit.native_authentication.create_native_authentication_proof(
                NativeAuthenticationProof(
                    proof_id=str(uuid4()),
                    reference_digest=earlier_reference.digest,
                    issuer_id=self.issuer.issuer_id,
                    native_subject=self.subject,
                    authenticator_id=self.authenticator.authenticator_id,
                    credential_revision=1,
                    authenticated_at=self.clock.now() - timedelta(seconds=3),
                    expires_at=self.clock.now() + timedelta(minutes=1),
                    audience="atlas.internal",
                )
            )
            unit.commit()
        with self.assertRaises(VerifiedIdentityContextRejected):
            self._service().admit_proof(earlier_reference)
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT status FROM native_authentication_proofs WHERE reference_digest = ?",
                (earlier_reference.digest,),
            ).fetchone()
        self.assertEqual(row["status"], "PENDING")

    def test_binding_failure_rolls_back_proof_consumption(self):
        SQLiteNativeIdentityAuthority(self.database).revoke_native_binding(
            self.binding.binding_id,
            expected_revision=1,
            revoked_at=self.clock.now() + timedelta(seconds=1),
        )
        with self.assertRaises(VerifiedIdentityContextRejected):
            self._service().admit_proof(self.reference)
        self.assertEqual(self._proof_status(), "PENDING")

    def test_expired_context_is_rejected(self):
        service = self._service()
        context = service.admit_proof(self.reference)
        self.clock.value += timedelta(minutes=3)
        with self.assertRaises(VerifiedIdentityContextRejected):
            service.verify(context)

    def test_context_requires_user_identity_and_positive_revisions(self):
        context = self._service().admit_proof(self.reference)
        with self.assertRaises(ContractError):
            replace(context, identity_revision=0)


if __name__ == "__main__":
    unittest.main()
