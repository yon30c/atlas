"""Tests for independently verified multi-authority recovery evidence."""

from datetime import datetime, timedelta, timezone
import unittest

from atlas.core.errors import ContractError
from atlas.application.recovery_evidence import (
    MultiAuthorityRecoveryEvidenceVerificationService,
    RecoveryEvidenceVerificationStatus,
)
from atlas.authorization.recovery_evidence_trust import (
    RecoveryEvidenceIssuerTrustPolicy,
)
from atlas.authorization.recovery_evidence_issuer_registry import (
    RecoveryEvidenceIssuerRegistration,
)
from atlas.memory.authority_changes import (
    AuthorityChangeTarget,
    AuthorityChangeTargetKind,
    AuthorityChangeTerminalTarget,
    MultiAuthorityRecoveryEvidence,
    MultiAuthorityRecoveryEvidenceKind,
)


NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def expected_targets():
    return (
        AuthorityChangeTarget(
            AuthorityChangeTargetKind.GRANT, "grant-1", 4, 5
        ),
        AuthorityChangeTarget(
            AuthorityChangeTargetKind.GRANT_RENEWAL, "renewal-1", 2, 3
        ),
    )


def evidence_targets():
    return (
        AuthorityChangeTerminalTarget(
            AuthorityChangeTargetKind.GRANT, "grant-1", 4, 5, 5
        ),
        AuthorityChangeTerminalTarget(
            AuthorityChangeTargetKind.GRANT_RENEWAL, "renewal-1", 2, 3, 3
        ),
    )


def make_evidence(**overrides):
    values = {
        "evidence_id": "evidence-1",
        "operation_id": "operation-1",
        "evidence_kind": MultiAuthorityRecoveryEvidenceKind.SOURCE_OUTCOME_RECEIPT,
        "issuer_id": "trusted-source-1",
        "issued_at": NOW - timedelta(minutes=1),
        "expires_at": NOW + timedelta(minutes=5),
        "payload_digest": "a" * 64,
        "attestation_ref": "attestation://receipt/1",
        "targets": evidence_targets(),
    }
    values.update(overrides)
    return MultiAuthorityRecoveryEvidence(**values)


class FakeIssuerRegistryPort:
    def __init__(self, registration="default", error=None):
        self.registration = (
            RecoveryEvidenceIssuerRegistration(
                issuer_id="trusted-source-1",
                registry_revision=1,
                enabled=True,
                changed_at=NOW - timedelta(days=2),
            )
            if registration == "default"
            else registration
        )
        self.error = error
        self.calls = 0

    def get_registration(self, issuer_id):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.registration


class FakeTrustPolicyPort:
    def __init__(self, policy=None, error=None):
        self.policy = policy or RecoveryEvidenceIssuerTrustPolicy(
            issuer_id="trusted-source-1",
            policy_revision=1,
            enabled=True,
            allowed_evidence_kinds=(
                MultiAuthorityRecoveryEvidenceKind.SOURCE_OUTCOME_RECEIPT,
            ),
            valid_from=NOW - timedelta(days=1),
            valid_until=NOW + timedelta(days=1),
            max_evidence_lifetime_seconds=600,
        )
        self.error = error
        self.calls = 0

    def get_policy(self, issuer_id):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.policy


class FakeVerifier:
    def __init__(self, result=True, error=None, on_verify=None):
        self.result = result
        self.error = error
        self.on_verify = on_verify
        self.calls = 0

    def verify(self, evidence, now):
        self.calls += 1
        if self.error is not None:
            raise self.error
        if self.on_verify is not None:
            self.on_verify()
        return self.result


class MultiAuthorityRecoveryEvidenceContractTests(unittest.TestCase):
    def test_evidence_is_bound_to_exact_operation_kind_and_all_targets(self):
        evidence = make_evidence()
        self.assertTrue(
            evidence.matches(
                "operation-1",
                MultiAuthorityRecoveryEvidenceKind.SOURCE_OUTCOME_RECEIPT,
                expected_targets(),
            )
        )
        self.assertFalse(
            evidence.matches(
                "another-operation",
                MultiAuthorityRecoveryEvidenceKind.SOURCE_OUTCOME_RECEIPT,
                expected_targets(),
            )
        )
        self.assertFalse(
            evidence.matches(
                "operation-1",
                MultiAuthorityRecoveryEvidenceKind.INVALIDATION_RECEIPT,
                expected_targets(),
            )
        )
        changed = (
            AuthorityChangeTarget(
                AuthorityChangeTargetKind.GRANT, "grant-1", 4, 5
            ),
            AuthorityChangeTarget(
                AuthorityChangeTargetKind.GRANT_RENEWAL, "renewal-1", 3, 4
            ),
        )
        self.assertFalse(
            evidence.matches(
                "operation-1",
                MultiAuthorityRecoveryEvidenceKind.SOURCE_OUTCOME_RECEIPT,
                changed,
            )
        )

    def test_evidence_canonicalizes_target_order(self):
        targets = tuple(reversed(evidence_targets()))
        evidence = make_evidence(targets=targets)
        self.assertEqual(
            tuple((item.authority_kind.value, item.authority_id) for item in evidence.targets),
            (("grant", "grant-1"), ("grant_renewal", "renewal-1")),
        )

    def test_evidence_rejects_invalid_digest_and_duplicate_targets(self):
        with self.assertRaises(ContractError):
            make_evidence(payload_digest="A" * 64)
        duplicate = (
            evidence_targets()[0],
            evidence_targets()[0],
        )
        with self.assertRaises(ContractError):
            make_evidence(targets=duplicate)

    def test_evidence_rejects_non_utc_or_invalid_validity_window(self):
        with self.assertRaises(ContractError):
            make_evidence(issued_at=NOW.replace(tzinfo=timezone(timedelta(hours=1))))
        with self.assertRaises(ContractError):
            make_evidence(expires_at=NOW - timedelta(minutes=2))


class MultiAuthorityRecoveryEvidenceVerificationTests(unittest.TestCase):
    def service(
        self,
        verifier,
        trust_policy_port=None,
        issuer_registry_port=None,
    ):
        return MultiAuthorityRecoveryEvidenceVerificationService(
            verifier,
            trust_policy_port or FakeTrustPolicyPort(),
            issuer_registry_port or FakeIssuerRegistryPort(),
        )

    def verify(self, service, evidence=None, **overrides):
        args = {
            "operation_id": "operation-1",
            "evidence_kind": MultiAuthorityRecoveryEvidenceKind.SOURCE_OUTCOME_RECEIPT,
            "targets": expected_targets(),
            "now": NOW,
        }
        args.update(overrides)
        return service.verify(evidence or make_evidence(), **args)

    def test_trusted_verifier_true_returns_verified_but_not_authority(self):
        verifier = FakeVerifier(result=True)
        result = self.verify(self.service(verifier))
        self.assertEqual(result.status, RecoveryEvidenceVerificationStatus.VERIFIED)
        self.assertEqual(result.evidence_id, "evidence-1")
        self.assertEqual(result.issuer_registry_revision, 1)
        self.assertEqual(verifier.calls, 1)

    def test_trusted_verifier_false_returns_denied(self):
        result = self.verify(self.service(FakeVerifier(result=False)))
        self.assertEqual(result.status, RecoveryEvidenceVerificationStatus.DENIED)

    def test_verifier_exception_returns_unavailable(self):
        result = self.verify(
            self.service(FakeVerifier(error=RuntimeError("issuer unavailable")))
        )
        self.assertEqual(result.status, RecoveryEvidenceVerificationStatus.UNAVAILABLE)

    def test_wrong_operation_or_targets_are_denied_before_verifier(self):
        verifier = FakeVerifier()
        service = self.service(verifier)
        result = self.verify(service, operation_id="operation-other")
        self.assertEqual(result.status, RecoveryEvidenceVerificationStatus.DENIED)
        self.assertEqual(verifier.calls, 0)

    def test_expired_or_not_yet_valid_evidence_is_denied_before_verifier(self):
        verifier = FakeVerifier()
        service = self.service(verifier)
        expired = make_evidence(expires_at=NOW)
        result = self.verify(service, evidence=expired)
        self.assertEqual(result.status, RecoveryEvidenceVerificationStatus.DENIED)
        future = make_evidence(
            issued_at=NOW + timedelta(seconds=1),
            expires_at=NOW + timedelta(minutes=5),
        )
        result = self.verify(service, evidence=future)
        self.assertEqual(result.status, RecoveryEvidenceVerificationStatus.DENIED)
        self.assertEqual(verifier.calls, 0)

    def test_wrong_evidence_kind_is_denied_before_verifier(self):
        verifier = FakeVerifier()
        result = self.verify(
            self.service(verifier),
            evidence=make_evidence(
                evidence_kind=MultiAuthorityRecoveryEvidenceKind.INVALIDATION_RECEIPT
            ),
        )
        self.assertEqual(result.status, RecoveryEvidenceVerificationStatus.DENIED)
        self.assertEqual(verifier.calls, 0)

    def test_service_rejects_invalid_verification_request(self):
        service = self.service(FakeVerifier())
        with self.assertRaises(ContractError):
            self.verify(service, targets=())
        with self.assertRaises(ContractError):
            self.verify(service, now=datetime(2026, 11, 16, 12, 0))
        with self.assertRaises(ContractError):
            MultiAuthorityRecoveryEvidenceVerificationService(
                object(), FakeTrustPolicyPort(), FakeIssuerRegistryPort()
            )
        with self.assertRaises(ContractError):
            MultiAuthorityRecoveryEvidenceVerificationService(
                FakeVerifier(), object(), FakeIssuerRegistryPort()
            )
        with self.assertRaises(ContractError):
            MultiAuthorityRecoveryEvidenceVerificationService(
                FakeVerifier(), FakeTrustPolicyPort(), object()
            )

    def test_untrusted_or_disabled_issuer_is_denied_before_verifier(self):
        verifier = FakeVerifier()
        policy = RecoveryEvidenceIssuerTrustPolicy(
            issuer_id="other-issuer",
            policy_revision=1,
            enabled=True,
            allowed_evidence_kinds=(
                MultiAuthorityRecoveryEvidenceKind.SOURCE_OUTCOME_RECEIPT,
            ),
            valid_from=NOW - timedelta(days=1),
            valid_until=NOW + timedelta(days=1),
            max_evidence_lifetime_seconds=600,
        )
        result = self.verify(self.service(verifier, FakeTrustPolicyPort(policy)))
        self.assertEqual(result.status, RecoveryEvidenceVerificationStatus.DENIED)
        self.assertEqual(verifier.calls, 0)

    def test_policy_restricts_evidence_kind_and_maximum_lifetime(self):
        verifier = FakeVerifier()
        wrong_kind = RecoveryEvidenceIssuerTrustPolicy(
            issuer_id="trusted-source-1",
            policy_revision=2,
            enabled=True,
            allowed_evidence_kinds=(
                MultiAuthorityRecoveryEvidenceKind.INVALIDATION_RECEIPT,
            ),
            valid_from=NOW - timedelta(days=1),
            valid_until=NOW + timedelta(days=1),
            max_evidence_lifetime_seconds=600,
        )
        result = self.verify(self.service(verifier, FakeTrustPolicyPort(wrong_kind)))
        self.assertEqual(result.status, RecoveryEvidenceVerificationStatus.DENIED)
        long_lived = make_evidence(
            expires_at=NOW + timedelta(minutes=20)
        )
        result = self.verify(
            self.service(verifier),
            evidence=long_lived,
        )
        self.assertEqual(result.status, RecoveryEvidenceVerificationStatus.DENIED)
        self.assertEqual(verifier.calls, 0)

    def test_disabled_issuer_policy_is_denied_before_verifier(self):
        verifier = FakeVerifier()
        disabled = RecoveryEvidenceIssuerTrustPolicy(
            issuer_id="trusted-source-1",
            policy_revision=3,
            enabled=False,
            allowed_evidence_kinds=(
                MultiAuthorityRecoveryEvidenceKind.SOURCE_OUTCOME_RECEIPT,
            ),
            valid_from=NOW - timedelta(days=1),
            valid_until=NOW + timedelta(days=1),
            max_evidence_lifetime_seconds=600,
        )
        result = self.verify(self.service(verifier, FakeTrustPolicyPort(disabled)))
        self.assertEqual(result.status, RecoveryEvidenceVerificationStatus.DENIED)
        self.assertEqual(verifier.calls, 0)


    def test_unregistered_issuer_is_denied_before_policy_and_verifier(self):
        verifier = FakeVerifier()
        policies = FakeTrustPolicyPort()
        registry = FakeIssuerRegistryPort(registration=None)
        result = self.verify(self.service(verifier, policies, registry))
        self.assertEqual(result.status, RecoveryEvidenceVerificationStatus.DENIED)
        self.assertEqual(registry.calls, 1)
        self.assertEqual(policies.calls, 0)
        self.assertEqual(verifier.calls, 0)

    def test_disabled_registry_issuer_is_denied_before_policy_and_verifier(self):
        verifier = FakeVerifier()
        policies = FakeTrustPolicyPort()
        registry = FakeIssuerRegistryPort(
            registration=RecoveryEvidenceIssuerRegistration(
                issuer_id="trusted-source-1",
                registry_revision=2,
                enabled=False,
                changed_at=NOW - timedelta(minutes=1),
            )
        )
        result = self.verify(self.service(verifier, policies, registry))
        self.assertEqual(result.status, RecoveryEvidenceVerificationStatus.DENIED)
        self.assertEqual(policies.calls, 0)
        self.assertEqual(verifier.calls, 0)

    def test_registry_source_failure_is_unavailable(self):
        verifier = FakeVerifier()
        policies = FakeTrustPolicyPort()
        registry = FakeIssuerRegistryPort(error=RuntimeError("registry unavailable"))
        result = self.verify(self.service(verifier, policies, registry))
        self.assertEqual(result.status, RecoveryEvidenceVerificationStatus.UNAVAILABLE)
        self.assertEqual(policies.calls, 0)
        self.assertEqual(verifier.calls, 0)

    def test_registry_identity_mismatch_is_denied(self):
        verifier = FakeVerifier()
        registration = RecoveryEvidenceIssuerRegistration(
            issuer_id="different-issuer",
            registry_revision=1,
            enabled=True,
            changed_at=NOW - timedelta(minutes=1),
        )
        result = self.verify(
            self.service(
                verifier,
                FakeTrustPolicyPort(),
                FakeIssuerRegistryPort(registration=registration),
            )
        )
        self.assertEqual(result.status, RecoveryEvidenceVerificationStatus.DENIED)
        self.assertEqual(verifier.calls, 0)


    def test_registry_revision_change_during_verification_denies_result(self):
        registry = FakeIssuerRegistryPort()
        registry_changed = RecoveryEvidenceIssuerRegistration(
            issuer_id="trusted-source-1",
            registry_revision=2,
            enabled=False,
            changed_at=NOW,
        )
        verifier = FakeVerifier(
            on_verify=lambda: setattr(registry, "registration", registry_changed)
        )
        result = self.verify(self.service(verifier, issuer_registry_port=registry))
        self.assertEqual(result.status, RecoveryEvidenceVerificationStatus.DENIED)
        self.assertIsNone(result.issuer_registry_revision)
        self.assertEqual(registry.calls, 2)

    def test_registry_revision_change_while_still_enabled_denies_stale_result(self):
        registry = FakeIssuerRegistryPort()
        registry_changed = RecoveryEvidenceIssuerRegistration(
            issuer_id="trusted-source-1",
            registry_revision=2,
            enabled=True,
            changed_at=NOW,
        )
        verifier = FakeVerifier(
            on_verify=lambda: setattr(registry, "registration", registry_changed)
        )
        result = self.verify(self.service(verifier, issuer_registry_port=registry))
        self.assertEqual(result.status, RecoveryEvidenceVerificationStatus.DENIED)
        self.assertEqual(registry.calls, 2)

    def test_registry_unavailable_on_post_verification_check_is_unavailable(self):
        class FailsOnSecondRead(FakeIssuerRegistryPort):
            def get_registration(self, issuer_id):
                self.calls += 1
                if self.calls == 2:
                    raise RuntimeError("registry lost during verification")
                return self.registration

        registry = FailsOnSecondRead()
        verifier = FakeVerifier()
        result = self.verify(self.service(verifier, issuer_registry_port=registry))
        self.assertEqual(result.status, RecoveryEvidenceVerificationStatus.UNAVAILABLE)
        self.assertEqual(registry.calls, 2)
        self.assertIsNone(result.issuer_registry_revision)

    def test_verified_result_requires_registry_revision(self):
        from atlas.application.recovery_evidence import RecoveryEvidenceVerification

        with self.assertRaises(ContractError):
            RecoveryEvidenceVerification(
                RecoveryEvidenceVerificationStatus.VERIFIED,
                "evidence-1",
            )

    def test_trust_policy_source_failure_is_unavailable(self):
        verifier = FakeVerifier()
        result = self.verify(
            self.service(
                verifier,
                FakeTrustPolicyPort(error=RuntimeError("policy source unavailable")),
            )
        )
        self.assertEqual(result.status, RecoveryEvidenceVerificationStatus.UNAVAILABLE)
        self.assertEqual(verifier.calls, 0)


if __name__ == "__main__":
    unittest.main()
