"""Pruebas deterministas de admisión, invalidación y egress ME-03.

Estos adaptadores son fakes de prueba: no demuestran durabilidad ni fencing
entre procesos o transportes reales.
"""
import threading
import unittest
from dataclasses import replace
from datetime import datetime, timezone

from atlas.core.errors import ContractError
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
from atlas.memory.forget import (
    ForgetClosure, ForgetClosureStatus, ForgetRecoverySnapshot, ForgetTarget,
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


class FakeVerifiedForgetAuthorization:
    """Solo test double; no representa un emisor/verificador confiable."""

    def __init__(
        self,
        memory_id=MEMORY_ID,
        owner_id="owner-1",
        subject_user_id="owner-1",
        request_id="request-forget-1",
    ):
        self.decision_id = "decision-forget-1"
        self.request_id = request_id
        self.actor_identity_id = "identity-1"
        self.subject_user_id = subject_user_id
        self.memory_id = memory_id
        self.owner_id = owner_id


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
        self.invalidation_requests = {}
        self.invalidation_receipts = {}
        self.fence_acks = {}
        self.completion_acks = {}
        self.ack_receipts = {}
        self.emissions = {}
        self.fenced_endpoints = set()
        self._next_admission = 1
        self._next_forget = 1
        self.memory_owners = {MEMORY_ID: "owner-1"}
        self.identity_subjects = {"identity-1": "owner-1"}
        self.suppressed_memories = set()
        self.forget_idempotency = {}
        self.forget_closures = {}

    def export_forget_recovery(self, operation_id):
        with self._lock:
            closure = self.forget_closures.get(operation_id)
            if closure is None:
                return None
            admissions = tuple(
                self.admissions[item]
                for item in sorted(closure.affected_admission_ids)
            )
            return ForgetRecoverySnapshot(
                generation=self.generation,
                closure=closure,
                admissions=admissions,
            )

    @classmethod
    def restore_forget_recovery(cls, snapshot):
        if not isinstance(snapshot, ForgetRecoverySnapshot):
            return None
        restored = cls()
        with restored._lock:
            restored.generation = snapshot.generation
            restored.suppressed_memories.add(snapshot.closure.target.memory_id)
            restored.forget_closures[snapshot.closure.operation_id] = snapshot.closure
            pending = snapshot.closure.status is ForgetClosureStatus.CLOSING
            restored.operations[snapshot.closure.operation_id] = {
                "affected": snapshot.closure.affected_admission_ids,
                "pending": pending,
                "kind": "forget",
            }
            for admission in snapshot.admissions:
                recovered = admission
                if admission.status not in (
                    ReadAdmissionStatus.COMPLETED,
                    ReadAdmissionStatus.CANCELLED,
                ):
                    recovered = replace(
                        admission,
                        status=ReadAdmissionStatus.UNRESOLVED,
                        terminal_evidence_id=None,
                    )
                restored.admissions[recovered.admission_id] = recovered
                restored.operations[f"read:{recovered.admission_id}"] = {
                    "affected": frozenset({recovered.admission_id}),
                    "pending": False,
                    "kind": "read",
                }
            # No se restauran acknowledgements en memoria: cada endpoint debe
            # demostrar de nuevo finalización o fencing en la generación vigente.
        return restored

    @staticmethod
    def _same_admission(current, candidate):
        return (
            current is not None
            and current.admission_id == candidate.admission_id
            and current.snapshot_id == candidate.snapshot_id
            and current.target == candidate.target
            and current.generation == candidate.generation
            and current.route_ids == candidate.route_ids
            and current.status in (candidate.status, ReadAdmissionStatus.ACTIVE)
        )

    def admit_read(self, snapshot, routes, now=NOW):
        with self._lock:
            if not isinstance(snapshot, AuthorizationSnapshot):
                return None
            if not isinstance(routes, DeliveryRouteSet):
                return None
            if (
                not isinstance(now, datetime)
                or now.tzinfo is None
                or now.utcoffset().total_seconds() != 0
            ):
                return None
            if snapshot.memory_id in self.suppressed_memories:
                return None
            if snapshot.grant_expires_at is not None and now >= snapshot.grant_expires_at:
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
                    snapshot.revisions.project_revision,
                    snapshot.revisions.environment_revision,
                    snapshot.revisions.grant_revision,
                )
                if revision is not None
            ):
                return None
            snapshot_authorities = {
                (revision.authority_kind, revision.authority_id)
                for revision in (
                    snapshot.revisions.memory_revision,
                    snapshot.revisions.version_revision,
                    snapshot.revisions.identity_revision,
                    snapshot.revisions.project_revision,
                    snapshot.revisions.environment_revision,
                    snapshot.revisions.grant_revision,
                )
                if revision is not None
            }
            if any(
                operation["pending"]
                and operation.get("kind") == "invalidation"
                and (operation["authority_kind"], operation["authority_id"])
                in snapshot_authorities
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
            self.operations[f"read:{admission_id}"] = {
                "authority_id": None,
                "affected": frozenset({admission_id}),
                "pending": True,
                "kind": "read",
            }
            return admission

    def begin_forget(self, target, authorization, idempotency_key, now=NOW):
        with self._lock:
            if not isinstance(target, ForgetTarget):
                return None
            if (
                not isinstance(now, datetime)
                or now.tzinfo is None
                or now.utcoffset().total_seconds() != 0
                or not isinstance(idempotency_key, str)
                or not idempotency_key.strip()
            ):
                return None
            required = (
                "decision_id", "request_id", "actor_identity_id",
                "subject_user_id", "memory_id", "owner_id",
            )
            if any(
                not isinstance(getattr(authorization, field, None), str)
                or not getattr(authorization, field).strip()
                for field in required
            ):
                return None
            if (
                authorization.memory_id != target.memory_id
                or authorization.subject_user_id != authorization.owner_id
                or self.memory_owners.get(target.memory_id) != authorization.owner_id
                or self.identity_subjects.get(authorization.actor_identity_id)
                != authorization.subject_user_id
            ):
                return None
            binding = (
                target.memory_id,
                authorization.decision_id,
                authorization.request_id,
                authorization.actor_identity_id,
                authorization.subject_user_id,
                authorization.owner_id,
            )
            prior = self.forget_idempotency.get(idempotency_key)
            if prior is not None:
                prior_binding, prior_closure = prior
                return prior_closure if prior_binding == binding else None
            if target.memory_id in self.suppressed_memories:
                return None

            affected = frozenset(
                admission_id
                for admission_id, admission in self.admissions.items()
                if admission.target.memory_id == target.memory_id
                and admission.status not in (
                    ReadAdmissionStatus.COMPLETED,
                    ReadAdmissionStatus.CANCELLED,
                )
            )
            if any(
                operation["pending"]
                and operation.get("kind") == "invalidation"
                and (
                    operation.get("authority_kind") is AuthorityKind.MEMORY
                    and operation.get("authority_id") == target.memory_id
                    or bool(affected.intersection(operation["affected"]))
                )
                for operation in self.operations.values()
            ):
                return None

            routes = frozenset(
                endpoint
                for admission_id in affected
                for endpoint in self.admissions[admission_id].route_ids
            )
            self.generation += 1
            self.suppressed_memories.add(target.memory_id)
            closure_id = f"018bcfe5-7b3a-7cc2-98c4-dc0c0c073a{14 + self._next_forget:02x}"
            self._next_forget += 1
            operation_id = f"forget:{closure_id}"
            closure = ForgetClosure(
                closure_id=closure_id,
                operation_id=operation_id,
                idempotency_key=idempotency_key,
                target=target,
                generation=self.generation,
                affected_admission_ids=affected,
                unresolved_admission_ids=affected,
                delivery_route_ids=routes,
                status=ForgetClosureStatus.CLOSING,
            )
            self.operations[operation_id] = {
                "affected": affected,
                "pending": True,
                "kind": "forget",
            }
            self.forget_idempotency[idempotency_key] = (binding, closure)
            self.forget_closures[operation_id] = closure
            return closure

    def reconcile_forget(self, operation_id):
        with self._lock:
            closure = self.forget_closures.get(operation_id)
            if closure is None:
                return None
            result = self.reconcile(operation_id)
            status = (
                ForgetClosureStatus.SUPPRESSED
                if not result.unresolved_admission_ids
                else ForgetClosureStatus.CLOSING
            )
            updated = replace(
                closure,
                unresolved_admission_ids=result.unresolved_admission_ids,
                status=status,
            )
            self.forget_closures[operation_id] = updated
            return updated

    def begin_invalidation(self, invalidation):
        with self._lock:
            if not isinstance(invalidation, AuthorizationInvalidation):
                return None
            prior = self.invalidation_requests.get(invalidation.invalidation_id)
            if prior is not None:
                if prior != invalidation:
                    return None
                return self.invalidation_receipts[invalidation.invalidation_id]
            key = (invalidation.authority, invalidation.authority_id)
            if self.revisions.get(key) != invalidation.previous_revision:
                return None
            if any(
                operation["pending"]
                and operation.get("kind") == "invalidation"
                and operation["authority_kind"] is invalidation.authority
                and operation["authority_id"] == invalidation.authority_id
                for operation in self.operations.values()
            ):
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
            if any(
                operation["pending"]
                and operation.get("kind") == "invalidation"
                and expected_affected.intersection(operation["affected"])
                for operation in self.operations.values()
            ):
                return None
            self.revisions[key] = invalidation.new_revision
            self.generation += 1
            self.operations[invalidation.invalidation_id] = {
                "authority_kind": invalidation.authority,
                "authority_id": invalidation.authority_id,
                "affected": invalidation.affected_admission_ids,
                "pending": True,
                "kind": "invalidation",
            }
            receipt = InvalidationReceipt(
                invalidation.invalidation_id,
                self.generation,
                invalidation.affected_admission_ids,
                NOW,
            )
            self.invalidation_requests[invalidation.invalidation_id] = invalidation
            self.invalidation_receipts[invalidation.invalidation_id] = receipt
            return receipt

    def record_endpoint_ack(self, receipt):
        with self._lock:
            operation = self.operations.get(receipt.operation_id)
            if operation is None:
                return False
            ack_key = (receipt.operation_id, receipt.admission_id, receipt.endpoint_id)
            if not operation["pending"]:
                return self.ack_receipts.get(ack_key) == receipt
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
                self.ack_receipts[ack_key] = receipt
                return True
            if isinstance(receipt, EndpointCompletionReceipt):
                last_sequence = self.emissions.get(key, 0)
                if receipt.final_sequence != last_sequence:
                    return False
                self.completion_acks.setdefault(receipt.operation_id, set()).add(key)
                self.ack_receipts[ack_key] = receipt
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
            if not self._same_admission(current, admission) or admission.generation != self.generation:
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
                or not isinstance(getattr(handle, "classification", None), MemoryClassification)
                or handle.classification is MemoryClassification.RESTRICTED
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
            if current.status is ReadAdmissionStatus.ADMITTED:
                self.admissions[admission.admission_id] = replace(
                    current, status=ReadAdmissionStatus.ACTIVE
                )
            return EgressReceipt(
                admission.admission_id,
                endpoint_id,
                emission_id,
                sequence,
                admission.generation,
                now,
            )

    def finish(self, admission, operation_id, endpoint_id, final_sequence, now):
        with self._lock:
            current = self.admissions.get(admission.admission_id)
            operation = self.operations.get(operation_id)
            if (
                not self._same_admission(current, admission)
                or operation is None
                or not operation["pending"]
                or admission.admission_id not in operation["affected"]
                or endpoint_id not in admission.route_ids
            ):
                return None
            key = (admission.admission_id, endpoint_id)
            if key in self.fenced_endpoints:
                return None
            if operation.get("kind") == "read" and any(
                pending["pending"]
                and pending.get("kind") == "invalidation"
                and admission.admission_id in pending["affected"]
                for pending in self.operations.values()
            ):
                return None
            if final_sequence != self.emissions.get(key, 0):
                return None
            return EndpointCompletionReceipt(
                operation_id=operation_id,
                admission_id=admission.admission_id,
                endpoint_id=endpoint_id,
                generation=self.generation,
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
            current = self.admissions.get(admission.admission_id)
            if current is not None and current.status in (ReadAdmissionStatus.ADMITTED, ReadAdmissionStatus.ACTIVE):
                return EndpointDeliveryStatus.ACTIVE
            return EndpointDeliveryStatus.UNRESOLVED

    def fence(self, admission, operation_id, endpoint_id, new_generation, now):
        with self._lock:
            operation = self.operations.get(operation_id)
            if (
                admission.admission_id not in self.admissions
                or operation is None
                or not operation["pending"]
                or operation.get("kind") not in ("invalidation", "forget")
                or admission.admission_id not in operation["affected"]
                or endpoint_id not in admission.route_ids
                or new_generation <= admission.generation
                or new_generation != self.generation
            ):
                return None
            self.fenced_endpoints.add((admission.admission_id, endpoint_id))
            return EndpointFenceReceipt(
                operation_id=operation_id,
                admission_id=admission.admission_id,
                endpoint_id=endpoint_id,
                generation=new_generation,
                fenced_at=now,
                confirmed=True,
            )


class FakeProtectedEgress:
    """Fake separado para satisfacer el contrato de ProtectedEgressPort."""

    def __init__(self, authority):
        self.authority = authority

    def commit_and_emit(self, admission, handle, endpoint_id, emission_id, sequence, now):
        return self.authority.commit_and_emit(
            admission, handle, endpoint_id, emission_id, sequence, now
        )

    def finish(self, admission, operation_id, endpoint_id, final_sequence, now):
        return self.authority.finish(
            admission, operation_id, endpoint_id, final_sequence, now
        )

    def fence(self, admission, operation_id, endpoint_id, new_generation, now):
        return self.authority.fence(
            admission, operation_id, endpoint_id, new_generation, now
        )

    def reconcile(self, admission, endpoint_id):
        if endpoint_id not in admission.route_ids:
            return EndpointDeliveryStatus.UNRESOLVED
        return self.authority.reconcile_endpoint(admission, endpoint_id)


class FakeProtectedMemoryContent:
    """Fake condicional: no permite recuperar por IDs aislados."""

    def __init__(self):
        self.handles = {}

    def register(self, snapshot, handle):
        self.handles[(snapshot.memory_id, snapshot.version_id)] = handle

    def read_version_if_admitted(self, snapshot, admission):
        if not isinstance(snapshot, AuthorizationSnapshot):
            return None
        if not isinstance(admission, ReadAdmission):
            return None
        if admission.snapshot_id != snapshot.snapshot_id:
            return None
        if admission.target.memory_id != snapshot.memory_id:
            return None
        if admission.target.version_id != snapshot.version_id:
            return None
        if admission.target.owner_id != snapshot.owner_id:
            return None
        if admission.target.scope != snapshot.scope:
            return None
        if admission.status not in (ReadAdmissionStatus.ADMITTED, ReadAdmissionStatus.ACTIVE):
            return None
        handle = self.handles.get((snapshot.memory_id, snapshot.version_id))
        if (
            handle is None
            or handle.admission_id != admission.admission_id
            or handle.memory_id != admission.target.memory_id
            or handle.version_id != admission.target.version_id
            or not isinstance(handle.classification, MemoryClassification)
            or handle.classification is MemoryClassification.RESTRICTED
        ):
            return None
        return handle


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
        self.egress = FakeProtectedEgress(self.authority)
        self.content = FakeProtectedMemoryContent()

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
            self.egress.commit_and_emit(
                admission,
                FakeHandle(admission),
                "assistant-response",
                "emission-1",
                1,
                NOW,
            )
        )

    def test_invalidation_is_idempotent_for_same_request_and_rejects_key_reuse(self):
        admission = self.authority.admit_read(
            private_snapshot(), DeliveryRouteSet(ROUTES)
        )
        request = AuthorizationInvalidation(
            "invalidate-idempotent", AuthorityKind.IDENTITY, "identity-1", 1, 2,
            frozenset({admission.admission_id})
        )
        first = self.authority.begin_invalidation(request)
        repeated = self.authority.begin_invalidation(request)
        self.assertEqual(first, repeated)
        self.assertEqual(self.authority.generation, 2)
        next_epoch = AuthorizationInvalidation(
            "invalidate-next-epoch", AuthorityKind.IDENTITY, "identity-1", 2, 3,
            frozenset()
        )
        self.assertIsNone(self.authority.begin_invalidation(next_epoch))
        reused = AuthorizationInvalidation(
            "invalidate-idempotent", AuthorityKind.MEMORY, MEMORY_ID, 1, 2,
            frozenset({admission.admission_id})
        )
        self.assertIsNone(self.authority.begin_invalidation(reused))
        self.assertEqual(self.authority.generation, 2)

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
        self.assertTrue(self.authority.record_endpoint_ack(second))
        reopened = self.authority.admit_read(
            private_snapshot(identity_revision=2), DeliveryRouteSet(ROUTES)
        )
        self.assertIsNotNone(reopened)
        self.assertEqual(reopened.generation, 2)

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

    def test_preclose_emission_can_be_completed_after_close_without_new_emission(self):
        admission = self.authority.admit_read(
            private_snapshot(), DeliveryRouteSet(ROUTES)
        )
        handle = FakeHandle(admission)
        committed = self.egress.commit_and_emit(
            admission, handle, "assistant-response", "before-close", 1, NOW
        )
        self.assertIsNotNone(committed)
        invalidation = AuthorizationInvalidation(
            "invalidate-after-emit", AuthorityKind.IDENTITY, "identity-1", 1, 2,
            frozenset({admission.admission_id})
        )
        closure = self.authority.begin_invalidation(invalidation)
        self.assertIsNone(
            self.egress.commit_and_emit(
                admission, handle, "assistant-response", "after-close", 2, NOW
            )
        )
        self.assertIsNone(
            self.egress.finish(
                admission, f"read:{admission.admission_id}",
                "assistant-response", 1, NOW
            )
        )
        completion = self.egress.finish(
            admission, "invalidate-after-emit", "assistant-response", 1, NOW
        )
        self.assertEqual(completion.operation_id, "invalidate-after-emit")
        self.assertEqual(completion.generation, closure.new_generation)
        self.assertTrue(self.authority.record_endpoint_ack(completion))
        other = EndpointFenceReceipt(
            "invalidate-after-emit", admission.admission_id, "api-response",
            closure.new_generation, NOW, True
        )
        self.assertTrue(self.authority.record_endpoint_ack(other))
        result = self.authority.reconcile("invalidate-after-emit")
        self.assertEqual(result.resolved_admission_ids, frozenset({admission.admission_id}))
        self.assertEqual(
            self.authority.admissions[admission.admission_id].status,
            ReadAdmissionStatus.CANCELLED,
        )

    def test_normal_read_completes_only_after_all_delivery_endpoints_ack(self):
        admission = self.authority.admit_read(
            private_snapshot(), DeliveryRouteSet(ROUTES)
        )
        for endpoint in admission.route_ids:
            receipt = self.egress.finish(admission, f"read:{admission.admission_id}", endpoint, 0, NOW)
            self.assertEqual(receipt.operation_id, f"read:{admission.admission_id}")
            self.assertTrue(self.authority.record_endpoint_ack(receipt))
        result = self.authority.reconcile(f"read:{admission.admission_id}")
        self.assertEqual(result.resolved_admission_ids, frozenset({admission.admission_id}))
        self.assertEqual(
            self.authority.admissions[admission.admission_id].status,
            ReadAdmissionStatus.COMPLETED,
        )

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

    def test_restart_recovery_keeps_forget_closed_and_requires_new_endpoint_proofs(self):
        admission = self.authority.admit_read(
            private_snapshot(), DeliveryRouteSet(ROUTES)
        )
        closure = self.authority.begin_forget(
            ForgetTarget(MEMORY_ID), FakeVerifiedForgetAuthorization(),
            "forget-recovery-key", NOW
        )
        snapshot = self.authority.export_forget_recovery(closure.operation_id)
        recovered = FakeReadConsistencyAndEgress.restore_forget_recovery(snapshot)

        self.assertEqual(recovered.generation, closure.generation)
        self.assertIn(MEMORY_ID, recovered.suppressed_memories)
        recovered_admission = recovered.admissions[admission.admission_id]
        self.assertEqual(recovered_admission.status, ReadAdmissionStatus.UNRESOLVED)
        self.assertEqual(
            recovered.reconcile_forget(closure.operation_id).status,
            ForgetClosureStatus.CLOSING,
        )
        self.assertIsNone(
            recovered.admit_read(private_snapshot(), DeliveryRouteSet(ROUTES))
        )
        self.assertIsNone(
            FakeProtectedEgress(recovered).commit_and_emit(
                admission, FakeHandle(admission), "assistant-response",
                "post-restart-stale-emission", 1, NOW
            )
        )
        stale_ack = EndpointFenceReceipt(
            closure.operation_id, admission.admission_id, "assistant-response",
            closure.generation - 1, NOW, True
        )
        self.assertFalse(recovered.record_endpoint_ack(stale_ack))

        for endpoint in sorted(admission.route_ids):
            receipt = FakeProtectedEgress(recovered).fence(
                admission, closure.operation_id, endpoint,
                recovered.generation, NOW
            )
            self.assertIsNotNone(receipt)
            self.assertTrue(recovered.record_endpoint_ack(receipt))
            intermediate = recovered.reconcile_forget(closure.operation_id)
            if endpoint != sorted(admission.route_ids)[-1]:
                self.assertEqual(intermediate.status, ForgetClosureStatus.CLOSING)

        final = recovered.reconcile_forget(closure.operation_id)
        self.assertEqual(final.status, ForgetClosureStatus.SUPPRESSED)
        self.assertFalse(final.unresolved_admission_ids)
        self.assertEqual(
            recovered.admissions[admission.admission_id].status,
            ReadAdmissionStatus.CANCELLED,
        )

    def test_recovery_rejects_incomplete_admission_inventory(self):
        admission = self.authority.admit_read(
            private_snapshot(), DeliveryRouteSet(ROUTES)
        )
        closure = self.authority.begin_forget(
            ForgetTarget(MEMORY_ID), FakeVerifiedForgetAuthorization(),
            "forget-inventory-key", NOW
        )
        snapshot = self.authority.export_forget_recovery(closure.operation_id)
        with self.assertRaises(ContractError):
            replace(snapshot, admissions=())

    def test_recovery_rejects_incomplete_delivery_route_inventory(self):
        self.authority.admit_read(
            private_snapshot(), DeliveryRouteSet(ROUTES)
        )
        closure = self.authority.begin_forget(
            ForgetTarget(MEMORY_ID), FakeVerifiedForgetAuthorization(),
            "forget-route-inventory-key", NOW
        )
        snapshot = self.authority.export_forget_recovery(closure.operation_id)
        incomplete_closure = replace(
            snapshot.closure,
            delivery_route_ids=frozenset({"assistant-response"}),
        )
        with self.assertRaises(ContractError):
            replace(snapshot, closure=incomplete_closure)

    def test_recovery_rejects_admission_from_current_or_future_generation(self):
        admission = self.authority.admit_read(
            private_snapshot(), DeliveryRouteSet(ROUTES)
        )
        closure = self.authority.begin_forget(
            ForgetTarget(MEMORY_ID), FakeVerifiedForgetAuthorization(),
            "forget-admission-generation-key", NOW
        )
        snapshot = self.authority.export_forget_recovery(closure.operation_id)
        same_generation = replace(admission, generation=closure.generation)
        with self.assertRaises(ContractError):
            replace(snapshot, admissions=(same_generation,))

    def test_recovery_rejects_generation_rollback(self):
        admission = self.authority.admit_read(
            private_snapshot(), DeliveryRouteSet(ROUTES)
        )
        closure = self.authority.begin_forget(
            ForgetTarget(MEMORY_ID), FakeVerifiedForgetAuthorization(),
            "forget-generation-key", NOW
        )
        snapshot = self.authority.export_forget_recovery(closure.operation_id)
        with self.assertRaises(ContractError):
            replace(snapshot, generation=closure.generation - 1)

    def test_suppressed_memory_remains_closed_after_restart(self):
        closure = self.authority.begin_forget(
            ForgetTarget(MEMORY_ID), FakeVerifiedForgetAuthorization(),
            "forget-already-suppressed", NOW
        )
        suppressed = self.authority.reconcile_forget(closure.operation_id)
        self.assertEqual(suppressed.status, ForgetClosureStatus.SUPPRESSED)
        snapshot = self.authority.export_forget_recovery(closure.operation_id)
        recovered = FakeReadConsistencyAndEgress.restore_forget_recovery(snapshot)
        self.assertIn(MEMORY_ID, recovered.suppressed_memories)
        self.assertEqual(
            recovered.forget_closures[closure.operation_id].status,
            ForgetClosureStatus.SUPPRESSED,
        )
        self.assertIsNone(
            recovered.admit_read(private_snapshot(), DeliveryRouteSet(ROUTES))
        )

    def test_forget_closes_new_admissions_and_waits_for_every_endpoint_fence(self):
        admission = self.authority.admit_read(
            private_snapshot(), DeliveryRouteSet(ROUTES)
        )
        authorization = FakeVerifiedForgetAuthorization()
        closure = self.authority.begin_forget(
            ForgetTarget(MEMORY_ID), authorization, "forget-key-1", NOW
        )
        self.assertEqual(closure.status, ForgetClosureStatus.CLOSING)
        self.assertEqual(closure.affected_admission_ids, frozenset({admission.admission_id}))
        self.assertEqual(closure.generation, 2)
        self.assertIsNone(
            self.authority.admit_read(private_snapshot(), DeliveryRouteSet(ROUTES))
        )

        first = self.egress.fence(
            admission, closure.operation_id, "assistant-response",
            closure.generation, NOW
        )
        self.assertIsNotNone(first)
        self.assertTrue(self.authority.record_endpoint_ack(first))
        partial = self.authority.reconcile_forget(closure.operation_id)
        self.assertEqual(partial.status, ForgetClosureStatus.CLOSING)
        self.assertEqual(partial.unresolved_admission_ids, frozenset({admission.admission_id}))

        second = self.egress.fence(
            admission, closure.operation_id, "api-response",
            closure.generation, NOW
        )
        self.assertIsNotNone(second)
        self.assertTrue(self.authority.record_endpoint_ack(second))
        final = self.authority.reconcile_forget(closure.operation_id)
        self.assertEqual(final.status, ForgetClosureStatus.SUPPRESSED)
        self.assertFalse(final.unresolved_admission_ids)
        self.assertEqual(final.affected_admission_ids, frozenset({admission.admission_id}))
        self.assertEqual(
            self.authority.admissions[admission.admission_id].status,
            ReadAdmissionStatus.CANCELLED,
        )

    def test_forget_is_idempotent_and_rejects_idempotency_key_reuse(self):
        authorization = FakeVerifiedForgetAuthorization()
        first = self.authority.begin_forget(
            ForgetTarget(MEMORY_ID), authorization, "forget-key-2", NOW
        )
        repeated = self.authority.begin_forget(
            ForgetTarget(MEMORY_ID), authorization, "forget-key-2", NOW
        )
        self.assertEqual(first, repeated)
        self.assertEqual(self.authority.generation, 2)
        different_request = FakeVerifiedForgetAuthorization(request_id="another-request")
        self.assertIsNone(
            self.authority.begin_forget(
                ForgetTarget(MEMORY_ID), different_request, "forget-key-2", NOW
            )
        )
        self.assertEqual(self.authority.generation, 2)

    def test_forget_rejects_owner_or_target_mismatch(self):
        wrong_owner = FakeVerifiedForgetAuthorization(owner_id="someone-else")
        self.assertIsNone(
            self.authority.begin_forget(
                ForgetTarget(MEMORY_ID), wrong_owner, "forget-key-3", NOW
            )
        )
        wrong_memory = FakeVerifiedForgetAuthorization(memory_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c073a15")
        wrong_subject = FakeVerifiedForgetAuthorization(subject_user_id="someone-else")
        self.assertIsNone(
            self.authority.begin_forget(
                ForgetTarget(MEMORY_ID), wrong_memory, "forget-key-4", NOW
            )
        )
        self.assertIsNone(
            self.authority.begin_forget(
                ForgetTarget(MEMORY_ID), wrong_subject, "forget-key-6", NOW
            )
        )
        self.assertEqual(self.authority.generation, 1)

    def test_forget_without_prior_reads_suppresses_only_after_reconciliation(self):
        closure = self.authority.begin_forget(
            ForgetTarget(MEMORY_ID), FakeVerifiedForgetAuthorization(),
            "forget-key-5", NOW
        )
        self.assertEqual(closure.status, ForgetClosureStatus.CLOSING)
        self.assertFalse(closure.affected_admission_ids)
        final = self.authority.reconcile_forget(closure.operation_id)
        self.assertEqual(final.status, ForgetClosureStatus.SUPPRESSED)
        self.assertFalse(final.affected_admission_ids)
        self.assertIsNone(
            self.authority.admit_read(private_snapshot(), DeliveryRouteSet(ROUTES))
        )

    def test_admission_and_forget_are_serialized_by_the_same_lock(self):
        barrier = threading.Barrier(3)
        admitted = []
        forgotten = []

        def read():
            barrier.wait()
            admitted.append(
                self.authority.admit_read(private_snapshot(), DeliveryRouteSet(ROUTES))
            )

        def forget():
            barrier.wait()
            forgotten.append(
                self.authority.begin_forget(
                    ForgetTarget(MEMORY_ID), FakeVerifiedForgetAuthorization(),
                    "forget-race", NOW
                )
            )

        read_thread = threading.Thread(target=read)
        forget_thread = threading.Thread(target=forget)
        read_thread.start()
        forget_thread.start()
        barrier.wait()
        read_thread.join()
        forget_thread.join()

        self.assertIsNotNone(forgotten[0])
        if admitted[0] is not None:
            self.assertIn(admitted[0].admission_id, forgotten[0].affected_admission_ids)
        self.assertIsNone(
            self.authority.admit_read(private_snapshot(), DeliveryRouteSet(ROUTES))
        )

    def test_conditional_content_read_requires_exact_snapshot_and_admission(self):
        snapshot = private_snapshot()
        admission = self.authority.admit_read(snapshot, DeliveryRouteSet(ROUTES))
        handle = FakeHandle(admission)
        self.content.register(snapshot, handle)
        self.assertIs(
            self.content.read_version_if_admitted(snapshot, admission), handle
        )
        wrong_snapshot = private_snapshot(identity_revision=2)
        self.assertIsNone(
            self.content.read_version_if_admitted(wrong_snapshot, admission)
        )
        wrong_admission = replace(admission, snapshot_id="another-snapshot")
        self.assertIsNone(
            self.content.read_version_if_admitted(snapshot, wrong_admission)
        )

    def test_egress_endpoint_reconciliation_is_explicit(self):
        admission = self.authority.admit_read(
            private_snapshot(), DeliveryRouteSet(ROUTES)
        )
        self.assertIs(
            self.egress.reconcile(admission, "assistant-response"),
            EndpointDeliveryStatus.ACTIVE,
        )
        self.assertIs(
            self.egress.reconcile(admission, "unregistered-endpoint"),
            EndpointDeliveryStatus.UNRESOLVED,
        )

    def test_commit_and_invalidation_share_one_ordering_lock(self):
        admission = self.authority.admit_read(
            private_snapshot(), DeliveryRouteSet(ROUTES)
        )
        handle = FakeHandle(admission)
        barrier = threading.Barrier(3)
        emitted = []
        invalidated = []

        def emit():
            barrier.wait()
            emitted.append(
                self.egress.commit_and_emit(
                    admission, handle, "assistant-response", "racing-emission", 1, NOW
                )
            )

        def invalidate():
            barrier.wait()
            invalidated.append(
                self.authority.begin_invalidation(
                    AuthorizationInvalidation(
                        "racing-invalidation", AuthorityKind.IDENTITY,
                        "identity-1", 1, 2, frozenset({admission.admission_id})
                    )
                )
            )

        first = threading.Thread(target=emit)
        second = threading.Thread(target=invalidate)
        first.start()
        second.start()
        barrier.wait()
        first.join()
        second.join()

        self.assertIsNotNone(invalidated[0])
        self.assertEqual(len(emitted), 1)
        self.assertIsNone(
            self.egress.commit_and_emit(
                admission, handle, "assistant-response", "late-emission", 2, NOW
            )
        )

    def test_egress_rejects_handle_for_another_admission_target(self):
        admission = self.authority.admit_read(
            private_snapshot(), DeliveryRouteSet(ROUTES)
        )
        handle = FakeHandle(admission)
        handle.version_id = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a13"
        self.assertIsNone(
            self.egress.commit_and_emit(
                admission, handle, "assistant-response", "wrong-target", 1, NOW
            )
        )

    def test_egress_is_sequence_checked_and_fenced_by_generation(self):
        admission = self.authority.admit_read(
            private_snapshot(), DeliveryRouteSet(ROUTES)
        )
        handle = FakeHandle(admission)
        first = self.egress.commit_and_emit(
            admission, handle, "assistant-response", "emission-1", 1, NOW
        )
        self.assertIsNotNone(first)
        self.assertEqual(
            self.authority.admissions[admission.admission_id].status,
            ReadAdmissionStatus.ACTIVE,
        )
        self.assertIsNone(
            self.egress.commit_and_emit(
                admission, handle, "assistant-response", "emission-2", 3, NOW
            )
        )
        closure = self.authority.begin_invalidation(
            AuthorizationInvalidation(
                "fence-emission-test", AuthorityKind.IDENTITY, "identity-1",
                1, 2, frozenset({admission.admission_id})
            )
        )
        fence_receipt = self.egress.fence(
            admission, "fence-emission-test", "assistant-response", closure.new_generation, NOW
        )
        self.assertIsNotNone(fence_receipt)
        self.assertEqual(fence_receipt.operation_id, "fence-emission-test")
        self.assertTrue(self.authority.record_endpoint_ack(fence_receipt))
        self.assertIsNone(
            self.egress.commit_and_emit(
                admission, handle, "assistant-response", "emission-2", 2, NOW
            )
        )


if __name__ == "__main__":
    unittest.main()
