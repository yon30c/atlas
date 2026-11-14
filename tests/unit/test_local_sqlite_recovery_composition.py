"""Contract tests for the local SQLite recovery composition root."""
import unittest

from atlas.adapters.sqlite.consistency_journal import SQLiteConsistencyJournal
from atlas.adapters.sqlite.local_journal_composition import (
    compose_local_sqlite_recovery_coordinator,
    compose_local_sqlite_recovery_gate_coordinator,
)
from atlas.core.errors import ContractError


class FakeAuthority:
    def __init__(self, journal):
        self.consistency_journal = journal

    def admit_read(self, *args): pass
    def begin_forget(self, *args): pass
    def reconcile_forget(self, *args): pass
    def begin_invalidation(self, *args): pass
    def record_endpoint_ack(self, *args): pass
    def get_nonterminal_admissions(self, *args): pass
    def reconcile(self, *args): pass
    def commit_and_emit(self, *args): pass
    def finish(self, *args): pass
    def fence(self, *args): pass
    def reconcile_endpoint(self, *args): pass
    def close_recovery_gate(self, *args): pass
    def ensure_recovery_gate_closed(self, *args): pass
    def reconcile_and_open_recovery_gate(self, *args): pass
    def ensure_recovery_gate_open(self, *args): pass


class IncompleteAuthority:
    def __init__(self, journal):
        self.consistency_journal = journal


class FakeVerifier:
    def verify_terminal_receipt_with_context(self, *args): pass


class FakeTrustContextFactory:
    def for_terminal_receipt(self, *args): pass


class LocalSQLiteRecoveryCompositionTests(unittest.TestCase):
    @staticmethod
    def make_journal():
        # Composition-only test double: no SQLite operations are invoked.
        journal = SQLiteConsistencyJournal.__new__(SQLiteConsistencyJournal)
        journal._recovery_trust_policy = object()
        journal._database = object()
        return journal

    def compose(self, journal, authority):
        return compose_local_sqlite_recovery_coordinator(
            journal=journal,
            consistency_authority=authority,
            fencer=object(),
            verifier=FakeVerifier(),
            trust_context_factory=FakeTrustContextFactory(),
            domain_id="domain-test",
            id_factory=lambda: "record-test",
            clock=lambda: None,
        )

    def test_coordinator_uses_paired_ports_and_exact_shared_authority(self):
        journal = self.make_journal()
        authority = FakeAuthority(journal)

        composition = self.compose(journal, authority)

        self.assertIs(composition.consistency_authority, authority)
        self.assertIs(composition.journal_ports.persistence._journal, journal)
        self.assertIs(composition.journal_ports.verified_recovery._journal, journal)
        self.assertIs(composition.coordinator._journal, composition.journal_ports.persistence)
        self.assertIs(
            composition.coordinator._verified_recovery,
            composition.journal_ports.verified_recovery,
        )
        self.assertIs(composition.coordinator._recovery_gate, authority)

    def test_authority_bound_to_another_journal_is_rejected(self):
        journal = self.make_journal()
        authority = FakeAuthority(self.make_journal())

        with self.assertRaises(ContractError):
            self.compose(journal, authority)

    def test_gate_only_composition_uses_exact_journal_and_gate(self):
        journal = self.make_journal()
        composition = compose_local_sqlite_recovery_gate_coordinator(
            journal=journal,
            fencer=object(),
            verifier=FakeVerifier(),
            trust_context_factory=FakeTrustContextFactory(),
            domain_id="domain-test",
            id_factory=lambda: "record-test",
            clock=lambda: None,
        )
        self.assertIs(composition.recovery_gate.consistency_journal, journal)
        self.assertIs(
            composition.journal_ports.persistence._journal,
            composition.recovery_gate.consistency_journal,
        )
        self.assertIs(
            composition.coordinator._recovery_gate,
            composition.recovery_gate,
        )
        self.assertIs(
            composition.coordinator._verified_recovery,
            composition.journal_ports.verified_recovery,
        )

    def test_incomplete_authority_is_rejected(self):
        journal = self.make_journal()

        with self.assertRaises(ContractError):
            self.compose(journal, IncompleteAuthority(journal))


if __name__ == "__main__":
    unittest.main()
