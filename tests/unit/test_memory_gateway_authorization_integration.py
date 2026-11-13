"""Pruebas integradas de CAM y MemoryGatewayService.

Usan el servicio de autorización real y adaptadores en memoria de prueba;
no demuestran integración con almacenamiento o proveedores reales.
"""
import unittest
from datetime import datetime, timedelta, timezone

from atlas.authorization.identity_binding import AuthenticatedUserSubject
from atlas.authorization.memory_metadata_resolver import MemoryMetadataResolver
from atlas.authorization.memory_service import MemoryAuthorizationService
from atlas.authorization.models import Grant, GrantResourceScope, AuthorizationDecision
from atlas.core.context import OperationContext
from atlas.core.identity import Identity, IdentityKind, IdentityStatus
from atlas.memory.gateway import MemoryGatewayService
from atlas.memory.metadata import (
    EnvironmentMetadata,
    MemoryVersionMetadata,
    ProjectMetadata,
)
from atlas.memory.models import (
    Memory,
    MemoryClassification,
    MemoryProvenance,
    MemoryScope,
    MemoryScopeKind,
    MemoryVersion,
    MemoryVersionStatus,
    ProvenanceContext,
    SourceKind,
)

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
MEMORY_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a11"
VERSION_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a12"
OTHER_MEMORY_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a13"
PROJECT_ID = "project-1"
ENVIRONMENT = "development"


class FakeMemoryMetadataPort:
    def __init__(self, memory, version):
        self.memory = memory
        self.version = version

    def get_memory(self, memory_id):
        return self.memory if self.memory and self.memory.memory_id == memory_id else None

    def get_version(self, memory_id, version_id):
        if (
            self.version
            and self.version.memory_id == memory_id
            and self.version.version_id == version_id
        ):
            return self.version
        return None


class FakeProjectMetadataPort:
    def get_project(self, project_id):
        return ProjectMetadata(project_id, "active", 1) if project_id == PROJECT_ID else None


class FakeEnvironmentMetadataPort:
    def get_environment(self, environment_id):
        return (
            EnvironmentMetadata(environment_id, "active", 1)
            if environment_id == ENVIRONMENT
            else None
        )


class FakeIdentityBindingPort:
    def __init__(self, subject_user_id="owner-1", actor_identity_id="identity-1"):
        self.subject_user_id = subject_user_id
        self.actor_identity_id = actor_identity_id
        self.calls = []

    def resolve_user_subject(self, actor_identity_id):
        self.calls.append(actor_identity_id)
        return AuthenticatedUserSubject(
            self.actor_identity_id,
            self.subject_user_id,
            True,
            1,
        )


class FakeGrantRepository:
    def __init__(self, grants=()):
        self.grants = grants
        self.owner_requests = []

    def list_by_owner(self, owner_user_id):
        self.owner_requests.append(owner_user_id)
        return self.grants


class SpyContentPort:
    def __init__(self, version):
        self.version = version
        self.calls = []

    def get_version_content(self, memory_id, version_id):
        self.calls.append((memory_id, version_id))
        if (
            self.version
            and self.version.memory_id == memory_id
            and self.version.version_id == version_id
        ):
            return self.version
        return None


class FixedClock:
    def now(self):
        return NOW


def make_context(project_id=None, environment=None):
    return OperationContext(
        request_id="request-1",
        correlation_id="correlation-1",
        actor=Identity("identity-1", IdentityKind.USER, IdentityStatus.ACTIVE),
        user_id="untrusted-context-user",
        origin="integration-test",
        delegation=None,
        project_id=project_id,
        environment=environment,
        purpose="verify integrated memory read authorization",
        classification="internal",
        created_at=NOW,
    )


def make_memory(scope=MemoryScopeKind.PRIVATE, project_id=None):
    return Memory(
        memory_id=MEMORY_ID,
        owner_id="owner-1",
        scope=MemoryScope(scope, project_id),
        current_approved_version_id=VERSION_ID,
        created_at=NOW - timedelta(days=1),
        updated_at=NOW,
    )


def make_metadata_version():
    return MemoryVersionMetadata(
        version_id=VERSION_ID,
        memory_id=MEMORY_ID,
        status=MemoryVersionStatus.APPROVED,
        classification=MemoryClassification.CONFIDENTIAL,
        parent_version_id=None,
        revision=1,
    )


def make_content_version():
    provenance = MemoryProvenance(
        source_kind=SourceKind.USER_INPUT,
        source_ref=None,
        captured_at=NOW,
        captured_by="identity-1",
        origin_context=ProvenanceContext(
            origin="integration-test",
            actor_identity_id="identity-1",
            request_id="request-1",
            correlation_id="correlation-1",
        ),
    )
    return MemoryVersion(
        version_id=VERSION_ID,
        memory_id=MEMORY_ID,
        version_number=1,
        content="contenido protegido de integración",
        classification=MemoryClassification.CONFIDENTIAL,
        status=MemoryVersionStatus.APPROVED,
        provenance=provenance,
        parent_version_id=None,
        created_at=NOW - timedelta(days=1),
        submitted_at=NOW - timedelta(days=1),
        reviewed_at=NOW,
        reviewed_by="owner-1",
    )


def make_grant(project_id=PROJECT_ID, resource_ids=None):
    return Grant(
        grant_id="grant-1",
        owner_user_id="owner-1",
        subject_identity_id="identity-1",
        project_id=project_id,
        environment=ENVIRONMENT,
        resource_scope=GrantResourceScope(
            "memory",
            frozenset(resource_ids if resource_ids is not None else {MEMORY_ID}),
        ),
        actions=frozenset({"memory.read"}),
        issued_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=1),
    )


class MemoryGatewayAuthorizationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.memory_port = FakeMemoryMetadataPort(make_memory(), make_metadata_version())
        self.project_port = FakeProjectMetadataPort()
        self.environment_port = FakeEnvironmentMetadataPort()
        self.identity_port = FakeIdentityBindingPort()
        self.grant_repository = FakeGrantRepository()
        resolver = MemoryMetadataResolver(
            self.memory_port,
            self.project_port,
            self.environment_port,
        )
        authorization = MemoryAuthorizationService(
            resolver,
            self.identity_port,
            grant_repository=self.grant_repository,
        )
        self.content = SpyContentPort(make_content_version())
        self.gateway = MemoryGatewayService(
            authorization,
            self.content,
            FixedClock(),
        )

    def test_private_owner_reads_content_after_real_cam_allows(self):
        result = self.gateway.get_version(make_context(), MEMORY_ID, VERSION_ID)

        self.assertIs(result, self.content.version)
        self.assertEqual(self.content.calls, [(MEMORY_ID, VERSION_ID)])
        self.assertEqual(self.identity_port.calls, ["identity-1"])
        self.assertEqual(self.grant_repository.owner_requests, [])

    def test_private_different_authenticated_user_never_reads_content(self):
        self.identity_port.subject_user_id = "another-user"

        result = self.gateway.get_version(make_context(), MEMORY_ID, VERSION_ID)

        self.assertIsNone(result)
        self.assertEqual(self.content.calls, [])

    def test_project_memory_with_exact_grant_reads_content(self):
        self.memory_port.memory = make_memory(MemoryScopeKind.PROJECT, PROJECT_ID)
        self.grant_repository.grants = (make_grant(),)

        result = self.gateway.get_version(
            make_context(PROJECT_ID, ENVIRONMENT),
            MEMORY_ID,
            VERSION_ID,
        )

        self.assertIs(result, self.content.version)
        self.assertEqual(self.content.calls, [(MEMORY_ID, VERSION_ID)])
        self.assertEqual(self.grant_repository.owner_requests, ["owner-1"])

    def test_project_memory_without_grant_never_reads_content(self):
        self.memory_port.memory = make_memory(MemoryScopeKind.PROJECT, PROJECT_ID)
        self.grant_repository.grants = ()

        result = self.gateway.get_version(
            make_context(PROJECT_ID, ENVIRONMENT),
            MEMORY_ID,
            VERSION_ID,
        )

        self.assertIsNone(result)
        self.assertEqual(self.content.calls, [])

    def test_project_memory_with_grant_for_another_project_is_denied(self):
        self.memory_port.memory = make_memory(MemoryScopeKind.PROJECT, PROJECT_ID)
        self.grant_repository.grants = (make_grant(project_id="another-project"),)

        result = self.gateway.get_version(
            make_context(PROJECT_ID, ENVIRONMENT),
            MEMORY_ID,
            VERSION_ID,
        )

        self.assertIsNone(result)
        self.assertEqual(self.content.calls, [])

    def test_project_memory_with_grant_for_another_memory_id_is_denied(self):
        self.memory_port.memory = make_memory(MemoryScopeKind.PROJECT, PROJECT_ID)
        self.grant_repository.grants = (
            make_grant(resource_ids={OTHER_MEMORY_ID}),
        )

        result = self.gateway.get_version(
            make_context(PROJECT_ID, ENVIRONMENT),
            MEMORY_ID,
            VERSION_ID,
        )

        self.assertIsNone(result)
        self.assertEqual(self.content.calls, [])

    def test_invalid_identity_binding_fails_closed_before_content_read(self):
        self.identity_port.actor_identity_id = "different-actor"

        result = self.gateway.get_version(make_context(), MEMORY_ID, VERSION_ID)

        self.assertIsNone(result)
        self.assertEqual(self.content.calls, [])


    def test_mismatched_canonical_memory_metadata_fails_closed(self):
        self.memory_port.memory = Memory(
            memory_id=OTHER_MEMORY_ID,
            owner_id="owner-1",
            scope=MemoryScope(MemoryScopeKind.PRIVATE),
            current_approved_version_id=VERSION_ID,
            created_at=NOW - timedelta(days=1),
            updated_at=NOW,
        )

        result = self.gateway.get_version(make_context(), MEMORY_ID, VERSION_ID)

        self.assertIsNone(result)
        self.assertEqual(self.content.calls, [])

    def test_missing_canonical_memory_metadata_fails_closed(self):
        self.memory_port.memory = None

        result = self.gateway.get_version(make_context(), MEMORY_ID, VERSION_ID)

        self.assertIsNone(result)
        self.assertEqual(self.content.calls, [])


if __name__ == "__main__":
    unittest.main()
