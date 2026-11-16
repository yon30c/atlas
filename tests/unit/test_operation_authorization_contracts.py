from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import unittest

from atlas.authorization.models import AuthorizationDecision, AuthorizationRequest
from atlas.authorization.operation_models import (
    OperationAuthorizationEvidence,
    OperationAuthorizationResult,
)
from atlas.core.errors import ContractError
from tests.fixtures.contexts import user_context


NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def make_request():
    context = replace(
        user_context(),
        request_id="request-workspace-1",
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


def make_evidence(request=None, **changes):
    request = request or make_request()
    context = request.context
    values = {
        "evidence_id": "evidence-1",
        "decision_id": "decision-1",
        "request_id": context.request_id,
        "actor_identity_id": context.actor.identity_id,
        "actor_revision": context.actor.revision,
        "project_id": context.project_id,
        "environment": context.environment,
        "action": request.action,
        "resource_type": request.resource_type,
        "resource_id": request.resource_id,
        "resource_owner_id": request.resource_owner_id,
        "grant_id": "grant-1",
        "grant_revision": 2,
        "project_revision": 3,
        "environment_revision": 4,
        "issued_at": NOW - timedelta(minutes=1),
        "expires_at": NOW + timedelta(minutes=5),
        "issuer_id": "cam-authority",
    }
    values.update(changes)
    return OperationAuthorizationEvidence(**values)


class OperationAuthorizationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.request = make_request()
        self.evidence = make_evidence(self.request)

    def test_evidence_matches_exact_request(self):
        self.assertTrue(self.evidence.matches(self.request))

    def test_evidence_rejects_changed_request_attributes(self):
        changes = (
            {"action": "workspace.read"},
            {"resource_type": "file"},
            {"resource_id": "other"},
            {"resource_owner_id": "other-owner"},
        )
        for change in changes:
            with self.subTest(change=change):
                self.assertFalse(
                    self.evidence.matches(replace(self.request, **change))
                )

    def test_evidence_rejects_changed_context_attributes(self):
        context_changes = (
            {"request_id": "other-request"},
            {"project_id": "other-project"},
            {"environment": "production"},
            {"actor": replace(self.request.context.actor, revision=99)},
        )
        for change in context_changes:
            with self.subTest(change=change):
                request = replace(
                    self.request,
                    context=replace(self.request.context, **change),
                )
                self.assertFalse(self.evidence.matches(request))

    def test_evidence_requires_complete_context_claims(self):
        for field in ("project_id", "environment", "actor_identity_id", "grant_id"):
            with self.subTest(field=field):
                with self.assertRaises(ContractError):
                    replace(self.evidence, **{field: " "})

    def test_revisions_must_be_positive_integers_not_booleans(self):
        for field in (
            "actor_revision",
            "grant_revision",
            "project_revision",
            "environment_revision",
        ):
            for value in (0, -1, True, 1.5):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ContractError):
                        replace(self.evidence, **{field: value})

    def test_evidence_requires_utc_validity_window(self):
        with self.assertRaises(ContractError):
            replace(self.evidence, issued_at=datetime(2026, 11, 16, 12, 0))
        with self.assertRaises(ContractError):
            replace(
                self.evidence,
                expires_at=NOW + timedelta(hours=1),
                issued_at=NOW + timedelta(hours=2),
            )

    def test_current_time_is_inclusive_at_issue_and_exclusive_at_expiry(self):
        self.assertTrue(self.evidence.is_current_at(self.evidence.issued_at))
        self.assertFalse(self.evidence.is_current_at(self.evidence.expires_at))
        self.assertTrue(self.evidence.is_current_at(NOW))

    def test_current_time_must_be_utc(self):
        with self.assertRaises(ContractError):
            self.evidence.is_current_at(datetime(2026, 11, 16, 12, 0))


class OperationAuthorizationResultTests(unittest.TestCase):
    def setUp(self):
        self.evidence = make_evidence()

    def test_allow_requires_operation_evidence(self):
        with self.assertRaises(ContractError):
            OperationAuthorizationResult(AuthorizationDecision.ALLOW)

    def test_allow_accepts_operation_evidence(self):
        result = OperationAuthorizationResult(
            AuthorizationDecision.ALLOW,
            self.evidence,
        )
        self.assertIs(result.evidence, self.evidence)

    def test_denial_and_approval_required_cannot_carry_allow_evidence(self):
        for decision in (
            AuthorizationDecision.DENY,
            AuthorizationDecision.REQUIRE_APPROVAL,
        ):
            with self.subTest(decision=decision):
                with self.assertRaises(ContractError):
                    OperationAuthorizationResult(decision, self.evidence)
                result = OperationAuthorizationResult(decision)
                self.assertIsNone(result.evidence)

    def test_result_rejects_untyped_decision_or_evidence(self):
        with self.assertRaises(ContractError):
            OperationAuthorizationResult("allow", self.evidence)
        with self.assertRaises(ContractError):
            OperationAuthorizationResult(AuthorizationDecision.ALLOW, object())

    def test_contracts_are_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            self.evidence.grant_revision = 3


if __name__ == "__main__":
    unittest.main()
