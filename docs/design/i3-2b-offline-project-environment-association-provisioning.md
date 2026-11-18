# Offline Project/Environment Association Provisioning

**Status:** operational trust boundary approved by the owner; V27 persistence, the narrow writer, and the guarded interactive Linux entrypoint are implemented on this branch. Owner-run Debian validation is still pending. No production database has been provisioned.

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

The dedicated writer uses one owned SQLite transaction to:
1. validate that the canonical Project and Environment records exist;
2. resolve `operation_id` idempotently;
3. reject an existing operation ID if its Project, Environment, or reason differs;
4. create exactly one initial association in ACTIVE/revision 1;
5. append exactly one immutable provisioning event;
6. commit association and event atomically.

Migration V27 adds `atlas_project_environment_provisioning_events` and a nullable `provisioning_event_id` reference on `atlas_project_environments`. A deferred bidirectional foreign-key relationship plus SQL triggers ensures:
- every association created after the migration has a matching provisioning event;
- every provisioning event references its association;
- event scope and initial state/revision match the inserted association;
- events cannot be updated or deleted;
- an event or association cannot be committed alone.

Associations that predate this migration remain valid with a NULL provisioning-event reference. No synthetic historical events are created.

## Capability separation

The general-purpose association repository exposed by `SQLiteLocalAuthorityUnitOfWork` is read-only. INSERT moved to `SQLiteProjectEnvironmentAssociationProvisioningWriter`, which is not exported through package `__all__`, not attached to the general UoW, and not registered in runtime composition. The dedicated CLI constructs it only after validating the host boundary.

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

1. Implement V27 immutable provisioning ledger and bidirectional deferred integrity constraints. **Implemented; validation pending.**
2. Separate the association reader from the narrow INSERT writer. **Implemented; validation pending.**
3. Add atomic persistence and idempotent operation-ID handling. **Implemented; validation pending.**
4. Add the unregistered interactive Linux command with `sudo`, UID, TTY, schema, and typed-confirmation guards. **Implemented; validation pending.**
5. Add adversarial tests for legacy-row preservation, idempotency, event/association atomicity, direct INSERT denial, and CLI guards. **Added; owner-run validation pending.**
6. Complete the final architecture audit and resolve any test findings.
7. Keep all runtime registration and actual first provisioning disabled.

## Validation boundary

The implementation will require owner-run Debian validation of focused tests, `compileall`, and the full suite. No real administrator, association, or production database will be provisioned during development or tests.
