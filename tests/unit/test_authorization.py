from dataclasses import FrozenInstanceError, replace
import unittest

from atlas.authorization.models import (
    AuthorizationDecision,
    AuthorizationRequest,
    AuthorizationResult,
)
from atlas.core.errors import ContractError
from tests.fixtures.contexts import user_context


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
                self.assertEqual(
                    AuthorizationResult(decision=decision).decision,
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
