from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from atlas.adapters.argon2id_password_hasher import Argon2idPasswordHasher
from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.local_authority_unit_of_work import SQLiteLocalAuthorityUnitOfWorkFactory
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.adapters.sqlite.native_identity_authority import SQLiteNativeIdentityAuthority
from atlas.authentication.credentials import LoginHandle
from atlas.authentication.native import NativeAuthenticator, NativeSubject
from atlas.authentication.password_hashing import Argon2idParameters
from atlas.authentication.service import (
    AuthenticationFailed,
    AuthenticationUnavailable,
    NativeAuthenticationConfig,
    NativeAuthenticationService,
)
from atlas.core.errors import ContractError
from atlas.ports.authentication_attempt_guard import (
    AuthenticationAttemptDenied,
    AuthenticationAttemptReservation,
)


class FixedClock:
    def __init__(self):
        self.value = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)

    def now(self):
        return self.value


class FakeAttemptGuard:
    def __init__(self, *, allowed=True, fail=False):
        self.allowed = allowed
        self.fail = fail
        self.failures = []
        self.successes = []
        self.abandoned = []

    def begin_attempt(self, issuer_id, login_handle, *, at):
        if self.fail:
            raise RuntimeError("guard unavailable")
        if not self.allowed:
            raise AuthenticationAttemptDenied()
        return AuthenticationAttemptReservation(
            reservation_id=str(uuid4()),
            expires_at=at + timedelta(seconds=120),
        )

    def complete_failure(self, reservation, *, at):
        if self.fail:
            raise RuntimeError("guard unavailable")
        self.failures.append((reservation, at))

    def complete_success(self, reservation, *, at):
        if self.fail:
            raise RuntimeError("guard unavailable")
        self.successes.append((reservation, at))

    def abandon_attempt(self, reservation):
        self.abandoned.append(reservation)


class CountingHasher:
    def __init__(self, delegate):
        self.delegate = delegate
        self.verify_calls = 0

    def hash_password(self, password):
        return self.delegate.hash_password(password)

    def verify_password(self, encoded_hash, password):
        self.verify_calls += 1
        return self.delegate.verify_password(encoded_hash, password)

    def needs_rehash(self, encoded_hash):
        return self.delegate.needs_rehash(encoded_hash)


class NativeAuthenticationServiceTests(unittest.TestCase):
    PASSWORD = "correct horse battery staple"

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "auth-service.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.issuer = SQLiteNativeIdentityAuthority(self.database).create_native_issuer(
            "atlas.primary"
        )
        self.factory = SQLiteLocalAuthorityUnitOfWorkFactory(self.database)
        self.clock = FixedClock()
        self.parameters = Argon2idParameters(
            time_cost=1, memory_cost_kib=8192, parallelism=1,
            hash_len=32, salt_len=16,
        )
        self.hasher = CountingHasher(Argon2idPasswordHasher(self.parameters))
        self.guard = FakeAttemptGuard()
        self.authenticator = NativeAuthenticator(
            authenticator_id=str(uuid4()),
            issuer_id=self.issuer.issuer_id,
            native_subject=NativeSubject.generate(),
            login_handle=LoginHandle("atlas.owner"),
            password_hash_phc=self.hasher.hash_password(self.PASSWORD),
        )
        with self.factory() as unit:
            unit.native_authentication.create_native_authenticator(self.authenticator)
            unit.commit()

    def _service(self, *, guard=None, hasher=None):
        return NativeAuthenticationService(
            unit_of_work_factory=self.factory,
            password_hasher=hasher or self.hasher,
            attempt_guard=guard or self.guard,
            clock=self.clock,
            config=NativeAuthenticationConfig(
                realm="atlas.primary",
                audience="atlas.internal",
                proof_ttl=timedelta(minutes=2),
            ),
        )

    def _proof_rows(self):
        with self.database.connection() as connection:
            return connection.execute(
                "SELECT reference_digest, audience, status, credential_revision "
                "FROM native_authentication_proofs"
            ).fetchall()

    def test_correct_password_returns_reference_only_after_persisting_digest(self):
        grant = self._service().authenticate("ATLAS.OWNER", self.PASSWORD)
        rows = self._proof_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reference_digest"], grant.reference.digest)
        self.assertNotEqual(rows[0]["reference_digest"], grant.reference.value)
        self.assertEqual(rows[0]["audience"], "atlas.internal")
        self.assertEqual(rows[0]["status"], "PENDING")
        self.assertEqual(grant.expires_at - grant.authenticated_at, timedelta(minutes=2))
        self.assertEqual(len(self.guard.successes), 1)

    def test_wrong_password_is_generic_and_does_not_issue_proof(self):
        with self.assertRaises(AuthenticationFailed):
            self._service().authenticate("atlas.owner", "incorrect password")
        self.assertEqual(self._proof_rows(), [])
        self.assertEqual(len(self.guard.failures), 1)

    def test_unknown_handle_runs_dummy_verification_and_is_generic(self):
        before = self.hasher.verify_calls
        with self.assertRaises(AuthenticationFailed):
            self._service().authenticate("unknown.owner", self.PASSWORD)
        self.assertEqual(self.hasher.verify_calls - before, 1)
        self.assertEqual(self._proof_rows(), [])
        self.assertEqual(len(self.guard.failures), 1)

    def test_blocked_attempt_does_not_run_password_verification(self):
        blocked = FakeAttemptGuard(allowed=False)
        hasher = CountingHasher(Argon2idPasswordHasher(self.parameters))
        service = self._service(guard=blocked, hasher=hasher)
        with self.assertRaises(AuthenticationFailed):
            service.authenticate("atlas.owner", self.PASSWORD)
        self.assertEqual(hasher.verify_calls, 0)
        self.assertEqual(self._proof_rows(), [])

    def test_guard_unavailability_fails_closed_without_proof(self):
        with self.assertRaises(AuthenticationUnavailable):
            self._service(guard=FakeAttemptGuard(fail=True)).authenticate(
                "atlas.owner", self.PASSWORD
            )
        self.assertEqual(self._proof_rows(), [])

    def test_rehash_uses_new_credential_revision_for_proof(self):
        old_hasher = Argon2idPasswordHasher(
            Argon2idParameters(
                time_cost=1, memory_cost_kib=8192, parallelism=1,
                hash_len=16, salt_len=16,
            )
        )
        old_phc = old_hasher.hash_password(self.PASSWORD)
        with self.factory() as unit:
            unit.native_authentication.update_native_password_hash(
                self.authenticator.authenticator_id,
                expected_credential_revision=1,
                password_hash_phc=old_phc,
            )
            unit.commit()

        current_hasher = CountingHasher(Argon2idPasswordHasher(self.parameters))
        self._service(hasher=current_hasher).authenticate("atlas.owner", self.PASSWORD)
        rows = self._proof_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["credential_revision"], 3)

    def test_config_rejects_non_positive_proof_ttl(self):
        with self.assertRaises(ContractError):
            NativeAuthenticationConfig(
                realm="atlas.primary",
                audience="atlas.internal",
                proof_ttl=timedelta(0),
            )


if __name__ == "__main__":
    unittest.main()
