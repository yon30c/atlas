"""Security and transaction tests for association lifecycle application service."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from threading import Barrier
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.local_authority_unit_of_work import SQLiteLocalAuthorityUnitOfWorkFactory
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.adapters.sqlite.platform_admin_bootstrap import SQLitePlatformAdminBootstrapAdapter
from atlas.adapters.sqlite.project_environment_lifecycle_ledger import SQLiteProjectEnvironmentLifecycleLedger
from atlas.adapters.sqlite.project_environment_lifecycle_association_writer import SQLiteProjectEnvironmentLifecycleAssociationWriter
from atlas.application.project_environment_lifecycle import ProjectEnvironmentLifecycleService
from atlas.core.context import OperationContext
from atlas.core.errors import AuthorizationError, ConcurrencyError
from atlas.core.identity import IdentityKind
from atlas.core.platform_admin import (
    INITIAL_PLATFORM_ADMIN_PERMISSIONS,
    PlatformAdminBootstrapCommand,
    PlatformAdminBootstrapProvenance,
    PlatformAdminBootstrapRequest,
    PlatformAdminGrant,
    PlatformAdminProvisioningMethod,
)
from atlas.core.project_environment_lifecycle import ProjectEnvironmentLifecycleRequest
from atlas.core.verified_identity_context import VerifiedIdentityContext
from atlas.memory.metadata import EnvironmentMetadata, ProjectMetadata
from atlas.memory.models import EnvironmentId, ProjectId
from atlas.ports.clock import Clock
from tests.unit.association_provisioning_test_support import provision_association
from atlas.workspace.models import ProjectEnvironmentAssociation, ProjectEnvironmentStatus


NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)


def _uuid():
    return str(uuid4())


class FixedClock(Clock):
    def __init__(self, now=NOW):
        self._now = now

    def now(self):
        return self._now


class TestIdentityVerifier:
    def __init__(self, canonical, now=NOW):
        self.canonical = canonical
        self.now = now

    def verify_in_unit_of_work(self, evidence, unit):
        current = unit.identity.get_user(evidence.user_id)
        if (
            current is None
            or current != self.canonical
            or evidence.identity_id != current.identity.identity_id
            or evidence.identity_revision != current.identity.revision
            or evidence.expires_at <= self.now
            or evidence.verified_at > self.now
        ):
            raise AuthorizationError("invalid identity evidence")
        return current


class ProjectEnvironmentLifecycleServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "atlas.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.uow_factory = SQLiteLocalAuthorityUnitOfWorkFactory(self.database)
        with self.uow_factory() as unit:
            self.user = unit.identity.create_user()
            unit.project_environments.create_project(
                ProjectMetadata(ProjectId("atlas"), "active", 1)
            )
            unit.project_environments.create_environment(
                EnvironmentMetadata(EnvironmentId("test"), "active", 1)
            )
            provision_association(
                self.database,
                ProjectEnvironmentAssociation(
                    ProjectId("atlas"), EnvironmentId("test"),
                    ProjectEnvironmentStatus.ACTIVE,
                ),
                unit_of_work=unit._unit,
            )
            unit.commit()
        self._provision_admin()
        self.context = OperationContext(
            request_id=_uuid(),
            correlation_id=_uuid(),
            actor=self.user.identity,
            user_id=self.user.user_id,
            origin="test",
            delegation=None,
            project_id="atlas",
            environment="test",
            purpose="association lifecycle",
            classification="internal",
            created_at=NOW,
        )
        self.evidence = VerifiedIdentityContext(
            context_id=_uuid(),
            identity_id=self.user.identity.identity_id,
            identity_type=IdentityKind.USER,
            identity_revision=self.user.identity.revision,
            user_id=self.user.user_id,
            binding_id=_uuid(),
            binding_revision=1,
            issuer_id=_uuid(),
            authenticated_at=NOW - timedelta(minutes=1),
            verified_at=NOW - timedelta(seconds=30),
            expires_at=NOW + timedelta(minutes=5),
            verification_ref="A" * 43,
            attestation="B" * 43,
        )
        self.service = ProjectEnvironmentLifecycleService(
            self.uow_factory,
            identity_verifier=TestIdentityVerifier(self.user),
            clock=FixedClock(),
            ledger_factory=lambda unit: SQLiteProjectEnvironmentLifecycleLedger(
                self.database, unit_of_work=unit._unit
            ),
            association_writer_factory=lambda unit: SQLiteProjectEnvironmentLifecycleAssociationWriter(
                self.database, unit_of_work=unit
            ),
        )

    def _provision_admin(self):
        confirmed = NOW - timedelta(days=1)
        request = PlatformAdminBootstrapRequest(
            operation_id=_uuid(),
            user_id=self.user.user_id,
            permissions=INITIAL_PLATFORM_ADMIN_PERMISSIONS,
        )
        provenance = PlatformAdminBootstrapProvenance(
            event_id=_uuid(),
            grant_id=_uuid(),
            operator_real_uid=1000,
            operator_effective_uid=1000,
            terminal_id="/dev/pts/test",
            confirmed_at=confirmed,
        )
        grant = PlatformAdminGrant(
            grant_id=provenance.grant_id,
            user_id=self.user.user_id,
            user_identity_id=self.user.identity.identity_id,
            user_identity_revision=self.user.identity.revision,
            permissions=INITIAL_PLATFORM_ADMIN_PERMISSIONS,
            provisioning_method=PlatformAdminProvisioningMethod.OFFLINE_BOOTSTRAP,
            bootstrap_event_id=provenance.event_id,
            issued_at=confirmed,
            not_before=confirmed,
            expires_at=confirmed + timedelta(days=90),
        )
        SQLitePlatformAdminBootstrapAdapter(self.database).provision_first_admin(
            PlatformAdminBootstrapCommand(request, provenance, grant)
        )

    def _request(self, target, revision=1):
        return ProjectEnvironmentLifecycleRequest(
            ProjectId("atlas"), EnvironmentId("test"), target,
            expected_revision=revision, reason="Approved maintenance action",
        )

    def test_suspend_requires_exact_admin_permission_and_writes_event_atomically(self):
        event = self.service.transition(
            self.context, self.evidence,
            self._request(ProjectEnvironmentStatus.SUSPENDED),
        )
        self.assertEqual(event.previous_status, ProjectEnvironmentStatus.ACTIVE)
        self.assertEqual(event.new_status, ProjectEnvironmentStatus.SUSPENDED)
        self.assertEqual(event.actor_user_id, self.user.user_id)
        self.assertEqual(event.actor_identity_id, self.user.identity.identity_id)
        with self.uow_factory() as unit:
            association = unit.project_environment_associations.get_association(
                ProjectId("atlas"), EnvironmentId("test")
            )
            self.assertEqual(association.status, ProjectEnvironmentStatus.SUSPENDED)
            self.assertEqual(association.revision, 2)
            self.assertEqual(
                unit._unit._connection_for(self.database).execute(
                    "SELECT COUNT(*) FROM atlas_project_environment_lifecycle_events"
                ).fetchone()[0],
                1,
            )
            unit.commit()

    def test_reactivate_requires_exact_admin_permission(self):
        self.service.transition(
            self.context, self.evidence,
            self._request(ProjectEnvironmentStatus.SUSPENDED),
        )
        event = self.service.transition(
            self.context, self.evidence,
            self._request(ProjectEnvironmentStatus.ACTIVE, revision=2),
        )
        self.assertEqual(event.previous_status, ProjectEnvironmentStatus.SUSPENDED)
        self.assertEqual(event.new_status, ProjectEnvironmentStatus.ACTIVE)
        self.assertEqual(event.new_revision, 3)

    def test_missing_admin_authority_denies(self):
        with self.database.unit_of_work() as unit:
            unit._connection_for(self.database).execute(
                "UPDATE platform_admin_grants SET status='revoked', revision=revision+1, revoked_at=?, revoked_by_user_id=?",
                (NOW.isoformat(), self.user.user_id),
            )
        with self.assertRaises(AuthorizationError):
            self.service.transition(
                self.context, self.evidence,
                self._request(ProjectEnvironmentStatus.SUSPENDED),
            )

    def test_stale_association_revision_denies_without_event(self):
        with self.assertRaises(ConcurrencyError):
            self.service.transition(
                self.context, self.evidence,
                self._request(ProjectEnvironmentStatus.SUSPENDED, revision=9),
            )
        with self.database.connection() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM atlas_project_environment_lifecycle_events"
                ).fetchone()[0],
                0,
            )

    def test_unverified_or_expired_identity_denies_before_writes(self):
        expired = VerifiedIdentityContext(
            context_id=_uuid(),
            identity_id=self.user.identity.identity_id,
            identity_type=IdentityKind.USER,
            identity_revision=self.user.identity.revision,
            user_id=self.user.user_id,
            binding_id=_uuid(),
            binding_revision=1,
            issuer_id=_uuid(),
            authenticated_at=NOW - timedelta(days=1),
            verified_at=NOW - timedelta(hours=1),
            expires_at=NOW - timedelta(seconds=1),
            verification_ref="C" * 43,
            attestation="D" * 43,
        )
        with self.assertRaises(AuthorizationError):
            self.service.transition(
                self.context, expired,
                self._request(ProjectEnvironmentStatus.SUSPENDED),
            )
        with self.database.connection() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM atlas_project_environment_lifecycle_events"
                ).fetchone()[0],
                0,
            )


    def test_expired_platform_admin_grant_denies_without_writes(self):
        future = NOW + timedelta(days=90)
        long_lived_evidence = replace(
            self.evidence,
            authenticated_at=NOW,
            verified_at=NOW,
            expires_at=future + timedelta(days=1),
        )
        service = ProjectEnvironmentLifecycleService(
            self.uow_factory,
            identity_verifier=TestIdentityVerifier(self.user, now=future),
            clock=FixedClock(future),
            ledger_factory=lambda unit: SQLiteProjectEnvironmentLifecycleLedger(
                self.database, unit_of_work=unit._unit
            ),
            association_writer_factory=lambda unit: SQLiteProjectEnvironmentLifecycleAssociationWriter(
                self.database, unit_of_work=unit
            ),
        )
        with self.assertRaises(AuthorizationError):
            service.transition(
                self.context,
                long_lived_evidence,
                self._request(ProjectEnvironmentStatus.SUSPENDED),
            )
        with self.database.connection() as connection:
            association = connection.execute(
                "SELECT status, revision FROM atlas_project_environments"
            ).fetchone()
            event_count = connection.execute(
                "SELECT COUNT(*) FROM atlas_project_environment_lifecycle_events"
            ).fetchone()[0]
        self.assertEqual((association["status"], association["revision"]), ("active", 1))
        self.assertEqual(event_count, 0)

    def test_clock_is_captured_after_uow_acquisition(self):
        future = NOW + timedelta(days=90)
        long_lived_evidence = replace(
            self.evidence,
            authenticated_at=future - timedelta(minutes=1),
            verified_at=future - timedelta(seconds=30),
            expires_at=future + timedelta(days=1),
        )
        clock = FixedClock(NOW)
        verifier = TestIdentityVerifier(self.user, now=future)
        delegate_factory = self.uow_factory

        class ClockAdvancingFactory:
            def __call__(self):
                delegate = delegate_factory()

                class ClockAdvancingUnit:
                    def __enter__(self):
                        unit = delegate.__enter__()
                        # Simulate time passing while BEGIN IMMEDIATE waits.
                        clock._now = future
                        return unit

                    def __exit__(self, exc_type, exc_value, traceback):
                        return delegate.__exit__(exc_type, exc_value, traceback)

                return ClockAdvancingUnit()

        service = ProjectEnvironmentLifecycleService(
            ClockAdvancingFactory(),
            identity_verifier=verifier,
            clock=clock,
            ledger_factory=lambda unit: SQLiteProjectEnvironmentLifecycleLedger(
                self.database, unit_of_work=unit._unit
            ),
            association_writer_factory=lambda unit: SQLiteProjectEnvironmentLifecycleAssociationWriter(
                self.database, unit_of_work=unit
            ),
        )
        with self.assertRaises(AuthorizationError):
            service.transition(
                self.context,
                long_lived_evidence,
                self._request(ProjectEnvironmentStatus.SUSPENDED),
            )
        with self.database.connection() as connection:
            association = connection.execute(
                "SELECT status, revision FROM atlas_project_environments"
            ).fetchone()
            event_count = connection.execute(
                "SELECT COUNT(*) FROM atlas_project_environment_lifecycle_events"
            ).fetchone()[0]
        self.assertEqual((association["status"], association["revision"]), ("active", 1))
        self.assertEqual(event_count, 0)

    def test_identity_revision_mismatch_denies_without_writes(self):
        mismatched = replace(
            self.evidence,
            identity_revision=self.evidence.identity_revision + 1,
        )
        with self.assertRaises(AuthorizationError):
            self.service.transition(
                self.context,
                mismatched,
                self._request(ProjectEnvironmentStatus.SUSPENDED),
            )
        with self.database.connection() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM atlas_project_environment_lifecycle_events"
                ).fetchone()[0],
                0,
            )

    def test_commit_failure_rolls_back_event_and_association(self):
        factory = self.uow_factory

        class CommitFailingUnit:
            def __enter__(self):
                self._unit = factory().__enter__()
                return self

            def __getattr__(self, name):
                return getattr(self._unit, name)

            def commit(self):
                raise RuntimeError("forced physical commit failure")

            def __exit__(self, exc_type, exc_value, traceback):
                return self._unit.__exit__(exc_type, exc_value, traceback)

        service = ProjectEnvironmentLifecycleService(
            lambda: CommitFailingUnit(),
            identity_verifier=TestIdentityVerifier(self.user),
            clock=FixedClock(),
            ledger_factory=lambda unit: SQLiteProjectEnvironmentLifecycleLedger(
                self.database, unit_of_work=unit._unit._unit
            ),
            association_writer_factory=lambda unit: SQLiteProjectEnvironmentLifecycleAssociationWriter(
                self.database, unit_of_work=unit._unit
            ),
        )
        with self.assertRaisesRegex(RuntimeError, "forced physical commit failure"):
            service.transition(
                self.context,
                self.evidence,
                self._request(ProjectEnvironmentStatus.SUSPENDED),
            )
        with self.database.connection() as connection:
            association = connection.execute(
                "SELECT status, revision FROM atlas_project_environments"
            ).fetchone()
            event_count = connection.execute(
                "SELECT COUNT(*) FROM atlas_project_environment_lifecycle_events"
            ).fetchone()[0]
            marker_count = connection.execute(
                "SELECT COUNT(*) FROM atlas_project_environment_lifecycle_commits"
            ).fetchone()[0]
        self.assertEqual((association["status"], association["revision"]), ("active", 1))
        self.assertEqual((event_count, marker_count), (0, 0))

    def test_concurrent_same_revision_allows_only_one_transition(self):
        barrier = Barrier(2)

        def attempt():
            barrier.wait(timeout=5)
            try:
                self.service.transition(
                    self.context,
                    self.evidence,
                    self._request(ProjectEnvironmentStatus.SUSPENDED),
                )
                return "committed"
            except ConcurrencyError:
                return "stale"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = tuple(pool.map(lambda _: attempt(), range(2)))
        self.assertCountEqual(outcomes, ("committed", "stale"))
        with self.database.connection() as connection:
            association = connection.execute(
                "SELECT status, revision FROM atlas_project_environments"
            ).fetchone()
            event_count = connection.execute(
                "SELECT COUNT(*) FROM atlas_project_environment_lifecycle_events"
            ).fetchone()[0]
        self.assertEqual((association["status"], association["revision"]), ("suspended", 2))
        self.assertEqual(event_count, 1)

    def test_ledger_failure_rolls_back_transition(self):
        def failing_ledger_factory(unit):
            class FailingLedger:
                def append_event(self, event):
                    raise RuntimeError("forced ledger failure")
            return FailingLedger()

        service = ProjectEnvironmentLifecycleService(
            self.uow_factory,
            identity_verifier=TestIdentityVerifier(self.user),
            clock=FixedClock(),
            ledger_factory=failing_ledger_factory,
            association_writer_factory=lambda unit: SQLiteProjectEnvironmentLifecycleAssociationWriter(
                self.database, unit_of_work=unit
            ),
        )
        with self.assertRaisesRegex(RuntimeError, "forced ledger failure"):
            service.transition(
                self.context, self.evidence,
                self._request(ProjectEnvironmentStatus.SUSPENDED),
            )
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT status, revision FROM atlas_project_environments"
            ).fetchone()
            self.assertEqual((row["status"], row["revision"]), ("active", 1))
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM atlas_project_environment_lifecycle_events"
                ).fetchone()[0],
                0,
            )


if __name__ == "__main__":
    unittest.main()
