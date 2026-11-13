from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
import unittest

from atlas.memory.consistency import (
    AuthorityKind, AuthorityRevision, AuthorizationRevisionSet, AuthorizationSnapshot,
)
from atlas.memory.models import (
    MemoryClassification, MemoryScope, MemoryScopeKind, MemoryVersionStatus,
)

from atlas.authorization.models import (
    AuthorizationDecision,
    AuthorizationRequest,
    AuthorizationResult,
)
from atlas.core.errors import ContractError
from tests.fixtures.contexts import user_context


def make_authorization_snapshot():
    memory_id = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a11"
    version_id = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a12"
    return AuthorizationSnapshot(
        snapshot_id="snapshot-1",
        decision_id="decision-1",
        request_id="request-1",
        action="memory.read",
        actor_identity_id="identity-1",
        subject_user_id="owner-1",
        memory_id=memory_id,
        version_id=version_id,
        owner_id="owner-1",
        scope=MemoryScope(MemoryScopeKind.PRIVATE),
        revisions=AuthorizationRevisionSet(
            memory_revision=AuthorityRevision(AuthorityKind.MEMORY, memory_id, 1),
            version_revision=AuthorityRevision(AuthorityKind.MEMORY_VERSION, version_id, 1),
            identity_revision=AuthorityRevision(AuthorityKind.IDENTITY, "identity-1", 1),
        ),
        version_status=MemoryVersionStatus.APPROVED,
        classification=MemoryClassification.CONFIDENTIAL,
        issued_at=datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc),
    )


class AuthorizationModelTests(unittest.TestCase):
    def setUp(self):
        self.request = AuthorizationRequest(
            context=user_context(),
            action="memory.read",
            resource_type="memory",
            resource_id="memory-1",
            resource_owner_id="user-1",
        )

    def test_request_accepts_valid_values(self):
        self.assertEqual(self.request.context.user_id, "user-1")

    def test_request_requires_operation_context(self):
        with self.assertRaises(ContractError):
            replace(self.request, context="context")

    def test_request_rejects_blank_string_fields(self):
        for field in (
            "action",
            "resource_type",
            "resource_id",
            "resource_owner_id",
        ):
            with self.subTest(field=field):
                with self.assertRaises(ContractError):
                    replace(self.request, **{field: "  "})

    def test_result_accepts_each_decision(self):
        for decision in AuthorizationDecision:
            with self.subTest(decision=decision):
                snapshot = (
                    make_authorization_snapshot()
                    if decision is AuthorizationDecision.ALLOW else None
                )
                self.assertEqual(
                    AuthorizationResult(decision=decision, snapshot=snapshot).decision,
                    decision,
                )

    def test_result_rejects_invalid_decision(self):
        with self.assertRaises(ContractError):
            AuthorizationResult(decision="allow")

    def test_request_and_result_are_immutable(self):
        result = AuthorizationResult(AuthorizationDecision.DENY)
        with self.assertRaises(FrozenInstanceError):
            self.request.action = "memory.write"
        with self.assertRaises(FrozenInstanceError):
            result.decision = AuthorizationDecision.ALLOW


if __name__ == "__main__":
    unittest.main()
