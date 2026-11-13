"""Reducer projection tests for v1 compatibility and exact v2 targets."""
import unittest
from datetime import datetime, timezone

from atlas.memory.consistency import (
    AuthorityKind,
    AuthorityRevision,
    AuthorizationRevisionSet,
    ReadAdmissionStatus,
)
from atlas.memory.journal import (
    ConsistencyPosition,
    ConsistencyRecordKind,
    ConsistencyRecoveryState,
    ConsistencyTransition,
    JournalEntry,
)
from atlas.memory.journal_reducer import (
    ConsistencyJournalReducer,
    reconstruct_read_target,
)
from atlas.memory.models import MemoryScope, MemoryScopeKind

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
DOMAIN = "schema-v2-reducer-domain"
MEMORY = "018bcfe5-7b3a-7cc2-98c4-dc0c0c074301"
VERSION = "018bcfe5-7b3a-7cc2-98c4-dc0c0c074302"
RECORDS = tuple(
    f"018bcfe5-7b3a-7cc2-98c4-dc0c0c074{n:03d}" for n in range(303, 307)
)


def revisions(scope):
    common = dict(
        memory_revision=AuthorityRevision(AuthorityKind.MEMORY, MEMORY, 1),
        version_revision=AuthorityRevision(AuthorityKind.MEMORY_VERSION, VERSION, 1),
        identity_revision=AuthorityRevision(AuthorityKind.IDENTITY, "identity-1", 1),
    )
    if scope is MemoryScopeKind.PROJECT:
        common.update(
            project_revision=AuthorityRevision(AuthorityKind.PROJECT, "project-1", 2),
            environment_revision=AuthorityRevision(AuthorityKind.ENVIRONMENT, "environment-1", 3),
            grant_revision=AuthorityRevision(AuthorityKind.GRANT, "grant-1", 4),
        )
    return AuthorizationRevisionSet(**common)


def admitted_v2(scope=MemoryScopeKind.PRIVATE):
    return ConsistencyTransition(
        record_id=RECORDS[0],
        schema_version=2,
        record_kind=ConsistencyRecordKind.READ_ADMITTED,
        operation_id="read:admission-v2",
        occurred_at=NOW,
        request_id="request-v2",
        actor_identity_id="identity-1",
        subject_user_id="owner-1" if scope is MemoryScopeKind.PRIVATE else None,
        owner_id="owner-1",
        memory_id=MEMORY,
        version_id=VERSION,
        snapshot_id="snapshot-v2",
        revisions=revisions(scope),
        admission_id="admission-v2",
        generation=5,
        route_ids=frozenset({"assistant-response"}),
        scope_kind=scope,
        scope_project_id="project-1" if scope is MemoryScopeKind.PROJECT else None,
    )


def recovery(transitions):
    entries = tuple(
        JournalEntry(ConsistencyPosition(DOMAIN, 1, index), transition)
        for index, transition in enumerate(transitions, start=1)
    )
    return ConsistencyRecoveryState(
        domain_id=DOMAIN,
        authority_epoch=1,
        checkpoint=None,
        entries=entries,
        head_sequence=len(entries),
        continuity_reference="fake-test-only",
    )


class JournalRecoveryProjectionV2Tests(unittest.TestCase):
    def test_v2_private_projection_preserves_exact_target_fields(self):
        transition = admitted_v2()
        projection = ConsistencyJournalReducer().reduce(recovery((transition,)))
        item = projection.admissions[0]
        self.assertTrue(item.recoverable)
        self.assertEqual(item.owner_id, "owner-1")
        self.assertIs(item.scope_kind, MemoryScopeKind.PRIVATE)
        self.assertIsNone(item.scope_project_id)
        self.assertEqual(item.admitted_at, NOW)
        self.assertEqual(item.route_ids, frozenset({"assistant-response"}))

    def test_v2_project_projection_preserves_exact_project_scope(self):
        transition = admitted_v2(MemoryScopeKind.PROJECT)
        projection = ConsistencyJournalReducer().reduce(recovery((transition,)))
        item = projection.admissions[0]
        self.assertTrue(item.recoverable)
        self.assertIs(item.scope_kind, MemoryScopeKind.PROJECT)
        self.assertEqual(item.scope_project_id, "project-1")
        self.assertEqual(item.revisions.project_revision.authority_id, "project-1")

    def test_v1_projection_is_historical_and_explicitly_non_recoverable(self):
        transition = ConsistencyTransition(
            record_id=RECORDS[0],
            schema_version=1,
            record_kind=ConsistencyRecordKind.READ_ADMITTED,
            operation_id="read:legacy",
            occurred_at=NOW,
            actor_identity_id="identity-1",
            memory_id=MEMORY,
            version_id=VERSION,
            snapshot_id="snapshot-legacy",
            revisions=revisions(MemoryScopeKind.PRIVATE),
            admission_id="legacy",
            generation=1,
            route_ids=frozenset({"assistant-response"}),
        )
        projection = ConsistencyJournalReducer().reduce(recovery((transition,)))
        item = projection.admissions[0]
        self.assertFalse(item.recoverable)
        self.assertIsNone(item.owner_id)
        self.assertIsNone(item.scope_kind)
        self.assertIsNone(item.scope_project_id)

    def test_v2_private_projection_reconstructs_exact_read_target(self):
        projection = ConsistencyJournalReducer().reduce(
            recovery((admitted_v2(MemoryScopeKind.PRIVATE),))
        )
        target = reconstruct_read_target(projection.admissions[0])
        self.assertIsNotNone(target)
        self.assertEqual(target.memory_id, MEMORY)
        self.assertEqual(target.version_id, VERSION)
        self.assertEqual(target.owner_id, "owner-1")
        self.assertEqual(target.scope, MemoryScope(MemoryScopeKind.PRIVATE))

    def test_v2_project_projection_reconstructs_exact_read_target(self):
        projection = ConsistencyJournalReducer().reduce(
            recovery((admitted_v2(MemoryScopeKind.PROJECT),))
        )
        target = reconstruct_read_target(projection.admissions[0])
        self.assertIsNotNone(target)
        self.assertEqual(
            target.scope, MemoryScope(MemoryScopeKind.PROJECT, "project-1")
        )

    def test_v1_projection_cannot_reconstruct_a_target_by_inference(self):
        transition = ConsistencyTransition(
            record_id=RECORDS[0],
            schema_version=1,
            record_kind=ConsistencyRecordKind.READ_ADMITTED,
            operation_id="read:legacy",
            occurred_at=NOW,
            actor_identity_id="identity-1",
            memory_id=MEMORY,
            version_id=VERSION,
            snapshot_id="snapshot-legacy",
            revisions=revisions(MemoryScopeKind.PRIVATE),
            admission_id="legacy",
            generation=1,
            route_ids=frozenset({"assistant-response"}),
        )
        projection = ConsistencyJournalReducer().reduce(recovery((transition,)))
        self.assertIsNone(reconstruct_read_target(projection.admissions[0]))

    def test_admission_terminal_receipt_is_preserved_in_projection(self):
        admitted = admitted_v2()
        endpoint_done = ConsistencyTransition(
            record_id=RECORDS[1],
            schema_version=1,
            record_kind=ConsistencyRecordKind.ENDPOINT_COMPLETED,
            operation_id="read:admission-v2",
            occurred_at=NOW,
            admission_id="admission-v2",
            endpoint_id="assistant-response",
            generation=5,
            receipt_id="endpoint-terminal-receipt",
            final_sequence=0,
        )
        reconciled = ConsistencyTransition(
            record_id=RECORDS[2],
            schema_version=1,
            record_kind=ConsistencyRecordKind.ADMISSION_RECONCILED,
            operation_id="read:admission-v2",
            occurred_at=NOW,
            admission_id="admission-v2",
            generation=5,
            receipt_id="admission-terminal-receipt",
            admission_terminal_status=ReadAdmissionStatus.COMPLETED,
        )
        projection = ConsistencyJournalReducer().reduce(
            recovery((admitted, endpoint_done, reconciled))
        )
        item = projection.admissions[0]
        self.assertIs(item.status, ReadAdmissionStatus.COMPLETED)
        self.assertEqual(item.terminal_receipt_id, "admission-terminal-receipt")
        self.assertEqual(
            item.endpoints[0].terminal_receipt_id, "endpoint-terminal-receipt"
        )
        self.assertEqual(
            item.endpoints[0].terminal_operation_id, "read:admission-v2"
        )
        self.assertEqual(item.endpoints[0].terminal_generation, 5)
        self.assertEqual(item.endpoints[0].final_sequence, 0)
        self.assertEqual(item.terminal_operation_id, "read:admission-v2")
        self.assertEqual(item.terminal_generation, 5)


if __name__ == "__main__":
    unittest.main()
