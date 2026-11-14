import unittest
from datetime import datetime, timedelta, timezone

from atlas.core.errors import ContractError
from atlas.memory.consistency import (
    AuthorityKind,
    AuthorityRevision,
    AuthorizationRevisionSet,
    AuthorizationSnapshot,
    DeliveryRouteSet,
    ConsistencyPosition,
)
from atlas.memory.models import (
    MemoryClassification,
    MemoryScope,
    MemoryScopeKind,
    MemoryVersionStatus,
)
from atlas.memory.revision_validation import (
    RevisionValidationResult,
    RevisionValidationStatus,
)
from atlas.memory.route_registry import (
    DeliveryRouteDescriptor,
    RouteRegistryResult,
    RouteRegistryStatus,
)


NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
POSITION = ConsistencyPosition("memory-domain", 1, 7)
MEMORY_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a11"
VERSION_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a12"


def private_snapshot():
    revisions = AuthorizationRevisionSet(
        memory_revision=AuthorityRevision(AuthorityKind.MEMORY, MEMORY_ID, 1),
        version_revision=AuthorityRevision(AuthorityKind.MEMORY_VERSION, VERSION_ID, 2),
        identity_revision=AuthorityRevision(AuthorityKind.IDENTITY, "identity-1", 3),
    )
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
        revisions=revisions,
        version_status=MemoryVersionStatus.APPROVED,
        classification=MemoryClassification.CONFIDENTIAL,
        issued_at=NOW,
    )


class RouteRegistryContractTests(unittest.TestCase):
    def test_resolved_result_requires_exact_route_set(self):
        requested = frozenset({"assistant-response", "api-response"})
        routes = (
            DeliveryRouteDescriptor("assistant-response", 1, True, True),
            DeliveryRouteDescriptor("api-response", 4, True, True),
        )
        result = RouteRegistryResult(requested, RouteRegistryStatus.RESOLVED, routes, POSITION)
        self.assertTrue(result.usable_for_protected_delivery)

    def test_partial_unknown_or_duplicate_routes_are_rejected(self):
        requested = frozenset({"assistant-response", "api-response"})
        with self.assertRaises(ContractError):
            RouteRegistryResult(
                requested,
                RouteRegistryStatus.RESOLVED,
                (DeliveryRouteDescriptor("assistant-response", 1, True, True),),
                POSITION,
            )
        with self.assertRaises(ContractError):
            RouteRegistryResult(
                requested,
                RouteRegistryStatus.RESOLVED,
                (
                    DeliveryRouteDescriptor("assistant-response", 1, True, True),
                    DeliveryRouteDescriptor("assistant-response", 2, True, True),
                ),
                POSITION,
            )

    def test_unavailable_and_rejected_results_cannot_return_partial_routes(self):
        requested = frozenset({"assistant-response"})
        route = DeliveryRouteDescriptor("assistant-response", 1, True, True)
        for status in (RouteRegistryStatus.UNAVAILABLE, RouteRegistryStatus.REJECTED):
            with self.assertRaises(ContractError):
                RouteRegistryResult(requested, status, (route,), POSITION)
        self.assertFalse(
            RouteRegistryResult(requested, RouteRegistryStatus.UNAVAILABLE).usable_for_protected_delivery
        )

    def test_disabled_or_unfenceable_route_is_not_usable(self):
        requested = frozenset({"assistant-response"})
        disabled = RouteRegistryResult(
            requested,
            RouteRegistryStatus.RESOLVED,
            (DeliveryRouteDescriptor("assistant-response", 1, False, True),),
            POSITION,
        )
        unfenceable = RouteRegistryResult(
            requested,
            RouteRegistryStatus.RESOLVED,
            (DeliveryRouteDescriptor("assistant-response", 1, True, False),),
            POSITION,
        )
        self.assertFalse(disabled.usable_for_protected_delivery)
        self.assertFalse(unfenceable.usable_for_protected_delivery)

    def test_route_descriptor_rejects_invalid_revision_and_flags(self):
        with self.assertRaises(ContractError):
            DeliveryRouteDescriptor("route", 0, True, True)
        with self.assertRaises(ContractError):
            DeliveryRouteDescriptor("route", 1, 1, True)


class RevisionValidationContractTests(unittest.TestCase):
    def test_current_result_is_bound_to_exact_snapshot_and_revisions(self):
        snapshot = private_snapshot()
        result = RevisionValidationResult.current(snapshot, NOW, POSITION)
        self.assertEqual(result.snapshot_id, snapshot.snapshot_id)
        self.assertEqual(result.status, RevisionValidationStatus.CURRENT)
        self.assertEqual(result.current_revisions, snapshot.revisions)
        self.assertEqual(result.validated_position, POSITION)

    def test_stale_result_requires_different_authoritative_revision_vector(self):
        snapshot = private_snapshot()
        current = AuthorizationRevisionSet(
            memory_revision=AuthorityRevision(AuthorityKind.MEMORY, MEMORY_ID, 1),
            version_revision=AuthorityRevision(AuthorityKind.MEMORY_VERSION, VERSION_ID, 3),
            identity_revision=AuthorityRevision(AuthorityKind.IDENTITY, "identity-1", 3),
        )
        result = RevisionValidationResult(
            snapshot_id=snapshot.snapshot_id,
            expected_revisions=snapshot.revisions,
            status=RevisionValidationStatus.STALE,
            checked_at=NOW,
            current_revisions=current,
            validated_position=POSITION,
        )
        self.assertNotEqual(result.current_revisions, result.expected_revisions)

    def test_stale_cannot_claim_identical_revision_vector(self):
        snapshot = private_snapshot()
        with self.assertRaises(ContractError):
            RevisionValidationResult(
                snapshot_id=snapshot.snapshot_id,
                expected_revisions=snapshot.revisions,
                status=RevisionValidationStatus.STALE,
                checked_at=NOW,
                current_revisions=snapshot.revisions,
                validated_position=POSITION,
            )

    def test_current_cannot_claim_different_revision_vector(self):
        snapshot = private_snapshot()
        different = AuthorizationRevisionSet(
            memory_revision=AuthorityRevision(AuthorityKind.MEMORY, MEMORY_ID, 2),
            version_revision=AuthorityRevision(AuthorityKind.MEMORY_VERSION, VERSION_ID, 2),
            identity_revision=AuthorityRevision(AuthorityKind.IDENTITY, "identity-1", 3),
        )
        with self.assertRaises(ContractError):
            RevisionValidationResult(
                snapshot_id=snapshot.snapshot_id,
                expected_revisions=snapshot.revisions,
                status=RevisionValidationStatus.CURRENT,
                checked_at=NOW,
                current_revisions=different,
                validated_position=POSITION,
            )

    def test_rejected_and_unavailable_do_not_expose_revision_data(self):
        snapshot = private_snapshot()
        for status in (RevisionValidationStatus.REJECTED, RevisionValidationStatus.UNAVAILABLE):
            result = RevisionValidationResult(
                snapshot_id=snapshot.snapshot_id,
                expected_revisions=snapshot.revisions,
                status=status,
                checked_at=NOW,
            )
            self.assertIsNone(result.current_revisions)
            with self.assertRaises(ContractError):
                RevisionValidationResult(
                    snapshot_id=snapshot.snapshot_id,
                    expected_revisions=snapshot.revisions,
                    status=status,
                    checked_at=NOW,
                    current_revisions=snapshot.revisions,
                )

    def test_validation_timestamp_must_be_utc(self):
        snapshot = private_snapshot()
        with self.assertRaises(ContractError):
            RevisionValidationResult.current(
                snapshot, NOW.astimezone(timezone(timedelta(hours=-4))), POSITION
            )


if __name__ == "__main__":
    unittest.main()
