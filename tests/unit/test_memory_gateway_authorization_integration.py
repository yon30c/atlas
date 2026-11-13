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
from atlas.memory.consistency import (
    DeliveryRouteSet,
    EgressReceipt,
    EndpointCompletionReceipt,
    ReadAdmission,
    ReadAdmissionStatus,
    ReadTarget,
    ReconciliationResult,
)
from atlas.memory.gateway import MemoryGatewayService
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
    def __init__(self):
        self.calls = []
        self.handle = None

    def read_version_if_admitted(self, snapshot, admission):
        self.calls.append((snapshot, admission))
        self.handle = FakeProtectedHandle(admission, snapshot.classification)
        return self.handle


class FakeProtectedHandle:
    def __init__(self, admission, classification):
        self.handle_id = f"handle:{admission.admission_id}"
        self.admission_id = admission.admission_id
        self.memory_id = admission.target.memory_id
        self.version_id = admission.target.version_id
        self.classification = classification


class FakeReadAuthority:
    def __init__(self):
        self.admissions = []
        self.acks = []

    def admit_read(self, snapshot, routes, now):
        admission = ReadAdmission(
            admission_id=f"admission-{len(self.admissions) + 1}",
            snapshot_id=snapshot.snapshot_id,
            target=ReadTarget(
                snapshot.memory_id, snapshot.version_id,
                snapshot.owner_id, snapshot.scope
            ),
            generation=1,
            route_ids=routes.route_ids,
            status=ReadAdmissionStatus.ADMITTED,
            admitted_at=NOW,
        )
        self.admissions.append(admission)
        return admission

    def record_endpoint_ack(self, receipt):
        self.acks.append(receipt)
        return True

    def reconcile(self, operation_id):
        return ReconciliationResult(operation_id, frozenset(), frozenset())


class FakeProtectedEgress:
    def commit_and_emit(self, admission, handle, endpoint_id, emission_id, sequence, now):
        return EgressReceipt(
            admission.admission_id, endpoint_id, emission_id, sequence,
            admission.generation, now
        )

    def finish(self, admission, operation_id, endpoint_id, final_sequence, now):
        return EndpointCompletionReceipt(
            operation_id, admission.admission_id, endpoint_id,
            admission.generation, final_sequence, now
        )

    def fence(self, admission, operation_id, endpoint_id, new_generation, now):
        return None

    def reconcile(self, admission, endpoint_id):
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
        self.content = SpyContentPort()
        self.authority = FakeReadAuthority()
        self.routes = DeliveryRouteSet(frozenset({"assistant-response"}))
        self.gateway = MemoryGatewayService(
            authorization,
            self.content,
            self.authority,
            FakeProtectedEgress(),
            self.routes,
            FixedClock(),
        )

    def test_private_owner_opens_protected_handle_after_real_cam_allows(self):
        result = self.gateway.get_version(make_context(), MEMORY_ID, VERSION_ID)

        self.assertIsNotNone(result)
        self.assertFalse(hasattr(result, "handle"))
        self.assertFalse(hasattr(result, "snapshot"))
        self.assertFalse(hasattr(result, "admission"))
        self.assertIsNotNone(self.content.handle)
        self.assertEqual(len(self.content.calls), 1)
        self.assertEqual(self.identity_port.calls, ["identity-1"])
        self.assertEqual(self.grant_repository.owner_requests, [])

    def test_private_different_authenticated_user_never_reads_content(self):
        self.identity_port.subject_user_id = "another-user"

        result = self.gateway.get_version(make_context(), MEMORY_ID, VERSION_ID)

        self.assertIsNone(result)
        self.assertEqual(self.content.calls, [])

    def test_project_memory_with_exact_grant_opens_protected_handle(self):
        self.memory_port.memory = make_memory(MemoryScopeKind.PROJECT, PROJECT_ID)
        self.grant_repository.grants = (make_grant(),)

        result = self.gateway.get_version(
            make_context(PROJECT_ID, ENVIRONMENT),
            MEMORY_ID,
            VERSION_ID,
        )

        self.assertIsNotNone(result)
        self.assertIs(result.handle, self.content.handle)
        self.assertEqual(len(self.content.calls), 1)
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
