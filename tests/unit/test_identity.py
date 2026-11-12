import unittest
from dataclasses import FrozenInstanceError

from atlas.core.errors import ContractError
from atlas.core.identity import Identity, IdentityKind, IdentityStatus


class IdentityTests(unittest.TestCase):
    def test_all_identity_kinds_are_supported(self):
        for kind in IdentityKind:
            with self.subTest(kind=kind):
                identity = Identity(
                    identity_id="test-identity",
                    kind=kind,
                    status=IdentityStatus.ACTIVE,
                )
                self.assertIs(identity.kind, kind)

    def test_all_identity_statuses_are_supported(self):
        for status in IdentityStatus:
            with self.subTest(status=status):
                identity = Identity(
                    identity_id="test-identity",
                    kind=IdentityKind.AGENT,
                    status=status,
                )
                self.assertIs(identity.status, status)

    def test_empty_identity_id_is_rejected(self):
        for value in ("", "   ", "\t", "\n"):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ContractError):
                    Identity(value, IdentityKind.AGENT, IdentityStatus.ACTIVE)

    def test_invalid_kind_is_rejected(self):
        with self.assertRaises(ContractError):
            Identity("agent-1", "agent", IdentityStatus.ACTIVE)

    def test_invalid_status_is_rejected(self):
        with self.assertRaises(ContractError):
            Identity("agent-1", IdentityKind.AGENT, "active")

    def test_identity_is_immutable(self):
        identity = Identity(
            "agent-1",
            IdentityKind.AGENT,
            IdentityStatus.ACTIVE,
        )
        with self.assertRaises(FrozenInstanceError):
            identity.identity_id = "agent-2"


if __name__ == "__main__":
    unittest.main()
