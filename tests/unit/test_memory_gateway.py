import unittest
from datetime import datetime, timezone

from atlas.authorization.models import AuthorizationDecision, AuthorizationResult
from atlas.core.context import OperationContext
from atlas.core.identity import Identity, IdentityKind, IdentityStatus
from atlas.memory.gateway import MemoryGatewayService
from atlas.memory.models import (
    MemoryClassification,
    MemoryVersion,
    MemoryVersionStatus,
    MemoryProvenance,
    ProvenanceContext,
    SourceKind,
)
from atlas.memory.models import MemoryId, MemoryVersionId


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
MEMORY_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a11"
VERSION_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a12"


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


def make_version(
    memory_id=MEMORY_ID,
    version_id=VERSION_ID,
    status=MemoryVersionStatus.APPROVED,
    classification=MemoryClassification.CONFIDENTIAL,
):
    provenance = MemoryProvenance(
        source_kind=SourceKind.USER_INPUT,
        source_ref=None,
        captured_at=NOW,
        captured_by="identity-1",
        origin_context=ProvenanceContext(
            origin="unit-test",
            actor_identity_id="identity-1",
            request_id="request-1",
            correlation_id="correlation-1",
        ),
    )
    return MemoryVersion(
        version_id=version_id,
        memory_id=memory_id,
        version_number=1,
        content="contenido confidencial de prueba",
        classification=classification,
        status=status,
        provenance=provenance,
        parent_version_id=None,
        created_at=NOW,
        submitted_at=NOW,
        reviewed_at=NOW if status is not MemoryVersionStatus.PENDING_REVIEW else None,
        reviewed_by="owner-1" if status is not MemoryVersionStatus.PENDING_REVIEW else None,
    )


class StubClock:
    def __init__(self, value=NOW, error=None):
        self.value = value
        self.error = error

    def now(self):
        if self.error:
            raise self.error
        return self.value


class StubAuthorization:
    def __init__(self, result=None, error=None):
        self.result = result or AuthorizationResult(AuthorizationDecision.ALLOW)
        self.error = error
        self.calls = []

    def authorize_read(self, context, memory_id, now, version_id):
        self.calls.append((context, memory_id, now, version_id))
        if self.error:
            raise self.error
        return self.result


class SpyContentPort:
    def __init__(self, version=None, error=None):
        self.version = version
        self.error = error
        self.calls = []

    def get_version_content(self, memory_id, version_id):
        self.calls.append((memory_id, version_id))
        if self.error:
            raise self.error
        return self.version


class MemoryGatewayServiceTests(unittest.TestCase):
    def setUp(self):
        self.authorization = StubAuthorization()
        self.content = SpyContentPort(make_version())
        self.clock = StubClock()
        self.gateway = MemoryGatewayService(
            self.authorization,
            self.content,
            self.clock,
        )
        self.context = make_context()

    def test_denial_never_reads_content_store(self):
        self.authorization.result = AuthorizationResult(AuthorizationDecision.DENY)

        result = self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)

        self.assertIsNone(result)
        self.assertEqual(self.content.calls, [])

    def test_require_approval_never_reads_content_store(self):
        self.authorization.result = AuthorizationResult(
            AuthorizationDecision.REQUIRE_APPROVAL
        )

        result = self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)

        self.assertIsNone(result)
        self.assertEqual(self.content.calls, [])

    def test_allow_reads_only_the_exact_memory_and_version(self):
        expected = self.content.version

        result = self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)

        self.assertIs(result, expected)
        self.assertEqual(self.content.calls, [(MEMORY_ID, VERSION_ID)])
        self.assertEqual(
            self.authorization.calls,
            [(self.context, MEMORY_ID, NOW, VERSION_ID)],
        )

    def test_mismatched_returned_ids_are_never_exposed(self):
        self.content.version = make_version(version_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c073a13")

        result = self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)

        self.assertIsNone(result)

    def test_unapproved_or_restricted_content_is_never_exposed(self):
        self.content.version = make_version(status=MemoryVersionStatus.PENDING_REVIEW)
        self.assertIsNone(self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID))

        self.content.version = make_version(
            classification=MemoryClassification.RESTRICTED
        )
        self.assertIsNone(self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID))

    def test_invalid_authorization_response_fails_closed(self):
        self.authorization.result = object()

        result = self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)

        self.assertIsNone(result)
        self.assertEqual(self.content.calls, [])

    def test_authorization_or_clock_failure_never_reads_content(self):
        self.authorization.error = TimeoutError("CAM unavailable")
        self.assertIsNone(self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID))
        self.assertEqual(self.content.calls, [])

        self.authorization.error = None
        self.clock.error = RuntimeError("clock unavailable")
        self.assertIsNone(self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID))
        self.assertEqual(self.content.calls, [])

    def test_content_store_failure_returns_no_content(self):
        self.content.error = TimeoutError("content store unavailable")

        result = self.gateway.get_version(self.context, MEMORY_ID, VERSION_ID)

        self.assertIsNone(result)

    def test_invalid_identifiers_do_not_call_authorization_or_content(self):
        result = self.gateway.get_version(self.context, MemoryId(" "), MemoryVersionId(VERSION_ID))

        self.assertIsNone(result)
        self.assertEqual(self.authorization.calls, [])
        self.assertEqual(self.content.calls, [])


if __name__ == "__main__":
    unittest.main()
