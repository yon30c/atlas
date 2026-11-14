# ME-03F — Journal schema v2 for exact admission recovery

**Status:** design proposal, pending implementation and acceptance validation.  
**Scope:** consistency journal envelope, reducer projection, and recovery contracts only.  
**Normative basis:** CT-04 Events, CT-05 Memory, DM-01 domain model, ME-03 read consistency, ME-03C reducer/recovery, and ME-03E integration/validation.  
**Non-goals:** choosing a database, journal product, transport, storage adapter, backup policy, cryptographic algorithm, or enabling production reads/Forget.

## 1. Problem statement

The current `READ_ADMITTED` transition records memory/version IDs, snapshot ID, authorization revisions, actor identity, owner (optional today), admission ID, generation, and route IDs. It does not persist the canonical memory scope.

The reducer therefore cannot reconstruct the exact `ReadTarget` required by `ReadAdmission`: `ReadTarget(memory_id, version_id, owner_id, scope)`. Inferring PRIVATE versus PROJECT from context, actor, revisions, or project metadata would be unsafe. The current recovery fake correctly refuses to restore any nonterminal admission rather than silently losing it.

The reducer also currently projects endpoint sequence/receipt state, but does not retain the admission's final reconciliation receipt as a dedicated projection field. A recoverable projection must preserve both endpoint-level evidence references and the exact terminal evidence reference.

## 2. Decision: introduce schema version 2

Add schema version 2 for `READ_ADMITTED`. Keep version 1 readable for historical replay and audit, but classify any v1 admission as **not recoverable for live admission restoration** because its target scope cannot be reconstructed exactly.

Unknown schema versions remain rejected. No implicit upgrade or default scope is permitted.

### 2.1 Additional v2 fields

Add the following closed fields to the `READ_ADMITTED` v2 allowlist:

| Field | Type | Requirement | Purpose |
|---|---|---|---|
| `scope_kind` | `MemoryScopeKind` | required | Exact PRIVATE/PROJECT discriminator |
| `scope_project_id` | opaque string or null | conditional | Canonical project identifier for PROJECT |

Existing fields are tightened for v2:

- `owner_id` is required and must be non-empty.
- `actor_identity_id` is required and must match `revisions.identity_revision.authority_id`.
- `request_id` is required and non-empty.
- `memory_id`, `version_id`, `snapshot_id`, `revisions`, `admission_id`, `generation`, and non-empty `route_ids` remain required.
- `occurred_at` is the authoritative `admitted_at`; do not duplicate timestamps.
- `subject_user_id` remains optional for PROJECT agent actors and is required/equal to owner for PRIVATE.

### 2.2 Scope validation

- PRIVATE: `scope_kind=PRIVATE`, `scope_project_id=None`, `subject_user_id=owner_id`, and project/environment/Grant revisions must be absent.
- PROJECT: `scope_kind=PROJECT`, `scope_project_id` is non-empty and exactly equals `revisions.project_revision.authority_id`; project, environment and Grant revisions must all exist. Subject may be absent for an agent actor.
- Any contradictory, incomplete, unknown, or wrongly typed scope data rejects the transition.
- `scope_project_id` is an opaque project ID, never a URL or user-provided substitute.

These constraints mirror the existing `MemoryScope` and `AuthorizationSnapshot` invariants; the journal does not become a source of canonical authorization truth.

## 3. Compatibility and reducer behavior

1. `SUPPORTED_CONSISTENCY_SCHEMA_VERSIONS` accepts 1 and 2.
2. The v1 field allowlist and validation semantics remain frozen. Existing v1 fixtures and historical records continue to parse.
3. The reducer creates an admission projection for v1 with an explicit non-recoverable marker and no reconstructed scope. It must not infer scope.
4. The reducer creates a recoverable target projection for v2 only after validating all v2 scope invariants.
5. Mixed v1/v2 journals are replayable in sequence. A v1 nonterminal admission blocks full authority recovery until it is independently fenced/reconciled using verifiable endpoint evidence; it cannot be dropped.
6. Checkpoint compatibility is unchanged: no checkpoint is accepted without a loaded, integrity-verified base projection. Schema migration does not relax checkpoint requirements.

## 4. Projection contract

Extend `AdmissionProjection` with the minimum exact reconstruction fields:

- `owner_id`;
- `scope_kind` and `scope_project_id` (nullable only for PRIVATE);
- `admitted_at` derived from the READ_ADMITTED `occurred_at`;
- a boolean/closed recovery classification that distinguishes reconstructable v2 from historical/incomplete v1;
- `terminal_receipt_id` for the admission-level `ADMISSION_RECONCILED` receipt.

Retain existing exact fields: admission/operation IDs, memory/version/snapshot IDs, generation, revisions, route inventory, admission status, endpoint IDs, last emission sequence, endpoint status, emission receipt IDs, and endpoint terminal receipt IDs.

Projection remains metadata-only. It must not contain memory content, fragments, payload, derived content, content hashes, authorization secrets, or bearer capabilities.

## 5. Recovery semantics

### 5.1 Reconstructable v2 admissions

A recovery adapter may reconstruct a typed `ReadTarget` only from a recoverable v2 projection:

- create `MemoryScope(PRIVATE)` for the validated PRIVATE tuple;
- create `MemoryScope(PROJECT, project_id)` for the validated PROJECT tuple;
- construct target using the exact memory ID, version ID, owner ID and scope;
- use `admitted_at` from the journal record;
- preserve the exact configured route inventory and generation.

A v2 record is necessary but not sufficient for recovery. The recovery authority must still verify journal authenticity, the continuity available under the selected profile, current authority revisions, suppression state, and every endpoint receipt before opening any delivery path. Local verification does not prove external anti-rollback or that a coherent restored journal is the latest state. External Trust Anchor verification is optional and deferred to Atlas's final project stage.

### 5.2 Old emitters and nonterminal admissions

After process recovery, a previously ADMITTED/ACTIVE/UNRESOLVED admission must not be resumed as an ordinary live emitter. It is restored as unresolved/fenced work:

- gate remains closed for that admission;
- old generation/capability cannot emit;
- every endpoint in the persisted route inventory must be independently verified as terminal or fenced;
- the fencing receipt must bind admission, endpoint, old generation, new generation, receipt identity and terminal result;
- only after all endpoints are verified may the admission be reconciled to CANCELLED (or COMPLETED where a verifiable completion was already committed before recovery).

A local lease timeout or journal receipt ID alone is not proof that a remote endpoint stopped.

### 5.3 Terminal admissions

COMPLETED/CANCELLED can be restored only when the reducer has a matching admission terminal receipt and every registered endpoint has a matching verified terminal receipt with sequence consistency. Missing, duplicated, contradictory or unverifiable receipts leave the admission unresolved and the gate closed.

### 5.4 Fresh authorization before any new content

Restoring metadata does not restore the old CAM decision as current authorization. Any future content read requires a fresh CAM decision and a new admission under the current authority generation/revisions. Recovery of old admissions is for safely closing/reconciling prior delivery work, not for reviving old read capabilities.

## 6. Receipt verification boundary

Add a typed verification port in a later implementation stage; the reducer itself remains a pure structural/semantic validator.

The verifier must validate, at minimum:

- receipt issuer/endpoint identity and trust status;
- exact admission ID, operation ID, endpoint ID, generation and receipt ID;
- emission sequence or final sequence and monotonicity;
- terminal outcome (completed versus fenced);
- binding to the journal record and consistency domain/epoch;
- duplicate/replay detection and revocation/expiry of the verifier's trust material.

If verification is unavailable, times out, returns an unknown result, or contradicts the journal, the result is unresolved and recovery remains fail-closed. Do not treat an opaque `receipt_id` as proof.

## 7. Acceptance scenarios

Add tests before implementing recovery:

- F01: v2 PRIVATE record accepts exact owner-bound scope and no project ID.
- F02: v2 PROJECT record accepts exact project ID matching project revision.
- F03: reject PRIVATE with project ID, non-owner subject, or project/environment/Grant revisions.
- F04: reject PROJECT with missing project ID/revisions or mismatched project revision authority ID.
- F05: reject missing owner, actor identity, request ID, or scope kind in v2.
- F06: v1 remains parseable but its admission projection is explicitly non-recoverable.
- F07: mixed v1/v2 replay retains both admissions and blocks recovery if the v1 admission is nonterminal.
- F08: projection preserves admitted_at, owner, scope, route inventory and terminal admission receipt.
- F09: reconstruction creates exactly the original PRIVATE ReadTarget.
- F10: reconstruction creates exactly the original PROJECT ReadTarget.
- F11: no scope is inferred from project/environment/Grant revisions when scope fields are absent.
- F12: a v2 nonterminal admission restores closed/unresolved, never ACTIVE.
- F13: missing endpoint receipt prevents terminal restoration.
- F14: duplicate or contradictory endpoint receipt prevents restoration.
- F15: endpoint receipt with wrong generation/admission/route/sequence is rejected.
- F16: unverified receipt ID alone cannot terminalize an admission.
- F17: old emitter/capability cannot emit after recovery.
- F18: fresh content delivery requires a new CAM decision and admission.
- F19: projection contains no payload/content/hash/capability fields.
- F20: unknown schema version remains rejected.
- F21: checkpoint without verified base remains rejected after schema migration.

## 8. Implementation sequence

1. Add v2 fields and version-aware allowlists/validation in `journal.py`; preserve v1 semantics.
2. Extend reducer projections with exact scope/owner/admitted_at/recovery classification and admission terminal receipt.
3. Add v1/v2, PRIVATE/PROJECT, malformed/mixed-journal tests (F01–F08, F11, F19–F21).
4. Add a pure reconstruction function for `ReadTarget`/recovery metadata, not a delivery-capable session.
5. Define the receipt-verification port and deterministic fake; verify endpoint evidence before terminal restoration.
6. Extend the fake authority to restore unresolved endpoint state and prove stale emitters are rejected (F12–F18).
7. Run the full Python 3.10–3.13 CI matrix and update ME-03E with exact outcomes.

Do not combine this work with real persistence, anti-rollback cryptography, network transports, physical deletion, or production activation.

## 9. Explicit limitations

This design does not establish durable storage, authenticated journal origin, external anti-rollback, distributed consensus, atomic network egress, endpoint liveness, complete delivery-route inventory, backup/restore policy, or physical Forget. External anti-rollback via Trust Anchor is optional and deferred to Atlas's final project stage. A passing fake/test suite will validate the model and integration contract only, not those runtime guarantees.

## 10. Implementation tracking

**Implemented and CI-validated (partial):**
- schema v2 for `READ_ADMITTED`, with frozen v1 compatibility and strict PRIVATE/PROJECT scope validation;
- projection of owner, scope, admitted_at, recoverability marker and admission terminal receipt;
- pure `reconstruct_read_target()` that refuses v1/incomplete projections;
- 19 focused tests across schema validation and reducer projection/reconstruction.

**Still pending:**
- recovery classification for mixed v1/v2 journals with unresolved v1 admissions;
- reconstruction of endpoint/admission lifecycle state as unresolved/fenced after restart;
- receipt verification port and verifier fake;
- validation of endpoint issuer, generation, sequence, operation and receipt bindings;
- stale-emitter rejection after recovery;
- tests F12–F18 and full adapter/runtime validation.

CI for the implemented portion: [Atlas CI #43529942908](https://github.com/yon30c/atlas/actions/runs/43529942908), all four Python versions successful.

This tracking note does not change the design's non-goals or imply durable recovery.


## 11. Decisión posterior — Trust Anchor opcional

**APROBADO — 13 de noviembre de 2026.** La recuperación de admisiones en el baseline local debe verificar la continuidad interna disponible, revisiones de autoridad, supresión y recibos de endpoints. No puede afirmar anti-rollback externo. El proveedor Trust Anchor y las pruebas de restauración frente a un ancla externa quedan postergados hasta la etapa final. No se reanudan emisores antiguos ni se abren rutas con inventarios, recibos o resultados ambiguos incompletos.
