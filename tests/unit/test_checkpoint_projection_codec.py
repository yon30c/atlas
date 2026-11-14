"""Tests for strict, versioned ME-03 checkpoint projection persistence."""
from datetime import datetime, timezone
import json
import unittest

from atlas.core.errors import ContractError
from atlas.memory.consistency import (
    AuthorityKind,
    AuthorityRevision,
    AuthorizationRevisionSet,
    ReadAdmissionStatus,
)
from atlas.memory.journal_reducer import (
    AdmissionProjection,
    ConsistencyProjection,
    EndpointProjection,
    EndpointProjectionStatus,
    ForgetProjection,
    IdempotencyProjection,
    InvalidationProjection,
    RecoveryProjection,
)
from atlas.memory.local_auth import canonical_json_bytes
from atlas.memory.models import MemoryScopeKind
from atlas.memory.checkpoint_projection_codec import (
    build_checkpoint_projection_artifacts,
    decode_checkpoint_projection_artifacts,
    decode_manifest,
    decode_projection,
    encode_manifest,
    encode_projection,
)


NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


def sample_projection() -> ConsistencyProjection:
    revisions = AuthorizationRevisionSet(
        memory_revision=AuthorityRevision(AuthorityKind.MEMORY, "memory-1", 2),
        version_revision=AuthorityRevision(AuthorityKind.MEMORY_VERSION, "version-1", 3),
        identity_revision=AuthorityRevision(AuthorityKind.IDENTITY, "identity-1", 4),
    )
    endpoint = EndpointProjection(
        endpoint_id="endpoint-1",
        last_emission_sequence=5,
        status=EndpointProjectionStatus.OPEN,
        receipt_ids=frozenset({"receipt-b", "receipt-a"}),
    )
    admission = AdmissionProjection(
        admission_id="admission-1",
        operation_id="operation-1",
        memory_id="memory-1",
        version_id="version-1",
        snapshot_id="snapshot-1",
        owner_id="owner-1",
        scope_kind=MemoryScopeKind.PRIVATE,
        scope_project_id=None,
        admitted_at=NOW,
        recoverable=True,
        generation=2,
        revisions=revisions,
        route_ids=frozenset({"route-b", "route-a"}),
        status=ReadAdmissionStatus.ACTIVE,
        terminal_receipt_id=None,
        terminal_operation_id=None,
        terminal_generation=None,
        endpoints=(endpoint,),
    )
    return ConsistencyProjection(
        domain_id="atlas-main",
        authority_epoch=3,
        head_sequence=12,
        admissions=(admission,),
        forget_closures=(
            ForgetProjection(
                operation_id="forget-1",
                memory_id="memory-2",
                generation=1,
                affected_admission_ids=frozenset({"admission-2"}),
                route_ids=frozenset({"route-1"}),
                suppressed=True,
            ),
        ),
        invalidations=(
            InvalidationProjection(
                operation_id="invalidate-1",
                authority_kind=AuthorityKind.IDENTITY,
                authority_id="identity-1",
                generation=2,
                previous_revision=4,
                new_revision=5,
                affected_admission_ids=frozenset({"admission-1"}),
                route_ids=frozenset({"route-a"}),
                reconciled=True,
            ),
        ),
        idempotency_records=(
            IdempotencyProjection(
                idempotency_key="idem-1",
                operation_id="operation-1",
                record_id="record-1",
            ),
        ),
        receipt_ids=frozenset({"receipt-a", "receipt-b"}),
        recovery_closures=(
            RecoveryProjection(
                operation_id="recovery-1",
                generation=2,
                affected_admission_ids=frozenset({"admission-1"}),
                route_ids=frozenset({"route-a"}),
                reconciled=True,
                terminal_receipt_id="terminal-1",
            ),
        ),
        emission_ids=frozenset({"emission-1", "emission-2"}),
        replay_metadata_version=1,
    )


class CheckpointProjectionCodecTests(unittest.TestCase):
    def setUp(self):
        self.projection = sample_projection()

    def test_projection_round_trip_preserves_nested_types_and_values(self):
        encoded = encode_projection(self.projection)
        decoded = decode_projection(encoded)
        self.assertEqual(decoded, self.projection)
        self.assertIsInstance(decoded.admissions[0].admitted_at, datetime)
        self.assertIsInstance(decoded.admissions[0].status, ReadAdmissionStatus)
        self.assertIsInstance(decoded.admissions[0].route_ids, frozenset)
        self.assertIsInstance(decoded.admissions[0].endpoints, tuple)
        self.assertIsInstance(decoded.admissions[0].revisions.memory_revision, AuthorityRevision)

    def test_codec_rejects_projection_with_unsupported_replay_metadata(self):
        from dataclasses import replace

        with self.assertRaises(ContractError):
            encode_projection(replace(self.projection, replay_metadata_version=0))

    def test_codec_rejects_unknown_wrapper_fields(self):
        document = json.loads(encode_projection(self.projection))
        document["unexpected"] = True
        with self.assertRaises(ContractError):
            decode_projection(canonical_json_bytes(document))

    def test_codec_rejects_duplicate_json_keys(self):
        raw = (
            b'{"format":"atlas-consistency-projection",'
            b'"format":"atlas-consistency-projection",'
            b'"format_version":1,"projection":{}}'
        )
        with self.assertRaises(ContractError):
            decode_projection(raw)

    def test_codec_rejects_noncanonical_json_bytes(self):
        with self.assertRaises(ContractError):
            decode_projection(encode_projection(self.projection) + b" ")

    def test_manifest_round_trip_is_canonical(self):
        artifacts = build_checkpoint_projection_artifacts(
            self.projection,
            checkpoint_id="checkpoint-1",
            schema_version=1,
            reducer_version="reducer-v1",
            trust_policy_version="local-policy-v1",
        )
        self.assertEqual(decode_manifest(artifacts.manifest_bytes), artifacts.manifest)
        self.assertEqual(artifacts.manifest.state_reference, artifacts.state_reference)

    def test_artifacts_bind_projection_and_manifest_separately(self):
        artifacts = build_checkpoint_projection_artifacts(
            self.projection,
            checkpoint_id="checkpoint-1",
            schema_version=1,
            reducer_version="reducer-v1",
            trust_policy_version="local-policy-v1",
        )
        projection, manifest, integrity_commitment = decode_checkpoint_projection_artifacts(
            artifacts.state_bytes,
            artifacts.manifest_bytes,
            expected_state_reference=artifacts.state_reference,
            expected_integrity_reference=artifacts.integrity_reference,
        )
        self.assertEqual(projection, self.projection)
        self.assertEqual(manifest, artifacts.manifest)
        self.assertEqual(integrity_commitment, artifacts.integrity_commitment)
        self.assertNotEqual(artifacts.state_commitment, artifacts.integrity_commitment)
        self.assertTrue(artifacts.state_reference.startswith("sha256:"))
        self.assertTrue(artifacts.integrity_reference.startswith("sha256:"))

    def test_artifact_decoder_rejects_state_tampering(self):
        artifacts = build_checkpoint_projection_artifacts(
            self.projection,
            checkpoint_id="checkpoint-1",
            schema_version=1,
            reducer_version="reducer-v1",
            trust_policy_version="local-policy-v1",
        )
        changed = self.projection.__class__(
            **{
                **{
                    field: getattr(self.projection, field)
                    for field in self.projection.__dataclass_fields__
                },
                "head_sequence": 13,
            }
        )
        with self.assertRaises(ContractError):
            decode_checkpoint_projection_artifacts(
                encode_projection(changed),
                artifacts.manifest_bytes,
                expected_state_reference=artifacts.state_reference,
                expected_integrity_reference=artifacts.integrity_reference,
            )

    def test_artifact_decoder_rejects_manifest_tampering(self):
        artifacts = build_checkpoint_projection_artifacts(
            self.projection,
            checkpoint_id="checkpoint-1",
            schema_version=1,
            reducer_version="reducer-v1",
            trust_policy_version="local-policy-v1",
        )
        document = json.loads(artifacts.manifest_bytes)
        document["trust_policy_version"] = "different-policy"
        changed_manifest = canonical_json_bytes(document)
        with self.assertRaises(ContractError):
            decode_checkpoint_projection_artifacts(
                artifacts.state_bytes,
                changed_manifest,
                expected_state_reference=artifacts.state_reference,
                expected_integrity_reference=artifacts.integrity_reference,
            )


if __name__ == "__main__":
    unittest.main()
