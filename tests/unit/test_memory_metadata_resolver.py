import unittest

from atlas.core.errors import ContractError
from datetime import datetime, timezone

from atlas.authorization.memory_metadata_resolver import MemoryMetadataResolver
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
OTHER_MEMORY_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a14"
VERSION_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a12"
OTHER_VERSION_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a15"


def make_memory(memory_id=MEMORY_ID):
    return Memory(
        memory_id=memory_id,
        owner_id="owner-1",
        scope=MemoryScope(MemoryScopeKind.PRIVATE),
        current_approved_version_id=VERSION_ID,
        created_at=NOW,
        updated_at=NOW,
    )


class StubMemoryPort:
    def __init__(self, memory=None, version=None, error=None):
        self.memory = memory
        self.version = version
        self.error = error
        self.memory_requests = []
        self.version_requests = []

    def get_memory(self, memory_id):
        self.memory_requests.append(memory_id)
        if self.error:
            raise self.error
        return self.memory

    def get_version(self, memory_id, version_id):
        self.version_requests.append((memory_id, version_id))
        if self.error:
            raise self.error
        return self.version


class StubProjectPort:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.requests = []

    def get_project(self, project_id):
        self.requests.append(project_id)
        if self.error:
            raise self.error
        return self.result


class StubEnvironmentPort:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.requests = []

    def get_environment(self, environment_id):
        self.requests.append(environment_id)
        if self.error:
            raise self.error
        return self.result


class MemoryMetadataResolverTests(unittest.TestCase):
    def setUp(self):
        self.memory = make_memory()
        self.version = MemoryVersionMetadata(
            version_id=VERSION_ID,
            memory_id=MEMORY_ID,
            status=MemoryVersionStatus.APPROVED,
            classification=MemoryClassification.CONFIDENTIAL,
            parent_version_id=None,
            revision=1,
        )
        self.memory_port = StubMemoryPort(self.memory, self.version)
        self.project_port = StubProjectPort(ProjectMetadata("project-1", "active", 1))
        self.environment_port = StubEnvironmentPort(
            EnvironmentMetadata("environment-1", "active", 1)
        )
        self.resolver = MemoryMetadataResolver(
            self.memory_port, self.project_port, self.environment_port
        )

    def test_resolves_memory_by_exact_id(self):
        self.assertEqual(self.resolver.resolve_memory(MEMORY_ID), self.memory)
        self.assertEqual(self.memory_port.memory_requests, [MEMORY_ID])

    def test_rejects_memory_result_with_different_id(self):
        self.memory_port.memory = make_memory(OTHER_MEMORY_ID)
        self.assertIsNone(self.resolver.resolve_memory(MEMORY_ID))

    def test_resolves_version_only_under_exact_parent_and_child_ids(self):
        self.assertEqual(
            self.resolver.resolve_version(MEMORY_ID, VERSION_ID), self.version
        )
        self.assertEqual(
            self.memory_port.version_requests, [(MEMORY_ID, VERSION_ID)]
        )

    def test_rejects_version_with_mismatched_parent_or_child(self):
        self.memory_port.version = MemoryVersionMetadata(
            version_id=VERSION_ID,
            memory_id=OTHER_MEMORY_ID,
            status=MemoryVersionStatus.APPROVED,
            classification=MemoryClassification.CONFIDENTIAL,
            parent_version_id=None,
            revision=1,
        )
        self.assertIsNone(self.resolver.resolve_version(MEMORY_ID, VERSION_ID))

        self.memory_port.version = MemoryVersionMetadata(
            version_id=OTHER_VERSION_ID,
            memory_id=MEMORY_ID,
            status=MemoryVersionStatus.APPROVED,
            classification=MemoryClassification.CONFIDENTIAL,
            parent_version_id=None,
            revision=1,
        )
        self.assertIsNone(self.resolver.resolve_version(MEMORY_ID, VERSION_ID))

    def test_resolves_project_and_rejects_mismatched_id(self):
        self.assertEqual(self.resolver.resolve_project("project-1").status, "active")
        self.project_port.result = ProjectMetadata("other-project", "active", 1)
        self.assertIsNone(self.resolver.resolve_project("project-1"))

    def test_resolves_environment_and_rejects_mismatched_id(self):
        self.assertEqual(
            self.resolver.resolve_environment("environment-1").status, "active"
        )
        self.environment_port.result = EnvironmentMetadata("other", "active", 1)
        self.assertIsNone(self.resolver.resolve_environment("environment-1"))

    def test_memory_and_version_revisions_are_positive(self):
        from atlas.memory.models import MemoryVersion, MemoryProvenance, ProvenanceContext, SourceKind
        provenance = MemoryProvenance(
            source_kind=SourceKind.USER_INPUT,
            source_ref=None,
            captured_at=NOW,
            captured_by="identity-1",
            origin_context=ProvenanceContext(
                origin="test",
                actor_identity_id="identity-1",
                request_id="request-1",
                correlation_id="correlation-1",
            ),
        )
        with self.assertRaises(ContractError):
            MemoryVersion(
                version_id=VERSION_ID,
                memory_id=MEMORY_ID,
                version_number=1,
                content="content",
                classification=MemoryClassification.CONFIDENTIAL,
                status=MemoryVersionStatus.PENDING_REVIEW,
                provenance=provenance,
                parent_version_id=None,
                created_at=NOW,
                submitted_at=NOW,
                revision=0,
            )

    def test_memory_revision_is_positive_and_immutable(self):
        with self.assertRaises(ContractError):
            Memory(
                memory_id=MEMORY_ID,
                owner_id="owner-1",
                scope=MemoryScope(MemoryScopeKind.PRIVATE),
                current_approved_version_id=VERSION_ID,
                created_at=NOW,
                updated_at=NOW,
                revision=0,
            )

    def test_metadata_requires_positive_canonical_revisions(self):
        with self.assertRaises(ContractError):
            MemoryVersionMetadata(
                version_id=VERSION_ID,
                memory_id=MEMORY_ID,
                status=MemoryVersionStatus.APPROVED,
                classification=MemoryClassification.CONFIDENTIAL,
                parent_version_id=None,
                revision=0,
            )
        with self.assertRaises(ContractError):
            ProjectMetadata("project-1", "active", 0)
        with self.assertRaises(ContractError):
            EnvironmentMetadata("environment-1", "active", 0)

    def test_invalid_ids_fail_closed_without_port_calls(self):
        self.assertIsNone(self.resolver.resolve_memory(""))
        self.assertIsNone(self.resolver.resolve_version(MEMORY_ID, ""))
        self.assertIsNone(self.resolver.resolve_project(" "))
        self.assertIsNone(self.resolver.resolve_environment(None))
        self.assertEqual(self.memory_port.memory_requests, [])
        self.assertEqual(self.memory_port.version_requests, [])
        self.assertEqual(self.project_port.requests, [])
        self.assertEqual(self.environment_port.requests, [])

    def test_port_errors_and_missing_results_fail_closed(self):
        self.memory_port.error = TimeoutError("metadata timeout")
        self.assertIsNone(self.resolver.resolve_memory(MEMORY_ID))
        self.assertIsNone(self.resolver.resolve_version(MEMORY_ID, VERSION_ID))
        self.memory_port.error = None
        self.memory_port.memory = None
        self.memory_port.version = None
        self.assertIsNone(self.resolver.resolve_memory(MEMORY_ID))
        self.assertIsNone(self.resolver.resolve_version(MEMORY_ID, VERSION_ID))

        self.project_port.error = RuntimeError("project source unavailable")
        self.environment_port.error = RuntimeError("environment source unavailable")
        self.assertIsNone(self.resolver.resolve_project("project-1"))
        self.assertIsNone(self.resolver.resolve_environment("environment-1"))

    def test_untyped_results_fail_closed(self):
        self.memory_port.memory = {"memory_id": MEMORY_ID}
        self.memory_port.version = {"version_id": VERSION_ID}
        self.project_port.result = {"project_id": "project-1"}
        self.environment_port.result = {"environment_id": "environment-1"}
        self.assertIsNone(self.resolver.resolve_memory(MEMORY_ID))
        self.assertIsNone(self.resolver.resolve_version(MEMORY_ID, VERSION_ID))
        self.assertIsNone(self.resolver.resolve_project("project-1"))
        self.assertIsNone(self.resolver.resolve_environment("environment-1"))


if __name__ == "__main__":
    unittest.main()
