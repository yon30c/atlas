"""Tests for canonical Identity(AGENT) SQLite persistence."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import UUID

from atlas.adapters.sqlite import SQLiteDatabase, SQLITE_MIGRATIONS
from atlas.adapters.sqlite.agent_identity_authority import SQLiteAgentIdentityAuthority
from atlas.adapters.sqlite.identity_authority import SQLiteIdentityAuthority
from atlas.core.errors import (
    ConcurrencyError,
    ContractError,
    IdentityConflictError,
    NotFoundError,
)
from atlas.core.identity import IdentityStatus


class SQLiteAgentIdentityAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "atlas.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.authority = SQLiteAgentIdentityAuthority(self.database)
        self.users = SQLiteIdentityAuthority(self.database)

    def test_create_agent_generates_canonical_uuid4_without_user_id(self):
        agent = self.authority.create_agent()
        self.assertEqual(agent.identity.kind.value, "agent")
        self.assertEqual(agent.identity.status, IdentityStatus.ACTIVE)
        self.assertEqual(agent.identity.revision, 1)
        self.assertEqual(str(UUID(agent.identity.identity_id)), agent.identity.identity_id)
        self.assertEqual(UUID(agent.identity.identity_id).version, 4)
        self.assertEqual(
            self.authority.get_agent_by_identity_id(agent.identity.identity_id), agent
        )
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT user_id FROM identity_records WHERE identity_id = ?",
                (agent.identity.identity_id,),
            ).fetchone()
            self.assertIsNone(row["user_id"])
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM atlas_users").fetchone()[0], 0
            )

    def test_agent_lookup_never_resolves_user_identity(self):
        user = self.users.create_user()
        self.assertIsNone(
            self.authority.get_agent_by_identity_id(user.identity.identity_id)
        )
        self.assertEqual(self.users.get_user(user.user_id), user)

    def test_agent_lookup_returns_none_for_unknown_identity(self):
        self.assertIsNone(
            self.authority.get_agent_by_identity_id(
                "11111111-1111-4111-8111-111111111111"
            )
        )

    def test_invalid_identity_uuid_is_rejected(self):
        with self.assertRaises(ContractError):
            self.authority.get_agent_by_identity_id("not-a-uuid")

    def test_duplicate_agent_identity_is_rejected_without_replacement(self):
        identity_ids = [
            UUID("11111111-1111-4111-8111-111111111111"),
            UUID("11111111-1111-4111-8111-111111111111"),
        ]
        with patch(
            "atlas.adapters.sqlite.agent_identity_authority.uuid4",
            side_effect=identity_ids,
        ):
            first = self.authority.create_agent()
            with self.assertRaises(IdentityConflictError):
                self.authority.create_agent()
        with self.database.connection() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM identity_records WHERE identity_kind = 'agent'"
                ).fetchone()[0],
                1,
            )
        self.assertEqual(
            self.authority.get_agent_by_identity_id(first.identity.identity_id), first
        )

    def test_status_update_uses_compare_and_swap_revision(self):
        agent = self.authority.create_agent()
        updated = self.authority.update_agent_status(
            agent.identity.identity_id,
            expected_revision=1,
            status=IdentityStatus.SUSPENDED,
        )
        self.assertEqual(updated.identity.status, IdentityStatus.SUSPENDED)
        self.assertEqual(updated.identity.revision, 2)
        with self.assertRaises(ConcurrencyError):
            self.authority.update_agent_status(
                agent.identity.identity_id,
                expected_revision=1,
                status=IdentityStatus.ACTIVE,
            )
        self.assertEqual(
            self.authority.get_agent_by_identity_id(agent.identity.identity_id), updated
        )

    def test_revoked_agent_identity_is_terminal(self):
        agent = self.authority.create_agent()
        revoked = self.authority.update_agent_status(
            agent.identity.identity_id,
            expected_revision=1,
            status=IdentityStatus.REVOKED,
        )
        with self.assertRaises(ContractError):
            self.authority.update_agent_status(
                agent.identity.identity_id,
                expected_revision=2,
                status=IdentityStatus.ACTIVE,
            )
        self.assertEqual(
            self.authority.get_agent_by_identity_id(agent.identity.identity_id), revoked
        )

    def test_unknown_agent_status_update_fails_closed(self):
        with self.assertRaises(NotFoundError):
            self.authority.update_agent_status(
                "22222222-2222-4222-8222-222222222222",
                expected_revision=1,
                status=IdentityStatus.SUSPENDED,
            )

    def test_invalid_revision_and_status_are_rejected(self):
        agent = self.authority.create_agent()
        with self.assertRaises(ContractError):
            self.authority.update_agent_status(
                agent.identity.identity_id,
                expected_revision=True,
                status=IdentityStatus.SUSPENDED,
            )
        with self.assertRaises(ContractError):
            self.authority.update_agent_status(
                agent.identity.identity_id,
                expected_revision=1,
                status="suspended",
            )

    def test_concurrent_updates_allow_only_one_expected_revision(self):
        agent = self.authority.create_agent()
        barrier = threading.Barrier(2)

        def update(status):
            barrier.wait(timeout=5)
            try:
                return self.authority.update_agent_status(
                    agent.identity.identity_id,
                    expected_revision=1,
                    status=status,
                )
            except ConcurrencyError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(update, (IdentityStatus.SUSPENDED, IdentityStatus.REVOKED))
            )
        self.assertEqual(sum(result is not None for result in results), 1)
        persisted = self.authority.get_agent_by_identity_id(agent.identity.identity_id)
        self.assertEqual(persisted.identity.revision, 2)

    def test_create_agent_participates_in_supplied_unit_of_work(self):
        with self.database.unit_of_work() as unit:
            authority = SQLiteAgentIdentityAuthority(
                self.database, unit_of_work=unit
            )
            agent = authority.create_agent()
            self.assertEqual(
                authority.get_agent_by_identity_id(agent.identity.identity_id), agent
            )
        self.assertEqual(
            self.authority.get_agent_by_identity_id(agent.identity.identity_id), agent
        )


if __name__ == "__main__":
    unittest.main()
