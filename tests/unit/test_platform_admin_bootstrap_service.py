import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID

from atlas.application.platform_admin_bootstrap import PlatformAdminBootstrapService
from atlas.core.errors import AuthorizationError, ConcurrencyError, ContractError
from atlas.core.identity import Identity, IdentityKind, IdentityStatus
from atlas.core.platform_admin import (
    INITIAL_PLATFORM_ADMIN_GRANT_TTL,
    INITIAL_PLATFORM_ADMIN_PERMISSIONS,
    PlatformAdminBootstrapCommand,
    PlatformAdminBootstrapRequest,
)
from atlas.core.user_identity import CanonicalUserIdentity


NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
USER_ID = "11111111-1111-4111-8111-111111111111"
IDENTITY_ID = "22222222-2222-4222-8222-222222222222"


class FakeIdentityAuthority:
    def __init__(self, canonical):
        self.canonical = canonical
        self.calls = []

    def get_user(self, user_id):
        self.calls.append(user_id)
        return self.canonical


class FakeBootstrapPort:
    def __init__(self):
        self.commands = []
        self.operations = {}

    def get_operation(self, operation_id):
        return self.operations.get(operation_id)

    def provision_first_admin(self, command):
        self.commands.append(command)
        self.operations[command.request.operation_id] = command
        return command.grant


class FakeClock:
    def __init__(self, value=NOW):
        self.value = value
        self.calls = 0

    def now(self):
        self.calls += 1
        return self.value


class PlatformAdminBootstrapServiceTests(unittest.TestCase):
    def setUp(self):
        self.canonical = CanonicalUserIdentity(
            user_id=USER_ID,
            identity=Identity(
                identity_id=IDENTITY_ID,
                kind=IdentityKind.USER,
                status=IdentityStatus.ACTIVE,
                revision=7,
            ),
        )
        self.identity = FakeIdentityAuthority(self.canonical)
        self.bootstrap = FakeBootstrapPort()
        self.clock = FakeClock()
        self.ids = iter((
            UUID("33333333-3333-4333-8333-333333333333"),
            UUID("44444444-4444-4444-8444-444444444444"),
        ))
        self.service = PlatformAdminBootstrapService(
            identity_authority=self.identity,
            bootstrap_port=self.bootstrap,
            clock=self.clock,
            uuid_factory=lambda: next(self.ids),
        )
        self.request = PlatformAdminBootstrapRequest(
            operation_id="55555555-5555-4555-8555-555555555555",
            user_id=USER_ID,
            permissions=INITIAL_PLATFORM_ADMIN_PERMISSIONS,
        )

    def test_builds_command_from_canonical_active_user_and_trusted_clock(self):
        grant = self.service.provision_first_admin(
            self.request,
            operator_real_uid=1000,
            operator_effective_uid=0,
            terminal_id="/dev/pts/2",
        )
        self.assertEqual(len(self.bootstrap.commands), 1)
        command = self.bootstrap.commands[0]
        self.assertIsInstance(command, PlatformAdminBootstrapCommand)
        self.assertEqual(command.grant, grant)
        self.assertEqual(grant.user_id, USER_ID)
        self.assertEqual(grant.user_identity_id, IDENTITY_ID)
        self.assertEqual(grant.user_identity_revision, 7)
        self.assertEqual(grant.permissions, INITIAL_PLATFORM_ADMIN_PERMISSIONS)
        self.assertEqual(grant.issued_at, NOW)
        self.assertEqual(grant.not_before, NOW)
        self.assertEqual(grant.expires_at, NOW + INITIAL_PLATFORM_ADMIN_GRANT_TTL)
        self.assertEqual(command.provenance.operator_real_uid, 1000)
        self.assertEqual(command.provenance.operator_effective_uid, 0)
        self.assertEqual(command.provenance.terminal_id, "/dev/pts/2")
        self.assertEqual(self.clock.calls, 1)


    def test_exact_replay_recovers_persisted_grant_without_new_provenance(self):
        first = self.service.provision_first_admin(
            self.request,
            operator_real_uid=1000,
            operator_effective_uid=0,
            terminal_id="/dev/pts/2",
        )
        clock_calls = self.clock.calls
        replay = self.service.provision_first_admin(
            self.request,
            operator_real_uid=2000,
            operator_effective_uid=2000,
            terminal_id="/dev/pts/9",
        )
        self.assertEqual(replay, first)
        self.assertEqual(len(self.bootstrap.commands), 1)
        self.assertEqual(self.clock.calls, clock_calls)

    def test_operation_id_replay_with_different_intent_is_rejected(self):
        self.service.provision_first_admin(
            self.request,
            operator_real_uid=1000,
            operator_effective_uid=1000,
            terminal_id="/dev/pts/2",
        )
        conflicting = replace(
            self.request,
            user_id="88888888-8888-4888-8888-888888888888",
        )
        with self.assertRaises(ConcurrencyError):
            self.service.provision_first_admin(
                conflicting,
                operator_real_uid=1000,
                operator_effective_uid=1000,
                terminal_id="/dev/pts/2",
            )
        self.assertEqual(len(self.bootstrap.commands), 1)

    def test_rejects_missing_user_without_calling_bootstrap_port(self):
        self.identity.canonical = None
        with self.assertRaises(AuthorizationError):
            self.service.provision_first_admin(
                self.request,
                operator_real_uid=1000,
                operator_effective_uid=1000,
                terminal_id="/dev/pts/2",
            )
        self.assertEqual(self.bootstrap.commands, [])

    def test_rejects_suspended_user_without_calling_bootstrap_port(self):
        self.identity.canonical = CanonicalUserIdentity(
            user_id=USER_ID,
            identity=Identity(
                identity_id=IDENTITY_ID,
                kind=IdentityKind.USER,
                status=IdentityStatus.SUSPENDED,
            ),
        )
        with self.assertRaises(AuthorizationError):
            self.service.provision_first_admin(
                self.request,
                operator_real_uid=1000,
                operator_effective_uid=1000,
                terminal_id="/dev/pts/2",
            )
        self.assertEqual(self.bootstrap.commands, [])

    def test_rejects_non_utc_clock_without_calling_bootstrap_port(self):
        self.clock.value = datetime(2026, 11, 17, 8, 0)
        with self.assertRaises(ContractError):
            self.service.provision_first_admin(
                self.request,
                operator_real_uid=1000,
                operator_effective_uid=1000,
                terminal_id="/dev/pts/2",
            )
        self.assertEqual(self.bootstrap.commands, [])

    def test_adapter_failure_is_propagated_without_fallback(self):
        class FailingBootstrap:
            def get_operation(self, operation_id):
                return None

            def provision_first_admin(self, command):
                raise RuntimeError("storage unavailable")

        failure_ids = iter((
            UUID("66666666-6666-4666-8666-666666666666"),
            UUID("77777777-7777-4777-8777-777777777777"),
        ))
        service = PlatformAdminBootstrapService(
            identity_authority=self.identity,
            bootstrap_port=FailingBootstrap(),
            clock=self.clock,
            uuid_factory=lambda: next(failure_ids),
        )
        with self.assertRaises(RuntimeError):
            service.provision_first_admin(
                self.request,
                operator_real_uid=1000,
                operator_effective_uid=1000,
                terminal_id="/dev/pts/2",
            )


if __name__ == "__main__":
    unittest.main()
