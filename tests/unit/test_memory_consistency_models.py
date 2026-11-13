import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

from atlas.core.errors import ContractError
from atlas.memory.consistency import (
    AuthorityKind,
    AuthorityRevision,
    AuthorizationInvalidation,
    AuthorizationRevisionSet,
    AuthorizationSnapshot,
    DeliveryRouteSet,
    EndpointFenceReceipt,
    ReadAdmission,
    ReadAdmissionStatus,
    ReadTarget,
)
from atlas.memory.models import (
    MemoryClassification,
    MemoryScope,
    MemoryScopeKind,
    MemoryVersionStatus,
)


NOW = datetime(2026, 11, 13, 16, 0, tzinfo=timezone.utc)
MEMORY_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a11"
VERSION_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a12"


def revision(kind, identifier, number=1):
    return AuthorityRevision(kind, identifier, number)


def private_revisions():
    return AuthorizationRevisionSet(
        memory_revision=revision(AuthorityKind.MEMORY, MEMORY_ID),
        version_revision=revision(AuthorityKind.MEMORY_VERSION, VERSION_ID),
        identity_revision=revision(AuthorityKind.IDENTITY, "identity-1"),
    )


def private_snapshot():
    return AuthorizationSnapshot(
        snapshot_id="snapshot-1",
        decision_id="decision-1",
        request_id="request-1",
        action="memory.read",
        actor_identity_id="identity-1",
        subject_user_id="user-1",
        memory_id=MEMORY_ID,
        version_id=VERSION_ID,
        owner_id="user-1",
        scope=MemoryScope(MemoryScopeKind.PRIVATE),
        revisions=private_revisions(),
        version_status=MemoryVersionStatus.APPROVED,
        classification=MemoryClassification.CONFIDENTIAL,
        issued_at=NOW,
    )


def admission(status=ReadAdmissionStatus.ADMITTED):
    return ReadAdmission(
        admission_id="admission-1",
        snapshot_id="snapshot-1",
        target=ReadTarget(
            memory_id=MEMORY_ID,
            version_id=VERSION_ID,
            owner_id="user-1",
            scope=MemoryScope(MemoryScopeKind.PRIVATE),
        ),
        generation=1,
        route_ids=frozenset({"assistant-response"}),
        status=status,
        admitted_at=NOW,
        terminal_evidence_id=("receipt-1" if status in (ReadAdmissionStatus.COMPLETED, ReadAdmissionStatus.CANCELLED) else None),
    )


class MemoryConsistencyModelTests(unittest.TestCase):
    def test_revision_requires_positive_integer_and_typed_authority(self):
        with self.assertRaises(ContractError):
            AuthorityRevision(AuthorityKind.MEMORY, MEMORY_ID, 0)
        with self.assertRaises(ContractError):
            AuthorityRevision("memory", MEMORY_ID, 1)
        with self.assertRaises(ContractError):
            AuthorityRevision(AuthorityKind.MEMORY, MEMORY_ID, True)

    def test_revision_set_requires_exact_authority_kinds(self):
        with self.assertRaises(ContractError):
            AuthorizationRevisionSet(
                memory_revision=revision(AuthorityKind.PROJECT, "p1"),
                version_revision=revision(AuthorityKind.MEMORY_VERSION, VERSION_ID),
                identity_revision=revision(AuthorityKind.IDENTITY, "identity-1"),
            )

    def test_private_snapshot_has_no_project_or_grant_revisions(self):
        snapshot = private_snapshot()
        self.assertEqual(snapshot.scope.kind, MemoryScopeKind.PRIVATE)
        with self.assertRaises(ContractError):
            AuthorizationSnapshot(
                snapshot_id="s2",
                decision_id="d2",
                request_id="r2",
                action="memory.read",
                actor_identity_id="identity-1",
                subject_user_id="user-1",
                memory_id=MEMORY_ID,
                version_id=VERSION_ID,
                owner_id="user-1",
                scope=MemoryScope(MemoryScopeKind.PRIVATE),
                revisions=AuthorizationRevisionSet(
                    memory_revision=revision(AuthorityKind.MEMORY, MEMORY_ID),
                    version_revision=revision(AuthorityKind.MEMORY_VERSION, VERSION_ID),
                    identity_revision=revision(AuthorityKind.IDENTITY, "identity-1"),
                    grant_revision=revision(AuthorityKind.GRANT, "grant-1"),
                ),
                version_status=MemoryVersionStatus.APPROVED,
                classification=MemoryClassification.CONFIDENTIAL,
                issued_at=NOW,
            )

    def test_snapshot_rejects_wrong_target_revision_or_non_approved_version(self):
        with self.assertRaises(ContractError):
            AuthorizationSnapshot(
                snapshot_id="s",
                decision_id="d",
                request_id="r",
                action="memory.read",
                actor_identity_id="identity-1",
                subject_user_id="user-1",
                memory_id=MEMORY_ID,
                version_id=VERSION_ID,
                owner_id="user-1",
                scope=MemoryScope(MemoryScopeKind.PRIVATE),
                revisions=AuthorizationRevisionSet(
                    memory_revision=revision(AuthorityKind.MEMORY, MEMORY_ID),
                    version_revision=revision(AuthorityKind.MEMORY_VERSION, "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a13"),
                    identity_revision=revision(AuthorityKind.IDENTITY, "identity-1"),
                ),
                version_status=MemoryVersionStatus.APPROVED,
                classification=MemoryClassification.CONFIDENTIAL,
                issued_at=NOW,
            )
        with self.assertRaises(ContractError):
            AuthorizationSnapshot(
                snapshot_id="s",
                decision_id="d",
                request_id="r",
                action="memory.read",
                actor_identity_id="identity-1",
                subject_user_id="user-1",
                memory_id=MEMORY_ID,
                version_id=VERSION_ID,
                owner_id="user-1",
                scope=MemoryScope(MemoryScopeKind.PRIVATE),
                revisions=private_revisions(),
                version_status=MemoryVersionStatus.PENDING_REVIEW,
                classification=MemoryClassification.CONFIDENTIAL,
                issued_at=NOW,
            )

    def test_project_snapshot_requires_exact_project_environment_and_grant_revisions(self):
        scope = MemoryScope(MemoryScopeKind.PROJECT, "project-1")
        revisions = AuthorizationRevisionSet(
            memory_revision=revision(AuthorityKind.MEMORY, MEMORY_ID),
            version_revision=revision(AuthorityKind.MEMORY_VERSION, VERSION_ID),
            identity_revision=revision(AuthorityKind.IDENTITY, "identity-1"),
            project_revision=revision(AuthorityKind.PROJECT, "project-1"),
            environment_revision=revision(AuthorityKind.ENVIRONMENT, "environment-1"),
            grant_revision=revision(AuthorityKind.GRANT, "grant-1"),
        )
        snapshot = AuthorizationSnapshot(
            snapshot_id="s",
            decision_id="d",
            request_id="r",
            action="memory.read",
            actor_identity_id="identity-1",
            subject_user_id="user-1",
            memory_id=MEMORY_ID,
            version_id=VERSION_ID,
            owner_id="owner-1",
            scope=scope,
            revisions=revisions,
            version_status=MemoryVersionStatus.APPROVED,
            classification=MemoryClassification.INTERNAL,
            issued_at=NOW,
            project_id="project-1",
            environment_id="environment-1",
            grant_expires_at=datetime(2026, 11, 14, 0, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(snapshot.revisions.grant_revision.authority_id, "grant-1")

        with self.assertRaises(ContractError):
            AuthorizationSnapshot(
                snapshot_id="s",
                decision_id="d",
                request_id="r",
                action="memory.read",
                actor_identity_id="identity-1",
                subject_user_id="user-1",
                memory_id=MEMORY_ID,
                version_id=VERSION_ID,
                owner_id="owner-1",
                scope=scope,
                revisions=revisions,
                version_status=MemoryVersionStatus.APPROVED,
                classification=MemoryClassification.INTERNAL,
                issued_at=NOW,
                project_id="another-project",
                environment_id="environment-1",
                grant_expires_at=datetime(2026, 11, 14, 0, 0, tzinfo=timezone.utc),
            )

    def test_snapshot_rejects_restricted_classification_and_non_utc_time(self):
        with self.assertRaises(ContractError):
            AuthorizationSnapshot(
                snapshot_id="s",
                decision_id="d",
                request_id="r",
                action="memory.read",
                actor_identity_id="identity-1",
                subject_user_id="user-1",
                memory_id=MEMORY_ID,
                version_id=VERSION_ID,
                owner_id="user-1",
                scope=MemoryScope(MemoryScopeKind.PRIVATE),
                revisions=private_revisions(),
                version_status=MemoryVersionStatus.APPROVED,
                classification=MemoryClassification.RESTRICTED,
                issued_at=NOW,
            )
        with self.assertRaises(ContractError):
            AuthorizationSnapshot(
                snapshot_id="s",
                decision_id="d",
                request_id="r",
                action="memory.read",
                actor_identity_id="identity-1",
                subject_user_id="user-1",
                memory_id=MEMORY_ID,
                version_id=VERSION_ID,
                owner_id="user-1",
                scope=MemoryScope(MemoryScopeKind.PRIVATE),
                revisions=private_revisions(),
                version_status=MemoryVersionStatus.APPROVED,
                classification=MemoryClassification.INTERNAL,
                issued_at=datetime(2026, 11, 13, 12, 0),
            )

    def test_read_admission_is_immutable_and_transitions_are_controlled(self):
        original = admission()
        active = original.transition(ReadAdmissionStatus.ACTIVE)
        unresolved = active.transition(ReadAdmissionStatus.UNRESOLVED)
        self.assertEqual(original.status, ReadAdmissionStatus.ADMITTED)
        self.assertEqual(active.status, ReadAdmissionStatus.ACTIVE)
        with self.assertRaises(ContractError):
            unresolved.transition(ReadAdmissionStatus.COMPLETED)
        with self.assertRaises(ContractError):
            active.transition(ReadAdmissionStatus.COMPLETED)
        with self.assertRaises(FrozenInstanceError):
            original.generation = 2
        with self.assertRaises(ContractError):
            original.transition(ReadAdmissionStatus.COMPLETED)

    def test_cancelled_and_completed_are_terminal_and_incompatible(self):
        cancelled = admission(ReadAdmissionStatus.CANCELLED)
        completed = admission(ReadAdmissionStatus.COMPLETED)
        with self.assertRaises(ContractError):
            cancelled.transition(ReadAdmissionStatus.ACTIVE)
        with self.assertRaises(ContractError):
            completed.transition(ReadAdmissionStatus.UNRESOLVED)

    def test_route_set_must_be_nonempty_and_explicit(self):
        self.assertEqual(DeliveryRouteSet(frozenset({"api"})).route_ids, frozenset({"api"}))
        with self.assertRaises(ContractError):
            DeliveryRouteSet(frozenset())
        with self.assertRaises(ContractError):
            DeliveryRouteSet({"api"})

    def test_invalidation_requires_monotonic_revision(self):
        invalidation = AuthorizationInvalidation(
            invalidation_id="invalidate-1",
            authority=AuthorityKind.IDENTITY,
            authority_id="identity-1",
            previous_revision=2,
            new_revision=3,
            affected_admission_ids=frozenset({"admission-1"}),
        )
        self.assertEqual(invalidation.new_revision, 3)
        with self.assertRaises(ContractError):
            AuthorizationInvalidation(
                invalidation_id="invalidate-2",
                authority=AuthorityKind.IDENTITY,
                authority_id="identity-1",
                previous_revision=3,
                new_revision=3,
                affected_admission_ids=frozenset(),
            )

    def test_fence_receipt_requires_explicit_confirmation_flag(self):
        receipt = EndpointFenceReceipt(
            operation_id="forget-1",
            admission_id="admission-1",
            endpoint_id="assistant-response",
            generation=2,
            fenced_at=NOW,
            confirmed=True,
        )
        self.assertTrue(receipt.confirmed)
        with self.assertRaises(ContractError):
            EndpointFenceReceipt(
                operation_id="forget-1",
                admission_id="admission-1",
                endpoint_id="assistant-response",
                generation=2,
                fenced_at=NOW,
                confirmed="yes",
            )


    def test_private_snapshot_requires_authenticated_subject_to_be_owner(self):
        with self.assertRaises(ContractError):
            AuthorizationSnapshot(
                snapshot_id="s",
                decision_id="d",
                request_id="r",
                action="memory.read",
                actor_identity_id="identity-1",
                subject_user_id="different-user",
                memory_id=MEMORY_ID,
                version_id=VERSION_ID,
                owner_id="user-1",
                scope=MemoryScope(MemoryScopeKind.PRIVATE),
                revisions=private_revisions(),
                version_status=MemoryVersionStatus.APPROVED,
                classification=MemoryClassification.CONFIDENTIAL,
                issued_at=NOW,
            )

    def test_cam_snapshot_cannot_preassign_admission_generation(self):
        revisions = AuthorizationRevisionSet(
            memory_revision=revision(AuthorityKind.MEMORY, MEMORY_ID),
            version_revision=revision(AuthorityKind.MEMORY_VERSION, VERSION_ID),
            identity_revision=revision(AuthorityKind.IDENTITY, "identity-1"),
            admission_generation=1,
        )
        with self.assertRaises(ContractError):
            AuthorizationSnapshot(
                snapshot_id="s",
                decision_id="d",
                request_id="r",
                action="memory.read",
                actor_identity_id="identity-1",
                subject_user_id="user-1",
                memory_id=MEMORY_ID,
                version_id=VERSION_ID,
                owner_id="user-1",
                scope=MemoryScope(MemoryScopeKind.PRIVATE),
                revisions=revisions,
                version_status=MemoryVersionStatus.APPROVED,
                classification=MemoryClassification.INTERNAL,
                issued_at=NOW,
            )

    def test_completion_receipt_and_reconciliation_are_typed_and_disjoint(self):
        from atlas.memory.consistency import EndpointCompletionReceipt, ReconciliationResult
        receipt = EndpointCompletionReceipt(
            admission_id="admission-1",
            endpoint_id="assistant-response",
            final_sequence=0,
            completed_at=NOW,
        )
        self.assertEqual(receipt.final_sequence, 0)
        result = ReconciliationResult(
            operation_id="invalidate-1",
            resolved_admission_ids=frozenset({"admission-1"}),
            unresolved_admission_ids=frozenset({"admission-2"}),
        )
        self.assertEqual(result.resolved_admission_ids, frozenset({"admission-1"}))
        with self.assertRaises(ContractError):
            ReconciliationResult(
                operation_id="invalidate-1",
                resolved_admission_ids=frozenset({"admission-1"}),
                unresolved_admission_ids=frozenset({"admission-1"}),
            )


    def test_project_snapshot_rejects_expired_grant_at_decision_time(self):
        revisions = AuthorizationRevisionSet(
            memory_revision=revision(AuthorityKind.MEMORY, MEMORY_ID),
            version_revision=revision(AuthorityKind.MEMORY_VERSION, VERSION_ID),
            identity_revision=revision(AuthorityKind.IDENTITY, "identity-1"),
            project_revision=revision(AuthorityKind.PROJECT, "project-1"),
            environment_revision=revision(AuthorityKind.ENVIRONMENT, "environment-1"),
            grant_revision=revision(AuthorityKind.GRANT, "grant-1"),
        )
        with self.assertRaises(ContractError):
            AuthorizationSnapshot(
                snapshot_id="s",
                decision_id="d",
                request_id="r",
                action="memory.read",
                actor_identity_id="identity-1",
                subject_user_id="user-1",
                memory_id=MEMORY_ID,
                version_id=VERSION_ID,
                owner_id="owner-1",
                scope=MemoryScope(MemoryScopeKind.PROJECT, "project-1"),
                revisions=revisions,
                version_status=MemoryVersionStatus.APPROVED,
                classification=MemoryClassification.INTERNAL,
                issued_at=NOW,
                project_id="project-1",
                environment_id="environment-1",
                grant_expires_at=datetime(2026, 11, 13, 15, 59, tzinfo=timezone.utc),
            )


    def test_invalidation_receipt_binds_generation_and_affected_admissions(self):
        from atlas.memory.consistency import InvalidationReceipt
        receipt = InvalidationReceipt(
            invalidation_id="invalidate-1",
            new_generation=4,
            affected_admission_ids=frozenset({"admission-1", "admission-2"}),
            accepted_at=NOW,
        )
        self.assertEqual(receipt.new_generation, 4)
        self.assertEqual(len(receipt.affected_admission_ids), 2)
        with self.assertRaises(ContractError):
            InvalidationReceipt(
                invalidation_id="invalidate-1",
                new_generation=0,
                affected_admission_ids=frozenset(),
                accepted_at=NOW,
            )


if __name__ == "__main__":
    unittest.main()
