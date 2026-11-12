from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import unittest

from atlas.core.context import OperationContext
from atlas.core.enums import DelegationMode
from atlas.core.errors import ContractError
from atlas.core.identity import Identity, IdentityKind, IdentityStatus
from tests.fixtures.contexts import user_context


class OperationContextTests(unittest.TestCase):
    def test_valid_context_is_created(self):
        context = user_context()
        self.assertIsInstance(context, OperationContext)
        self.assertIsInstance(context.actor, Identity)
        self.assertEqual(context.actor.identity_id, "assistant")
        self.assertIs(context.actor.kind, IdentityKind.AGENT)
        self.assertIs(context.actor.status, IdentityStatus.ACTIVE)
        self.assertEqual(context.user_id, "user-1")
        self.assertIs(context.delegation, DelegationMode.DELEGATED)

    def test_required_fields_reject_blank_values(self):
        fields = (
            "request_id",
            "correlation_id",
            "user_id",
            "origin",
            "purpose",
            "classification",
        )
        for field in fields:
            with self.subTest(field=field):
                with self.assertRaises(ContractError):
                    replace(user_context(), **{field: "   "})

    def test_actor_must_be_identity(self):
        with self.assertRaises(ContractError):
            replace(user_context(), actor="assistant")

    def test_delegation_can_be_none(self):
        context = replace(user_context(), delegation=None)
        self.assertIsNone(context.delegation)

    def test_invalid_delegation_is_rejected(self):
        with self.assertRaises(ContractError):
            replace(user_context(), delegation="delegated")

    def test_project_and_environment_can_be_none(self):
        context = replace(
            user_context(),
            project_id=None,
            environment=None,
        )
        self.assertIsNone(context.project_id)
        self.assertIsNone(context.environment)

    def test_blank_project_or_environment_is_rejected(self):
        for field in ("project_id", "environment"):
            with self.subTest(field=field):
                with self.assertRaises(ContractError):
                    replace(user_context(), **{field: "   "})

    def test_created_at_must_be_datetime(self):
        with self.assertRaises(ContractError):
            replace(user_context(), created_at="2026-01-01T00:00:00+00:00")

    def test_created_at_must_be_timezone_aware(self):
        with self.assertRaises(ContractError):
            replace(user_context(), created_at=datetime(2026, 1, 1))

    def test_created_at_must_have_zero_utc_offset(self):
        created_at = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=1)))
        with self.assertRaises(ContractError):
            replace(user_context(), created_at=created_at)

    def test_context_is_immutable(self):
        context = user_context()
        with self.assertRaises(FrozenInstanceError):
            context.user_id = "user-2"


if __name__ == "__main__":
    unittest.main()
