"""End-to-end SQLite append tests using the real local HMAC signer."""
from datetime import datetime
import tempfile
import unittest
from pathlib import Path

from atlas.adapters.local_hmac_signer import HmacLocalConsistencySigner
from atlas.adapters.sqlite.consistency_journal import SQLiteConsistencyJournal
from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.core.errors import ContractError
from atlas.memory.envelope import AuthenticatedConsistencyEnvelope
from atlas.memory.journal import ConsistencyPosition, JournalEntry
from atlas.memory.local_auth import journal_entry_payload, verify_envelope
from atlas.memory.local_keys import ActiveLocalConsistencyKey
from unit.test_memory_journal import RECORD_1, read_admitted


class FakeActiveKeyProvider:
    """Test-only in-memory key source; never used by production composition."""

    def __init__(self, key):
        self.key = key

    def load_active_key(self):
        return self.key


class SQLiteLocalHmacIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "atlas.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.key = bytes.fromhex("6d" * 32)

    def _journal(self, key_reference="local-key-v1", active_key_reference=None):
        active_reference = active_key_reference or key_reference
        provider = FakeActiveKeyProvider(
            ActiveLocalConsistencyKey(active_reference, self.key)
        )
        signer = HmacLocalConsistencySigner(provider)
        journal = SQLiteConsistencyJournal(
            self.database,
            signer,
            reducer_version="reducer-v1",
            issuer_id="atlas-journal",
            issuer_role="consistency-journal",
            key_reference=key_reference,
            trust_policy_version="local-policy-v1",
        )
        self.assertTrue(journal.create_local_domain("atlas-local", 1))
        return journal

    def test_sqlite_append_is_signed_by_real_hmac_signer_and_verifiable(self):
        journal = self._journal()
        transition = read_admitted(record_id=RECORD_1)
        commit = journal.append_transition(
            ConsistencyPosition("atlas-local", 1, 0),
            "append-hmac-integration",
            transition,
        )

        self.assertIsNotNone(commit)
        self.assertFalse(commit.replayed)

        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM journal_entries
                WHERE domain_id='atlas-local' AND authority_epoch=1 AND sequence=1
                """
            ).fetchone()

        self.assertIsNotNone(row)
        position = ConsistencyPosition(
            row["domain_id"], row["authority_epoch"], row["sequence"]
        )
        envelope = AuthenticatedConsistencyEnvelope(
            object_kind="journal_entry",
            envelope_version=row["envelope_version"],
            consistency_domain_id=row["domain_id"],
            authority_epoch=row["authority_epoch"],
            sequence=row["sequence"],
            object_id=row["record_id"],
            schema_version=row["schema_version"],
            reducer_version=row["reducer_version"],
            previous_commitment=row["previous_commitment"],
            object_commitment=row["object_commitment"],
            issuer_id=row["issuer_id"],
            issuer_role=row["issuer_role"],
            key_reference=row["key_reference"],
            trust_policy_version=row["trust_policy_version"],
            issued_at=datetime.fromisoformat(row["issued_at"]),
            authentication_evidence=row["authentication_evidence"],
        )
        entry = JournalEntry(position, transition, envelope)

        self.assertEqual(envelope.key_reference, "local-key-v1")
        self.assertTrue(
            verify_envelope(envelope, journal_entry_payload(entry), self.key)
        )

    def test_missing_active_key_aborts_sqlite_append_atomically(self):
        class MissingKeyProvider:
            def load_active_key(self):
                return None

        signer = HmacLocalConsistencySigner(MissingKeyProvider())
        journal = SQLiteConsistencyJournal(
            self.database,
            signer,
            reducer_version="reducer-v1",
            issuer_id="atlas-journal",
            issuer_role="consistency-journal",
            key_reference="local-key-v1",
            trust_policy_version="local-policy-v1",
        )
        self.assertTrue(journal.create_local_domain("atlas-local", 1))
        result = journal.append_transition(
            ConsistencyPosition("atlas-local", 1, 0),
            "append-no-key",
            read_admitted(record_id=RECORD_1),
        )
        self.assertIsNone(result)
        with self.database.connection() as connection:
            head = connection.execute(
                "SELECT head_sequence FROM consistency_domains WHERE domain_id='atlas-local'"
            ).fetchone()[0]
            count = connection.execute(
                "SELECT COUNT(*) FROM journal_entries WHERE domain_id='atlas-local'"
            ).fetchone()[0]
        self.assertEqual(head, 0)
        self.assertEqual(count, 0)

    def test_active_key_reference_mismatch_aborts_sqlite_append_atomically(self):
        journal = self._journal(
            key_reference="local-key-v1",
            active_key_reference="different-key",
        )
        result = journal.append_transition(
            ConsistencyPosition("atlas-local", 1, 0),
            "append-wrong-key-ref",
            read_admitted(record_id=RECORD_1),
        )
        self.assertIsNone(result)
        with self.database.connection() as connection:
            head = connection.execute(
                "SELECT head_sequence FROM consistency_domains WHERE domain_id='atlas-local'"
            ).fetchone()[0]
            count = connection.execute(
                "SELECT COUNT(*) FROM journal_entries WHERE domain_id='atlas-local'"
            ).fetchone()[0]
        self.assertEqual(head, 0)
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
