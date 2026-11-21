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
- **A09b (application authorization):** use a separate, disposable fixture whose directory is traversable but not writable by other UIDs (for example 0711) and whose test socket permits connect (for example 0666). A different UID must reach the listener; the real handler must read SO_PEERCRED, reject that UID as UNAUTHORIZED_PEER, and send no protocol response. These relaxed permissions belong only to the isolated fixture and must never be applied to the candidate endpoint or treated as production settings. The fixture must be a sibling of the private probe sandbox, directly under a verified shared sticky temporary parent (such as /tmp), not nested inside the sandbox root (0700), because the parent directory's DAC permissions also govern traversal.

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


### A09 external-identity execution prerequisite

The private sandbox root is 0700. An A09b fixture nested below it would remain unreachable to a different UID regardless of the fixture's own 0711 mode. The fixture must instead be created as a separate temporary directory directly under a verified shared sticky temporary parent (for example /tmp), with its own mode 0711 and test socket mode 0666. The candidate endpoint remains unchanged.

The initial two-terminal coordination proposal was superseded by the bounded SSH-subprocess design in the A-IPC-01 design document. The runner remains under the ordinary checkout UID and starts a local SSH client; sshd launches only the fixed forced-command helper under the distinct peer UID. The runner must not invoke sudo, su, runuser, setuid, systemd, or any credential-switching mechanism.


## A09 temporary external identity design

A dedicated temporary account `atlas-a09-test` has been created and verified by the owner in Debian. Its UID is `1001`, primary GID `984`, its only reported group is the dedicated `atlas-a09-test` group, its HOME `/var/lib/atlas-a09-test` is mode `0700`, its shell is `/bin/bash`, and its password is locked (`passwd -S` state `L`). See [the provisioning record and remaining procedure](../../../docs/design/a09-temporary-test-identity-provisioning.md).

The existing `atlas-sandbox` account is excluded because it belongs to the earlier Atlas Broker/rootless-container environment and has an active lingering user manager. Do not reuse, unlock, stop or modify it.

The peer identity is provisioned. The owner reported a read-only inactivity check: `ps -u atlas-a09-test` returned no processes; `loginctl show-user` reported that UID 1001 is neither logged in nor lingering; `user@1001.service` is inactive; the linger file is absent; and `sudo -l -U atlas-a09-test` confirmed no sudo permission. This is a point-in-time check and does not prove that no unrelated system unit references the account. SSH preflight found public-key authentication enabled, keyboard-interactive disabled and strict modes enabled; X11, TCP and agent forwarding are globally enabled. The SSH daemon listens on all interfaces and the reported nftables INPUT policies are ACCEPT; this experiment does not establish global SSH isolation and must not modify SSH/PAM/firewall. The loopback ED25519 host-key fingerprint matched the locally inspected host key: `SHA256:txiDPT+/ldcIwnN6BPotbeL7QsofAieAeqF3GKMa9xI`.

The owner subsequently installed an ephemeral Ed25519 key restricted with `from="127.0.0.1",restrict` and forced command `/usr/bin/id -u`. A strict local SSH connection returned `1001`, confirming key authentication and the forced identity command. The private key remains outside the repository. This does not validate A09a/A09b. The helper/runner remain unimplemented; changing the forced command to the reviewed A09 helper is a separate host change requiring explicit approval. The latest evidence remains 15 PASS + A09 SKIP + 0 FAIL / INCOMPLETE.


## A09 SSH identity — current status (2026-11-21)

The owner installed an ephemeral Ed25519 key for `atlas-a09-test` and confirmed one strict loopback SSH authentication. The authorized key currently uses:

```text
from="127.0.0.1",restrict,command="/usr/bin/id -u"
```

The forced command returned UID `1001`. The private key remains under the owner's private runtime directory and is not in the repository. The temporary known_hosts file is owner-only and the ED25519 host key was pinned after fingerprint comparison.

This proves SSH public-key authentication and the forced identity command only. It does not exercise either A09 subscenario. The runner still implements neither A09a nor A09b and retains the prior 15 PASS + A09 SKIP + 0 FAIL / INCOMPLETE evidence.

The proposed orchestration design is recorded in [the A-IPC-01 design](../../../docs/design/local-authority-admin-private-unix-listener-probe.md#16-diseño-de-coordinación-externa-para-a09aa09b--2026-11-21). It uses a fixed, reviewed helper over stdin/stdout and a bounded SSH subprocess; no credential switching is performed by the runner. Implementing the helper is pending static review. Replacing the current forced command in `authorized_keys` is a separate host security change and requires explicit approval. Do not change it or run A09 yet.
