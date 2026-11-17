from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest
from uuid import uuid4

from atlas.core.errors import AuthorizationError, ContractError
from atlas.core.platform_admin import (
    PlatformAdminGrant,
    PlatformAdminGrantStatus,
    PlatformAdminPermission,
    PlatformAdminProvisioningMethod,
    require_platform_admin_permission,
)
from atlas.ports.platform_admin_authority import (
    PlatformAdminAuthorityReaderPort,
    PlatformAdminBootstrapPort,
)


def uid():
    return str(uuid4())


class PlatformAdminDomainContractTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
        self.user_id = uid()
        self.identity_id = uid()
        self.grant = PlatformAdminGrant(
            grant_id=uid(),
            user_id=self.user_id,
            user_identity_id=self.identity_id,
            user_identity_revision=3,
            permissions=frozenset({
                PlatformAdminPermission.ASSOCIATION_SUSPEND,
            }),
            provisioning_method=PlatformAdminProvisioningMethod.OFFLINE_BOOTSTRAP,
            bootstrap_event_id=uid(),
            issued_at=self.now - timedelta(minutes=1),
            not_before=self.now,
            expires_at=self.now + timedelta(days=1),
        )

    def test_exact_permission_is_required(self):
        require_platform_admin_permission(
            self.grant,
            permission=PlatformAdminPermission.ASSOCIATION_SUSPEND,
            user_id=self.user_id,
            user_identity_id=self.identity_id,
            user_identity_revision=3,
            now=self.now,
        )
        with self.assertRaises(AuthorizationError):
            require_platform_admin_permission(
                self.grant,
                permission=PlatformAdminPermission.ASSOCIATION_REACTIVATE,
                user_id=self.user_id,
                user_identity_id=self.identity_id,
                user_identity_revision=3,
                now=self.now,
            )

    def test_user_and_identity_revision_are_bound_exactly(self):
        for changes in (
            {"user_id": uid()},
            {"user_identity_id": uid()},
            {"user_identity_revision": 4},
        ):
            with self.subTest(changes=changes), self.assertRaises(AuthorizationError):
                require_platform_admin_permission(
                    self.grant,
                    permission=PlatformAdminPermission.ASSOCIATION_SUSPEND,
                    user_id=changes.get("user_id", self.user_id),
                    user_identity_id=changes.get("user_identity_id", self.identity_id),
                    user_identity_revision=changes.get("user_identity_revision", 3),
                    now=self.now,
                )

    def test_inactive_revoked_and_expired_grants_fail_closed(self):
        revoked = replace(
            self.grant,
            status=PlatformAdminGrantStatus.REVOKED,
            revision=2,
            revoked_at=self.now,
            revoked_by_user_id=self.user_id,
        )
        expired = replace(
            self.grant,
            issued_at=self.now - timedelta(minutes=2),
            not_before=self.now - timedelta(minutes=1),
            expires_at=self.now,
        )
        for grant in (revoked, expired):
            with self.subTest(grant=grant.status), self.assertRaises(AuthorizationError):
                require_platform_admin_permission(
                    grant,
                    permission=PlatformAdminPermission.ASSOCIATION_SUSPEND,
                    user_id=self.user_id,
                    user_identity_id=self.identity_id,
                    user_identity_revision=3,
                    now=self.now,
                )

    def test_not_before_is_enforced(self):
        with self.assertRaises(AuthorizationError):
            require_platform_admin_permission(
                self.grant,
                permission=PlatformAdminPermission.ASSOCIATION_SUSPEND,
                user_id=self.user_id,
                user_identity_id=self.identity_id,
                user_identity_revision=3,
                now=self.now - timedelta(microseconds=1),
            )

    def test_only_canonical_permission_and_bootstrap_types_are_accepted(self):
        with self.assertRaises(ContractError):
            replace(self.grant, permissions=frozenset({"association.suspend"}))
        with self.assertRaises(ContractError):
            replace(self.grant, provisioning_method="offline_bootstrap")
        with self.assertRaises(ContractError):
            replace(self.grant, permissions=frozenset())

    def test_identifiers_and_revisions_are_validated(self):
        with self.assertRaises(ContractError):
            replace(self.grant, grant_id="not-a-uuid")
        with self.assertRaises(ContractError):
            replace(self.grant, user_identity_revision=True)
        with self.assertRaises(ContractError):
            replace(self.grant, revision=0)

    def test_timestamps_must_be_utc_and_ordered(self):
        with self.assertRaises(ContractError):
            replace(self.grant, expires_at=self.grant.not_before)
        with self.assertRaises(ContractError):
            replace(self.grant, issued_at=self.now.replace(tzinfo=None))

    def test_runtime_reader_cannot_issue_admin_authority(self):
        self.assertIn("get_grant", PlatformAdminAuthorityReaderPort.__dict__)
        self.assertIn("list_grants_for_user", PlatformAdminAuthorityReaderPort.__dict__)
        self.assertNotIn("provision_first_admin", PlatformAdminAuthorityReaderPort.__dict__)
        self.assertIn("provision_first_admin", PlatformAdminBootstrapPort.__dict__)


if __name__ == "__main__":
    unittest.main()
