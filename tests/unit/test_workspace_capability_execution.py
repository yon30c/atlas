"""Tests for CAM-gated read-only workspace capability execution."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4
from pathlib import Path
import tempfile
import unittest

from atlas.adapters.trusted_workspace_mount_resolver import TrustedWorkspaceMountResolver
from atlas.adapters.sqlite.local_authority_unit_of_work import (
    SQLiteLocalAuthorityUnitOfWorkFactory,
)
from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.adapters.sqlite.project_environment_lifecycle_association_writer import SQLiteProjectEnvironmentLifecycleAssociationWriter
from atlas.application.workspace_capability_execution import (
    WorkspaceCapabilityExecutionService,
)
from atlas.assistant.planning import (
    AssistantIntent,
    AssistantPlan,
    IntentKind,
    PlanStep,
)
from atlas.authorization.models import Grant, GrantResourceScope
from atlas.core.context import OperationContext
from atlas.core.errors import AuthorizationError, ContractError
from atlas.memory.metadata import EnvironmentMetadata, ProjectMetadata
from atlas.memory.models import EnvironmentId, ProjectId
from atlas.workspace.models import (
    ProjectEnvironmentAssociation,
    ProjectEnvironmentStatus,
    WorkspaceRecord,
    WorkspaceStatus,
)


NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


class WorkspaceCapabilityExecutionServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.workspace_root = self.root / "workspace"
        self.workspace_root.mkdir()
        (self.workspace_root / "readme.txt").write_text("Atlas", encoding="utf-8")

        self.database = SQLiteDatabase(self.root / "authority.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.uow_factory = SQLiteLocalAuthorityUnitOfWorkFactory(self.database)

        with self.uow_factory() as unit:
            self.user = unit.identity.create_user()
            unit.project_environments.create_project(
                ProjectMetadata(ProjectId("atlas-demo"), "active", 1)
            )
            unit.project_environments.create_environment(
                EnvironmentMetadata(EnvironmentId("test"), "active", 1)
            )
            unit.project_environment_associations.create_association(
                ProjectEnvironmentAssociation(
                    ProjectId("atlas-demo"),
                    EnvironmentId("test"),
                    ProjectEnvironmentStatus.ACTIVE,
                )
            )
            unit.workspaces.create_workspace(
                WorkspaceRecord(
                    workspace_id="demo",
                    owner_user_id=self.user.user_id,
                    project_id=ProjectId("atlas-demo"),
                    environment_id=EnvironmentId("test"),
                    root_ref="mount:demo-root",
                    status=WorkspaceStatus.ACTIVE,
                )
            )
            unit.commit()

        self.context = OperationContext(
            request_id="request-001",
            correlation_id="correlation-001",
            actor=self.user.identity,
            user_id=self.user.user_id,
            origin="local-console",
            delegation=None,
            project_id="atlas-demo",
            environment="test",
            purpose="workspace test",
            classification="internal",
            created_at=NOW,
        )
        self.mount_resolver = TrustedWorkspaceMountResolver(
            {"demo-root": self.workspace_root}
        )
        self.service = WorkspaceCapabilityExecutionService(
            unit_of_work_factory=self.uow_factory,
            mount_resolver=self.mount_resolver,
        )

    def _plan(self, kind, parameters):
        intent = AssistantIntent(kind, tuple(parameters))
        return AssistantPlan.create(
            goal="Inspeccionar el workspace demo",
            intent=intent,
            steps=(
                PlanStep(
                    step_id="step-001",
                    capability=kind,
                    parameters=tuple(parameters),
                    expected_result="Resultado de workspace",
                ),
            ),
            created_at=NOW,
        )

    def _grant(self, *, kind, resource_id, grant_id="grant-001"):
        resource_type = "workspace" if kind is IntentKind.WORKSPACE_LIST else "workspace_file"
        grant = Grant(
            grant_id=grant_id,
            owner_user_id=self.user.user_id,
            subject_identity_id=self.user.identity.identity_id,
            project_id="atlas-demo",
            environment="test",
            resource_scope=GrantResourceScope(
                resource_type=resource_type,
                resource_ids=frozenset({resource_id}),
            ),
            actions=frozenset({kind.value}),
            issued_at=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(hours=1),
        )
        with self.uow_factory() as unit:
            unit.grants.create(grant)
            unit.commit()
        return grant

    def test_list_executes_only_after_exact_grant_and_explicit_review(self):
        self._grant(kind=IntentKind.WORKSPACE_LIST, resource_id="demo")
        plan = self._plan(
            IntentKind.WORKSPACE_LIST,
            (("workspace_id", "demo"),),
        )

        result = self.service.execute(
            plan, self.context, NOW, review_confirmed=True
        )

        self.assertEqual(result.plan_id, plan.plan_id)
        self.assertEqual(result.grant_id, "grant-001")
        self.assertEqual(result.result.entries[0].name, "readme.txt")

    def test_read_uses_canonical_workspace_and_path_resource_id(self):
        resource_id = self.service.workspace_file_resource_id("demo", "readme.txt")
        self._grant(kind=IntentKind.WORKSPACE_READ, resource_id=resource_id)
        plan = self._plan(
            IntentKind.WORKSPACE_READ,
            (("workspace_id", "demo"), ("path", "readme.txt")),
        )

        result = self.service.execute(
            plan, self.context, NOW, review_confirmed=True
        )

        self.assertEqual(result.resource_id, resource_id)
        self.assertEqual(result.result.content, "Atlas")

    def test_missing_grant_denies_before_workspace_access(self):
        plan = self._plan(
            IntentKind.WORKSPACE_LIST,
            (("workspace_id", "demo"),),
        )
        with self.assertRaises(AuthorizationError):
            self.service.execute(plan, self.context, NOW, review_confirmed=True)

    def test_missing_grant_denies_before_mount_resolution(self):
        class ResolverMustNotRun:
            called = False

            def resolve(self, root_ref):
                self.called = True
                raise AssertionError("mount resolver must not run before CAM ALLOW")

        resolver = ResolverMustNotRun()
        service = WorkspaceCapabilityExecutionService(
            unit_of_work_factory=self.uow_factory,
            mount_resolver=resolver,
        )
        plan = self._plan(
            IntentKind.WORKSPACE_LIST,
            (("workspace_id", "demo"),),
        )
        with self.assertRaises(AuthorizationError):
            service.execute(plan, self.context, NOW, review_confirmed=True)
        self.assertFalse(resolver.called)

    def test_unconfirmed_plan_is_denied(self):
        plan = self._plan(
            IntentKind.WORKSPACE_LIST,
            (("workspace_id", "demo"),),
        )
        with self.assertRaises(AuthorizationError):
            self.service.execute(plan, self.context, NOW, review_confirmed=False)

    def test_context_identity_must_match_canonical_identity_revision(self):
        from dataclasses import replace
        altered = replace(
            self.context,
            actor=replace(self.context.actor, revision=2),
        )
        plan = self._plan(
            IntentKind.WORKSPACE_LIST,
            (("workspace_id", "demo"),),
        )
        with self.assertRaises(AuthorizationError):
            self.service.execute(plan, altered, NOW, review_confirmed=True)

    def test_inactive_project_denies(self):
        from dataclasses import replace
        with self.uow_factory() as unit:
            current = unit.project_environments.get_project(ProjectId("atlas-demo"))
            unit.project_environments.update_project(
                replace(current, status="suspended", revision=2),
                expected_revision=1,
            )
            unit.commit()
        plan = self._plan(
            IntentKind.WORKSPACE_LIST,
            (("workspace_id", "demo"),),
        )
        with self.assertRaises(AuthorizationError):
            self.service.execute(plan, self.context, NOW, review_confirmed=True)

    def test_inactive_environment_denies(self):
        from dataclasses import replace
        with self.uow_factory() as unit:
            current = unit.project_environments.get_environment(EnvironmentId("test"))
            unit.project_environments.update_environment(
                replace(current, status="disabled", revision=2),
                expected_revision=1,
            )
            unit.commit()
        plan = self._plan(
            IntentKind.WORKSPACE_LIST,
            (("workspace_id", "demo"),),
        )
        with self.assertRaises(AuthorizationError):
            self.service.execute(plan, self.context, NOW, review_confirmed=True)

    def test_workspace_owner_must_match_canonical_user(self):
        with self.uow_factory() as unit:
            other_user = unit.identity.create_user()
            unit.workspaces.create_workspace(
                WorkspaceRecord(
                    workspace_id="foreign",
                    owner_user_id=other_user.user_id,
                    project_id=ProjectId("atlas-demo"),
                    environment_id=EnvironmentId("test"),
                    root_ref="mount:demo-root",
                )
            )
            unit.commit()
        self._grant(kind=IntentKind.WORKSPACE_LIST, resource_id="foreign")
        plan = self._plan(IntentKind.WORKSPACE_LIST, (("workspace_id", "foreign"),))
        with self.assertRaises(AuthorizationError):
            self.service.execute(plan, self.context, NOW, review_confirmed=True)

    def test_workspace_scope_must_match_context(self):
        from dataclasses import replace
        plan = self._plan(IntentKind.WORKSPACE_LIST, (("workspace_id", "demo"),))
        altered = replace(self.context, project_id="another-project")
        with self.assertRaises(AuthorizationError):
            self.service.execute(plan, altered, NOW, review_confirmed=True)

    def test_suspended_workspace_denies(self):
        from dataclasses import replace
        with self.uow_factory() as unit:
            current = unit.workspaces.get_workspace("demo")
            unit.workspaces.update_workspace(
                replace(current, status=WorkspaceStatus.SUSPENDED, revision=2),
                expected_revision=1,
            )
            unit.commit()
        self._grant(kind=IntentKind.WORKSPACE_LIST, resource_id="demo")
        plan = self._plan(IntentKind.WORKSPACE_LIST, (("workspace_id", "demo"),))
        with self.assertRaises(AuthorizationError):
            self.service.execute(plan, self.context, NOW, review_confirmed=True)

    def test_suspended_project_environment_association_denies(self):
        from dataclasses import replace
        with self.uow_factory() as unit:
            current = unit.project_environment_associations.get_association(
                ProjectId("atlas-demo"), EnvironmentId("test")
            )
            lifecycle_event_id = str(uuid4())
            connection = unit._unit._connection_for(self.database)
            connection.execute(
                """INSERT INTO atlas_project_environment_lifecycle_events (
                    event_id, project_id, environment_id, previous_status, new_status,
                    previous_revision, new_revision, actor_user_id, actor_identity_id,
                    verified_identity_context_id, request_id, correlation_id, reason, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    lifecycle_event_id, current.project_id, current.environment_id,
                    current.status.value, ProjectEnvironmentStatus.SUSPENDED.value,
                    current.revision, current.revision + 1, self.user.user_id,
                    self.user.identity.identity_id, str(uuid4()), self.context.request_id,
                    self.context.correlation_id, "Lifecycle suspension test",
                    NOW.isoformat(),
                ),
            )
            writer = SQLiteProjectEnvironmentLifecycleAssociationWriter(
                self.database, unit_of_work=unit
            )
            writer.update_association(
                replace(current, status=ProjectEnvironmentStatus.SUSPENDED, revision=2),
                expected_revision=1,
                lifecycle_event_id=lifecycle_event_id,
            )
            unit.commit()
        self._grant(kind=IntentKind.WORKSPACE_LIST, resource_id="demo")
        plan = self._plan(IntentKind.WORKSPACE_LIST, (("workspace_id", "demo"),))
        with self.assertRaises(AuthorizationError):
            self.service.execute(plan, self.context, NOW, review_confirmed=True)

    def test_unknown_mount_denies_after_cam_without_filesystem_access(self):
        service = WorkspaceCapabilityExecutionService(
            unit_of_work_factory=self.uow_factory,
            mount_resolver=TrustedWorkspaceMountResolver(
                {"other-root": self.workspace_root}
            ),
        )
        self._grant(kind=IntentKind.WORKSPACE_LIST, resource_id="demo")
        plan = self._plan(IntentKind.WORKSPACE_LIST, (("workspace_id", "demo"),))
        with self.assertRaises(AuthorizationError):
            service.execute(plan, self.context, NOW, review_confirmed=True)

    def test_missing_project_or_environment_denies(self):
        from dataclasses import replace
        plan = self._plan(
            IntentKind.WORKSPACE_LIST,
            (("workspace_id", "demo"),),
        )
        for changes in (
            {"project_id": None},
            {"environment": None},
        ):
            with self.subTest(changes=changes):
                context = replace(self.context, **changes)
                with self.assertRaises(AuthorizationError):
                    self.service.execute(plan, context, NOW, review_confirmed=True)

    def test_plan_must_contain_exactly_one_matching_step(self):
        from dataclasses import replace
        plan = self._plan(
            IntentKind.WORKSPACE_LIST,
            (("workspace_id", "demo"),),
        )
        extra_step = PlanStep(
            step_id="step-002",
            capability=IntentKind.WORKSPACE_LIST,
            parameters=(("workspace_id", "demo"),),
            expected_result="Segundo resultado",
        )
        malformed = replace(plan, steps=plan.steps + (extra_step,))
        with self.assertRaises(ContractError):
            self.service.execute(malformed, self.context, NOW, review_confirmed=True)

    def test_expired_grant_denies(self):
        expired = Grant(
            grant_id="expired-grant",
            owner_user_id=self.user.user_id,
            subject_identity_id=self.user.identity.identity_id,
            project_id="atlas-demo",
            environment="test",
            resource_scope=GrantResourceScope("workspace", frozenset({"demo"})),
            actions=frozenset({IntentKind.WORKSPACE_LIST.value}),
            issued_at=NOW - timedelta(hours=2),
            expires_at=NOW - timedelta(hours=1),
        )
        with self.uow_factory() as unit:
            unit.grants.create(expired)
            unit.commit()
        plan = self._plan(
            IntentKind.WORKSPACE_LIST,
            (("workspace_id", "demo"),),
        )
        with self.assertRaises(AuthorizationError):
            self.service.execute(plan, self.context, NOW, review_confirmed=True)

    def test_read_grant_does_not_authorize_listing(self):
        resource_id = self.service.workspace_file_resource_id("demo", "readme.txt")
        self._grant(kind=IntentKind.WORKSPACE_READ, resource_id=resource_id)
        plan = self._plan(
            IntentKind.WORKSPACE_LIST,
            (("workspace_id", "demo"),),
        )
        with self.assertRaises(AuthorizationError):
            self.service.execute(plan, self.context, NOW, review_confirmed=True)


if __name__ == "__main__":
    unittest.main()
