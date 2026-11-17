from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.identity_authority import SQLiteIdentityAuthority
from atlas.adapters.sqlite.native_identity_authority import SQLiteNativeIdentityAuthority
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.core.errors import (
    ConcurrencyError,
    ContractError,
    IdentityConflictError,
    NotFoundError,
)
from atlas.core.identity import IdentityStatus


class SQLiteNativeIdentityAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "native-identity.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.identity_authority = SQLiteIdentityAuthority(self.database)
        self.authority = SQLiteNativeIdentityAuthority(self.database)
        self.user = self.identity_authority.create_user()
        self.issuer = self.authority.create_native_issuer("atlas.primary")

    def _verified_at(self):
        return datetime.now(timezone.utc)

    def _binding(self, *, identity=None, digest="a" * 64, verified_at=None):
        return self.authority.create_native_binding(
            self.user if identity is None else identity,
            self.issuer.issuer_id,
            digest,
            verified_at=self._verified_at() if verified_at is None else verified_at,
        )

    def test_create_and_resolve_stable_native_issuer(self):
        self.assertEqual(self.authority.get_native_issuer("atlas.primary"), self.issuer)
        self.assertEqual(self.issuer.profile.value, "NATIVE_AUTHORITY_PROOF")
        self.assertEqual(self.issuer.status.value, "ACTIVE")

    def test_issuer_realm_is_unique_and_never_replaced(self):
        with self.assertRaises(IdentityConflictError):
            self.authority.create_native_issuer("atlas.primary")
        self.assertEqual(self.authority.get_native_issuer("atlas.primary"), self.issuer)

    def test_rejects_invalid_realm(self):
        for realm in ("Atlas", "x", "host:atlas", "../atlas", "ñative"):
            with self.subTest(realm=realm):
                with self.assertRaises(ContractError):
                    self.authority.get_native_issuer(realm)

    def test_create_and_resolve_active_binding(self):
        binding = self._binding()
        self.assertEqual(
            self.authority.get_native_binding(self.issuer.issuer_id, "a" * 64),
            binding,
        )
        self.assertEqual(
            self.authority.get_native_binding_by_id(binding.binding_id),
            binding,
        )
        self.assertIsNone(
            self.authority.get_native_binding_by_id(
                "ffffffff-ffff-4fff-8fff-ffffffffffff"
            )
        )
        self.assertEqual(binding.identity_id, self.user.identity.identity_id)

    def test_duplicate_subject_digest_is_never_reassigned(self):
        self._binding()
        other_user = self.identity_authority.create_user()
        with self.assertRaises(IdentityConflictError):
            self._binding(identity=other_user)

    def test_binding_requires_existing_matching_active_canonical_user(self):
        other_user = self.identity_authority.create_user()
        mismatched = type(self.user)(
            user_id=self.user.user_id,
            identity=other_user.identity,
        )
        with self.assertRaises(IdentityConflictError):
            self._binding(identity=mismatched)

        from atlas.core.identity import Identity
        stale = type(self.user)(
            user_id=self.user.user_id,
            identity=Identity(
                identity_id=self.user.identity.identity_id,
                kind=self.user.identity.kind,
                status=IdentityStatus.SUSPENDED,
                revision=self.user.identity.revision + 1,
            ),
        )
        with self.assertRaises(ConcurrencyError):
            self._binding(identity=stale, digest="f" * 64)

        suspended = self.identity_authority.update_user_status(
            self.user.user_id,
            expected_revision=1,
            status=IdentityStatus.SUSPENDED,
        )
        with self.assertRaises(ContractError):
            self._binding(identity=suspended, digest="b" * 64)

        with self.assertRaises(NotFoundError):
            self.authority.create_native_binding(
                other_user,
                "ffffffff-ffff-4fff-8fff-ffffffffffff",
                "c" * 64,
                verified_at=self._verified_at(),
            )

    def test_revocation_uses_cas_and_retains_terminal_tombstone(self):
        binding = self._binding()
        revoked_at = self._verified_at() + timedelta(seconds=1)
        revoked = self.authority.revoke_native_binding(
            binding.binding_id,
            expected_revision=1,
            revoked_at=revoked_at,
        )
        self.assertEqual(revoked.revision, 2)
        self.assertEqual(revoked.status.value, "REVOKED")
        self.assertEqual(
            self.authority.get_native_binding(self.issuer.issuer_id, "a" * 64),
            revoked,
        )
        with self.assertRaises(ConcurrencyError):
            self.authority.revoke_native_binding(
                binding.binding_id,
                expected_revision=1,
                revoked_at=revoked_at + timedelta(seconds=1),
            )
        with self.assertRaises(IdentityConflictError):
            self._binding(digest="a" * 64, verified_at=revoked_at + timedelta(seconds=1))

    def test_revoked_binding_cannot_be_reactivated_or_deleted_by_sql(self):
        binding = self._binding()
        revoked_at = self._verified_at() + timedelta(seconds=1)
        self.authority.revoke_native_binding(
            binding.binding_id,
            expected_revision=1,
            revoked_at=revoked_at,
        )
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    UPDATE native_identity_bindings
                    SET status = 'ACTIVE', revision = 3, revoked_at = NULL
                    WHERE binding_id = ?
                    """,
                    (binding.binding_id,),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM native_identity_bindings WHERE binding_id = ?",
                    (binding.binding_id,),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE native_identity_bindings SET identity_id = ? WHERE binding_id = ?",
                    (self.identity_authority.create_user().identity.identity_id, binding.binding_id),
                )

    def test_shared_local_authority_unit_commits_or_rolls_back_issuer_and_binding(self):
        from atlas.adapters.sqlite.local_authority_unit_of_work import (
            SQLiteLocalAuthorityUnitOfWorkFactory,
        )

        factory = SQLiteLocalAuthorityUnitOfWorkFactory(self.database)
        user = self.identity_authority.create_user()
        issuer_id = None
        binding_id = None
        with factory() as unit:
            self.assertIs(unit.native_identity._unit_of_work, unit._unit)
            issuer = unit.native_identity.create_native_issuer("atlas.transactional")
            issuer_id = issuer.issuer_id
            binding = unit.native_identity.create_native_binding(
                user,
                issuer.issuer_id,
                "d" * 64,
                verified_at=self._verified_at(),
            )
            binding_id = binding.binding_id
            unit.commit()
        self.assertIsNotNone(
            self.authority.get_native_issuer("atlas.transactional")
        )
        self.assertIsNotNone(
            self.authority.get_native_binding(issuer_id, "d" * 64)
        )

        with self.assertRaisesRegex(RuntimeError, "rollback native authority"):
            with factory() as unit:
                rollback_issuer = unit.native_identity.create_native_issuer(
                    "atlas.rollback"
                )
                unit.native_identity.create_native_binding(
                    user,
                    rollback_issuer.issuer_id,
                    "e" * 64,
                    verified_at=self._verified_at(),
                )
                raise RuntimeError("rollback native authority")
        self.assertIsNone(self.authority.get_native_issuer("atlas.rollback"))
        self.assertIsNone(
            self.authority.get_native_binding(
                rollback_issuer.issuer_id,
                "e" * 64,
            )
        )


if __name__ == "__main__":
    unittest.main()
