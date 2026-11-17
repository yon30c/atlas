"""SQLite integration tests for atomic recovery evidence admission."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from threading import Barrier

from atlas.adapters.sqlite import SQLiteDatabase, SQLITE_MIGRATIONS
from atlas.adapters.sqlite.local_authority_unit_of_work import SQLiteLocalAuthorityUnitOfWork
from atlas.application.recovery_admission import RecoveryEvidenceAdmissionCommand
from atlas.application.recovery_evidence import (
    RecoveryEvidenceVerification,
    RecoveryEvidenceVerificationStatus,
    recovery_evidence_digest,
)
from atlas.authorization.recovery_evidence_issuer_registry import (
    RecoveryEvidenceIssuerRegistration,
)
from atlas.memory.authority_changes import (
    AuthorityChangeTarget,
    AuthorityChangeTargetKind,
    AuthorityChangeStatus,
    MultiAuthorityChangeIntent,
    MultiAuthorityRecoveryEvidenceKind,
    MultiAuthorityRecoveryEvidence,
    AuthorityChangeTerminalTarget,
)
from atlas.ports.recovery_evidence_admission import RecoveryEvidenceAdmissionStatus


NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


class SQLiteRecoveryEvidenceAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "atlas.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)

    @staticmethod
    def targets():
        return (
            AuthorityChangeTarget(AuthorityChangeTargetKind.GRANT, "grant-1", 4, 5),
            AuthorityChangeTarget(
                AuthorityChangeTargetKind.GRANT_RENEWAL, "renewal-1", 2, 3
            ),
        )

    def _prepare(self, *, enabled=True, revision=1):
        with SQLiteLocalAuthorityUnitOfWork(self.database) as uow:
            uow.recovery_evidence_issuer_registry.create(
                RecoveryEvidenceIssuerRegistration(
                    "issuer-1", 1, enabled, NOW
                )
            )
            for next_revision in range(2, revision + 1):
                uow.recovery_evidence_issuer_registry.append(
                    RecoveryEvidenceIssuerRegistration(
                        "issuer-1", next_revision, enabled, NOW
                    ),
                    expected_revision=next_revision - 1,
                )
            reservation = uow.authority_changes.reserve_multi_change(
                MultiAuthorityChangeIntent(
                    idempotency_key="idem-1",
                    consumer_id="recovery-test",
                    action="recover.multi",
                    actor_identity_id="actor-1",
                    owner_id="owner-1",
                    project_id="project-1",
                    environment_id="environment-1",
                    targets=self.targets(),
                    request_context_ref="test://recovery",
                    requested_at=NOW,
                )
            )
            self.assertIsNotNone(reservation)
            operation_id = reservation.operation_id
            self.assertTrue(uow.authority_changes.acquire_multi_claims(operation_id))
            self.assertTrue(uow.authority_changes.transition_multi_status(
                operation_id,
                AuthorityChangeStatus.REQUESTED,
                AuthorityChangeStatus.INVALIDATION_PENDING,
            ))
            uow.commit()
        return operation_id

    def _command(self, operation_id, **overrides):
        targets = overrides.pop("targets", self.targets())
        evidence_id = overrides.pop("evidence_id", "evidence-1")
        admission_id = overrides.pop("admission_id", "admission-1")
        issuer_revision = overrides.pop("issuer_registry_revision", 1)
        evidence_kind = MultiAuthorityRecoveryEvidenceKind.SOURCE_OUTCOME_RECEIPT
        evidence = MultiAuthorityRecoveryEvidence(
            evidence_id=evidence_id,
            operation_id=operation_id,
            evidence_kind=evidence_kind,
            issuer_id="issuer-1",
            issued_at=NOW,
            expires_at=datetime(2026, 11, 16, 13, 0, tzinfo=timezone.utc),
            payload_digest="a" * 64,
            attestation_ref="attestation://test",
            targets=tuple(
                AuthorityChangeTerminalTarget(
                    target.authority_kind,
                    target.authority_id,
                    target.expected_revision,
                    target.proposed_revision,
                    target.proposed_revision,
                )
                for target in targets
            ),
        )
        verification = RecoveryEvidenceVerification(
            RecoveryEvidenceVerificationStatus.VERIFIED,
            evidence_id,
            issuer_revision,
            recovery_evidence_digest(evidence),
        )
        return RecoveryEvidenceAdmissionCommand.from_verified_evidence(
            admission_id=admission_id,
            evidence=evidence,
            verification=verification,
            operation_id=operation_id,
            evidence_kind=evidence_kind,
            targets=targets,
            requested_at=NOW,
        )

    def test_admits_and_persists_exact_command_and_replays_idempotently(self):
        operation_id = self._prepare()
        command = self._command(operation_id)
        with SQLiteLocalAuthorityUnitOfWork(self.database) as uow:
            first = uow.recovery_evidence_admissions.admit(command)
            second = uow.recovery_evidence_admissions.admit(command)
            self.assertEqual(first.status, RecoveryEvidenceAdmissionStatus.ADMITTED)
            self.assertEqual(second.status, RecoveryEvidenceAdmissionStatus.REPLAYED)
            self.assertFalse(first.effect_permitted)
            uow.commit()
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT admission_id, evidence_id, evidence_digest, operation_id, issuer_registry_revision "
                "FROM recovery_evidence_admissions"
            ).fetchone()
        self.assertEqual(
            tuple(row),
            (
                "admission-1", "evidence-1", command.evidence_digest,
                operation_id, 1,
            ),
        )

    def test_rejects_stale_issuer_revision(self):
        operation_id = self._prepare(revision=2)
        with SQLiteLocalAuthorityUnitOfWork(self.database) as uow:
            result = uow.recovery_evidence_admissions.admit(
                self._command(operation_id, issuer_registry_revision=1)
            )
        self.assertEqual(result.status, RecoveryEvidenceAdmissionStatus.STALE_ISSUER)

    def test_rejects_disabled_issuer(self):
        operation_id = self._prepare(enabled=False)
        with SQLiteLocalAuthorityUnitOfWork(self.database) as uow:
            result = uow.recovery_evidence_admissions.admit(
                self._command(operation_id)
            )
        self.assertEqual(result.status, RecoveryEvidenceAdmissionStatus.ISSUER_DISABLED)

    def test_rejects_target_or_operation_state_mismatch(self):
        operation_id = self._prepare()
        changed = (
            AuthorityChangeTarget(AuthorityChangeTargetKind.GRANT, "grant-1", 5, 6),
            self.targets()[1],
        )
        with SQLiteLocalAuthorityUnitOfWork(self.database) as uow:
            result = uow.recovery_evidence_admissions.admit(
                self._command(operation_id, targets=changed)
            )
        self.assertEqual(result.status, RecoveryEvidenceAdmissionStatus.OPERATION_MISMATCH)

    def test_rejects_reuse_of_evidence_with_another_admission_id(self):
        operation_id = self._prepare()
        with SQLiteLocalAuthorityUnitOfWork(self.database) as uow:
            first = uow.recovery_evidence_admissions.admit(
                self._command(operation_id)
            )
            replay_as_new = uow.recovery_evidence_admissions.admit(
                self._command(operation_id, admission_id="admission-2")
            )
        self.assertEqual(first.status, RecoveryEvidenceAdmissionStatus.ADMITTED)
        self.assertEqual(
            replay_as_new.status, RecoveryEvidenceAdmissionStatus.EVIDENCE_REUSED
        )

    def test_audits_persisted_admission_as_healthy(self):
        operation_id = self._prepare()
        command = self._command(operation_id)
        with SQLiteLocalAuthorityUnitOfWork(self.database) as uow:
            result = uow.recovery_evidence_admissions.admit(command)
            self.assertEqual(result.status, RecoveryEvidenceAdmissionStatus.ADMITTED)
            uow.commit()
        with SQLiteLocalAuthorityUnitOfWork(self.database) as uow:
            audit = uow.recovery_evidence_admissions.audit_admission("admission-1")
            report = uow.recovery_evidence_admissions.audit_all()
            self.assertEqual(audit.status.value, "HEALTHY")
            self.assertEqual(audit.diagnostic_codes, ())
            self.assertEqual(report.healthy_count, 1)
            self.assertEqual(report.corrupt_count, 0)
            self.assertTrue(report.is_healthy)
            self.assertEqual(report.global_diagnostic_codes, ())
            self.assertIsNone(
                uow.recovery_evidence_admissions.audit_admission("missing")
            )

    def test_global_audit_detects_operation_claim_set_corruption(self):
        operation_id = self._prepare()
        command = self._command(operation_id)
        with SQLiteLocalAuthorityUnitOfWork(self.database) as uow:
            uow.recovery_evidence_admissions.admit(command)
            uow.commit()

        with SQLiteLocalAuthorityUnitOfWork(self.database) as uow:
            connection = uow._unit._connection_for(self.database)
            connection.execute("DROP TRIGGER multi_authority_change_claims_no_delete")
            deleted = connection.execute(
                """
                DELETE FROM multi_authority_change_claims
                WHERE operation_id = ?
                  AND authority_id = 'grant-1'
                """,
                (operation_id,),
            )
            self.assertEqual(deleted.rowcount, 1)
            report = uow.recovery_evidence_admissions.audit_all()
            self.assertEqual(report.healthy_count, 0)
            self.assertEqual(report.corrupt_count, 1)
            self.assertFalse(report.is_healthy)
            self.assertIn(
                "OPERATION_CLAIMS_MISMATCH",
                report.global_diagnostic_codes,
            )
            self.assertIn(
                "OPERATION_CLAIMS_MISMATCH",
                report.admissions[0].diagnostic_codes,
            )

    def test_audit_detects_command_digest_corruption_without_mutating_receipt(self):
        operation_id = self._prepare()
        command = self._command(operation_id)
        with SQLiteLocalAuthorityUnitOfWork(self.database) as uow:
            uow.recovery_evidence_admissions.admit(command)
            uow.commit()
        with SQLiteLocalAuthorityUnitOfWork(self.database) as uow:
            connection = uow._unit._connection_for(self.database)
            connection.execute("DROP TRIGGER recovery_evidence_admissions_no_update")
            connection.execute(
                "UPDATE recovery_evidence_admissions SET command_digest = ? "
                "WHERE admission_id = ?",
                ("0" * 64, "admission-1"),
            )
            audit = uow.recovery_evidence_admissions.audit_admission("admission-1")
            report = uow.recovery_evidence_admissions.audit_all()
            self.assertEqual(audit.status.value, "CORRUPT")
            self.assertIn("COMMAND_DIGEST_MISMATCH", audit.diagnostic_codes)
            self.assertEqual(report.healthy_count, 0)
            self.assertEqual(report.corrupt_count, 1)




    def test_audit_detects_unknown_persisted_evidence_kind(self):
        operation_id = self._prepare()
        command = self._command(operation_id)
        with SQLiteLocalAuthorityUnitOfWork(self.database) as uow:
            uow.recovery_evidence_admissions.admit(command)
            uow.commit()

        with SQLiteLocalAuthorityUnitOfWork(self.database) as uow:
            connection = uow._unit._connection_for(self.database)
            connection.execute("DROP TRIGGER recovery_evidence_admissions_no_update")
            connection.execute("PRAGMA ignore_check_constraints = ON")
            row = connection.execute(
                "SELECT command_canonical FROM recovery_evidence_admissions "
                "WHERE admission_id = ?",
                ("admission-1",),
            ).fetchone()
            payload = json.loads(bytes(row["command_canonical"]).decode("utf-8"))
            payload["evidence_kind"] = "UNKNOWN_EVIDENCE_KIND"
            canonical = json.dumps(
                payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            connection.execute(
                """
                UPDATE recovery_evidence_admissions
                SET evidence_kind = ?, command_canonical = ?, command_digest = ?
                WHERE admission_id = ?
                """,
                (
                    "UNKNOWN_EVIDENCE_KIND",
                    sqlite3.Binary(canonical),
                    hashlib.sha256(canonical).hexdigest(),
                    "admission-1",
                ),
            )
            audit = uow.recovery_evidence_admissions.audit_admission("admission-1")
            report = uow.recovery_evidence_admissions.audit_all()

        self.assertEqual(audit.status.value, "CORRUPT")
        self.assertIn("INVALID_EVIDENCE_KIND", audit.diagnostic_codes)
        self.assertIn("INVALID_EVIDENCE_KIND", report.global_diagnostic_codes)
        self.assertFalse(report.is_healthy)

    def test_audit_detects_unknown_authority_kind_even_when_records_match(self):
        operation_id = self._prepare()
        command = self._command(operation_id)
        with SQLiteLocalAuthorityUnitOfWork(self.database) as uow:
            uow.recovery_evidence_admissions.admit(command)
            uow.commit()

        with SQLiteLocalAuthorityUnitOfWork(self.database) as uow:
            connection = uow._unit._connection_for(self.database)
            for table in (
                "recovery_evidence_admissions",
                "multi_authority_change_targets",
                "multi_authority_change_claims",
            ):
                triggers = connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'trigger' AND tbl_name = ?",
                    (table,),
                ).fetchall()
                for trigger in triggers:
                    connection.execute(
                        'DROP TRIGGER "' + trigger["name"].replace('"', '""') + '"'
                    )
            connection.execute("PRAGMA ignore_check_constraints = ON")
            row = connection.execute(
                "SELECT command_canonical FROM recovery_evidence_admissions "
                "WHERE admission_id = ?",
                ("admission-1",),
            ).fetchone()
            payload = json.loads(bytes(row["command_canonical"]).decode("utf-8"))
            payload["targets"][0]["authority_kind"] = "unknown_authority_kind"
            canonical = json.dumps(
                payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            connection.execute(
                """
                UPDATE multi_authority_change_targets
                SET authority_kind = ?
                WHERE operation_id = ? AND authority_id = ?
                """,
                ("unknown_authority_kind", operation_id, "grant-1"),
            )
            connection.execute(
                """
                UPDATE multi_authority_change_claims
                SET authority_kind = ?
                WHERE operation_id = ? AND authority_id = ?
                """,
                ("unknown_authority_kind", operation_id, "grant-1"),
            )
            connection.execute(
                """
                UPDATE recovery_evidence_admissions
                SET command_canonical = ?, command_digest = ?
                WHERE admission_id = ?
                """,
                (
                    sqlite3.Binary(canonical),
                    hashlib.sha256(canonical).hexdigest(),
                    "admission-1",
                ),
            )
            audit = uow.recovery_evidence_admissions.audit_admission("admission-1")
            report = uow.recovery_evidence_admissions.audit_all()

        self.assertEqual(audit.status.value, "CORRUPT")
        self.assertIn("INVALID_AUTHORITY_KIND", audit.diagnostic_codes)
        self.assertIn("INVALID_AUTHORITY_KIND", report.global_diagnostic_codes)
        self.assertFalse(report.is_healthy)

    def test_audit_accepts_issuer_change_effective_after_admission(self):
        operation_id = self._prepare()
        command = self._command(operation_id)
        with SQLiteLocalAuthorityUnitOfWork(self.database) as uow:
            uow.recovery_evidence_admissions.admit(command)
            uow.commit()
        with self.database.connection() as connection:
            recorded_at = datetime.fromisoformat(
                connection.execute(
                    "SELECT recorded_at FROM recovery_evidence_admissions "
                    "WHERE admission_id = ?",
                    ("admission-1",),
                ).fetchone()["recorded_at"]
            )
        with SQLiteLocalAuthorityUnitOfWork(self.database) as uow:
            uow.recovery_evidence_issuer_registry.append(
                RecoveryEvidenceIssuerRegistration(
                    "issuer-1", 2, False, recorded_at + timedelta(seconds=1)
                ),
                expected_revision=1,
            )
            uow.commit()
        with SQLiteLocalAuthorityUnitOfWork(self.database) as uow:
            audit = uow.recovery_evidence_admissions.audit_admission("admission-1")
        self.assertEqual(audit.status.value, "HEALTHY")
        self.assertEqual(audit.diagnostic_codes, ())

    def test_audit_detects_issuer_revision_backdated_before_admission(self):
        operation_id = self._prepare()
        command = self._command(operation_id)
        with SQLiteLocalAuthorityUnitOfWork(self.database) as uow:
            uow.recovery_evidence_admissions.admit(command)
            uow.commit()
        with self.database.connection() as connection:
            recorded_at = datetime.fromisoformat(
                connection.execute(
                    "SELECT recorded_at FROM recovery_evidence_admissions "
                    "WHERE admission_id = ?",
                    ("admission-1",),
                ).fetchone()["recorded_at"]
            )
        with SQLiteLocalAuthorityUnitOfWork(self.database) as uow:
            uow.recovery_evidence_issuer_registry.append(
                RecoveryEvidenceIssuerRegistration(
                    "issuer-1", 2, False, recorded_at - timedelta(seconds=1)
                ),
                expected_revision=1,
            )
            uow.commit()
        with SQLiteLocalAuthorityUnitOfWork(self.database) as uow:
            audit = uow.recovery_evidence_admissions.audit_admission("admission-1")
        self.assertEqual(audit.status.value, "CORRUPT")
        self.assertIn(
            "ISSUER_REVISION_NOT_LATEST_AT_ADMISSION",
            audit.diagnostic_codes,
        )

    def test_concurrent_admission_and_issuer_disable_are_serialized(self):
        operation_id = self._prepare()
        command = self._command(operation_id)
        admission_database = SQLiteDatabase(self.database.path)
        revocation_database = SQLiteDatabase(self.database.path)
        barrier = Barrier(2)

        def admit():
            barrier.wait()
            with SQLiteLocalAuthorityUnitOfWork(admission_database) as uow:
                result = uow.recovery_evidence_admissions.admit(command)
                uow.commit()
                return result.status

        def disable_issuer():
            barrier.wait()
            with SQLiteLocalAuthorityUnitOfWork(revocation_database) as uow:
                uow.recovery_evidence_issuer_registry.append(
                    RecoveryEvidenceIssuerRegistration(
                        "issuer-1", 2, False, NOW
                    ),
                    expected_revision=1,
                )
                uow.commit()

        with ThreadPoolExecutor(max_workers=2) as executor:
            admission_future = executor.submit(admit)
            revocation_future = executor.submit(disable_issuer)
            admission_status = admission_future.result(timeout=10)
            revocation_future.result(timeout=10)

        current = SQLiteLocalAuthorityUnitOfWork(admission_database)
        with current as uow:
            registration = uow.recovery_evidence_issuer_registry.get_registration(
                "issuer-1"
            )
            self.assertEqual(registration.registry_revision, 2)
            self.assertFalse(registration.enabled)
        with admission_database.connection() as connection:
            row = connection.execute(
                "SELECT issuer_registry_revision FROM recovery_evidence_admissions "
                "WHERE admission_id = ?",
                ("admission-1",),
            ).fetchone()

        if admission_status == RecoveryEvidenceAdmissionStatus.ADMITTED:
            self.assertIsNotNone(row)
            self.assertEqual(row["issuer_registry_revision"], 1)
        else:
            self.assertEqual(
                admission_status, RecoveryEvidenceAdmissionStatus.STALE_ISSUER
            )
            self.assertIsNone(row)

    def test_concurrent_exact_admissions_are_admitted_once_and_replayed(self):
        operation_id = self._prepare()
        command = self._command(operation_id)
        databases = (
            SQLiteDatabase(self.database.path),
            SQLiteDatabase(self.database.path),
        )
        barrier = Barrier(2)

        def admit(database):
            barrier.wait()
            with SQLiteLocalAuthorityUnitOfWork(database) as uow:
                result = uow.recovery_evidence_admissions.admit(command)
                uow.commit()
                return result.status

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(admit, database) for database in databases]
            statuses = [future.result(timeout=10) for future in futures]

        self.assertCountEqual(
            statuses,
            [
                RecoveryEvidenceAdmissionStatus.ADMITTED,
                RecoveryEvidenceAdmissionStatus.REPLAYED,
            ],
        )
        with self.database.connection() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM recovery_evidence_admissions "
                "WHERE evidence_id = ?",
                ("evidence-1",),
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_schema_rejects_non_current_issuer_revision(self):
        operation_id = self._prepare(revision=2)
        with self.assertRaises(sqlite3.IntegrityError):
            with SQLiteLocalAuthorityUnitOfWork(self.database) as uow:
                uow._unit._connection_for(self.database).execute(
                    """
                    INSERT INTO recovery_evidence_admissions (
                        admission_id, evidence_id, evidence_digest, operation_id, issuer_id,
                        issuer_registry_revision, evidence_kind, target_count,
                        command_digest, command_canonical, requested_at, recorded_at
                    ) VALUES ('raw-admission', 'raw-evidence', ?, ?, 'issuer-1', 1,
                              'SOURCE_OUTCOME_RECEIPT', 2, ?, X'7B7D', ?, ?)
                    """,
                    ("b" * 64, operation_id, "a" * 64, NOW.isoformat(), NOW.isoformat()),
                )


if __name__ == "__main__":
    unittest.main()
