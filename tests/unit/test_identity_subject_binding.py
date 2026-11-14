import unittest
from datetime import datetime, timezone

from atlas.authorization.identity_binding import (
    AuthenticatedUserSubject,
    resolve_authenticated_user_subject,
)
from atlas.core.context import OperationContext
from atlas.core.errors import ContractError
from atlas.core.identity import Identity, IdentityKind, IdentityStatus


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


class StubBindingPort:
    def __init__(self, binding=None, error=None):
        self.binding = binding
        self.error = error
        self.requested_actor_ids = []

    def resolve_user_subject(self, actor_identity_id):
        self.requested_actor_ids.append(actor_identity_id)
        if self.error is not None:
            raise self.error
        return self.binding


def make_context(kind=IdentityKind.USER, status=IdentityStatus.ACTIVE):
    return OperationContext(
        request_id="request-1",
        correlation_id="correlation-1",
        actor=Identity("identity-user-1", kind, status),
        user_id="untrusted-context-user",
        origin="test",
        delegation=None,
        project_id=None,
        environment=None,
        purpose="test identity binding",
        classification="internal",
        created_at=NOW,
    )


class IdentitySubjectBindingTests(unittest.TestCase):
    def test_returns_subject_from_trusted_binding_not_context_user_id(self):
        port = StubBindingPort(
            AuthenticatedUserSubject("identity-user-1", "canonical-user-7", True, 1)
        )

        result = resolve_authenticated_user_subject(make_context(), port)

        self.assertEqual(result, "canonical-user-7")
        self.assertEqual(port.requested_actor_ids, ["identity-user-1"])

    def test_non_user_actor_is_denied_without_lookup(self):
        port = StubBindingPort(
            AuthenticatedUserSubject("identity-user-1", "user-7", True, 1)
        )
        context = make_context(kind=IdentityKind.AGENT)

        self.assertIsNone(resolve_authenticated_user_subject(context, port))
        self.assertEqual(port.requested_actor_ids, [])

    def test_inactive_actor_or_binding_is_denied(self):
        active_binding = AuthenticatedUserSubject(
            "identity-user-1", "user-7", True, 1
        )
        port = StubBindingPort(active_binding)
        self.assertIsNone(resolve_authenticated_user_subject(
            make_context(status=IdentityStatus.SUSPENDED), port
        ))

        port = StubBindingPort(AuthenticatedUserSubject(
            "identity-user-1", "user-7", False, 1
        ))
        self.assertIsNone(resolve_authenticated_user_subject(make_context(), port))

    def test_mismatched_actor_binding_is_denied(self):
        port = StubBindingPort(
            AuthenticatedUserSubject("another-identity", "user-7", True, 1)
        )
        self.assertIsNone(resolve_authenticated_user_subject(make_context(), port))

    def test_stale_binding_revision_is_denied(self):
        port = StubBindingPort(
            AuthenticatedUserSubject("identity-user-1", "user-7", True, 2)
        )
        self.assertIsNone(resolve_authenticated_user_subject(make_context(), port))

    def test_missing_or_failing_binding_port_is_denied(self):
        self.assertIsNone(resolve_authenticated_user_subject(make_context(), None))
        port = StubBindingPort(error=TimeoutError("identity provider unavailable"))
        self.assertIsNone(resolve_authenticated_user_subject(make_context(), port))

    def test_invalid_binding_values_are_rejected(self):
        with self.assertRaises(ContractError):
            AuthenticatedUserSubject("", "user-7", True, 1)
        with self.assertRaises(ContractError):
            AuthenticatedUserSubject("identity-user-1", "user-7", True, 0)
        with self.assertRaises(ContractError):
            AuthenticatedUserSubject("identity-user-1", "user-7", 1, 1)


if __name__ == "__main__":
    unittest.main()
