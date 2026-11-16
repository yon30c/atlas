from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest

from atlas.authorization.models import AuthorizationRequest
from atlas.authorization.operation_models import OperationAuthorizationEvidence
from atlas.authorization.operation_verification import (
    OperationAuthorizationEvidenceVerificationService,
    OperationEvidenceStatus,
)
from atlas.core.errors import ContractError
from tests.unit.test_operation_authorization_contracts import (
    NOW,
    make_evidence,
    make_request,
)


class FakeVerifier:
    def __init__(self, result=True, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def verify(self, request, evidence, now):
        self.calls.append((request, evidence, now))
        if self.error is not None:
            raise self.error
        return self.result


class OperationAuthorizationEvidenceVerificationTests(unittest.TestCase):
    def setUp(self):
        self.request = make_request()
        self.evidence = make_evidence(self.request)
        self.verifier = FakeVerifier()
        self.service = OperationAuthorizationEvidenceVerificationService(
            self.verifier
        )

    def test_valid_claims_are_delegated_to_trusted_verifier(self):
        result = self.service.verify(self.request, self.evidence, NOW)
        self.assertIs(result.status, OperationEvidenceStatus.VERIFIED)
        self.assertEqual(len(self.verifier.calls), 1)

    def test_mismatched_request_is_denied_without_calling_verifier(self):
        request = replace(self.request, resource_id="other-workspace")
        result = self.service.verify(request, self.evidence, NOW)
        self.assertIs(result.status, OperationEvidenceStatus.DENIED)
        self.assertEqual(self.verifier.calls, [])

    def test_expired_evidence_is_denied_without_calling_verifier(self):
        result = self.service.verify(
            self.request,
            self.evidence,
            self.evidence.expires_at,
        )
        self.assertIs(result.status, OperationEvidenceStatus.DENIED)
        self.assertEqual(self.verifier.calls, [])

    def test_not_yet_valid_evidence_is_denied_without_calling_verifier(self):
        result = self.service.verify(
            self.request,
            self.evidence,
            self.evidence.issued_at - timedelta(microseconds=1),
        )
        self.assertIs(result.status, OperationEvidenceStatus.DENIED)
        self.assertEqual(self.verifier.calls, [])

    def test_authoritative_verifier_denial_is_denied(self):
        self.verifier.result = False
        result = self.service.verify(self.request, self.evidence, NOW)
        self.assertIs(result.status, OperationEvidenceStatus.DENIED)

    def test_verifier_exception_fails_closed_as_unavailable(self):
        self.verifier.error = RuntimeError("authority unavailable")
        result = self.service.verify(self.request, self.evidence, NOW)
        self.assertIs(result.status, OperationEvidenceStatus.UNAVAILABLE)

    def test_verifier_must_return_exact_true(self):
        self.verifier.result = 1
        result = self.service.verify(self.request, self.evidence, NOW)
        self.assertIs(result.status, OperationEvidenceStatus.DENIED)

    def test_invalid_inputs_are_rejected(self):
        with self.assertRaises(ContractError):
            self.service.verify(object(), self.evidence, NOW)
        with self.assertRaises(ContractError):
            self.service.verify(self.request, object(), NOW)
        with self.assertRaises(ContractError):
            self.service.verify(
                self.request,
                self.evidence,
                datetime(2026, 11, 16, 12, 0),
            )

    def test_verification_result_is_not_an_execution_permission(self):
        result = self.service.verify(self.request, self.evidence, NOW)
        self.assertEqual(
            set(result.__dataclass_fields__),
            {"status", "evidence_id"},
        )


if __name__ == "__main__":
    unittest.main()
