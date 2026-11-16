"""SQLite integration tests for atomic recovery evidence admission."""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

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
            self.assertIsNone(
                uow.recovery_evidence_admissions.audit_admission("missing")
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
