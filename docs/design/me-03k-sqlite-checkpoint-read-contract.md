# ME-03K — SQLite checkpoint recovery read contract

**Status:** implementation on `feature/me-03k-local-profile`; pending owner-run validation.  
**Scope:** structural reconstruction of the latest local checkpoint and its journal suffix, followed by the existing independent checkpoint-projection verifier.  
**Non-goals:** checkpoint creation/commit API, checkpoint projection storage adapter, external Trust Anchor, anti-rollback guarantees, production activation, schema migration.

## 1. Sequence model

A checkpoint has two distinct positions:

1. `ConsistencyCheckpoint.position.sequence` identifies the journal position represented by the base projection.
2. Its `CHECKPOINT_COMMITTED` marker is a journal entry at the immediately following sequence.

For checkpoint position `N`, the durable journal must contain the matching marker at `N + 1`. The marker must bind:
- `record_id == checkpoint_id`;
- `operation_id == "checkpoint:" + checkpoint_id`;
- `checkpoint_reference == state_reference`;
- `occurred_at == checkpoint.created_at`.

The checkpoint envelope is an independently authenticated replay root. Its `previous_commitment` is null; the first journal entry after it must link to its `object_commitment`. This does not claim that the omitted prefix is anti-rollback protected. The projection port must independently resolve and verify the base state.

## 2. Structural SQLite read

The adapter reads the domain, checkpoint rows, journal suffix, and operation-resolution rows inside one SQLite read transaction.

When no checkpoint exists:
- the full journal must begin at sequence 1;
- a checkpoint marker without a checkpoint row is rejected;
- the previous-commitment chain begins at null.

When checkpoints exist:
- the latest checkpoint for the exact domain and authority epoch is selected;
- its position must precede the current head;
- its envelope and canonical checkpoint payload must agree structurally;
- the suffix begins at checkpoint sequence + 1;
- the first suffix entry must be the exact matching checkpoint marker;
- no unrepresented checkpoint marker may occur later in the suffix;
- journal and operation rows must form an exact one-to-one, contiguous suffix through the persisted head;
- each suffix transition must round-trip through canonical serialization;
- each operation row must match its semantic request projection and digest;
- each entry envelope's object commitment and predecessor commitment must match the canonical payload and preceding checkpoint/entry commitment;
- the final suffix commitment must equal the domain's persisted head commitment.

The reader does not load or trust the pre-checkpoint journal prefix. The independently verified checkpoint projection replaces that prefix for semantic replay.

Malformed or contradictory persisted state returns `REJECTED`. Missing domain or SQLite read failure returns `UNAVAILABLE`. No partial recovery state is returned.

## 3. Trust and replay boundary

Structural loading produces only `ConsistencyRecoveryState`; it does not authenticate HMACs or grant recovery authority.

Operational recovery remains gated by `LocalConsistencyRecoveryVerifier`:
1. verify checkpoint and suffix envelopes under the configured local trust policy and historical key port;
2. request the base projection from the explicitly configured `LocalConsistencyCheckpointProjectionPort`;
3. accept the projection only through `require_verified_checkpoint_projection`;
4. call `reduce_from_projection()` only after those checks;
5. verify external inventories against the exact recovered head;
6. expose local verified evidence only if every required step succeeds.

A missing projection port or unavailable projection source remains `UNAVAILABLE`. A rejected projection or mismatch remains `REJECTED`. The SQLite `checkpoint_projections` table is not itself a trust authority; a row in the restored database cannot self-attest as `VERIFIED`.

## 4. Deliberate limitations

- `SQLiteConsistencyJournal` still has no durable `commit_checkpoint()` implementation. The current work adds the read path only.
- No migration was added; schema v1-v3 remain unchanged.
- The projection port must be composed from an independent trusted source. A future SQLite-backed projection adapter must not claim independence merely because it reads a second table in the same restored database.
- A locally authenticated checkpoint does not prove that a restored backup contains the latest checkpoint or latest head. No external anti-rollback protection is claimed.
- Trust Anchor integration remains deferred.

## 5. Validation cases added

- successful structural checkpoint reconstruction and suffix-only loading;
- rejection when the checkpoint state reference no longer matches its commit marker;
- rejection when the checkpoint commit marker is missing;
- rejection when a marker exists without a checkpoint row;
- successful verified recovery through the configured checkpoint projection port, followed by replay and inventory verification.

These tests require owner-run execution on Debian. No tests, deployment, service restart, Docker operation, or production mutation are performed by this change.
