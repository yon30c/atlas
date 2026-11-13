
from collections import UserDict
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from atlas.authorization.models import (
    Grant,
    GrantRenewalRequest,
    RenewalStatus,
    GrantResourceScope,
)
from atlas.core.errors import ConcurrencyError
from tests.fakes.authorization_unit_of_work import (
    InMemoryAuthorizationUnitOfWorkFactory,
)


NOW = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)


class AuthorizationUnitOfWorkTests(unittest.TestCase):

    def setUp(self) -> None:
        self.factory = InMemoryAuthorizationUnitOfWorkFactory()

        self.grant = Grant(
            grant_id="grant-001",
            owner_user_id="user-001",
            subject_identity_id="agent-001",
            project_id="atlas",
            environment="development",
            resource_scope=GrantResourceScope("files", frozenset({"file-001"})),
            actions=frozenset({"read"}),
            issued_at=NOW - timedelta(days=1),
            expires_at=NOW + timedelta(days=2),
        )

        self.request = GrantRenewalRequest(
            renewal_id="renewal-001",
            grant_id="grant-001",
            owner_user_id="user-001",
            subject_identity_id="agent-001",
            requested_by_identity_id="agent-001",
            current_expires_at=self.grant.expires_at,
            proposed_expires_at=NOW + timedelta(days=9),
            requested_at=NOW,
            status=RenewalStatus.PENDING,
        )

        self.factory.grants.create(self.grant)
        self.factory.renewals.create(self.request)

    def test_commit_preserves_changes_in_both_repositories(self) -> None:
        updated_grant = replace(
            self.grant,
            expires_at=self.request.proposed_expires_at,
        )

        updated_request = replace(
            self.request,
            status=RenewalStatus.APPROVED,
            decided_at=NOW + timedelta(hours=1),
            decided_by_user_id="user-001",
        )

        with self.factory() as uow:
            uow.grants.update(updated_grant)
            uow.renewals.update(updated_request)
            uow.commit()

        self.assertEqual(
            self.factory.grants.get("grant-001"),
            updated_grant,
        )
        self.assertEqual(
            self.factory.renewals.get("renewal-001"),
            updated_request,
        )

    def test_exit_without_commit_rolls_back_both_repositories(self) -> None:
        updated_grant = replace(
            self.grant,
            expires_at=self.request.proposed_expires_at,
        )

        with self.factory() as uow:
            uow.grants.update(updated_grant)

        self.assertEqual(
            self.factory.grants.get("grant-001"),
            self.grant,
        )
        self.assertEqual(
            self.factory.renewals.get("renewal-001"),
            self.request,
        )

    def test_exception_rolls_back_both_repositories(self) -> None:
        updated_grant = replace(
            self.grant,
            expires_at=self.request.proposed_expires_at,
        )

        with self.assertRaises(RuntimeError):
            with self.factory() as uow:
                uow.grants.update(updated_grant)
                raise RuntimeError("Simulated failure")

        self.assertEqual(
            self.factory.grants.get("grant-001"),
            self.grant,
        )
        self.assertEqual(
            self.factory.renewals.get("renewal-001"),
            self.request,
        )

    def test_failure_updating_renewal_rolls_back_grant(self) -> None:
        updated_grant = replace(
            self.grant,
            expires_at=self.request.proposed_expires_at,
        )

        updated_request = replace(
            self.request,
            status=RenewalStatus.APPROVED,
            decided_at=NOW + timedelta(hours=1),
            decided_by_user_id="user-001",
        )

        self.factory.renewals.fail_on_update = True

        with self.assertRaises(RuntimeError):
            with self.factory() as uow:
                uow.grants.update(updated_grant)
                uow.renewals.update(updated_request)
                uow.commit()

        self.assertEqual(
            self.factory.grants.get("grant-001"),
            self.grant,
        )
        self.assertEqual(
            self.factory.renewals.get("renewal-001"),
            self.request,
        )


    def test_commit_preparation_failure_preserves_both_repositories(self) -> None:
        updated_grant = replace(
            self.grant,
            expires_at=self.request.proposed_expires_at,
        )

        updated_request = replace(
            self.request,
            status=RenewalStatus.APPROVED,
            decided_at=NOW + timedelta(hours=1),
            decided_by_user_id="user-001",
        )
        original_requests = self.factory.renewals.requests

        class FailingMapping(UserDict):
            def __iter__(self):
                raise RuntimeError("Fallo simulado durante la preparación")

        self.factory.renewals.requests = FailingMapping(original_requests)
        try:
            with self.assertRaises(RuntimeError):
                with self.factory() as uow:
                    uow.grants.update(updated_grant)
                    uow.renewals.update(updated_request)
                    uow.commit()
        finally:
            self.factory.renewals.requests = original_requests

        self.assertEqual(
            self.factory.grants.get("grant-001"),
            self.grant,
        )
        self.assertEqual(
            self.factory.renewals.get("renewal-001"),
            self.request,
        )


    def test_concurrent_updates_only_allow_one_commit(self) -> None:
        first_grant = replace(
            self.grant,
            expires_at=NOW + timedelta(days=10),
        )
        second_grant = replace(
            self.grant,
            expires_at=NOW + timedelta(days=11),
        )
        first_request = replace(
            self.request,
            status=RenewalStatus.APPROVED,
            decided_at=NOW,
            decided_by_user_id="user-001",
            version=2,
        )
        second_request = replace(
            self.request,
            status=RenewalStatus.REJECTED,
            decided_at=NOW,
            decided_by_user_id="user-001",
            version=2,
        )
        with self.factory() as first_uow:
            with self.factory() as second_uow:
                self.assertTrue(
                    first_uow.renewals.update_if_version(
                        first_request,
                        expected_version=1,
                    )
                )
                self.assertTrue(
                    second_uow.renewals.update_if_version(
                        second_request,
                        expected_version=1,
                    )
                )
                first_uow.grants.update(first_grant)
                second_uow.grants.update(second_grant)
                first_uow.commit()
                with self.assertRaises(ConcurrencyError):
                    second_uow.commit()
        self.assertEqual(
            self.factory.grants.get("grant-001"),
            first_grant,
        )
        self.assertEqual(
            self.factory.renewals.get("renewal-001"),
            first_request,
        )

    def test_rollback_does_not_overwrite_another_committed_transaction(self) -> None:
        committed_grant = replace(
            self.grant,
            expires_at=NOW + timedelta(days=10),
        )
        uncommitted_grant = replace(
            self.grant,
            expires_at=NOW + timedelta(days=20),
        )
        with self.factory() as first_uow:
            with self.factory() as second_uow:
                first_uow.grants.update(committed_grant)
                second_uow.grants.update(uncommitted_grant)
                first_uow.commit()
                # La segunda transacción sale sin commit.
                # Su rollback no debe restaurar un snapshot antiguo.
        self.assertEqual(
            self.factory.grants.get("grant-001"),
            committed_grant,
        )


if __name__ == "__main__":
    unittest.main()
