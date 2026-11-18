# Offline Project/Environment Association Provisioning

**Status:** V27 persistence, the narrow writer, and the guarded interactive Linux entrypoint are implemented. The existing entrypoint was designed and validated under a privileged-process-writes-database trust model. That host-filesystem assumption is superseded for the future primary authority database by [the local authority storage operational contract](local-authority-storage-operational-contract.md). The current CLI must not be used against that future database until adapted and tested. No production database has been provisioned.

## Decision

Initial Project/Environment association creation is an offline, explicit operation controlled by the local platform operator. It is separate from Platform Admin lifecycle authority.

The existing permissions `association.suspend` and `association.reactivate` do not authorize creation. Project ownership, USER authentication, AGENT identity, delegation, ordinary Grants, and caller-supplied context fields are not provisioning authority.

## Trust boundary

The approved operational boundary is a dedicated local command, not an HTTP endpoint, runtime service, plugin, AGENT capability, or general-purpose CLI command.

The current implementation requires:
- invocation through `sudo` (effective UID exactly `0`, with a real UID different from `0`);
- an interactive foreground terminal (stdin/stdout must share a TTY and the process group must own the terminal foreground; no pipes, background invocation, or unattended startup);
- explicit typed confirmation containing the exact Project and Environment identifiers;
- a mandatory normalized reason;
- a caller-supplied UUIDv4 `operation_id` to make retries idempotent.

The command records the real/effective UIDs, terminal identifier, operation ID, exact scope, reason, and UTC timestamp. This is host-process provenance, **not** an Atlas USER identity and not proof of a person's civil identity. The host's sudo/authentication and audit configuration remains part of the trust boundary.

No secrets, passwords, tokens, or private keys are accepted as command-line arguments or written to the audit record.

The current dedicated entrypoint is invoked explicitly as `python -m atlas.adapters.sqlite.offline_association_provisioning_cli --database <absolute-existing-sqlite-path> --operation-id <uuid4>` under `sudo`. It verifies the complete migration ledger through V27 and never applies migrations itself.

### Deployment restriction for the future primary authority DB

The current CLI performs its UID/TTY/confirmation checks and opens SQLite in the same EUID-0 process. This is incompatible with the adopted ownership contract for the future `/var/lib/atlas-runtime/authority/authority.sqlite3`.

Therefore:
- **Do not run the current CLI against the future primary authority DB.**
- Do not make the future DB or its containing directory writable by root/ordinary operators merely to accommodate the current CLI.
- Do not change the DB owner to root.
- Do not treat passing the current CLI tests as validation of the future privilege boundary.

For the future primary DB, the privileged authorization frontend must validate operator provenance and typed confirmation without opening, migrating, or writing SQLite. It must delegate the narrow request and provenance through a reviewed, non-forgeable local channel to a writer running as `atlas-runtime`. The writer must not retain root or capabilities and must independently validate domain invariants, schema, scope, idempotency, and transaction rules. The audit record must distinguish the operator who authorized the operation from the Linux identity that executed it.

The exact launcher/delegation mechanism is **not yet selected or implemented**. No ad-hoc `setuid`, `setpriv`, shell wrapper, pipe, environment-variable, or argument-based design is approved without threat analysis and adversarial tests. Root remains trusted host administration; this boundary is intended to keep normal Atlas DB writes out of the privileged process, not to defend against a malicious host root.

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

For the future privilege-separated implementation, provenance must also preserve the distinction between the operator's authorization context and the `atlas-runtime` execution identity. The service must not accept a boolean such as `is_admin`, a client claim, a USER/AGENT identity, or a Platform Admin grant as a substitute for host provenance.

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

The general-purpose association repository exposed by `SQLiteLocalAuthorityUnitOfWork` is read-only. INSERT moved to `SQLiteProjectEnvironmentAssociationProvisioningWriter`, which is not exported through package `__all__`, not attached to the general UoW, and not registered in runtime composition.

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

1. Implement V27 immutable provisioning ledger and bidirectional deferred integrity constraints. **Implemented.**
2. Separate the association reader from the narrow INSERT writer. **Implemented.**
3. Add atomic persistence and idempotent operation-ID handling. **Implemented.**
4. Add the unregistered interactive Linux command with `sudo`, UID, TTY, schema, and typed-confirmation guards. **Implemented under the original privileged-writer model.**
5. Add adversarial tests for legacy-row preservation, idempotency, event/association atomicity, direct INSERT denial, and CLI guards. **Implemented for the current model.**
6. Adapt the command to the future privilege-separated model in the local authority storage contract. **Not implemented; required before use against the future primary DB.**
7. Keep all runtime registration and actual first provisioning disabled.

## Validation boundary

Historical owner-run Debian validation covered focused provisioning/CLI tests, affected lifecycle/workspace regression tests, and a full unit suite. Those results validate the implementation under its original model only; they do not validate the future `atlas-runtime` privilege separation, deployment filesystem permissions, or a production authority DB. No real administrator, association, or production database was provisioned during that validation.

## Residual host trust assumption

The writer is an internal Python adapter, not a Python sandbox or an OS privilege boundary. A caller able to execute arbitrary Python with write access to the authority database can import internal modules or write SQLite directly, and can construct a syntactically valid provenance dataclass.

For the future primary authority DB, the intended filesystem owner is `atlas-runtime`, and every DB writer must run under that identity. The privileged frontend must not have a code path that opens SQLite. Host root remains trusted and can alter the system; this design does not claim protection against malicious root. The launcher, provenance channel, sudo policy, and audit sink require a separate reviewed implementation before deployment.
