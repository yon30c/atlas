"""Contract tests for recovery evidence admission requests."""

from datetime import datetime, timezone
import unittest

from atlas.application.recovery_admission import RecoveryEvidenceAdmissionCommand
from atlas.application.recovery_evidence import (
    RecoveryEvidenceVerification,
    RecoveryEvidenceVerificationStatus,
)
from atlas.core.errors import ContractError
from atlas.memory.authority_changes import (
    AuthorityChangeTarget,
    AuthorityChangeTargetKind,
    MultiAuthorityRecoveryEvidenceKind,
    MultiAuthorityRecoveryEvidence,
    AuthorityChangeTerminalTarget,
)


NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def targets():
    return (
        AuthorityChangeTarget(AuthorityChangeTargetKind.GRANT, "grant-1", 4, 5),
        AuthorityChangeTarget(
            AuthorityChangeTargetKind.GRANT_RENEWAL, "renewal-1", 2, 3
        ),
    )


def evidence():
    return MultiAuthorityRecoveryEvidence(
        evidence_id="evidence-1",
        operation_id="operation-1",
        evidence_kind=MultiAuthorityRecoveryEvidenceKind.SOURCE_OUTCOME_RECEIPT,
        issuer_id="issuer-1",
        issued_at=NOW,
        expires_at=datetime(2026, 11, 16, 13, 0, tzinfo=timezone.utc),
        payload_digest="a" * 64,
        attestation_ref="attestation://one",
        targets=(
            AuthorityChangeTerminalTarget(
                AuthorityChangeTargetKind.GRANT, "grant-1", 4, 5, 5
            ),
            AuthorityChangeTerminalTarget(
                AuthorityChangeTargetKind.GRANT_RENEWAL, "renewal-1", 2, 3, 3
            ),
        ),
    )


def verified():
    return RecoveryEvidenceVerification(
        RecoveryEvidenceVerificationStatus.VERIFIED, "evidence-1", 7
    )


class RecoveryEvidenceAdmissionCommandTests(unittest.TestCase):
    def build(self, **overrides):
        args = dict(
            admission_id="admission-1",
            evidence=evidence(),
            verification=verified(),
            operation_id="operation-1",
            evidence_kind=MultiAuthorityRecoveryEvidenceKind.SOURCE_OUTCOME_RECEIPT,
            targets=targets(),
            requested_at=NOW,
        )
        args.update(overrides)
        return RecoveryEvidenceAdmissionCommand.from_verified_evidence(**args)

    def test_builds_exact_command_from_verified_evidence(self):
        command = self.build()
        self.assertEqual(command.admission_id, "admission-1")
        self.assertEqual(command.operation_id, "operation-1")
        self.assertEqual(command.evidence_id, "evidence-1")
        self.assertEqual(command.issuer_id, "issuer-1")
        self.assertEqual(command.issuer_registry_revision, 7)
        self.assertEqual(command.targets, targets())

    def test_rejects_direct_construction_bypassing_verified_factory(self):
        with self.assertRaises(ContractError):
            RecoveryEvidenceAdmissionCommand(
                "admission-1", "operation-1", "evidence-1", "issuer-1", 7,
                MultiAuthorityRecoveryEvidenceKind.SOURCE_OUTCOME_RECEIPT,
                targets(), NOW,
            )

    def test_rejects_non_verified_result(self):
        with self.assertRaises(ContractError):
            self.build(verification=RecoveryEvidenceVerification(
                RecoveryEvidenceVerificationStatus.DENIED, "evidence-1"
            ))

    def test_rejects_verification_for_different_evidence(self):
        with self.assertRaises(ContractError):
            self.build(verification=RecoveryEvidenceVerification(
                RecoveryEvidenceVerificationStatus.VERIFIED, "other-evidence", 7
            ))

    def test_rejects_operation_or_target_mismatch(self):
        with self.assertRaises(ContractError):
            self.build(operation_id="other-operation")
        changed = (
            AuthorityChangeTarget(AuthorityChangeTargetKind.GRANT, "grant-1", 5, 6),
            targets()[1],
        )
        with self.assertRaises(ContractError):
            self.build(targets=changed)

    def test_rejects_invalid_command_fields_and_time(self):
        with self.assertRaises(ContractError):
            self.build(admission_id=" ")
        with self.assertRaises(ContractError):
            self.build(requested_at=datetime(2026, 11, 16, 12, 0))
        with self.assertRaises(ContractError):
            self.build(verification=RecoveryEvidenceVerification(
                RecoveryEvidenceVerificationStatus.VERIFIED, "evidence-1", 0
            ))

    def test_canonicalizes_target_order(self):
        reversed_targets = tuple(reversed(targets()))
        command = self.build(targets=reversed_targets)
        self.assertEqual(command.targets, targets())


if __name__ == "__main__":
    unittest.main()
