"""Atomicity tests for the SQLite Grant + renewal unit of work."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.authorization_unit_of_work import (
    SQLiteAuthorizationUnitOfWorkFactory,
)
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.authorization.grant_management import GrantManagementService
from atlas.authorization.renewal_service import GrantRenewalService
from atlas.core.context import OperationContext
from atlas.core.enums import DelegationMode
from atlas.core.identity import Identity, IdentityKind, IdentityStatus
from atlas.authorization.models import (
    Grant,
    GrantRenewalRequest,
    GrantResourceScope,
    RenewalStatus,
)
from atlas.core.errors import ContractError


NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


class SQLiteAuthorizationUnitOfWorkTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "authority.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.factory = SQLiteAuthorizationUnitOfWorkFactory(self.database)
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
        self.renewal = GrantRenewalRequest(
            renewal_id="renewal-001",
            grant_id=self.grant.grant_id,
            owner_user_id=self.grant.owner_user_id,
            subject_identity_id=self.grant.subject_identity_id,
            requested_by_identity_id=self.grant.subject_identity_id,
            current_expires_at=self.grant.expires_at,
            proposed_expires_at=self.grant.expires_at + timedelta(days=7),
            requested_at=NOW,
        )

    def test_grant_and_renewal_share_exact_transaction_connection(self):
        with self.factory() as uow:
            grant_connection = uow.grants._unit_of_work._connection_for(self.database)
            renewal_connection = uow.renewals._unit_of_work._connection_for(self.database)
            self.assertIs(grant_connection, renewal_connection)
            uow.grants.create(self.grant)
            uow.renewals.create(self.renewal)
            uow.commit()

        with self.database.connection() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM authorization_grants").fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM authorization_grant_renewals").fetchone()[0],
                1,
            )

    def test_leaving_without_explicit_commit_rolls_back_both_repositories(self):
        with self.factory() as uow:
            uow.grants.create(self.grant)
            uow.renewals.create(self.renewal)

        self.assertIsNone(self.factory().grants.get(self.grant.grant_id))
        self.assertIsNone(self.factory().renewals.get(self.renewal.renewal_id))

    def test_exception_rolls_back_grant_and_renewal_together(self):
        with self.assertRaises(RuntimeError):
            with self.factory() as uow:
                uow.grants.create(self.grant)
                uow.renewals.create(self.renewal)
                raise RuntimeError("injected failure")

        self.assertIsNone(self.factory().grants.get(self.grant.grant_id))
        self.assertIsNone(self.factory().renewals.get(self.renewal.renewal_id))

    def test_renewal_decision_cas_and_grant_update_commit_atomically(self):
        with self.factory() as uow:
            uow.grants.create(self.grant)
            uow.renewals.create(self.renewal)
            uow.commit()

        approved_grant = replace(
            self.grant,
            expires_at=self.renewal.proposed_expires_at,
            revision=2,
        )
        approved_renewal = replace(
            self.renewal,
            status=RenewalStatus.APPROVED,
            decided_at=NOW + timedelta(hours=1),
            decided_by_user_id="user-001",
            version=2,
        )
        with self.factory() as uow:
            uow.grants.update(approved_grant)
            self.assertTrue(uow.renewals.update_if_version(approved_renewal, 1))
            uow.commit()

        self.assertEqual(self.factory().grants.get(self.grant.grant_id), approved_grant)
        self.assertEqual(
            self.factory().renewals.get(self.renewal.renewal_id),
            approved_renewal,
        )

    def test_stale_renewal_version_does_not_commit_grant_extension(self):
        with self.factory() as uow:
            uow.grants.create(self.grant)
            uow.renewals.create(self.renewal)
            uow.commit()

        approved_grant = replace(
            self.grant,
            expires_at=self.renewal.proposed_expires_at,
            revision=2,
        )
        approved_renewal = replace(
            self.renewal,
            status=RenewalStatus.APPROVED,
            decided_at=NOW + timedelta(hours=1),
            decided_by_user_id="user-001",
            version=2,
        )
        with self.factory() as uow:
            uow.grants.update(approved_grant)
            self.assertFalse(uow.renewals.update_if_version(approved_renewal, 9))
            # No commit: the Grant extension must be rolled back.

        self.assertEqual(self.factory().grants.get(self.grant.grant_id), self.grant)
        self.assertEqual(
            self.factory().renewals.get(self.renewal.renewal_id),
            self.renewal,
        )

    def test_grant_issue_service_uses_atomic_shared_unit_of_work(self):
        actor = Identity(
            identity_id="user-001",
            kind=IdentityKind.USER,
            status=IdentityStatus.ACTIVE,
        )
        context = OperationContext(
            request_id="request-issue",
            correlation_id="correlation-issue",
            actor=actor,
            user_id="user-001",
            origin="unit-test",
            delegation=None,
            project_id="atlas",
            environment="test",
            purpose="issue grant",
            classification="internal",
            created_at=NOW,
        )
        service = GrantManagementService(
            SQLiteGrantRepository(self.database),
            unit_of_work_factory=self.factory,
        )
        self.assertEqual(service.issue(context, self.grant, NOW), self.grant)
        with self.assertRaises(ContractError):
            service.issue(context, self.grant, NOW)
        self.assertEqual(self.factory().grants.get(self.grant.grant_id), self.grant)

    def test_grant_renewal_service_runs_on_sqlite_unit_of_work(self):
        with self.factory() as uow:
            uow.grants.create(self.grant)
            uow.commit()

        agent = Identity(
            identity_id="agent-001",
            kind=IdentityKind.AGENT,
            status=IdentityStatus.ACTIVE,
        )
        subject_context = OperationContext(
            request_id="request-renew",
            correlation_id="correlation-renew",
            actor=agent,
            user_id="user-001",
            origin="unit-test",
            delegation=DelegationMode.DELEGATED,
            project_id="atlas",
            environment="test",
            purpose="renew grant",
            classification="internal",
            created_at=NOW,
        )
        service = GrantRenewalService(self.factory)
        request = service.request_renewal(
            subject_context,
            "renewal-service",
            self.grant.grant_id,
            self.grant.expires_at + timedelta(days=7),
            NOW + timedelta(hours=1),
        )
        owner = Identity(
            identity_id="user-001",
            kind=IdentityKind.USER,
            status=IdentityStatus.ACTIVE,
        )
        owner_context = replace(
            subject_context,
            actor=owner,
            delegation=None,
            request_id="request-approve",
        )
        updated = service.approve_renewal(
            owner_context,
            request.renewal_id,
            NOW + timedelta(hours=2),
        )
        self.assertEqual(updated.revision, 2)
        self.assertEqual(updated.expires_at, request.proposed_expires_at)
        self.assertEqual(
            self.factory().renewals.get(request.renewal_id).status,
            RenewalStatus.APPROVED,
        )

    def test_repository_cannot_use_unit_of_work_after_context(self):
        with self.factory() as uow:
            repository = uow.grants
            uow.commit()
        with self.assertRaises(ContractError):
            repository.get(self.grant.grant_id)


if __name__ == "__main__":
    unittest.main()
