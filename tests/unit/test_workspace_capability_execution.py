"""Tests for CAM-gated read-only workspace capability execution."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from atlas.adapters.local_workspace import LocalWorkspaceAdapter
from atlas.adapters.sqlite.local_authority_unit_of_work import (
    SQLiteLocalAuthorityUnitOfWorkFactory,
)
from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.application.workspace_file_reading import WorkspaceFileReadingService
from atlas.application.workspace_listing import WorkspaceListingService
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
        adapter = LocalWorkspaceAdapter({"demo": self.workspace_root})
        self.service = WorkspaceCapabilityExecutionService(
            unit_of_work_factory=self.uow_factory,
            listing_service=WorkspaceListingService(adapter),
            reading_service=WorkspaceFileReadingService(adapter),
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
        malformed = replace(plan, steps=())
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
