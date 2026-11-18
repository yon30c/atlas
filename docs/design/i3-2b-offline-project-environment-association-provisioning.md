# Offline Project/Environment Association Provisioning

**Status:** operational trust boundary approved by the owner; implementation in progress. This document-only approval update does not add code, apply migrations, register runtime capabilities, or modify databases.

## Decision

Initial Project/Environment association creation is an offline, explicit operation controlled by the local platform operator. It is separate from Platform Admin lifecycle authority.

The existing permissions `association.suspend` and `association.reactivate` do not authorize creation. Project ownership, USER authentication, AGENT identity, delegation, ordinary Grants, and caller-supplied context fields are not provisioning authority.

## Trust boundary

The approved operational boundary is a dedicated local command, not an HTTP endpoint, runtime service, plugin, AGENT capability, or general-purpose CLI command.

For the Linux deployment, the approved command requires:
- invocation through `sudo` (effective UID exactly `0`, with a real UID different from `0`);
- an interactive terminal (TTY required; no stdin pipe, background invocation, or unattended startup);
- explicit typed confirmation containing the exact Project and Environment identifiers;
- a mandatory normalized reason;
- a caller-supplied UUIDv4 `operation_id` to make retries idempotent.

The command records the real/effective UIDs, terminal identifier, operation ID, exact scope, reason, and UTC timestamp. This is host-process provenance, **not** an Atlas USER identity and not proof of a person's civil identity. The host's sudo/authentication and audit configuration remains part of the trust boundary.

No secrets, passwords, tokens, or private keys are accepted as command-line arguments or written to the audit record.

## Domain contract

A provisioning request contains only:
- `operation_id` (canonical UUIDv4);
- `project_id`;
- `environment_id`;
- mandatory normalized reason (1–500 characters, no control characters).

A separate immutable provenance record contains:
- event UUIDv4;
- real and effective OS UIDs;
- terminal identifier;
- trusted UTC confirmation timestamp.

The service must not accept a boolean such as `is_admin`, a client claim, a USER/AGENT identity, or a Platform Admin grant as a substitute for this provenance.

## Transaction and persistence

The future implementation should use one `SQLiteLocalAuthorityUnitOfWork` transaction to:
1. validate that the canonical Project and Environment records exist;
2. resolve `operation_id` idempotently;
3. reject an existing operation ID if its Project, Environment, or reason differs;
4. create exactly one initial association in ACTIVE/revision 1;
5. append exactly one immutable provisioning event;
6. commit association and event atomically.

A new SQLite migration (next schema version) should add a provisioning-event ledger and an association event reference. A deferred foreign-key relationship plus SQL triggers should ensure:
- every association created after the migration has a matching provisioning event;
- every provisioning event references its association;
- event scope and initial state/revision match the inserted association;
- events cannot be updated or deleted;
- an event or association cannot be committed alone.

Associations that predate this migration remain valid with a NULL provisioning-event reference. No synthetic historical events are created.

## Capability separation

The general-purpose association repository exposed by `SQLiteLocalAuthorityUnitOfWork` should become read-only. The INSERT capability should move to a narrow internal provisioning writer constructed only inside the offline provisioning composition. It must not be exported through package `__all__`, attached to the general UoW, or registered in runtime composition.

The existing lifecycle writer remains separate. Provisioning does not call the lifecycle service and does not create a lifecycle event: creation is not an ACTIVE/SUSPENDED transition.

## Idempotency and failure behavior

- Same `operation_id` + same exact intent: return the original committed result without a second insert or event.
- Same `operation_id` + different intent: fail closed.
- Different `operation_id` for an already-associated Project/Environment pair: reject as a duplicate; do not silently reinterpret it as an idempotent retry.
- Missing Project/Environment, invalid provenance, non-interactive invocation, insufficient OS privilege, SQL constraint failure, or commit failure: no partial association/event.
- The command is never run automatically at process startup, migration, install, or deployment.

## Explicit non-goals

This slice does not:
- create or modify Project or Environment records;
- create, promote, or modify Atlas USER identities;
- grant Platform Admin authority;
- suspend or reactivate associations;
- expose an API, runtime capability, AGENT tool, plugin, or general CLI route;
- run against a production database as part of tests or deployment.

## Implementation sequence

1. Add domain request/provenance/event contracts and contract tests.
2. Add the immutable provisioning ledger and SQL integrity migration.
3. Separate the association reader from the narrow INSERT writer.
4. Add the transactional provisioning service and an unregistered offline composition.
5. Add a dedicated interactive Linux command with host-provenance checks and typed confirmation.
6. Add adversarial tests for idempotency, event/association atomicity, direct INSERT denial, and offline command guards.
7. Keep all runtime registration and actual first provisioning disabled.

## Validation boundary

The implementation will require owner-run Debian validation of focused tests, `compileall`, and the full suite. No real administrator, association, or production database will be provisioned during development or tests.
