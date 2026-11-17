"""Persistence contract tests for SQLite Grant renewal requests."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.grant_repository import SQLiteGrantRepository
from atlas.adapters.sqlite.grant_renewal_repository import SQLiteGrantRenewalRepository
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.authorization.models import (
    Grant,
    GrantRenewalRequest,
    GrantResourceScope,
    RenewalStatus,
)
from atlas.core.errors import ConcurrencyError, ContractError


NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


class SQLiteGrantRenewalRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "authority.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.grants = SQLiteGrantRepository(self.database)
        self.repository = SQLiteGrantRenewalRepository(self.database)
        self.grant = Grant(
            grant_id="grant-001",
            owner_user_id="user-001",
            subject_identity_id="agent-001",
            project_id="atlas",
            environment="test",
            resource_scope=GrantResourceScope("workspace", frozenset({"demo"})),
            actions=frozenset({"list", "read"}),
            issued_at=NOW,
            expires_at=NOW + timedelta(days=7),
        )
        self.request = GrantRenewalRequest(
            renewal_id="renewal-001",
            grant_id=self.grant.grant_id,
            owner_user_id=self.grant.owner_user_id,
            subject_identity_id=self.grant.subject_identity_id,
            requested_by_identity_id=self.grant.subject_identity_id,
            current_expires_at=self.grant.expires_at,
            proposed_expires_at=self.grant.expires_at + timedelta(days=7),
            requested_at=NOW,
        )
        self.grants.create(self.grant)

    def test_create_get_and_list_round_trip(self):
        self.repository.create(self.request)
        self.assertEqual(self.repository.get(self.request.renewal_id), self.request)
        self.assertEqual(
            self.repository.list_by_grant(self.grant.grant_id),
            (self.request,),
        )

    def test_duplicate_id_and_missing_parent_grant_are_rejected(self):
        self.repository.create(self.request)
        with self.assertRaises(ContractError):
            self.repository.create(self.request)
        missing_parent = replace(
            self.request,
            renewal_id="renewal-missing-parent",
            grant_id="missing-grant",
        )
        with self.assertRaises(ContractError):
            self.repository.create(missing_parent)

    def test_schema_rejects_partial_agent_authority_evidence(self):
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO authorization_grant_renewals (
                        renewal_id, grant_id, owner_user_id, subject_identity_id,
                        requested_by_identity_id, current_expires_at,
                        proposed_expires_at, requested_at, status, decided_at,
                        decided_by_user_id, version, grant_revision,
                        delegation_id, delegation_revision
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, NULL, 1, ?, NULL, NULL)
                    """,
                    (
                        "renewal-partial-evidence",
                        self.grant.grant_id,
                        self.grant.owner_user_id,
                        self.grant.subject_identity_id,
                        self.grant.subject_identity_id,
                        self.grant.expires_at.isoformat(timespec="microseconds"),
                        (self.grant.expires_at + timedelta(days=1)).isoformat(timespec="microseconds"),
                        NOW.isoformat(timespec="microseconds"),
                        self.grant.revision,
                    ),
                )

    def test_schema_rejects_agent_evidence_without_matching_canonical_delegation(self):
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO authorization_grant_renewals (
                        renewal_id, grant_id, owner_user_id, subject_identity_id,
                        requested_by_identity_id, current_expires_at,
                        proposed_expires_at, requested_at, status, decided_at,
                        decided_by_user_id, version, grant_revision,
                        delegation_id, delegation_revision
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, NULL, 1, ?, ?, ?)
                    """,
                    (
                        "renewal-unbound-evidence",
                        self.grant.grant_id,
                        self.grant.owner_user_id,
                        self.grant.subject_identity_id,
                        self.grant.subject_identity_id,
                        self.grant.expires_at.isoformat(timespec="microseconds"),
                        (self.grant.expires_at + timedelta(days=1)).isoformat(timespec="microseconds"),
                        NOW.isoformat(timespec="microseconds"),
                        self.grant.revision,
                        "22222222-2222-4222-8222-222222222222",
                        1,
                    ),
                )

    def test_update_if_version_is_compare_and_swap(self):
        self.repository.create(self.request)
        approved = replace(
            self.request,
            status=RenewalStatus.APPROVED,
            decided_at=NOW + timedelta(hours=1),
            decided_by_user_id="user-001",
            version=2,
        )
        self.assertTrue(self.repository.update_if_version(approved, 1))
        self.assertFalse(self.repository.update_if_version(approved, 1))
        self.assertEqual(self.repository.get(self.request.renewal_id), approved)

    def test_update_uses_next_version_and_reports_stale_write(self):
        self.repository.create(self.request)
        rejected = replace(
            self.request,
            status=RenewalStatus.REJECTED,
            decided_at=NOW + timedelta(hours=1),
            decided_by_user_id="user-001",
            version=2,
        )
        self.repository.update(rejected)
        with self.assertRaises(ConcurrencyError):
            self.repository.update(rejected)

    def test_database_rejects_binding_changes_and_reopening_decision(self):
        self.repository.create(self.request)
        approved = replace(
            self.request,
            status=RenewalStatus.APPROVED,
            decided_at=NOW + timedelta(hours=1),
            decided_by_user_id="user-001",
            version=2,
        )
        self.repository.update(approved)
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    UPDATE authorization_grant_renewals
                    SET status = 'pending', decided_at = NULL,
                        decided_by_user_id = NULL, version = 3
                    WHERE renewal_id = ?
                    """,
                    (self.request.renewal_id,),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    UPDATE authorization_grant_renewals
                    SET proposed_expires_at = ?, version = 3
                    WHERE renewal_id = ?
                    """,
                    (
                        (self.request.proposed_expires_at + timedelta(days=1)).isoformat(),
                        self.request.renewal_id,
                    ),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM authorization_grant_renewals WHERE renewal_id = ?",
                    (self.request.renewal_id,),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    UPDATE authorization_grant_renewals
                    SET decided_by_user_id = 'other-user', version = 3
                    WHERE renewal_id = ?
                    """,
                    (self.request.renewal_id,),
                )
        self.assertEqual(self.repository.get(self.request.renewal_id), approved)


if __name__ == "__main__":
    unittest.main()
