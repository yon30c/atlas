"""Acceptance tests for versioned READ_ADMITTED schema v2."""
import unittest
from dataclasses import replace
from datetime import datetime, timezone

from atlas.core.errors import ContractError
from atlas.memory.consistency import (
    AuthorityKind,
    AuthorityRevision,
    AuthorizationRevisionSet,
    ReadAdmissionStatus,
)
from atlas.memory.journal import ConsistencyRecordKind, ConsistencyTransition
from atlas.memory.models import MemoryScopeKind

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
MEMORY = "018bcfe5-7b3a-7cc2-98c4-dc0c0c074201"
VERSION = "018bcfe5-7b3a-7cc2-98c4-dc0c0c074202"
RECORD = "018bcfe5-7b3a-7cc2-98c4-dc0c0c074203"


def private_v2(**overrides):
    values = dict(
        record_id=RECORD,
        schema_version=2,
        record_kind=ConsistencyRecordKind.READ_ADMITTED,
        operation_id="read:admission-v2",
        occurred_at=NOW,
        request_id="request-v2",
        actor_identity_id="identity-v2",
        subject_user_id="owner-v2",
        owner_id="owner-v2",
        memory_id=MEMORY,
        version_id=VERSION,
        snapshot_id="snapshot-v2",
        revisions=AuthorizationRevisionSet(
            memory_revision=AuthorityRevision(AuthorityKind.MEMORY, MEMORY, 1),
            version_revision=AuthorityRevision(AuthorityKind.MEMORY_VERSION, VERSION, 1),
            identity_revision=AuthorityRevision(AuthorityKind.IDENTITY, "identity-v2", 1),
        ),
        admission_id="admission-v2",
        generation=1,
        route_ids=frozenset({"assistant-response"}),
        scope_kind=MemoryScopeKind.PRIVATE,
    )
    values.update(overrides)
    return ConsistencyTransition(**values)


def project_v2(**overrides):
    values = dict(
        record_id=RECORD,
        schema_version=2,
        record_kind=ConsistencyRecordKind.READ_ADMITTED,
        operation_id="read:admission-project",
        occurred_at=NOW,
        request_id="request-project",
        actor_identity_id="agent-identity",
        subject_user_id=None,
        owner_id="owner-project",
        memory_id=MEMORY,
        version_id=VERSION,
        snapshot_id="snapshot-project",
        revisions=AuthorizationRevisionSet(
            memory_revision=AuthorityRevision(AuthorityKind.MEMORY, MEMORY, 1),
            version_revision=AuthorityRevision(AuthorityKind.MEMORY_VERSION, VERSION, 1),
            identity_revision=AuthorityRevision(AuthorityKind.IDENTITY, "agent-identity", 1),
            project_revision=AuthorityRevision(AuthorityKind.PROJECT, "project-1", 3),
            environment_revision=AuthorityRevision(AuthorityKind.ENVIRONMENT, "environment-1", 2),
            grant_revision=AuthorityRevision(AuthorityKind.GRANT, "grant-1", 4),
        ),
        admission_id="admission-project",
        generation=2,
        route_ids=frozenset({"assistant-response", "api-response"}),
        scope_kind=MemoryScopeKind.PROJECT,
        scope_project_id="project-1",
    )
    values.update(overrides)
    return ConsistencyTransition(**values)


class ReadAdmissionSchemaV2Tests(unittest.TestCase):
    def test_private_scope_v2_accepts_exact_owner_bound_scope(self):
        item = private_v2()
        self.assertIs(item.scope_kind, MemoryScopeKind.PRIVATE)
        self.assertIsNone(item.scope_project_id)

    def test_project_scope_v2_accepts_exact_project_revision_binding(self):
        item = project_v2()
        self.assertIs(item.scope_kind, MemoryScopeKind.PROJECT)
        self.assertEqual(item.scope_project_id, "project-1")

    def test_private_scope_rejects_project_id(self):
        with self.assertRaises(ContractError):
            private_v2(scope_project_id="project-1")

    def test_private_scope_rejects_subject_other_than_owner(self):
        with self.assertRaises(ContractError):
            private_v2(subject_user_id="another-user")

    def test_private_scope_rejects_project_environment_or_grant_revisions(self):
        revisions = AuthorizationRevisionSet(
            memory_revision=AuthorityRevision(AuthorityKind.MEMORY, MEMORY, 1),
            version_revision=AuthorityRevision(AuthorityKind.MEMORY_VERSION, VERSION, 1),
            identity_revision=AuthorityRevision(AuthorityKind.IDENTITY, "identity-v2", 1),
            project_revision=AuthorityRevision(AuthorityKind.PROJECT, "project-1", 1),
        )
        with self.assertRaises(ContractError):
            private_v2(revisions=revisions)

    def test_project_scope_requires_project_id(self):
        with self.assertRaises(ContractError):
            project_v2(scope_project_id=None)

    def test_project_scope_rejects_mismatched_project_revision_id(self):
        with self.assertRaises(ContractError):
            project_v2(scope_project_id="another-project")

    def test_project_scope_requires_environment_and_grant_revisions(self):
        revisions = AuthorizationRevisionSet(
            memory_revision=AuthorityRevision(AuthorityKind.MEMORY, MEMORY, 1),
            version_revision=AuthorityRevision(AuthorityKind.MEMORY_VERSION, VERSION, 1),
            identity_revision=AuthorityRevision(AuthorityKind.IDENTITY, "agent-identity", 1),
            project_revision=AuthorityRevision(AuthorityKind.PROJECT, "project-1", 3),
        )
        with self.assertRaises(ContractError):
            project_v2(revisions=revisions)

    def test_v2_requires_owner_actor_request_and_scope_kind(self):
        for field in ("owner_id", "actor_identity_id", "request_id", "scope_kind"):
            values = dict(
                owner_id="owner-v2",
                actor_identity_id="identity-v2",
                request_id="request-v2",
                scope_kind=MemoryScopeKind.PRIVATE,
            )
            values[field] = None
            with self.subTest(field=field), self.assertRaises(ContractError):
                private_v2(**values)

    def test_v1_remains_readable_without_scope(self):
        item = ConsistencyTransition(
            record_id=RECORD,
            schema_version=1,
            record_kind=ConsistencyRecordKind.READ_ADMITTED,
            operation_id="read:legacy",
            occurred_at=NOW,
            actor_identity_id="identity-v1",
            memory_id=MEMORY,
            version_id=VERSION,
            snapshot_id="snapshot-v1",
            revisions=AuthorizationRevisionSet(
                memory_revision=AuthorityRevision(AuthorityKind.MEMORY, MEMORY, 1),
                version_revision=AuthorityRevision(AuthorityKind.MEMORY_VERSION, VERSION, 1),
                identity_revision=AuthorityRevision(AuthorityKind.IDENTITY, "identity-v1", 1),
            ),
            admission_id="legacy",
            generation=1,
            route_ids=frozenset({"assistant-response"}),
        )
        self.assertEqual(item.schema_version, 1)
        self.assertIsNone(item.scope_kind)

    def test_v2_is_restricted_to_read_admitted(self):
        with self.assertRaises(ContractError):
            ConsistencyTransition(
                record_id=RECORD,
                schema_version=2,
                record_kind=ConsistencyRecordKind.READ_ACTIVATED,
                operation_id="read:admission-v2",
                occurred_at=NOW,
                admission_id="admission-v2",
                generation=1,
            )

    def test_v1_cannot_smuggle_v2_scope_fields(self):
        with self.assertRaises(ContractError):
            private_v2(schema_version=1)


if __name__ == "__main__":
    unittest.main()
