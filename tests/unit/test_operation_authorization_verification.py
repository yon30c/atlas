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
from tests.fixtures.contexts import user_context


NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def make_request():
    context = replace(
        user_context(),
        request_id="request-workspace-verify",
        project_id="atlas-demo",
        environment="test",
    )
    return AuthorizationRequest(
        context=context,
        action="workspace.list",
        resource_type="workspace",
        resource_id="demo",
        resource_owner_id="owner-1",
    )


def make_evidence(request):
    context = request.context
    return OperationAuthorizationEvidence(
        evidence_id="evidence-verify-1",
        decision_id="decision-verify-1",
        request_id=context.request_id,
        actor_identity_id=context.actor.identity_id,
        actor_revision=context.actor.revision,
        project_id=context.project_id,
        environment=context.environment,
        action=request.action,
        resource_type=request.resource_type,
        resource_id=request.resource_id,
        resource_owner_id=request.resource_owner_id,
        grant_id="grant-verify-1",
        grant_revision=2,
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=5),
        issuer_id="cam-authority",
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
