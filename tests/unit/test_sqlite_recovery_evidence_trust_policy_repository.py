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
from atlas.authorization.recovery_evidence_trust_audit import (
    RecoveryEvidenceIssuerTrustPolicyAuditStatus,
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
                    ) VALUES (?, 3, 1, '["SOURCE_OUTCOME_RECEIPT"]', ?, ?, 600)
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


    def test_audit_reports_healthy_and_disabled_issuers_without_mutating_rows(self):
        healthy = make_policy(issuer_id="healthy-source")
        disabled = make_policy(issuer_id="disabled-source", enabled=False)
        self.repository.create(healthy)
        self.repository.create(disabled)
        with self.database.connection() as connection:
            before = connection.execute(
                "SELECT COUNT(*) FROM recovery_evidence_issuer_trust_policies"
            ).fetchone()[0]

        report = self.repository.audit_all()

        with self.database.connection() as connection:
            after = connection.execute(
                "SELECT COUNT(*) FROM recovery_evidence_issuer_trust_policies"
            ).fetchone()[0]
        self.assertEqual(before, after)
        self.assertEqual(len(report.issuers), 2)
        by_id = {item.issuer_id: item for item in report.issuers}
        self.assertEqual(
            by_id["healthy-source"].status,
            RecoveryEvidenceIssuerTrustPolicyAuditStatus.HEALTHY,
        )
        self.assertEqual(
            by_id["disabled-source"].status,
            RecoveryEvidenceIssuerTrustPolicyAuditStatus.DISABLED,
        )
        self.assertIn("LATEST_POLICY_DISABLED", by_id["disabled-source"].diagnostic_codes)
        self.assertFalse(report.is_healthy)

    def test_audit_issuer_reports_missing_policy_explicitly(self):
        audit = self.repository.audit_issuer("not-registered")
        self.assertEqual(
            audit.status,
            RecoveryEvidenceIssuerTrustPolicyAuditStatus.MISSING_POLICY,
        )
        self.assertEqual(audit.diagnostic_codes, ("NO_POLICY_REGISTERED",))
        self.assertIsNone(audit.latest_revision)

    def test_audit_detects_revision_gap_if_database_history_is_damaged(self):
        policy = make_policy()
        self.repository.create(policy)
        with self.database.connection() as connection:
            connection.execute(
                "DROP TRIGGER recovery_evidence_trust_policy_revision_sequential"
            )
            connection.execute(
                """
                INSERT INTO recovery_evidence_issuer_trust_policies (
                    issuer_id, policy_revision, enabled,
                    allowed_evidence_kinds_json, valid_from, valid_until,
                    max_evidence_lifetime_seconds
                ) VALUES (?, 3, 1, ?, ?, ?, ?)
                """,
                (
                    policy.issuer_id,
                    self.repository._values(policy)[3],
                    policy.valid_from.isoformat(timespec="microseconds"),
                    policy.valid_until.isoformat(timespec="microseconds"),
                    policy.max_evidence_lifetime_seconds,
                ),
            )
        audit = self.repository.audit_issuer(policy.issuer_id)
        self.assertEqual(
            audit.status,
            RecoveryEvidenceIssuerTrustPolicyAuditStatus.CORRUPT,
        )
        self.assertIn("REVISION_SEQUENCE_GAP", audit.diagnostic_codes)
        self.assertEqual(audit.revisions, (1, 3))

    def test_audit_detects_malformed_policy_payload(self):
        policy = make_policy()
        self.repository.create(policy)
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO recovery_evidence_issuer_trust_policies (
                    issuer_id, policy_revision, enabled,
                    allowed_evidence_kinds_json, valid_from, valid_until,
                    max_evidence_lifetime_seconds
                ) VALUES (?, 2, 1, '["unknown_evidence_kind"]', ?, ?, 600)
                """,
                (
                    policy.issuer_id,
                    policy.valid_from.isoformat(timespec="microseconds"),
                    policy.valid_until.isoformat(timespec="microseconds"),
                ),
            )
        audit = self.repository.audit_issuer(policy.issuer_id)
        self.assertEqual(
            audit.status,
            RecoveryEvidenceIssuerTrustPolicyAuditStatus.CORRUPT,
        )
        self.assertIn("INVALID_POLICY_RECORD", audit.diagnostic_codes)
        self.assertEqual(audit.latest_revision, 2)

    def test_audit_all_is_sorted_by_issuer_id(self):
        self.repository.create(make_policy(issuer_id="z-source"))
        self.repository.create(make_policy(issuer_id="a-source"))
        report = self.repository.audit_all()
        self.assertEqual(
            tuple(item.issuer_id for item in report.issuers),
            ("a-source", "z-source"),
        )
        self.assertTrue(report.is_healthy)

    def test_audit_all_empty_inventory_is_not_reported_healthy(self):
        report = self.repository.audit_all()
        self.assertEqual(report.issuers, ())
        self.assertFalse(report.is_healthy)


if __name__ == "__main__":
    unittest.main()
