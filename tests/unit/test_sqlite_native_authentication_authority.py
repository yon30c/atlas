from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import threading
import unittest
from uuid import uuid4

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.local_authority_unit_of_work import SQLiteLocalAuthorityUnitOfWorkFactory
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.adapters.sqlite.native_identity_authority import SQLiteNativeIdentityAuthority
from atlas.adapters.sqlite.native_authentication_authority import SQLiteNativeAuthenticationAuthority
from atlas.authentication.credentials import LoginHandle
from atlas.authentication.native import (
    NativeAuthenticationProof,
    NativeAuthenticationProofStatus,
    NativeAuthenticator,
    NativeProofReference,
    NativeSubject,
)
from atlas.core.errors import ConcurrencyError, IdentityConflictError


_PHC = "$argon2id$v=19$m=8,t=1,p=1$c2FsdHNhbHRzYWx0c2FsdA$aGFzaGhhc2hoYXNo"


class SQLiteNativeAuthenticationAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "native-auth.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.identity = SQLiteNativeIdentityAuthority(self.database)
        self.authority = SQLiteNativeAuthenticationAuthority(self.database)
        self.issuer = self.identity.create_native_issuer("atlas.primary")
        self.authenticator = NativeAuthenticator(
            authenticator_id=str(uuid4()), issuer_id=self.issuer.issuer_id,
            native_subject=NativeSubject.generate(), login_handle=LoginHandle("Yohenrry.Login"),
            password_hash_phc=_PHC,
        )
        self.authority.create_native_authenticator(self.authenticator)

    def _proof(self, *, expires=None):
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=1) if expires is None else expires
        authenticated_at = (
            expires_at - timedelta(seconds=30)
            if expires_at <= now else now
        )
        reference = NativeProofReference.generate()
        proof = NativeAuthenticationProof(
            proof_id=str(uuid4()), reference_digest=reference.digest,
            issuer_id=self.authenticator.issuer_id,
            native_subject=self.authenticator.native_subject,
            authenticator_id=self.authenticator.authenticator_id,
            credential_revision=self.authenticator.credential_revision,
            authenticated_at=authenticated_at, expires_at=expires_at,
            audience="atlas.internal",
        )
        return reference, self.authority.create_native_authentication_proof(proof)

    def test_authenticator_round_trip_and_login_handle_uniqueness(self):
        self.assertEqual(self.authority.get_native_authenticator(self.authenticator.authenticator_id), self.authenticator)
        self.assertEqual(self.authority.get_native_authenticator_by_login_handle(self.issuer.issuer_id, "yohenrry.login"), self.authenticator)
        duplicate = NativeAuthenticator(
            authenticator_id=str(uuid4()), issuer_id=self.issuer.issuer_id,
            native_subject=NativeSubject.generate(), login_handle=LoginHandle("YOHENRRY.LOGIN"),
            password_hash_phc=_PHC,
        )
        with self.assertRaises(IdentityConflictError):
            self.authority.create_native_authenticator(duplicate)

    def test_proof_persists_only_digest_and_consumes_once(self):
        reference, proof = self._proof()
        with self.database.connection() as connection:
            digest = connection.execute("SELECT reference_digest FROM native_authentication_proofs WHERE proof_id = ?", (proof.proof_id,)).fetchone()[0]
        self.assertEqual(digest, reference.digest)
        self.assertNotIn(reference.value, digest)
        now = datetime.now(timezone.utc)
        self.assertIsNone(self.authority.consume_native_authentication_proof(reference, expected_audience="atlas.other", consumed_at=now))
        consumed = self.authority.consume_native_authentication_proof(reference, expected_audience="atlas.internal", consumed_at=now)
        self.assertEqual(consumed.status, NativeAuthenticationProofStatus.CONSUMED)
        self.assertIsNone(self.authority.consume_native_authentication_proof(reference, expected_audience="atlas.internal", consumed_at=now))

    def test_expired_proof_becomes_terminal(self):
        now = datetime.now(timezone.utc)
        reference, proof = self._proof(expires=now - timedelta(seconds=1))
        self.assertIsNone(self.authority.consume_native_authentication_proof(reference, expected_audience="atlas.internal", consumed_at=now))
        with self.database.connection() as connection:
            status = connection.execute("SELECT status FROM native_authentication_proofs WHERE proof_id = ?", (proof.proof_id,)).fetchone()[0]
        self.assertEqual(status, "EXPIRED")

    def test_password_revision_change_revokes_pending_proofs(self):
        reference, proof = self._proof()
        updated = self.authority.update_native_password_hash(self.authenticator.authenticator_id, expected_credential_revision=1, password_hash_phc=_PHC + "x")
        self.assertEqual(updated.credential_revision, 2)
        self.assertIsNone(self.authority.consume_native_authentication_proof(reference, expected_audience="atlas.internal", consumed_at=datetime.now(timezone.utc)))
        with self.database.connection() as connection:
            status = connection.execute("SELECT status FROM native_authentication_proofs WHERE proof_id = ?", (proof.proof_id,)).fetchone()[0]
        self.assertEqual(status, "REVOKED")

    def test_password_revision_update_uses_cas(self):
        with self.assertRaises(ConcurrencyError):
            self.authority.update_native_password_hash(self.authenticator.authenticator_id, expected_credential_revision=8, password_hash_phc=_PHC + "x")

    def test_concurrent_consumers_have_exactly_one_winner(self):
        reference, _ = self._proof()
        barrier = threading.Barrier(2)
        def consume(_):
            barrier.wait()
            return SQLiteNativeAuthenticationAuthority(self.database).consume_native_authentication_proof(
                reference, expected_audience="atlas.internal", consumed_at=datetime.now(timezone.utc)
            )
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(consume, range(2)))
        self.assertEqual(sum(item is not None for item in results), 1)

    def test_shared_uow_commits_and_rolls_back_authenticator(self):
        factory = SQLiteLocalAuthorityUnitOfWorkFactory(self.database)
        auth_id = str(uuid4())
        with factory() as unit:
            self.assertIs(unit.native_authentication._unit_of_work, unit._unit)
            unit.native_authentication.create_native_authenticator(NativeAuthenticator(
                authenticator_id=auth_id, issuer_id=self.issuer.issuer_id,
                native_subject=NativeSubject.generate(), login_handle=LoginHandle("transactional"),
                password_hash_phc=_PHC,
            ))
            unit.commit()
        self.assertIsNotNone(self.authority.get_native_authenticator(auth_id))
        rollback_id = str(uuid4())
        with self.assertRaisesRegex(RuntimeError, "rollback auth"):
            with factory() as unit:
                unit.native_authentication.create_native_authenticator(NativeAuthenticator(
                    authenticator_id=rollback_id, issuer_id=self.issuer.issuer_id,
                    native_subject=NativeSubject.generate(), login_handle=LoginHandle("rollback"),
                    password_hash_phc=_PHC,
                ))
                raise RuntimeError("rollback auth")
        self.assertIsNone(self.authority.get_native_authenticator(rollback_id))

    def test_v19_to_v20_upgrade_and_foreign_key_check(self):
        legacy = SQLiteDatabase(Path(self.temp_dir.name) / "v19.sqlite")
        legacy.apply_migrations(SQLITE_MIGRATIONS[:-1])
        legacy_identity = SQLiteNativeIdentityAuthority(legacy)
        preserved_issuer = legacy_identity.create_native_issuer("atlas.preserved")
        with legacy.connection() as connection:
            self.assertEqual(connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 19)
        self.assertEqual(legacy.apply_migrations(SQLITE_MIGRATIONS), 20)
        self.assertEqual(legacy_identity.get_native_issuer("atlas.preserved"), preserved_issuer)
        self.assertEqual(legacy.apply_migrations(SQLITE_MIGRATIONS), 20)
        with legacy.connection() as connection:
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertIsNotNone(connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='native_authenticators'").fetchone())


if __name__ == "__main__":
    unittest.main()
