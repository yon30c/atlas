# ME-03K — Durable SQLite checkpoint write contract

**Status:** design contract; implementation not started.  
**Target branch:** `feature/me-03k-local-profile`.  
**Scope:** atomically persist an authenticated checkpoint and its matching journal marker, preserving the read contract in `me-03k-sqlite-checkpoint-read-contract.md`.  
**Non-goals:** schema migration unless implementation proves the existing schema insufficient; external Trust Anchor; anti-rollback guarantees; production activation; Broker changes.

## 1. Purpose and invariants

The writer turns a verified, durable projection of the current consistency state into a new local replay root.

A successful checkpoint operation MUST guarantee all of the following:

1. The checkpoint describes exactly the current persisted journal head at sequence `N`.
2. The base projection is durable and independently verifiable before the SQLite checkpoint transaction begins.
3. The checkpoint payload is canonicalized and committed by a locally authenticated envelope.
4. The matching `CHECKPOINT_COMMITTED` journal marker is committed in the same SQLite transaction as the checkpoint row.
5. The marker is at sequence `N + 1` and its predecessor commitment is the checkpoint envelope commitment.
6. The domain head advances atomically from `N` to `N + 1`, with the marker commitment as the new head commitment.
7. Any failure before transaction commit leaves neither a visible checkpoint row nor a visible marker nor an advanced head.
8. A retry after an uncertain outcome can determine whether the exact checkpoint was committed without creating a second marker.
9. The existing read contract can reconstruct the latest checkpoint and its contiguous suffix without schema changes.

A checkpoint is a local authenticated replay root. It is not an external anti-rollback anchor and MUST NOT be described as protection against restoring an older coherent database backup.

## 2. Trusted input boundary

The public write operation MUST NOT accept caller-supplied strings as sufficient proof of a checkpoint projection.

Its projection input MUST be the existing typed, independently verified checkpoint-projection value accepted by the recovery boundary (the same trust boundary used by `require_verified_checkpoint_projection`). The implementation must inspect and reuse the actual type and port already present in the branch; it must not create a second, weaker "verified" type.

Before any persistence, the writer MUST establish that:

- the projection belongs to the requested consistency domain and authority epoch;
- the projection represents exactly the current journal head position `N`;
- its state and inventory commitments are internally consistent under the existing projection verifier;
- the projection has been durably stored by the configured independent projection port;
- reading the projection back by its opaque reference yields the same verified projection.

The projection store MUST be independent of the SQLite database being checkpointed. A second table in the same SQLite file is not an independent recovery source. The existing `checkpoint_projections` table MUST NOT be treated as authority merely because it contains a row.

The SQLite writer may persist opaque `state_reference` and `integrity_reference` values, but it MUST NOT persist memory content, projection payloads, secrets, or credentials in the journal checkpoint row.

## 3. Sequence and commitment model

Let the persisted domain head before checkpointing be `N`, with prior head commitment `H_N`.

The checkpoint represents `ConsistencyPosition(domain, epoch, N)`.

The writer constructs the checkpoint payload from:

- `checkpoint_id`;
- position `(domain, epoch, N)`;
- opaque `state_reference`;
- opaque `integrity_reference`;
- `created_at` in UTC.

The checkpoint envelope MUST have:

- `object_kind = "checkpoint"`;
- `object_id = checkpoint_id`;
- sequence `N`;
- the configured schema, reducer, issuer, role, key reference and trust-policy metadata;
- `previous_commitment = null`;
- `object_commitment = SHA256(canonical_json_bytes(checkpoint_payload))`;
- HMAC evidence produced by the configured signer.

The marker MUST be a `ConsistencyTransition` with:

- `record_id = checkpoint_id`;
- `record_kind = CHECKPOINT_COMMITTED`;
- `operation_id = "checkpoint:" + checkpoint_id`;
- `checkpoint_reference = state_reference`;
- `occurred_at = checkpoint.created_at`.

The marker position is `(domain, epoch, N + 1)`. Its envelope MUST use the checkpoint envelope commitment as `previous_commitment`, and its object commitment MUST be calculated from the canonical journal-entry payload.

The final persisted domain head is therefore:

- `head_sequence = N + 1`;
- `head_commitment = marker_envelope.object_commitment`.

The previous journal prefix ending at `H_N` is intentionally replaced as the replay chain root. The independently verified projection represents that prefix. Do not chain the marker to `H_N`: the read contract requires the checkpoint envelope to be an independent root and the first suffix entry to link to the checkpoint commitment.

## 4. SQLite transaction boundary

The operation MUST use the existing `SQLiteDatabase.write_transaction()` and its `BEGIN IMMEDIATE` writer serialization.

Within one transaction, the implementation MUST:

1. Read the domain row and validate local profile, authority epoch and configured trust-policy version.
2. Validate that the current head still equals the projection's expected position `N`.
3. Resolve an existing checkpoint operation by its stable checkpoint identity before attempting a new append.
4. Construct and sign the checkpoint envelope.
5. Construct and sign the marker envelope with the checkpoint commitment as predecessor.
6. Insert the checkpoint row.
7. Insert the marker journal row at `N + 1`.
8. Insert the matching journal-operation resolution row, with canonical request bytes and digest consistent with K01.
9. Advance the domain head using a conditional update requiring the previous head sequence `N`.
10. Require exactly one affected row and commit.

The checkpoint row, marker row, operation row and domain-head update MUST be in the same transaction. A uniqueness, foreign-key, signing, serialization or conditional-update failure MUST roll back all of them.

The writer MUST NOT call the ordinary `append_transition()` after inserting the checkpoint. That method chains a normal entry from the existing head commitment; the checkpoint marker has the different predecessor rule above. The checkpoint operation therefore needs a dedicated transaction path or a carefully factored internal append primitive that accepts the authenticated predecessor explicitly and cannot be called with an arbitrary predecessor by external callers.

No write may occur before the projection has passed independent verification and durable read-back.

## 5. Idempotency and uncertain outcomes

The checkpoint identity is stable across retries. The marker operation identity remains `checkpoint:<checkpoint_id>`; its journal `append_id` is a distinct append-attempt identifier, consistent with K01's separation of append identity and semantic operation identity.

For an existing checkpoint identity:

- If the stored checkpoint payload, envelope metadata, marker, operation row and final head binding match the exact requested checkpoint, return a replayed/previously-committed result without advancing the head.
- If the identity exists but any semantic field or commitment differs, return CONFLICT/REJECTED. Never overwrite the old checkpoint or append a second marker.
- If the database cannot establish whether the operation committed, return UNKNOWN/UNAVAILABLE. Do not guess and do not create a replacement identity automatically.

After a caller receives an uncertain result, it must resolve using the same checkpoint identity and exact expected semantics. The resolution path must distinguish exact committed, not committed, conflict and unknown outcomes, following the existing typed K01 resolution pattern.

A retry MUST NOT treat a different projection reference, integrity reference, position, timestamp or checkpoint commitment as the same semantic request.

## 6. Ordering across the independent projection store and SQLite

There is no distributed atomic transaction between the independent projection store and SQLite. The safe ordering is:

1. Produce the projection for the exact current head.
2. Persist it immutably in the independent projection store.
3. Read it back and independently verify it.
4. Execute the single SQLite transaction described above.

A crash between steps 2 and 4 may leave an orphan projection. This is acceptable: an unreferenced immutable projection is inert and can be garbage-collected only by a separately designed, conservative retention process.

The reverse order is forbidden. Committing a SQLite checkpoint before the projection is durable could leave a checkpoint that cannot be replayed after a crash.

If SQLite commit succeeds but the process loses the response, the caller resolves the same checkpoint identity. It must not delete the projection or create another checkpoint until the outcome is known.

## 7. Failure classification

The API should expose a typed result with at least these semantic outcomes (names may follow the repository's existing conventions):

- **COMMITTED:** new checkpoint and marker committed atomically.
- **REPLAYED:** exact same checkpoint was already committed.
- **CONFLICT:** checkpoint identity or current head conflicts with the requested operation.
- **UNAVAILABLE / UNKNOWN:** projection store, key custody, SQLite, signer or outcome resolution is unavailable; no success may be inferred.

Malformed input, wrong domain/epoch, unverified projection, invalid commitment, or contradictory persisted rows are rejection/conflict conditions, not successful recovery.

Signer/key failures must preserve the existing distinction: unavailable key material or signer failure is UNAVAILABLE; invalid authenticated evidence is REJECTED. The implementation must not fall back to unsigned writes, generate a replacement key, or silently rotate keys.

## 8. Concurrency and fencing

SQLite `BEGIN IMMEDIATE` serializes local writers. The transaction MUST re-read the head after acquiring the write lock and compare it with the projection's exact expected position. A projection that was current before waiting for the lock may be stale when the lock is acquired; in that case the operation returns CONFLICT and does not write.

The conditional head update is still required as a defensive compare-and-swap invariant. Exactly one row must be updated.

No network call or independent projection-store write should occur while holding the SQLite write transaction. This avoids holding the database writer lock across external latency and prevents an external dependency from creating a long-lived partial transaction.

This contract is single-host SQLite coordination. It does not claim distributed fencing across multiple independent databases or hosts.

## 9. Schema compatibility

The implementation MUST first inspect the existing v1-v3 schema and checkpoint table constraints. It should reuse the current schema if it can persist:

- checkpoint identity, domain, authority epoch and represented sequence;
- state and integrity references;
- creation time;
- complete authenticated envelope fields;
- the matching journal marker and operation-resolution row.

Do not add a migration pre-emptively. If an actual missing field or constraint makes the contract impossible, stop and propose the smallest additive migration separately, including migration checksum and upgrade tests. Never rewrite historical migrations.

## 10. Required tests before owner validation

Add focused tests for:

1. Successful checkpoint commit at head `N`, marker at `N + 1`, checkpoint envelope rooted at null, marker predecessor equal to checkpoint commitment.
2. Existing normal journal prefix is not used as the marker predecessor after checkpoint compaction.
3. Checkpoint row, marker row, operation row and head update are all visible together after commit.
4. Injected failure after each persistence step rolls back every row and leaves the old head unchanged.
5. Signer failure causes no partial persistence.
6. Projection unavailable, unverified, wrong-domain, wrong-epoch, wrong-position or failed read-back causes no SQLite mutation.
7. Concurrent append advances the head after projection creation; checkpoint detects stale position and returns conflict without writing.
8. Exact retry returns REPLAYED and does not advance the head.
9. Same checkpoint identity with changed semantic content returns CONFLICT.
10. Simulated lost response after commit is resolved as exact committed on retry.
11. Marker fields exactly satisfy the existing checkpoint read contract.
12. A subsequent `load_recovery_state_result()` reconstructs the checkpoint and suffix; the existing independent recovery verifier and reducer path can consume the result.
13. No schema migration is needed, or a separately approved minimal migration is fully tested.

All tests are owner-run on Debian. Do not run tests/builds in GitHub or deploy as part of this work.

## 11. Explicit non-claims

This checkpoint writer will provide atomic local persistence and a verified projection-based replay boundary. It will not provide:

- external anti-rollback protection;
- detection of a coherent restoration of an older SQLite backup;
- cross-host consensus or distributed fencing;
- atomic commit across the projection store and SQLite;
- production readiness without owner-run tests and operational review.

Trust Anchor remains a separate later phase.
