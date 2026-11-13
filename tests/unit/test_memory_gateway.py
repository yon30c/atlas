import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from atlas.authorization.models import AuthorizationDecision, AuthorizationResult
from atlas.core.context import OperationContext
from atlas.core.identity import Identity, IdentityKind, IdentityStatus
from atlas.memory.consistency import (
    AuthorityKind,
    AuthorityRevision,
    AuthorizationRevisionSet,
    AuthorizationSnapshot,
    DeliveryRouteSet,
    EgressReceipt,
    EndpointCompletionReceipt,
    ReadAdmission,
    ReadAdmissionStatus,
    ReadTarget,
    ReconciliationResult,
)
from atlas.memory.gateway import MemoryGatewayService
from atlas.memory.models import (
    MemoryClassification,
    MemoryVersion,
    MemoryScope,
    MemoryScopeKind,
    MemoryVersionStatus,
)
from atlas.ports.protected_memory_read import ProtectedMemoryRead


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
MEMORY_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a11"
VERSION_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a12"
ROUTES = frozenset({"assistant-response", "api-response"})


def make_context():
    return OperationContext(
        request_id="request-1",
        correlation_id="correlation-1",
        actor=Identity("identity-1", IdentityKind.USER, IdentityStatus.ACTIVE),
        user_id="owner-1",
        origin="unit-test",
        delegation=None,
        project_id=None,
        environment=None,
        purpose="test memory gateway",
        classification="internal",
        created_at=NOW,
    )


def make_snapshot(grant_expires_at=None, memory_id=MEMORY_ID):
    project = grant_expires_at is not None
    scope = (
        MemoryScope(MemoryScopeKind.PROJECT, "project-1")
        if project
        else MemoryScope(MemoryScopeKind.PRIVATE)
    )
    revisions = AuthorizationRevisionSet(
        memory_revision=AuthorityRevision(AuthorityKind.MEMORY, memory_id, 1),
        version_revision=AuthorityRevision(AuthorityKind.MEMORY_VERSION, VERSION_ID, 1),
        identity_revision=AuthorityRevision(AuthorityKind.IDENTITY, "identity-1", 1),
        project_revision=(
            AuthorityRevision(AuthorityKind.PROJECT, "project-1", 1)
            if project else None
        ),
        environment_revision=(
            AuthorityRevision(AuthorityKind.ENVIRONMENT, "environment-1", 1)
            if project else None
        ),
        grant_revision=(
            AuthorityRevision(AuthorityKind.GRANT, "grant-1", 1)
            if project else None
        ),
    )
    return AuthorizationSnapshot(
        snapshot_id="snapshot-1",
        decision_id="decision-1",
        request_id="request-1",
        action="memory.read",
        actor_identity_id="identity-1",
        subject_user_id=None if project else "owner-1",
        memory_id=memory_id,
        version_id=VERSION_ID,
        owner_id="owner-1",
        scope=scope,
        revisions=revisions,
        version_status=MemoryVersionStatus.APPROVED,
        classification=MemoryClassification.CONFIDENTIAL,
        issued_at=NOW,
        project_id="project-1" if project else None,
        environment_id="environment-1" if project else None,
        grant_expires_at=grant_expires_at,
    )


class StubClock:
    def __init__(self, value=NOW, error=None):
        self.value = value
        self.error = error

    def now(self):
        if self.error:
            raise self.error
        return self.value


class SequenceClock:
    def __init__(self, values):
        self.values = list(values)

    def now(self):
        if not self.values:
            raise RuntimeError("clock sequence exhausted")
        return self.values.pop(0)


class StubAuthorization:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def authorize_read(self, context, memory_id, now, version_id):
        self.calls.append((context, memory_id, now, version_id))
        return self.result


class FakeHandle:
    def __init__(self, admission, classification=MemoryClassification.CONFIDENTIAL):
        self.handle_id = f"handle:{admission.admission_id}"
        self.admission_id = admission.admission_id
        self.memory_id = admission.target.memory_id
        self.version_id = admission.target.version_id
        self.classification = classification


class StubAuthority:
    def __init__(self, admission=None):
        self.admission = admission
        self.admit_calls = []
        self.acks = []
        self.reconciliations = []

    def admit_read(self, snapshot, routes, now):
        self.admit_calls.append((snapshot, routes))
        return self.admission

    def record_endpoint_ack(self, receipt):
        self.acks.append(receipt)
        return True

    def reconcile(self, operation_id):
        self.reconciliations.append(operation_id)
        return ReconciliationResult(operation_id, frozenset(), frozenset())


class StubContent:
    def __init__(self, handle=None, error=None):
        self.handle = handle
        self.error = error
        self.calls = []

    def read_version_if_admitted(self, snapshot, admission):
        self.calls.append((snapshot, admission))
        if self.error:
            raise self.error
        return self.handle


class StubEgress:
    def __init__(self):
        self.emissions = []
        self.finishes = []

    def commit_and_emit(self, admission, handle, endpoint_id, emission_id, sequence, now):
        self.emissions.append((admission, handle, endpoint_id, emission_id, sequence, now))
        return EgressReceipt(
            admission.admission_id, endpoint_id, emission_id, sequence,
            admission.generation, now
        )

    def finish(self, admission, operation_id, endpoint_id, final_sequence, now):
        self.finishes.append((admission, operation_id, endpoint_id, final_sequence, now))
        return EndpointCompletionReceipt(
            operation_id, admission.admission_id, endpoint_id,
            admission.generation, final_sequence, now
        )

    def fence(self, admission, operation_id, endpoint_id, new_generation, now):
        raise AssertionError("no debe llamarse desde el flujo de lectura normal")

    def reconcile(self, admission, endpoint_id):
        raise AssertionError("no se usa en estas pruebas")


def make_admission(snapshot, routes=ROUTES, snapshot_id=None):
    return ReadAdmission(
        admission_id="admission-1",
        snapshot_id=snapshot_id or snapshot.snapshot_id,
        target=ReadTarget(
            snapshot.memory_id, snapshot.version_id, snapshot.owner_id, snapshot.scope
        ),
        generation=1,
        route_ids=frozenset(routes),
        status=ReadAdmissionStatus.ADMITTED,
        admitted_at=NOW,
    )


class MemoryGatewayServiceTests(unittest.TestCase):

    def test_snapshot_for_another_actor_is_rejected_before_admission(self):
        revisions = replace(
            self.snapshot.revisions,
            identity_revision=AuthorityRevision(AuthorityKind.IDENTITY, "other-identity", 1),
        )
        other_actor_snapshot = replace(
            self.snapshot, actor_identity_id="other-identity", revisions=revisions
        )
        self.authorization.result = AuthorizationResult(
            AuthorizationDecision.ALLOW, other_actor_snapshot
        )
        self.assertIsNone(
            self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)
        )
        self.assertEqual(self.authority.admit_calls, [])
        self.assertEqual(self.content.calls, [])

    def test_snapshot_for_another_request_is_rejected_before_admission(self):
        other_request_snapshot = replace(self.snapshot, request_id="other-request")
        self.authorization.result = AuthorizationResult(
            AuthorizationDecision.ALLOW, other_request_snapshot
        )
        self.assertIsNone(
            self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)
        )
        self.assertEqual(self.authority.admit_calls, [])
        self.assertEqual(self.content.calls, [])

    def setUp(self):
        self.snapshot = make_snapshot()
        self.admission = make_admission(self.snapshot)
        self.authorization = StubAuthorization(
            AuthorizationResult(AuthorizationDecision.ALLOW, self.snapshot)
        )
        self.authority = StubAuthority(self.admission)
        self.egress = StubEgress()
        self.handle = FakeHandle(self.admission)
        self.content = StubContent(self.handle)
        self.clock = StubClock()
        self.gateway = MemoryGatewayService(
            self.authorization,
            self.content,
            self.authority,
            self.egress,
            DeliveryRouteSet(ROUTES),
            self.clock,
        )
        self.context = make_context()

    def test_denial_never_admits_or_reads_content(self):
        self.authorization.result = AuthorizationResult(AuthorizationDecision.DENY)

        result = self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)

        self.assertIsNone(result)
        self.assertEqual(self.authority.admit_calls, [])
        self.assertEqual(self.content.calls, [])

    def test_allow_returns_opaque_read_not_memory_version(self):
        result = self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)

        self.assertIsInstance(result, ProtectedMemoryRead)
        self.assertNotIsInstance(result, MemoryVersion)
        self.assertEqual(result.operation_id, "read:admission-1")
        self.assertIs(result.handle, self.handle)
        self.assertEqual(len(self.authority.admit_calls), 1)
        self.assertEqual(len(self.content.calls), 1)

    def test_preexisting_active_admission_is_not_closed_as_empty(self):
        self.authority.admission = replace(
            self.admission, status=ReadAdmissionStatus.ACTIVE
        )

        result = self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)

        self.assertIsNone(result)
        self.assertEqual(self.content.calls, [])
        self.assertEqual(self.egress.finishes, [])

    def test_mismatched_admission_is_rejected_before_content_read(self):
        self.authority.admission = make_admission(self.snapshot, snapshot_id="other")

        result = self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)

        self.assertIsNone(result)
        self.assertEqual(self.content.calls, [])
        self.assertEqual(len(self.egress.finishes), len(ROUTES))

    def test_missing_or_invalid_handle_closes_empty_admission(self):
        self.content.handle = None

        result = self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)

        self.assertIsNone(result)
        self.assertEqual(len(self.egress.finishes), len(ROUTES))
        self.assertEqual(len(self.authority.acks), len(ROUTES))
        self.assertEqual(
            self.authority.reconciliations, ["read:admission-1"]
        )

    def test_content_port_failure_closes_empty_admission(self):
        self.content.error = TimeoutError("protected content unavailable")

        result = self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)

        self.assertIsNone(result)
        self.assertEqual(len(self.egress.finishes), len(ROUTES))
        self.assertEqual(len(self.authority.acks), len(ROUTES))
        self.assertEqual(
            self.authority.reconciliations, ["read:admission-1"]
        )

    def test_snapshot_for_another_resource_is_rejected_before_admission(self):
        other = make_snapshot(
            memory_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c073a13"
        )
        self.authorization.result = AuthorizationResult(
            AuthorizationDecision.ALLOW, other
        )

        result = self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)

        self.assertIsNone(result)
        self.assertEqual(self.authority.admit_calls, [])
        self.assertEqual(self.content.calls, [])

    def test_restricted_or_mismatched_handle_is_never_returned(self):
        self.content.handle = FakeHandle(
            self.admission, MemoryClassification.RESTRICTED
        )
        self.assertIsNone(
            self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)
        )
        self.assertEqual(len(self.egress.finishes), len(ROUTES))

    def test_handle_for_another_memory_or_version_is_rejected(self):
        self.content.handle = FakeHandle(self.admission)
        self.content.handle.version_id = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a13"

        result = self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)

        self.assertIsNone(result)
        self.assertEqual(len(self.egress.finishes), len(ROUTES))
        self.assertEqual(len(self.authority.acks), len(ROUTES))

    def test_emit_requires_registered_endpoint_and_returns_egress_receipt(self):
        read = self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)
        receipt = self.gateway.emit_version(
            read, "assistant-response", "emission-1", 1
        )

        self.assertIsInstance(receipt, EgressReceipt)
        self.assertEqual(len(self.egress.emissions), 1)
        self.assertEqual(self.egress.emissions[0][2], "assistant-response")
        self.assertIsNone(
            self.gateway.emit_version(read, "unregistered", "emission-2", 2)
        )
        self.assertEqual(len(self.egress.emissions), 1)

    def test_grant_expiry_between_cam_and_admission_rejects_read(self):
        expires = NOW + timedelta(seconds=5)
        snapshot = make_snapshot(grant_expires_at=expires)
        self.authorization.result = AuthorizationResult(
            AuthorizationDecision.ALLOW, snapshot
        )
        self.gateway = MemoryGatewayService(
            self.authorization,
            self.content,
            self.authority,
            self.egress,
            DeliveryRouteSet(ROUTES),
            SequenceClock([NOW + timedelta(seconds=1), expires]),
        )

        result = self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)

        self.assertIsNone(result)
        self.assertEqual(self.authority.admit_calls, [])
        self.assertEqual(self.content.calls, [])

    def test_grant_expiry_is_checked_at_each_emission(self):
        expires = NOW + timedelta(seconds=5)
        snapshot = make_snapshot(grant_expires_at=expires)
        admission = make_admission(snapshot)
        handle = FakeHandle(admission)
        self.authorization.result = AuthorizationResult(
            AuthorizationDecision.ALLOW, snapshot
        )
        self.authority.admission = admission
        self.content.handle = handle
        self.clock.value = NOW + timedelta(seconds=1)
        read = self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)
        self.assertIsNotNone(read)
        self.clock.value = expires
        self.assertIsNone(
            self.gateway.emit_version(read, "assistant-response", "late", 1)
        )
        self.assertEqual(self.egress.emissions, [])

    def test_finish_requires_exact_endpoint_and_records_ack(self):
        read = self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)

        self.assertFalse(self.gateway.finish_version(read, "unknown", 0))
        self.assertTrue(
            self.gateway.finish_version(read, "assistant-response", 0)
        )
        self.assertEqual(len(self.egress.finishes), 1)
        self.assertEqual(len(self.authority.acks), 1)

    def test_reconciliation_is_read_only(self):
        read = self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)

        result = self.gateway.reconcile_version(read)

        self.assertIsInstance(result, ReconciliationResult)
        self.assertEqual(
            self.authority.reconciliations, ["read:admission-1"]
        )

    def test_non_utc_clock_is_rejected_before_admission_and_emission(self):
        self.clock.value = datetime(
            2026, 11, 13, 8, 0, tzinfo=timezone(timedelta(hours=-4))
        )
        self.assertIsNone(
            self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)
        )
        self.assertEqual(self.authority.admit_calls, [])
        self.assertEqual(self.content.calls, [])

        self.clock.value = NOW
        read = self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)
        self.clock.value = datetime(
            2026, 11, 13, 8, 0, tzinfo=timezone(timedelta(hours=-4))
        )
        self.assertIsNone(
            self.gateway.emit_version(read, "assistant-response", "bad-time", 1)
        )
        self.assertEqual(self.egress.emissions, [])

    def test_clock_or_authorization_failure_never_reads_content(self):
        self.clock.error = RuntimeError("clock unavailable")
        self.assertIsNone(
            self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)
        )
        self.clock.error = None
        self.authorization.result = object()
        self.assertIsNone(
            self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)
        )
        self.assertEqual(self.content.calls, [])


if __name__ == "__main__":
    unittest.main()
