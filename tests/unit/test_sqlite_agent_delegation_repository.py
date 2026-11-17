"""Tests for canonical AGENT delegation persistence and revocation."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4

from atlas.adapters.sqlite import (
    SQLiteAgentDelegationRepository,
    SQLiteAgentIdentityAuthority,
    SQLiteDatabase,
    SQLiteGrantRepository,
    SQLiteIdentityAuthority,
    SQLiteNativeAgentIdentityAuthority,
    SQLiteNativeIdentityAuthority,
    SQLITE_MIGRATIONS,
)
from atlas.authorization.models import Grant, GrantResourceScope
from atlas.core.agent_delegation import (
    AgentDelegation,
    AgentDelegationScope,
    AgentDelegationStatus,
)
from atlas.core.errors import ConcurrencyError, ContractError, NotFoundError


class SQLiteAgentDelegationRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "atlas.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.users = SQLiteIdentityAuthority(self.database)
        self.agents = SQLiteAgentIdentityAuthority(self.database)
        self.native_users = SQLiteNativeIdentityAuthority(self.database)
        self.native_agents = SQLiteNativeAgentIdentityAuthority(self.database)
        self.grants = SQLiteGrantRepository(self.database)
        self.repository = SQLiteAgentDelegationRepository(self.database)

        self.owner = self.users.create_user()
        self.agent = self.agents.create_agent()
        self.issuer = self.native_users.create_native_issuer("atlas.agent.delegation")
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.native_agents.create_native_agent_binding(
            self.agent, self.issuer.issuer_id, "b" * 64,
            verified_at=self.now,
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
            issued_at=self.now - timedelta(minutes=5),
            expires_at=self.now + timedelta(days=3),
        )
        self.grants.create(self.grant)

    def _delegation(self, **changes):
        delegation = AgentDelegation(
            delegation_id=str(uuid4()),
            owner_user_id=self.owner.user_id,
            owner_identity_id=self.owner.identity.identity_id,
            agent_identity_id=self.agent.identity.identity_id,
            grant_id=self.grant.grant_id,
            grant_revision=self.grant.revision,
            project_id=self.grant.project_id,
            environment=self.grant.environment,
            scope=AgentDelegationScope(
                resource_type="workspace",
                resource_ids=frozenset({"workspace-a"}),
                actions=frozenset({"read"}),
            ),
            issuer_id=self.issuer.issuer_id,
            issued_at=self.now,
            not_before=self.now,
            expires_at=self.now + timedelta(days=1),
            created_by_user_identity_id=self.owner.identity.identity_id,
        )
        return replace(delegation, **changes) if changes else delegation

    def test_create_and_get_round_trip_canonical_delegation(self):
        delegation = self._delegation()
        self.repository.create(delegation)
        self.assertEqual(self.repository.get(delegation.delegation_id), delegation)
        self.assertEqual(
            self.repository.list_by_grant(self.grant.grant_id), (delegation,)
        )

    def test_scope_must_be_subset_of_exact_grant(self):
        too_wide_resource = self._delegation(
            scope=AgentDelegationScope(
                "workspace", frozenset({"workspace-c"}), frozenset({"read"})
            )
        )
        with self.assertRaises(ContractError):
            self.repository.create(too_wide_resource)

        too_wide_action = self._delegation(
            scope=AgentDelegationScope(
                "workspace", frozenset({"workspace-a"}), frozenset({"delete"})
            )
        )
        with self.assertRaises(ContractError):
            self.repository.create(too_wide_action)

    def test_owner_agent_project_grant_revision_and_issuer_are_bound(self):
        wrong_owner = self._delegation(owner_user_id=str(uuid4()))
        with self.assertRaises(ContractError):
            self.repository.create(wrong_owner)

        wrong_agent = self._delegation(agent_identity_id=str(uuid4()))
        with self.assertRaises(ContractError):
            self.repository.create(wrong_agent)

        stale_grant = self._delegation(grant_revision=2)
        with self.assertRaises(ContractError):
            self.repository.create(stale_grant)

        wrong_issuer = self._delegation(issuer_id=str(uuid4()))
        with self.assertRaises(ContractError):
            self.repository.create(wrong_issuer)

    def test_delegation_cannot_outlive_grant(self):
        too_long = self._delegation(expires_at=self.grant.expires_at + timedelta(seconds=1))
        with self.assertRaises(ContractError):
            self.repository.create(too_long)

    def test_revocation_is_auditable_terminal_and_cas_guarded(self):
        delegation = self._delegation()
        self.repository.create(delegation)
        revoked = self.repository.revoke(
            delegation.delegation_id,
            expected_revision=1,
            revoked_at=self.now + timedelta(seconds=1),
            revoked_by_user_id=self.owner.user_id,
        )
        self.assertEqual(revoked.status, AgentDelegationStatus.REVOKED)
        self.assertEqual(revoked.revision, 2)
        self.assertEqual(self.repository.get(delegation.delegation_id), revoked)
        with self.assertRaises(ConcurrencyError):
            self.repository.revoke(
                delegation.delegation_id,
                expected_revision=1,
                revoked_at=self.now + timedelta(seconds=2),
                revoked_by_user_id=self.owner.user_id,
            )
        with self.assertRaises(ContractError):
            self.repository.update(
                replace(
                    revoked,
                    status=AgentDelegationStatus.ACTIVE,
                    revision=3,
                    revoked_at=None,
                    revoked_by_user_id=None,
                )
            )

    def test_missing_delegation_and_invalid_identifiers_fail_closed(self):
        self.assertIsNone(self.repository.get(str(uuid4())))
        with self.assertRaises(ContractError):
            self.repository.get("not-a-uuid")
        with self.assertRaises(NotFoundError):
            self.repository.revoke(
                str(uuid4()),
                expected_revision=1,
                revoked_at=self.now,
                revoked_by_user_id=self.owner.user_id,
            )

    def test_database_prevents_direct_claim_mutation_and_deletion(self):
        delegation = self._delegation()
        self.repository.create(delegation)
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    UPDATE agent_delegations
                    SET agent_identity_id = ?, revision = 2
                    WHERE delegation_id = ?
                    """,
                    (str(uuid4()), delegation.delegation_id),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM agent_delegations WHERE delegation_id = ?",
                    (delegation.delegation_id,),
                )
        self.assertEqual(self.repository.get(delegation.delegation_id), delegation)

    def test_repository_participates_in_supplied_unit_of_work(self):
        with self.database.unit_of_work() as unit:
            repository = SQLiteAgentDelegationRepository(
                self.database, unit_of_work=unit
            )
            delegation = self._delegation()
            repository.create(delegation)
            self.assertEqual(repository.get(delegation.delegation_id), delegation)
        self.assertEqual(
            self.repository.get(delegation.delegation_id), delegation
        )

    def test_supplied_unit_of_work_rolls_back_delegation_write(self):
        delegation = self._delegation()
        with self.assertRaisesRegex(RuntimeError, "rollback delegation"):
            with self.database.unit_of_work() as unit:
                repository = SQLiteAgentDelegationRepository(
                    self.database, unit_of_work=unit
                )
                repository.create(delegation)
                raise RuntimeError("rollback delegation")
        self.assertIsNone(self.repository.get(delegation.delegation_id))


if __name__ == "__main__":
    unittest.main()
