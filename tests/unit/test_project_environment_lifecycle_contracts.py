"""Domain contract tests for audited Project/Environment lifecycle."""

from dataclasses import replace
from datetime import datetime, timezone
import unittest
from uuid import uuid4

from atlas.core.errors import ContractError
from atlas.core.project_environment_lifecycle import (
    ProjectEnvironmentLifecycleEvent,
    ProjectEnvironmentLifecycleRequest,
)
from atlas.memory.models import EnvironmentId, ProjectId
from atlas.workspace.models import ProjectEnvironmentStatus


def uid():
    return str(uuid4())


class ProjectEnvironmentLifecycleContractTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
        self.request = ProjectEnvironmentLifecycleRequest(
            project_id=ProjectId("project-alpha"),
            environment_id=EnvironmentId("production"),
            target_status=ProjectEnvironmentStatus.SUSPENDED,
            expected_revision=4,
            reason="security incident review",
        )
        self.event = ProjectEnvironmentLifecycleEvent(
            event_id=uid(),
            project_id=self.request.project_id,
            environment_id=self.request.environment_id,
            previous_status=ProjectEnvironmentStatus.ACTIVE,
            new_status=ProjectEnvironmentStatus.SUSPENDED,
            previous_revision=4,
            new_revision=5,
            actor_user_id=uid(),
            actor_identity_id=uid(),
            verified_identity_context_id=uid(),
            request_id="request-123",
            correlation_id="correlation-456",
            reason=self.request.reason,
            occurred_at=self.now,
        )

    def test_request_accepts_only_explicit_normalized_intent(self):
        self.assertEqual(self.request.expected_revision, 4)
        for changes in (
            {"target_status": "suspended"},
            {"expected_revision": True},
            {"expected_revision": 0},
            {"reason": ""},
            {"reason": "  security incident review"},
            {"reason": "security  incident review"},
            {"reason": "security\nincident review"},
            {"reason": "x" * 501},
        ):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                replace(self.request, **changes)

    def test_event_binds_actor_context_and_revision_step(self):
        self.assertEqual(self.event.new_revision, self.event.previous_revision + 1)
        self.assertEqual(self.event.new_status, ProjectEnvironmentStatus.SUSPENDED)

    def test_event_rejects_noop_or_invalid_transition(self):
        for changes in (
            {"new_status": ProjectEnvironmentStatus.ACTIVE},
            {"previous_status": ProjectEnvironmentStatus.SUSPENDED,
             "new_status": ProjectEnvironmentStatus.ACTIVE,
             "previous_revision": 4, "new_revision": 4},
            {"new_revision": 6},
        ):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                replace(self.event, **changes)

    def test_event_rejects_invalid_actor_or_context_references(self):
        for changes in (
            {"actor_user_id": "not-a-uuid"},
            {"actor_identity_id": "not-a-uuid"},
            {"verified_identity_context_id": "not-a-uuid"},
            {"event_id": "not-a-uuid"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                replace(self.event, **changes)

    def test_event_requires_normalized_reason_and_utc_time(self):
        with self.assertRaises(ContractError):
            replace(self.event, reason="reason with  spaces")
        with self.assertRaises(ContractError):
            replace(self.event, occurred_at=self.now.replace(tzinfo=None))


if __name__ == "__main__":
    unittest.main()
