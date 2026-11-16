"""Persistence, concurrency and cross-audit tests for the issuer inventory."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from atlas.adapters.sqlite import (
    SQLiteDatabase,
    SQLiteLocalAuthorityUnitOfWorkFactory,
    SQLiteRecoveryEvidenceIssuerRegistryRepository,
    SQLiteRecoveryEvidenceIssuerTrustPolicyRepository,
    SQLITE_MIGRATIONS,
)
from atlas.authorization.recovery_evidence_issuer_registry import (
    RecoveryEvidenceIssuerRegistration,
)
from atlas.authorization.recovery_evidence_trust import (
    RecoveryEvidenceIssuerTrustPolicy,
)
from atlas.authorization.recovery_evidence_trust_audit import (
    RecoveryEvidenceIssuerInventoryAuditStatus,
)
from atlas.core.errors import ConcurrencyError, ContractError, NotFoundError
from atlas.memory.authority_changes import MultiAuthorityRecoveryEvidenceKind


NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def make_registration(**overrides):
    values = {
        "issuer_id": "source-a",
        "registry_revision": 1,
        "enabled": True,
        "changed_at": NOW,
    }
    values.update(overrides)
    return RecoveryEvidenceIssuerRegistration(**values)


def make_policy(**overrides):
    values = {
        "issuer_id": "source-a",
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


class SQLiteRecoveryEvidenceIssuerRegistryRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "atlas.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.repository = SQLiteRecoveryEvidenceIssuerRegistryRepository(
            self.database
        )
        self.policies = SQLiteRecoveryEvidenceIssuerTrustPolicyRepository(
            self.database
        )

    def test_create_and_get_registration_round_trip(self):
        registration = make_registration()
        self.repository.create(registration)
        self.assertEqual(
            self.repository.get_registration(registration.issuer_id),
            registration,
        )

    def test_duplicate_and_invalid_initial_registration_are_rejected(self):
        with self.assertRaises(ContractError):
            self.repository.create(make_registration(registry_revision=2))
        registration = make_registration()
        self.repository.create(registration)
        with self.assertRaises(ContractError):
            self.repository.create(registration)
        with self.assertRaises(ContractError):
            self.repository.get_registration(" ")

    def test_append_preserves_history_and_current_snapshot(self):
        first = make_registration()
        second = replace(first, registry_revision=2, enabled=False, changed_at=NOW + timedelta(minutes=1))
        self.repository.create(first)
        self.repository.append(second, expected_revision=1)
        self.assertEqual(self.repository.get_registration(first.issuer_id), second)
        self.assertEqual(
            self.repository.list_registrations(),
            (second,),
        )

    def test_append_rejects_stale_revision_and_unknown_issuer(self):
        first = make_registration()
        self.repository.create(first)
        second = replace(first, registry_revision=2, enabled=False)
        self.repository.append(second, expected_revision=1)
        with self.assertRaises(ConcurrencyError):
            self.repository.append(
                replace(first, registry_revision=2, changed_at=NOW + timedelta(minutes=2)),
                expected_revision=1,
            )
        with self.assertRaises(NotFoundError):
            self.repository.append(
                make_registration(issuer_id="missing", registry_revision=2),
                expected_revision=1,
            )
        self.assertEqual(self.repository.get_registration(first.issuer_id), second)

    def test_concurrent_appends_have_one_winner(self):
        first = make_registration()
        self.repository.create(first)
        barrier = threading.Barrier(2)

        def append(enabled):
            candidate = replace(
                first,
                registry_revision=2,
                enabled=enabled,
                changed_at=NOW + timedelta(minutes=1),
            )
            barrier.wait()
            try:
                self.repository.append(candidate, expected_revision=1)
                return "committed"
            except ConcurrencyError:
                return "stale"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = tuple(pool.map(append, (False, True)))
        self.assertCountEqual(outcomes, ("committed", "stale"))
        self.assertEqual(len(self.repository.list_history("source-a")), 2)

    def test_sql_prevents_update_delete_and_revision_skip(self):
        registration = make_registration()
        self.repository.create(registration)
        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE recovery_evidence_issuer_registry SET enabled=0 WHERE issuer_id='source-a'"
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM recovery_evidence_issuer_registry WHERE issuer_id='source-a'"
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO recovery_evidence_issuer_registry
                    (issuer_id, registry_revision, enabled, changed_at)
                    VALUES ('source-a', 3, 1, ?)
                    """,
                    (NOW.isoformat(),),
                )

    def test_shared_unit_of_work_commits_and_rolls_back_registry_and_policy(self):
        factory = SQLiteLocalAuthorityUnitOfWorkFactory(self.database)
        registration = make_registration()
        policy = make_policy()
        with factory() as unit:
            unit.recovery_evidence_issuer_registry.create(registration)
            unit.recovery_evidence_trust_policies.create(policy)
        self.assertIsNone(self.repository.get_registration("source-a"))
        self.assertIsNone(self.policies.get_policy("source-a"))

        with factory() as unit:
            unit.recovery_evidence_issuer_registry.create(registration)
            unit.recovery_evidence_trust_policies.create(policy)
            unit.commit()
        self.assertEqual(self.repository.get_registration("source-a"), registration)
        self.assertEqual(self.policies.get_policy("source-a"), policy)

    def test_repository_rejects_foreign_unit_of_work(self):
        other = SQLiteDatabase(Path(self.temp_dir.name) / "other.sqlite")
        other.apply_migrations(SQLITE_MIGRATIONS)
        with other.unit_of_work() as unit:
            foreign = SQLiteRecoveryEvidenceIssuerRegistryRepository(
                self.database,
                unit_of_work=unit,
            )
            with self.assertRaises(ContractError):
                foreign.list_registrations()

    def test_list_registrations_returns_latest_revision_sorted_by_id(self):
        for issuer in ("z-source", "a-source"):
            first = make_registration(issuer_id=issuer)
            self.repository.create(first)
            self.repository.append(
                replace(first, registry_revision=2, changed_at=NOW + timedelta(minutes=1)),
                expected_revision=1,
            )
        self.assertEqual(
            tuple(item.issuer_id for item in self.repository.list_registrations()),
            ("a-source", "z-source"),
        )
        self.assertTrue(
            all(item.registry_revision == 2 for item in self.repository.list_registrations())
        )

    def test_cross_audit_reports_missing_disabled_orphan_and_healthy(self):
        self.repository.create(make_registration(issuer_id="healthy"))
        self.policies.create(make_policy(issuer_id="healthy"))

        self.repository.create(make_registration(issuer_id="registry-disabled", enabled=False))
        self.policies.create(make_policy(issuer_id="registry-disabled"))

        self.repository.create(make_registration(issuer_id="policy-missing"))

        self.repository.create(make_registration(issuer_id="policy-disabled"))
        self.policies.create(make_policy(issuer_id="policy-disabled", enabled=False))

        self.policies.create(make_policy(issuer_id="orphan-policy"))

        report = self.repository.audit_inventory()
        by_id = {item.issuer_id: item for item in report.issuers}
        self.assertEqual(by_id["healthy"].status, RecoveryEvidenceIssuerInventoryAuditStatus.HEALTHY)
        self.assertEqual(
            by_id["registry-disabled"].status,
            RecoveryEvidenceIssuerInventoryAuditStatus.REGISTRY_DISABLED,
        )
        self.assertEqual(
            by_id["policy-missing"].status,
            RecoveryEvidenceIssuerInventoryAuditStatus.POLICY_MISSING,
        )
        self.assertEqual(
            by_id["policy-disabled"].status,
            RecoveryEvidenceIssuerInventoryAuditStatus.POLICY_DISABLED,
        )
        self.assertEqual(
            by_id["orphan-policy"].status,
            RecoveryEvidenceIssuerInventoryAuditStatus.POLICY_ORPHAN,
        )
        self.assertEqual(report.orphan_policy_issuer_ids, ("orphan-policy",))
        self.assertFalse(report.is_healthy)

    def test_cross_audit_detects_registry_revision_gap(self):
        first = make_registration()
        self.repository.create(first)
        with self.database.connection() as connection:
            connection.execute(
                "DROP TRIGGER recovery_evidence_issuer_registry_revision_sequential"
            )
            connection.execute(
                """
                INSERT INTO recovery_evidence_issuer_registry
                (issuer_id, registry_revision, enabled, changed_at)
                VALUES ('source-a', 3, 1, ?)
                """,
                ((NOW + timedelta(minutes=2)).isoformat(timespec="microseconds"),),
            )
        audit = self.repository.audit_inventory().issuers[0]
        self.assertEqual(
            audit.status,
            RecoveryEvidenceIssuerInventoryAuditStatus.REGISTRY_CORRUPT,
        )
        self.assertIn("REGISTRY_REVISION_SEQUENCE_GAP", audit.diagnostic_codes)

    def test_cross_audit_is_read_only(self):
        self.repository.create(make_registration())
        self.policies.create(make_policy())
        with self.database.connection() as connection:
            before_registry = connection.execute(
                "SELECT COUNT(*) FROM recovery_evidence_issuer_registry"
            ).fetchone()[0]
            before_policies = connection.execute(
                "SELECT COUNT(*) FROM recovery_evidence_issuer_trust_policies"
            ).fetchone()[0]
        self.repository.audit_inventory()
        with self.database.connection() as connection:
            after_registry = connection.execute(
                "SELECT COUNT(*) FROM recovery_evidence_issuer_registry"
            ).fetchone()[0]
            after_policies = connection.execute(
                "SELECT COUNT(*) FROM recovery_evidence_issuer_trust_policies"
            ).fetchone()[0]
        self.assertEqual((before_registry, before_policies), (after_registry, after_policies))


if __name__ == "__main__":
    unittest.main()
