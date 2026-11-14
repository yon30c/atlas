"""Pruebas puras del modelo de cierre lógico Forget."""
import unittest

from atlas.core.errors import ContractError
from atlas.memory.forget import (
    ForgetClosure,
    ForgetClosureStatus,
    ForgetTarget,
)


MEMORY_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a11"
CLOSURE_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a13"


def closure(
    status=ForgetClosureStatus.CLOSING,
    affected=frozenset({"admission-1"}),
    unresolved=frozenset({"admission-1"}),
    generation=2,
):
    return ForgetClosure(
        closure_id=CLOSURE_ID,
        operation_id="forget-op-1",
        idempotency_key="forget-key-1",
        target=ForgetTarget(MEMORY_ID),
        generation=generation,
        affected_admission_ids=affected,
        unresolved_admission_ids=unresolved,
        delivery_route_ids=frozenset({"assistant-response", "api-response"}),
        status=status,
    )


class ForgetClosureModelTests(unittest.TestCase):
    def test_closing_retains_all_prior_admissions_as_unresolved(self):
        item = closure()
        self.assertIs(item.status, ForgetClosureStatus.CLOSING)
        self.assertEqual(item.affected_admission_ids, item.unresolved_admission_ids)

    def test_suppressed_retains_history_but_requires_no_unresolved_admissions(self):
        item = closure(
            status=ForgetClosureStatus.SUPPRESSED,
            affected=frozenset({"admission-1", "admission-2"}),
            unresolved=frozenset(),
        )
        self.assertEqual(item.affected_admission_ids, frozenset({"admission-1", "admission-2"}))
        self.assertFalse(item.unresolved_admission_ids)

    def test_suppressed_with_unresolved_admission_is_rejected(self):
        with self.assertRaises(ContractError):
            closure(status=ForgetClosureStatus.SUPPRESSED)

    def test_unresolved_must_be_subset_of_affected_admissions(self):
        with self.assertRaises(ContractError):
            closure(unresolved=frozenset({"unknown-admission"}))

    def test_target_requires_canonical_memory_id(self):
        with self.assertRaises(ContractError):
            ForgetTarget("not-a-uuid")

    def test_closure_requires_positive_generation(self):
        with self.assertRaises(ContractError):
            closure(generation=0)

    def test_evidence_contains_no_memory_payload_or_content_hash_fields(self):
        item = closure()
        self.assertFalse(hasattr(item, "content"))
        self.assertFalse(hasattr(item, "content_hash"))
        self.assertFalse(hasattr(item, "payload"))


if __name__ == "__main__":
    unittest.main()
