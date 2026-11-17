"""Tests for native issuer bindings to canonical AGENT identities."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from atlas.adapters.sqlite import (
    SQLiteDatabase,
    SQLITE_MIGRATIONS,
)
from atlas.adapters.sqlite.agent_identity_authority import SQLiteAgentIdentityAuthority
from atlas.adapters.sqlite.identity_authority import SQLiteIdentityAuthority
from atlas.adapters.sqlite.native_agent_identity_authority import (
    SQLiteNativeAgentIdentityAuthority,
)
from atlas.adapters.sqlite.native_identity_authority import SQLiteNativeIdentityAuthority
from atlas.core.errors import (
    ConcurrencyError,
    ContractError,
    IdentityConflictError,
)
from atlas.core.identity import IdentityStatus


class SQLiteNativeAgentIdentityAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "atlas.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.agents = SQLiteAgentIdentityAuthority(self.database)
        self.users = SQLiteIdentityAuthority(self.database)
        self.native_users = SQLiteNativeIdentityAuthority(self.database)
        self.native_agents = SQLiteNativeAgentIdentityAuthority(self.database)
        self.issuer = self.native_users.create_native_issuer("atlas.agent.test")
        self.now = datetime.now(timezone.utc)
        self.digest = "a" * 64

    def test_create_and_resolve_native_agent_binding(self):
        agent = self.agents.create_agent()
        binding = self.native_agents.create_native_agent_binding(
            agent, self.issuer.issuer_id, self.digest, verified_at=self.now
        )
        self.assertEqual(binding.identity_id, agent.identity.identity_id)
        self.assertEqual(binding.issuer_id, self.issuer.issuer_id)
        self.assertEqual(binding.status.value, "active")
        self.assertEqual(binding.revision, 1)
        self.assertEqual(
            self.native_agents.get_native_agent_binding(
                self.issuer.issuer_id, self.digest
            ),
            binding,
        )
        self.assertEqual(
            self.native_agents.get_native_agent_binding_by_id(binding.binding_id),
            binding,
        )

    def test_user_identity_cannot_be_bound_through_agent_authority(self):
        user = self.users.create_user()
        with self.assertRaises(ContractError):
            self.native_agents.create_native_agent_binding(
                user, self.issuer.issuer_id, self.digest, verified_at=self.now
            )
        self.assertIsNone(
            self.native_agents.get_native_agent_binding(
                self.issuer.issuer_id, self.digest
            )
        )

    def test_suspended_agent_cannot_receive_native_binding(self):
        agent = self.agents.create_agent()
        self.agents.update_agent_status(
            agent.identity.identity_id,
            expected_revision=1,
            status=IdentityStatus.SUSPENDED,
        )
        with self.assertRaises(ConcurrencyError):
            self.native_agents.create_native_agent_binding(
                agent, self.issuer.issuer_id, self.digest, verified_at=self.now
            )

    def test_duplicate_subject_is_rejected_without_reassignment(self):
        first = self.agents.create_agent()
        second = self.agents.create_agent()
        binding = self.native_agents.create_native_agent_binding(
            first, self.issuer.issuer_id, self.digest, verified_at=self.now
        )
        with self.assertRaises(IdentityConflictError):
            self.native_agents.create_native_agent_binding(
                second, self.issuer.issuer_id, self.digest, verified_at=self.now
            )
        self.assertEqual(
            self.native_agents.get_native_agent_binding_by_id(binding.binding_id),
            binding,
        )

    def test_native_subject_cannot_be_bound_to_both_user_and_agent(self):
        user = self.users.create_user()
        self.native_users.create_native_binding(
            user, self.issuer.issuer_id, self.digest, verified_at=self.now
        )
        agent = self.agents.create_agent()
        with self.assertRaises(IdentityConflictError):
            self.native_agents.create_native_agent_binding(
                agent, self.issuer.issuer_id, self.digest, verified_at=self.now
            )

    def test_agent_subject_cannot_be_rebound_to_user(self):
        agent = self.agents.create_agent()
        self.native_agents.create_native_agent_binding(
            agent, self.issuer.issuer_id, self.digest, verified_at=self.now
        )
        user = self.users.create_user()
        with self.assertRaises(IdentityConflictError):
            self.native_users.create_native_binding(
                user, self.issuer.issuer_id, self.digest, verified_at=self.now
            )

    def test_revocation_uses_cas_and_is_terminal(self):
        agent = self.agents.create_agent()
        binding = self.native_agents.create_native_agent_binding(
            agent, self.issuer.issuer_id, self.digest, verified_at=self.now
        )
        revoked = self.native_agents.revoke_native_agent_binding(
            binding.binding_id,
            expected_revision=1,
            revoked_at=self.now + timedelta(seconds=1),
        )
        self.assertEqual(revoked.status.value, "revoked")
        self.assertEqual(revoked.revision, 2)
        with self.assertRaises(ConcurrencyError):
            self.native_agents.revoke_native_agent_binding(
                binding.binding_id,
                expected_revision=1,
                revoked_at=self.now + timedelta(seconds=2),
            )
        self.assertEqual(
            self.native_agents.get_native_agent_binding_by_id(binding.binding_id),
            revoked,
        )

    def test_unknown_binding_and_invalid_inputs_fail_closed(self):
        self.assertIsNone(
            self.native_agents.get_native_agent_binding_by_id(
                "11111111-1111-4111-8111-111111111111"
            )
        )
        with self.assertRaises(ContractError):
            self.native_agents.get_native_agent_binding(self.issuer.issuer_id, "bad")
        agent = self.agents.create_agent()
        with self.assertRaises(ContractError):
            self.native_agents.create_native_agent_binding(
                agent,
                self.issuer.issuer_id,
                self.digest,
                verified_at=self.now.astimezone(timezone(timedelta(hours=1))),
            )


if __name__ == "__main__":
    unittest.main()
