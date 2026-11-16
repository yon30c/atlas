"""Contract tests for immutable SQLite recovery-evidence issuer trust policies."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from atlas.adapters.sqlite import (
    SQLiteDatabase,
    SQLiteLocalAuthorityUnitOfWorkFactory,
    SQLiteRecoveryEvidenceIssuerTrustPolicyRepository,
    SQLITE_MIGRATIONS,
)
from atlas.authorization.recovery_evidence_trust import (
    RecoveryEvidenceIssuerTrustPolicy,
)
from atlas.core.errors import ConcurrencyError, ContractError, NotFoundError
from atlas.memory.authority_changes import MultiAuthorityRecoveryEvidenceKind


NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def make_policy(**overrides):
    values = {
        "issuer_id": "trusted-source-1",
        "policy_revision": 1,
        "enabled": True,
        "allowed_evidence_kinds": (
            MultiAuthorityRecoveryEvidenceKind.SOURCE_OUTCOME_RECEIPT,
        ),
        "valid_from": NOW - timedelta(days=1),
        "valid_until": NOW + timedelta(days=30),
        "max_evidence_lifetime_seconds": 600,
    }
    values.update(overrides)
    return RecoveryEvidenceIssuerTrustPolicy(**values)


class SQLiteRecoveryEvidenceIssuerTrustPolicyRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "atlas.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.repository = SQLiteRecoveryEvidenceIssuerTrustPolicyRepository(
            self.database
        )

    def test_create_and_get_policy_round_trip(self):
        policy = make_policy()
        self.repository.create(policy)
        self.assertEqual(self.repository.get_policy(policy.issuer_id), policy)

    def test_unknown_issuer_returns_none_and_blank_id_is_rejected(self):
        self.assertIsNone(self.repository.get_policy("unknown"))
        with self.assertRaises(ContractError):
            self.repository.get_policy(" ")

    def test_create_requires_first_revision_and_rejects_duplicate(self):
        with self.assertRaises(ContractError):
            self.repository.create(make_policy(policy_revision=2))
        policy = make_policy()
        self.repository.create(policy)
        with self.assertRaises(ContractError):
            self.repository.create(policy)

    def test_append_creates_next_revision_and_preserves_history(self):
        first = make_policy()
        self.repository.create(first)
        second = replace(first, policy_revision=2, enabled=False)
        self.repository.append(second, expected_revision=1)
        self.assertEqual(self.repository.get_policy(first.issuer_id), second)
        self.assertEqual(self.repository.list_history(first.issuer_id), (first, second))

    def test_append_rejects_stale_revision_without_overwriting(self):
        first = make_policy()
        self.repository.create(first)
        second = replace(first, policy_revision=2, enabled=False)
        self.repository.append(second, expected_revision=1)
        stale = replace(first, policy_revision=2, max_evidence_lifetime_seconds=300)
        with self.assertRaises(ConcurrencyError):
            self.repository.append(stale, expected_revision=1)
        self.assertEqual(self.repository.get_policy(first.issuer_id), second)
        self.assertEqual(len(self.repository.list_history(first.issuer_id)), 2)

    def test_append_requires_exact_next_revision(self):
        self.repository.create(make_policy())
        with self.assertRaises(ContractError):
            self.repository.append(
                make_policy(policy_revision=3),
                expected_revision=1,
            )

    def test_append_to_unknown_issuer_raises_not_found(self):
        with self.assertRaises(NotFoundError):
            self.repository.append(
                make_policy(policy_revision=2),
                expected_revision=1,
            )

    def test_history_is_scoped_and_sorted_by_revision(self):
        first = make_policy()
        self.repository.create(first)
        second = replace(first, policy_revision=2, enabled=False)
        self.repository.append(second, expected_revision=1)
        other = make_policy(issuer_id="other-source")
        self.repository.create(other)
        self.assertEqual(self.repository.list_history(first.issuer_id), (first, second))
        self.assertEqual(self.repository.list_history(other.issuer_id), (other,))

    def test_database_rejects_update_and_delete_of_policy_history(self):
        policy = make_policy()
        self.repository.create(policy)
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    UPDATE recovery_evidence_issuer_trust_policies
                    SET enabled = 0 WHERE issuer_id = ?
                    """,
                    (policy.issuer_id,),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM recovery_evidence_issuer_trust_policies WHERE issuer_id = ?",
                    (policy.issuer_id,),
                )
        self.assertEqual(self.repository.get_policy(policy.issuer_id), policy)

    def test_database_rejects_revision_skip(self):
        policy = make_policy()
        self.repository.create(policy)
        with self.assertRaises(sqlite3.IntegrityError):
            with self.database.connection() as connection:
                connection.execute(
                    """
                    INSERT INTO recovery_evidence_issuer_trust_policies (
                        issuer_id, policy_revision, enabled,
                        allowed_evidence_kinds_json, valid_from, valid_until,
                        max_evidence_lifetime_seconds
                    ) VALUES (?, 3, 1, '["source_outcome_receipt"]', ?, ?, 600)
                    """,
                    (
                        policy.issuer_id,
                        policy.valid_from.isoformat(),
                        policy.valid_until.isoformat(),
                    ),
                )

    def test_shared_unit_of_work_commits_and_rolls_back_policy_changes(self):
        factory = SQLiteLocalAuthorityUnitOfWorkFactory(self.database)
        policy = make_policy()
        with factory() as unit:
            unit.recovery_evidence_trust_policies.create(policy)
        self.assertIsNone(self.repository.get_policy(policy.issuer_id))

        with factory() as unit:
            unit.recovery_evidence_trust_policies.create(policy)
            unit.commit()
        self.assertEqual(self.repository.get_policy(policy.issuer_id), policy)

    def test_repository_rejects_foreign_or_inactive_unit_of_work(self):
        other = SQLiteDatabase(Path(self.temp_dir.name) / "other.sqlite")
        other.apply_migrations(SQLITE_MIGRATIONS)
        with other.unit_of_work() as unit:
            foreign = SQLiteRecoveryEvidenceIssuerTrustPolicyRepository(
                self.database,
                unit_of_work=unit,
            )
            with self.assertRaises(ContractError):
                foreign.get_policy("trusted-source-1")


if __name__ == "__main__":
    unittest.main()
