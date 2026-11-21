# A-IPC-01 — private Unix listener probe

**Status:** opt-in experiment, executed locally by the owner on Debian 13 with
15 scenarios PASS and the original A09 SKIP; overall result INCOMPLETE. The
review has since split that missing evidence into A09a (DAC) and A09b
(SO_PEERCRED); neither is implemented or validated yet. This is not a
production listener and does not select AF_UNIX pathname sockets as the
production IPC transport.

## Scope and safety boundary

The probe creates one unique temporary sandbox under the current user's
temporary directory. It refuses UID 0, requires Linux and SO_PEERCRED, checks
that the temporary path components are real directories, and requires the
sandbox root and each scenario directory to be owned by the effective UID with
mode exactly 0700.

Each listener is AF_UNIX/SOCK_SEQPACKET; its pathname is created only inside
the sandbox and its mode is set and checked as exactly 0600. The runner never
uses sudo, changes UID/GID, changes host configuration, installs or invokes
systemd, accesses SQLite, or connects to Atlas services.

Collision handling never unlinks a pathname before bind(). Stale sockets are
not removed to make a bind succeed. Cleanup compares the current lstat()
identity (device, inode and file type) with the identity captured after a
successful bind. A mismatch is preserved and reported. The comparison followed
by unlink() is not atomic: this does not protect against root or a malicious
process running under the same UID.

The ping scenario imports the existing handler and exercises only
authority.ping under atlas-admin/1. The remaining six catalogued operations
are not called or enabled.

## Run manually on Debian

From the repository root, as the ordinary unprivileged account that owns the
checkout:

    PYTHONPATH=src python tests/integration/private_unix_listener/run_probe.py

Do not prefix the command with sudo. The runner does not run as part of the
default unit-test suite and must be invoked explicitly.

The runner prints one JSON report and returns:

- 0: PASS — every scenario passed and no conditional scenario was skipped.
- 1: FAIL — an invariant failed or sandbox cleanup could not be verified.
- 2: INCOMPLETE — a required precondition or conditional scenario was not
  demonstrated. INCOMPLETE is not a pass.

## Scenario coverage

| ID | Coverage |
|---|---|
| A01 | Private directory/socket modes; bind, listen, accept and close |
| A02 | Regular-file collision preserves identity and sentinel |
| A03 | Symlink collision preserves link and target |
| A04 | Second bind cannot replace an active listener |
| A05 | Stale socket collision is not auto-cleaned |
| A06 | Cleanup preserves a replacement pathname |
| A07 | Cleanup removes the unchanged socket created by this instance |
| A08 | Allowed peer completes one authority.ping request |
| A09a | DAC blocks a different-UID client from the private 0700/0600 candidate endpoint; no SO_PEERCRED authorization claim |
| A09b | Separate temporary fixture lets a different-UID client reach the handler; real SO_PEERCRED UID is rejected before request processing, with no protocol response |
| A10 | Allowed peer UID/PID/GID are read from kernel credentials and match the current authorized UID |
| A11 | Disconnect before request is handled without a fabricated response |
| A12 | Truncated packet and ancillary data are rejected without an error response |
| A13 | Idle peer is released by the bounded read timeout |
| A14 | Test-only bounded accept harness rejects excess clients and recovers capacity |
| A15 | A closed listener no longer accepts new connections |
| A16 | Two concurrent binds produce exactly one winner; winner remains operational |

A09 is split into two independent checks and both remain SKIP in the current runner:

- **A09a (filesystem DAC):** use the candidate endpoint with its unchanged directory mode 0700 and socket mode 0600. A pre-existing different-UID process should be denied before the listener accepts the connection. This proves filesystem reachability isolation only; it does not exercise the handler's SO_PEERCRED allowlist.
- **A09b (application authorization):** use a separate, disposable fixture whose directory is traversable but not writable by other UIDs (for example 0711) and whose test socket permits connect (for example 0666). A different UID must reach the listener; the real handler must read SO_PEERCRED, reject that UID as UNAUTHORIZED_PEER, and send no protocol response. These relaxed permissions belong only to the isolated fixture and must never be applied to the candidate endpoint or treated as production settings.

Both checks require a pre-existing unprivileged identity and an externally launched client. The runner must not create accounts, change UID/GID, use sudo, or alter host configuration. If the owner cannot safely provide that external peer, retain SKIP and overall INCOMPLETE. Do not replace the real credential exchange with mocks.

A14 tests the resource ceiling of this temporary probe harness, not a production
listener implementation. Admitted workers are held behind a test-only release
gate until saturation has been observed, so the rejection check does not depend
on the handler read timeout or thread scheduling. Unexpected worker exceptions
are reported as failures. Its fixed experimental limits are included in the
JSON report; they do not establish production capacity values.

## Interpreting the report

The JSON includes the checkout commit, kernel, Python version, effective UID,
temporary sandbox path, fixed limits, per-scenario status/duration, overall
classification, cleanup result, and observed peer PID/UID/GID for the successful ping cases.

Any FAIL involving a changed pre-existing object, an unexpected unlink, a
peer receiving a response when the contract requires silence, an unbounded
resource count, or cleanup uncertainty is a stop condition. Preserve the JSON
report and the checkout commit for review; do not rerun against any host path.

A successful run does not demonstrate protection from root or same-UID
processes, multi-UID authorization, production service lifecycle, systemd
activation, separation of privileges, SQLite authorization, or suitability
for deployment. It does not approve a persistent listener or any administrative
operation beyond the non-mutating ping used as a protocol fixture.


## Owner-reported execution — 2026-11-20

The owner ran the command above without sudo on Debian 13 from checkout
`314e7395fbc972f8b9ab4a10dd800e85c11c7b59`.

- Kernel: `6.12.117+deb13-amd64`; Python: `3.13.5`; effective UID: `1000`.
- Overall: `INCOMPLETE`; duration: `0.876 s`; cleanup:
  `empty sandbox root removed`.
- A01–A08 and A10–A16: PASS (15 scenarios).
- A09: SKIP; no different-UID peer was tested. The runner intentionally does
  not change UID/GID, use sudo, or assume another identity.
- No scenario reported FAIL.

A14 observations: peak active workers 2, six rejected connections, eight
handled connections, and zero active connections after recovery. A16 observed
exactly one successful concurrent bind, and the winning listener remained
operational. A08/A10 observed peer PID 3751, UID 1000 and GID 1000.

This confirms only the experimental cases actually exercised. In particular,
it does not establish multi-UID rejection, production authorization, privilege
separation, resistance to root or same-UID malicious processes, persistent
service lifecycle, systemd integration, SQLite authorization, or production
suitability. Keep the overall result classified as INCOMPLETE while A09 is
unverified; do not relabel it PASS.


## A09 security-layer distinction

The candidate endpoint's DAC boundary (directory 0700, socket 0600) prevents another UID from reaching the listener. A kernel-level access denial occurs before accept() and therefore cannot prove that the application inspected SO_PEERCRED. A09a records this filesystem control.

A09b tests the separate application control with a disposable fixture that intentionally permits connection from the external test UID. Its permissions are test scaffolding only; it does not weaken or replace the candidate endpoint's DAC boundary. The two results must be reported separately.
