"""Pruebas deterministas de admisión, invalidación y egress ME-03.

Estos adaptadores son fakes de prueba: no demuestran durabilidad ni fencing
entre procesos o transportes reales.
"""
import threading
import unittest
from dataclasses import replace
from datetime import datetime, timezone

from atlas.memory.consistency import (
    AuthorityKind,
    AuthorizationInvalidation,
    AuthorizationSnapshot,
    DeliveryRouteSet,
    EgressReceipt,
    EndpointCompletionReceipt,
    EndpointDeliveryStatus,
    EndpointFenceReceipt,
    InvalidationReceipt,
    ReadAdmission,
    ReadAdmissionStatus,
    ReadTarget,
    ReconciliationResult,
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
ROUTES = frozenset({"assistant-response", "api-response"})


def private_snapshot(identity_revision=1):
    from atlas.memory.consistency import (
        AuthorityRevision,
        AuthorizationRevisionSet,
    )

    return AuthorizationSnapshot(
        snapshot_id=f"snapshot-{identity_revision}",
        decision_id=f"decision-{identity_revision}",
        request_id="request-1",
        action="memory.read",
        actor_identity_id="identity-1",
        subject_user_id="owner-1",
        memory_id=MEMORY_ID,
        version_id=VERSION_ID,
        owner_id="owner-1",
        scope=MemoryScope(MemoryScopeKind.PRIVATE),
        revisions=AuthorizationRevisionSet(
            memory_revision=AuthorityRevision(AuthorityKind.MEMORY, MEMORY_ID, 1),
            version_revision=AuthorityRevision(AuthorityKind.MEMORY_VERSION, VERSION_ID, 1),
            identity_revision=AuthorityRevision(
                AuthorityKind.IDENTITY, "identity-1", identity_revision
            ),
        ),
        version_status=MemoryVersionStatus.APPROVED,
        classification=MemoryClassification.CONFIDENTIAL,
        issued_at=NOW,
    )


class FakeReadConsistencyAndEgress:
    """Fake atómico, determinista y de proceso único para probar los contratos."""

    def __init__(self):
        self._lock = threading.RLock()
        self.revisions = {
            (AuthorityKind.MEMORY, MEMORY_ID): 1,
            (AuthorityKind.MEMORY_VERSION, VERSION_ID): 1,
            (AuthorityKind.IDENTITY, "identity-1"): 1,
        }
        self.registered_routes = set(ROUTES)
        self.generation = 1
        self.admissions = {}
        self.admission_snapshots = {}
        self.operations = {}
        self.fence_acks = {}
        self.completion_acks = {}
        self.emissions = {}
        self.fenced_endpoints = set()
        self._next_admission = 1

    def admit_read(self, snapshot, routes):
        with self._lock:
            if not isinstance(snapshot, AuthorizationSnapshot):
                return None
            if not isinstance(routes, DeliveryRouteSet):
                return None
            if not routes.route_ids.issubset(self.registered_routes):
                return None
            if any(
                self.revisions.get((revision.authority_kind, revision.authority_id))
                != revision.revision
                for revision in (
                    snapshot.revisions.memory_revision,
                    snapshot.revisions.version_revision,
                    snapshot.revisions.identity_revision,
                )
            ):
                return None
            if any(
                operation["pending"]
                and operation["authority_id"] == snapshot.actor_identity_id
                for operation in self.operations.values()
            ):
                return None

            admission_id = f"admission-{self._next_admission}"
            self._next_admission += 1
            admission = ReadAdmission(
                admission_id=admission_id,
                snapshot_id=snapshot.snapshot_id,
                target=ReadTarget(
                    snapshot.memory_id,
                    snapshot.version_id,
                    snapshot.owner_id,
                    snapshot.scope,
                ),
                generation=self.generation,
                route_ids=routes.route_ids,
                status=ReadAdmissionStatus.ADMITTED,
                admitted_at=NOW,
            )
            self.admissions[admission_id] = admission
            self.admission_snapshots[admission_id] = snapshot
            return admission

    def begin_invalidation(self, invalidation):
        with self._lock:
            if not isinstance(invalidation, AuthorizationInvalidation):
                return None
            key = (invalidation.authority, invalidation.authority_id)
            if self.revisions.get(key) != invalidation.previous_revision:
                return None
            if invalidation.new_revision <= invalidation.previous_revision:
                return None
            if any(
                admission_id not in self.admissions
                for admission_id in invalidation.affected_admission_ids
            ):
                return None
            expected_affected = set()
            for admission_id, admission in self.admissions.items():
                if admission.status in (
                    ReadAdmissionStatus.COMPLETED,
                    ReadAdmissionStatus.CANCELLED,
                ):
                    continue
                snapshot = self.admission_snapshots[admission_id]
                revisions = (
                    snapshot.revisions.memory_revision,
                    snapshot.revisions.version_revision,
                    snapshot.revisions.identity_revision,
                    snapshot.revisions.project_revision,
                    snapshot.revisions.environment_revision,
                    snapshot.revisions.grant_revision,
                )
                if any(
                    revision is not None
                    and revision.authority_kind is invalidation.authority
                    and revision.authority_id == invalidation.authority_id
                    and revision.revision == invalidation.previous_revision
                    for revision in revisions
                ):
                    expected_affected.add(admission_id)
            if expected_affected != set(invalidation.affected_admission_ids):
                return None
            self.revisions[key] = invalidation.new_revision
            self.generation += 1
            self.operations[invalidation.invalidation_id] = {
                "authority_id": invalidation.authority_id,
                "affected": invalidation.affected_admission_ids,
                "pending": True,
            }
            return InvalidationReceipt(
                invalidation.invalidation_id,
                self.generation,
                invalidation.affected_admission_ids,
                NOW,
            )

    def record_endpoint_ack(self, receipt):
        with self._lock:
            operation = self.operations.get(receipt.operation_id)
            if operation is None or not operation["pending"]:
                return False
            admission = self.admissions.get(receipt.admission_id)
            if admission is None or receipt.admission_id not in operation["affected"]:
                return False
            if receipt.endpoint_id not in admission.route_ids:
                return False
            if receipt.generation != self.generation:
                return False
            key = (receipt.admission_id, receipt.endpoint_id)
            if isinstance(receipt, EndpointFenceReceipt):
                if not receipt.confirmed:
                    return False
                self.fence_acks.setdefault(receipt.operation_id, set()).add(key)
                return True
            if isinstance(receipt, EndpointCompletionReceipt):
                last_sequence = self.emissions.get(key, 0)
                if receipt.final_sequence != last_sequence:
                    return False
                self.completion_acks.setdefault(receipt.operation_id, set()).add(key)
                return True
            return False

    def get_nonterminal_admissions(self, operation_id):
        with self._lock:
            operation = self.operations.get(operation_id)
            if operation is None:
                return ()
            return tuple(
                self.admissions[item]
                for item in operation["affected"]
                if self.admissions[item].status
                not in (ReadAdmissionStatus.COMPLETED, ReadAdmissionStatus.CANCELLED)
            )

    def reconcile(self, operation_id):
        with self._lock:
            operation = self.operations.get(operation_id)
            if operation is None:
                return ReconciliationResult(operation_id, frozenset(), frozenset())
            resolved, unresolved = set(), set()
            fence_acks = self.fence_acks.get(operation_id, set())
            completion_acks = self.completion_acks.get(operation_id, set())
            for admission_id in operation["affected"]:
                admission = self.admissions[admission_id]
                required = {(admission_id, endpoint) for endpoint in admission.route_ids}
                if required.issubset(completion_acks):
                    evidence = f"completion:{operation_id}:{admission_id}"
                    self.admissions[admission_id] = replace(
                        admission,
                        status=ReadAdmissionStatus.COMPLETED,
                        terminal_evidence_id=evidence,
                    )
                    resolved.add(admission_id)
                elif required.issubset(fence_acks | completion_acks):
                    evidence = f"fencing:{operation_id}:{admission_id}"
                    self.admissions[admission_id] = replace(
                        admission,
                        status=ReadAdmissionStatus.CANCELLED,
                        terminal_evidence_id=evidence,
                    )
                    resolved.add(admission_id)
                else:
                    unresolved.add(admission_id)
            if not unresolved:
                operation["pending"] = False
            return ReconciliationResult(
                operation_id, frozenset(resolved), frozenset(unresolved)
            )

    def commit_and_emit(
        self, admission, handle, endpoint_id, emission_id, sequence, now
    ):
        with self._lock:
            current = self.admissions.get(admission.admission_id)
            if current != admission or admission.generation != self.generation:
                return None
            if admission.status not in (ReadAdmissionStatus.ADMITTED, ReadAdmissionStatus.ACTIVE):
                return None
            if endpoint_id not in admission.route_ids:
                return None
            if (admission.admission_id, endpoint_id) in self.fenced_endpoints:
                return None
            if (
                getattr(handle, "admission_id", None) != admission.admission_id
                or getattr(handle, "memory_id", None) != admission.target.memory_id
                or getattr(handle, "version_id", None) != admission.target.version_id
                or getattr(handle, "classification", None) is MemoryClassification.RESTRICTED
                or not getattr(handle, "handle_id", None)
            ):
                return None
            if (
                not isinstance(now, datetime)
                or now.tzinfo is None
                or now.utcoffset().total_seconds() != 0
            ):
                return None
            if not isinstance(emission_id, str) or not emission_id.strip():
                return None
            if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
                return None
            key = (admission.admission_id, endpoint_id)
            expected = self.emissions.get(key, 0) + 1
            if sequence != expected:
                return None
            self.emissions[key] = sequence
            return EgressReceipt(
                admission.admission_id,
                endpoint_id,
                emission_id,
                sequence,
                admission.generation,
                now,
            )

    def finish(self, admission, endpoint_id, final_sequence, now):
        with self._lock:
            current = self.admissions.get(admission.admission_id)
            if current != admission or endpoint_id not in admission.route_ids:
                return None
            key = (admission.admission_id, endpoint_id)
            if key in self.fenced_endpoints:
                return None
            if final_sequence != self.emissions.get(key, 0):
                return None
            return EndpointCompletionReceipt(
                operation_id=f"completion:{admission.admission_id}",
                admission_id=admission.admission_id,
                endpoint_id=endpoint_id,
                generation=admission.generation,
                final_sequence=final_sequence,
                completed_at=now,
            )

    def reconcile_endpoint(self, admission, endpoint_id):
        with self._lock:
            key = (admission.admission_id, endpoint_id)
            if key in self.fenced_endpoints:
                return EndpointDeliveryStatus.FENCED
            if any(key in values for values in self.completion_acks.values()):
                return EndpointDeliveryStatus.COMPLETED
            if self.admissions.get(admission.admission_id) == admission:
                return EndpointDeliveryStatus.ACTIVE
            return EndpointDeliveryStatus.UNRESOLVED

    def fence(self, admission, endpoint_id, new_generation, now):
        with self._lock:
            if admission.admission_id not in self.admissions:
                return None
            if endpoint_id not in admission.route_ids or new_generation <= admission.generation:
                return None
            self.fenced_endpoints.add((admission.admission_id, endpoint_id))
            return EndpointFenceReceipt(
                operation_id="direct-fence",
                admission_id=admission.admission_id,
                endpoint_id=endpoint_id,
                generation=new_generation,
                fenced_at=now,
                confirmed=True,
            )


class FakeHandle:
    def __init__(self, admission):
        self.handle_id = f"handle:{admission.admission_id}"
        self.admission_id = admission.admission_id
        self.memory_id = admission.target.memory_id
        self.version_id = admission.target.version_id
        self.classification = MemoryClassification.CONFIDENTIAL


class MemoryConsistencyAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.authority = FakeReadConsistencyAndEgress()

    def test_admission_requires_current_snapshot_and_registered_routes(self):
        admission = self.authority.admit_read(
            private_snapshot(), DeliveryRouteSet(ROUTES)
        )
        self.assertIsNotNone(admission)
        self.assertEqual(admission.generation, 1)
        self.assertIsNone(
            self.authority.admit_read(
                private_snapshot(), DeliveryRouteSet(frozenset({"unknown-route"}))
            )
        )

    def test_stale_identity_revision_is_rejected(self):
        self.assertIsNone(
            self.authority.admit_read(
                private_snapshot(identity_revision=2), DeliveryRouteSet(ROUTES)
            )
        )

    def test_invalidation_advances_generation_and_blocks_old_snapshot(self):
        admission = self.authority.admit_read(
            private_snapshot(), DeliveryRouteSet(ROUTES)
        )
        invalidation = AuthorizationInvalidation(
            "invalidate-1",
            AuthorityKind.IDENTITY,
            "identity-1",
            1,
            2,
            frozenset({admission.admission_id}),
        )
        receipt = self.authority.begin_invalidation(invalidation)
        self.assertEqual(receipt.new_generation, 2)
        self.assertIsNone(
            self.authority.admit_read(
                private_snapshot(identity_revision=2), DeliveryRouteSet(ROUTES)
            )
        )
        self.assertIsNone(
            self.authority.commit_and_emit(
                admission,
                FakeHandle(admission),
                "assistant-response",
                "emission-1",
                1,
                NOW,
            )
        )

    def test_invalidation_rejects_incomplete_or_unrelated_admission_inventory(self):
        admission = self.authority.admit_read(
            private_snapshot(), DeliveryRouteSet(ROUTES)
        )
        incomplete = AuthorizationInvalidation(
            "invalidate-incomplete", AuthorityKind.IDENTITY, "identity-1", 1, 2,
            frozenset()
        )
        unrelated = AuthorizationInvalidation(
            "invalidate-unrelated", AuthorityKind.IDENTITY, "identity-1", 1, 2,
            frozenset({"not-an-admission"})
        )
        self.assertIsNone(self.authority.begin_invalidation(incomplete))
        self.assertIsNone(self.authority.begin_invalidation(unrelated))
        self.assertEqual(self.authority.admissions[admission.admission_id].status, ReadAdmissionStatus.ADMITTED)

    def test_invalidation_remains_unresolved_until_every_endpoint_is_fenced(self):
        admission = self.authority.admit_read(
            private_snapshot(), DeliveryRouteSet(ROUTES)
        )
        invalidation = AuthorizationInvalidation(
            "invalidate-2",
            AuthorityKind.IDENTITY,
            "identity-1",
            1,
            2,
            frozenset({admission.admission_id}),
        )
        receipt = self.authority.begin_invalidation(invalidation)
        first = EndpointFenceReceipt(
            "invalidate-2", admission.admission_id, "assistant-response",
            receipt.new_generation, NOW, True
        )
        self.assertTrue(self.authority.record_endpoint_ack(first))
        partial = self.authority.reconcile("invalidate-2")
        self.assertEqual(partial.unresolved_admission_ids, frozenset({admission.admission_id}))
        self.assertEqual(self.authority.admissions[admission.admission_id].status, ReadAdmissionStatus.ADMITTED)

        second = EndpointFenceReceipt(
            "invalidate-2", admission.admission_id, "api-response",
            receipt.new_generation, NOW, True
        )
        self.assertTrue(self.authority.record_endpoint_ack(second))
        final = self.authority.reconcile("invalidate-2")
        self.assertEqual(final.resolved_admission_ids, frozenset({admission.admission_id}))
        self.assertEqual(self.authority.admissions[admission.admission_id].status, ReadAdmissionStatus.CANCELLED)

    def test_ack_from_unknown_endpoint_or_wrong_generation_is_rejected(self):
        admission = self.authority.admit_read(
            private_snapshot(), DeliveryRouteSet(ROUTES)
        )
        receipt = self.authority.begin_invalidation(
            AuthorizationInvalidation(
                "invalidate-3", AuthorityKind.IDENTITY, "identity-1", 1, 2,
                frozenset({admission.admission_id})
            )
        )
        unknown = EndpointFenceReceipt(
            "invalidate-3", admission.admission_id, "unregistered",
            receipt.new_generation, NOW, True
        )
        stale = EndpointFenceReceipt(
            "invalidate-3", admission.admission_id, "assistant-response",
            receipt.new_generation - 1, NOW, True
        )
        self.assertFalse(self.authority.record_endpoint_ack(unknown))
        self.assertFalse(self.authority.record_endpoint_ack(stale))

    def test_invalidation_can_resolve_after_all_endpoints_complete(self):
        admission = self.authority.admit_read(
            private_snapshot(), DeliveryRouteSet(ROUTES)
        )
        invalidation = AuthorizationInvalidation(
            "invalidate-complete", AuthorityKind.IDENTITY, "identity-1", 1, 2,
            frozenset({admission.admission_id})
        )
        receipt = self.authority.begin_invalidation(invalidation)
        for endpoint in admission.route_ids:
            completion = EndpointCompletionReceipt(
                "invalidate-complete", admission.admission_id, endpoint,
                receipt.new_generation, 0, NOW
            )
            self.assertTrue(self.authority.record_endpoint_ack(completion))
        result = self.authority.reconcile("invalidate-complete")
        self.assertEqual(result.resolved_admission_ids, frozenset({admission.admission_id}))
        self.assertEqual(
            self.authority.admissions[admission.admission_id].status,
            ReadAdmissionStatus.COMPLETED,
        )

    def test_egress_is_sequence_checked_and_fenced_by_generation(self):
        admission = self.authority.admit_read(
            private_snapshot(), DeliveryRouteSet(ROUTES)
        )
        handle = FakeHandle(admission.admission_id)
        first = self.authority.commit_and_emit(
            admission, handle, "assistant-response", "emission-1", 1, NOW
        )
        self.assertIsNotNone(first)
        self.assertIsNone(
            self.authority.commit_and_emit(
                admission, handle, "assistant-response", "emission-2", 3, NOW
            )
        )
        self.assertIsNotNone(
            self.authority.fence(admission, "assistant-response", 2, NOW)
        )
        self.assertIsNone(
            self.authority.commit_and_emit(
                admission, handle, "assistant-response", "emission-2", 2, NOW
            )
        )


if __name__ == "__main__":
    unittest.main()
