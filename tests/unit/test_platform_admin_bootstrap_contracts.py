"""Domain tests for the offline Platform Admin bootstrap contracts."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import unittest
from uuid import uuid4

from atlas.core.errors import AuthorizationError, ContractError
from atlas.core.platform_admin import (
    INITIAL_PLATFORM_ADMIN_GRANT_TTL,
    INITIAL_PLATFORM_ADMIN_PERMISSIONS,
    PlatformAdminBootstrapCommand,
    PlatformAdminBootstrapProvenance,
    PlatformAdminBootstrapRequest,
    PlatformAdminGrant,
    PlatformAdminGrantStatus,
    PlatformAdminPermission,
    PlatformAdminProvisioningMethod,
    require_platform_admin_permission,
)


def _uuid():
    return str(uuid4())


class PlatformAdminBootstrapContractTests(unittest.TestCase):
    def setUp(self):
        self.operation_id = _uuid()
        self.user_id = _uuid()
        self.event_id = _uuid()
        self.grant_id = _uuid()
        self.identity_id = _uuid()
        self.confirmed_at = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
        self.request = PlatformAdminBootstrapRequest(
            operation_id=self.operation_id,
            user_id=self.user_id,
            permissions=INITIAL_PLATFORM_ADMIN_PERMISSIONS,
        )
        self.provenance = PlatformAdminBootstrapProvenance(
            event_id=self.event_id,
            grant_id=self.grant_id,
            operator_real_uid=1000,
            operator_effective_uid=1000,
            terminal_id="/dev/pts/4",
            confirmed_at=self.confirmed_at,
        )
        self.grant = PlatformAdminGrant(
            grant_id=self.grant_id,
            user_id=self.user_id,
            user_identity_id=self.identity_id,
            user_identity_revision=3,
            permissions=INITIAL_PLATFORM_ADMIN_PERMISSIONS,
            provisioning_method=PlatformAdminProvisioningMethod.OFFLINE_BOOTSTRAP,
            bootstrap_event_id=self.event_id,
            issued_at=self.confirmed_at,
            not_before=self.confirmed_at,
            expires_at=self.confirmed_at + timedelta(days=90),
        )

    def test_request_requires_exact_initial_permissions(self):
        with self.assertRaises(ContractError):
            PlatformAdminBootstrapRequest(
                operation_id=self.operation_id,
                user_id=self.user_id,
                permissions=frozenset({PlatformAdminPermission.ASSOCIATION_SUSPEND}),
            )
        with self.assertRaises(ContractError):
            PlatformAdminBootstrapRequest(
                operation_id=self.operation_id,
                user_id=self.user_id,
                permissions=frozenset(),
            )
        with self.assertRaises(ContractError):
            PlatformAdminBootstrapRequest(
                operation_id=self.operation_id,
                user_id=self.user_id,
                permissions=frozenset({"association.suspend", "association.reactivate"}),
            )

    def test_request_requires_canonical_uuid4_identifiers(self):
        with self.assertRaises(ContractError):
            PlatformAdminBootstrapRequest(
                operation_id="not-a-uuid",
                user_id=self.user_id,
                permissions=INITIAL_PLATFORM_ADMIN_PERMISSIONS,
            )

    def test_provenance_requires_distinct_uuid4_event_and_grant_ids(self):
        with self.assertRaises(ContractError):
            PlatformAdminBootstrapProvenance(
                event_id=self.event_id,
                grant_id=self.event_id,
                operator_real_uid=1000,
                operator_effective_uid=1000,
                terminal_id="/dev/pts/4",
                confirmed_at=self.confirmed_at,
            )

    def test_provenance_rejects_invalid_uids_and_terminal(self):
        for real_uid, effective_uid, terminal in (
            (-1, 1000, "/dev/pts/4"),
            (1000, True, "/dev/pts/4"),
            (1000, 1000, ""),
            (1000, 1000, "/dev/pts/4\nforged"),
        ):
            with self.subTest(real_uid=real_uid, effective_uid=effective_uid, terminal=terminal):
                with self.assertRaises(ContractError):
                    PlatformAdminBootstrapProvenance(
                        event_id=self.event_id,
                        grant_id=self.grant_id,
                        operator_real_uid=real_uid,
                        operator_effective_uid=effective_uid,
                        terminal_id=terminal,
                        confirmed_at=self.confirmed_at,
                    )

    def test_provenance_requires_utc_aware_confirmation(self):
        with self.assertRaises(ContractError):
            PlatformAdminBootstrapProvenance(
                event_id=self.event_id,
                grant_id=self.grant_id,
                operator_real_uid=1000,
                operator_effective_uid=1000,
                terminal_id="/dev/pts/4",
                confirmed_at=datetime(2026, 11, 17, 12, 0),
            )

    def test_valid_command_binds_request_provenance_and_90_day_grant(self):
        command = PlatformAdminBootstrapCommand(
            request=self.request,
            provenance=self.provenance,
            grant=self.grant,
        )
        self.assertIs(command.request, self.request)
        self.assertEqual(
            self.grant.expires_at - self.grant.issued_at,
            INITIAL_PLATFORM_ADMIN_GRANT_TTL,
        )

    def test_command_rejects_mismatched_subject_event_or_permissions(self):
        variants = (
            replace(self.grant, user_id=_uuid()),
            replace(
                self.grant,
                permissions=frozenset({PlatformAdminPermission.ASSOCIATION_SUSPEND}),
            ),
        )
        for grant in variants:
            with self.subTest(grant=grant):
                with self.assertRaises(ContractError):
                    PlatformAdminBootstrapCommand(self.request, self.provenance, grant)

        wrong_event_grant = PlatformAdminGrant(
            grant_id=self.grant_id,
            user_id=self.user_id,
            user_identity_id=self.identity_id,
            user_identity_revision=3,
            permissions=INITIAL_PLATFORM_ADMIN_PERMISSIONS,
            provisioning_method=PlatformAdminProvisioningMethod.OFFLINE_BOOTSTRAP,
            bootstrap_event_id=_uuid(),
            issued_at=self.confirmed_at,
            not_before=self.confirmed_at,
            expires_at=self.confirmed_at + timedelta(days=90),
        )
        with self.assertRaises(ContractError):
            PlatformAdminBootstrapCommand(self.request, self.provenance, wrong_event_grant)

    def test_command_rejects_wrong_expiry_and_non_initial_grant_state(self):
        short_grant = PlatformAdminGrant(
            grant_id=self.grant_id,
            user_id=self.user_id,
            user_identity_id=self.identity_id,
            user_identity_revision=3,
            permissions=INITIAL_PLATFORM_ADMIN_PERMISSIONS,
            provisioning_method=PlatformAdminProvisioningMethod.OFFLINE_BOOTSTRAP,
            bootstrap_event_id=self.event_id,
            issued_at=self.confirmed_at,
            not_before=self.confirmed_at,
            expires_at=self.confirmed_at + timedelta(days=89),
        )
        with self.assertRaises(ContractError):
            PlatformAdminBootstrapCommand(self.request, self.provenance, short_grant)

        revoked_grant = PlatformAdminGrant(
            grant_id=self.grant_id,
            user_id=self.user_id,
            user_identity_id=self.identity_id,
            user_identity_revision=3,
            permissions=INITIAL_PLATFORM_ADMIN_PERMISSIONS,
            provisioning_method=PlatformAdminProvisioningMethod.OFFLINE_BOOTSTRAP,
            bootstrap_event_id=self.event_id,
            issued_at=self.confirmed_at,
            not_before=self.confirmed_at,
            expires_at=self.confirmed_at + timedelta(days=90),
            status=PlatformAdminGrantStatus.REVOKED,
            revision=2,
            revoked_at=self.confirmed_at + timedelta(days=1),
            revoked_by_user_id=_uuid(),
        )
        with self.assertRaises(ContractError):
            PlatformAdminBootstrapCommand(self.request, self.provenance, revoked_grant)

    def test_request_and_provenance_are_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            self.request.user_id = _uuid()
        with self.assertRaises(FrozenInstanceError):
            self.provenance.operator_real_uid = 0


    def test_permission_check_accepts_only_matching_active_unexpired_identity(self):
        require_platform_admin_permission(
            self.grant,
            permission=PlatformAdminPermission.ASSOCIATION_SUSPEND,
            user_id=self.user_id,
            user_identity_id=self.identity_id,
            user_identity_revision=3,
            now=self.confirmed_at + timedelta(days=1),
        )

        denied_claims = (
            {"user_id": _uuid()},
            {"user_identity_id": _uuid()},
            {"user_identity_revision": 4},
            {"now": self.grant.expires_at},
            {"now": self.grant.not_before - timedelta(microseconds=1)},
        )
        for overrides in denied_claims:
            arguments = {
                "user_id": self.user_id,
                "user_identity_id": self.identity_id,
                "user_identity_revision": 3,
                "now": self.confirmed_at + timedelta(days=1),
            }
            arguments.update(overrides)
            with self.subTest(overrides=overrides):
                with self.assertRaises(AuthorizationError):
                    require_platform_admin_permission(
                        self.grant,
                        permission=PlatformAdminPermission.ASSOCIATION_SUSPEND,
                        **arguments,
                    )

    def test_permission_check_rejects_revoked_grant_and_unheld_permission(self):
        revoked = replace(
            self.grant,
            status=PlatformAdminGrantStatus.REVOKED,
            revision=2,
            revoked_at=self.confirmed_at + timedelta(days=1),
            revoked_by_user_id=_uuid(),
        )
        with self.assertRaises(AuthorizationError):
            require_platform_admin_permission(
                revoked,
                permission=PlatformAdminPermission.ASSOCIATION_SUSPEND,
                user_id=self.user_id,
                user_identity_id=self.identity_id,
                user_identity_revision=3,
                now=self.confirmed_at + timedelta(days=2),
            )

        limited_grant = replace(
            self.grant,
            permissions=frozenset({PlatformAdminPermission.ASSOCIATION_SUSPEND}),
        )
        with self.assertRaises(AuthorizationError):
            require_platform_admin_permission(
                limited_grant,
                permission=PlatformAdminPermission.ASSOCIATION_REACTIVATE,
                user_id=self.user_id,
                user_identity_id=self.identity_id,
                user_identity_revision=3,
                now=self.confirmed_at + timedelta(days=2),
            )


if __name__ == "__main__":
    unittest.main()
