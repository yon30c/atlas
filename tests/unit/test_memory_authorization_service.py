import unittest
from datetime import datetime, timedelta, timezone

from atlas.authorization.identity_binding import AuthenticatedUserSubject
from atlas.authorization.memory_metadata_resolver import MemoryMetadataResolver
from atlas.authorization.memory_service import MemoryAuthorizationService
from atlas.authorization.models import (
    AuthorizationDecision,
    AuthorizationResult,
    Grant,
    GrantResourceScope,
)
from atlas.core.context import OperationContext
from atlas.core.identity import Identity, IdentityKind, IdentityStatus
from atlas.memory.metadata import (
    EnvironmentMetadata,
    MemoryVersionMetadata,
    ProjectMetadata,
)
from atlas.memory.models import (
    Memory,
    MemoryClassification,
    MemoryScope,
    MemoryScopeKind,
    MemoryVersionStatus,
)


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
MEMORY_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a11"
VERSION_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a12"


class StubMemoryPort:
    def __init__(self, memory, version):
        self.memory = memory
        self.version = version

    def get_memory(self, memory_id):
        return self.memory if memory_id == self.memory.memory_id else None

    def get_version(self, memory_id, version_id):
        if memory_id == self.version.memory_id and version_id == self.version.version_id:
            return self.version
        return None


class StubProjectPort:
    def __init__(self, status="active"):
        self.status = status

    def get_project(self, project_id):
        return ProjectMetadata(project_id, self.status, 1)


class StubEnvironmentPort:
    def __init__(self, status="active"):
        self.status = status

    def get_environment(self, environment_id):
        return EnvironmentMetadata(environment_id, self.status, 1)


class StubIdentityBindingPort:
    def __init__(self, subject="owner-1", error=None):
        self.subject = subject
        self.error = error
        self.calls = []

    def resolve_user_subject(self, actor_identity_id):
        self.calls.append(actor_identity_id)
        if self.error:
            raise self.error
        return AuthenticatedUserSubject(actor_identity_id, self.subject, True, 1)


class StubGrantRepository:
    def __init__(self, grants=(), error=None):
        self.grants = grants
        self.error = error
        self.owner_requests = []

    def list_by_owner(self, owner_user_id):
        self.owner_requests.append(owner_user_id)
        if self.error:
            raise self.error
        return self.grants


def make_context(kind=IdentityKind.USER, project_id=None, environment=None):
    return OperationContext(
        request_id="request-1",
        correlation_id="correlation-1",
        actor=Identity("identity-1", kind, IdentityStatus.ACTIVE),
        user_id="untrusted-context-user",
        origin="unit-test",
        delegation=None,
        project_id=project_id,
        environment=environment,
        purpose="test memory authorization",
        classification="internal",
        created_at=NOW,
    )


def make_memory(scope=MemoryScopeKind.PRIVATE, project_id=None):
    return Memory(
        memory_id=MEMORY_ID,
        owner_id="owner-1",
        scope=MemoryScope(scope, project_id),
        current_approved_version_id=VERSION_ID,
        created_at=NOW,
        updated_at=NOW,
    )


def make_version(
    status=MemoryVersionStatus.APPROVED,
    classification=MemoryClassification.CONFIDENTIAL,
):
    return MemoryVersionMetadata(
        version_id=VERSION_ID,
        memory_id=MEMORY_ID,
        status=status,
        classification=classification,
        parent_version_id=None,
    )


def make_grant():
    return Grant(
        grant_id="grant-1",
        owner_user_id="owner-1",
        subject_identity_id="identity-1",
        project_id="project-1",
        environment="development",
        resource_scope=GrantResourceScope("memory", frozenset({MEMORY_ID})),
        actions=frozenset({"memory.read"}),
        issued_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=1),
    )


class MemoryAuthorizationServiceTests(unittest.TestCase):
    def setUp(self):
        self.memory = make_memory()
        self.version = make_version()
        self.memory_port = StubMemoryPort(self.memory, self.version)
        self.project_port = StubProjectPort()
        self.environment_port = StubEnvironmentPort()
        self.resolver = MemoryMetadataResolver(
            self.memory_port, self.project_port, self.environment_port
        )
        self.binding = StubIdentityBindingPort()
        self.grant_repository = StubGrantRepository()
        self.service = MemoryAuthorizationService(
            self.resolver,
            self.binding,
            grant_repository=self.grant_repository,
        )

    def decision(self, result):
        return result.decision

    def test_private_owner_is_allowed_using_trusted_subject(self):
        result = self.service.authorize_read(make_context(), MEMORY_ID, NOW)
        self.assertIs(self.decision(result), AuthorizationDecision.ALLOW)
        self.assertIsNotNone(result.snapshot)
        self.assertEqual(result.snapshot.revisions.memory_revision.revision, 1)
        self.assertEqual(result.snapshot.revisions.version_revision.revision, 1)
        self.assertEqual(result.snapshot.revisions.identity_revision.revision, 1)
        self.assertEqual(self.binding.calls, ["identity-1"])
        self.assertEqual(self.grant_repository.owner_requests, [])

    def test_public_cam_allow_requires_snapshot_and_denials_forbid_one(self):
        with self.assertRaises(Exception):
            AuthorizationResult(AuthorizationDecision.ALLOW)
        allowed = self.service.authorize_read(make_context(), MEMORY_ID, NOW)
        denied = AuthorizationResult(AuthorizationDecision.DENY)
        self.assertIsNotNone(allowed.snapshot)
        self.assertIsNone(denied.snapshot)
        with self.assertRaises(Exception):
            AuthorizationResult(AuthorizationDecision.DENY, allowed.snapshot)

    def test_private_owner_does_not_use_context_user_id(self):
        self.binding.subject = "another-user"
        result = self.service.authorize_read(make_context(), MEMORY_ID, NOW)
        self.assertIs(self.decision(result), AuthorizationDecision.DENY)
        self.assertIsNone(result.snapshot)

    def test_private_non_user_actor_and_missing_binding_are_denied(self):
        agent_context = make_context(kind=IdentityKind.AGENT)
        result = self.service.authorize_read(agent_context, MEMORY_ID, NOW)
        self.assertIs(self.decision(result), AuthorizationDecision.DENY)

        self.service = MemoryAuthorizationService(
            self.resolver, None, grant_repository=self.grant_repository
        )
        result = self.service.authorize_read(make_context(), MEMORY_ID, NOW)
        self.assertIs(self.decision(result), AuthorizationDecision.DENY)

    def test_project_memory_requires_matching_scope_and_trusted_grant(self):
        self.memory_port.memory = make_memory(MemoryScopeKind.PROJECT, "project-1")
        self.grant_repository.grants = (make_grant(),)
        context = make_context(project_id="project-1", environment="development")
        result = self.service.authorize_read(context, MEMORY_ID, NOW)
        self.assertIs(self.decision(result), AuthorizationDecision.ALLOW)
        self.assertIsNotNone(result.snapshot)
        self.assertEqual(result.snapshot.revisions.project_revision.authority_id, "project-1")
        self.assertEqual(result.snapshot.revisions.environment_revision.authority_id, "development")
        self.assertEqual(result.snapshot.revisions.grant_revision.authority_id, "grant-1")
        self.assertEqual(result.snapshot.grant_expires_at, make_grant().expires_at)
        self.assertEqual(self.grant_repository.owner_requests, ["owner-1"])

    def test_project_memory_denies_cross_project_or_missing_grant(self):
        self.memory_port.memory = make_memory(MemoryScopeKind.PROJECT, "project-1")
        self.grant_repository.grants = (make_grant(),)
        context = make_context(project_id="another-project", environment="development")
        result = self.service.authorize_read(context, MEMORY_ID, NOW)
        self.assertIs(self.decision(result), AuthorizationDecision.DENY)
        self.assertEqual(self.grant_repository.owner_requests, [])

        context = make_context(project_id="project-1", environment="development")
        self.grant_repository.grants = ()
        result = self.service.authorize_read(context, MEMORY_ID, NOW)
        self.assertIs(self.decision(result), AuthorizationDecision.DENY)
        self.assertEqual(self.grant_repository.owner_requests, ["owner-1"])

    def test_project_memory_denies_if_grant_repository_fails_or_is_untyped(self):
        self.memory_port.memory = make_memory(MemoryScopeKind.PROJECT, "project-1")
        context = make_context(project_id="project-1", environment="development")
        self.grant_repository.error = TimeoutError("grant store unavailable")
        self.assertIs(
            self.decision(self.service.authorize_read(context, MEMORY_ID, NOW)),
            AuthorizationDecision.DENY,
        )
        self.grant_repository.error = None
        self.grant_repository.grants = [make_grant()]
        self.assertIs(
            self.decision(self.service.authorize_read(context, MEMORY_ID, NOW)),
            AuthorizationDecision.DENY,
        )

    def test_project_memory_requires_active_project_and_environment(self):
        self.memory_port.memory = make_memory(MemoryScopeKind.PROJECT, "project-1")
        self.grant_repository.grants = (make_grant(),)
        context = make_context(project_id="project-1", environment="development")
        self.project_port.status = "suspended"
        self.assertIs(
            self.decision(self.service.authorize_read(context, MEMORY_ID, NOW)),
            AuthorizationDecision.DENY,
        )
        self.project_port.status = "active"
        self.environment_port.status = "suspended"
        self.assertIs(
            self.decision(self.service.authorize_read(context, MEMORY_ID, NOW)),
            AuthorizationDecision.DENY,
        )

    def test_project_memory_requires_explicit_environment_and_repository(self):
        self.memory_port.memory = make_memory(MemoryScopeKind.PROJECT, "project-1")
        context = make_context(project_id="project-1")
        self.assertIs(
            self.decision(self.service.authorize_read(context, MEMORY_ID, NOW)),
            AuthorizationDecision.DENY,
        )
        context = make_context(project_id="project-1", environment="development")
        service_without_repository = MemoryAuthorizationService(
            self.resolver, self.binding
        )
        self.assertIs(
            self.decision(
                service_without_repository.authorize_read(context, MEMORY_ID, NOW)
            ),
            AuthorizationDecision.DENY,
        )

    def test_restricted_or_unapproved_version_is_denied(self):
        self.memory_port.version = make_version(
            classification=MemoryClassification.RESTRICTED
        )
        self.assertIs(
            self.decision(self.service.authorize_read(make_context(), MEMORY_ID, NOW)),
            AuthorizationDecision.DENY,
        )
        self.memory_port.version = make_version(
            status=MemoryVersionStatus.PENDING_REVIEW
        )
        self.assertIs(
            self.decision(self.service.authorize_read(make_context(), MEMORY_ID, NOW)),
            AuthorizationDecision.DENY,
        )

    def test_missing_current_version_or_invalid_time_is_denied(self):
        self.memory_port.memory = Memory(
            memory_id=MEMORY_ID,
            owner_id="owner-1",
            scope=MemoryScope(MemoryScopeKind.PRIVATE),
            current_approved_version_id=None,
            created_at=NOW,
            updated_at=NOW,
        )
        self.assertIs(
            self.decision(self.service.authorize_read(make_context(), MEMORY_ID, NOW)),
            AuthorizationDecision.DENY,
        )
        self.memory_port.memory = self.memory
        self.assertIs(
            self.decision(
                self.service.authorize_read(
                    make_context(), MEMORY_ID, datetime(2026, 11, 13, 12, 0)
                )
            ),
            AuthorizationDecision.DENY,
        )


if __name__ == "__main__":
    unittest.main()
