"""Pruebas de fallos controlados para C45-C64 del journal ME-03.

Los fakes de este módulo son modelos deterministas de protocolo. No demuestran
durabilidad, consenso, fencing de procesos reales ni garantías de transporte.
"""
import unittest
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from atlas.core.errors import ContractError
from atlas.memory.consistency import (
    AuthorityKind,
    AuthorityRevision,
    AuthorizationRevisionSet,
)
from atlas.memory.journal import (
    ConsistencyCheckpoint,
    ConsistencyPosition,
    ConsistencyRecordKind,
    ConsistencyRecoveryState,
    ConsistencyTransition,
    JournalCommit,
    JournalEntry,
)

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
DOMAIN = "memory-domain-c45"
MEMORY_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c074001"
VERSION_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c074002"
OWNER_RECORD = "018bcfe5-7b3a-7cc2-98c4-dc0c0c074003"
CHECKPOINT_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c074004"


class AppendOutcomeUnknown(RuntimeError):
    """El caller no sabe si el append se confirmó."""


def pos(sequence, domain=DOMAIN, epoch=1):
    return ConsistencyPosition(domain, epoch, sequence)


def admitted(record_id=OWNER_RECORD, admission_id="admission-c45", generation=1):
    return ConsistencyTransition(
        record_id=record_id,
        schema_version=1,
        record_kind=ConsistencyRecordKind.READ_ADMITTED,
        operation_id=f"read:{admission_id}",
        occurred_at=NOW,
        idempotency_key=f"admit:{admission_id}",
        memory_id=MEMORY_ID,
        version_id=VERSION_ID,
        snapshot_id=f"snapshot:{admission_id}",
        actor_identity_id="identity-owner",
        revisions=AuthorizationRevisionSet(
            memory_revision=AuthorityRevision(AuthorityKind.MEMORY, MEMORY_ID, 1),
            version_revision=AuthorityRevision(AuthorityKind.MEMORY_VERSION, VERSION_ID, 1),
            identity_revision=AuthorityRevision(AuthorityKind.IDENTITY, "identity-owner", 1),
        ),
        admission_id=admission_id,
        generation=generation,
        route_ids=frozenset({"assistant-response", "api-response"}),
    )


def forget_closed(
    record_id=OWNER_RECORD,
    operation_id="forget:op-c45",
    memory_id=MEMORY_ID,
    generation=2,
    key="forget:key-c45",
):
    return ConsistencyTransition(
        record_id=record_id,
        schema_version=1,
        record_kind=ConsistencyRecordKind.FORGET_CLOSED,
        operation_id=operation_id,
        occurred_at=NOW,
        idempotency_key=key,
        request_id="forget-request-c45",
        actor_identity_id="owner-identity",
        subject_user_id="owner-user",
        owner_id="owner-user",
        memory_id=memory_id,
        generation=generation,
        proof_reference="verified-owner-proof-receipt",
    )


def egress_committed(
    record_id=OWNER_RECORD,
    admission_id="admission-c45",
    endpoint_id="assistant-response",
    generation=1,
    receipt_id="receipt-c45",
):
    return ConsistencyTransition(
        record_id=record_id,
        schema_version=1,
        record_kind=ConsistencyRecordKind.EGRESS_COMMITTED,
        operation_id=f"read:{admission_id}",
        occurred_at=NOW,
        admission_id=admission_id,
        endpoint_id=endpoint_id,
        generation=generation,
        emission_id="emission-c45",
        emission_sequence=1,
        receipt_id=receipt_id,
    )


@dataclass(frozen=True)
class EndpointReceipt:
    admission_id: str
    endpoint_id: str
    generation: int
    receipt_id: str
    emission_id: str
    emission_sequence: int


class FaultInjectingJournalFake:
    """Fake secuencial con puntos de fallo antes/después del append."""

    def __init__(self, domain=DOMAIN, epoch=1):
        self.domain = domain
        self.epoch = epoch
        self.sequence = 0
        self.entries = []
        self.idempotency = {}
        self.record_ids = {}
        self.receipt_index = {}
        self.fail_before_append = False
        self.fail_after_append = False
        self.corrupt_recovery = False
        self.unsupported_schema = False
        self.trusted_watermark = 0
        self.compacted_idempotency = set()

    def position(self):
        return pos(self.sequence, self.domain, self.epoch)

    @staticmethod
    def canonical(transition):
        return replace(transition, record_id=OWNER_RECORD, occurred_at=NOW)

    def append_transition(self, expected, transition):
        if not isinstance(expected, ConsistencyPosition):
            return None
        if (
            expected.consistency_domain_id != self.domain
            or expected.authority_epoch != self.epoch
            or transition.schema_version != 1
        ):
            return None

        if transition.idempotency_key:
            previous = self.idempotency.get(transition.idempotency_key)
            if previous:
                canonical, commit = previous
                if canonical != self.canonical(transition):
                    return None
                return replace(commit, replayed=True)

        if transition.receipt_id:
            previous = self.receipt_index.get(transition.receipt_id)
            if previous:
                canonical, commit = previous
                if canonical != self.canonical(transition):
                    return None
                return replace(commit, replayed=True)

        if expected != self.position():
            return None
        if transition.record_id in self.record_ids:
            return None
        if self.fail_before_append:
            self.fail_before_append = False
            return None

        self.sequence += 1
        committed_position = self.position()
        entry = JournalEntry(committed_position, transition)
        commit = JournalCommit(committed_position, transition.record_id, False)
        self.entries.append(entry)
        self.record_ids[transition.record_id] = entry
        canonical = self.canonical(transition)
        if transition.idempotency_key:
            self.idempotency[transition.idempotency_key] = (canonical, commit)
        if transition.receipt_id:
            self.receipt_index[transition.receipt_id] = (canonical, commit)

        if self.fail_after_append:
            self.fail_after_append = False
            raise AppendOutcomeUnknown("append pudo haberse confirmado")
        return commit

    def load_recovery_state(self, domain_id):
        if (
            domain_id != self.domain
            or self.corrupt_recovery
            or self.unsupported_schema
            or self.sequence < self.trusted_watermark
        ):
            return None
        try:
            return ConsistencyRecoveryState(
                domain_id=self.domain,
                authority_epoch=self.epoch,
                checkpoint=None,
                entries=tuple(self.entries),
                head_sequence=self.sequence,
                continuity_reference="fake-watermark-not-cryptographic",
            )
        except ContractError:
            return None

    def load_endpoint_receipts(self, admission_id):
        return tuple(
            entry for entry in self.entries
            if entry.transition.admission_id == admission_id
            and entry.transition.record_kind in (
                ConsistencyRecordKind.EGRESS_COMMITTED,
                ConsistencyRecordKind.ENDPOINT_COMPLETED,
                ConsistencyRecordKind.ENDPOINT_FENCED,
            )
        )

    def compact_idempotency(self, key, still_required):
        if still_required or key in self.idempotency:
            return False
        self.compacted_idempotency.add(key)
        return True


class ReadForgetGateFake:
    """Ordena admisión/cierre/egress en una única secuencia determinista."""

    def __init__(self, journal):
        self.journal = journal
        self.closed = False
        self.generation = 1
        self.content_reads = 0
        self.admissions = set()
        self.egress = []

    def admit(self, transition):
        if self.closed:
            return False
        commit = self.journal.append_transition(self.journal.position(), transition)
        if commit is None:
            return False
        self.admissions.add(transition.admission_id)
        self.content_reads += 1
        return True

    def close_forget(self, transition):
        commit = self.journal.append_transition(self.journal.position(), transition)
        if commit is None:
            return False
        self.closed = True
        self.generation = transition.generation
        return True

    def emit(self, transition):
        if self.closed or transition.generation != self.generation:
            return False
        commit = self.journal.append_transition(self.journal.position(), transition)
        if commit is None:
            return False
        self.egress.append(transition.receipt_id)
        return True


class OneShotOwnerProofVerifierFake:
    """Emite éxito una sola vez; no implementa criptografía ni issuer real."""

    def __init__(self, available=True):
        self.available = available
        self.consumed = set()

    def verify_and_consume(self, proof_id):
        if not self.available or proof_id in self.consumed:
            return False
        self.consumed.add(proof_id)
        return True


def receipt_matches_transition(receipt, transition):
    return (
        receipt.admission_id == transition.admission_id
        and receipt.endpoint_id == transition.endpoint_id
        and receipt.generation == transition.generation
        and receipt.receipt_id == transition.receipt_id
        and receipt.emission_id == transition.emission_id
        and receipt.emission_sequence == transition.emission_sequence
    )


def begin_forget_with_proof(journal, verifier, proof_id):
    if not verifier.verify_and_consume(proof_id):
        return False
    transition = forget_closed(
        record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074005",
        key=f"forget:{proof_id}",
    )
    return journal.append_transition(journal.position(), transition) is not None


def restore_gate_from_verified_inventory(required_admissions, verified_admissions):
    """La puerta solo puede abrir si el inventario completo está demostrado."""
    if verified_admissions is None:
        return False
    return set(required_admissions).issubset(set(verified_admissions))


class MemoryJournalFailureScenarios(unittest.TestCase):
    def test_c45_failed_durable_admission_never_reads_content(self):
        journal = FaultInjectingJournalFake()
        gate = ReadForgetGateFake(journal)
        journal.fail_before_append = True
        self.assertFalse(gate.admit(admitted()))
        self.assertEqual(gate.content_reads, 0)
        self.assertEqual(journal.sequence, 0)

    def test_c46_admission_and_forget_close_have_one_deterministic_order(self):
        journal = FaultInjectingJournalFake()
        gate = ReadForgetGateFake(journal)
        self.assertTrue(gate.admit(admitted()))
        self.assertTrue(gate.close_forget(forget_closed(record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074005")))
        self.assertEqual(journal.entries[0].transition.record_kind, ConsistencyRecordKind.READ_ADMITTED)
        self.assertEqual(journal.entries[1].transition.record_kind, ConsistencyRecordKind.FORGET_CLOSED)
        self.assertFalse(gate.admit(admitted(record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074006", admission_id="late-read")))

        close_first_journal = FaultInjectingJournalFake()
        close_first_gate = ReadForgetGateFake(close_first_journal)
        self.assertTrue(close_first_gate.close_forget(forget_closed()))
        self.assertFalse(close_first_gate.admit(admitted(
            record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074005",
            admission_id="read-after-close",
        )))
        self.assertEqual(close_first_journal.sequence, 1)

    def test_c47_egress_before_close_is_ordered_before_close(self):
        journal = FaultInjectingJournalFake()
        gate = ReadForgetGateFake(journal)
        self.assertTrue(gate.admit(admitted()))
        self.assertTrue(gate.emit(egress_committed(record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074005")))
        self.assertTrue(gate.close_forget(forget_closed(record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074006")))
        self.assertEqual(journal.entries[1].transition.record_kind, ConsistencyRecordKind.EGRESS_COMMITTED)
        self.assertEqual(journal.entries[2].transition.record_kind, ConsistencyRecordKind.FORGET_CLOSED)
        self.assertFalse(gate.emit(egress_committed(record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074007", generation=1)))

    def test_c48_same_idempotency_key_and_request_replays_one_commit(self):
        journal = FaultInjectingJournalFake()
        first = journal.append_transition(journal.position(), admitted())
        retry = journal.append_transition(journal.position(), replace(admitted(record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074005"), occurred_at=NOW))
        self.assertEqual(retry.position, first.position)
        self.assertTrue(retry.replayed)
        self.assertEqual(len(journal.entries), 1)

    def test_c49_idempotency_key_with_different_target_is_conflict(self):
        journal = FaultInjectingJournalFake()
        journal.append_transition(journal.position(), admitted())
        different = replace(
            admitted(record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074005"),
            snapshot_id="different-snapshot-for-same-idempotency-key",
        )
        self.assertIsNone(journal.append_transition(journal.position(), different))
        self.assertEqual(len(journal.entries), 1)

    def test_c50_recovery_after_forget_closed_keeps_gate_closed(self):
        journal = FaultInjectingJournalFake()
        gate = ReadForgetGateFake(journal)
        self.assertTrue(gate.close_forget(forget_closed()))
        recovered = journal.load_recovery_state(DOMAIN)
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.entries[0].transition.record_kind, ConsistencyRecordKind.FORGET_CLOSED)
        restored_gate = ReadForgetGateFake(journal)
        restored_gate.closed = any(
            entry.transition.record_kind is ConsistencyRecordKind.FORGET_CLOSED
            for entry in recovered.entries
        )
        self.assertTrue(restored_gate.closed)
        self.assertFalse(restored_gate.admit(admitted(record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074005")))

    def test_c51_endpoint_commit_before_journal_ack_is_reconciled_by_receipt(self):
        journal = FaultInjectingJournalFake()
        endpoint_store = {
            "receipt-c45": EndpointReceipt(
                admission_id="admission-c45",
                endpoint_id="assistant-response",
                generation=1,
                receipt_id="receipt-c45",
                emission_id="emission-c45",
                emission_sequence=1,
            )
        }
        transition = egress_committed()
        journal.fail_before_append = True
        self.assertIsNone(journal.append_transition(journal.position(), transition))
        self.assertEqual(journal.sequence, 0)
        external_receipt = endpoint_store["receipt-c45"]
        self.assertTrue(receipt_matches_transition(external_receipt, transition))
        # Solo después de validar todos los campos correlacionados se registra el recibo.
        recovered = journal.append_transition(journal.position(), transition)
        self.assertEqual(recovered.position.sequence, 1)
        self.assertEqual(journal.sequence, 1)

        mismatches = (
            replace(external_receipt, endpoint_id="api-response"),
            replace(external_receipt, generation=2),
            replace(external_receipt, emission_id="different-emission"),
            replace(external_receipt, emission_sequence=2),
            replace(external_receipt, receipt_id="different-receipt"),
        )
        self.assertTrue(all(not receipt_matches_transition(item, transition) for item in mismatches))

    def test_c52_identical_endpoint_receipt_is_idempotent(self):
        journal = FaultInjectingJournalFake()
        transition = egress_committed()
        first = journal.append_transition(journal.position(), transition)
        repeated = journal.append_transition(journal.position(), replace(
            transition, record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074005"
        ))
        self.assertTrue(repeated.replayed)
        self.assertEqual(first.position, repeated.position)
        self.assertEqual(journal.sequence, 1)

    def test_c53_contradictory_endpoint_or_generation_receipt_is_rejected(self):
        journal = FaultInjectingJournalFake()
        journal.append_transition(journal.position(), egress_committed())
        contradictory = egress_committed(
            record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074005",
            endpoint_id="api-response",
        )
        self.assertIsNone(journal.append_transition(journal.position(), contradictory))
        wrong_generation = egress_committed(
            record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074006",
            generation=2,
        )
        self.assertIsNone(journal.append_transition(journal.position(), wrong_generation))
        self.assertEqual(journal.sequence, 1)

    def test_c54_duplicate_sequence_with_different_record_is_quarantined(self):
        journal = FaultInjectingJournalFake()
        journal.append_transition(journal.position(), admitted())
        conflicting = JournalEntry(pos(1), admitted(record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074005"))
        journal.entries.append(conflicting)
        journal.sequence = 1
        with self.assertRaises(ContractError):
            ConsistencyRecoveryState(
                domain_id=DOMAIN,
                authority_epoch=1,
                checkpoint=None,
                entries=tuple(journal.entries),
                head_sequence=1,
                continuity_reference="untrusted",
            )

    def test_c55_truncated_journal_with_head_gap_is_quarantined(self):
        journal = FaultInjectingJournalFake()
        journal.append_transition(journal.position(), admitted())
        journal.append_transition(journal.position(), replace(
            admitted(record_id="018bcfe5-7b3a-7cc2-98c4-dc0c0c074005", admission_id="second"),
            idempotency_key="admit:second",
        ))
        journal.entries.pop(0)
        self.assertIsNone(journal.load_recovery_state(DOMAIN))

    def test_c56_journal_head_behind_trusted_watermark_is_rejected(self):
        journal = FaultInjectingJournalFake()
        journal.trusted_watermark = 4
        journal.sequence = 3
        self.assertIsNone(journal.load_recovery_state(DOMAIN))

    def test_c57_checkpoint_without_active_admission_inventory_keeps_gate_closed(self):
        journal = FaultInjectingJournalFake()
        gate = ReadForgetGateFake(journal)
        gate.admit(admitted())
        required = {"admission-c45"}
        # El checkpoint actual no transporta inventario verificable de admisiones.
        verified_inventory = None
        self.assertFalse(restore_gate_from_verified_inventory(required, verified_inventory))
        restored_gate = ReadForgetGateFake(journal)
        restored_gate.closed = not restore_gate_from_verified_inventory(
            required, verified_inventory
        )
        self.assertTrue(restored_gate.closed)

    def test_c58_consumed_owner_proof_is_not_reused_after_close_append_failure(self):
        journal = FaultInjectingJournalFake()
        verifier = OneShotOwnerProofVerifierFake()
        journal.fail_before_append = True
        self.assertFalse(begin_forget_with_proof(journal, verifier, "proof-once"))
        self.assertTrue(verifier.verify_and_consume("proof-once") is False)
        self.assertEqual(journal.sequence, 0)

    def test_c59_unavailable_proof_verifier_prevents_forget_close(self):
        journal = FaultInjectingJournalFake()
        verifier = OneShotOwnerProofVerifierFake(available=False)
        self.assertFalse(begin_forget_with_proof(journal, verifier, "proof-unavailable"))
        self.assertEqual(journal.sequence, 0)
        self.assertIsNone(journal.load_recovery_state("unknown-domain"))

    def test_c60_compaction_preserves_tombstone_needed_for_idempotency(self):
        journal = FaultInjectingJournalFake()
        journal.append_transition(journal.position(), admitted())
        self.assertFalse(journal.compact_idempotency("admit:admission-c45", still_required=True))
        self.assertIn("admit:admission-c45", journal.idempotency)
        self.assertNotIn("admit:admission-c45", journal.compacted_idempotency)

    def test_c61_partial_multi_resource_recovery_keeps_all_overlapping_routes_closed(self):
        journal = FaultInjectingJournalFake()
        gate = ReadForgetGateFake(journal)
        gate.closed = True
        verified_resources = {MEMORY_ID}
        required_resources = {MEMORY_ID, "018bcfe5-7b3a-7cc2-98c4-dc0c0c074099"}
        all_verified = required_resources.issubset(verified_resources)
        if all_verified:
            gate.closed = False
        self.assertFalse(all_verified)
        self.assertTrue(gate.closed)

    def test_c62_unknown_schema_version_fails_closed(self):
        journal = FaultInjectingJournalFake()
        journal.unsupported_schema = True
        self.assertIsNone(journal.load_recovery_state(DOMAIN))
        with self.assertRaises(ContractError):
            replace(admitted(), schema_version=2)
        self.assertEqual(journal.sequence, 0)

    def test_c63_endpoint_fence_without_correlated_journal_receipt_does_not_suppress(self):
        journal = FaultInjectingJournalFake()
        external_fence_receipt = EndpointReceipt(
            admission_id="admission-c45",
            endpoint_id="assistant-response",
            generation=2,
            receipt_id="external-fence-receipt",
            emission_id="fence-control",
            emission_sequence=0,
        )
        journaled = journal.load_endpoint_receipts(external_fence_receipt.admission_id)
        suppression_confirmed = bool(journaled)
        self.assertFalse(suppression_confirmed)
        self.assertEqual(journal.sequence, 0)

    def test_c64_ambiguous_append_retry_does_not_create_second_operation(self):
        journal = FaultInjectingJournalFake()
        transition = admitted()
        journal.fail_after_append = True
        with self.assertRaises(AppendOutcomeUnknown):
            journal.append_transition(journal.position(), transition)
        retry = journal.append_transition(pos(0), transition)
        self.assertTrue(retry.replayed)
        self.assertEqual(journal.sequence, 1)
        self.assertEqual(len(journal.entries), 1)


if __name__ == "__main__":
    unittest.main()
