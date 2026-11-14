# ME-03H — Recovery of unresolved admissions after process restart

**Status:** recovery-plan and endpoint-fencing orchestration contract; deterministic validation only.  
**Normative basis:** CT-04, CT-05, ME-03, ME-03C, ME-03E, ME-03F and ME-03G.  
**Non-goals:** durable journal adapter, process supervisor, network transport, cryptographic implementation, production recovery or Forget completion.

## 1. Recovery must not resume an old read

After a process restart, no prior read capability, in-memory session, or emitter is restored. Every nonterminal admission is recovered as unresolved work. Its prior endpoints are treated as potentially live, even if the last journal projection shows an endpoint as open or contains an unverified terminal receipt.

The recovery authority must close the consistency domain before accepting new reads or emissions. It must establish a strictly newer fencing generation than every generation in the recovered projection. The generation must be allocated by the consistency authority; a caller cannot choose an arbitrary value in production.

## 2. Preserve every unresolved admission

The recovery plan includes every admission whose reducer status is not COMPLETED or CANCELLED, including schema-v1 admissions.

- v2: exact target metadata may be reconstructed with `reconstruct_read_target()`, but it is not an authorization or content capability.
- v1: target remains unavailable; no PRIVATE/PROJECT scope is inferred.
- Both versions retain admission ID, old generation, route inventory and endpoint sequence metadata.
- No admission or endpoint may be dropped because its target is unavailable.

All persisted endpoints are fenced again under the new generation. Historical endpoint receipts are not used to skip fencing in this stage. This deliberately favors safety over avoiding duplicate endpoint coordination.

## 3. Recovery fence plan

The pure plan binds:
- consistency domain and authority epoch;
- unique recovery operation ID;
- new generation;
- every unresolved admission and its old generation;
- exact endpoint route inventory and last committed sequence.

For each endpoint, the fencer receives an exact request binding domain/epoch, operation, admission, endpoint, old generation, new generation, and last committed sequence. The endpoint receipt and independent verifier must bind the exact last committed sequence covered by the fence. The request contains no content or capability.

The plan is metadata only. It does not mark any admission terminal and does not open the gate.

## 4. Endpoint fencing and verification

Each endpoint must return a positive receipt bound to the exact request. A negative, missing, malformed, mismatched, timed-out or unknown result leaves the entire recovery operation unresolved.

The coordinator then asks the independent ME-03G verifier to verify an `ENDPOINT_FENCED` receipt bound to:
- domain and epoch;
- recovery operation and admission;
- endpoint ID;
- previous and new generations;
- receipt ID.

No endpoint is considered fenced based on a local timeout, a boolean alone, a journal receipt ID, or a successful request dispatch.

The verified batch is returned only when every endpoint of every unresolved admission has independently verified fencing evidence. Partial evidence may be retained in a future durable adapter, but this pure stage returns no completed batch on partial failure.

## 5. Reconciliation boundary

A verified batch is evidence for a later atomic journal/authority operation. The production authority must:
1. confirm the recovery closure and new generation are durably committed before contacting endpoints;
2. verify the complete route inventory against the trusted endpoint registry;
3. append every verified endpoint fence receipt idempotently;
4. append admission reconciliation only after all endpoints for that admission are terminal;
5. keep the domain gate closed until all unresolved admissions are reconciled and the recovery operation itself is durably finalized;
6. reject old generation/capability emissions at the egress commit point.

The pure journal model now includes `RECOVERY_CLOSED` and `RECOVERY_RECONCILED` transitions. The reducer marks every captured admission UNRESOLVED at closure, rejects egress and new admissions while recovery is pending, accepts endpoint fencing only for the exact recovery operation/new generation, and reconciles the domain only after every affected admission is terminal. This does not implement a durable journal adapter or an atomic authority coordinator.

## 6. Fail-closed behavior

- recovery generation is not strictly newer than all recovered generations;
- missing or duplicate admission/endpoint IDs;
- missing or inconsistent route inventory;
- unknown/unrecoverable journal continuity;
- any v1 or v2 admission omitted from the plan;
- fencer absent, exception, timeout, or malformed receipt;
- endpoint/admission/operation/domain/epoch/generation mismatch;
- verifier unavailable, rejected, malformed or mismatched;
- any partial endpoint verification.

The consistency domain remains closed in all such cases.

## 7. Acceptance scenarios

- H01 every nonterminal v1 and v2 admission appears in the plan;
- H02 v1 target remains unavailable; no scope inference;
- H03 v2 target may be reconstructed as metadata only;
- H04 every persisted route appears exactly once;
- H05 recovery generation exceeds every unresolved admission generation and prior closure generation;
- H06 stale/invalid generation rejected;
- H07 every endpoint receives a new-generation fence request;
- H08 prior terminal receipts do not bypass fresh fencing;
- H09 wrong endpoint/admission/operation/generation receipt rejected;
- H10 missing endpoint receipt prevents batch;
- H11 verifier REJECTED/UNAVAILABLE/exception prevents batch;
- H12 partial success does not produce a verified batch;
- H13 no read capability or content handle is created;
- H14 old generations are never restored as active;
- H15 verified batch is not itself an admission reconciliation or gate-opening command.

## 8. Limits and next integration work

A deterministic fencer/verifier validates only the orchestration contract. Real endpoint identity, trust, process termination/fencing, durable idempotency, journal append, anti-rollback, atomic domain closure, crash recovery and egress enforcement remain unproven. No production read or Forget operation may rely on this stage alone.


## 9. Initial pure implementation and validation

Implemented:
- metadata-only recovery plan that includes every nonterminal admission, including legacy v1 projections;
- exact v2 `ReadTarget` reconstruction where available, while v1 target remains `None` and is never inferred;
- exact per-admission endpoint inventory and last committed sequence;
- strictly newer recovery generation check against all admission and prior closure/invalidation generations;
- endpoint fence requests bound to domain, epoch, recovery operation, admission, endpoint, old/new generation and last committed sequence;
- raw endpoint receipt validation followed by independent ME-03G verification;
- all-or-nothing `VerifiedRecoveryFenceBatch`; missing, mismatched, rejected, unavailable, timed-out or partial results produce no batch;
- no read capability, content handle, admission terminalization or gate-opening action is created.

The ME-03G receipt contract was strengthened so an `ENDPOINT_FENCED` receipt must bind `fenced_through_sequence`. This prevents accepting a fence that advances generation but does not attest the last sequence already committed by the endpoint.

Tests:
- 25 focused tests in `tests/unit/test_memory_unresolved_admission_recovery.py`, including journal reducer closure/reconciliation cases;
- fake-authority recovery test in `tests/unit/test_memory_consistency_authority.py`: restored admission is UNRESOLVED, old-generation emission is rejected, new reads remain blocked until every endpoint acknowledges fencing, and only then can a fresh admission use the new generation;
- ME-03G terminal receipt tests updated for fenced-through sequence binding.

**Important boundary:** this is still a pure/model and fake-verifier stage. The reducer can replay recovery closure and reconciliation records, but no durable authority currently commits `RECOVERY_CLOSED` before endpoint contact, and no production coordinator appends the endpoint/admission receipts. The next integration slice must connect the verified batch to an atomic journal/authority workflow and prove that the journal receipt IDs, verifier evidence and authority acknowledgements are committed together before the recovery gate opens. No production admission is marked CANCELLED by this implementation.


## 10. ME-03I — Coordinador journal-first

El coordinador `RecoveryJournalCoordinator` ahora exige que el cierre del gate y el registro `RECOVERY_CLOSED` se realicen mediante `RecoveryGatePort.close_recovery_gate`, una única operación lógica serializada con admisión y egress. En una reanudación, `ensure_recovery_gate_closed` debe restaurar y confirmar el cierre exacto antes de contactar endpoints.

Cada recibo de endpoint verificado se registra inmediatamente como `ENDPOINT_FENCED`. Si el proceso cae, la proyección permite omitir los endpoints ya registrados y continuar con los pendientes. Si un endpoint fue cercado pero el append no llegó a confirmarse, el adaptador debe soportar repetición idempotente de la misma solicitud.

La prueba de reinicio usa fakes y confirma que el gate se restaura antes de contactar el endpoint pendiente. El coordinador nunca marca las admisiones como CANCELLED ni abre el gate: incluso cuando todos los fences están registrados, el resultado es solo `FENCING_RECORDED`.

Ver diseño: `docs/design/me-03i-journal-first-recovery-coordinator-design.md`.

CI de pruebas de coordinación: [Atlas CI #43533291237](https://github.com/yon30c/atlas/actions/runs/43533291237), Python 3.10–3.13: éxito.

**Límite:** todavía no hay adaptadores durables ni una implementación real de `RecoveryGatePort`. El gate y journal coordinados se validan únicamente con fakes de proceso único.
