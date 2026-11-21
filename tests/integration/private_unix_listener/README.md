# A-IPC-01 — private Unix listener probe

**Status:** opt-in experimental probe implemented and owner-validated on
commit `1d5bdb122a8480c36b445be7dd961b93806de74b`: A01–A16 all PASS,
including A09a (DAC) and A09b (SO_PEERCRED), with 0 SKIP and 0 FAIL.
The recorded Debian execution is documented below and in
[the validation record](../../../docs/status-aipc01-validation-2026-11-21.md).
This is not a production listener and does not select AF_UNIX pathname sockets
as the production IPC transport.

 
> **Current direction (2026-11-21):** the owner selected alternative A as the
> primary line of technical evaluation and development. This is not production
> transport approval. The owner-reported execution below supersedes all earlier
> A09 SKIP / INCOMPLETE statements in the historical notes: A01–A16 = 16 PASS,
> 0 SKIP, 0 FAIL on commit
> `1d5bdb122a8480c36b445be7dd961b93806de74b`. Historical sections are retained
> to preserve the sequence of implementation and preflight decisions; read them
> as historical snapshots, not as the current validation state. PR #30 remains
> Draft on the separate design branch `design/isolated-private-unix-listener-probe`;
> it is not this experimental branch and does not contain the A09-enabled run.
> See the
> [canonical validation record](../../../docs/status-aipc01-validation-2026-11-21.md).

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

A09 is split into two independent checks. Both remain SKIP by default unless
the operator explicitly enables them with the reviewed SSH identity, the host
forced command has been separately approved and updated, and shell startup
files have been reviewed. The owner has now reported one successful opt-in
execution; see the execution record below:

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

The initial two-terminal coordination proposal was superseded by the bounded SSH-subprocess implementation described in the A-IPC-01 design document. The runner remains under the ordinary checkout UID and starts a local SSH client; sshd launches only the fixed forced-command helper under the distinct peer UID. The runner must not invoke sudo, su, runuser, setuid, systemd, or any credential-switching mechanism.


## A09 temporary external identity design

A dedicated temporary account `atlas-a09-test` has been created and verified by the owner in Debian. Its UID is `1001`, primary GID `984`, its only reported group is the dedicated `atlas-a09-test` group, its HOME `/var/lib/atlas-a09-test` is mode `0700`, its shell is `/bin/bash`, and its password is locked (`passwd -S` state `L`). See [the provisioning record and remaining procedure](../../../docs/design/a09-temporary-test-identity-provisioning.md).

The existing `atlas-sandbox` account is excluded because it belongs to the earlier Atlas Broker/rootless-container environment and has an active lingering user manager. Do not reuse, unlock, stop or modify it.

The peer identity is provisioned. The owner reported a read-only inactivity check: `ps -u atlas-a09-test` returned no processes; `loginctl show-user` reported that UID 1001 is neither logged in nor lingering; `user@1001.service` is inactive; the linger file is absent; and `sudo -l -U atlas-a09-test` confirmed no sudo permission. This is a point-in-time check and does not prove that no unrelated system unit references the account. SSH preflight found public-key authentication enabled, keyboard-interactive disabled and strict modes enabled; X11, TCP and agent forwarding are globally enabled. The SSH daemon listens on all interfaces and the reported nftables INPUT policies are ACCEPT; this experiment does not establish global SSH isolation and must not modify SSH/PAM/firewall. The loopback ED25519 host-key fingerprint matched the locally inspected host key: `SHA256:txiDPT+/ldcIwnN6BPotbeL7QsofAieAeqF3GKMa9xI`.

The owner subsequently installed an ephemeral Ed25519 key restricted with `from="127.0.0.1",restrict` and forced command `/usr/bin/id -u`. A strict local SSH connection returned `1001`, confirming key authentication and the forced identity command. The private key remains outside the repository. This does not validate A09a/A09b. The helper/runner are now implemented on this branch; changing the forced command to the reviewed A09 helper is a separate host change requiring explicit approval. The latest execution evidence remains 15 PASS + original A09 SKIP + 0 FAIL / INCOMPLETE.


## A09 SSH identity — current status (2026-11-21)

The owner installed an ephemeral Ed25519 key for `atlas-a09-test` and confirmed one strict loopback SSH authentication. The authorized key currently uses:

```text
from="127.0.0.1",restrict,command="/usr/bin/id -u"
```

The forced command returned UID `1001`. The private key remains under the owner's private runtime directory and is not in the repository. The temporary known_hosts file is owner-only and the ED25519 host key was pinned after fingerprint comparison.

This proves SSH public-key authentication and the forced identity command only. It does not exercise either A09 subscenario. The A09a/A09b helper and runner have since been implemented on this branch, but remain unexecuted and unvalidated. The last owner-reported execution still predates that implementation and remains 15 PASS + original A09 SKIP + 0 FAIL / INCOMPLETE.

The orchestration design and implementation details are recorded in [the A-IPC-01 design](../../../docs/design/local-authority-admin-private-unix-listener-probe.md#16-diseño-de-coordinación-externa-para-a09aa09b--2026-11-21). The current authorized-key forced command remains `/usr/bin/id -u`; replacing it with the fixed helper is a separate host security change requiring explicit approval. Do not change it or run A09 yet.


## A09 helper/runner implementation — 2026-11-21

The following code is now present on the experimental branch:

- `a09_ssh_client.py`: fixed standard-library-only remote helper. It accepts one JSON instruction up to 4096 bytes, allows only A09a/A09b and the corresponding probe socket path shapes, rejects a non-empty `SSH_ORIGINAL_COMMAND`, never executes shell commands, never changes credentials, and does not access the checkout. Its stdout/stderr exchange is capped at 4096 bytes per stream; the helper emits at most 2048 bytes.
- `run_probe.py`: A09a and A09b are separate report rows. A09 remains disabled by default. Enabling it requires all of:
  - `--enable-a09`;
  - `--a09-identity-file` and `--a09-known-hosts`;
  - `--a09-forced-command-confirmed`, acknowledging the separately approved host-side `authorized_keys` forced-command update;
  - `--a09-shell-startup-reviewed`, acknowledging read-only review of the peer account's shell startup files.
- Preflight checks the peer account UID/GID from the local account database, requires a distinct non-root identity, exact key/known_hosts ownership and modes, no hard links, known_hosts directly under `/tmp`, the previously verified loopback ED25519 host-key fingerprint, and `/tmp` as a root-owned 01777 directory.
- SSH is invoked with `-F /dev/null`, an explicit identity, `IdentityAgent=none`, public-key-only authentication, strict host-key checking, ED25519-only algorithms, no PTY, no forwarding, no proxy, no control master and a bounded connection/total timeout. No remote command is supplied; the authorized-key forced command is the only remote entrypoint.
- The helper is copied to `/tmp/atlas-a09-client.py` with exclusive creation, mode 0644, and identity-checked cleanup. A pre-existing helper path is never overwritten.
- A09a requires external `EACCES`, zero accepted connections and unchanged candidate endpoint identity/modes.
- A09b requires the kernel-observed peer PID/UID/GID to match the helper/account, the real handler to raise `UNAUTHORIZED_PEER`, a non-empty ping request to have been sent, and zero response bytes before EOF/reset. The temporary fixture is a sibling directly under `/tmp`, directory 0711/socket 0666; the candidate endpoint remains 0700/0600.
- If the SSH child cannot be stopped, the runner preserves the helper/socket/fixture rather than deleting resources that may still be in use; this is a failure requiring manual inspection.

### Do not run A09 yet

The installed key still forces `/usr/bin/id -u`. The implementation expects the separately approved forced command:

```text
/usr/bin/python3 -I /tmp/atlas-a09-client.py
```

Changing `authorized_keys` is a host security change and has **not** been authorized or performed. Before that change, the owner must also inspect the peer account's `.bashrc`, `.bash_profile`, `.profile` and relevant shell startup behavior read-only. No SSH/PAM/firewall changes are permitted.

After those independent gates are completed, the opt-in form is:

```bash
PYTHONPATH=src python tests/integration/private_unix_listener/run_probe.py \
  --enable-a09 \
  --a09-identity-file /path/to/id_ed25519 \
  --a09-known-hosts /path/to/known_hosts \
  --a09-forced-command-confirmed \
  --a09-shell-startup-reviewed
```

The example is documentation only and must not be run until the host change and execution are explicitly approved. A normal invocation without these options leaves A09a/A09b as SKIP and the global result INCOMPLETE.

**Validation status:** static code review of the helper/runner is complete in GitHub; no tests, builds or workflows were run. The implementation has not been executed or validated. The owner must inspect shell startup behavior read-only, authorize any host-side forced-command change separately, and execute the probe locally on Debian. `main` remains untouched; no PR exists and no production transport is approved.


## Owner-reported execution — 2026-11-21 (A09 enabled)

The owner executed the opt-in runner on Debian 13 from checkout
`1d5bdb122a8480c36b445be7dd961b93806de74b`, as unprivileged UID 1000,
with the pre-provisioned peer account `atlas-a09-test` (UID 1001, GID 984).
Kernel: `6.12.117+deb13-amd64`; Python: `3.13.5`; duration: `1.72 s`.

**Reported result: `overall=PASS`; all 16 scenarios A01–A16 passed.**
There were no SKIP or FAIL rows. Cleanup reported
`empty sandbox root removed`.

A09 evidence:

- **A09a — DAC:** external peer UID 1001/GID 984/PID 5405 received
  `EACCES` (`errno=13`) connecting to the candidate endpoint. The listener
  accepted zero connections. Candidate socket remained owned by UID 1000,
  mode 0600; candidate directory mode remained 0700.
- **A09b — SO_PEERCRED:** external peer UID 1001/GID 984/PID 5417 connected
  to the separate fixture (directory mode 0711, socket mode 0666). The real
  handler rejected it with `UNAUTHORIZED_PEER`. The client observed reset
  and received zero response bytes after sending a 122-byte ping request.
- The temporary sandbox root was removed successfully.

The existing A01–A08 and A10–A16 scenarios also reported PASS. A14 observed
peak_active=2, rejected_connections=6, handled_connections=8 and
active_after_recovery=0. A16 observed exactly one bind winner and a
functioning winner listener.

This owner-reported result validates only the experimental probe scenarios
actually exercised on the recorded commit and host. It does **not** approve
a persistent listener, select AF_UNIX pathname sockets for production, enable
any administrative operation beyond the non-mutating ping fixture, prove
protection against root or same-UID malicious processes, validate systemd
activation, privilege separation, SQLite authorization, or authorize
deployment. SSH/PAM/firewall global configuration was not changed as part of
the reported run.


## A-IPC-02 — mutual authentication and bounded-capacity probe

**Current status (2026-11-21):** the owner ran the complete A-IPC-02
runner on checkout `66b348e1be9a7e614d51c4b3ade9e643c9152106` in the
disposable `Atlas-VM-test` (Debian 13, kernel 6.12.117,
Python 3.13.5, EUID 0; SERVICE 2005/2005, OTHER 2006/2006).
**MA-01..MA-10 and CP-01..CP-12: PASS; overall=PASS; 0 skipped; 0 failed.**
The owner-reported evidence is recorded at the end of this document.
This is not a production listener or transport approval. A-IPC-01 remains
a separate unprivileged runner that refuses EUID 0; A-IPC-02 requires direct
root execution inside a disposable VM.

The runner creates a fresh root-owned mode-0700 private sandbox and a separate
root-owned mode-0711 traversal fixture root under `/run`. The latter permits the
alternate-UID client to reach a deliberately exposed fixture socket; it is not
writable by group/others. It stages read-only copies of the probe and IPC module
under that traversal root so dropped-UID child processes can execute/import them.
Only temporary fixture directories and socket pathnames are created.
It does not create NSS users/groups, edit host configuration, invoke sudo/su,
install systemd units, access SQLite, or connect to any Atlas service. The
service child clears supplementary groups, sets real/effective/saved GID and
UID to the supplied numeric fixture values, and caps its own
`RLIMIT_NOFILE` at 64. No host account provisioning is performed.

The fixture IDs must be dedicated, unused numeric identities in the disposable
VM. The operator is responsible for selecting them and explicitly confirming
that the VM and IDs are disposable fixtures. Do not use IDs belonging to
real host users/groups or run this probe on the production server.

### Invocation

From the repository root, in a disposable Debian/Linux VM, start a root shell
directly (do not use sudo for this probe), then supply four dedicated numeric
fixture IDs:

```sh
read -r -p "UID numérico reservado para atlas-runtime fixture: " SERVICE_UID
read -r -p "GID numérico reservado para atlas-runtime fixture: " SERVICE_GID
read -r -p "UID numérico reservado para peer alternativo: " OTHER_UID
read -r -p "GID numérico reservado para peer alternativo: " OTHER_GID

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 tests/integration/private_unix_listener/run_mutual_auth_capacity_probe.py \
  --service-uid "$SERVICE_UID" \
  --service-gid "$SERVICE_GID" \
  --other-uid "$OTHER_UID" \
  --other-gid "$OTHER_GID" \
  --confirm-disposable-vm \
  --confirm-fixture-ids
```

The command is intentionally not part of the default test suite. Do not invent
or reuse IDs from the host; first reserve four numeric fixture IDs exclusively
inside the disposable VM. The runner does not create accounts or groups.

### Owner-reported baseline execution — 2026-11-21

The owner executed A-IPC-02 in the disposable VM `Atlas-VM-test`, directly
as root, on commit `fbc8c68e75c7d5d32768442666cf861f7880eb28`, using fixture
UID/GID pairs 2005/2005 and 2006/2006. Debian 13, kernel
`6.12.117+deb13-amd64`, Python 3.13.5.

- MA-01, MA-02, MA-04 and MA-05: PASS.
- CP-01 and CP-04: PASS; observed maximum active workers 4, and zero active
  workers after recovery.
- Kernel backlog was configured to 8 but exact saturation was not tested.
- Overall: INCOMPLETE, as required while omitted scenarios remain.
- Duration: 1.177 s.
- Cleanup: both private and traversal `/run` sandboxes removed after child
  processes exited.
- No FAIL rows were reported.

This execution validates only the six scenarios above on the recorded
commit/environment. The current MA-03 addition was authored afterward in
commit `7a0d4f1` and has not yet been executed. Do not attribute MA-03 PASS
or the baseline run to the newer commit.

### Implemented evidence in this increment

| Scenario | Evidence |
|---|---|
| MA-01 | Root client verifies the server's kernel UID before sending a valid ping |
| MA-02 | Root client rejects a server running under the alternate UID and sends zero bytes |
| MA-03 | Non-root client fixture is rejected by the EUID guard before socket creation/connect; server observes no connection (new code, pending owner execution) |
| MA-04 | Service receives a real kernel peer UID 0 and processes the ping |
| MA-05 | Service rejects the alternate-UID client before calling recv and sends no response |
| CP-01 | Four active workers occupy all slots; a fifth connection remains pending rather than creating a fifth worker |
| CP-04 | After a slot is released, the queued connection is accepted and the service returns to zero active workers |

The probe verifies the service child's real/effective/saved UID/GID, empty
supplementary groups, socket ownership/mode and `RLIMIT_NOFILE=64`; it records
the configured backlog, read/write timeout and global deadline. Behavioral
tests for timeout expiry remain incomplete; exact backlog saturation is implemented but pending owner validation.

**Not yet implemented/validated:** full open-FD accounting; idle/read/write
deadline adversaries; exception-path worker recovery; request/response boundary
and JSON-depth adversaries; pathname component-walk, symlink and collision
matrix; stale recovery. CP-02/CP-03 backlog saturation has now been implemented
in the runner but is pending owner execution on the disposable VM. The runner
continues to report all unimplemented or unvalidated scenarios as INCOMPLETE.

### Safety and result codes

- Run only in a disposable VM with root access and four numeric IDs reserved
  exclusively for the fixture.
- The process drops credentials only in child processes; no host account,
  group, permission, service or global configuration is changed.
- Temporary data is confined to fresh root-owned `/run/atlas-mutual-auth-*`
  and `/run/atlas-mutual-auth-public-*` directories. The public traversal root
  is mode 0711 and not writable by group/others. If a child fails to stop or a
  socket pathname identity cannot be verified, the sandboxes are preserved and
  the report is FAIL.
- 0: PASS (all required scenarios implemented and passed; not expected yet).
- 1: FAIL (an implemented invariant failed or cleanup could not be verified).
- 2: INCOMPLETE (preconditions unavailable or scenarios remain unimplemented).

No tests, builds or workflows have been run by the assistant. The owner must
review and execute this probe manually. A-IPC-02 does not implement or approve
a persistent listener or production transport.


## A-IPC-02 owner validation and MA-06 update — 2026-11-21

The owner executed the A-IPC-02 runner in disposable VM `Atlas-VM-test`,
directly as root, on commit
`069dbb9520f9e640955d9122f3a8012b2f55ba1a`, Debian 13, kernel
`6.12.117+deb13-amd64`, Python 3.13.5, with SERVICE UID/GID 2005/2005
and OTHER UID/GID 2006/2006.

- MA-01 through MA-05: PASS.
- MA-03 specifically observed client EUID 2006, `connect_attempted=false`,
  and `server_observed_connection=false`.
- CP-01 and CP-04: PASS; maximum active workers 4; active workers after
  recovery 0.
- Backlog 8 was configured but not saturated.
- Overall INCOMPLETE; duration 1.339 s; private and traversal `/run`
  sandboxes removed after child processes exited.
- No FAIL rows were reported.

This evidence belongs to commit `069dbb9` only. The subsequent MA-06
implementation is in commit `9a8380e` and has not been executed.

### MA-06 — reject client-supplied identity claims

The runner now sends a valid ping envelope augmented with untrusted top-level
`uid`, `gid` and `pid` claims. The fixture authenticates the connected
peer using kernel SO_PEERCRED first, then passes the packet through the strict
request decoder. MA-06 requires rejection with `INVALID_REQUEST`, while the
observed peer UID remains the kernel UID (root in this scenario); the supplied
identity fields are not accepted as credentials.

MA-06 is implemented but pending owner execution. This is a protocol-envelope
negative test, not proof against a compromised root client or kernel. The
overall runner remains INCOMPLETE until the remaining MA/CP scenarios are
implemented and owner-validated.



## A-IPC-02 — validación del propietario de MA-06 (2026-11-21)

El propietario ejecutó el runner directamente como root en la VM desechable
`Atlas-VM-test`, Debian 13, kernel `6.12.117+deb13-amd64`, Python
`3.13.5`, sobre el commit `b4eda57d36338f065adb2cb4e00d19a8ade58069`,
con fixtures SERVICE UID/GID `2005/2005` y OTHER UID/GID `2006/2006`.

- **MA-01..MA-06: PASS.** Cliente root autenticó el servidor UID 2005 y
  completó ping. El cliente rechazó el servidor UID 2006 antes de enviar
  bytes (`bytes_sent_by_client=0`). El servidor rechazó al peer UID 2006
  antes de leer (`response_bytes=0`). El cliente no-root EUID 2006 fue
  rechazado antes de connect (`connect_attempted=false`; el servidor no
  observó conexión).
- **MA-06:** el envelope ping incluía claims top-level falsos
  `uid=0`, `gid=0`, `pid=1`. El decoder respondió
  `INVALID_REQUEST`; la evidencia de identidad conservó
  `kernel_peer_uid=0`. Los campos aportados por el cliente no se aceptaron
  como credenciales.
- **CP-01/CP-04: PASS.** Máximo observado de workers/conexiones activas: 4;
  después de liberar carga, `active_after_recovery=0`.
- Backlog del kernel configurado en 8, **sin saturación exacta**.
- Duración: 1.431 s. Cleanup confirmado: sandboxes privado y de traversal
  bajo `/run` eliminados después de finalizar los procesos hijos.
- Resultado global: **INCOMPLETE**, sin escenarios FAIL.

La evidencia aplica al commit y entorno indicados; no se extiende a commits
posteriores sin repetir la ejecución. Permanecen sin implementar o validar
MA-07..MA-10 y CP-02..CP-03/CP-05..CP-12: configuración ausente/duplicada/
desconocida/alterada y snapshot inmutable; desconexión y variantes de
transporte; saturación exacta del backlog; adversarios de read/write/deadline;
recuperación ante excepciones; límites de payload/profundidad JSON y
contabilidad completa de FDs.

**Siguiente incremento propuesto:** revisar y diseñar MA-07/MA-08 antes de
codificar. El diseño de configuración confiable exige parser cerrado,
resolución segura desde descriptor, validación de tipo/owner/mode/tamaño,
fallo cerrado e inmutabilidad en memoria. La propuesta de
`/etc/atlas/admin-ipc.conf` sigue siendo solo diseño: no existe archivo
operativo, parser productivo ni entrypoint IPC revisado. Cualquier fixture
MA-07/08 debe vivir exclusivamente en sandbox temporal y no leer ni crear
configuración del host.

No se ejecutaron pruebas, compilaciones ni workflows desde GitHub. El
propietario ejecutó el probe localmente en la VM indicada. `main` no se
modificó, no se creó PR y no se aprobó listener persistente, transporte de
producción ni despliegue.


### MA-07 / MA-08 — strict config fixture and immutable snapshot (owner-validated)

The runner imports `probe_config.py`, located beside the runner under
`tests/integration/private_unix_listener/`. It is experimental fixture code,
not a production configuration parser and not part of `src/atlas`.

The fixture grammar is strict ASCII `key=value` with eight required keys,
no defaults, duplicate or unknown keys, and fixed test policy:
`client_uids=0`, `SOCK_SEQPACKET`, socket mode 0600 and directory mode
0700. It is intentionally not a decision about the final production format.

The loader opens the fixture filename relative to an already-open descriptor
for a root-owned mode-0700 sandbox directory, using `O_NOFOLLOW`,
`O_NONBLOCK` and `O_CLOEXEC`. It requires a regular root:root file, exact
mode 0644, one hard link and size 1–4096 bytes; reads through that descriptor;
compares metadata before/after; parses strictly; and compares service UID/GID
to the numeric fixture identity.

MA-07 expects rejection for: absent file, duplicate key, unknown key, missing
required key, altered service identity, symlink, FIFO, group/other-writable
mode, wrong owner, oversized file and hardlink. It also requires one valid
fixture to load with the exact expected identity and root-only client policy.

MA-08 loads a snapshot, atomically replaces the pathname with a different
valid configuration, and verifies the existing frozen dataclass and tuple
remain unchanged. There is no watcher or reload path.

**Scope limitation:** this validates the final file relative to a trusted
temporary directory descriptor. It does not validate all path ancestors from
`/`; the PA pathname-resolution probe remains separate. It does not read or
create `/etc/atlas/admin-ipc.conf`, alter the host, or approve production
configuration.

The owner validated MA-07/MA-08 on commit `585dd3d979bc1b800550e4b9c79c382b22cf1f6c` in disposable `Atlas-VM-test`; see the execution record below. No tests, builds or workflows have been run by the assistant.

### A-IPC-02 — owner validation MA-07/MA-08 (2026-11-21)

Owner execution on commit `585dd3d979bc1b800550e4b9c79c382b22cf1f6c` in disposable `Atlas-VM-test` (Debian 13, kernel `6.12.117+deb13-amd64`, Python 3.13.5, real EUID 0; SERVICE fixture 2005/2005, OTHER fixture 2006/2006):

- MA-01..MA-08: PASS.
- MA-07: valid fixture accepted with `client_uids=[0]`; all 11 invalid cases rejected (absent, duplicate/unknown/missing key, altered service identity, symlink, FIFO, unsafe mode, wrong owner, oversized file and hardlink).
- MA-08: atomic pathname replacement did not change the loaded snapshot; frozen fields and tuple collection remained immutable.
- CP-01/CP-04: PASS; maximum active workers 4, recovered to 0. Kernel backlog 8 was configured but not saturated.
- Duration 1.497 s; private and traversal `/run` sandboxes removed after child processes exited; no FAIL rows. Overall remains **INCOMPLETE**.

Remaining: MA-09/MA-10 and CP-02/CP-03/CP-05..CP-12. This evidence does not validate production configuration, full ancestor path resolution, a persistent listener, or deployment. The fixture parser remains probe-only.

### MA-09 / MA-10 — disconnect and unsupported transport (implemented; owner validation pending)

Commit `f41df94d0f87d288bfc7e3df45c66295fa19d570` adds two scenarios that call the actual `handle_admin_connection` implementation in `src/atlas/platform_admin_ipc.py`:

- **MA-09:** an authorized AF_UNIX/SOCK_SEQPACKET peer shuts down its write side before sending a request. The handler must raise `AdminPeerDisconnected` with `PEER_DISCONNECTED`; the probe checks that no response bytes are emitted and no request is accepted. This is an EOF/half-close before the first request, not an interruption inside the kernel SO_PEERCRED syscall.
- **MA-10:** the handler receives AF_UNIX/SOCK_STREAM and AF_INET/SOCK_STREAM connections with a valid ping packet already queued. It must reject both with `AdminProtocolRejected/INVALID_REQUEST` before reading; a non-consuming `MSG_PEEK` confirms the first request byte remains queued and the peer receives no protocol bytes.
- The runner reports MA-09 and MA-10 independently. The remaining INCOMPLETE scenarios are CP-02/CP-03 and CP-05..CP-12.
- **Owner action:** pull the branch and run the probe only in disposable `Atlas-VM-test`. No test/build/workflow was run by the assistant. MA-09/10 are implemented, not yet validated.


## A-IPC-02 — latest owner execution (2026-11-21)

The owner updated the disposable VM checkout by fast-forward from
`991f91e` to `901c792cb723d920da4970ecce98ea7f871c4f85`, then ran the
runner directly as EUID 0 with SERVICE fixture UID/GID `2005/2005` and OTHER
fixture UID/GID `2006/2006`.

Environment: Debian 13; kernel `6.12.117+deb13-amd64`; Python `3.13.5`;
duration `1.687 s`.

- **MA-01..MA-06: PASS.** Valid root client authenticated service UID 2005;
  alternate service UID 2006 was rejected before client send; alternate
  client UID 2006 was rejected before server recv; non-root EUID 2006 was
  rejected before connect; forged top-level UID/GID/PID claims were rejected
  as `INVALID_REQUEST`, with kernel peer UID remaining 0.
- **MA-07: PASS.** Valid fixture configuration accepted; all 11 invalid cases
  rejected (absent, duplicate, unknown, altered/missing required values,
  symlink, FIFO, unsafe mode, wrong owner, oversized file and hardlink).
- **MA-08: PASS.** Frozen fields and immutable collections retained the
  original `/run/atlas/admin.sock` snapshot after atomic replacement with
  `/run/atlas/changed.sock`.
- **MA-09: PASS.** Authorized AF_UNIX/SOCK_SEQPACKET peer closed its write
  side before sending a request; the handler reported
  `PEER_DISCONNECTED`, accepted no request and emitted zero response bytes.
- **MA-10: PASS.** AF_UNIX/SOCK_STREAM and AF_INET/SOCK_STREAM were both
  rejected as `INVALID_REQUEST` before reading; `MSG_PEEK` confirmed the
  first request byte remained queued and each peer received zero protocol
  response bytes.
- **CP-01/CP-04: PASS.** Four configured workers were observed active at
  maximum; after recovery, `active_after_recovery=0`.
- Kernel backlog 8 was configured but **not saturated**.
- Both private and traversal `/run` sandboxes were removed after child
  processes exited. No FAIL rows were reported.
- Overall: **INCOMPLETE**, correctly, because exact backlog saturation,
  read/write/global deadline adversaries, exception recovery, payload/JSON
  depth boundaries and full FD accounting remain unimplemented/unvalidated.

The JSON reported `commit: null`; the preceding successful owner-side
`git pull` fast-forwarded the checkout to `901c792`. Preserve this metadata
limitation when citing the execution. This owner-reported run is evidence only
for the scenarios and environment listed. It does not validate the production
listener lifecycle, path-walk, stale recovery, systemd, SQLite, or deployment,
and does not approve a persistent listener or production transport. No tests,
builds or workflows were run by the assistant.


## A-IPC-02 — última ejecución del propietario y CP-02/CP-03 implementados (2026-11-21)

El propietario ejecutó el runner en `Atlas-VM-test`, Debian 13, kernel
`6.12.117+deb13-amd64`, Python 3.13.5, EUID 0, fixtures SERVICE
2005/2005 y OTHER 2006/2006. Resultado comunicado: MA-01..MA-10 PASS;
CP-01/CP-04 PASS; duración 1.687 s; cleanup de ambos sandboxes `/run`
completado; cero FAIL. Global INCOMPLETE por CP-02/CP-03 y CP-05..CP-12
pendientes en el commit ejecutado. El checkout estaba en
`901c792cb723d920da4970ecce98ea7f871c4f85`; el JSON informó
`commit: null`.

Después de esa ejecución, el runner añadió CP-02/CP-03:
- Observa `Recv-Q` y `Send-Q` del listener AF_UNIX mediante
  `ss -x -l -n -H` de iproute2.
- Ocupa los cuatro workers y exige que exactamente ocho conexiones queden
  pendientes en el backlog configurado.
- Intenta una novena conexión no bloqueante y exige `EAGAIN`, sin aumento
  de cola ni aceptación por la aplicación.
- Verifica que el número de workers/aceptaciones no exceda cuatro durante
  la saturación.

**Estado de CP-02/CP-03:** implementación estática en GitHub, pendiente de
ejecución y validación del propietario. Requiere `ss` root-owned y no
escribible por grupo/otros; si no está disponible o no puede observarse el
listener, el runner declara INCOMPLETE. No se han ejecutado pruebas,
compilaciones ni workflows desde GitHub. CP-05..CP-12 continúan pendientes.


## A-IPC-02 — backlog AF_UNIX: resultado y corrección (2026-11-21)

El propietario ejecutó el commit `1ebf930` en Debian 13/kernel
`6.12.117+deb13-amd64`. MA-01..MA-10 y CP-01/CP-04 PASS. CP-02/CP-03
falló porque, tras observar Recv-Q=8/Send-Q=8, la conexión adicional devolvió
`connect_ex=0`; cleanup de sandboxes correcto.

La revisión del kernel Linux AF_UNIX muestra comparación `queue_len > backlog`.
Con `listen(8)`, Linux admite nueve conexiones pendientes: la novena debe
conectar y la décima debe obtener EAGAIN si no se liberó ningún slot. El runner
fue corregido en commit `634e19decce2322e94ca0d1fe410b259f23dcb67` para
medir 8/8, luego 9/8, y exigir EAGAIN en la décima, sin accepts/workers extra.
La corrección está pendiente de ejecución local; no atribuir PASS a CP-02/03
hasta recibir el nuevo JSON.


### Ejecución del propietario — CP-02/CP-03 (2026-11-21)

Sobre commit `1ebf930a6559c3d6a81965f0f94c28ed8e6eef56`, el propietario
reportó MA-01..MA-10 y CP-01/CP-04 PASS. CP-02/CP-03 falló al esperar EAGAIN
en la conexión novena: connect_ex devolvió 0 después de observar 8/8.
Cleanup de sandboxes completado.

El kernel Linux AF_UNIX compara longitud de cola con backlog usando `>`.
Con `listen(8)`, la novena conexión pendiente es admitida; la décima debe
rechazarse con EAGAIN. Runner corregido en
`634e19decce2322e94ca0d1fe410b259f23dcb67` para medir los límites 8/8 y
9/8 y exigir EAGAIN en la décima. Requiere nueva ejecución; CP-02/03 no
están validados. CP-05..CP-12 siguen pendientes.


### Owner-reported validation — CP-02/CP-03 (2026-11-21)

The owner ran commit `b5b0128e2646e41e3a2f927251c6fa6dafa897d7` in `Atlas-VM-test` (Debian 13, kernel `6.12.117+deb13-amd64`, Python 3.13.5, EUID 0, fixtures 2005/2005 and 2006/2006). MA-01..MA-10, CP-01/CP-04 and CP-02/CP-03 PASS. Overall is INCOMPLETE because CP-05..CP-12 remain pending. Cleanup removed both `/run` sandboxes.

CP-02/03 observed listen backlog 8, Recv-Q/Send-Q 8/8, ninth pending connection admitted (connect result 0, queue 9/8), tenth nonblocking connection rejected with EAGAIN (errno 11), queue remained 9/8, accepted count remained 9 after overflow, and worker limit was respected.

**Design gate before CP-05:** the scenario table says a silent client terminates at the 15-second global deadline, but the fixture applies `min(READ_TIMEOUT=5 s, remaining_global)` to its first read. A fully silent client therefore hits the 5-second read timeout first. Clarify whether CP-05 should test the 5-second read/idle timeout or whether global-deadline semantics are intended to differ before implementation.


## A-IPC-02 — CP-05 read timeout and CP-06 global deadline (implemented; owner validation pending)

Runner commit: `59fafb801a31d7adf51a6598db78440255744321`.

The approved limits remain unchanged: read/write timeout 5 seconds and
accept-based global deadline 15 seconds.

- **CP-05:** a real authorized AF_UNIX/SOCK_SEQPACKET peer connects and sends
  no packet. The fixture records when its first read begins and when the
  5-second read timeout expires. It requires elapsed time near 5 seconds,
  confirms the global deadline was not reached, and verifies peer EOF with
  zero response bytes.
- **CP-06:** a dedicated fixture server injects an 11-second delay after
  accept/authentication and before its read phase. The read timeout is clipped
  to the remaining accept-based global budget (approximately 4 seconds);
  the fixture must close the peer at approximately 15 seconds from accept.
  The JSON records monotonic elapsed time, effective read timeout, remaining
  global budget and peer EOF.

The 11-second delay is **test-only harness instrumentation**. It is not a
production handler delay and does not simulate a blocked write. The current
fixture has one receive and one send; with individual read/write timeouts of
5 seconds, ordinary I/O alone cannot consume the 15-second global budget.
CP-06 therefore validates that a later read phase inherits the remaining
accept-based deadline, not a real cumulative read-plus-write workload.

CP-05 and CP-06 are implemented but **not owner-validated**. The full probe
must still report INCOMPLETE while CP-07..CP-12 remain pending. Run only in
the disposable `Atlas-VM-test`, directly as root as required by the existing
runner instructions. The assistant has not run tests, builds or workflows.
No production handler, host, account, service, SQLite or `main` changes.


## A-IPC-02 — ejecución validada de CP-05 / CP-06 (2026-11-21)

El propietario ejecutó el commit 0db262802ce30ec38a4ce52a4f5bfaa3081fc2b1 directamente como EUID 0 en Atlas-VM-test, Debian 13, kernel 6.12.117+deb13-amd64, Python 3.13.5, fixtures SERVICE 2005/2005 y OTHER 2006/2006.

**Resultado reportado:** MA-01..MA-10 y CP-01..CP-06 PASS; CP-07..CP-12 INCOMPLETE; overall INCOMPLETE; duración 22.095 s; cleanup de ambos sandboxes bajo /run completado.

CP-05 observó timeout de lectura de 5.002 s desde accept (configuración 5.0), deadline global no alcanzado, EOF y cero bytes de respuesta.

CP-06 observó la espera test-only de 11.0 s, inicio de lectura a 11.004 s, timeout efectivo/restante de 3.996 s y cierre a 15.006 s desde accept; deadline global alcanzado, EOF y cero bytes de respuesta. Esta instrumentación verifica el recorte del presupuesto global, no simula trabajo productivo ni una escritura bloqueada.

CP-02/03 observó Recv-Q 8 y 9, conexión novena admitida, décima rechazada con EAGAIN errno 11, nueve accepts sin accepts adicionales tras overflow y workers dentro del máximo de cuatro.

No se ejecutaron pruebas, builds ni workflows desde GitHub. La evidencia valida los escenarios reportados en el commit y VM indicados; no aprueba transporte productivo, listener persistente ni despliegue.


## CP-07 — worker exception recovery (implemented; owner validation pending)

Runner commit: fbd4512d163b31e53b355280e636fb47cf8d66a9.

The scenario starts a dedicated fixture server with a one-shot, test-only worker exception. After the worker owns the accepted socket, the injected RuntimeError is recorded. The worker's exception handler records worker_error; the socket context closes the peer; and finally decrements the active count and releases the bounded-semaphore slot.

The probe requires EOF and zero response bytes on the faulting peer, the expected worker_error event, active=0 after the exception, a still-running server process, and a subsequent valid authority.ping that succeeds and returns active to zero. This checks both slot release and continued accept/worker-pool operation.

The exception injection is harness-only; it is not a production handler change. CP-07 is implemented but not owner-validated. CP-08..CP-12 remain INCOMPLETE. Run only in the disposable Atlas-VM-test as root using the existing invocation; do not run on greed. No tests, builds or workflows were run by the assistant.


### CP-07 — corrección tras primera ejecución

El propietario ejecutó el runner en d054f95f4cce9e33fe55bf61080dcd3f493ed3ce. MA-01..MA-10 y CP-01..CP-06 pasaron de nuevo. CP-07 falló antes de sus aserciones de recuperación porque Server._record trató el evento worker_error deliberadamente inyectado como un error inesperado. No se demostró aún EOF/slot release/segunda petición y CP-07 no está validado.

Runner corregido en c1fdcc12eb3d7a0fcb6cccccb8eb07b0028dcb40: solo el servidor CP-07 permite consumir exactamente un evento con el mensaje de excepción previsto; todos los demás errores de worker siguen siendo fatales. Repetir el runner completo únicamente en Atlas-VM-test desechable, como root, usando el comando de ejecución ya documentado. No ejecutar en greed. No se ejecutaron pruebas, builds ni workflows desde GitHub.


### CP-07 — diagnóstico de ConnectionResetError y corrección

En la ejecución del commit ccfc495e4bcbe0adc9283f75bee1823d5338451b, MA-01..MA-10 y CP-01..CP-06 pasaron, pero CP-07 falló con ConnectionResetError (ECONNRESET). El fixture lanzaba la excepción sin leer el paquete SOCK_SEQPACKET enviado por el peer. El cierre con un registro pendiente puede producir reset en lugar de EOF, así que el resultado no demuestra la recuperación esperada.

Runner corregido en 1df8385f3783308636ccd9538d4c1033fd05be33: el worker de CP-07 consume el paquete desencadenante antes de inyectar RuntimeError. El evento de inyección informa trigger_request_bytes. Se conserva la exigencia de EOF, cero respuesta, active=0, servidor vivo y segunda petición válida. Repetir únicamente en Atlas-VM-test desechable, como root; nunca en greed. No se ejecutaron pruebas, builds ni workflows.

## A-IPC-02 — CP-08/CP-09 boundary scenarios

The separate root-only mutual-auth/capacity runner now includes:

- **CP-08 request size:** a packet exactly 16 KiB reaches schema validation;
  16 KiB + 1 is rejected with `REQUEST_TOO_LARGE`; a packet larger than
  the `recvmsg(16 KiB + 1)` buffer is rejected with `MESSAGE_TRUNCATED`
  and no response envelope.
- **CP-08 response size:** the real response sender transmits an exact 64 KiB
  packet without truncation. A 64 KiB + 1 response is rejected with
  `INTERNAL_ERROR` before any peer bytes are sent.
- **CP-09 JSON depth:** total container depth 16 reaches schema validation;
  depth 17 is rejected with `INVALID_JSON`. The root JSON object counts as
  depth 1.

These cases use temporary AF_UNIX/SOCK_SEQPACKET socketpairs and the existing
IPC decoder/encoder/sender; they do not change production handler code or the
protocol contract. CP-08/CP-09 are implemented but require owner execution
on the disposable `Atlas-VM-test` before they can be called PASS.

CP-10..CP-12 remain pending: full FD/thread accounting under load, repeated
load/recovery after saturation, and startup rejection when the inherited
`RLIMIT_NOFILE` is insufficient (without raising it). The overall result
must remain INCOMPLETE until all required scenarios are implemented and
owner-validated. Never run this root-only probe on the `greed` production
server.

### A-IPC-02 — CP-08/CP-09 owner validation; CP-10 added

The owner ran commit `caf7bbb8c83388a3723b66a7f4060a01c97c171d` on the
disposable Debian 13 `Atlas-VM-test` (kernel 6.12.117, Python 3.13.5,
EUID 0; service fixture 2005/2005, alternate fixture 2006/2006):

- MA-01..MA-10 and CP-01..CP-09: PASS.
- CP-08 confirmed 16 KiB request boundary, 16 KiB+1 rejection,
  `MESSAGE_TRUNCATED` for a packet beyond the receive buffer, exact 64 KiB
  response delivery, and rejection of 64 KiB+1 before sending peer bytes.
- CP-09 confirmed total JSON depth 16 reaches schema validation and depth
  17 is rejected as `INVALID_JSON`.
- Cleanup succeeded; overall remained INCOMPLETE because CP-10..CP-12 were
  not yet implemented in the executed commit.

The runner now includes CP-10 (commits
`e02bbbb7e3eacb45fbeab620d00cf0463e1c827e` and
`bf3c62375fd8a3017b332efe406be9d1fd903568`). It samples
`/proc/<pid>/fd`, `/proc/<pid>/task`, and `/proc/<pid>/status` at
baseline, with four active workers and nine pending connections, and after
recovery. It requires no more than 64 open FDs, exactly four worker threads
plus the main thread at saturation (maximum 5), soft/hard `RLIMIT_NOFILE`
64/64, active=0 after draining, and a live server process.

CP-10 is implemented but not owner-validated. CP-11/CP-12 remain pending:
repeated saturation/recovery cycles and startup rejection under an
insufficient inherited `RLIMIT_NOFILE` without raising it. Run only in the
disposable `Atlas-VM-test`, never on `greed` production. No tests, builds
or workflows were run by the assistant.


### CP-10 — procfs reader correction (2026-11-21)

The owner ran commit `cbfe0e20a79ae3ee8fd901ba43ea6df360962398` on the disposable `Atlas-VM-test`. MA-01..MA-10 and CP-01..CP-09 passed; CP-10 stopped with `ProbeFailure: CP-10 procfs status omitted Max open files`. Sandbox cleanup succeeded. This was a probe evidence-reader failure, not an observed FD/thread limit violation.

Static review found that Linux exposes `Max open files` in `/proc/<pid>/limits`, not `/proc/<pid>/status`. Commit `47b9ed94c21d26b18c415bedd2f1d352894f2620` changes the reader to `limits` and retains the 64/64 soft/hard assertion; FD and thread counts continue to come from `fd/` and `task/`. CP-10 is statically corrected but **requires a fresh owner execution** before it can be marked PASS. CP-11/CP-12 remain pending. Run only on the disposable `Atlas-VM-test`, never on production `greed`. No tests, builds or workflows were run by the assistant.


### CP-10 — accepted-event baseline synchronization (2026-11-21)

The owner ran `892d934267684fc8d5a179993f71c2b11c614c7e`: MA-01..MA-10 and CP-01..CP-09 passed; CP-10 failed its accepted-count saturation assertion. The original error did not report baseline/observed values, so it does not establish whether a queued connection was actually accepted.

Static review found that `Server` receives stdout through an asynchronous reader thread, while CP-10 calculated `accepted_before` without first draining pending events. This could leave the baseline stale. Commit `7c009dac7fd7c4270ea6edf8bc1a004a8fb8f898` drains prior events before capturing the baseline and adds baseline/expected/observed/pending/workers to any assertion failure. The strict assertion remains unchanged in intent; real acceptance is not ignored. CP-10 still requires owner execution. No tests, builds or workflows were run by the assistant. Run only on disposable `Atlas-VM-test`.


Follow-up commit `664c398a5afdafda313eb81379cbb85a5b71007d` makes `Server.drain(duration)` observe for the full requested interval instead of returning at the first temporarily empty queue. This allows the asynchronous stdout reader to transfer already-emitted events before CP-10 captures its accepted-count baseline. The saturation assertion remains strict; CP-10 still requires owner execution.

### CP-10 — owner validation (2026-11-21)

The owner ran commit `75929e1f9f3a17e2a19bb9a98d30e7cd86b26a0a` as root on the disposable Debian 13 `Atlas-VM-test` (kernel `6.12.117+deb13-amd64`, Python 3.13.5; service fixture 2005/2005, alternate fixture 2006/2006). MA-01..MA-10 and CP-01..CP-10 all passed; overall remains INCOMPLETE only because CP-11/CP-12 are not implemented.

CP-10 observations: four active workers and nine pending connections; accepted count remained stable at saturation (22); process snapshots were baseline 4 FDs/5 threads, saturation 8 FDs/5 threads, and recovery 4 FDs/5 threads. Soft/hard `RLIMIT_NOFILE` remained 64/64, active workers returned to zero, and the server remained alive. Cleanup removed both private and traversal `/run` sandboxes after child exit. Total duration: 22.725 s.

This validates the resource-accounting scenario on the stated commit and VM only. It does not establish production resource policy or authorize a persistent listener/deployment. CP-11 repeated saturation/recovery and CP-12 low-`RLIMIT_NOFILE` startup rejection remain outstanding. No tests, builds, or workflows were run by the assistant.

### CP-11 — repeated saturation/recovery implemented (owner validation pending)

Runner commit: `70ee6a7a77dc671fe4ec26a6ca98a25a2e47e104`. CP-11 performs three consecutive cycles against the same fixture server. Each cycle occupies all four workers, queues nine AF_UNIX connections, verifies the accepted count does not advance while saturated, closes all peers, and requires all 13 accepted connections to drain. It snapshots FD/thread counts before, during, and after each cycle; FD and thread counts must return exactly to that cycle's baseline, and the server must remain alive. The scenario is harness-only and does not change production code.

CP-11 is implemented and statically reviewed, but **not yet owner-validated**. CP-12 remains unimplemented: startup rejection when the child inherits an insufficient `RLIMIT_NOFILE`, without raising the limit. Run the updated probe only on disposable `Atlas-VM-test`, never on production `greed`. The overall result must remain INCOMPLETE until CP-12 is implemented and validated.

### CP-11 — owner validation (2026-11-21)

The owner ran commit `da8c6ea9ed0ce36d2c7b4c2c8c5417dd79975fb7` on disposable `Atlas-VM-test` (Debian 13, kernel `6.12.117+deb13-amd64`, Python 3.13.5). MA-01..MA-10 and CP-01..CP-11 all passed. Three consecutive saturation/recovery cycles each held four workers and nine queued connections; accepted counts were 31→35→44, 44→48→57, and 57→61→70. Each cycle returned to 4 FDs/5 threads, with 8 FDs/5 threads at saturation, zero active workers after recovery, and the server alive. Cleanup succeeded; duration 24.72 s.

This validates CP-11 only on the stated commit and VM. CP-12 remains pending owner execution.

### CP-12 — low inherited RLIMIT_NOFILE startup rejection implemented (owner validation pending)

Runner commit: `0fb5c3989f5ac9e11b14344557b18ad7bd75027b`. The server child now rejects startup if either inherited soft or hard `RLIMIT_NOFILE` is below 64; it reports both values and returns before creating/binding the listener. CP-12 launches a fixture through a small exec wrapper that lowers both inherited limits to 32 before exec, then verifies exit code 3, the exact startup rejection event and limits, and absence of a socket pathname. It does not raise the limit. This is harness-only validation, not production policy. Static review only; the owner must run it on disposable `Atlas-VM-test`. Do not run on production `greed`.



## A-IPC-02 — validación completa por el propietario (2026-11-21)

El propietario ejecutó el runner completo en la VM desechable `Atlas-VM-test`
sobre el checkout `66b348e1be9a7e614d51c4b3ade9e643c9152106`:
Debian 13, kernel `6.12.117+deb13-amd64`, Python 3.13.5, EUID efectivo 0,
fixtures SERVICE UID/GID `2005/2005` y OTHER `2006/2006`.
Duración: 24.991 s. El JSON reportó **`overall=PASS`**, sin escenarios
omitidos ni fallidos, y confirmó la eliminación de ambos sandboxes temporales
bajo `/run` después de salir los procesos hijos.

**Resultado:** MA-01..MA-10 y CP-01..CP-12: PASS.

Observaciones relevantes:

- **Autenticación mutua (MA-01..MA-06):** cliente root autenticó servidor
  UID 2005 antes de enviar; servidor rechazó peer UID 2006 antes de leer
  (cero bytes de respuesta); cliente rechazó servidor UID 2006 antes de
  enviar (cero bytes); cliente EUID 2006 fue rechazado antes de connect.
  Claims JSON falsos UID 0/GID 0/PID 1 fueron rechazados como
  `INVALID_REQUEST`; la identidad observada provino de SO_PEERCRED.
- **Configuración/snapshot (MA-07/08):** 11 variantes inválidas rechazadas;
  configuración válida aceptada con `client_uids=[0]`; reemplazo del archivo
  no alteró el snapshot inmutable cargado.
- **Desconexión y transporte (MA-09/10):** desconexión previa a request produjo
  `PEER_DISCONNECTED`, cero respuesta; AF_UNIX/SOCK_STREAM y
  AF_INET/SOCK_STREAM fueron rechazados antes de leer.
- **Capacidad y backpressure (CP-01..04):** máximo cuatro workers; con
  `listen(8)`, Linux permitió nueve conexiones pendientes; la décima recibió
  EAGAIN (errno 11). La cola observada fue 8 y luego 9, sin exceder cuatro
  workers activos.
- **Timeouts (CP-05/06):** timeout de lectura observado en 5.009 s; el
  escenario de deadline global cerró a 15.005 s, con 3.998 s disponibles al
  comenzar la lectura después de la demora test-only.
- **Recuperación (CP-07):** excepción `RuntimeError` aislada, peer EOF y
  cero respuesta; slot liberado, servidor vivo y ping posterior `OK`.
- **Tamaños y JSON (CP-08/09):** request 16 KiB aceptado hasta schema
  validation; 16 KiB+1 rechazado; paquete truncado detectado. Response
  64 KiB enviado íntegro y tamaño superior rechazado antes de enviar.
  Profundidad JSON 16 llegó a schema validation; profundidad 17 produjo
  `INVALID_JSON`.
- **Recursos (CP-10/11):** baseline 4 FDs/5 threads; saturación 8 FDs/5
  threads; recuperación exacta a 4 FDs/5 threads, active=0 y servidor vivo.
  Tres ciclos consecutivos repitieron la recuperación sin crecimiento de
  recursos.
- **Límite heredado (CP-12):** el child heredó soft/hard
  `RLIMIT_NOFILE=32/32` frente al requisito 64; rechazó startup con exit
  code 3 y evento `startup_error`, no elevó el límite y no creó el socket.

Esta evidencia valida los escenarios del harness A-IPC-02 en el commit y VM
indicados. **No aprueba** un listener persistente, el transporte AF_UNIX
para producción, el entrypoint administrativo real, integración systemd,
acceso a SQLite, operaciones mutantes ni despliegue. El perfil de capacidad
continúa siendo experimental. No se ejecutaron pruebas, builds ni workflows
desde GitHub; el resultado fue ejecutado por el propietario. 


## A-IPC-03 — isolated path resolution probe (owner-validated PASS, 2026-11-21)

Runner: `run_path_resolution_probe.py`. Design: `docs/design/local-authority-admin-private-listener-path-resolution-probe.md`.

The harness implements PR-01..PR-12 for canonical path parsing, descriptor-relative
walk from `/`, symlink rejection at each fixture level, non-directory and
writable/foreign-owned ancestor rejection, endpoint fixture ownership/mode,
configuration loading through a validated parent descriptor, final symlink/FIFO/
hardlink rejection, descriptor anchoring after pathname replacement, and DAC
denial for OTHER UID. It creates one private root-owned sandbox under `/run`,
uses numeric fixture identities, and removes only that sandbox after child exit.
It does not create a socket, bind/connect, inspect real `/etc/atlas`, or modify
production code or host configuration.

**Owner validation:** checkout `b200c292ac0602593c8dbefafb1bd71b79001b06`, Debian 13 / kernel `6.12.117+deb13-amd64`, Python `3.13.5`, EUID 0, SERVICE fixture 2005:2005 and OTHER fixture 2006:2006. Result: `overall=PASS`, 12/12 PASS, 0 failures, duration 0.062 s; sandbox cleanup confirmed. PR-01 rejected 13/13 lexical cases; PR-03 rejected symlinks at alpha/beta/gamma with sentinel unchanged; PR-09 loaded immutable config snapshot through validated parent descriptor; PR-10 rejected symlink/FIFO/hardlink; PR-11 read `anchored-original` after pathname replacement with symlink; PR-12 denied rename/symlink for OTHER UID with errno 13 (`EACCES`).

This validates A-THREAT-06 only within the isolated fixture scope and stated commit/VM. It does not establish a production path/owner policy or approve bind, stale recovery, lifecycle, or deployment. The probe did not create a socket or perform bind/connect.

Run only in the disposable `Atlas-VM-test`, never on `greed`:

```bash
# As greed, from the VM checkout:
cd ~/atlas-dev
git fetch origin
git pull --ff-only origin experiment/a-ipc-01-private-unix-listener-probe
git rev-parse HEAD

# Then enter a root shell and wait for the root@Atlas-VM-test prompt:
sudo -i

# As root, run the isolated harness:
cd /home/greed/atlas-dev
PYTHONDONTWRITEBYTECODE=1 python3 tests/integration/private_unix_listener/run_path_resolution_probe.py \
  --service-uid 2005 \
  --service-gid 2005 \
  --other-uid 2006 \
  --other-gid 2006 \
  --confirm-disposable-vm \
  --confirm-fixture-ids
```

The run should report the exact checkout commit and `overall=PASS`, with
12 PASS scenarios and successful sandbox cleanup. If any scenario fails or
cleanup is not confirmed, preserve the complete JSON and do not rerun until
the failure is reviewed. The assistant does not run tests, builds, or workflows.


**Next gate:** A-IPC-04 design plan is published at `docs/design/local-authority-admin-private-listener-stale-recovery-probe.md`. It proposes SR-01..SR-12 and explicitly keeps runner implementation pending until namespace-coverage and procfs parsing questions are resolved. It must remain fail-closed, must not connect to test liveness, and must model namespace enumeration failures as aborts. Do not turn the maintenance procedure into automatic startup cleanup.
